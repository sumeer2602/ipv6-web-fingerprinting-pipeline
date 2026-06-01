"""
domains_per_ip_db.py — Domains-per-IP Distribution from PostgreSQL (Stage 2)

Queries the PostgreSQL DNS database for a single A and AAAA snapshot
(identified by timestamp) and counts how many unique domain names resolve
to each IP address. CNAME chains are followed recursively.

This produces the co-location degree distribution used in Figure 1 of the
paper (domains-per-IP CDF).

Alternative: if you do not have the PostgreSQL database, use
  06_provider_analysis/domain_per_ip.py with the raw zdns gzip files directly.

Inputs:
  --db-url         PostgreSQL connection URL
  --a-timestamp    Snapshot timestamp for A records (format: "YYYY-MM-DD HH:MM:SS")
  --aaaa-timestamp Snapshot timestamp for AAAA records
  --output-dir     Directory for output CSVs

Outputs:
  domains_per_ipv4.csv   columns: ip_address, domain_count
  domains_per_ipv6.csv   columns: ip_address, domain_count

Usage:
  python domains_per_ip_db.py \\
      --db-url          postgresql://localhost/zdns_data \\
      --a-timestamp    "2024-04-29 14:00:42" \\
      --aaaa-timestamp "2024-04-29 14:05:24" \\
      --output-dir      /path/to/output/
"""

import argparse
import csv
import ipaddress
from collections import defaultdict

import psycopg2


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute domains-per-IP distribution from the PostgreSQL DNS database")
    parser.add_argument("--db-url", default="postgresql://localhost/zdns_data",
                        help="PostgreSQL connection URL")
    parser.add_argument("--a-timestamp", required=True,
                        help="Snapshot timestamp for A records: 'YYYY-MM-DD HH:MM:SS'")
    parser.add_argument("--aaaa-timestamp", required=True,
                        help="Snapshot timestamp for AAAA records: 'YYYY-MM-DD HH:MM:SS'")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to write domains_per_ipv4.csv and domains_per_ipv6.csv")
    return parser.parse_args()


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _is_ipv4(value):
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def _is_ipv6(value):
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


def _resolve_cname(cursor, table, cname, visited, timestamp):
    """Follow a CNAME chain and return the set of resolved IP addresses."""
    if _is_ip(cname) or cname in visited:
        return set()
    visited.add(cname)
    cursor.execute(
        f"SELECT r.ip_address FROM {table} r "
        "JOIN domains d ON r.domain_id = d.domain_id "
        "WHERE d.domain_name = %s AND r.timestamp = %s",
        (cname, timestamp)
    )
    results = set()
    for (ip_or_cname,) in cursor.fetchall():
        if _is_ip(ip_or_cname):
            results.add(ip_or_cname)
        else:
            results.update(_resolve_cname(cursor, table, ip_or_cname, visited.copy(), timestamp))
    return results


def collect_ip_domain_counts(conn, table, timestamp):
    """
    Query one DNS snapshot table and return two dicts:
      ipv4_to_domains : ip → set of domain names
      ipv6_to_domains : ip → set of domain names
    """
    ipv4_to_domains = defaultdict(set)
    ipv6_to_domains = defaultdict(set)
    cursor = conn.cursor()

    cursor.execute(
        f"SELECT r.ip_address, d.domain_name "
        f"FROM {table} r "
        "JOIN domains d ON r.domain_id = d.domain_id "
        "WHERE r.timestamp = %s",
        (timestamp,)
    )
    for ip_or_cname, domain in cursor.fetchall():
        if _is_ip(ip_or_cname):
            if _is_ipv4(ip_or_cname):
                ipv4_to_domains[ip_or_cname].add(domain)
            elif _is_ipv6(ip_or_cname):
                ipv6_to_domains[ip_or_cname].add(domain)
        else:
            resolved = _resolve_cname(conn.cursor(), table, ip_or_cname, set(), timestamp)
            for ip in resolved:
                if _is_ipv4(ip):
                    ipv4_to_domains[ip].add(domain)
                elif _is_ipv6(ip):
                    ipv6_to_domains[ip].add(domain)

    return ipv4_to_domains, ipv6_to_domains


def write_csv(path, ip_to_domains):
    import os
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ip_address", "domain_count"])
        for ip, domains in ip_to_domains.items():
            writer.writerow([ip, len(domains)])
    print(f"  Wrote {len(ip_to_domains):,} rows → {path}")


def main():
    args = parse_args()
    import os
    os.makedirs(args.output_dir, exist_ok=True)

    conn = psycopg2.connect(args.db_url)

    print("[+] Processing A records...")
    ipv4_from_a, _ = collect_ip_domain_counts(conn, "a_records", args.a_timestamp)
    write_csv(os.path.join(args.output_dir, "domains_per_ipv4.csv"), ipv4_from_a)

    print("[+] Processing AAAA records...")
    _, ipv6_from_aaaa = collect_ip_domain_counts(conn, "aaaa_records", args.aaaa_timestamp)
    write_csv(os.path.join(args.output_dir, "domains_per_ipv6.csv"), ipv6_from_aaaa)

    conn.close()
    print("[✓] Done.")


if __name__ == "__main__":
    main()
