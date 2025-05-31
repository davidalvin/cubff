import os
import csv
import struct
from collections import Counter

# ============================================================================
# Configuration Constants
# ============================================================================

TAPE_SIZE = 64
NOOP_SYMBOL = '∅'

# ============================================================================
# Byte-to-Symbol Mapping
# ============================================================================

BFF_COMMANDS = {
    0x00: '0', 0x5b: '[', 0x5d: ']', 0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',', 0x3c: '<', 0x3e: '>', 0x7b: '{', 0x7d: '}'
}

def is_noop(byte):
    return chr(byte) not in "[]+-.,<>{}0"

def get_bff_byte_map():
    symbol_map = {}
    for i in range(256):
        if i in BFF_COMMANDS:
            symbol_map[i] = BFF_COMMANDS[i]
        else:
            try:
                symbol_map[i] = chr(i)
            except:
                symbol_map[i] = f"\\x{i:02x}"
    return symbol_map

BFF_SYMBOL_MAP = get_bff_byte_map()

# ============================================================================
# Binary Soup I/O
# ============================================================================

def load_soup(path: str, max_programs: int | None = None) -> bytes:
    """Reads a binary soup file and returns raw program bytes."""
    with open(path, "rb") as f:
        header = f.read(24)  # 3 unsigned 64-bit values
        _, n_programs, _ = struct.unpack('<QQQ', header)
        n_read = min(max_programs or n_programs, n_programs)
        blob = f.read(n_read * TAPE_SIZE)
    print(f"Loaded {n_read} programs from {path}")
    return blob

def to_symbol_sequences(raw: bytes, normalize_noops: bool = False) -> list[list[str]]:
    """Converts raw byte programs into symbolic opcode sequences."""
    programs = []
    for i in range(0, len(raw), TAPE_SIZE):
        chunk = raw[i:i + TAPE_SIZE]
        syms = [
            BFF_COMMANDS.get(b, NOOP_SYMBOL if normalize_noops else chr(0x100 + b))
            for b in chunk
        ]
        programs.append(syms)
    return programs

# ============================================================================
# CSV + Metadata Helpers
# ============================================================================

def save_partial_soup_csv_raw(state, path, epoch, replace_noops=True, as_characters=True, program_size=128, num_to_save=10):
    binary_sample = state.soup[:num_to_save * program_size]
    suffix = "_chars" if as_characters else "_raw"
    csv_path = os.path.join(path, f"partial_soup_epoch{epoch:04d}{suffix}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["program_index"] + [f"b{i}" for i in range(program_size)]
        writer.writerow(header)

        for i in range(num_to_save):
            start = i * program_size
            end = start + program_size
            program = state.soup[start:end]

            row = [i]
            for byte in program:
                if replace_noops and byte != 0 and is_noop(byte):
                    row.append('-' if as_characters else -1)
                else:
                    row.append(BFF_SYMBOL_MAP[byte] if as_characters else byte)
            writer.writerow(row)

def save_run_metadata(path, state, params):
    metadata_path = os.path.join(path, "run_metadata.txt")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write("=== Run Parameters ===\n")
        for k, v in params.items():
            f.write(f"{k} = {v}\n")

        f.write("\n=== Runtime Metrics ===\n")
        f.write(f"Final Epoch = {state.epoch}\n")
        f.write(f"Total Ops = {state.total_ops}\n")
        f.write(f"MOPS/s = {state.mops_s:.2f}\n")
        f.write(f"Brotli Size = {state.brotli_size}\n")
        f.write(f"Bytes per Program = {state.bytes_per_prog:.2f}\n")
        f.write(f"h0 Entropy = {state.h0:.4f}\n")
        f.write(f"Brotli bpb = {state.brotli_bpb:.4f}\n")
        f.write(f"Entropy Gap = {state.higher_entropy:.4f}\n")
