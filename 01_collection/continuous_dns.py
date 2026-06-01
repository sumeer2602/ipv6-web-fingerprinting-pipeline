"""
continuous_dns.py — Continuous DNS Collection (Stage 1)

Runs periodically (via cron or a loop) to:
  1. Extract all unique domains seen across HAR files in completed crawl batches
  2. Run zdns to resolve those domains for both A and AAAA records
  3. Save gzip-compressed JSON output files timestamped at collection time

This is designed to run *concurrently with the crawler* so that DNS snapshots
are captured close in time to each site's crawl. The resulting timestamped zdns
files are later used by ip_connections_browser.py (Stage 2) to find the DNS
state at the time of each crawl.

Inputs:
  --output-dir   Base directory containing crawl output and domain data
                 (e.g. /media/chaos/v6wft). Expects subdirs: chrome/, brave/, index/
  --workers      Number of multiprocessing workers for HAR parsing (default: 4)

Outputs:
  <output_dir>/domains/A_<timestamp>.gz    ← zdns A record results
  <output_dir>/domains/AAAA_<timestamp>.gz ← zdns AAAA record results
  ./parsed_har_files.gz   ← tracks which HAR files have already been processed
  ./parsed_zdns_files.gz  ← tracks which zdns files have already been parsed

Prerequisites:
  - zdns installed and in PATH
  - /tmp/domains must be writable (temporary domain list for zdns)

Usage:
  # Run once (call repeatedly via cron during crawl):
  python continuous_dns.py --output-dir /media/chaos/v6wft --workers 8

  # Example cron entry (every 20 minutes):
  # */20 * * * * python /path/to/continuous_dns.py --output-dir /media/chaos/v6wft --workers 8
"""

import argparse
import gzip
import json
import os
import time
from datetime import datetime
from multiprocessing import Manager, Process
from subprocess import Popen, CalledProcessError
from urllib.parse import urlparse

DNS_RESOLVERS = "1.1.1.1,8.8.8.8,9.9.9.9,1.0.0.1,8.8.4.4,149.112.112.112"
DOMAIN_TEMP_FILE = "/tmp/domains"


def parse_args():
    parser = argparse.ArgumentParser(description="Continuous DNS resolution alongside web crawl")
    parser.add_argument("--output-dir", required=True,
                        help="Base crawl directory (e.g. /media/chaos/v6wft)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel HAR-parsing workers (default: 4)")
    return parser.parse_args()


def read_hars(har_files, all_domains, master_path):
    """Parse a subset of HAR files and add unique domains to the shared dict."""
    local_domains = set()
    for file in har_files:
        try:
            primary_domain = file.split('/')[-1][:-4]  # strip .har
            local_domains.add(primary_domain)
            with open(os.path.join(master_path, file), 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"JSON error in {file}: {e}")
                    continue
                for entry in data['log']['entries']:
                    url = entry['request']['url']
                    domain = urlparse(url).netloc
                    if ':' in domain:
                        domain = domain.split(':')[0]
                    local_domains.add(domain)
        except FileNotFoundError:
            continue

    for domain in local_domains:
        all_domains[domain] = 1


def main():
    t0 = time.time()
    args = parse_args()
    master_path = args.output_dir

    manager = Manager()
    all_domains = manager.dict()
    already_parsed_hars = set()

    # Load previously parsed HAR file list
    if os.path.exists('./parsed_har_files.gz'):
        with gzip.open('./parsed_har_files.gz', 'rt') as f:
            for line in f:
                already_parsed_hars.add(line.strip())
    print(f"Previously parsed HAR files: {len(already_parsed_hars)}")

    # Find new HAR files to parse (from completed, settled batch index files)
    tobe_parsed = []
    for browser in ['chrome', 'brave']:
        for batch_number in range(1, 50):
            index_path = os.path.join(master_path, 'index', f'{browser}_{batch_number}')
            if os.path.exists(index_path):
                age_seconds = time.time() - os.path.getmtime(index_path)
                if age_seconds > 300:  # Only process index files older than 5 minutes
                    with open(index_path, 'r') as f:
                        for line in f:
                            entry = line.strip()
                            if entry and entry not in already_parsed_hars:
                                tobe_parsed.append(entry)

    print(f"New HAR files to parse: {len(tobe_parsed)}")

    # Parse HAR files in parallel
    if tobe_parsed:
        chunk_size = max(1, len(tobe_parsed) // args.workers)
        processes = []
        for i in range(args.workers):
            chunk = tobe_parsed[i * chunk_size: (i + 1) * chunk_size]
            p = Process(target=read_hars, args=(chunk, all_domains, master_path))
            p.start()
            processes.append(p)
        for p in processes:
            p.join()

        with gzip.open('./parsed_har_files.gz', 'at') as f:
            for entry in tobe_parsed:
                f.write(entry + '\n')

    all_domains_set = set(all_domains.keys())

    # Also extract domains from existing ZDNS outputs (CNAME targets etc.)
    already_parsed_zdns = set()
    if os.path.exists('./parsed_zdns_files.gz'):
        with gzip.open('./parsed_zdns_files.gz', 'rt') as f:
            for line in f:
                already_parsed_zdns.add(line.strip())

    import glob
    new_zdns_files = []
    for path in sorted(glob.glob(os.path.join(master_path, 'domains', 'A*'))):
        if path not in already_parsed_zdns:
            new_zdns_files.append(path)

    for path in new_zdns_files:
        print(f"Scanning ZDNS file: {path}")
        with gzip.open(path, 'rt') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    all_domains_set.add(data['name'])
                    for answer in data.get('data', {}).get('answers', []):
                        if answer.get('type') == 'CNAME':
                            all_domains_set.add(answer['answer'])
                except (json.JSONDecodeError, KeyError):
                    continue

    with gzip.open('./parsed_zdns_files.gz', 'at') as f:
        for path in new_zdns_files:
            f.write(path + '\n')

    # Write domain list for zdns
    with open(DOMAIN_TEMP_FILE, 'w') as f:
        for domain in all_domains_set:
            f.write(domain + '\n')
    print(f"Total unique domains for zdns: {len(all_domains_set)}")

    # Run zdns for A and AAAA records
    domains_dir = os.path.join(master_path, 'domains')
    os.makedirs(domains_dir, exist_ok=True)

    for record_type in ['A', 'AAAA']:
        ts = datetime.now().strftime("%Y-%m-%dT%H.%M.%S")
        output_file = os.path.join(domains_dir, f"{record_type}_{ts}")
        cmd = (f"zdns {record_type} --input-file {DOMAIN_TEMP_FILE} "
               f"--output-file {output_file} "
               f"--retries 6 --name-servers={DNS_RESOLVERS}")
        print(f"Running zdns {record_type}...")
        try:
            Popen(cmd, shell=True).wait()
        except CalledProcessError as e:
            print(f"zdns error ({record_type}): {e}")
            continue
        Popen(f"gzip --best {output_file}", shell=True).wait()
        print(f"Saved: {output_file}.gz")

    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
