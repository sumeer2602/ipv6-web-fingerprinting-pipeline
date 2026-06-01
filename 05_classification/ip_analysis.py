"""
ip_analysis.py — Classify Sites by Dual-Stack Status (Stage 5)

Reads the test-phase IP connection files and classifies each website as:
  - ipv6_available: whether the primary domain resolved to IPv6 ("yes"/"no")
  - dual_stack: "yes" if any secondary resource was only reachable via IPv4
                "no"  if all secondary resources are available via IPv6

IMPORTANT — dual_stack encoding:
  dual_stack = "yes"  →  "dual-stack INCOMPLETE" in the paper
                         (site has IPv4-only third-party resources)
  dual_stack = "no"   →  "dual-stack COMPLETE" in the paper
                         (all resources available over IPv6)

This is the classification that drives Table 1 and Table 3 in the paper.

Inputs:
  --input-dir    Directory of IP connection .txt files
                 (e.g. /media/chaos/v6wft/ip_connections/1)
  --output       Output CSV file path (e.g. ip_analysis.csv)

Output CSV columns:
  website_name      Domain name
  ipv6_available    "yes" if primary IP is IPv6, else "no"
  dual_stack        "yes" if any secondary IP is IPv4, else "no"

Usage:
  python ip_analysis.py \\
      --input-dir /media/chaos/v6wft/ip_connections/1 \\
      --output ip_analysis.csv
"""

import argparse
import csv
import ipaddress
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(
        description="Classify websites by dual-stack status from IP connection files")
    parser.add_argument("--input-dir", required=True,
                        help="Directory of IP connection .txt files")
    parser.add_argument("--output", required=True,
                        help="Output CSV file path")
    return parser.parse_args()


def is_ipv6(addr):
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv6Address)
    except ValueError:
        return False


def is_ipv4(addr):
    try:
        return isinstance(ipaddress.ip_address(addr), ipaddress.IPv4Address)
    except ValueError:
        return False


def extract_json_objects(text):
    """Extract all JSON objects from text (handles 2-JSON-per-line format)."""
    objects = []
    brace_level = 0
    current = ""
    for char in text:
        if char == "{":
            if brace_level == 0:
                current = ""
            brace_level += 1
        if brace_level > 0:
            current += char
        if char == "}":
            brace_level -= 1
            if brace_level == 0:
                try:
                    objects.append(json.loads(current))
                except json.JSONDecodeError:
                    continue
    return objects


def classify_site(file_path):
    """
    Returns (ipv6_available, dual_stack) for one connection file.
    Uses the SECOND JSON object (index 1) which contains the dual-stack
    connection data (primary=IPv6, secondary may include IPv4 fallbacks).
    """
    with open(file_path) as f:
        raw = f.read()

    objects = extract_json_objects(raw)
    ipv6_available = "no"
    dual_stack = "no"

    if len(objects) >= 2:
        conn = objects[1]  # second object = dual-stack connection data
        primary = conn.get("0", [])
        secondary = conn.get("1", [])

        if primary and all(is_ipv6(ip) for ip in primary):
            ipv6_available = "yes"

        if any(is_ipv4(ip) for ip in secondary):
            dual_stack = "yes"  # ← "dual-stack INCOMPLETE" in the paper

    return ipv6_available, dual_stack


def main():
    args = parse_args()

    rows = []
    files = [f for f in os.listdir(args.input_dir) if f.endswith(".txt")]
    print(f"Processing {len(files):,} connection files...")

    for i, fname in enumerate(files):
        if (i + 1) % 10000 == 0:
            print(f"  {i+1:,}/{len(files):,}...")
        website = os.path.splitext(fname)[0]
        path = os.path.join(args.input_dir, fname)
        try:
            ipv6_avail, dual_stack = classify_site(path)
        except Exception as e:
            print(f"  Warning: error on {fname}: {e}")
            continue
        rows.append({
            "website_name": website,
            "ipv6_available": ipv6_avail,
            "dual_stack": dual_stack
        })

    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["website_name", "ipv6_available", "dual_stack"])
        writer.writeheader()
        writer.writerows(rows)

    ds_yes = sum(1 for r in rows if r["dual_stack"] == "yes")
    ds_no = sum(1 for r in rows if r["dual_stack"] == "no")
    print(f"\nWrote {len(rows):,} rows to {args.output}")
    print(f"  dual_stack=yes (INCOMPLETE): {ds_yes:,}")
    print(f"  dual_stack=no  (COMPLETE):   {ds_no:,}")


if __name__ == "__main__":
    main()
