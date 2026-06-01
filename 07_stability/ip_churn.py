"""
ip_churn.py — IP Address Churn Rate Analysis (Stage 7)

For each domain in the zdns snapshot directory, tracks how its A and AAAA
records change over time. Computes the average interval (in hours) between
consecutive IP set changes for each domain.

Only records an entry when the IP set actually changes — if a domain's IPs
are stable between two snapshots, no event is recorded. The output therefore
reflects genuine churn, not just re-observation of the same records.

Inputs:
  --zdns-dir    Directory containing zdns A_*.gz and AAAA_*.gz snapshot files
  --output-dir  Directory to write A_records.csv and AAAA_records.csv

Outputs:
  A_records.csv    columns: Domain, Average_IP_Change_Interval_Hours, Number_of_Changes
  AAAA_records.csv same

Usage:
  python ip_churn.py \\
      --zdns-dir  /path/to/zdns/snapshots \\
      --output-dir /path/to/output/ip_rotation/
"""

import argparse
import csv
import gzip
import json
import os
import re
from collections import defaultdict
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compute IP address churn rates from zdns snapshot files")
    parser.add_argument("--zdns-dir", required=True,
                        help="Directory containing zdns A_*.gz and AAAA_*.gz files")
    parser.add_argument("--output-dir", required=True,
                        help="Output directory for A_records.csv and AAAA_records.csv")
    return parser.parse_args()


def _extract_timestamp(filename):
    """Extract datetime from filenames like A_2024-08-21T08.01.04.gz"""
    match = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2})", filename)
    if match:
        return datetime.fromisoformat(match.group(1).replace(".", ":"))
    return None


def _resolve_cname_chain(answers):
    """Follow CNAME chains in a zdns answers list; return final IP set."""
    name_to_answers = defaultdict(list)
    for ans in answers:
        name_to_answers[ans["name"].rstrip(".")].append(ans)

    def _get_ips(name, visited=None):
        if visited is None:
            visited = set()
        if name in visited:
            return set()
        visited.add(name)
        ips = set()
        for ans in name_to_answers.get(name, []):
            if ans["type"] in ("A", "AAAA"):
                ips.add(ans["answer"])
            elif ans["type"] == "CNAME":
                ips |= _get_ips(ans["answer"].rstrip("."), visited.copy())
        return ips

    all_ips = set()
    for name in name_to_answers:
        all_ips |= _get_ips(name)
    return all_ips


def process_zdns_files(directory, record_type):
    """
    Parse all zdns snapshot files for one record type.
    Returns domain_history: domain → list of (timestamp, ip_set) for each change event.
    """
    files = []
    for fname in os.listdir(directory):
        if fname.startswith(f"{record_type}_") and fname.endswith(".gz"):
            ts = _extract_timestamp(fname)
            if ts:
                files.append((ts, fname))
    files.sort(key=lambda x: x[0])

    domain_history  = defaultdict(list)
    domain_last_ips = {}

    for i, (timestamp, fname) in enumerate(files):
        filepath = os.path.join(directory, fname)
        print(f"  [{i+1}/{len(files)}] {fname}")

        try:
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("status") != "NOERROR":
                            continue

                        domain = record.get("altered_name") or record.get("name", "")
                        domain = domain.rstrip(".")
                        if not domain:
                            continue

                        answers = record.get("data", {}).get("answers", [])
                        if not answers:
                            continue

                        ip_set = _resolve_cname_chain(answers)
                        # Filter to the correct record type only
                        filtered = {
                            ans["answer"]
                            for ans in answers
                            if ans.get("type") == record_type
                        }
                        # Also include IPs resolved via CNAME
                        filtered |= {ip for ip in ip_set}

                        # Keep only IPs of the right address-family
                        import ipaddress
                        final = set()
                        for ip in filtered:
                            try:
                                addr = ipaddress.ip_address(ip)
                                if record_type == "A"    and addr.version == 4:
                                    final.add(ip)
                                elif record_type == "AAAA" and addr.version == 6:
                                    final.add(ip)
                            except ValueError:
                                pass

                        if not final:
                            continue

                        # Only record when IPs change
                        if domain not in domain_last_ips or final != domain_last_ips[domain]:
                            domain_history[domain].append((timestamp, final))
                            domain_last_ips[domain] = final

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"  [!] Error processing {fname}: {e}")

    return domain_history


def calculate_change_intervals(domain_history):
    """Return {domain: {avg_interval_hours, num_changes}} for domains with ≥2 changes."""
    result = {}
    for domain, history in domain_history.items():
        if len(history) < 2:
            continue
        history.sort(key=lambda x: x[0])
        intervals = [
            (history[i][0] - history[i-1][0]).total_seconds() / 3600
            for i in range(1, len(history))
        ]
        result[domain] = {
            "avg_interval_hours": sum(intervals) / len(intervals),
            "num_changes":        len(intervals),
        }
    return result


def save_csv(domain_intervals, output_path):
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Domain", "Average_IP_Change_Interval_Hours", "Number_of_Changes"])
        for domain, stats in sorted(domain_intervals.items(),
                                    key=lambda x: x[1]["avg_interval_hours"]):
            writer.writerow([domain,
                             round(stats["avg_interval_hours"], 2),
                             stats["num_changes"]])
    print(f"  Wrote {len(domain_intervals):,} rows → {output_path}")


def main():
    args = parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    for record_type, out_name in [("A", "A_records.csv"), ("AAAA", "AAAA_records.csv")]:
        print(f"\nProcessing {record_type} records...")
        history   = process_zdns_files(args.zdns_dir, record_type)
        intervals = calculate_change_intervals(history)
        save_csv(intervals, os.path.join(args.output_dir, out_name))
        print(f"  {record_type}: {len(intervals):,} domains with IP changes")

    print("\n[✓] Done.")


if __name__ == "__main__":
    main()
