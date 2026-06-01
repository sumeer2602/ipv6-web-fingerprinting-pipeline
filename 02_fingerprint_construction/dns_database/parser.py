"""
parser.py — Parse zdns Gzip Files into PostgreSQL (Stage 2)

Reads a single zdns gzip output file (A or AAAA records) and inserts all
unique (domain, ip, timestamp) triples into the PostgreSQL database.
Called by populate_db.py for each file in the zdns snapshot directory.

Each zdns file contains JSON Lines records. For each domain, we store every
answer (A, AAAA, or CNAME) as a separate row, tagged with the file's timestamp.
Duplicates are deduplicated before insertion using PostgreSQL COPY for speed.

Inputs:
  file_path   — Path to a zdns gzip file (e.g. A_2024-08-21T20.01.19.gz)
  record_type — "A" or "AAAA"
  queue       — multiprocessing.Queue to pass (record_class, rows) to the DB inserter
  timestamp   — datetime extracted from the filename

Dependencies:
  schema.py — SQLAlchemy ORM models (Domain, ARecord, AAAARecord)
"""

import gzip
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from schema import ARecord, AAAARecord, Domain


def parse_zdns_file(file_path, record_type, queue, timestamp, db_url):
    """
    Parse one zdns gzip file and put (record_class, rows) onto the queue.

    Args:
        file_path   : pathlib.Path to the .gz file
        record_type : "A" or "AAAA"
        queue       : multiprocessing.Queue consumed by the DB inserter process
        timestamp   : datetime corresponding to this file's scan time
        db_url      : PostgreSQL connection URL
    """
    engine = create_engine(db_url)
    Session = scoped_session(sessionmaker(bind=engine))
    session = Session()

    domain_cache = {}   # domain_name → domain_id  (avoid repeated DB lookups)
    unique_records = set()
    rows = []

    try:
        with gzip.open(file_path, "rt") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    answers = record.get("data", {}).get("answers", [])
                    if not answers:
                        continue

                    for ans in answers:
                        rtype  = ans.get("type")
                        name   = ans.get("name")
                        answer = ans.get("answer")

                        if not name or not answer:
                            continue
                        if rtype not in (record_type, "CNAME"):
                            continue

                        # Insert domain row if not cached
                        if name not in domain_cache:
                            domain = session.query(Domain).filter_by(domain_name=name).first()
                            if not domain:
                                try:
                                    domain = Domain(domain_name=name)
                                    session.add(domain)
                                    session.commit()
                                except Exception:
                                    session.rollback()
                                    domain = session.query(Domain).filter_by(domain_name=name).first()
                                    if not domain:
                                        continue
                            domain_cache[name] = domain.domain_id

                        domain_id = domain_cache[name]
                        record_cls = ARecord if record_type == "A" else AAAARecord

                        key = (domain_id, answer, timestamp.isoformat())
                        if key not in unique_records:
                            unique_records.add(key)
                            rows.append({
                                "domain_id": domain_id,
                                "ip_address": answer,
                                "timestamp":  timestamp.isoformat(),
                            })

                except Exception as e:
                    print(f"[!] Error parsing line in {file_path.name}: {e}")

        if rows:
            print(f"  {file_path.name}: {len(rows):,} unique records → queue")
            queue.put((record_cls, rows))
        else:
            print(f"  {file_path.name}: no records to insert")

    except Exception as e:
        print(f"[!] Failed to open or parse {file_path}: {e}")
    finally:
        session.close()
