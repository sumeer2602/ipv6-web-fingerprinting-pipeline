"""
website_ip.py — Extract Primary IP per Website (Stage 6)

For each website in fp_match_results.csv, extracts its primary IPv4 and IPv6
addresses from the zdns A/AAAA record files. This mapping is used by
colocation_table.py to look up the hosting provider.

Only websites with at least one IPv6 address are included (IPv6-only analysis).

Inputs:
  --fp-results  fp_match_results.csv (provides the list of test sites)
  --zdns-a      Path to a zdns A record gzip file
  --zdns-aaaa   Path to a zdns AAAA record gzip file
  --output      Output CSV path (default: website_ip.csv)

Output CSV columns:
  website_name    Domain name
  ipv4_address    Primary IPv4 address (empty if none)
  ipv6_address    Primary IPv6 address

Usage:
  python website_ip.py \\
      --fp-results /media/chaos/v6wft/ip_connections/1/fp_match_results.csv \\
      --zdns-a /path/to/A_2024-04-15T23.18.47.gz \\
      --zdns-aaaa /path/to/AAAA_2024-04-15T23.23.11.gz \\
      --output website_ip.csv
"""

import argparse
import gzip
import json
from collections import defaultdict

import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="Extract primary IPv4/IPv6 per website")
    parser.add_argument("--fp-results", required=True,
                        help="fp_match_results.csv")
    parser.add_argument("--zdns-a", required=True,
                        help="zdns A record gzip file")
    parser.add_argument("--zdns-aaaa", required=True,
                        help="zdns AAAA record gzip file")
    parser.add_argument("--output", default="website_ip.csv",
                        help="Output CSV path (default: website_ip.csv)")
    return parser.parse_args()


def resolve_final_ips(domain, cname_map, ip_map, visited=None):
    """Follow CNAME chain and return resolved IPs."""
    if visited is None:
        visited = set()
    if domain in visited:
        return set()
    visited.add(domain)
    if domain in ip_map:
        return set(ip_map[domain])
    if domain in cname_map:
        return resolve_final_ips(cname_map[domain], cname_map, ip_map, visited)
    return set()


def build_resolved_map(zdns_file, ipv6=False):
    """
    Parse a zdns gzip file and return dict of domain → [resolved IPs].
    CNAME chains are followed to find the final IP.
    """
    resolved_map = {}
    record_type = "AAAA" if ipv6 else "A"
    open_fn = gzip.open if zdns_file.endswith(".gz") else open

    print(f"Parsing {zdns_file}...")
    with open_fn(zdns_file, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                domain = entry.get("name")
                answers = entry.get("data", {}).get("answers", [])

                ip_map = defaultdict(list)
                cname_map = {}

                for ans in answers:
                    typ = ans.get("type")
                    name = ans.get("name")
                    answer = ans.get("answer")
                    if not name or not answer:
                        continue
                    if typ == "CNAME":
                        cname_map[name] = answer.rstrip(".")
                    elif typ == record_type:
                        ip_map[name].append(answer)

                resolved = resolve_final_ips(domain, cname_map, ip_map)
                if resolved:
                    resolved_map[domain] = list(resolved)
            except Exception:
                continue

    print(f"  Resolved {len(resolved_map):,} domains")
    return resolved_map


def main():
    args = parse_args()

    fp = pd.read_csv(args.fp_results)
    websites = fp["test_site"].unique()
    print(f"Test sites to look up: {len(websites):,}")

    ipv4_map = build_resolved_map(args.zdns_a, ipv6=False)
    ipv6_map = build_resolved_map(args.zdns_aaaa, ipv6=True)

    rows = []
    skipped = 0
    for site in websites:
        ipv4s = ipv4_map.get(site, [])
        ipv6s = ipv6_map.get(site, [])
        if not ipv6s:
            skipped += 1
            continue  # skip sites with no IPv6
        rows.append({
            "website_name": site,
            "ipv4_address": ipv4s[0] if ipv4s else "",
            "ipv6_address": ipv6s[0]
        })

    df = pd.DataFrame(rows)
    df.to_csv(args.output, index=False)
    print(f"\nSaved {len(df):,} entries to {args.output}")
    print(f"Skipped {skipped:,} sites with no IPv6 address")


if __name__ == "__main__":
    main()
