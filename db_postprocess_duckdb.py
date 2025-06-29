"""
DuckDB‑based post‑processing pipeline for cubff evolutionary runs.
Replaces the original pandas implementation with a streaming SQL
workflow that runs comfortably in ≤4 GB RAM even for 4 096 epochs.

Usage (stand‑alone):
    python db_postprocess_duckdb.py \
        --local-tmp ./tmp_postprocess \
        --s3-prefix soup/db_run_test/ \
        --bin-size 25 \
        --max-epochs 4096 \
        --skip-upload

The CLI mimics the old script so existing Jenkins / bash wrappers
need minimal changes.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# DuckDB is required - no fallback
try:
    import duckdb  # pip install duckdb>=0.10
except ImportError as e:
    print(f"❌ DuckDB not available: {e}")
    print("DuckDB is required for this script. Please install with: pip install duckdb>=0.10")
    sys.exit(1)

# Setup logging
logger = logging.getLogger("postprocess_duckdb")

# ──────────────────────────────────────────────────────────────────────────────
# Configuration defaults (override via CLI)
# ──────────────────────────────────────────────────────────────────────────────
BIN_SIZE_DEFAULT: int = 25
MAX_EPOCHS_DEFAULT: int = 4096
LOCAL_TMP_DEFAULT: str = "./tmp_postprocess"
S3_BUCKET_DEFAULT: str = "bff-grammar"
S3_PREFIX_DEFAULT: str = "soup/db_run_test/"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mk_duckdb_conn() -> duckdb.DuckDBPyConnection:  # pragma: no cover
    """Return a fresh in‑process DuckDB connection with HTTPFS enabled."""
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    # Conservative settings to prevent memory allocation failures
    conn.execute("PRAGMA threads=2;")  # Reduce threads to flatten memory spikes
    conn.execute("PRAGMA preserve_insertion_order=false;")  # huge memory saver
    conn.execute("PRAGMA memory_limit='3GB';")              # Force early spilling, prevent large allocations
    conn.execute("PRAGMA enable_progress_bar=true;")        # live progress visibility
    return conn


def _glob_paths(tmp_dir: Path) -> tuple[str, str]:
    """Return wildcard strings for nodes and edges CSVs inside *tmp_dir*."""
    nodes_glob = str(tmp_dir / "nodes_epoch_*.csv")
    edges_glob = str(tmp_dir / "edges_epoch_*.csv")
    return nodes_glob, edges_glob


def csv_to_parquet_dir(csv_glob: str, output_dir: Path) -> None:
    """Convert CSV files to Parquet format for more efficient processing."""
    import glob
    
    csv_files = glob.glob(csv_glob)
    if not csv_files:
        logger.warning(f"No CSV files found matching pattern: {csv_glob}")
        return
    
    logger.info(f"🔄 Converting {len(csv_files)} CSV files to Parquet...")
    
    conn = _mk_duckdb_conn()
    
    for i, csv_file in enumerate(csv_files, 1):
        csv_path = Path(csv_file)
        parquet_path = output_dir / f"{csv_path.stem}.parquet"
        
        if parquet_path.exists():
            logger.info(f"   ⏭️  [{i}/{len(csv_files)}] Skipping {csv_path.name} (Parquet already exists)")
            continue
            
        logger.info(f"   🔄 [{i}/{len(csv_files)}] Converting {csv_path.name} → {parquet_path.name}")
        try:
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_csv_auto('{csv_path}', HEADER=TRUE)
                ) TO '{parquet_path}' (FORMAT PARQUET);
            """)
            logger.info(f"      ✅ Converted ({parquet_path.stat().st_size:,} bytes)")
        except Exception as e:
            logger.error(f"      ❌ Failed to convert {csv_path.name}: {e}")
    
    conn.close()
    logger.info("✅ CSV to Parquet conversion complete")


# ──────────────────────────────────────────────────────────────────────────────
# Core transforms
# ──────────────────────────────────────────────────────────────────────────────

def build_edges_steps_duckdb(tmp_dir: Path, bin_size: int) -> None:
    """DuckDB postprocessing using Parquet inputs and 1-file batches (low memory mode)."""
    nodes_glob = str(tmp_dir / "nodes_epoch_*.parquet")
    edges_glob = str(tmp_dir / "edges_epoch_*.parquet")
    edges_steps_csv = tmp_dir / "edges_steps.csv"
    binned_csv = tmp_dir / f"edges_steps_binned_{bin_size}.csv"

    logger.info("🦆 Building edges_steps via DuckDB (parquet + 1-file batches)...")
    logger.info(f"   📁 Nodes glob: {nodes_glob}")
    logger.info(f"   📁 Edges glob: {edges_glob}")

    conn = _mk_duckdb_conn()

    logger.info("📊 Step 1: Indexing all_nodes table")
    start_time = time.time()
    conn.execute(f"""
        CREATE TABLE all_nodes AS
        SELECT *, epoch FROM read_parquet('{nodes_glob}');
    """)
    conn.execute("CREATE INDEX idx_all_nodes_epoch_tape ON all_nodes(epoch, tape_idx);")
    elapsed = time.time() - start_time
    logger.info(f"   ✅ all_nodes loaded in {elapsed:.1f}s")

    edge_files = sorted(tmp_dir.glob("edges_epoch_*.parquet"), key=lambda f: int(f.stem.split("_")[-1]))
    if not edge_files:
        logger.error("❌ No edge files found")
        conn.close()
        return

    batch_output_dir = tmp_dir / "edges_steps_batches"
    batch_output_dir.mkdir(exist_ok=True)

    logger.info(f"🔄 Step 2: Processing {len(edge_files)} batches (batch size = 1)")

    total_edges = 0
    start_time = time.time()
    for i, edge_file in enumerate(edge_files, 1):
        logger.info(f"   📦 Batch {i}/{len(edge_files)}: {edge_file.name}")
        try:
            conn.execute("DROP TABLE IF EXISTS batch_edges;")
            conn.execute("DROP TABLE IF EXISTS batch_joined;")

            conn.execute(f"""
                CREATE TEMP TABLE batch_edges AS
                SELECT * FROM read_parquet('{edge_file}');
            """)

            conn.execute("""
                CREATE TEMP TABLE batch_joined AS
                SELECT e.*,
                       p1.exec_steps AS p1_steps,
                       p2.exec_steps AS p2_steps,
                       c1.exec_steps AS c1_steps,
                       c2.exec_steps AS c2_steps
                FROM batch_edges e
                LEFT JOIN all_nodes p1 ON e.parent_epoch = p1.epoch AND e.p1_idx = p1.tape_idx
                LEFT JOIN all_nodes p2 ON e.parent_epoch = p2.epoch AND e.p2_idx = p2.tape_idx
                LEFT JOIN all_nodes c1 ON e.child_epoch = c1.epoch AND e.c1_idx = c1.tape_idx
                LEFT JOIN all_nodes c2 ON e.child_epoch = c2.epoch AND e.c2_idx = c2.tape_idx;
            """)

            out_path = batch_output_dir / f"edges_steps_batch_{i:03d}.csv"
            conn.execute(f"COPY batch_joined TO '{out_path}' (HEADER, DELIMITER ',');")

            count = conn.execute("SELECT COUNT(*) FROM batch_joined").fetchone()[0]
            total_edges += count
            logger.info(f"      ✅ {count:,} edges → {out_path.name}")

        except Exception as e:
            logger.error(f"      ❌ Batch {i} failed: {e}")

    elapsed = time.time() - start_time
    logger.info(f"   ✅ All batches complete: {total_edges:,} edges in {elapsed:.1f}s")

    if not list(batch_output_dir.glob("edges_steps_batch_*.csv")):
        logger.error("❌ No batch output files were created. Aborting.")
        conn.close()
        return

    logger.info("📆 Step 3: Merging batch outputs")
    batch_glob = str(batch_output_dir / "edges_steps_batch_*.csv")
    conn.execute(f"""
        COPY (
            SELECT * FROM read_csv_auto('{batch_glob}', HEADER=TRUE)
        ) TO '{edges_steps_csv}' (HEADER, DELIMITER ',');
    """)
    logger.info(f"   ✅ Merged edges_steps.csv → {edges_steps_csv.stat().st_size:,} bytes")

    logger.info("📊 Step 4: Binning steps")
    conn.execute(f"""
        CREATE TABLE edges_steps_binned AS
        SELECT parent_epoch,
               CAST(p1_steps/{bin_size} AS INT) AS p1_bin,
               CAST(p2_steps/{bin_size} AS INT) AS p2_bin,
               child_epoch,
               CAST(c1_steps/{bin_size} AS INT) AS c1_bin,
               CAST(c2_steps/{bin_size} AS INT) AS c2_bin
        FROM read_csv_auto('{edges_steps_csv}', HEADER=TRUE);
    """)
    conn.execute(f"""
        COPY edges_steps_binned TO '{binned_csv}' (HEADER, DELIMITER ',');
    """)
    logger.info(f"   ✅ Binned → {binned_csv.stat().st_size:,} bytes")

    logger.info("🧹 Cleaning up intermediate batch files")
    import shutil
    shutil.rmtree(batch_output_dir, ignore_errors=True)

    conn.close()
    logger.info("✅ Done (parquet, batch=1, ultra low-memory)")


def export_gephi_csvs(tmp_dir: Path, bin_size: int) -> None:
    """Aggregate weighted edges and node labels for Gephi."""
    binned_csv = tmp_dir / f"edges_steps_binned_{bin_size}.csv"
    gephi_edges = tmp_dir / f"gephi_edges_weighted_{bin_size}.csv"
    gephi_nodes = tmp_dir / f"gephi_nodes_{bin_size}.csv"

    logger.info("🎛️  Aggregating Gephi edge weights …")
    logger.info(f"   📁 Input: {binned_csv}")
    
    conn = _mk_duckdb_conn()
    
    # Step 1: Materialize binned data once (one CSV parse)
    logger.info("📊 Step 1: Materializing binned data (one CSV parse)...")
    start_time = time.time()
    conn.execute(f"CREATE TABLE b AS SELECT * FROM read_csv_auto('{binned_csv}', HEADER=TRUE);")
    elapsed = time.time() - start_time
    logger.info(f"   ✅ Binned data materialized in {elapsed:.1f}s (one CSV parse)")
    
    try:
        binned_count = conn.execute("SELECT COUNT(*) FROM b").fetchone()[0]
        logger.info(f"   📈 Loaded {binned_count:,} binned edges")
        
        # Show data range
        data_range = conn.execute("""
            SELECT 
                MIN(parent_epoch) as min_epoch, 
                MAX(parent_epoch) as max_epoch,
                MIN(p1_bin) as min_bin,
                MAX(p1_bin) as max_bin
            FROM b
        """).fetchone()
        logger.info(f"   📅 Epoch range: {data_range[0]} to {data_range[1]}")
        logger.info(f"   📦 Bin range: {data_range[2]} to {data_range[3]}")
        
    except Exception as e:
        logger.warning(f"   ⚠️  Could not analyze binned data: {e}")

    # Step 2: Create weighted edges (using materialized table)
    logger.info("🔗 Step 2: Creating weighted edges...")
    logger.info("   ⏳ Aggregating edge weights (using materialized table)...")
    
    start_time = time.time()
    conn.execute("""
        CREATE TABLE gephi_edges AS
        SELECT p1_bin AS source, c1_bin AS target, COUNT(*) AS weight
        FROM   b WHERE p1_bin >= 0 AND c1_bin >= 0
        GROUP  BY 1,2
        UNION ALL
        SELECT p2_bin, c2_bin, COUNT(*)
        FROM   b WHERE p2_bin >= 0 AND c2_bin >= 0
        GROUP  BY 1,2;
    """)
    
    elapsed = time.time() - start_time
    logger.info(f"   ✅ Weighted edges created in {elapsed:.1f}s")
    
    # Analyze weighted edges
    try:
        edge_stats = conn.execute("""
            SELECT 
                COUNT(*) as total_edges,
                SUM(weight) as total_weight,
                AVG(weight) as avg_weight,
                MAX(weight) as max_weight
            FROM gephi_edges
        """).fetchone()
        logger.info(f"   📊 Edge stats: {edge_stats[0]:,} edges, {edge_stats[1]:,} total weight")
        logger.info(f"   📊 Average weight: {edge_stats[2]:.1f}, Max weight: {edge_stats[3]}")
        
    except Exception as e:
        logger.warning(f"   ⚠️  Could not analyze edge stats: {e}")

    # Step 3: Export weighted edges
    logger.info(f"💾 Step 3: Exporting weighted edges to {gephi_edges}...")
    start_time = time.time()
    conn.execute(
        f"COPY gephi_edges TO '{gephi_edges}' (HEADER, DELIMITER ',');"
    )
    elapsed = time.time() - start_time
    file_size = gephi_edges.stat().st_size if gephi_edges.exists() else 0
    logger.info(f"   ✅ Weighted edges exported ({file_size:,} bytes) in {elapsed:.1f}s")

    # Step 4: Create node labels (using materialized table)
    logger.info("🔖 Step 4: Generating Gephi node labels …")
    logger.info("   ⏳ Extracting unique bins and creating labels...")
    
    start_time = time.time()
    conn.execute(f"""
        CREATE TABLE gephi_nodes AS
        WITH bins AS (
            SELECT p1_bin AS bin FROM b UNION
            SELECT p2_bin FROM b UNION
            SELECT c1_bin FROM b UNION
            SELECT c2_bin FROM b
        )
        SELECT DISTINCT bin AS id,
               printf('%d–%d steps', CAST(bin AS INTEGER)*{bin_size}, CAST(bin AS INTEGER)*{bin_size}+{bin_size}-1) AS label
        FROM bins WHERE bin >= 0;
    """)
    
    elapsed = time.time() - start_time
    logger.info(f"   ✅ Node labels created in {elapsed:.1f}s")
    
    # Analyze nodes
    try:
        node_count = conn.execute("SELECT COUNT(*) FROM gephi_nodes").fetchone()[0]
        logger.info(f"   📊 Created {node_count:,} unique node labels")
        
    except Exception as e:
        logger.warning(f"   ⚠️  Could not count nodes: {e}")

    # Step 5: Export node labels
    logger.info(f"💾 Step 5: Exporting node labels to {gephi_nodes}...")
    start_time = time.time()
    conn.execute(
        f"COPY gephi_nodes TO '{gephi_nodes}' (HEADER, DELIMITER ',');"
    )
    elapsed = time.time() - start_time
    file_size = gephi_nodes.stat().st_size if gephi_nodes.exists() else 0
    logger.info(f"   ✅ Node labels exported ({file_size:,} bytes) in {elapsed:.1f}s")
    
    conn.close()
    logger.info("✅ Gephi CSVs ready.")


# ──────────────────────────────────────────────────────────────────────────────
# Plotting (chunked fetch → low RAM) - COMMENTED OUT
# ──────────────────────────────────────────────────────────────────────────────

# def stream_lineage_plot(tmp_dir: Path, max_epoch: int, bin_size: int) -> None:
#     """Render the lineage plot without loading the full CSV into memory."""
#     import matplotlib.pyplot as plt
#     from matplotlib.collections import LineCollection
# 
#     binned_csv = tmp_dir / f"edges_steps_binned_{bin_size}.csv"
#     out_png = tmp_dir / f"epoch_lineage_{bin_size}.png"
# 
#     logger.info("📈 Streaming lineage plot …")
#     logger.info(f"   📁 Input: {binned_csv}")
#     logger.info(f"   🎯 Output: {out_png}")
#     logger.info(f"   📊 Max epoch: {max_epoch}, Bin size: {bin_size}")
#     
#     conn = _mk_duckdb_conn()
# 
#     # Step 1: Analyze data for plotting
#     logger.info("📊 Step 1: Analyzing data for plotting...")
#     try:
#         total_rows = conn.execute(f"SELECT COUNT(*) FROM read_csv_auto('{binned_csv}', HEADER=TRUE)").fetchone()[0]
#         logger.info(f"   📈 Total rows to process: {total_rows:,}")
#         
#         # Get data range
#         data_range = conn.execute(f"""
#             SELECT 
#                 MIN(parent_epoch) as min_epoch, 
#                 MAX(parent_epoch) as max_epoch,
#                 MIN(p1_bin) as min_bin,
#                 MAX(p1_bin) as max_bin
#             FROM read_csv_auto('{binned_csv}', HEADER=TRUE)
#         """).fetchone()
#         logger.info(f"   📅 Data epoch range: {data_range[0]} to {data_range[1]}")
#         logger.info(f"   📦 Data bin range: {data_range[2]} to {data_range[3]}")
#         
#     except Exception as e:
#         logger.warning(f"   ⚠️  Could not analyze data: {e}")
# 
#     # Step 2: Create plot
#     logger.info("🎨 Step 2: Creating matplotlib figure...")
#     fig, ax = plt.subplots(figsize=(14, 8))
#     ax.set_xlabel("Epoch")
#     ax.set_ylabel(f"Step Bin ({bin_size} per bin)")
#     ax.set_title("Program lineage by execution‑step bins")
# 
#     # Step 3: Stream data in batches
#     logger.info("🔄 Step 3: Streaming data in batches...")
#     batch_size = 1_000_000
#     off = 0
#     total_lines = 0
#     batch_count = 0
#     
#     start_time = time.time()
#     
#     while True:
#         batch_count += 1
#         logger.info(f"   📦 Processing batch {batch_count} (offset {off:,})...")
#         
#         query = (
#             f"SELECT parent_epoch, p1_bin, p2_bin, child_epoch, c1_bin, c2_bin "
#             f"FROM read_csv_auto('{binned_csv}', HEADER=TRUE) "
#             f"LIMIT {batch_size} OFFSET {off};"
#         )
#         df = conn.execute(query).fetch_df()
#         
#         if df.empty:
#             logger.info(f"   ✅ No more data to process")
#             break
#             
#         batch_lines = 0
#         lines = []
#         for (_, r) in df.iterrows():
#             pe, ce = int(r.parent_epoch), int(r.child_epoch)
#             lines.extend(
#                 [
#                     [(pe, int(r.p1_bin)), (ce, int(r.c1_bin))],
#                     [(pe, int(r.p2_bin)), (ce, int(r.c2_bin))],
#                 ]
#             )
#             batch_lines += 2
#         
#         ax.add_collection(LineCollection(lines, linewidths=0.25, alpha=0.2))
#         total_lines += batch_lines
#         off += batch_size
#         
#         logger.info(f"   📊 Batch {batch_count}: {len(df):,} rows → {batch_lines:,} lines")
#         logger.info(f"   📈 Total progress: {total_lines:,} lines drawn")
#     
#     elapsed = time.time() - start_time
#     logger.info(f"   ✅ Data streaming complete in {elapsed:.1f}s")
#     logger.info(f"   📊 Final stats: {batch_count} batches, {total_lines:,} total lines")
# 
#     # Step 4: Finalize plot
#     logger.info("🎯 Step 4: Finalizing plot...")
#     ax.set_xlim(0, max_epoch)
#     ax.set_ylim(bottom=0)
#     fig.tight_layout()
#     
#     # Step 5: Save plot
#     logger.info(f"💾 Step 5: Saving plot to {out_png}...")
#     start_time = time.time()
#     fig.savefig(out_png, dpi=200)
#     elapsed = time.time() - start_time
#     
#     file_size = out_png.stat().st_size if out_png.exists() else 0
#     logger.info(f"   ✅ Plot saved ({file_size:,} bytes) in {elapsed:.1f}s")
#     
#     plt.close(fig)
#     conn.close()
#     logger.info("✅ Lineage plot saved → %s", out_png)


# ──────────────────────────────────────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────────────────────────────────────

def run_postprocessing_duckdb(args: argparse.Namespace) -> None:  # pragma: no cover
    """Run the complete DuckDB post-processing pipeline."""
    
    # Convert CSVs to Parquet if requested
    if args.convert_to_parquet:
        logger.info("🔄 Converting CSV files to Parquet format...")
        csv_to_parquet_dir(str(args.local_tmp / "nodes_epoch_*.csv"), args.local_tmp)
        csv_to_parquet_dir(str(args.local_tmp / "edges_epoch_*.csv"), args.local_tmp)
        logger.info("✅ CSV to Parquet conversion complete")
        return
    
    # Check if we should use CSV mode (fallback)
    if args.use_csv:
        logger.info("📄 Using CSV mode (fallback)")
        # Modify the function to use CSV files
        import types
        original_func = build_edges_steps_duckdb
        
        def csv_build_edges_steps_duckdb(tmp_dir: Path, bin_size: int) -> None:
            """CSV fallback version of build_edges_steps_duckdb."""
            nodes_glob = str(tmp_dir / "nodes_epoch_*.csv")
            edges_glob = str(tmp_dir / "edges_epoch_*.csv")
            edges_steps_csv = tmp_dir / "edges_steps.csv"
            binned_csv = tmp_dir / f"edges_steps_binned_{bin_size}.csv"

            logger.info("🦆 Building edges_steps via DuckDB (CSV + 1-file batches)...")
            logger.info(f"   📁 Nodes glob: {nodes_glob}")
            logger.info(f"   📁 Edges glob: {edges_glob}")

            conn = _mk_duckdb_conn()

            logger.info("📊 Step 1: Indexing all_nodes table")
            start_time = time.time()
            conn.execute(f"""
                CREATE TABLE all_nodes AS
                SELECT *, epoch FROM read_csv_auto('{nodes_glob}', HEADER=TRUE);
            """)
            conn.execute("CREATE INDEX idx_all_nodes_epoch_tape ON all_nodes(epoch, tape_idx);")
            elapsed = time.time() - start_time
            logger.info(f"   ✅ all_nodes loaded in {elapsed:.1f}s")

            edge_files = sorted(tmp_dir.glob("edges_epoch_*.csv"), key=lambda f: int(f.stem.split("_")[-1]))
            if not edge_files:
                logger.error("❌ No edge files found")
                conn.close()
                return

            batch_output_dir = tmp_dir / "edges_steps_batches"
            batch_output_dir.mkdir(exist_ok=True)

            logger.info(f"🔄 Step 2: Processing {len(edge_files)} batches (batch size = 1)")

            total_edges = 0
            start_time = time.time()
            for i, edge_file in enumerate(edge_files, 1):
                logger.info(f"   📦 Batch {i}/{len(edge_files)}: {edge_file.name}")
                try:
                    conn.execute("DROP TABLE IF EXISTS batch_edges;")
                    conn.execute("DROP TABLE IF EXISTS batch_joined;")

                    conn.execute(f"""
                        CREATE TEMP TABLE batch_edges AS
                        SELECT * FROM read_csv_auto('{edge_file}', HEADER=TRUE);
                    """)

                    conn.execute("""
                        CREATE TEMP TABLE batch_joined AS
                        SELECT e.*,
                               p1.exec_steps AS p1_steps,
                               p2.exec_steps AS p2_steps,
                               c1.exec_steps AS c1_steps,
                               c2.exec_steps AS c2_steps
                        FROM batch_edges e
                        LEFT JOIN all_nodes p1 ON e.parent_epoch = p1.epoch AND e.p1_idx = p1.tape_idx
                        LEFT JOIN all_nodes p2 ON e.parent_epoch = p2.epoch AND e.p2_idx = p2.tape_idx
                        LEFT JOIN all_nodes c1 ON e.child_epoch = c1.epoch AND e.c1_idx = c1.tape_idx
                        LEFT JOIN all_nodes c2 ON e.child_epoch = c2.epoch AND e.c2_idx = c2.tape_idx;
                    """)

                    out_path = batch_output_dir / f"edges_steps_batch_{i:03d}.csv"
                    conn.execute(f"COPY batch_joined TO '{out_path}' (HEADER, DELIMITER ',');")

                    count = conn.execute("SELECT COUNT(*) FROM batch_joined").fetchone()[0]
                    total_edges += count
                    logger.info(f"      ✅ {count:,} edges → {out_path.name}")

                except Exception as e:
                    logger.error(f"      ❌ Batch {i} failed: {e}")

            elapsed = time.time() - start_time
            logger.info(f"   ✅ All batches complete: {total_edges:,} edges in {elapsed:.1f}s")

            if not list(batch_output_dir.glob("edges_steps_batch_*.csv")):
                logger.error("❌ No batch output files were created. Aborting.")
                conn.close()
                return

            logger.info("📆 Step 3: Merging batch outputs")
            batch_glob = str(batch_output_dir / "edges_steps_batch_*.csv")
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_csv_auto('{batch_glob}', HEADER=TRUE)
                ) TO '{edges_steps_csv}' (HEADER, DELIMITER ',');
            """)
            logger.info(f"   ✅ Merged edges_steps.csv → {edges_steps_csv.stat().st_size:,} bytes")

            logger.info("📊 Step 4: Binning steps")
            conn.execute(f"""
                CREATE TABLE edges_steps_binned AS
                SELECT parent_epoch,
                       CAST(p1_steps/{bin_size} AS INT) AS p1_bin,
                       CAST(p2_steps/{bin_size} AS INT) AS p2_bin,
                       child_epoch,
                       CAST(c1_steps/{bin_size} AS INT) AS c1_bin,
                       CAST(c2_steps/{bin_size} AS INT) AS c2_bin
                FROM read_csv_auto('{edges_steps_csv}', HEADER=TRUE);
            """)
            conn.execute(f"""
                COPY edges_steps_binned TO '{binned_csv}' (HEADER, DELIMITER ',');
            """)
            logger.info(f"   ✅ Binned → {binned_csv.stat().st_size:,} bytes")

            logger.info("🧹 Cleaning up intermediate batch files")
            import shutil
            shutil.rmtree(batch_output_dir, ignore_errors=True)

            conn.close()
            logger.info("✅ Done (CSV, batch=1, ultra low-memory)")
        
        # Replace the function temporarily
        globals()['build_edges_steps_duckdb'] = csv_build_edges_steps_duckdb
    
    # Run the post-processing pipeline
    logger.info("🧾 Running DuckDB post-processing...")
    
    # Check if required input files exist
    if args.use_csv:
        edge_files = list(args.local_tmp.glob("edges_epoch_*.csv"))
        node_files = list(args.local_tmp.glob("nodes_epoch_*.csv"))
    else:
        edge_files = list(args.local_tmp.glob("edges_epoch_*.parquet"))
        node_files = list(args.local_tmp.glob("nodes_epoch_*.parquet"))
    
    logger.info(f"🔍 Found {len(edge_files)} edge files and {len(node_files)} node files")
    
    if not edge_files:
        logger.error("❌ No edge files found")
        return
    
    if not node_files:
        logger.error("❌ No node files found")
        return
    
    # Run the post-processing steps
    logger.info("➡️  Step 1: Building edges_steps and binned edges via DuckDB")
    build_edges_steps_duckdb(args.local_tmp, args.bin_size)
    
    # Verify outputs
    step_edges_path = args.local_tmp / "edges_steps.csv"
    binned_edges_path = args.local_tmp / f"edges_steps_binned_{args.bin_size}.csv"
    
    if not step_edges_path.exists():
        logger.error("❌ edges_steps.csv not created")
        return
    if not binned_edges_path.exists():
        logger.error(f"❌ edges_steps_binned_{args.bin_size}.csv not created")
        return
        
    logger.info(f"   ✅ Step-based edges: {step_edges_path.stat().st_size:,} bytes")
    logger.info(f"   ✅ Binned edges: {binned_edges_path.stat().st_size:,} bytes")
    
    logger.info("➡️  Step 2: Exporting Gephi CSVs")
    export_gephi_csvs(args.local_tmp, args.bin_size)
    
    # Verify Gephi outputs
    gephi_edges_path = args.local_tmp / f"gephi_edges_weighted_{args.bin_size}.csv"
    gephi_nodes_path = args.local_tmp / f"gephi_nodes_{args.bin_size}.csv"
    
    if not gephi_edges_path.exists():
        logger.error("❌ Gephi edges file not created")
        return
    if not gephi_nodes_path.exists():
        logger.error("❌ Gephi nodes file not created")
        return
        
    logger.info(f"   ✅ Gephi edges: {gephi_edges_path.stat().st_size:,} bytes")
    logger.info(f"   ✅ Gephi nodes: {gephi_nodes_path.stat().st_size:,} bytes")
    
    logger.info("✅ DuckDB post-processing complete.")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:  # pragma: no cover
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DuckDB-based post-processing pipeline for cubff evolutionary runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert CSVs to Parquet first (one-time setup)
  python db_postprocess_duckdb.py --convert-to-parquet --local-tmp ./tmp_postprocess
  
  # Run post-processing with Parquet files (ultra-low-memory)
  python db_postprocess_duckdb.py --local-tmp ./tmp_postprocess --bin-size 25 --max-epochs 4096
  
  # Run with CSV files (fallback)
  python db_postprocess_duckdb.py --use-csv --local-tmp ./tmp_postprocess --bin-size 25
        """
    )
    
    parser.add_argument(
        "--local-tmp",
        type=Path,
        default=Path(LOCAL_TMP_DEFAULT),
        help=f"Local temporary directory (default: {LOCAL_TMP_DEFAULT})"
    )
    parser.add_argument(
        "--bin-size",
        type=int,
        default=BIN_SIZE_DEFAULT,
        help=f"Bin width for step binning (default: {BIN_SIZE_DEFAULT})"
    )
    parser.add_argument(
        "--max-epochs",
        type=int,
        default=MAX_EPOCHS_DEFAULT,
        help=f"Maximum epochs to process (default: {MAX_EPOCHS_DEFAULT})"
    )
    parser.add_argument(
        "--convert-to-parquet",
        action="store_true",
        help="Convert CSV files to Parquet format for efficient processing"
    )
    parser.add_argument(
        "--use-csv",
        action="store_true",
        help="Use CSV files instead of Parquet (fallback mode)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    return parser.parse_args(argv)


if __name__ == "__main__":  # pragma: no cover
    args = _parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    run_postprocessing_duckdb(args)
