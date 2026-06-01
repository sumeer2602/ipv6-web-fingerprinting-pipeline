"""
ip_fingerprints.py — Domain Fingerprints → IP-Based Fingerprints (Stage 2)

Converts domain-based fingerprints (from basicFingerprint.py) into IP-based
fingerprints by resolving each domain using pre-built JSON DNS databases.

CNAME chains are resolved recursively. For each website, separate IPv4 and
IPv6 fingerprints are produced using the corresponding A/AAAA database.

Output format (one .txt file per domain, written to --output-dir):
  Line 1: {"0": ["ipv4_1", ...], "1": ["ipv4_2", ...]}  ← IPv4 FP
  Line 2: {"0": ["ipv6_1", ...], "1": ["ipv6_2", ...]}  ← IPv6 FP
  Key "0" = primary domain IPs, key "1" = secondary domain IPs

Inputs:
  --domain-fp-dir   Directory of domain fingerprint .txt files
                    (output of basicFingerprint.py)
  --db-a            Path to database_A.json (built by build_dns_db.py)
  --db-aaaa         Path to database_AAAA.json (built by build_dns_db.py)
  --output-dir      Directory for IP fingerprint .txt files
                    (e.g. /media/chaos/v6wft/ip_based/1)

Usage:
  python ip_fingerprints.py \\
      --domain-fp-dir /media/chaos/v6wft/domain_based/chrome/1 \\
      --db-a database_A.json \\
      --db-aaaa database_AAAA.json \\
      --output-dir /media/chaos/v6wft/ip_based/1
"""

import argparse
import ast
import json
import os
import sys

sys.setrecursionlimit(5000)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert domain fingerprints to IP-based fingerprints")
    parser.add_argument("--domain-fp-dir", required=True,
                        help="Directory of domain fingerprint .txt files")
    parser.add_argument("--db-a", required=True,
                        help="Path to database_A.json (IPv4 DNS lookup)")
    parser.add_argument("--db-aaaa", required=True,
                        help="Path to database_AAAA.json (IPv6 DNS lookup)")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for IP fingerprint .txt files")
    return parser.parse_args()


def query_db(domain, db, seen_cnames=None):
    """
    Resolve a domain to a set of IPs using a flat JSON DNS database.
    Follows CNAME chains recursively (CNAMEs end with '.').
    """
    if seen_cnames is None:
        seen_cnames = set()
    ips = set()
    if domain not in db:
        return ips
    for answer in db[domain]:
        if not answer.endswith('.'):
            ips.add(answer)
        else:
            if answer in seen_cnames:
                continue
            seen_cnames.add(answer)
            ips.update(query_db(answer, db, seen_cnames))
    return ips


def make_ip_fingerprint(primary_domain_set, secondary_domain_set, db):
    """
    Build an IP fingerprint dict from sets of primary/secondary domains.
    Returns {"0": [primary_ips], "1": [secondary_ips]} (sorted lists).
    """
    primary_ips = set()
    for domain in primary_domain_set:
        primary_ips.update(query_db(domain, db))

    secondary_ips = set()
    for domain in secondary_domain_set:
        secondary_ips.update(query_db(domain, db))

    return {"0": sorted(primary_ips), "1": sorted(secondary_ips)}


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Loading database_A from {args.db_a}...")
    with open(args.db_a, 'r') as f:
        db_a = json.load(f)
    print(f"  {len(db_a):,} entries")

    print(f"Loading database_AAAA from {args.db_aaaa}...")
    with open(args.db_aaaa, 'r') as f:
        db_aaaa = json.load(f)
    print(f"  {len(db_aaaa):,} entries")

    counter = 0
    skipped = 0

    for root, _, files in os.walk(args.domain_fp_dir):
        for fname in files:
            if not fname.endswith('.txt'):
                continue
            fp_path = os.path.join(root, fname)
            try:
                with open(fp_path, 'r') as f:
                    f.readline()  # skip line 1 (timed sequence)
                    label_map = ast.literal_eval(f.readline())

                primary_domains = label_map[0]   # set of primary domain(s)
                secondary_domains = label_map[1]  # set of secondary domains

                ipv4_fp = make_ip_fingerprint(primary_domains, secondary_domains, db_a)
                ipv6_fp = make_ip_fingerprint(primary_domains, secondary_domains, db_aaaa)

                out_path = os.path.join(args.output_dir, fname)
                with open(out_path, 'w') as f:
                    f.write(json.dumps(ipv4_fp) + '\n')
                    f.write(json.dumps(ipv6_fp) + '\n')

                counter += 1
                if counter % 1000 == 0:
                    print(f"  Processed {counter:,} fingerprints...")
            except Exception as e:
                print(f"Error on {fp_path}: {e}")
                skipped += 1

    print(f"\nDone. {counter:,} IP fingerprints written to {args.output_dir}")
    if skipped:
        print(f"  Skipped {skipped} files due to errors")


if __name__ == "__main__":
    main()
