"""
progress_tracker.py — Monitor Crawl Progress (Stage 1)

Polls a parent directory every N seconds and prints the number of files
in each immediate subdirectory. Use this to watch crawl batch output
directories fill up in real time.

Usage:
  python progress_tracker.py /media/chaos/v6wft/chrome/1 --interval 30
  python progress_tracker.py /media/chaos/v6wft/ip_based/1
"""

import argparse
import os
import time
from collections import defaultdict


def get_file_counts(parent_dir):
    """Count files in each immediate subdirectory."""
    counts = defaultdict(int)
    for root, dirs, files in os.walk(parent_dir):
        if root == parent_dir:
            for subdir in dirs:
                subdir_path = os.path.join(parent_dir, subdir)
                counts[subdir] = sum(1 for _ in os.scandir(subdir_path) if _.is_file())
    return counts


def main():
    parser = argparse.ArgumentParser(description="Watch file counts in subdirectories")
    parser.add_argument("parent_dir", help="Directory to monitor")
    parser.add_argument("--interval", type=int, default=60,
                        help="Polling interval in seconds (default: 60)")
    args = parser.parse_args()

    if not os.path.isdir(args.parent_dir):
        print(f"Error: '{args.parent_dir}' is not a valid directory.")
        return

    print(f"Monitoring {args.parent_dir} every {args.interval}s  (Ctrl+C to stop)")
    try:
        while True:
            counts = get_file_counts(args.parent_dir)
            os.system('clear')
            print(f"Files per subdirectory in: {args.parent_dir}")
            print("-" * 40)
            for subdir in sorted(counts, key=lambda x: (x.isdigit() and int(x), x)):
                print(f"  {subdir:20s}  {counts[subdir]:>8,} files")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
