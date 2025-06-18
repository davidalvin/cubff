import os
import csv
import base64


def write_epoch_table(save_path: str, max_epoch: int):
    """Create a CSV mapping epoch numbers to their .dat soup files."""
    out_path = os.path.join(save_path, "epochs.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "soup_path"])
        for epoch in range(1, max_epoch + 1):
            dat_file = f"{epoch - 1:06d}.dat"
            writer.writerow([epoch, dat_file])


def write_node_table(epoch: int, soup: bytes, exec_steps: list[int], save_path: str, tape_size: int = 64):
    """Save one row per tape (program half) in the soup, for a given epoch."""
    out_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")
    num_tapes = len(soup) // tape_size

    assert num_tapes == len(exec_steps), (
        f"Expected {num_tapes} exec steps, got {len(exec_steps)}"
    )

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "tape_idx", "tape_hex", "exec_steps"])
        for i in range(num_tapes):
            tape = soup[i * tape_size : (i + 1) * tape_size]
            tape_hex = tape.hex()  # 128-character hex string for 64 bytes
            writer.writerow([epoch, i, tape_hex, exec_steps[i]])



def append_edges(epoch: int, shuffle_idx: list[int], save_path: str):
    """
    Append parent-child tape index mappings from shuffle_idx to edges.csv.
    Note: children are stored in-place at the same indices as parents.
    """
    out_path = os.path.join(save_path, "edges.csv")
    is_first = not os.path.exists(out_path)

    with open(out_path, "a", newline="") as f:
        writer = csv.writer(f)
        if is_first:
            writer.writerow(["parent_epoch", "p1_idx", "p2_idx", "child_epoch", "c1_idx", "c2_idx"])

        for i in range(0, len(shuffle_idx), 2):
            p1, p2 = shuffle_idx[i], shuffle_idx[i + 1]
            writer.writerow([epoch - 1, p1, p2, epoch, p1, p2])
