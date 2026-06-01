# PostgreSQL DNS Database

This subdirectory contains scripts to build and query a PostgreSQL database
of A and AAAA DNS records collected by zdns during continuous crawling.

## Why PostgreSQL?

The zdns continuous crawl produces ~6,800 snapshot files (~500 GB total) over
the crawl period. Building a time-indexed database allows:
- Fast nearest-timestamp lookups (used by `ip_connections_browser.py`)
- Efficient per-IP domain counts (used by `ip_entropy.py` and `domains_per_ip_db.py`)

**Alternative (no PostgreSQL):** `../build_dns_db.py` builds a flat JSON file
from the same zdns files — faster to set up but does not support time-synchronized
lookups. The flat JSON approach was used for IP fingerprint construction
(`ip_fingerprints.py`). The PostgreSQL approach was used for IP entropy
(`03_entropy/ip_entropy.py`) and the domains-per-IP figure.

## Setup

```bash
# 1. Create the database
createdb zdns_data

# 2. Install Python dependencies
pip install sqlalchemy psycopg2-binary

# 3. Create tables (run once)
python -c "
from sqlalchemy import create_engine
from schema import init_db
engine = create_engine('postgresql://localhost/zdns_data')
init_db(engine)
print('Tables created.')
"

# 4. Populate from zdns snapshots (~hours, depending on data volume)
python populate_db.py \
    --data-dir /path/to/zdns/snapshots \
    --db-url   postgresql://localhost/zdns_data \
    --num-workers 22
```

## Scripts

| Script | Description |
|---|---|
| `schema.py` | SQLAlchemy ORM models (Domain, ARecord, AAAARecord) |
| `parser.py` | Parse one zdns gzip file → push records to insertion queue |
| `populate_db.py` | Orchestrate parallel parsing and bulk insertion |
| `query.py` | Look up IPs for a domain at the closest snapshot timestamp |
| `domains_per_ip_db.py` | Compute domains-per-IP distribution from a snapshot |

## Resuming an Interrupted Run

`populate_db.py` accepts `--start-index N` to skip the first N files.
Use this if the run was interrupted:

```bash
# Check how many files were already processed, then resume:
python populate_db.py \
    --data-dir /path/to/zdns/snapshots \
    --db-url   postgresql://localhost/zdns_data \
    --start-index 1325    # resume from file 1325
```

## Database Size

- ~550k domains × ~6800 snapshots → A records table: ~tens of millions of rows
- AAAA records: smaller (only dual-stack domains resolve to IPv6)
- Total DB size: ~hundreds of GB depending on crawl duration
