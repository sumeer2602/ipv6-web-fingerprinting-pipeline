"""
fill_missingip_helper.py — Retry Domains with Missing IPs (Stage 1)

Reads a CSV of IP connection data, identifies domains that have a blank primary
IP and empty secondary IPs, and re-runs a processing script for each one in
parallel. Use this after the main crawl to recover domains that failed IP
extraction on the first pass.

Inputs:
  csv_file        Path to CSV with columns: website_name, primary_IP, all_connections
  script_path     Path to the reprocessing script to invoke per domain
  domain_based    Domain fingerprint directory (passed as arg to script)
  zdns            zdns files directory (passed as arg to script)
  har_file        HAR files directory (passed as arg to script)
  network_trace   Network trace directory (passed as arg to script)
  --workers       Number of parallel workers (default: 10)

Usage:
  python fill_missingip_helper.py ip_connections.csv \\
      fill_missing_cons.py \\
      /media/chaos/v6wft/domain_based/chrome/1 \\
      /media/chaos/v6wft/domains \\
      /media/chaos/v6wft/chrome/1 \\
      /media/chaos/v6wft/ip_connections/1 \\
      --workers 10
"""

import argparse
import csv
import multiprocessing
import subprocess
from multiprocessing import Manager


def load_domains(csv_file):
    """Find domains with missing primary IP and empty secondary connections."""
    domains = []
    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 3:
                continue
            website_name, primary_ip, secondary_ips = row[0], row[1], row[2].strip()
            if primary_ip == "" and secondary_ips in ("[]", "null", "None"):
                domains.append(website_name)
    return domains


def process_domain(args):
    """Invoke the reprocessing script for one domain."""
    website_name, script_path, domain_based, zdns, har_file, network_trace, total, counter_queue = args
    try:
        print(f"Processing: {website_name}")
        subprocess.run(
            ["python3", script_path, website_name, domain_based, zdns, har_file, network_trace],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error on {website_name}: {e}")
    finally:
        counter_queue.put(1)


def main():
    parser = argparse.ArgumentParser(description="Retry domains with missing IP connections")
    parser.add_argument("csv_file", help="CSV with website_name, primary_IP, all_connections")
    parser.add_argument("script_path", help="Reprocessing script to call per domain")
    parser.add_argument("domain_based", help="Domain fingerprint directory")
    parser.add_argument("zdns", help="zdns files directory")
    parser.add_argument("har_file", help="HAR files directory")
    parser.add_argument("network_trace", help="Network trace / ip_connections output directory")
    parser.add_argument("--workers", type=int, default=10, help="Parallel workers (default: 10)")
    args = parser.parse_args()

    domains = load_domains(args.csv_file)
    if not domains:
        print("No domains with missing IP data found.")
        return

    total = len(domains)
    print(f"Found {total} domains to retry.")

    with Manager() as manager:
        counter_queue = manager.Queue()
        task_args = [
            (d, args.script_path, args.domain_based, args.zdns,
             args.har_file, args.network_trace, total, counter_queue)
            for d in domains
        ]
        n_workers = min(args.workers, total)
        with multiprocessing.Pool(processes=n_workers) as pool:
            pool.map_async(process_domain, task_args)
            done = 0
            while done < total:
                counter_queue.get()
                done += 1
                print(f"Progress: {done}/{total}", end='\r', flush=True)
    print(f"\nFinished {total} domains.")


if __name__ == "__main__":
    main()
