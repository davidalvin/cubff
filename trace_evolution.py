import os
import struct
import csv
import argparse
from collections import defaultdict
from bin import cubff  # Assuming cubff is your compiled interface

TAPE_SIZE = 64

def read_soup_file(path):
    """Read raw soup data, skipping 24-byte header."""
    with open(path, "rb") as f:
        f.read(24)
        return f.read()

def trace_evolution(tape_idx, run_path, language, start_epoch=2, max_epochs=10):
    current_tape = tape_idx

    for epoch in range(start_epoch, max_epochs + 1):
        print(f"\n🔄 Epoch {epoch} — Tracing TAPE {current_tape}")

        edges_path = os.path.join(run_path, f"edges_{epoch:04d}.csv")
        soup_prev_path = os.path.join(run_path, f"{epoch - 1:010d}.dat")
        soup_curr_path = os.path.join(run_path, f"{epoch:010d}.dat")

        if not all(os.path.exists(p) for p in [edges_path, soup_prev_path, soup_curr_path]):
            print(f"[!] Missing data at epoch {epoch}. Stopping trace.")
            break

        soup_prev = read_soup_file(soup_prev_path)
        soup_curr = read_soup_file(soup_curr_path)

        with open(edges_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        found = False
        for i in range(0, len(rows), 4):
            group = rows[i:i + 4]
            sources = sorted({int(r["source"]) for r in group})
            targets = sorted({int(r["target"]) for r in group})

            if current_tape in sources:
                t1, t2 = sources
                c1, c2 = targets

                found = True
                print(f"\n🧬 Parents (Epoch {epoch - 1}) — TAPES {t1}, {t2}")
                parent_bytes = (
                    soup_prev[t1 * TAPE_SIZE : (t1 + 1) * TAPE_SIZE] +
                    soup_prev[t2 * TAPE_SIZE : (t2 + 1) * TAPE_SIZE]
                )
                language.PrintProgram(0, cubff.VectorUint8(parent_bytes), [TAPE_SIZE])

                print(f"👶 Children (Epoch {epoch}) — TAPES {c1}, {c2}")
                child_bytes = (
                    soup_curr[c1 * TAPE_SIZE : (c1 + 1) * TAPE_SIZE] +
                    soup_curr[c2 * TAPE_SIZE : (c2 + 1) * TAPE_SIZE]
                )
                language.PrintProgram(0, cubff.VectorUint8(child_bytes), [TAPE_SIZE])

                # 🧭 Choose which child to follow: keep same index if possible
                current_tape = c1 if current_tape == t1 else c2
                break

        if not found:
            print(f"[!] TAPE {current_tape} not found in any edge group at epoch {epoch}")
            break


def main():
    parser = argparse.ArgumentParser(description="Trace the evolution of a TAPE over epochs.")
    parser.add_argument("--tape", type=int, required=True, help="Index of the tape to trace.")
    parser.add_argument("--run-dir", type=str, required=True, help="Path to simulation output folder.")
    parser.add_argument("--start-epoch", type=int, default=2, help="Epoch to begin tracing from.")
    parser.add_argument("--max-epoch", type=int, default=10, help="Epoch to stop tracing at.")
    parser.add_argument("--lang", type=str, default="bff_noheads", help="Language name to use for decoding.")
    args = parser.parse_args()

    language = cubff.GetLanguage(args.lang)
    cubff.ResetColors()

    trace_evolution(
        tape_idx=args.tape,
        run_path=args.run_dir,
        language=language,
        start_epoch=args.start_epoch,
        max_epochs=args.max_epoch
    )

if __name__ == "__main__":
    main()
