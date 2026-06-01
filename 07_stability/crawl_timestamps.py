"""
crawl_timestamps.py — Report Crawl Batch Timestamp Range (Stage 7 / Utility)

Given a crawl batch directory (where each website has a subdirectory created
when its HAR file was saved), reports the earliest and latest folder creation
times. Useful for correlating a crawl batch with the zdns snapshots collected
during the same time window.

Input:
  directory   Path to a crawl batch directory (e.g. chrome/1/ or ip_connections/1/)

Output:
  Prints the earliest and latest subdirectory creation timestamps.

Usage:
  python crawl_timestamps.py /path/to/chrome/1
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Report the creation-time range of subdirectories in a crawl batch")
    parser.add_argument("directory",
                        help="Crawl batch directory (each website is a subdirectory)")
    return parser.parse_args()


def get_folder_creation_times(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a valid directory")

    timestamps = []
    for item in directory.iterdir():
        if item.is_dir():
            try:
                timestamps.append(item.stat().st_ctime)
            except Exception as e:
                print(f"  [!] Could not stat {item}: {e}")

    if not timestamps:
        return None, None

    return datetime.fromtimestamp(min(timestamps)), datetime.fromtimestamp(max(timestamps))


def main():
    args = parse_args()
    earliest, latest = get_folder_creation_times(args.directory)
    if earliest:
        print(f"Earliest folder creation: {earliest}")
        print(f"Latest   folder creation: {latest}")
    else:
        print("No subdirectories found.")


if __name__ == "__main__":
    main()
