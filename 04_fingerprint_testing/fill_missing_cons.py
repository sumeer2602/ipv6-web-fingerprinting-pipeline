"""
fill_missing_cons.py — Fill Missing IP Connections (Stage 4)

Some websites in the test-phase ip_connections directory may be missing
because the test crawl failed (timeout, browser crash, blocked). This script
finds domains that are present in the domain-based fingerprint directory but
absent from the ip_connections directory, then attempts to fill them in from
a fallback source (a second batch's ip_connections directory, or the
enrolled ip_based fingerprints directly).

Inputs:
  --domain-fp-dir   Reference directory of domain fingerprints (.txt files)
  --ip-conn-dir     Test-phase ip_connections directory (may have gaps)
  --fallback-dir    Fallback source: another batch's ip_connections or ip_based dir
  --output-dir      Where to write the filled ip_connections (default: same as --ip-conn-dir)

Output:
  Copies missing .txt files from --fallback-dir into --output-dir.
  Prints a summary: how many were missing, how many filled, how many still absent.

Usage:
  python fill_missing_cons.py \\
      --domain-fp-dir  /path/to/domain_based/1 \\
      --ip-conn-dir    /path/to/ip_connections/1 \\
      --fallback-dir   /path/to/ip_connections/2 \\
      --output-dir     /path/to/ip_connections/1_filled
"""

import argparse
import os
import shutil


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fill missing ip_connections files from a fallback directory")
    parser.add_argument("--domain-fp-dir", required=True,
                        help="Reference domain fingerprint directory (.txt files, one per domain)")
    parser.add_argument("--ip-conn-dir", required=True,
                        help="Test-phase ip_connections directory to check for gaps")
    parser.add_argument("--fallback-dir", required=True,
                        help="Fallback directory to copy missing files from")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: --ip-conn-dir, modified in place)")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = args.output_dir or args.ip_conn_dir
    os.makedirs(output_dir, exist_ok=True)

    # All domains in the reference fingerprint directory
    reference = {f for f in os.listdir(args.domain_fp_dir) if f.endswith(".txt")}
    # All domains already in the ip_connections directory
    present   = {f for f in os.listdir(args.ip_conn_dir)   if f.endswith(".txt")}
    missing   = reference - present

    print(f"Reference domains : {len(reference):,}")
    print(f"Present in conn   : {len(present):,}")
    print(f"Missing           : {len(missing):,}")

    filled  = 0
    absent  = 0
    for fname in sorted(missing):
        src = os.path.join(args.fallback_dir, fname)
        dst = os.path.join(output_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            filled += 1
        else:
            absent += 1

    print(f"\nFilled from fallback : {filled:,}")
    print(f"Still absent         : {absent:,}")
    if absent:
        print("  (these domains will be skipped by fp_testing_opt.py)")


if __name__ == "__main__":
    main()
