"""
cleaner.py — Remove Empty IP Connection Files (Stage 4)

Deletes .txt files from the ip_connections directory where the first line is
'[]' (empty connection list). These occur when a website was crawled but no
network connections were captured, and they would produce spurious zero-score
matches in fp_testing_opt.py.

Run this before fingerprint testing to keep the connection directory clean.

Inputs:
  --directory   Directory of IP connection .txt files to clean
                (e.g. /media/chaos/v6wft/ip_connections/1)

Usage:
  python cleaner.py --directory /media/chaos/v6wft/ip_connections/1
"""

import argparse
import os


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete IP connection files with empty first line")
    parser.add_argument("--directory", required=True,
                        help="Directory of .txt connection files to clean")
    return parser.parse_args()


def main():
    args = parse_args()
    deleted = 0
    kept = 0

    for fname in os.listdir(args.directory):
        if not fname.endswith('.txt'):
            continue
        path = os.path.join(args.directory, fname)
        try:
            with open(path, 'r') as f:
                first_line = f.readline().strip()
            if first_line == '[]':
                os.remove(path)
                deleted += 1
            else:
                kept += 1
        except Exception as e:
            print(f"Warning: could not process {path}: {e}")

    print(f"Done. Deleted {deleted:,} empty files, kept {kept:,} files.")


if __name__ == "__main__":
    main()
