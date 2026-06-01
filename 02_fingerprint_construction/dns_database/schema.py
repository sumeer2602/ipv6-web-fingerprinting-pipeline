"""
schema.py — PostgreSQL Database Schema for zdns DNS Records (Stage 2)

Defines the SQLAlchemy ORM models for the PostgreSQL database used to store
A and AAAA DNS records collected by zdns during continuous crawling.

Tables:
  domains     — unique domain names (domain_id, domain_name)
  a_records   — A record snapshots  (record_id, domain_id, ip_address, timestamp)
  aaaa_records— AAAA record snapshots (same structure as a_records)

This schema is used by:
  populate_db.py — to create tables and insert records
  query.py       — to look up IPs by domain + timestamp
  ip_entropy.py  — to build per-IP average entropy values
  domains_per_ip_db.py — to compute the domains-per-IP distribution

Usage:
  from schema import Base, Domain, ARecord, AAAARecord, init_db
  engine = create_engine(db_url)
  Session = init_db(engine)   # creates tables if they don't exist
"""

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Domain(Base):
    """One row per unique domain name observed in zdns output."""
    __tablename__ = "domains"
    domain_id   = Column(Integer, primary_key=True)
    domain_name = Column(String, unique=True, index=True)
    a_records    = relationship("ARecord",    back_populates="domain")
    aaaa_records = relationship("AAAARecord", back_populates="domain")


class ARecord(Base):
    """A DNS A record snapshot: one row per (domain, ip, timestamp) triple."""
    __tablename__ = "a_records"
    record_id  = Column(BigInteger, primary_key=True)
    domain_id  = Column(Integer, ForeignKey("domains.domain_id"))
    ip_address = Column(String)
    timestamp  = Column(DateTime)
    domain     = relationship("Domain", back_populates="a_records")


class AAAARecord(Base):
    """A DNS AAAA record snapshot: one row per (domain, ip, timestamp) triple."""
    __tablename__ = "aaaa_records"
    record_id  = Column(BigInteger, primary_key=True)
    domain_id  = Column(Integer, ForeignKey("domains.domain_id"))
    ip_address = Column(String)
    timestamp  = Column(DateTime)
    domain     = relationship("Domain", back_populates="aaaa_records")


def init_db(engine):
    """Create all tables (idempotent) and return a Session factory."""
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
