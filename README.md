# IPv6 Web Fingerprinting — Measurement Pipeline

This repository contains the data collection and processing pipeline for our work on IPv6 Website Fingerprinting accepted to PETs 2026:

> **"IPv6 Web Fingerprinting"**

The pipeline replicates the full measurement study: crawling websites, building domain- and IP-based fingerprints, computing entropy, and evaluating fingerprinting accuracy.

---

## Overview

The study measures whether IPv6 addresses leak more precise location information than IPv4 addresses when used for web fingerprinting. We crawl ~550,000 top websites twice (enrollment + test), build IP-based fingerprints, and test re-identification accuracy.

Key distinction — **dual-stack status**:
- **Dual-stack Incomplete**: site has IPv4-only third-party resources → fingerprint mixes IPv4 and IPv6
- **Dual-stack Complete**: all resources reachable over IPv6 → pure IPv6 fingerprint

---

## Prerequisites

### Hardware
- High core count (≥32 cores recommended for fingerprint matching)
- ≥64 GB RAM (fp_testing_opt.py loads all fingerprints into memory)
- Large storage (≥2 TB) for HAR files, zdns outputs, and fingerprint data

### Software
- Python 3.10+
- [zdns](https://github.com/zmap/zdns) — installed and in PATH
- [Browsertime](https://www.sitespeed.io/documentation/browsertime/) — `npm install -g browsertime`
- Node.js ≥18
- Google Chrome + Brave browser
- Xvfb (for headless display)

### Python packages
```bash
pip install -r requirements.txt
```

### Data
- **Tranco domain list**: download from [tranco-list.eu](https://tranco-list.eu) and place at `data/tranco_full_24.csv` (format: `rank,domain` with no header)
- **MaxMind GeoLite2 ASN**: free registration required at [maxmind.com](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data). Place `GeoLite2-ASN-Blocks-IPv6.csv` in `data/`.

---

## Pipeline Stages

```
[INPUT: Tranco domain list]
        │
        ▼
┌─────────────────────────────────────────────┐
│  Stage 1: Data Collection                   │
│  crawler.py         — web crawl (HAR files) │
│  continuous_dns.py  — DNS snapshots         │
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 2: Fingerprint Construction          │
│  basicFingerprint.py      — HAR → domain FP │
│  build_dns_db.py          — zdns → JSON DB  │
│  dns_database/            — PostgreSQL DB   │
│  ip_fingerprints.py       — domain → IP FP  │
│  ip_connections_browser.py— test connections│
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 3: Entropy Calculation               │
│  domain_entropy.py  — per-domain entropy    │
│  ip_entropy.py      — per-IP entropy        │
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 4: Fingerprint Testing               │
│  cleaner.py           — remove empty files  │
│  fp_testing_opt.py    — match + accuracy    │
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 5: Classification & Accuracy Tables  │
│  ip_analysis.py     — dual-stack status     │
│  accuracy_table.py  — Table 1 (rank tiers)  │
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 6: Provider & Co-location Analysis   │
│  website_ip.py       — primary IP per site  │
│  colocation_table.py — Tables 2 & 3         │
└────────────────────────┬────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│  Stage 7: Stability Analysis                │
│  ip_churn.py        — IP churn rate         │
│  domain_fp_diff.py  — FP diff degree        │
│  crawl_timestamps.py— batch time ranges     │
└─────────────────────────────────────────────┘
```

---

## Step-by-Step Instructions

### Stage 1 — Data Collection

**1a. Crawl websites with Browsertime**

Run `crawler.py` repeatedly (once per batch of 1000 domains) until all ~550k domains are covered. The script shuffles the domain list and picks 1000 per run; re-running automatically fills in uncrawled domains.

```bash
# Batch 1 (run multiple times until fully covered)
python 01_collection/crawler.py \
    --domain-list data/tranco_full_24.csv \
    --output-dir /your/storage/v6wft \
    --workers 25 \
    --batch 1
```

Output: `/your/storage/v6wft/chrome/1/<domain>/<domain>.har` (and same for `brave/`)

**1b. Collect DNS snapshots in parallel**

Run `continuous_dns.py` every 20 minutes *while the crawler is running*. It extracts domains from completed HAR files and resolves them with zdns, producing timestamped A/AAAA snapshots.

```bash
# Add to cron: */20 * * * * python /path/to/continuous_dns.py ...
python 01_collection/continuous_dns.py \
    --output-dir /your/storage/v6wft \
    --workers 8
```

Output: `/your/storage/v6wft/domains/A_<timestamp>.gz` and `AAAA_<timestamp>.gz`

**1c. Align DNS snapshots to each batch**

After completing a batch, copy the relevant zdns files to a per-batch directory:

```bash
python 01_collection/give_zdns_for_batch.py \
    /your/storage/v6wft/chrome/1 \
    /your/storage/v6wft/domains \
    /your/storage/v6wft/batchwise_domains/1
```

**Repeat Stage 1 for all batches.** We used 10 enrollment batches + 1 test batch (~550k unique domains).

---

### Stage 2 — Fingerprint Construction

**2a. Extract domain-based fingerprints from HAR files**

```bash
python 02_fingerprint_construction/basicFingerprint.py \
    --har-dir /your/storage/v6wft/chrome/1 \
    --output-dir /your/storage/v6wft/domain_based/chrome/1
```

Output: one `.txt` file per domain with timed request sequence and domain sets.

**2b. Build flat JSON DNS databases**

Run twice — once for A records (IPv4) and once for AAAA records (IPv6):

```bash
python 02_fingerprint_construction/build_dns_db.py \
    --zdns-dir /your/storage/v6wft/domains \
    --output database_A.json \
    --record-type A

python 02_fingerprint_construction/build_dns_db.py \
    --zdns-dir /your/storage/v6wft/domains \
    --output database_AAAA.json \
    --record-type AAAA
```

⚠️ These files can be several GB. Keep them in fast storage.

**2c. Convert domain fingerprints to IP fingerprints (enrollment)**

```bash
python 02_fingerprint_construction/ip_fingerprints.py \
    --domain-fp-dir /your/storage/v6wft/domain_based/chrome/1 \
    --db-a database_A.json \
    --db-aaaa database_AAAA.json \
    --output-dir /your/storage/v6wft/ip_based/1
```

Output format per file (2 JSON lines):
```
{"0": ["ipv4_primary"], "1": ["ipv4_secondary1", ...]}   ← IPv4 fingerprint
{"0": ["ipv6_primary"], "1": ["ipv6_secondary1", ...]}   ← IPv6 fingerprint
```

**2d. Extract test-phase IP connections** *(for the test batch only)*

This is the "test crawl" — a separate crawl used to simulate a fingerprinter observing the website. Uses time-synchronized DNS (closest snapshot captured ≥5 days after crawl).

```bash
python 02_fingerprint_construction/ip_connections_browser.py \
    --har-dir /your/storage/v6wft/chrome/test_batch \
    --zdns-dir /your/storage/v6wft/domains \
    --db-dir /path/to/db_dir \
    --output-dir /your/storage/v6wft/ip_connections/1
```

---

### Stage 3 — Entropy Calculation

Entropy must be computed **before** fingerprint testing.

**3a. Domain entropy** (from enrollment domain fingerprints):

```bash
python 03_entropy/domain_entropy.py \
    --domain-fp-dir /your/storage/v6wft/domain_based/chrome/1 \
    --output domain_entropy.csv
```

**3b. IP entropy** (from a zdns AAAA snapshot):

```bash
# IPv6 entropy (for dual-stack matching):
python 03_entropy/ip_entropy.py \
    --zdns-file /your/storage/v6wft/domains/AAAA_<timestamp>.gz \
    --output ip_entropy_AAAA.csv

# IPv4 entropy (for IPv4 matching):
python 03_entropy/ip_entropy.py \
    --zdns-file /your/storage/v6wft/domains/A_<timestamp>.gz \
    --output ip_entropy_A.csv
```

---

### Stage 4 — Fingerprint Testing

**4a. Clean empty connection files**

```bash
python 04_fingerprint_testing/cleaner.py \
    --directory /your/storage/v6wft/ip_connections/1
```

**4b. Create a cache file listing all connection files to process**

```bash
python -c "
import json, os
files = [f for f in os.listdir('/your/storage/v6wft/ip_connections/1') if f.endswith('.txt')]
json.dump(files, open('conn_cache.json','w'))
print(f'{len(files)} connection files')
"
```

Similarly create `directory_cache.json` for IP fingerprints:

```bash
python -c "
import json, os
files = [f for f in os.listdir('/your/storage/v6wft/ip_based/1') if f.endswith('.txt')]
json.dump(files, open('/your/storage/v6wft/ip_based/1/directory_cache.json','w'))
"
```

**4c. Run fingerprint matching**

```bash
python 04_fingerprint_testing/fp_testing_opt.py \
    /your/storage/v6wft/ip_connections/1 \
    conn_cache.json \
    /your/storage/v6wft/ip_based/1 \
    /your/storage/v6wft/ip_based/1 \
    ip_entropy_A.csv \
    ip_entropy_AAAA.csv
```

Output: `fp_match_results.csv` — one row per test site with `ipv4_match` and `dual_stack_match`.

`dual_stack_match == test_site` → correct IPv6 re-identification.

---

### Stage 5 — Classification & Accuracy Tables

**5a. Classify sites by dual-stack status**

```bash
python 05_classification/ip_analysis.py \
    --input-dir /your/storage/v6wft/ip_connections/1 \
    --output ip_analysis.csv
```

**5b. Compute accuracy by Tranco rank tier (Table 1)**

```bash
python 05_classification/accuracy_table.py \
    --fp-results fp_match_results.csv \
    --ip-analysis ip_analysis.csv \
    --tranco data/tranco_full_24.csv \
    --output-dir results/
```

---

### Stage 6 — Provider & Co-location Analysis

**6a. Extract primary IP per website**

```bash
python 06_provider_analysis/website_ip.py \
    --fp-results fp_match_results.csv \
    --zdns-a /path/to/A_<timestamp>.gz \
    --zdns-aaaa /path/to/AAAA_<timestamp>.gz \
    --output website_ip.csv
```

**6b. Compute provider-level accuracy (Tables 2 & 3)**

```bash
python 06_provider_analysis/colocation_table.py \
    --website-ip website_ip.csv \
    --ip-analysis ip_analysis.csv \
    --fp-results fp_match_results.csv \
    --geolite-v6 data/GeoLite2-ASN-Blocks-IPv6.csv \
    --top-n 10
```

---

### Stage 7 — Stability Analysis

**7a. IP address churn rate** (Figure 8)

Tracks IP set changes across all zdns snapshots. Requires the full snapshot
directory (~6,800 A and AAAA files).

```bash
python 07_stability/ip_churn.py \
    --zdns-dir   /your/storage/v6wft/domains \
    --output-dir results/ip_rotation/
```

Output: `A_records.csv` and `AAAA_records.csv` — one row per domain with
`Average_IP_Change_Interval_Hours` and `Number_of_Changes`.

**7b. Domain fingerprint difference degree** (Figures 7 & A1)

Compares domain fingerprints across batches to measure stability over time.

```bash
python 07_stability/domain_fp_diff.py \
    --base-dir /your/storage/v6wft/domain_based/chrome \
    --ref-batch 1 \
    --batches 2 3 4 5 \
    --strategy common_only \
    --output results/batch_difference_degrees_common_only.csv
```

**7c. Batch timestamp range** (utility)

Check what time window a crawl batch covers, for aligning with zdns snapshots:

```bash
python 07_stability/crawl_timestamps.py /your/storage/v6wft/chrome/1
```

---

### PostgreSQL DNS Database (Stage 2 — optional path)

`02_fingerprint_construction/dns_database/` provides an alternative to the
flat JSON database (`build_dns_db.py`) for use cases requiring time-synchronized
IP lookups. This was used to compute `ip_entropy_A.csv` and `ip_entropy_AAAA.csv`.

See `02_fingerprint_construction/dns_database/README.md` for setup instructions.

---

## Key Data File Formats

### Domain fingerprint `.txt` (output of `basicFingerprint.py`)
```
[(0.0, 'example.com'), (0.1, 'cdn.example.net'), (0.2, 'analytics.com'), ...]
{0: {'example.com'}, 1: {'cdn.example.net', 'analytics.com'}}
```
Line 1: timed request sequence `[(seconds, domain), ...]`
Line 2: label map — `0` = primary domain, `1` = secondary domains

### IP fingerprint `.txt` (output of `ip_fingerprints.py`)
```
{"0": ["93.184.216.34"], "1": ["192.0.2.1", "198.51.100.2"]}
{"0": ["2001:db8::1"], "1": ["2001:db8::2"]}
```
Line 1: IPv4 fingerprint — `"0"` = primary IPs, `"1"` = secondary IPs
Line 2: IPv6 fingerprint — same format

### IP connection `.txt` (output of `ip_connections_browser.py`)
```
{"0": ["93.184.216.34"], "1": []}
{"0": ["2001:db8::1"], "1": []}
```
Same format as IP fingerprint — captured during the test crawl.

### `ip_analysis.csv`
| website_name | ipv6_available | dual_stack |
|---|---|---|
| example.com | yes | no |
| test.org | yes | yes |

`dual_stack='yes'` = INCOMPLETE (has IPv4-only secondary resources) — **counterintuitive!**
`dual_stack='no'`  = COMPLETE (all resources IPv6-reachable)

### `fp_match_results.csv`
| test_site | ipv4_match | ipv4_score | dual_stack_match | dual_stack_score |
|---|---|---|---|---|
| example.com | example.com | 14.2 | example.com | 9.8 |

`dual_stack_match == test_site` → correct IPv6-based re-identification.

---

## Citation

If you use this pipeline, please cite:

```bibtex
@inproceedings{_______________________,
  title     = {More Space, Less Privacy?},
  booktitle = {Proceedings on Privacy Enhancing Technologies (PETs)},
  year      = {2026}
}
```
