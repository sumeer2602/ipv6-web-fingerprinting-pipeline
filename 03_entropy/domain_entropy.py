"""
domain_entropy.py — Domain Entropy Calculation (Stage 3)

Computes the Shannon information entropy for each domain across all website
fingerprints. A domain with high entropy (rare, appears in few fingerprints)
provides strong discriminating power. A domain with low entropy (common CDN)
provides little information.

Formula:  H(d) = -log2( count(d) / sum_of_all_domain_counts )

The entropy values are used by fp_testing_opt.py to score fingerprint matches.

Inputs:
  --domain-fp-dir   Directory of domain fingerprint .txt files
                    (output of basicFingerprint.py)
  --output          Output CSV file path (e.g. domain_entropy.csv)

Output CSV columns:
  domain    The domain name
  entropy   Shannon entropy value (higher = rarer = more discriminating)

Usage:
  python domain_entropy.py \\
      --domain-fp-dir /media/chaos/v6wft/domain_based/chrome/1 \\
      --output domain_entropy.csv
"""

import argparse
import ast
import csv
import math
import os
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser(description="Compute Shannon entropy for each domain")
    parser.add_argument("--domain-fp-dir", required=True,
                        help="Directory of domain fingerprint .txt files")
    parser.add_argument("--output", required=True,
                        help="Output CSV file path")
    return parser.parse_args()


def read_domain_sets(directory):
    """
    Read all domain fingerprint .txt files and return a list of domain sets
    (one set per website, combining primary and secondary domains).
    """
    domains_per_website = []
    files = [f for f in os.listdir(directory) if f.endswith('.txt')]
    print(f"Reading {len(files):,} fingerprint files...")

    for i, fname in enumerate(files):
        if i % 10000 == 0 and i > 0:
            print(f"  {i:,}/{len(files):,}...")
        path = os.path.join(directory, fname)
        try:
            with open(path, 'r') as f:
                f.readline()  # skip timed sequence (line 1)
                label_map = ast.literal_eval(f.readline())
            # Combine primary (key 0) and secondary (key 1) domain sets
            all_domains = label_map[0].union(label_map[1])
            domains_per_website.append(all_domains)
        except Exception as e:
            print(f"  Warning: could not parse {fname}: {e}")

    return domains_per_website


def calculate_entropy(domains_per_website, output_csv):
    """Compute frequency-based Shannon entropy for each domain and write CSV."""
    domain_counts = defaultdict(int)
    for website_domains in domains_per_website:
        for domain in website_domains:
            domain_counts[domain] += 1

    total = sum(domain_counts.values())
    print(f"Total domain occurrences across all sites: {total:,}")
    print(f"Unique domains: {len(domain_counts):,}")

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['domain', 'entropy'])
        for domain, count in domain_counts.items():
            p = count / total
            entropy = -math.log2(p)
            writer.writerow([domain, entropy])

    print(f"Entropy written to {output_csv}")


def main():
    args = parse_args()
    domains_per_website = read_domain_sets(args.domain_fp_dir)
    print(f"Loaded fingerprints for {len(domains_per_website):,} websites")
    calculate_entropy(domains_per_website, args.output)


if __name__ == "__main__":
    main()
