import os
import csv
import base64
from collections import Counter
import matplotlib.pyplot as plt
import sqlite3
import time

# === Command Mapping from BFF Grammar ===
COMMAND_REPR = list("[]+-.,<>{}")
COMMAND_KIND_LOOKUP = {ord(c): i for i, c in enumerate(COMMAND_REPR)}

def get_op_kind(byte):
    if byte == 0:
        return "kNull"
    elif byte in COMMAND_KIND_LOOKUP:
        return "kCommand"
    else:
        return "kNoop"

def character_repr(byte):
    # Match some overrides in the C++ table
    overrides = {
        0xC0: 'A', 0xC1: 'B', 0xC2: 'C', 0xC3: 'D', 0xC4: 'E', 0xC5: 'F',
        0xC6: 'G', 0xC7: 'H', 0xC8: 'I', 0xF0: 'J', 0xF1: 'K', 0xF2: 'L',
    }
    return overrides.get(byte, chr(0x0100 + byte))  # default Unicode string

def map_char(byte):
    kind = get_op_kind(byte)
    if kind == "kCommand":
        return COMMAND_REPR[COMMAND_KIND_LOOKUP[byte]]
    elif kind == "kNull":
        return "0"
    else:
        return character_repr(byte)

# === Precomputed 256-entry byte-to-string map
CHAR_MAP = [map_char(b) for b in range(256)]

def pretty_print_tape(tape: bytes, split_at: int = 64) -> str:
    """Human-readable visual tape display."""
    return "[" + ''.join(CHAR_MAP[b] for b in tape[:split_at]) + \
           "|" + ''.join(CHAR_MAP[b] for b in tape[split_at:]) + "]"

def write_epoch_table(save_path: str, max_epoch: int):
    """Create a CSV mapping epoch numbers to their .dat soup files."""
    out_path = os.path.join(save_path, "epochs.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "soup_path"])
        for epoch in range(1, max_epoch + 1):
            dat_file = f"{epoch - 1:06d}.dat"
            writer.writerow([epoch, dat_file])


def write_node_table(
    epoch: int,
    soup: bytes,
    exec_steps: list[int],
    save_path: str,
    tape_size: int = 64,
    save_format: str = "both"  # "hex", "pretty", "both", or "none"
):
    """Save one row per tape (program half) in the soup, for a given epoch."""
    out_path = os.path.join(save_path, f"nodes_epoch_{epoch:04d}.csv")
    num_tapes = len(soup) // tape_size

    assert num_tapes == len(exec_steps), (
        f"Expected {num_tapes} exec steps, got {len(exec_steps)}"
    )

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)

        # Base columns
        fields = ["epoch", "tape_idx", "exec_steps"]

        if save_format == "hex":
            fields.insert(2, "tape_hex")
        elif save_format == "pretty":
            fields.insert(2, "tape_pretty")
        elif save_format == "both":
            fields.insert(2, "tape_pretty")
            fields.insert(2, "tape_hex")
        elif save_format == "none":
            pass
        else:
            raise ValueError(f"Unknown save_format: {save_format}")

        writer.writerow(fields)

        for i in range(num_tapes):
            tape = soup[i * tape_size : (i + 1) * tape_size]
            row = [epoch, i, exec_steps[i]]

            if save_format == "hex":
                row.append(tape.hex())
            elif save_format == "pretty":
                row.append(pretty_print_tape(tape))
            elif save_format == "both":
                row.append(pretty_print_tape(tape))
                row.append(tape.hex())
            elif save_format == "none":
                pass  # only epoch, tape_idx, exec_steps

            writer.writerow(row)



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

def write_step_edges(save_path: str):
    """
    Creates edges_steps.csv from edges.csv by replacing all tape indices
    (p1_idx, p2_idx, c1_idx, c2_idx) with their exec_steps.
    
    Uses SQLite streaming approach for minimal memory usage - never exceeds ~200MB RAM.
    """
    edges_csv = os.path.join(save_path, "edges.csv")
    out_csv   = os.path.join(save_path, "edges_steps.csv")
    db_path   = os.path.join(save_path, "_steps.sqlite")

    t0 = time.perf_counter()
    print("🪶 1/3  building on-disk step index …")

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=OFF;")
    con.execute("CREATE TABLE IF NOT EXISTS steps("
                "epoch INT, tape INT, exec INT, "
                "PRIMARY KEY(epoch,tape));")

    for node in sorted(f for f in os.listdir(save_path)
                       if f.startswith("nodes_epoch_") and f.endswith(".csv")):
        epoch = int(node[12:-4])
        with open(os.path.join(save_path, node)) as f:
            rows = [(epoch, int(r["tape_idx"]), int(r["exec_steps"]))
                    for r in csv.DictReader(f)]
        con.executemany("INSERT OR IGNORE INTO steps VALUES (?,?,?)", rows)
    con.execute("CREATE INDEX IF NOT EXISTS idx ON steps(epoch,tape);")
    con.commit()
    print(f"✅  index ready in {time.perf_counter()-t0:.1f}s")

    # ---------- pass-1: write parent-side ----------
    tmp_csv = out_csv + ".tmp"
    with open(edges_csv) as fin, open(tmp_csv, "w", newline="") as fout:
        rdr, w = csv.DictReader(fin), csv.writer(fout)
        w.writerow(["parent_epoch","p1_steps","p2_steps",
                    "child_epoch","c1_idx","c2_idx"])
        q = "SELECT exec FROM steps WHERE epoch=? AND tape=?"
        for r in rdr:
            pe = int(r["parent_epoch"])
            p1 = int(r["p1_idx"]); p2 = int(r["p2_idx"])
            s1 = con.execute(q,(pe,p1)).fetchone()
            s2 = con.execute(q,(pe,p2)).fetchone()
            w.writerow([pe, s1[0] if s1 else -1, s2[0] if s2 else -1,
                        r["child_epoch"], r["c1_idx"], r["c2_idx"]])
    print("✍️  pass-1 complete")

    # ---------- pass-2: patch child-side ----------
    with open(tmp_csv) as fin, open(out_csv, "w", newline="") as fout:
        rdr, w = csv.DictReader(fin), csv.writer(fout)
        w.writerow(["parent_epoch","p1_steps","p2_steps",
                    "child_epoch","c1_steps","c2_steps"])
        q = "SELECT exec FROM steps WHERE epoch=? AND tape=?"
        for r in rdr:
            ce   = int(r["child_epoch"])
            c1   = int(r["c1_idx"]); c2 = int(r["c2_idx"])
            s1   = con.execute(q,(ce,c1)).fetchone()
            s2   = con.execute(q,(ce,c2)).fetchone()
            w.writerow([ r["parent_epoch"], r["p1_steps"], r["p2_steps"],
                         ce, s1[0] if s1 else -1, s2[0] if s2 else -1 ])
    con.close(); os.remove(db_path); os.remove(tmp_csv)
    print(f"✅  edges_steps.csv written in {time.perf_counter()-t0:.1f}s")

def write_binned_step_edges(save_path: str, bin_size: int = 25):
    """
    Creates edges_steps_binned.csv by replacing exec_steps with bin indices.
    For example, bin_size=25 means 0–24 → bin 0, 25–49 → bin 1, etc.
    """
    in_path = os.path.join(save_path, "edges_steps.csv")
    out_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")

    with open(in_path, newline="") as f_in, open(out_path, "w", newline="") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow(["parent_epoch", "p1_bin", "p2_bin", "child_epoch", "c1_bin", "c2_bin"])

        for row in reader:
            def bin_val(val_str):
                try:
                    val = int(val_str)
                    return val // bin_size
                except:
                    return -1  # fallback bin for missing or bad data

            writer.writerow([
                int(row["parent_epoch"]),
                bin_val(row["p1_steps"]),
                bin_val(row["p2_steps"]),
                int(row["child_epoch"]),
                bin_val(row["c1_steps"]),
                bin_val(row["c2_steps"]),
            ])

def plot_epoch_lineage_graph(save_path: str, max_epoch: int, bin_size: int = 25):
    """Plots execution steps (binned) across epochs with lineage lines between programs."""
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    import os
    import csv
    import time

    print("📈 Starting epoch lineage plot generation...")
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")

    if not os.path.exists(edges_path):
        print(f"❌ Missing required file: {edges_path}")
        return

    print("🔍 Reading binned step transitions from edges...")
    t0 = time.perf_counter()

    bins_seen = set()
    lines = []
    edge_count = 0
    skipped = 0

    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                pbins = [int(row["p1_bin"]), int(row["p2_bin"])]
                cbins = [int(row["c1_bin"]), int(row["c2_bin"])]

                for pb in pbins:
                    for cb in cbins:
                        if pb >= 0 and cb >= 0:
                            lines.append([(pe, pb), (ce, cb)])
                            bins_seen.update([pb, cb])
                            edge_count += 1
                        else:
                            skipped += 1
            except Exception as e:
                print(f"⚠️  Skipping row due to error: {e}")
                skipped += 1

    print(f"✅ Loaded {edge_count} edges (skipped {skipped}) in {time.perf_counter() - t0:.2f}s")

    print("🎨 Generating plot...")
    t1 = time.perf_counter()
    fig, ax = plt.subplots(figsize=(14, 8))
    ax.set_xlabel("Epoch")
    ax.set_ylabel(f"Step Bin ({bin_size} per bin)")
    ax.set_title("Lineage of Programs by Execution Step Bins")

    # Scatter endpoints for context
    all_points = [pt for line in lines for pt in line]
    ax.scatter(
        [pt[0] for pt in all_points],
        [pt[1] for pt in all_points],
        s=1,
        color="black",
        alpha=0.1
    )

    lc = LineCollection(lines, colors="blue", linewidths=0.25, alpha=0.2)
    ax.add_collection(lc)

    ax.set_ylim(0, max(bins_seen) + 1)
    ax.set_xlim(0, max_epoch + 1)

    print(f"✅ Rendered in {time.perf_counter() - t1:.2f}s")

    out_path = os.path.join(save_path, "epoch_lineage_plot.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"📁 Lineage plot saved to: {out_path}")

def write_gephi_weighted_edges_from_binned_steps(save_path: str, bin_size: int):
    """
    Create a directed, weighted edge list from binned execution transitions.
    Optimized using DuckDB for better performance with large datasets.

    Each parent bin (p1, p2) points to both child bins (c1, c2).
    Duplicate edges are aggregated with a weight.

    Output: edges_gephi_binned_<bin_size>.csv
    Format: Source, Target, Weight
    """
    in_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    out_path = os.path.join(save_path, f"edges_gephi_binned_{bin_size}.csv")

    print(f"🔗 Creating Gephi weighted edges from binned steps (bin_size={bin_size})...")
    
    try:
        import duckdb
        import time
        t0 = time.perf_counter()
        
        con = duckdb.connect()
        con.execute("SET threads TO 2;")
        con.execute("SET memory_limit TO '1GB';")
        
        # Load binned edges into DuckDB
        con.execute(f"""
            CREATE TABLE binned_edges AS
            SELECT * FROM read_csv_auto('{in_path}', HEADER=TRUE, AUTO_DETECT=TRUE);
        """)
        
        # Use SQL to efficiently aggregate edge weights
        result = con.execute("""
            WITH edge_pairs AS (
                SELECT p1_bin as src, c1_bin as tgt FROM binned_edges WHERE p1_bin != -1 AND c1_bin != -1
                UNION ALL
                SELECT p1_bin as src, c2_bin as tgt FROM binned_edges WHERE p1_bin != -1 AND c2_bin != -1
                UNION ALL
                SELECT p2_bin as src, c1_bin as tgt FROM binned_edges WHERE p2_bin != -1 AND c1_bin != -1
                UNION ALL
                SELECT p2_bin as src, c2_bin as tgt FROM binned_edges WHERE p2_bin != -1 AND c2_bin != -1
            )
            SELECT src as Source, tgt as Target, COUNT(*) as Weight
            FROM edge_pairs
            GROUP BY src, tgt
            ORDER BY src, tgt
        """).fetchdf()
        
        print(f"✅ Aggregated {len(result):,} unique edges")
        
        # Write to CSV
        result.to_csv(out_path, index=False)
        print(f"📁 Saved to: {out_path}")
        print(f"⏱️ Total time: {time.perf_counter() - t0:.2f}s")
        
        con.close()
        
    except ImportError:
        print("⚠️ DuckDB not available, falling back to Python Counter...")
        write_gephi_weighted_edges_python(save_path, bin_size)
    except Exception as e:
        print(f"❌ DuckDB failed: {e}")
        print("🔄 Falling back to Python Counter...")
        write_gephi_weighted_edges_python(save_path, bin_size)

def write_gephi_weighted_edges_python(save_path: str, bin_size: int):
    """Fallback Python implementation using Counter."""
    in_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    out_path = os.path.join(save_path, f"edges_gephi_binned_{bin_size}.csv")

    edge_counter = Counter()

    with open(in_path, newline="") as fin:
        reader = csv.DictReader(fin)
        for row in reader:
            p1 = row["p1_bin"]
            p2 = row["p2_bin"]
            c1 = row["c1_bin"]
            c2 = row["c2_bin"]

            # Only count valid transitions (non -1)
            for src in (p1, p2):
                for tgt in (c1, c2):
                    if src != "-1" and tgt != "-1":
                        edge_counter[(int(src), int(tgt))] += 1

    with open(out_path, "w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["Source", "Target", "Weight"])
        for (src, tgt), weight in sorted(edge_counter.items()):
            writer.writerow([src, tgt, weight])

def write_gephi_nodes_from_bins(save_path: str, bin_size: int):
    """
    Create Gephi-compatible node file using bin indices as IDs.
    Optimized to extract unique bins efficiently using DuckDB.
    Each node is labeled with its step range, e.g., '0–24 steps'.
    """
    edge_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    out_path = os.path.join(save_path, f"gephi_nodes_binned_{bin_size}.csv")

    print(f"🔗 Creating Gephi nodes from binned steps (bin_size={bin_size})...")
    
    try:
        import duckdb
        import time
        t0 = time.perf_counter()
        
        con = duckdb.connect()
        con.execute("SET threads TO 2;")
        con.execute("SET memory_limit TO '1GB';")
        
        # Extract unique bins efficiently using SQL
        result = con.execute(f"""
            WITH all_bins AS (
                SELECT p1_bin as bin FROM read_csv_auto('{edge_path}', HEADER=TRUE, AUTO_DETECT=TRUE) WHERE p1_bin >= 0
                UNION
                SELECT p2_bin as bin FROM read_csv_auto('{edge_path}', HEADER=TRUE, AUTO_DETECT=TRUE) WHERE p2_bin >= 0
                UNION
                SELECT c1_bin as bin FROM read_csv_auto('{edge_path}', HEADER=TRUE, AUTO_DETECT=TRUE) WHERE c1_bin >= 0
                UNION
                SELECT c2_bin as bin FROM read_csv_auto('{edge_path}', HEADER=TRUE, AUTO_DETECT=TRUE) WHERE c2_bin >= 0
            )
            SELECT DISTINCT bin as id
            FROM all_bins
            ORDER BY bin
        """).fetchdf()
        
        print(f"✅ Found {len(result):,} unique bins")
        
        # Create labels and write to CSV
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "label"])
            for _, row in result.iterrows():
                bin_id = row['id']
                label = f"{bin_id * bin_size}–{(bin_id + 1) * bin_size - 1} steps"
                writer.writerow([bin_id, label])
        
        print(f"📁 Saved to: {out_path}")
        print(f"⏱️ Total time: {time.perf_counter() - t0:.2f}s")
        
        con.close()
        
    except ImportError:
        print("⚠️ DuckDB not available, falling back to Python set...")
        write_gephi_nodes_python(save_path, bin_size)
    except Exception as e:
        print(f"❌ DuckDB failed: {e}")
        print("🔄 Falling back to Python set...")
        write_gephi_nodes_python(save_path, bin_size)

def write_gephi_nodes_python(save_path: str, bin_size: int):
    """Fallback Python implementation using set."""
    edge_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    out_path = os.path.join(save_path, f"gephi_nodes_binned_{bin_size}.csv")

    bins = set()

    with open(edge_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for col in ["p1_bin", "p2_bin", "c1_bin", "c2_bin"]:
                val = int(row[col])
                if val >= 0:  # skip -1 invalid bins
                    bins.add(val)

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label"])
        for b in sorted(bins):
            label = f"{b * bin_size}–{(b + 1) * bin_size - 1} steps"
            writer.writerow([b, label])