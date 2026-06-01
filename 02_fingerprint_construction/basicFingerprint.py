"""
basicFingerprint.py — HAR → Domain-Based Fingerprints (Stage 2)

Walks a directory of Browsertime HAR files and extracts a domain-based
fingerprint for each website. A fingerprint records:
  - The timed sequence of all domain requests during the page load
  - The set of primary and secondary domains contacted

Output format (one .txt file per domain):
  Line 1: [(relative_time_secs, 'domain'), ...]  ← timed request sequence
  Line 2: {0: {'primary.com'}, 1: {'cdn.net', 'analytics.com', ...}}
            └─ key 0 = primary domain, key 1 = secondary domains

Inputs:
  --har-dir     Directory containing browsertime output (HAR files)
                Structure: <har_dir>/<domain>/<domain>.har
                (e.g. /media/chaos/v6wft/chrome/1)
  --output-dir  Directory where domain fingerprint .txt files will be written
                (e.g. /media/chaos/v6wft/domain_based/chrome/1)

Usage:
  python basicFingerprint.py \\
      --har-dir /media/chaos/v6wft/chrome/1 \\
      --output-dir /media/chaos/v6wft/domain_based/chrome/1
"""

import argparse
import json
import os
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="Extract domain-based fingerprints from HAR files")
    parser.add_argument("--har-dir", required=True,
                        help="Directory containing browsertime HAR files")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for domain fingerprint .txt files")
    return parser.parse_args()


def parse_har_file(har_file_path):
    """
    Parse a HAR file and return the timed domain request sequence and secondary domains.

    Returns:
        primary_domain (str): The crawled domain (from filename)
        domain_sequence (list): [(relative_time_secs, domain), ...]
        secondary_domains (set): All domains contacted besides the primary
    """
    with open(har_file_path, 'r') as f:
        har_data = json.load(f)

    primary_domain = os.path.basename(har_file_path).replace('.har', '')
    domain_sequence = []
    secondary_domains = set()
    first_request_time = None

    for entry in har_data['log']['entries']:
        try:
            start_time = datetime.strptime(str(entry['startedDateTime']), '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            start_time = datetime.strptime('2024-01-01T00:00:00.000Z', '%Y-%m-%dT%H:%M:%S.%fZ')

        if first_request_time is None:
            first_request_time = start_time

        relative_time = round((start_time - first_request_time).total_seconds(), 3)
        domain = entry['request']['url'].split('/')[2]  # extract host from URL

        if domain != primary_domain:
            secondary_domains.add(domain)
        domain_sequence.append((relative_time, domain))

    return primary_domain, domain_sequence, secondary_domains


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    counter = 0
    for root, _, files in os.walk(args.har_dir):
        for fname in files:
            if not fname.endswith('.har'):
                continue
            har_path = os.path.join(root, fname)
            try:
                primary_domain, domain_sequence, secondary_domains = parse_har_file(har_path)

                # Write output: line 1 = timed sequence, line 2 = label map
                label_map = f"{{0: {{'{primary_domain}'}}, 1: {secondary_domains}}}"
                out_path = os.path.join(args.output_dir, primary_domain + '.txt')
                with open(out_path, 'w') as f:
                    f.write(str(domain_sequence) + '\n')
                    f.write(label_map + '\n')

                counter += 1
                print(f"[{counter}] {primary_domain}")
            except Exception as e:
                print(f"Error processing {har_path}: {e}")

    print(f"\nDone. Wrote {counter} fingerprint files to {args.output_dir}")


if __name__ == "__main__":
    main()
