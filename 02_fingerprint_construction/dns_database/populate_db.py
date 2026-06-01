"""
populate_db.py — Bulk-Load zdns Snapshots into PostgreSQL (Stage 2)

Scans a directory of zdns gzip files (A_*.gz and AAAA_*.gz), parses them in
parallel using multiple worker processes, and inserts all DNS records into the
PostgreSQL database defined in schema.py.

Files are interleaved (A and AAAA alternately) so the database receives both
record types incrementally rather than finishing all A records before any AAAA.

A single inserter process consumes a multiprocessing Queue, writing each batch
via PostgreSQL COPY for maximum throughput.

Inputs:
  --data-dir      Directory containing zdns A_*.gz and AAAA_*.gz files
  --db-url        PostgreSQL connection URL (default: postgresql://localhost/zdns_data)
  --num-workers   Number of parallel parser processes (default: 16)
  --start-index   Skip the first N files (useful for resuming; default: 0)

Usage:
  python populate_db.py \\
      --data-dir /media/chaos/v6wft/domains \\
      --db-url   postgresql://user@localhost/zdns_data \\
      --num-workers 22
"""

import argparse
import csv
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from multiprocessing import Process, Queue
from pathlib import Path

from sqlalchemy import create_engine

from schema import init_db
from parser import parse_zdns_file


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bulk-load zdns gzip snapshots into PostgreSQL")
    parser.add_argument("--data-dir", required=True,
                        help="Directory containing zdns A_*.gz and AAAA_*.gz files")
    parser.add_argument("--db-url", default="postgresql://localhost/zdns_data",
                        help="PostgreSQL connection URL (default: postgresql://localhost/zdns_data)")
    parser.add_argument("--num-workers", type=int, default=16,
                        help="Number of parallel parser processes (default: 16)")
    parser.add_argument("--start-index", type=int, default=0,
                        help="Skip the first N files — for resuming interrupted runs (default: 0)")
    return parser.parse_args()


def interleave_sorted_files(data_dir):
    """Interleave A and AAAA files sorted by filename (timestamp order)."""
    a_files    = sorted(Path(data_dir).glob("A_*.gz"))
    aaaa_files = sorted(Path(data_dir).glob("AAAA_*.gz"))
    interleaved = []
    for i in range(max(len(a_files), len(aaaa_files))):
        if i < len(a_files):
            interleaved.append(a_files[i])
        if i < len(aaaa_files):
            interleaved.append(aaaa_files[i])
    return interleaved


@contextmanager
def temp_csv_file():
    fd, path = tempfile.mkstemp(suffix=".csv", text=True)
    try:
        os.close(fd)
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _write_rows_to_csv(rows, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow([row["domain_id"], row["ip_address"], row["timestamp"]])


def _copy_from_csv(engine, table_name, csv_path, num_rows):
    conn = None
    try:
        conn = engine.raw_connection()
        cursor = conn.cursor()
        with open(csv_path, "r", encoding="utf-8") as f:
            cursor.copy_expert(
                f"COPY {table_name} (domain_id, ip_address, timestamp) FROM STDIN WITH CSV",
                f
            )
        conn.commit()
        cursor.close()
        print(f"  [✓] Copied {num_rows:,} records → {table_name}")
        return True
    except Exception as e:
        print(f"  [!] COPY error for {table_name}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def db_inserter(queue, db_url):
    """Single consumer process: dequeues batches and inserts via COPY."""
    engine = create_engine(db_url)
    init_db(engine)
    files_done = 0

    while True:
        item = queue.get()
        if item is None:   # sentinel — all workers finished
            break

        record_cls, rows = item
        if not rows:
            continue

        try:
            with temp_csv_file() as csv_path:
                _write_rows_to_csv(rows, csv_path)
                _copy_from_csv(engine, record_cls.__tablename__, csv_path, len(rows))
        except Exception as e:
            print(f"  [!] DB insert error: {e}")

        files_done += 1
        print(f"  Files inserted: {files_done}  (queue depth: {queue.qsize()})")

    print("[✓] Inserter process finished")


def worker(files, queue, db_url):
    """Parser worker: processes its assigned files and pushes batches to queue."""
    for file in files:
        fname = file.stem
        try:
            record_type, timestamp_str = fname.split("_", 1)
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%dT%H.%M.%S")
        except ValueError:
            print(f"  [-] Skipping malformed filename: {file}")
            continue

        print(f"  [+] Worker processing: {file.name}")
        parse_zdns_file(file, record_type, queue, timestamp, db_url)


def main():
    args = parse_args()

    all_files = interleave_sorted_files(args.data_dir)
    total = len(all_files)
    print(f"Found {total} zdns files in {args.data_dir}")

    if args.start_index > 0:
        print(f"Skipping first {args.start_index} files (--start-index)")
        all_files = all_files[args.start_index:]

    print(f"Processing {len(all_files)} files with {args.num_workers} workers")

    chunks = [all_files[i::args.num_workers] for i in range(args.num_workers)]
    queue  = Queue(maxsize=20)

    inserter = Process(target=db_inserter, args=(queue, args.db_url))
    inserter.start()

    workers = []
    for chunk in chunks:
        p = Process(target=worker, args=(chunk, queue, args.db_url))
        p.start()
        workers.append(p)

    for p in workers:
        p.join()

    queue.put(None)   # signal inserter to exit
    inserter.join()
    print("[✓] All done.")


if __name__ == "__main__":
    main()
