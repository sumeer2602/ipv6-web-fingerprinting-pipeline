# Stage 6 — Provider & Co-location Analysis

Identify hosting providers via MaxMind GeoLite2 and compute per-provider
fingerprinting accuracy.

## Scripts

| Script | Purpose |
|---|---|
| `website_ip.py` | Extract primary IPv4/IPv6 address per website from zdns |
| `colocation_table.py` | Compute provider-level site counts + accuracy (Tables 2 & 3) |

## Run

```bash
# 1. Extract primary IPs per website
python website_ip.py \
    --fp-results fp_match_results.csv \
    --zdns-a /storage/v6wft/domains/A_<timestamp>.gz \
    --zdns-aaaa /storage/v6wft/domains/AAAA_<timestamp>.gz \
    --output website_ip.csv

# 2. Compute provider accuracy tables
python colocation_table.py \
    --website-ip website_ip.csv \
    --ip-analysis ip_analysis_1.csv \   # use batch-matched file (506k rows)
    --fp-results fp_match_results.csv \
    --geolite-v6 data/GeoLite2-ASN-Blocks-IPv6.csv \
    --top-n 10
```

## Important: ip_analysis file selection

For Table 3 accuracy values, use `ip_analysis_1.csv` (506,637 rows) — the file
from the **same crawl batch** as `fp_match_results.csv`. Using a different
`ip_analysis.csv` (e.g. 539k rows from a broader crawl) produces mismatched
site counts and incorrect accuracy values.

## Outputs

Printed tables:
- **Dual-stack Incomplete** top-10 providers (by site count) + accuracy
- **Dual-stack Complete** top-10 providers (by site count) + accuracy

Provider lookup uses IPv6 GeoLite2 for **both** columns.
