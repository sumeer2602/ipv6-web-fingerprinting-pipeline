# Stage 5 — Classification & Accuracy Tables

Classify sites by dual-stack status and compute fingerprinting accuracy by rank tier.

## Scripts

| Script | Purpose |
|---|---|
| `ip_analysis.py` | Classify each site as dual-stack complete/incomplete |
| `accuracy_table.py` | Compute fingerprinting accuracy by Tranco rank tier (Table 1) |

## Run

```bash
# 1. Classify dual-stack status
python ip_analysis.py \
    --input-dir /storage/v6wft/ip_connections/1 \
    --output ip_analysis.csv

# 2. Compute accuracy table
python accuracy_table.py \
    --fp-results fp_match_results.csv \
    --ip-analysis ip_analysis.csv \
    --tranco data/tranco_full_24.csv \
    --output-dir results/
```

## Critical Encoding Note

`dual_stack` column in `ip_analysis.csv`:

| Value | Meaning in paper | Description |
|---|---|---|
| `'yes'` | **Dual-stack Incomplete** | Has IPv4-only third-party resources |
| `'no'`  | **Dual-stack Complete**   | All resources reachable over IPv6 |

This is counterintuitive. `dual_stack='yes'` does NOT mean "complete dual-stack."
It means the site has a mixed (incomplete) IPv6 deployment.

## Outputs

| File | Description |
|---|---|
| `fingerprinting_accuracy_results.csv` | Tier-level accuracy (Table 1 source) |
| `processed_fingerprinting_data.csv` | Full merged dataset with `position` column |
| `dual_stack_domains.csv` | Sites with `dual_stack='yes'` (incomplete) |
| `ipv6_only_domains.csv` | Sites with `dual_stack='no'` (complete) |
