import os
import csv
import argparse
from bin import cubff  # Compiled C++ simulation bindings

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
        soup_prev_path = os.path.join(run_path, f"{epoch - 2:010d}.dat")  # Parents
        soup_curr_path = os.path.join(run_path, f"{epoch - 1:010d}.dat")  # Children

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

            if len(group) < 4:
                continue  # Malformed

            # Preserve ordering from callback (not sorted!)
            p1 = int(group[0]["source"])
            p2 = int(group[1]["source"])
            c1 = int(group[0]["target"])
            c2 = int(group[2]["target"])

            if current_tape not in (c1, c2):
                continue

            print(f"\n🧬 Parents (Epoch {epoch - 1}) — TAPES {p1}, {p2}")
            parent_bytes = (
                soup_prev[p1 * TAPE_SIZE : (p1 + 1) * TAPE_SIZE] +
                soup_prev[p2 * TAPE_SIZE : (p2 + 1) * TAPE_SIZE]
            )
            language.PrintProgram(0, cubff.VectorUint8(parent_bytes), [TAPE_SIZE])

            print(f"👶 Children (Epoch {epoch}) — TAPES {c1}, {c2}")
            child_bytes = (
                soup_curr[c1 * TAPE_SIZE : (c1 + 1) * TAPE_SIZE] +
                soup_curr[c2 * TAPE_SIZE : (c2 + 1) * TAPE_SIZE]
            )
            language.PrintProgram(0, cubff.VectorUint8(child_bytes), [TAPE_SIZE])

            # Follow the tape in same slot as before, if still present
            current_tape = c1 if current_tape == c1 else c2
            found = True
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
