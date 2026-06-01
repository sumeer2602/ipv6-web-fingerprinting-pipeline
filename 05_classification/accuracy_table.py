"""
accuracy_table.py — Fingerprinting Accuracy by Tranco Rank Tier (Stage 5)

Merges fingerprinting match results, dual-stack classification, and Tranco
rankings to compute accuracy by rank tier. Produces the data for Table 1 in
the paper ("IPv6 Web Fingerprinting Accuracy").

Tiers: Top 100, Top 1K, Top 10K, Top 50K, Top 100K, Top 250K, Top 500K, All

Accuracy is computed separately for:
  - Dual-stack INCOMPLETE sites (dual_stack='yes'): IPv4 + IPv6 fingerprinting
  - Dual-stack COMPLETE sites  (dual_stack='no'):   IPv4 + IPv6 fingerprinting

Inputs:
  --fp-results    fp_match_results.csv from fp_testing_opt.py
  --ip-analysis   ip_analysis.csv from ip_analysis.py
  --tranco        Tranco ranking CSV (columns: rank, domain — no header)
  --output-dir    Directory for output CSV files (default: current directory)

Outputs (written to --output-dir):
  fingerprinting_accuracy_results.csv  ← tier-level accuracy table (Table 1 source)
  processed_fingerprinting_data.csv    ← full merged dataset with position column
  dual_stack_domains.csv               ← domain list for incomplete sites
  ipv6_only_domains.csv                ← domain list for complete sites

Usage:
  python accuracy_table.py \\
      --fp-results /media/chaos/v6wft/ip_connections/1/fp_match_results.csv \\
      --ip-analysis ip_analysis.csv \\
      --tranco data/tranco_full_24.csv \\
      --output-dir .

Notes:
  - Uses the 'position' column (1-indexed sort by Tranco rank) for tier membership,
    NOT the raw 'rank' column which has duplicates and gaps.
  - Only IPv6-available sites (ipv6_available='yes') are included in the analysis.
"""

import argparse
import os

import numpy as np
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(description="Compute fingerprinting accuracy by Tranco rank tier")
    parser.add_argument("--fp-results", required=True,
                        help="fp_match_results.csv")
    parser.add_argument("--ip-analysis", required=True,
                        help="ip_analysis.csv")
    parser.add_argument("--tranco", required=True,
                        help="Tranco ranking CSV (rank, domain — no header)")
    parser.add_argument("--output-dir", default=".",
                        help="Output directory (default: current directory)")
    return parser.parse_args()


def normalize_domain(domain):
    if pd.isna(domain):
        return domain
    domain = str(domain).lower().strip()
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


TIERS = {
    'Top 100':    100,
    'Top 1K':     1_000,
    'Top 10K':    10_000,
    'Top 50K':    50_000,
    'Top 100K':   100_000,
    'Top 250K':   250_000,
    'Top 500K':   500_000,
    'All domains': float('inf'),
}


def compute_tier_accuracy(data):
    """Compute accuracy per tier, split by dual-stack status."""
    ds_yes = data[data['dual_stack'] == 'yes']   # INCOMPLETE
    ds_no  = data[data['dual_stack'] == 'no']    # COMPLETE

    rows = []
    for tier_name, limit in TIERS.items():
        if limit == float('inf'):
            grp_yes = ds_yes
            grp_no  = ds_no
        else:
            grp_yes = ds_yes[ds_yes['position'] <= limit]
            grp_no  = ds_no[ds_no['position']  <= limit]

        def acc(grp, col):
            if len(grp) == 0:
                return 0, 0.0
            correct = (grp[col] == grp['test_site']).sum()
            return int(correct), round(correct / len(grp) * 100, 2)

        v4c_yes, v4a_yes = acc(grp_yes, 'ipv4_match')
        v6c_yes, v6a_yes = acc(grp_yes, 'dual_stack_match')
        v4c_no,  v4a_no  = acc(grp_no,  'ipv4_match')
        v6c_no,  v6a_no  = acc(grp_no,  'dual_stack_match')

        rows.append({
            'Tier':                        tier_name,
            'Dual Stack Sites':            len(grp_yes),   # = INCOMPLETE
            'IPv6 Only Sites':             len(grp_no),    # = COMPLETE
            'IPv4 Correct (Dual Stack)':   v4c_yes,
            'IPv4 Acc (Dual Stack) %':     v4a_yes,
            'IPv6 Correct (Dual Stack)':   v6c_yes,
            'IPv6 Acc (Dual Stack) %':     v6a_yes,
            'IPv4 Correct (IPv6 Only)':    v4c_no,
            'IPv4 Acc (IPv6 Only) %':      v4a_no,
            'IPv6 Correct (IPv6 Only)':    v6c_no,
            'IPv6 Acc (IPv6 Only) %':      v6a_no,
        })

    return pd.DataFrame(rows)


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print("Loading data...")
    fp = pd.read_csv(args.fp_results)
    ia = pd.read_csv(args.ip_analysis)
    tranco = pd.read_csv(args.tranco, names=['rank', 'domain'])

    # Normalize domains for joining
    fp['_norm']     = fp['test_site'].apply(normalize_domain)
    ia['_norm']     = ia['website_name'].apply(normalize_domain)
    tranco['_norm'] = tranco['domain'].apply(normalize_domain)

    print(f"  fp_match_results: {len(fp):,} rows")
    print(f"  ip_analysis:      {len(ia):,} rows")
    print(f"  tranco:           {len(tranco):,} rows")

    # Merge
    merged = fp.merge(ia, on='_norm', how='left')
    print(f"After IPv6 filter (ipv6_available='yes'): ", end="")
    merged = merged[merged['ipv6_available'] == 'yes']
    print(f"{len(merged):,} sites")

    merged = merged.merge(tranco[['_norm', 'rank']], on='_norm', how='left')
    merged['rank'] = merged['rank'].fillna(float('inf'))
    merged = merged.sort_values('rank').reset_index(drop=True)
    merged['position'] = merged.index + 1

    print(f"  Dual-stack incomplete (yes): {(merged['dual_stack']=='yes').sum():,}")
    print(f"  Dual-stack complete   (no):  {(merged['dual_stack']=='no').sum():,}")

    print("\nComputing accuracy by tier...")
    accuracy_table = compute_tier_accuracy(merged)
    print(accuracy_table.to_string(index=False))

    # Save outputs
    acc_path = os.path.join(args.output_dir, 'fingerprinting_accuracy_results.csv')
    accuracy_table.to_csv(acc_path, index=False)

    proc_path = os.path.join(args.output_dir, 'processed_fingerprinting_data.csv')
    merged.drop(columns=['_norm'], errors='ignore').to_csv(proc_path, index=False)

    for ds_val, out_name in [('yes', 'dual_stack_domains.csv'), ('no', 'ipv6_only_domains.csv')]:
        sub = merged[merged['dual_stack'] == ds_val][['test_site', 'position', 'rank']].sort_values('position')
        sub.to_csv(os.path.join(args.output_dir, out_name), index=False)

    print(f"\nOutputs written to {args.output_dir}/")


if __name__ == "__main__":
    main()
