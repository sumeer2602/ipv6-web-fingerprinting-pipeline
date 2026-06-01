"""
query.py — Time-Synchronized IP Lookup from PostgreSQL (Stage 2)

Given a domain name and a crawl timestamp, returns the IP address(es) that
resolved for that domain at the closest available snapshot time in the database.

This is the DNS lookup primitive used by ip_connections_browser.py to convert
domain fingerprints (domain names + crawl timing) into IP-based connections.
The time-synchronized lookup is critical: we want the IP that was actually
serving that domain at the time of the crawl, not a current or arbitrary lookup.

Inputs (importable function):
  get_closest_ips(domain_name, timestamp, db_url, record_type="A")
    Returns: list of IP strings (may be empty if domain not found)

Standalone usage:
  python query.py --domain google.com \\
                  --timestamp "2024-08-21 10:00:00" \\
                  --db-url postgresql://localhost/zdns_data \\
                  --record-type AAAA
"""

import argparse
from datetime import datetime

from sqlalchemy import create_engine, func

from schema import init_db, Domain, ARecord, AAAARecord


def get_closest_ips(domain_name, timestamp, db_url, record_type="A"):
    """
    Return the IP addresses that resolved for domain_name at the snapshot
    closest in time to the given timestamp.

    Args:
        domain_name : domain to look up (e.g. "google.com")
        timestamp   : datetime of the crawl that needs this resolution
        db_url      : PostgreSQL connection URL
        record_type : "A" (IPv4) or "AAAA" (IPv6)

    Returns:
        List of IP address strings. Empty list if domain not found or no records.
    """
    engine = create_engine(db_url)
    Session = init_db(engine)
    session = Session()

    try:
        domain = session.query(Domain).filter_by(domain_name=domain_name).first()
        if not domain:
            return []

        Record = ARecord if record_type == "A" else AAAARecord

        # Find the snapshot timestamp closest to the crawl time
        closest = (
            session.query(Record.timestamp)
            .filter_by(domain_id=domain.domain_id)
            .order_by(
                func.abs(
                    func.extract("epoch", Record.timestamp)
                    - func.extract("epoch", timestamp)
                )
            )
            .first()
        )

        if not closest:
            return []

        records = (
            session.query(Record.ip_address)
            .filter_by(domain_id=domain.domain_id, timestamp=closest[0])
            .all()
        )
        return [r[0] for r in records]

    finally:
        session.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Look up IP address(es) for a domain at a given crawl timestamp")
    parser.add_argument("--domain", required=True,
                        help="Domain name to look up")
    parser.add_argument("--timestamp", required=True,
                        help="Crawl timestamp, format: 'YYYY-MM-DD HH:MM:SS'")
    parser.add_argument("--db-url", default="postgresql://localhost/zdns_data",
                        help="PostgreSQL connection URL")
    parser.add_argument("--record-type", choices=["A", "AAAA"], default="AAAA",
                        help="DNS record type (default: AAAA)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ts = datetime.strptime(args.timestamp, "%Y-%m-%d %H:%M:%S")
    ips = get_closest_ips(args.domain, ts, args.db_url, args.record_type)
    if ips:
        print(f"{args.record_type} records for {args.domain} near {args.timestamp}:")
        for ip in ips:
            print(f"  {ip}")
    else:
        print(f"No {args.record_type} records found for {args.domain}")
