# Stage 4 — Fingerprint Testing

Match test-phase IP connections against enrolled IP fingerprints to compute
re-identification accuracy.

## Scripts

| Script | Purpose |
|---|---|
| `cleaner.py` | Delete empty connection files before testing |
| `fp_testing_opt.py` | Core matching: test connections × enrolled FPs → fp_match_results.csv |
| `fill_missing_cons.py` | Per-domain fallback: rebuild connection file from zdns (helper) |

## Run Order

```bash
# 1. Remove empty connection files
python cleaner.py --directory /storage/v6wft/ip_connections/1

# 2. Build cache files (lists of filenames to process)
python -c "
import json, os
conn_files = [f for f in os.listdir('/storage/v6wft/ip_connections/1') if f.endswith('.txt')]
json.dump(conn_files, open('conn_cache.json', 'w'))
fp_files = [f for f in os.listdir('/storage/v6wft/ip_based/1') if f.endswith('.txt')]
json.dump(fp_files, open('/storage/v6wft/ip_based/1/directory_cache.json', 'w'))
print(f'{len(conn_files)} connections, {len(fp_files)} fingerprints')
"

# 3. Run fingerprint matching (high RAM + CPU)
python fp_testing_opt.py \
    /storage/v6wft/ip_connections/1 \
    conn_cache.json \
    /storage/v6wft/ip_based/1 \
    /storage/v6wft/ip_based/1 \
    ip_entropy_A.csv \
    ip_entropy_AAAA.csv \
    16   # optional: number of processes (default = auto)
```

## Output

`fp_match_results.csv` — written to `<ip_connections_dir>/fp_match_results.csv`:

| test_site | ipv4_match | ipv4_score | dual_stack_match | dual_stack_score |
|---|---|---|---|---|
| example.com | example.com | 14.2 | example.com | 9.8 |

- `dual_stack_match == test_site` → correct IPv6 re-identification ✓
- `ipv4_match == test_site` → correct IPv4 re-identification ✓

## Performance Notes

- Matching 506k connections × 506k fingerprints requires ~64 GB RAM and ~2–4 hours
  on a 32-core machine
- All fingerprints and connections are loaded into RAM before matching begins
- Use `--num-processes 0` to let the script auto-detect optimal core count
