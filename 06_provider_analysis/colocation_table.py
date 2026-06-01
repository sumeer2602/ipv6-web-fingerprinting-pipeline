"""
colocation_table.py — Provider-Level Fingerprinting Accuracy (Stage 6)

For each hosting provider (identified via MaxMind GeoLite2 ASN data), computes:
  - Number of dual-stack INCOMPLETE and COMPLETE sites hosted
  - IPv6 fingerprinting accuracy for each category

Provider is determined by the IPv6 address of each website (from website_ip.csv).
Accuracy is measured by dual_stack_match correctness in fp_match_results.csv.

This produces the data for Tables 2 and 3 in the paper.

Inputs:
  --website-ip    website_ip.csv (from website_ip.py)
  --ip-analysis   ip_analysis.csv (from ip_analysis.py) — NOTE: use ip_analysis_1.csv
                  (506,637 rows, same batch as fp_match_results.csv) for Table 3
  --fp-results    fp_match_results.csv (from fp_testing_opt.py)
  --geolite-v6    GeoLite2-ASN-Blocks-IPv6.csv (MaxMind ASN database)
  --top-n         Number of top providers to display (default: 10)

Output: Printed tables (pipe to file or modify to save CSV)

Usage:
  python colocation_table.py \\
      --website-ip website_ip.csv \\
      --ip-analysis ip_analysis_1.csv \\
      --fp-results fp_match_results.csv \\
      --geolite-v6 data/GeoLite2-ASN-Blocks-IPv6.csv \\
      --top-n 10

Notes:
  - dual_stack='yes' in ip_analysis = INCOMPLETE (has IPv4-only third-party resources)
  - dual_stack='no'  in ip_analysis = COMPLETE (all resources available over IPv6)
  - Both columns use IPv6 GeoLite2 for provider lookup
"""

import argparse
import ipaddress

import pandas as pd
import pytricia


PROV_NORM = {
    'AMAZON-02':                       'AMAZON',
    'Jsc timeweb':                     'JSC Timeweb',
    'Hostinger International Limited': "Hostinger Int'l Ltd",
    'Akamai International B.V.':       "Akamai Int'l B.V.",
    'GOOGLE-CLOUD-PLATFORM':           'GOOGLE-GCP',
    'DIGITALOCEAN-ASN':                'DIGITALOCEAN',
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute provider-level fingerprinting accuracy (Tables 2 & 3)")
    parser.add_argument("--website-ip", required=True,
                        help="website_ip.csv (website_name, ipv4_address, ipv6_address)")
    parser.add_argument("--ip-analysis", required=True,
                        help="ip_analysis.csv (website_name, ipv6_available, dual_stack)")
    parser.add_argument("--fp-results", required=True,
                        help="fp_match_results.csv (test_site, ipv4_match, dual_stack_match)")
    parser.add_argument("--geolite-v6", required=True,
                        help="GeoLite2-ASN-Blocks-IPv6.csv")
    parser.add_argument("--top-n", type=int, default=10,
                        help="Number of top providers per category (default: 10)")
    return parser.parse_args()


def build_trie(asn_csv, bits=128):
    """Build a pytricia prefix trie for IP → provider lookup."""
    df = pd.read_csv(asn_csv)[['network', 'autonomous_system_organization']].dropna()
    trie = pytricia.PyTricia(bits)
    print(f"Building {bits}-bit prefix trie ({len(df):,} prefixes)...")
    for _, row in df.iterrows():
        try:
            trie[str(row['network'])] = row['autonomous_system_organization']
        except Exception:
            continue
    print("  Trie built.")
    return trie


def get_provider(ip_str, trie):
    try:
        return trie[str(ipaddress.ip_address(str(ip_str)))]
    except Exception:
        return None


def normalize_provider(name):
    return PROV_NORM.get(name, name) if name else None


def compute_provider_table(sites_set, wip, fp, label):
    """
    For a set of site names and a provider-tagged website_ip DataFrame,
    compute per-provider site count and IPv6 fingerprinting accuracy.
    """
    sub = wip[wip['website_name'].isin(sites_set) & wip['provider'].notna()].copy()
    records = []
    for prov, grp in sub.groupby('provider'):
        ws = grp['website_name'].tolist()
        in_fp = [s for s in ws if s in fp.index]
        if not in_fp:
            continue
        correct = sum(fp.loc[s, 'dual_stack_match'] == s for s in in_fp)
        records.append({
            'Provider':  prov,
            '# Sites':   len(in_fp),
            'WF Acc %':  round(correct / len(in_fp) * 100, 1),
        })

    df = (pd.DataFrame(records)
            .sort_values('# Sites', ascending=False)
            .head(args_global.top_n)
            .reset_index(drop=True))
    df.insert(0, 'Rank', range(1, len(df) + 1))
    print(f"\n=== {label} sites (top {args_global.top_n}) ===")
    print(df.to_string(index=False))
    return df


args_global = None  # set in main() so compute_provider_table can access top_n


def main():
    global args_global
    args = parse_args()
    args_global = args

    trie_v6 = build_trie(args.geolite_v6, bits=128)

    wip = pd.read_csv(args.website_ip)
    ia  = pd.read_csv(args.ip_analysis)
    fp  = pd.read_csv(args.fp_results).set_index('test_site')

    print(f"\nLoaded: website_ip={len(wip):,}  ip_analysis={len(ia):,}  fp_match={len(fp):,}")

    # Assign provider via IPv6 address
    wip['provider'] = (wip['ipv6_address']
                       .apply(lambda x: get_provider(x, trie_v6) if pd.notna(x) else None)
                       .apply(normalize_provider))

    for ds_val, label in [('yes', 'Dual-stack Incomplete'), ('no', 'Dual-stack Complete')]:
        sites = set(ia[ia['dual_stack'] == ds_val]['website_name'])
        compute_provider_table(sites, wip, fp, label)


if __name__ == "__main__":
    main()
