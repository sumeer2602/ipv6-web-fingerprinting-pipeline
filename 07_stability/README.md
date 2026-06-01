# Stage 7 — Stability Analysis

Scripts for analyzing fingerprint and IP stability across crawl batches.
These produce the supporting evidence in §4.3 and the Appendix.

## Scripts

| Script | Input | Output | Paper figure |
|---|---|---|---|
| `ip_churn.py` | zdns snapshot directory | `A_records.csv`, `AAAA_records.csv` | Figure 8 |
| `domain_fp_diff.py` | domain_based batch dirs | `batch_difference_degrees.csv` | Figure A1, Figure 7 |
| `crawl_timestamps.py` | crawl batch directory | prints timestamp range | utility |

## ip_churn.py — IP Address Churn Rate

Tracks how each domain's A and AAAA records change across all zdns snapshots.
For each domain that changes at least once, records the average interval (hours)
between IP set changes.

```bash
python ip_churn.py \
    --zdns-dir   /path/to/zdns/snapshots \
    --output-dir /path/to/output/ip_rotation/
```

**Expected runtime:** Several hours for a full snapshot directory (~6,800 files).
Outputs `A_records.csv` and `AAAA_records.csv`.

## domain_fp_diff.py — Fingerprint Difference Degree

Compares domain fingerprints (third-party domain sets) between a reference
batch and subsequent batches. Uses the difference degree metric:

  diff_degree = (|D_ref ∪ D_curr| - |D_ref ∩ D_curr|) / |D_ref ∪ D_curr|

A value of 0 = identical fingerprints; 1 = completely disjoint third-party sets.

```bash
python domain_fp_diff.py \
    --base-dir /path/to/domain_based/chrome \
    --ref-batch 1 \
    --batches 2 3 4 5 \
    --strategy common_only \
    --output batch_difference_degrees_common_only.csv
```

**Strategy options:**
- `common_only` — only compare sites present in all batches (recommended)
- `reference_only` — compare all reference sites; missing in other batches = empty set
- `include_missing` — include all sites; missing = empty set

## crawl_timestamps.py — Batch Timestamp Range

Utility to check when a crawl batch ran, for matching with zdns snapshots:

```bash
python crawl_timestamps.py /path/to/chrome/1
# Earliest folder creation: 2024-04-28 14:12:03
# Latest   folder creation: 2024-04-29 02:47:31
```
