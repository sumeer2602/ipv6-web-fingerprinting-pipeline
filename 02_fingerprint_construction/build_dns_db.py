"""
build_dns_db.py — Build Flat JSON DNS Lookup Database (Stage 2)

Reads all zdns gzip output files for a given record type (A or AAAA) and
builds a flat JSON dictionary mapping each domain name to the list of answers
it received (IPs or CNAME targets).

This database is used by ip_fingerprints.py to resolve domain fingerprints to
IP-based fingerprints without re-querying DNS.

CNAME targets are stored with their trailing dot (e.g. "cdn.example.net.")
so they can be detected and resolved recursively during lookup.

Output format (database_A.json or database_AAAA.json):
  {
    "example.com":    ["93.184.216.34"],
    "www.example.com":["cdn.example.net."],    ← CNAME, trailing dot
    "cdn.example.net":["93.184.216.34"]
  }

Inputs:
  --zdns-dir      Directory containing zdns gzip files (A_*.gz or AAAA_*.gz)
  --output        Output JSON file path (e.g. database_AAAA.json)
  --record-type   A or AAAA (default: AAAA)

Usage:
  # Build IPv6 database:
  python build_dns_db.py --zdns-dir /media/chaos/v6wft/domains \\
                         --output database_AAAA.json --record-type AAAA

  # Build IPv4 database:
  python build_dns_db.py --zdns-dir /media/chaos/v6wft/domains \\
                         --output database_A.json --record-type A

Notes:
  - Incremental: if --output already exists, new entries are merged in
  - Database files can be several GB for a full 550k-domain dataset
  - Run separately for A and AAAA records; both are needed by ip_fingerprints.py
"""

import argparse
import glob
import gzip
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(description="Build flat JSON DNS lookup database from zdns outputs")
    parser.add_argument("--zdns-dir", required=True,
                        help="Directory containing zdns gzip files")
    parser.add_argument("--output", required=True,
                        help="Output JSON file (e.g. database_AAAA.json)")
    parser.add_argument("--record-type", choices=["A", "AAAA"], default="AAAA",
                        help="DNS record type to process (default: AAAA)")
    return parser.parse_args()


def update_database(file_path, database):
    """Parse one zdns gzip file and add all answers to the database dict."""
    with gzip.open(file_path, 'rt') as f:
        for line in f:
            try:
                data = json.loads(line)
                domain = data.get('name')
                if not domain:
                    continue
                if data.get('status') != 'NOERROR':
                    continue
                answers = data.get('data', {}).get('answers', [])
                if not answers:
                    continue
                if domain not in database:
                    database[domain] = []
                for answer in answers:
                    value = answer.get('answer')
                    if value and value not in database[domain]:
                        database[domain].append(value)
            except json.JSONDecodeError:
                continue


def main():
    args = parse_args()

    # Load existing database if present (incremental mode)
    if os.path.exists(args.output):
        print(f"Loading existing database from {args.output}...")
        with open(args.output, 'r') as f:
            database = json.load(f)
        print(f"  Loaded {len(database):,} existing entries")
    else:
        database = {}

    pattern = os.path.join(args.zdns_dir, f"{args.record_type}_*.gz")
    files = sorted(glob.glob(pattern))
    print(f"Found {len(files)} {args.record_type} zdns files in {args.zdns_dir}")

    for i, path in enumerate(files):
        print(f"[{i+1}/{len(files)}] Processing {os.path.basename(path)}...")
        update_database(path, database)

    print(f"Writing {len(database):,} entries to {args.output}...")
    with open(args.output, 'w') as f:
        json.dump(database, f)
    print(f"Done. Database saved to {args.output}")


if __name__ == "__main__":
    main()
