"""
ip_entropy.py — IP Address Entropy Calculation (Stage 3)

Computes Shannon entropy for each IP address across all AAAA DNS records.
An IP shared by many domains (high co-location, like a large CDN) has low
entropy and provides weak fingerprinting signal. A unique or rare IP has
high entropy and is a strong fingerprinting signal.

Formula:  H(ip) = -log2( occurrence(ip) / total_unique_ips )

The entropy values are used by fp_testing_opt.py to weight IP matches.

Inputs:
  --zdns-file   Path to a zdns AAAA output file (gzip or plain JSON lines)
                (e.g. /media/chaos/v6wft/domains/AAAA_2024-04-15T23.23.11.gz)
  --output      Output CSV file path (e.g. ip_entropy_AAAA.csv)

Output CSV columns:
  ip        The IPv6 address
  entropy   Shannon entropy value (higher = rarer = more discriminating)

Usage:
  python ip_entropy.py \\
      --zdns-file /media/chaos/v6wft/domains/AAAA_2024-04-15T23.23.11.gz \\
      --output ip_entropy_AAAA.csv

  # For IPv4 (using an A record zdns file):
  python ip_entropy.py \\
      --zdns-file /media/chaos/v6wft/domains/A_2024-04-15T23.18.47.gz \\
      --output ip_entropy_A.csv

Notes:
  - Reads the zdns file once to build domain→IP mapping, then computes entropy
  - Can handle both gzip (.gz) and plain JSON lines files
"""

import argparse
import csv
import gzip
import json
import math


def parse_args():
    parser = argparse.ArgumentParser(description="Compute Shannon entropy for each IP address")
    parser.add_argument("--zdns-file", required=True,
                        help="zdns output file (.gz or plain JSON lines)")
    parser.add_argument("--output", required=True,
                        help="Output CSV file path")
    return parser.parse_args()


def build_domain_ip_map(zdns_file):
    """
    Parse a zdns output file and build a dict of domain → set of IP answers.
    Only AAAA or A answers are included (not CNAME targets).
    """
    domain_ip_dict = {}
    open_fn = gzip.open if zdns_file.endswith('.gz') else open

    print(f"Reading {zdns_file}...")
    with open_fn(zdns_file, 'rt') as f:
        for line in f:
            try:
                data = json.loads(line)
                domain = data.get('name')
                if not domain:
                    continue
                if data.get('status') != 'NOERROR':
                    continue
                answers = data.get('data', {}).get('answers', [])
                for answer in answers:
                    ans_type = answer.get('type', '')
                    if ans_type in ('A', 'AAAA'):
                        ip = answer.get('answer')
                        if ip:
                            if domain not in domain_ip_dict:
                                domain_ip_dict[domain] = set()
                            domain_ip_dict[domain].add(ip)
            except json.JSONDecodeError:
                continue

    print(f"  Domains with records: {len(domain_ip_dict):,}")
    return domain_ip_dict


def compute_and_write_entropy(domain_ip_dict, output_csv):
    """Compute per-IP entropy and write to CSV."""
    # Collect all unique IPs across all domains
    all_ips = set()
    for ips in domain_ip_dict.values():
        all_ips.update(ips)

    total_unique = len(all_ips)
    print(f"  Unique IP addresses: {total_unique:,}")

    with open(output_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ip', 'entropy'])
        for i, ip in enumerate(all_ips):
            # Count how many domains map to this IP
            occurrence = sum(1 for ips in domain_ip_dict.values() if ip in ips)
            probability = occurrence / total_unique
            entropy = -math.log2(probability)
            writer.writerow([ip, entropy])
            if (i + 1) % 100000 == 0:
                print(f"  Written {i+1:,}/{total_unique:,}...")

    print(f"IP entropy written to {output_csv}")


def main():
    args = parse_args()
    domain_ip_dict = build_domain_ip_map(args.zdns_file)
    compute_and_write_entropy(domain_ip_dict, args.output)


if __name__ == "__main__":
    main()
