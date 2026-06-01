# Stage 1 — Data Collection

Crawl websites and capture DNS snapshots in parallel.

## Scripts

| Script | Purpose |
|---|---|
| `crawler.py` | Crawl domains with Chrome + Brave via Browsertime, capture HAR files |
| `continuous_dns.py` | Run zdns periodically during the crawl to snapshot A/AAAA records |
| `give_zdns_for_batch.py` | Copy zdns files timestamped within a batch's crawl window |
| `fill_missingip_helper.py` | Retry domains that failed IP extraction |
| `progress_tracker.py` | Watch file counts in output directories during crawl |

## Quick Run

```bash
# Terminal 1: Run crawler (repeat for each batch)
python crawler.py \
    --domain-list ../data/tranco_full_24.csv \
    --output-dir /your/storage/v6wft \
    --workers 25 \
    --batch 1

# Terminal 2: Run DNS collection every 20 minutes (while crawler is running)
watch -n 1200 python continuous_dns.py \
    --output-dir /your/storage/v6wft \
    --workers 8

# After batch completes: align DNS snapshots to this batch
python give_zdns_for_batch.py \
    /your/storage/v6wft/chrome/1 \
    /your/storage/v6wft/domains \
    /your/storage/v6wft/batchwise_domains/1
```

## Output Structure

```
/your/storage/v6wft/
├── chrome/1/<domain>/<domain>.har       ← HAR files (Chrome)
├── brave/1/<domain>/<domain>.har        ← HAR files (Brave)
├── domains/A_<timestamp>.gz             ← zdns A record snapshots
├── domains/AAAA_<timestamp>.gz          ← zdns AAAA record snapshots
├── batchwise_domains/1/                 ← zdns files matched to batch 1
├── index/chrome_1, brave_1 ...          ← batch domain lists
└── failed/<browser>/1/<domain>          ← retry counter files
```
