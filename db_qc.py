import os
import csv

HEADER_SIZE = 24


def inspect_tape(epoch, tape_idx, save_path, tape_size=64):
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    with open(dat_path, "rb") as f:
        dat_bytes = f.read()

    expected = dat_bytes[HEADER_SIZE + tape_idx * tape_size : HEADER_SIZE + (tape_idx + 1) * tape_size]

    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["tape_idx"]) == tape_idx:
                pretty = row["tape_pretty"]
                break
        else:
            print(f"❌ Tape {tape_idx} not found in {nodes_path}")
            return

    print(f"\n🔍 Tape @ Epoch {epoch}, Index {tape_idx}")
    print(f"📦 .dat bytes  ({len(expected)}): {expected.hex()}")
    print(f"🧾 Tape pretty : {pretty}")



def check_node_vs_dat_size(epoch, save_path, tape_size=64):
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    with open(dat_path, "rb") as f:
        dat_bytes = f.read()
    expected_bytes = len(dat_bytes) - HEADER_SIZE
    expected_tapes = expected_bytes // tape_size

    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    actual_tapes = len(rows)

    print(f"\n🔍 QC: check_node_vs_dat_size() for epoch {epoch}")
    print(f"  .dat bytes: {expected_bytes}")
    print(f"  Expected tapes: {expected_tapes}")
    print(f"  CSV rows: {actual_tapes}")

    if actual_tapes != expected_tapes:
        print(f"❌ MISMATCH: CSV row count ({actual_tapes}) != expected tapes ({expected_tapes})")
        return False

    print("✅ CSV tape count matches .dat")
    return True


def check_tape_matches(epoch, save_path, tape_size=64):
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    with open(dat_path, "rb") as f:
        dat_bytes = f.read()

    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"\n🔍 QC: check_tape_matches() for epoch {epoch}")
    print(f"  Total tapes: {len(rows)}\n")

    all_ok = True
    for row in rows:
        idx = int(row["tape_idx"])
        expected = dat_bytes[HEADER_SIZE + idx * tape_size : HEADER_SIZE + (idx + 1) * tape_size]

        hex_repr = row.get("tape_hex", None)
        pretty_repr = row.get("tape_pretty", None)

        decoded = None
        if hex_repr and all(c in "0123456789abcdefABCDEF" for c in hex_repr.strip()):
            try:
                decoded = bytes.fromhex(hex_repr)
            except ValueError as e:
                print(f"❌ Hex decode error at tape {idx}: {e}")

        print(f"🧪 Checking tape {idx}:")
        print(f"   .dat bytes : {expected.hex()}")
        if hex_repr:
            print(f"   tape_hex   : {hex_repr}")
        if pretty_repr:
            print(f"   tape_pretty: {pretty_repr}")

        if decoded and decoded != expected:
            mismatch_idx = next((i for i in range(tape_size) if decoded[i] != expected[i]), -1)
            print(f"❌ MISMATCH at tape {idx} — first byte mismatch @ offset {mismatch_idx}")
            all_ok = False
        elif decoded:
            print(f"✅ Match at tape {idx}\n")
        else:
            print(f"⚠️ Skipping byte comparison (hex not available)\n")

    if all_ok:
        print(f"✅ All {len(rows)} tapes in epoch {epoch} match .dat content")
    else:
        print(f"❌ At least one mismatch found in epoch {epoch}")

    return all_ok



def check_children_steps_match(epoch, save_path):
    """Verbose: Print exec steps for all child pairs and flag mismatches."""
    edges_path = os.path.join(save_path, "edges.csv")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    # Load exec steps from node table
    steps_by_idx = {}
    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            steps_by_idx[int(row["tape_idx"])] = int(row["exec_steps"])

    all_ok = True
    pair_count = 0

    print(f"\n🔍 QC: check_children_steps_match() for epoch {epoch}")

    # Load edges and inspect child steps
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["child_epoch"]) != epoch:
                continue

            c1 = int(row["c1_idx"])
            c2 = int(row["c2_idx"])
            s1 = steps_by_idx.get(c1)
            s2 = steps_by_idx.get(c2)

            pair_count += 1

            if s1 is None or s2 is None:
                print(f"❌ Missing exec steps: C1={c1}, C2={c2}")
                all_ok = False
                continue

            print(f"  ➤ Pair {pair_count}: C1={c1} ({s1} steps), C2={c2} ({s2} steps)")

            if s1 != s2:
                print(f"     ❌ Mismatch!")
                all_ok = False

    if all_ok:
        print(f"\n✅ All {pair_count} child pairs in epoch {epoch} have equal exec steps")
    else:
        print(f"\n❌ Some child pairs in epoch {epoch} had mismatched exec steps")

    return all_ok


def read_node_info(epoch, save_path):
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")
    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        first_row = next(reader)
        f.seek(0)
        reader = csv.DictReader(f)

        key = "tape_pretty" if "tape_pretty" in first_row else "tape_hex"
        return {
            int(row["tape_idx"]): {
                "repr": row.get(key, ""),
                "steps": int(row["exec_steps"])
            } for row in reader
        }


def trace_tape_interactive(start_epoch, start_idx, save_path):
    import csv
    import os

    def load_node_info(epoch):
        path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return {
                int(row["tape_idx"]): {
                    "pretty": row.get("tape_pretty", ""),
                    "steps": int(row["exec_steps"])
                } for row in reader
            }

    edges_path = os.path.join(save_path, "edges.csv")
    if not os.path.exists(edges_path):
        raise FileNotFoundError("edges.csv not found in save_path")

    with open(edges_path, newline="") as f:
        edges = list(csv.DictReader(f))

    current_epoch = start_epoch
    current_idx = start_idx

    print(f"\n🔍 Starting trace at epoch {current_epoch}, tape {current_idx}")

    while True:
        match = next(
            (row for row in edges
             if int(row["parent_epoch"]) == current_epoch and
                (int(row["p1_idx"]) == current_idx or int(row["p2_idx"]) == current_idx)),
            None
        )

        if not match:
            print(f"❌ No edge found for epoch {current_epoch} with tape {current_idx}")
            break

        # Print raw CSV row
        print("\n📄 Raw edge row:")
        print(", ".join(match.keys()))
        print(", ".join(match.values()))

        # Load pretty representations
        node_info_now = load_node_info(current_epoch)
        node_info_next = load_node_info(current_epoch + 1)

        p1 = int(match["p1_idx"])
        p2 = int(match["p2_idx"])
        c1 = int(match["c1_idx"])
        c2 = int(match["c2_idx"])

        print(f"\n🎛️ Parents (epoch {current_epoch}):")
        print(f"  P1 = {p1}: {node_info_now[p1]['pretty'][:64]}..., {node_info_now[p1]['steps']} steps")
        print(f"  P2 = {p2}: {node_info_now[p2]['pretty'][:64]}..., {node_info_now[p2]['steps']} steps")

        print(f"\n🧬 Children (epoch {current_epoch + 1}):")
        print(f"  C1 = {c1}: {node_info_next[c1]['pretty'][:64]}..., {node_info_next[c1]['steps']} steps")
        print(f"  C2 = {c2}: {node_info_next[c2]['pretty'][:64]}..., {node_info_next[c2]['steps']} steps")

        # Interactive step
        choice = input("👉 Follow (1) C1 or (2) C2? [1/2, or 'q' to quit]: ").strip().lower()
        if choice == '1':
            current_idx = c1
        elif choice == '2':
            current_idx = c2
        else:
            print("✅ Trace ended by user.")
            break

        current_epoch += 1


def validate_step_trace_interactive(start_epoch, start_idx, save_path, bin_size=25):
    import csv, os

    edges_path = os.path.join(save_path, "edges.csv")
    steps_path = os.path.join(save_path, "edges_steps.csv")
    binned_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")

    # Load all edges (raw, steps, binned)
    with open(edges_path, newline="") as f:
        edges = list(csv.DictReader(f))
    with open(steps_path, newline="") as f:
        edges_steps = list(csv.DictReader(f))
    with open(binned_path, newline="") as f:
        edges_binned = list(csv.DictReader(f))

    def read_steps(epoch):
        path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return {int(row["tape_idx"]): int(row["exec_steps"]) for row in reader}

    current_epoch = start_epoch
    current_idx = start_idx

    print(f"\n🔍 Starting trace validation at epoch {current_epoch}, tape {current_idx}\n")

    while True:
        next_epoch = current_epoch + 1

        match = next((row for row in edges
                      if int(row["parent_epoch"]) == current_epoch and
                         (int(row["p1_idx"]) == current_idx or int(row["p2_idx"]) == current_idx)),
                     None)
        if not match:
            print(f"❌ No match found in edges.csv for idx={current_idx} at epoch {current_epoch}")
            break

        # Locate same row in edges_steps and edges_binned
        row_index = edges.index(match)
        steps_row = edges_steps[row_index]
        binned_row = edges_binned[row_index]

        p1_idx = int(match["p1_idx"])
        p2_idx = int(match["p2_idx"])
        c1_idx = int(match["c1_idx"])
        c2_idx = int(match["c2_idx"])

        parent_steps = read_steps(current_epoch)
        child_steps = read_steps(next_epoch)

        # Compute expected values
        expected_p1_steps = parent_steps.get(p1_idx, -1)
        expected_p2_steps = parent_steps.get(p2_idx, -1)
        expected_c1_steps = child_steps.get(c1_idx, -1)
        expected_c2_steps = child_steps.get(c2_idx, -1)

        expected_p1_bin = expected_p1_steps // bin_size if expected_p1_steps >= 0 else -1
        expected_p2_bin = expected_p2_steps // bin_size if expected_p2_steps >= 0 else -1
        expected_c1_bin = expected_c1_steps // bin_size if expected_c1_steps >= 0 else -1
        expected_c2_bin = expected_c2_steps // bin_size if expected_c2_steps >= 0 else -1

        print(f"📚 Epoch {current_epoch} → {next_epoch}")
        print(f"  Parent idx: P1={p1_idx}, P2={p2_idx}")
        print(f"    ➤ exec_steps: {expected_p1_steps}, {expected_p2_steps}")
        print(f"  Child idx:  C1={c1_idx}, C2={c2_idx}")
        print(f"    ➤ exec_steps: {expected_c1_steps}, {expected_c2_steps}")

        # Validate edges_steps
        step_ok = (
            int(steps_row["p1_steps"]) == expected_p1_steps and
            int(steps_row["p2_steps"]) == expected_p2_steps and
            int(steps_row["c1_steps"]) == expected_c1_steps and
            int(steps_row["c2_steps"]) == expected_c2_steps
        )

        # Validate binned
        bin_ok = (
            int(binned_row["p1_bin"]) == expected_p1_bin and
            int(binned_row["p2_bin"]) == expected_p2_bin and
            int(binned_row["c1_bin"]) == expected_c1_bin and
            int(binned_row["c2_bin"]) == expected_c2_bin
        )

        if step_ok:
            print("  ✅ edges_steps.csv values match.")
        else:
            print("  ❌ MISMATCH in edges_steps.csv!")

        if bin_ok:
            print(f"  ✅ edges_steps_binned_{bin_size}.csv values match.")
        else:
            print(f"  ❌ MISMATCH in edges_steps_binned_{bin_size}.csv!")

        # Prompt for next
        choice = input("👉 Follow (1) C1 or (2) C2, or 'q' to quit: ").strip()
        if choice == "1":
            current_idx = c1_idx
        elif choice == "2":
            current_idx = c2_idx
        else:
            print("✅ Trace complete.")
            break

        current_epoch = next_epoch
        print()