# Stage 2 — Fingerprint Construction

Convert HAR files and DNS data into IP-based fingerprints.

## Scripts

| Script | Purpose |
|---|---|
| `basicFingerprint.py` | Parse HAR files → domain-based fingerprints (.txt per site) |
| `build_dns_db.py` | Merge zdns gzip files → flat JSON DNS lookup (database_A/AAAA.json) |
| `ip_fingerprints.py` | Domain FPs + JSON DB → IP-based fingerprints (.txt per site) |
| `ip_connections_browser.py` | Test-crawl HAR + time-synced zdns → test IP connections |

## Run Order

```bash
# 1. Extract domain fingerprints from HAR files
python basicFingerprint.py \
    --har-dir /storage/v6wft/chrome/1 \
    --output-dir /storage/v6wft/domain_based/chrome/1

# 2a. Build IPv6 DNS database (large file — may take 30+ min)
python build_dns_db.py \
    --zdns-dir /storage/v6wft/domains \
    --output database_AAAA.json \
    --record-type AAAA

# 2b. Build IPv4 DNS database
python build_dns_db.py \
    --zdns-dir /storage/v6wft/domains \
    --output database_A.json \
    --record-type A

# 3. Convert domain fingerprints to IP fingerprints (run per batch)
python ip_fingerprints.py \
    --domain-fp-dir /storage/v6wft/domain_based/chrome/1 \
    --db-a database_A.json \
    --db-aaaa database_AAAA.json \
    --output-dir /storage/v6wft/ip_based/1

# 4. Extract test-phase connections (for the test crawl batch only)
python ip_connections_browser.py \
    --har-dir /storage/v6wft/chrome/test_batch \
    --zdns-dir /storage/v6wft/domains \
    --db-dir /path/to/db_dir \
    --output-dir /storage/v6wft/ip_connections/1
```

## DNS Database Format

`database_A.json` / `database_AAAA.json`:
```json
{
  "example.com":        ["93.184.216.34"],
  "www.example.com":    ["cdn.example.net."],
  "cdn.example.net.":   ["192.0.2.1"]
}
```
CNAME targets end with `.` and are resolved recursively during fingerprint building.

## Time-Synchronized DNS (ip_connections_browser.py)

This script intentionally uses a zdns snapshot captured **at least 5 days after**
the test crawl. This simulates the DNS state a real fingerprinter would observe —
potentially stale relative to the crawl — rather than using the exact crawl-time DNS.

The `--min-gap-days` parameter controls this minimum gap (default: 5).
