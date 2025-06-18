import os
import csv

HEADER_SIZE = 24


def inspect_tape(epoch, tape_idx, save_path, tape_size=64):
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    # Get .dat tape
    with open(dat_path, "rb") as f:
        dat_bytes = f.read()
    expected = dat_bytes[HEADER_SIZE + tape_idx * tape_size : HEADER_SIZE + (tape_idx + 1) * tape_size]


    # Get tape_hex from CSV
    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row["tape_idx"]) == tape_idx:
                tape_hex = row["tape_hex"]
                decoded = bytes.fromhex(tape_hex)
                break
        else:
            print(f"❌ Tape {tape_idx} not found in {nodes_path}")
            return

    print(f"\n🔍 Tape @ Epoch {epoch}, Index {tape_idx}")
    print(f"📦 .dat bytes  ({len(expected)}): {expected.hex()}")
    print(f"📤 CSV decoded ({len(decoded)}): {decoded.hex()}")
    print(f"📝 Hex string: {tape_hex[:32]}...")

    if expected == decoded:
        print("✅ Match!")
    else:
        print("❌ Mismatch:")
        for i, (b1, b2) in enumerate(zip(expected, decoded)):
            if b1 != b2:
                print(f"  Offset {i}: .dat={b1:02x} vs CSV={b2:02x}")


def check_node_vs_dat_size(epoch, save_path, tape_size=64):
    """Verbose: Check total hex character count against .dat size"""
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    with open(dat_path, "rb") as f:
        dat_bytes = f.read()
    expected_bytes = len(dat_bytes) - HEADER_SIZE

    expected_tapes = expected_bytes // tape_size
    expected_chars = expected_bytes * 2  # 2 hex chars per byte

    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    actual_tapes = len(rows)
    total_chars = sum(len(row["tape_hex"]) for row in rows)

    print(f"\n🔍 QC: check_node_vs_dat_size() for epoch {epoch}")
    print(f"  .dat bytes: {expected_bytes}")
    print(f"  Expected tapes: {expected_tapes}, hex chars: {expected_chars}")
    print(f"  CSV rows: {actual_tapes}")
    print(f"  Total tape_hex chars: {total_chars}")

    if actual_tapes != expected_tapes:
        print(f"❌ MISMATCH: CSV row count ({actual_tapes}) != expected tapes ({expected_tapes})")
        return False

    if total_chars != expected_chars:
        print(f"❌ MISMATCH: total_chars ({total_chars}) != expected ({expected_chars})")
        for i, row in enumerate(rows[:5]):
            print(f"    row {i}: len={len(row['tape_hex'])} → {row['tape_hex'][:20]}...")
        return False

    print("✅ CSV tape count and hex char size matches .dat")
    return True


def check_tape_matches(epoch, save_path, tape_size=64):
    """Verbose: Compare decoded hex to actual .dat bytes tape-by-tape"""
    HEADER_SIZE = 24  # Explicit again for local clarity
    dat_path = os.path.join(save_path, f"{epoch - 1:010d}.dat")
    nodes_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")

    with open(dat_path, "rb") as f:
        dat_bytes = f.read()

    with open(nodes_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    all_ok = True

    print(f"\n🔍 QC: check_tape_matches() for epoch {epoch}")
    print(f"  Total tapes: {len(rows)}\n")

    for row in rows:
        idx = int(row["tape_idx"])
        expected = dat_bytes[HEADER_SIZE + idx * tape_size : HEADER_SIZE + (idx + 1) * tape_size]

        try:
            decoded = bytes.fromhex(row["tape_hex"])
        except Exception as e:
            print(f"❌ Tape {idx}: Hex decode error: {e}")
            return False

        print(f"🧪 Checking tape {idx}:")
        print(f"   Expected : {expected.hex()}")
        print(f"   Decoded  : {decoded.hex()}")

        if decoded != expected:
            mismatch_idx = next((i for i in range(tape_size) if decoded[i] != expected[i]), -1)
            print(f"❌ MISMATCH at index {idx} — first byte mismatch @ offset {mismatch_idx}")
            print(f"   expected: {expected[:16].hex()}...")
            print(f"   decoded : {decoded[:16].hex()}...")
            all_ok = False
        else:
            print(f"✅ Match at tape {idx}\n")

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
        return {int(row["tape_idx"]): {
            "hex": row["tape_hex"],
            "steps": int(row["exec_steps"])
        } for row in reader}

def trace_tape_interactive(start_epoch, start_idx, save_path):
    edges_path = os.path.join(save_path, "edges.csv")
    if not os.path.exists(edges_path):
        raise FileNotFoundError("edges.csv not found in save_path")

    with open(edges_path, newline="") as f:
        edges = list(csv.DictReader(f))

    current_epoch = start_epoch
    current_idx = start_idx

    print(f"\n🔍 Starting trace at epoch {current_epoch}, tape {current_idx}")

    while True:
        next_epoch = current_epoch + 1
        parent_matches = [row for row in edges if int(row["parent_epoch"]) == current_epoch and 
                          (int(row["p1_idx"]) == current_idx or int(row["p2_idx"]) == current_idx)]

        if not parent_matches:
            print(f"❌ No child found for program {current_idx} in epoch {current_epoch}")
            break

        node_info = read_node_info(current_epoch, save_path)
        next_info = read_node_info(next_epoch, save_path)

        row = parent_matches[0]  # Pick the first match

        p1, p2 = int(row["p1_idx"]), int(row["p2_idx"])
        c1, c2 = int(row["c1_idx"]), int(row["c2_idx"])

        print(f"\n📚 Epoch {current_epoch} → {next_epoch}")
        print(f"  Parents:")
        print(f"    P1 = {p1}: {node_info[p1]['hex'][:32]}..., {node_info[p1]['steps']} steps")
        print(f"    P2 = {p2}: {node_info[p2]['hex'][:32]}..., {node_info[p2]['steps']} steps")
        print(f"  Children:")
        print(f"    C1 = {c1}: {next_info[c1]['hex'][:32]}..., {next_info[c1]['steps']} steps")
        print(f"    C2 = {c2}: {next_info[c2]['hex'][:32]}..., {next_info[c2]['steps']} steps")

        choice = input("👉 Follow (1) C1 or (2) C2? [1/2, or 'q' to quit]: ").strip().lower()
        if choice == '1':
            current_idx = c1
        elif choice == '2':
            current_idx = c2
        else:
            print("✅ Trace ended by user.")
            break

        current_epoch += 1


