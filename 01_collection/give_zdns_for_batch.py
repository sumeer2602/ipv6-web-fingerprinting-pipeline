"""
give_zdns_for_batch.py — Align DNS Snapshots to Crawl Batch (Stage 1)

Copies all zdns A/AAAA gzip files whose timestamps fall within the time range
of a given crawl batch (determined by the creation times of website folders).

This is a post-processing helper to organize per-batch DNS data for later stages.

Inputs:
  websites_dir   Directory of website crawl folders for one batch
                 (e.g. /media/chaos/v6wft/chrome/5)
  zdns_dir       Directory containing all zdns gzip files
                 (e.g. /media/chaos/v6wft/domains)
  output_dir     Destination for matched zdns files
                 (e.g. /media/chaos/v6wft/batchwise_domains/5)

Outputs:
  Copies of matched A_*.gz and AAAA_*.gz files in <output_dir>

Usage:
  python give_zdns_for_batch.py <websites_dir> <zdns_dir> <output_dir>

  Example:
    python give_zdns_for_batch.py /media/chaos/v6wft/chrome/5 \\
                                  /media/chaos/v6wft/domains \\
                                  /media/chaos/v6wft/batchwise_domains/5
"""

import os
import re
import shutil
import sys
from datetime import datetime


def extract_timestamp(filename):
    """Extract datetime from filenames like A_2024-05-03T21.05.53.gz"""
    match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}\.\d{2}\.\d{2})', filename)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%dT%H.%M.%S")
    return None


def main(websites_dir, zdns_dir, output_dir):
    if not os.path.isdir(websites_dir):
        print(f"Error: websites directory not found: {websites_dir}")
        sys.exit(1)
    if not os.path.isdir(zdns_dir):
        print(f"Error: zdns directory not found: {zdns_dir}")
        sys.exit(1)
    os.makedirs(output_dir, exist_ok=True)

    # Collect creation times of all domain subdirectories
    folder_times = []
    for folder in os.listdir(websites_dir):
        folder_path = os.path.join(websites_dir, folder)
        if os.path.isdir(folder_path):
            try:
                folder_times.append(datetime.fromtimestamp(os.stat(folder_path).st_ctime))
            except Exception as e:
                print(f"Warning: could not stat {folder_path}: {e}")

    if not folder_times:
        print("No website folders found — nothing to do.")
        return

    earliest = min(folder_times)
    latest = max(folder_times)
    print(f"Batch time range: {earliest} → {latest}")

    # Find zdns files whose timestamps fall within the batch window
    matched = []
    for fname in os.listdir(zdns_dir):
        if fname.endswith(".gz") and ("A_" in fname or "AAAA_" in fname):
            ts = extract_timestamp(fname)
            if ts and earliest <= ts <= latest:
                matched.append(os.path.join(zdns_dir, fname))

    if not matched:
        print("No zdns files matched the batch time range.")
        return

    print(f"Copying {len(matched)} matching zdns files to {output_dir}")
    for src in matched:
        try:
            shutil.copy2(src, output_dir)
            print(f"  Copied: {os.path.basename(src)}")
        except Exception as e:
            print(f"  Failed to copy {src}: {e}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python give_zdns_for_batch.py <websites_dir> <zdns_dir> <output_dir>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
