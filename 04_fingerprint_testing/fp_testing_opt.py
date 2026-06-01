"""
fp_testing_opt.py — Fingerprint Matching (Stage 4)

Tests whether enrolled IP fingerprints can correctly re-identify websites
from their test-phase IP connections. Uses entropy-weighted scoring:
the more unique an IP is (high entropy), the more it contributes to the score.

For each test site, finds the enrolled fingerprint with the highest matching
score across both IPv4 and dual-stack (IPv6) channels.

Scoring:
  - IPv4 match: sum of entropy of matching secondary IPs (key "1")
  - Dual-stack match: sum of IPv6 + fallback IPv4 entropy for matching IPs

Output CSV (fp_match_results.csv) columns:
  test_site         The website being tested
  ipv4_match        Best-matching enrolled site via IPv4
  ipv4_score        Matching score for IPv4
  dual_stack_match  Best-matching enrolled site via dual-stack (IPv6)
  dual_stack_score  Matching score for dual-stack

  dual_stack_match == test_site  →  correct IPv6 identification

Inputs:
  ip_connections_dir    Directory of IP connection .txt files (test phase)
  conn_cache_json       JSON file listing connection filenames to process
  fingerprint_dir       Directory of enrolled IP fingerprint .txt files
  fp_cache_dir          Directory containing directory_cache.json for fingerprints
  ipv4_entropy_csv      CSV with columns: ip, avg_entropy (for IPv4 IPs)
  ipv6_entropy_csv      CSV with columns: ip, avg_entropy (for IPv6/AAAA IPs)
  [num_processes]       Optional: number of parallel processes (default: auto)

Usage:
  python fp_testing_opt.py \\
      /media/chaos/v6wft/ip_connections/1 \\
      /media/chaos/v6wft/ip_connections/1/conn_cache.json \\
      /media/chaos/v6wft/ip_based/1 \\
      /media/chaos/v6wft/ip_based/1 \\
      ip_entropy_A.csv \\
      ip_entropy_AAAA.csv

Notes:
  - Results are written to <ip_connections_dir>/fp_match_results.csv
  - Loads ALL fingerprints and connections into RAM before matching
    (requires ~32–64 GB RAM for 500k sites)
  - Uses multiprocessing.Pool with imap for parallel matching
"""

import multiprocessing as mp
import os
import sys
import time
import json
import pandas as pd
from pathlib import Path


# --- Data loading ---

def load_ip_connections(file_path):
    """Load a 2-JSON-line connection file. Returns (ipv4_dict, dual_dict)."""
    with open(file_path, 'r') as f:
        content = f.read().strip()
    split_index = content.find('}\n{')
    if split_index == -1:
        raise ValueError("Expected 2 JSON objects separated by newline")
    ipv4 = json.loads(content[:split_index + 1])
    dual = json.loads(content[split_index + 1:])
    return ipv4, dual


def load_entropy_map(csv_path):
    """Load ip→entropy mapping from CSV."""
    df = pd.read_csv(csv_path)
    return dict(zip(df['ip'], df['avg_entropy']))


def load_fingerprints(fingerprint_dir, cache_file):
    """Load all enrolled IP fingerprints from directory using cache file."""
    with open(cache_file, 'r') as f:
        filenames = json.load(f)
    fingerprints = {}
    for i, fname in enumerate(filenames):
        if (i + 1) % 10000 == 0:
            print(f"  Loaded {i+1:,} fingerprints...")
        path = Path(fingerprint_dir) / fname
        try:
            with open(path, 'r') as f:
                ipv4_fp = json.loads(f.readline())
                ipv6_fp = json.loads(f.readline())
            fingerprints[fname.replace(".txt", "")] = (ipv4_fp, ipv6_fp)
        except Exception as e:
            print(f"  Warning: could not load {fname}: {e}")
    return fingerprints


def load_all_connections(conn_dir, conn_cache_path):
    """Load all test-phase connection files into memory."""
    with open(conn_cache_path, 'r') as f:
        conn_files = json.load(f)
    connections = {}
    for i, fname in enumerate(conn_files):
        if (i + 1) % 10000 == 0:
            print(f"  Loaded {i+1:,} connections...")
        site = fname.replace(".txt", "")
        path = Path(conn_dir) / fname
        try:
            ipv4, dual = load_ip_connections(path)
            connections[site] = (ipv4, dual)
        except Exception as e:
            print(f"  Warning: could not load {fname}: {e}")
    print(f"  Loaded {len(connections):,} connection files")
    return connections


# --- Preprocessing ---

def preprocess_fingerprints(fingerprints):
    """Convert fingerprint lists to sets for fast intersection."""
    return {
        site: {
            'ipv4_0_set': set(ipv4_fp.get("0", [])),
            'ipv4_1_set': set(ipv4_fp.get("1", [])),
            'ipv6_0_set': set(ipv6_fp.get("0", [])),
            'ipv6_1_set': set(ipv6_fp.get("1", []))
        }
        for site, (ipv4_fp, ipv6_fp) in fingerprints.items()
    }


def preprocess_connections(connections):
    """Convert connection lists to sets for fast intersection."""
    return {
        site: {
            'ipv4_0_set': set(ipv4_conn.get("0", [])),
            'ipv4_1_set': set(ipv4_conn.get("1", [])),
            'dual_0_set': set(dual_conn.get("0", [])),
            'dual_1_set': set(dual_conn.get("1", []))
        }
        for site, (ipv4_conn, dual_conn) in connections.items()
    }


# --- Matching (runs in worker processes) ---

def worker_init(fingerprints_processed, ipv4_ent, ipv6_ent):
    global worker_fingerprints, worker_ipv4_ent, worker_ipv6_ent
    worker_fingerprints = fingerprints_processed
    worker_ipv4_ent = ipv4_ent
    worker_ipv6_ent = ipv6_ent


def process_single_connection(conn_item):
    """Match one test connection against all enrolled fingerprints."""
    site_test, conn_data = conn_item

    best_ipv4, best_ds = None, None
    best_v4_score, best_ds_score = 0.0, 0.0

    ipv4_0 = conn_data['ipv4_0_set']
    ipv4_1 = conn_data['ipv4_1_set']
    dual_0 = conn_data['dual_0_set']
    dual_1 = conn_data['dual_1_set']

    for site_fp, fp_data in worker_fingerprints.items():
        # IPv4 matching
        if ipv4_0 & fp_data['ipv4_0_set']:
            if not ipv4_1 and not fp_data['ipv4_1_set']:
                score_v4 = worker_ipv4_ent.get(next(iter(ipv4_0)), 0.0)
            else:
                matching = ipv4_1 & fp_data['ipv4_1_set']
                score_v4 = sum(worker_ipv4_ent.get(ip, 0.0) for ip in matching)
            if score_v4 > best_v4_score:
                best_v4_score = score_v4
                best_ipv4 = site_fp

        # Dual-stack (IPv6) matching
        if dual_0 & fp_data['ipv6_0_set']:
            matching_v6 = dual_1 & fp_data['ipv6_1_set']
            matching_v4_fallback = dual_1 & fp_data['ipv4_1_set']
            score_ds = (sum(worker_ipv6_ent.get(ip, 0.0) for ip in matching_v6) +
                        sum(worker_ipv4_ent.get(ip, 0.0) for ip in matching_v4_fallback))
            if score_ds > best_ds_score:
                best_ds_score = score_ds
                best_ds = site_fp

    return {
        "test_site": site_test,
        "ipv4_match": best_ipv4,
        "ipv4_score": best_v4_score,
        "dual_stack_match": best_ds,
        "dual_stack_score": best_ds_score
    }


def optimal_process_count():
    n = mp.cpu_count()
    if n <= 8:
        return min(n, 4)
    elif n <= 32:
        return min(n, 16)
    return min(n, 32)


def match_all_parallel(connections, fingerprints, ipv4_ent, ipv6_ent, num_processes=None):
    if num_processes is None:
        num_processes = optimal_process_count()

    total = len(connections)
    print(f"Matching {total:,} connections against {len(fingerprints):,} fingerprints")
    print(f"Using {num_processes} processes")

    fps_proc = preprocess_fingerprints(fingerprints)
    conns_proc = preprocess_connections(connections)
    work_items = list(conns_proc.items())

    t0 = time.time()
    results = []
    with mp.Pool(processes=num_processes,
                 initializer=worker_init,
                 initargs=(fps_proc, ipv4_ent, ipv6_ent)) as pool:
        for i, result in enumerate(pool.imap(process_single_connection, work_items, chunksize=10)):
            results.append(result)
            if (i + 1) % 1000 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(f"  {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%) "
                      f"— {rate:.0f}/s — ETA {eta:.0f}s")
    print(f"Matching done in {time.time()-t0:.1f}s")
    return results


# --- Entry point ---

if __name__ == "__main__":
    if len(sys.argv) not in [7, 8]:
        print("Usage: python fp_testing_opt.py <conn_dir> <conn_cache_json> "
              "<fp_dir> <fp_cache_dir> <ipv4_entropy.csv> <ipv6_entropy.csv> [num_processes]")
        sys.exit(1)

    conn_dir = Path(sys.argv[1])
    conn_cache = Path(sys.argv[2])
    fp_dir = Path(sys.argv[3])
    fp_cache_dir = Path(sys.argv[4])
    ipv4_entropy_file = sys.argv[5]
    ipv6_entropy_file = sys.argv[6]
    num_processes = int(sys.argv[7]) if len(sys.argv) == 8 and sys.argv[7] != '0' else None

    print(f"Available CPUs: {mp.cpu_count()}  |  Recommended: {optimal_process_count()}")

    print("Loading entropy maps...")
    ipv4_ent = load_entropy_map(ipv4_entropy_file)
    ipv6_ent = load_entropy_map(ipv6_entropy_file)

    print("Loading fingerprints...")
    fingerprints = load_fingerprints(fp_dir, fp_cache_dir / "directory_cache.json")

    print("Loading connections...")
    connections = load_all_connections(conn_dir, conn_cache)

    results = match_all_parallel(connections, fingerprints, ipv4_ent, ipv6_ent, num_processes)

    output_csv = conn_dir / "fp_match_results.csv"
    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"Results saved to {output_csv}  ({len(results):,} rows)")
