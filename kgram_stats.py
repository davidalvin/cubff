#!/usr/bin/env python3
"""
Analyze k-gram frequencies in a BFF soup snapshot.

Usage:
    python kgram_stats.py --file path/to/snapshot.dat [options]

Options:
    --lengths 2,4,8         Comma-separated list of k-gram lengths to analyze
    --top 20                Show top-N most frequent k-grams for each length
    --no-color              Disable ANSI color output for compatibility
    --normalize-noops       Replace all non-opcode bytes with a single no-op token
"""

import argparse
import collections
import struct
import sys
from pathlib import Path

# Each program is 64 bytes (half of a full BFF program)
TAPE_SIZE = 64

# Maps byte values to their printable BFF character
BFF_COMMANDS = {
    0x00: '0',    # null
    0x5b: '[', 0x5d: ']',
    0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',',
    0x3c: '<', 0x3e: '>',
    0x7b: '{', 0x7d: '}',
}

# Set of valid BFF opcodes
BFF_OP_BYTES = set(BFF_COMMANDS.keys())


def load_soup(path: Path):
    """
    Load raw soup data from a .dat snapshot file.

    Returns:
        raw (bytes): Flattened byte stream of all programs
        num_progs (int): Number of programs in the soup
    """
    with path.open("rb") as f:
        header = f.read(24)
        if len(header) != 24:
            sys.exit("File too small or corrupt.")
        reset_idx, num_progs, epoch = struct.unpack("<QQQ", header)
        print(f"snapshot epoch {epoch}, {num_progs} programs")

        raw = f.read(num_progs * TAPE_SIZE)
        if len(raw) != num_progs * TAPE_SIZE:
            sys.exit("Truncated file.")

    return raw, num_progs


def count_kgrams(raw: bytes, lengths, normalize_noops=False):
    """
    Count k-grams of specified lengths across all programs in the soup.

    Only k-grams that start with a valid BFF opcode are counted. This helps reduce
    redundancy from repeated junk bytes and focuses the analysis on instruction-aligned
    motifs.

    Args:
        raw (bytes): Flat byte string of concatenated programs.
        lengths (list[int]): List of k values to analyze (e.g., [2, 4, 8]).
        normalize_noops (bool): If True, all non-opcode bytes are replaced with 255.

    Returns:
        dict[int, Counter]: Dictionary mapping k to frequency Counter of k-grams.
    """
    counts = {k: collections.Counter() for k in lengths}
    total_programs = len(raw) // TAPE_SIZE

    for prog_idx in range(total_programs):
        # Extract a single program from the soup
        offset = prog_idx * TAPE_SIZE
        prog = raw[offset : offset + TAPE_SIZE]

        # Optionally replace all non-opcode bytes with a normalized "noop" marker
        if normalize_noops:
            prog = bytes(b if b in BFF_OP_BYTES else 255 for b in prog)

        for k in lengths:
            if k > TAPE_SIZE:
                continue  # Skip if k is longer than the program

            # Slide a window of size k over the program
            for i in range(TAPE_SIZE - k + 1):
                first_byte = prog[i]

                # Only count if the first byte is a known BFF opcode
                if first_byte not in BFF_OP_BYTES:
                    continue

                kgram = prog[i : i + k]
                counts[k][kgram] += 1

        # Print progress every 10k programs for visibility
        if prog_idx > 0 and prog_idx % 10000 == 0:
            print(f"Processed {prog_idx:,} / {total_programs:,} programs...")

    return counts


def format_bff_kgram(gram: bytes, use_color=True):
    """
    Convert a k-gram to a human-readable, optionally colorized string.
    """
    def color(c, kind):
        if not use_color:
            return c
        if kind == 'cmd':
            return f"\033[38;5;255m{c}\033[0m"  # bright white
        elif kind == 'noop':
            return f"\033[38;5;237m{c}\033[0m"  # gray
        return c

    out = []
    for b in gram:
        if b in BFF_COMMANDS:
            out.append(color(BFF_COMMANDS[b], 'cmd'))
        else:
            out.append(color(chr(0x0100 + b), 'noop'))
    return ''.join(out)


def main():
    # Parse CLI arguments
    ap = argparse.ArgumentParser(description="Analyze BFF soup k-gram frequencies.")
    ap.add_argument("--file", "-f", required=True, help="Path to .dat snapshot file")
    ap.add_argument("--lengths", type=str, default="4,5,6",
                    help="Comma-separated list of k-gram lengths (e.g. 2,4,8)")
    ap.add_argument("--top", type=int, default=20, help="Top N k-grams to show per length")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    ap.add_argument("--normalize-noops", action="store_true", help="Treat all non-op bytes as a single no-op")
    args = ap.parse_args()

    # Convert lengths argument to sorted list of ints
    try:
        lengths = sorted(set(int(k) for k in args.lengths.split(',')))
    except ValueError:
        sys.exit("Invalid --lengths argument: must be a list like 2,4,8")

    # Show parsed config
    print(f"Analyzing file: {args.file}")
    print(f"K-gram lengths: {lengths}")
    print(f"Top N: {args.top}")
    print(f"Normalize NO-OPS: {args.normalize_noops}")
    print(f"Color Output: {'Disabled' if args.no_color else 'Enabled'}")
    print("")

    # Load file and count
    raw, _ = load_soup(Path(args.file))
    print("Counting k-grams...")
    counts = count_kgrams(raw, lengths, normalize_noops=args.normalize_noops)

    # Display results
    for k in lengths:
        print(f"\n=== top {args.top} {k}-grams ===")
        for gram, c in counts[k].most_common(args.top):
            show = format_bff_kgram(gram, use_color=not args.no_color)
            print(f"{show:<30} {c:>8}")


if __name__ == "__main__":
    main()
