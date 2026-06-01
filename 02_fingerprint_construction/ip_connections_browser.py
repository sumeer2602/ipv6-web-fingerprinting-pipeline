"""
ip_connections_browser.py — Extract Test-Phase IP Connections (Stage 2)

For each website's test-crawl HAR file, finds the zdns snapshot captured
closest in time (at least 5 days after the crawl) and resolves every
requested domain to its IP address at that time. This produces the
"test connections" used by the fingerprint matcher.

The 5-day minimum gap ensures we use a DNS snapshot from after the crawl,
capturing the DNS state that a real fingerprinter would observe.

Output format (one .txt file per domain, written to --output-dir):
  Line 1: {"0": ["ipv4"], "1": []}  ← IPv4 connections (primary=0, secondary=1)
  Line 2: {"0": ["ipv6"], "1": []}  ← IPv6/dual-stack connections

Inputs:
  --har-dir       Browser HAR directory (test crawl batch)
                  (e.g. /media/chaos/v6wft/chrome/5)
  --zdns-dir      Directory containing all A_*.gz and AAAA_*.gz files
  --db-dir        Directory containing database_A.json and database_AAAA.json
                  (built by build_dns_db.py — used for CNAME fallback)
  --output-dir    Output directory for IP connection .txt files
                  (e.g. /media/chaos/v6wft/ip_connections/1)
  --min-gap-days  Minimum days between crawl and DNS snapshot (default: 5)

Usage:
  python ip_connections_browser.py \\
      --har-dir /media/chaos/v6wft/chrome/5 \\
      --zdns-dir /media/chaos/v6wft/domains \\
      --db-dir /path/to/db_dir \\
      --output-dir /media/chaos/v6wft/ip_connections/1
"""

import argparse
import gzip
import json
import os
import re
from datetime import datetime
from glob import glob
from urllib.parse import urlparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract test-phase IP connections from HAR files using time-synced DNS")
    parser.add_argument("--har-dir", required=True,
                        help="HAR directory for the test crawl batch")
    parser.add_argument("--zdns-dir", required=True,
                        help="Directory of A_*.gz and AAAA_*.gz zdns files")
    parser.add_argument("--db-dir", required=True,
                        help="Directory containing database_A.json and database_AAAA.json")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for IP connection .txt files")
    parser.add_argument("--min-gap-days", type=float, default=5.0,
                        help="Minimum days between crawl and DNS snapshot (default: 5)")
    return parser.parse_args()


def parse_filename_datetime(filename):
    """Extract datetime from filenames like A_2024-05-03T21.05.53.gz"""
    match = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2}', filename)
    if match:
        return datetime.strptime(match.group(), '%Y-%m-%dT%H.%M.%S')
    return None


def get_crawl_time(har_path):
    """Read crawl start time from the HAR file's first page entry."""
    with open(har_path, 'r') as f:
        har_data = json.load(f)
    return datetime.strptime(
        str(har_data['log']['pages'][0]['startedDateTime']),
        '%Y-%m-%dT%H:%M:%S.%fZ'
    )


def find_closest_zdns(crawl_time, zdns_dir, record_type, min_gap_days):
    """
    Find the zdns file of the given record type with the smallest positive time
    difference from crawl_time, subject to the minimum gap constraint.
    """
    min_gap_secs = min_gap_days * 86400
    pattern = os.path.join(zdns_dir, f"{record_type}_*.gz")
    best_file = None
    best_diff = float('inf')

    for path in glob(pattern):
        file_dt = parse_filename_datetime(os.path.basename(path))
        if file_dt:
            diff = (file_dt - crawl_time).total_seconds()
            if diff >= min_gap_secs and diff < best_diff:
                best_diff = diff
                best_file = path
    return best_file


def resolve_domain(domain, aaaa_path, a_path):
    """
    Resolve a domain to an IP address by scanning zdns files.
    Tries AAAA first, falls back to A. Follows CNAMEs recursively.
    """
    for path, record_type in [(aaaa_path, 'AAAA'), (a_path, 'A')]:
        if path is None:
            continue
        with gzip.open(path, 'rt') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('status') != 'NOERROR':
                        continue
                    answers = data.get('data', {}).get('answers', [])
                    if not answers:
                        continue
                    first = answers[0]
                    if first.get('name') != domain:
                        continue
                    if first.get('type') == record_type:
                        return first['answer']
                    elif first.get('type') == 'CNAME':
                        return resolve_domain(first['answer'], aaaa_path, a_path)
                except (json.JSONDecodeError, TypeError):
                    continue
    return None


def make_connections(har_path, aaaa_file, a_file):
    """
    Build the IP connection dict for one HAR file.
    Returns a 2-element list: [ipv4_connections, dual_connections]
    Each element is {"0": [primary_ip], "1": [secondary_ips]}.
    """
    ipv4_conn = {"0": [], "1": []}
    dual_conn = {"0": [], "1": []}
    cached = {}

    with open(har_path, 'r') as f:
        har_data = json.load(f)

    primary_domain = os.path.basename(har_path).replace('.har', '')

    for entry in har_data['log']['entries']:
        url = entry['request']['url']
        domain = urlparse(url).netloc
        if ':' in domain:
            domain = domain.split(':')[0]

        if domain not in cached:
            cached[domain] = resolve_domain(domain, aaaa_file, a_file)

        ip = cached[domain]
        if ip is None:
            continue

        key = "0" if domain == primary_domain else "1"
        # Detect IP version and route to appropriate connection dict
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
            if isinstance(addr, ipaddress.IPv6Address):
                if ip not in dual_conn[key]:
                    dual_conn[key].append(ip)
            else:
                if ip not in ipv4_conn[key]:
                    ipv4_conn[key].append(ip)
        except ValueError:
            pass

    return ipv4_conn, dual_conn


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    counter = 0
    skipped = 0

    for root, _, files in os.walk(args.har_dir):
        for fname in files:
            if not fname.endswith('.har'):
                continue
            har_path = os.path.join(root, fname)
            domain = fname.replace('.har', '')
            out_path = os.path.join(args.output_dir, domain + '.txt')

            if os.path.exists(out_path):
                continue  # already processed

            try:
                crawl_time = get_crawl_time(har_path)
                aaaa_file = find_closest_zdns(crawl_time, args.zdns_dir, 'AAAA', args.min_gap_days)
                a_file = find_closest_zdns(crawl_time, args.zdns_dir, 'A', args.min_gap_days)

                if aaaa_file is None and a_file is None:
                    print(f"No zdns files found for {domain} (crawl: {crawl_time})")
                    skipped += 1
                    continue

                ipv4_conn, dual_conn = make_connections(har_path, aaaa_file, a_file)

                with open(out_path, 'w') as f:
                    f.write(json.dumps(ipv4_conn) + '\n')
                    f.write(json.dumps(dual_conn) + '\n')

                counter += 1
                if counter % 500 == 0:
                    print(f"  Processed {counter:,} sites...")
            except Exception as e:
                print(f"Error on {har_path}: {e}")
                skipped += 1

    print(f"\nDone. {counter:,} connection files written to {args.output_dir}")
    if skipped:
        print(f"  Skipped {skipped} sites due to errors or missing DNS data")


if __name__ == "__main__":
    main()
