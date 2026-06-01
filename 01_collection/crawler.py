"""
crawler.py — Web Crawler (Stage 1)

Crawls a list of domains using Browsertime with both Chrome and Brave browsers,
capturing HAR files and performance metrics per domain per batch.

Inputs:
  --domain-list   CSV file with one domain per line
  --output-dir    Base directory for crawl output (e.g. /media/chaos/v6wft)
  --workers       Number of parallel browser workers (default: 25)
  --batch         Batch number (integer, e.g. 1 for first batch)

Outputs:
  <output_dir>/chrome/<batch>/<domain>/<domain>.har
  <output_dir>/chrome/<batch>/<domain>/<domain>.json
  <output_dir>/brave/<batch>/<domain>/<domain>.har
  <output_dir>/brave/<batch>/<domain>/<domain>.json
  <output_dir>/failed/<browser>/<batch>/<domain>  ← retry counter if crawl fails

Prerequisites:
  - browsertime installed globally (npm install -g browsertime)
  - Chrome and Brave browsers installed
  - Xvfb installed (for headless display)
  - Run under a display server or Xvfb will be started per-domain

Usage:
  python crawler.py --domain-list data/tranco_full_24.csv \\
                    --output-dir /media/chaos/v6wft \\
                    --workers 25 --batch 1

Notes:
  - Processes 1000 randomly sampled domains per run (re-run to cover all domains)
  - Retries up to 3 times per domain; further failures are skipped
  - Tries https:// first, falls back to http:// on timeout
"""

import argparse
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from subprocess import check_output, CalledProcessError, TimeoutExpired


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl domains with Browsertime (Chrome + Brave)")
    parser.add_argument("--domain-list", required=True, help="Path to CSV file with one domain per line")
    parser.add_argument("--output-dir", required=True, help="Base output directory (e.g. /media/chaos/v6wft)")
    parser.add_argument("--workers", type=int, default=25, help="Number of parallel workers (default: 25)")
    parser.add_argument("--batch", type=int, required=True, help="Batch number (e.g. 1)")
    return parser.parse_args()


def export_retry_count(result_dir, output_dir):
    failed_path = result_dir.replace(output_dir, os.path.join(output_dir, "failed"))
    if os.path.exists(failed_path):
        with open(failed_path, 'r') as f:
            retries = int(f.read().strip())
        with open(failed_path, 'w') as f:
            f.write(str(retries + 1))
    else:
        os.makedirs(os.path.dirname(failed_path), exist_ok=True)
        with open(failed_path, 'w') as f:
            f.write('1')


def run_browsertime(domain, domains, master_path, batch_number):
    domain_index = domains.index(domain)
    display_port = 1025 + domain_index

    for _browser in ['chrome', 'brave']:
        result_dir = os.path.join(master_path, _browser, str(batch_number), domain)
        failed_path = result_dir.replace(master_path, os.path.join(master_path, "failed"))

        # Skip if already failed too many times
        if os.path.exists(failed_path):
            with open(failed_path, 'r') as f:
                retries = int(f.read().strip())
            if retries > 3:
                print(f"Skipping {domain} ({_browser}): exceeded retry limit")
                continue

        # Skip if already crawled successfully
        if os.path.exists(result_dir):
            if os.path.exists(os.path.join(result_dir, f"{domain}.json")) and \
               os.path.exists(os.path.join(result_dir, f"{domain}.har")):
                continue
            else:
                # Clean up stale incomplete directory (older than 10 min)
                if os.path.getctime(result_dir) < time.time() - 600:
                    try:
                        check_output(f'sudo rm -rf {result_dir}', shell=True)
                    except CalledProcessError:
                        pass
                else:
                    continue

        brave_extra = ""
        if _browser == 'brave':
            display_port += 1_000_000
            brave_extra = '--chrome.binaryPath "/usr/bin/brave-browser" --timeToSettle 5000'

        for scheme in ['https', 'http']:
            print(f"Crawling {domain} ({_browser}, {scheme})")
            cmd = f"""browsertime \\
                --timeouts.browserStart 120000 \\
                --timeouts.script 180000 \\
                --chrome.includeResponseBodies none \\
                --chrome.ignoreCertificateErrors true \\
                {brave_extra} \\
                --chrome.args="--incognito" \\
                --screenshot true \\
                --screenshotParams.jpg.quality 100 \\
                --screenshotParams.maxSize 2000 \\
                --viewPort 1920x1080 \\
                --video false \\
                --visualMetrics false \\
                --browser chrome \\
                --iterations 1 \\
                --resultDir {result_dir} \\
                --output {domain} \\
                --har {domain} \\
                --useSameDir true \\
                --xvfb true \\
                --xvfbParams.display {display_port} \\
                {scheme}://{domain}/"""
            try:
                check_output(cmd, shell=True, timeout=300)
                if os.path.exists(os.path.join(result_dir, f"{domain}.har")):
                    print(f"Done: {domain} ({_browser}, {scheme})")
                    break
                raise CalledProcessError(1, cmd)
            except (CalledProcessError, TimeoutExpired) as e:
                display_port += 1_000_000
                if scheme == 'http':
                    print(f"Failed: {domain} ({_browser}): {e}")
                    export_retry_count(result_dir, master_path)
                    return


def main():
    args = parse_args()

    domains = []
    with open(args.domain_list, 'r') as f:
        for line in f:
            d = line.strip().lower()
            if d:
                domains.append(d)

    random.shuffle(domains)
    domains = domains[:1000]  # Process 1000 per run; re-run to cover all domains
    print(f"Crawling {len(domains)} domains (batch {args.batch})")

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        executor.map(lambda d: run_browsertime(d, domains, args.output_dir, args.batch), domains)


if __name__ == "__main__":
    main()
