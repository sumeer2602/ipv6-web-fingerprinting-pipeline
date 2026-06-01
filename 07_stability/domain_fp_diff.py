"""
domain_fp_diff.py — Domain Fingerprint Difference Degree Across Batches (Stage 7)

Compares domain-based fingerprints between a reference batch (batch 1) and one
or more subsequent batches. For each domain present in the compared batches,
computes the difference degree:

  diff_degree = (|D_ref ∪ D_curr| - |D_ref ∩ D_curr|) / |D_ref ∪ D_curr|

where D_ref and D_curr are the sets of third-party domains in the fingerprint.
A value of 0 means identical fingerprints; 1 means completely disjoint.

This measures fingerprint stability over time — high diff_degree means the
site's third-party domain set changed significantly between batches.

Inputs:
  --base-dir    Directory containing numbered batch subdirs (e.g. 1/, 2/, 3/, ...)
  --ref-batch   Batch number to use as reference (default: 1)
  --batches     Which batch numbers to compare against reference (default: all others)
  --strategy    How to handle sites missing from a batch:
                  common_only     — only compare sites present in ALL batches (default)
                  reference_only  — compare all reference sites (missing = empty set)
                  include_missing — compare all sites across all batches
  --output      Output CSV file path

Output CSV columns:
  website, batch, reference_batch, difference_degree,
  ref_domain_count, curr_domain_count, ref_present, curr_present

Usage:
  python domain_fp_diff.py \\
      --base-dir /path/to/domain_based/chrome \\
      --ref-batch 1 \\
      --batches 2 3 4 5 \\
      --strategy common_only \\
      --output batch_difference_degrees.csv
"""

import argparse
import ast
import csv
import glob
import os
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute domain fingerprint difference degrees across crawl batches")
    parser.add_argument("--base-dir", required=True,
                        help="Directory containing numbered batch subdirs (1/, 2/, ...)")
    parser.add_argument("--ref-batch", type=int, default=1,
                        help="Reference batch number (default: 1)")
    parser.add_argument("--batches", type=int, nargs="+", default=None,
                        help="Batch numbers to compare (default: all subdirs except ref)")
    parser.add_argument("--strategy",
                        choices=["common_only", "reference_only", "include_missing"],
                        default="common_only",
                        help="How to handle sites missing from a batch (default: common_only)")
    parser.add_argument("--output", required=True,
                        help="Output CSV file path")
    return parser.parse_args()


def _read_domain_set(file_path):
    """
    Parse a domain fingerprint .txt file and return the union of primary and
    secondary domain sets (line 2 of the file).
    Returns an empty set on any parse error.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.readline()            # skip line 1 (timed request sequence)
            domain_fp = f.readline()
        d = ast.literal_eval(domain_fp.strip())
        return set(d[0]) | set(d[1])
    except Exception as e:
        print(f"  [!] Error parsing {file_path}: {e}")
        return set()


def _diff_degree(d_ref, d_curr):
    union = d_ref | d_curr
    if not union:
        return 0.0
    return (len(union) - len(d_ref & d_curr)) / len(union)


def load_batch(batch_dir):
    """Return {website: domain_set} for all .txt files in batch_dir."""
    data = {}
    files = glob.glob(os.path.join(batch_dir, "*.txt"))
    for i, txt_file in enumerate(files):
        website = os.path.splitext(os.path.basename(txt_file))[0]
        data[website] = _read_domain_set(txt_file)
        if (i + 1) % 10000 == 0:
            print(f"    Loaded {i+1:,} files...")
    return data


def main():
    args = parse_args()

    # Discover batch directories
    all_batch_dirs = {}
    for item in os.listdir(args.base_dir):
        path = os.path.join(args.base_dir, item)
        if os.path.isdir(path):
            try:
                all_batch_dirs[int(item)] = path
            except ValueError:
                pass

    ref_batch_num = args.ref_batch
    if ref_batch_num not in all_batch_dirs:
        print(f"[!] Reference batch {ref_batch_num} not found in {args.base_dir}")
        return

    compare_batches = args.batches or [b for b in sorted(all_batch_dirs) if b != ref_batch_num]
    print(f"Reference batch : {ref_batch_num}")
    print(f"Compare batches : {compare_batches}")
    print(f"Strategy        : {args.strategy}")

    print(f"\nLoading reference batch {ref_batch_num}...")
    ref_data = load_batch(all_batch_dirs[ref_batch_num])
    print(f"  {len(ref_data):,} sites")

    batch_data = {ref_batch_num: ref_data}
    for b in compare_batches:
        if b not in all_batch_dirs:
            print(f"  [!] Batch {b} directory not found, skipping")
            continue
        print(f"\nLoading batch {b}...")
        batch_data[b] = load_batch(all_batch_dirs[b])
        print(f"  {len(batch_data[b]):,} sites")

    # Determine website set based on strategy
    if args.strategy == "common_only":
        websites = set(ref_data.keys())
        for b in compare_batches:
            if b in batch_data:
                websites &= set(batch_data[b].keys())
        print(f"\nCommon sites (all batches): {len(websites):,}")
    elif args.strategy == "reference_only":
        websites = set(ref_data.keys())
        print(f"\nReference-only sites: {len(websites):,}")
    else:
        websites = set(ref_data.keys())
        for b in compare_batches:
            if b in batch_data:
                websites |= set(batch_data[b].keys())
        print(f"\nAll unique sites: {len(websites):,}")

    # Compute difference degrees
    results = []
    for b in compare_batches:
        if b not in batch_data:
            continue
        curr_data = batch_data[b]
        for website in websites:
            ref_domains  = ref_data.get(website)
            curr_domains = curr_data.get(website)

            if args.strategy == "common_only":
                if ref_domains is None or curr_domains is None:
                    continue
            elif args.strategy == "reference_only":
                if ref_domains is None:
                    continue
                curr_domains = curr_domains or set()
            else:
                ref_domains  = ref_domains  or set()
                curr_domains = curr_domains or set()

            results.append({
                "website":           website,
                "batch":             b,
                "reference_batch":   ref_batch_num,
                "difference_degree": _diff_degree(ref_domains, curr_domains),
                "ref_domain_count":  len(ref_domains),
                "curr_domain_count": len(curr_domains),
                "ref_present":       bool(ref_data.get(website)),
                "curr_present":      bool(curr_data.get(website)),
            })

    # Write output
    fieldnames = ["website", "batch", "reference_batch", "difference_degree",
                  "ref_domain_count", "curr_domain_count", "ref_present", "curr_present"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    avg_dd = sum(r["difference_degree"] for r in results) / len(results) if results else 0
    print(f"\nWrote {len(results):,} rows → {args.output}")
    print(f"Average difference degree: {avg_dd:.4f}")


if __name__ == "__main__":
    main()
