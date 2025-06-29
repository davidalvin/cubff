from pathlib import Path
import duckdb
import logging
import argparse
import sys
import boto3
from boto3.s3.transfer import S3Transfer, TransferConfig
import pandas as pd

logger = logging.getLogger("per_epoch_postprocess")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

BIN_SIZE = 25  # Change as needed

# Global S3 config
S3_BUCKET = "bff-grammar"
S3_PREFIX = "soup/db_run_test"

# Initialize S3 client
s3 = boto3.client("s3")
transfer = S3Transfer(s3, config=TransferConfig(max_concurrency=4))

def download_from_s3_and_convert(epoch: int, input_dir: Path):
    """Download required CSVs for a given epoch, convert to Parquet."""
    filenames = [
        f"edges_epoch_{epoch:05d}.csv",
        f"nodes_epoch_{epoch:05d}.csv",
        f"nodes_epoch_{epoch+1:05d}.csv"
    ]

    for csv_fname in filenames:
        parquet_fname = csv_fname.replace(".csv", ".parquet")
        local_csv_path = input_dir / csv_fname
        local_parquet_path = input_dir / parquet_fname
        s3_key = f"{S3_PREFIX}/{csv_fname}"

        if local_parquet_path.exists():
            logger.debug(f"✅ Already present: {parquet_fname}")
            continue

        try:
            logger.info(f"⏬ Downloading {csv_fname} from s3://{S3_BUCKET}/{s3_key}")
            transfer.download_file(S3_BUCKET, s3_key, str(local_csv_path))

            logger.info(f"🔄 Converting {csv_fname} → {parquet_fname}")
            df = pd.read_csv(local_csv_path)
            df.to_parquet(local_parquet_path, index=False)
            local_csv_path.unlink()  # Delete CSV after conversion
        except Exception as e:
            logger.error(f"❌ Failed to download or convert {csv_fname}: {e}")
            raise

def download_all_required_files(start_epoch: int, end_epoch: int, input_dir: Path):
    """Download all required CSV files for the entire epoch range up front and convert to Parquet"""
    logger.info(f"📥 Downloading all required CSV files from s3://{S3_BUCKET}/{S3_PREFIX}")
    logger.info(f"📊 Epoch range: {start_epoch} to {end_epoch-1}")
    
    total_files = 0
    downloaded_files = 0
    skipped_files = 0
    
    for epoch in range(start_epoch, end_epoch):
        filenames = [
            f"edges_epoch_{epoch:05d}.csv",
            f"nodes_epoch_{epoch:05d}.csv",
            f"nodes_epoch_{epoch+1:05d}.csv"
        ]
        
        for csv_fname in filenames:
            total_files += 1
            parquet_fname = csv_fname.replace(".csv", ".parquet")
            local_csv_path = input_dir / csv_fname
            local_parquet_path = input_dir / parquet_fname
            s3_key = f"{S3_PREFIX}/{csv_fname}"
            
            if local_parquet_path.exists():
                logger.debug(f"✅ Already present: {parquet_fname}")
                skipped_files += 1
                continue
                
            try:
                logger.info(f"⏬ Downloading {csv_fname} from s3://{S3_BUCKET}/{s3_key}")
                transfer.download_file(S3_BUCKET, s3_key, str(local_csv_path))

                logger.info(f"🔄 Converting {csv_fname} → {parquet_fname}")
                df = pd.read_csv(local_csv_path)
                df.to_parquet(local_parquet_path, index=False)
                local_csv_path.unlink()  # Delete CSV after conversion
                downloaded_files += 1
            except Exception as e:
                logger.error(f"❌ Failed to download or convert {csv_fname}: {e}")
                raise
    
    logger.info(f"📊 Download summary: {downloaded_files} downloaded and converted, {skipped_files} skipped, {total_files} total files")

def download_from_s3(epoch: int, input_dir: Path):
    """Download required Parquet files for a given epoch (legacy function for backward compatibility)"""
    download_from_s3_and_convert(epoch, input_dir)

def get_duckdb_conn():
    conn = duckdb.connect()
    conn.execute("PRAGMA threads=1;")
    conn.execute("PRAGMA preserve_insertion_order=false;")
    conn.execute("PRAGMA memory_limit='3GB';")
    return conn

def process_epoch(epoch: int, input_dir: Path, output_dir: Path, bin_size: int, download: bool = False):
    if download:
        download_from_s3(epoch, input_dir)
    
    edges_path = input_dir / f"edges_epoch_{epoch:05d}.parquet"
    nodes_p_path = input_dir / f"nodes_epoch_{epoch:05d}.parquet"
    nodes_c_path = input_dir / f"nodes_epoch_{epoch+1:05d}.parquet"

    if not edges_path.exists() or not nodes_p_path.exists() or not nodes_c_path.exists():
        logger.warning(f"Skipping epoch {epoch}: missing files")
        return

    conn = get_duckdb_conn()
    try:
        logger.info(f"▶️ Epoch {epoch:05d}: loading input")
        # Drop tables individually
        conn.execute("DROP TABLE IF EXISTS edges")
        conn.execute("DROP TABLE IF EXISTS nodes_p")
        conn.execute("DROP TABLE IF EXISTS nodes_c")
        conn.execute("DROP TABLE IF EXISTS step_edges")
        conn.execute("DROP TABLE IF EXISTS step_edges_binned")

        conn.execute(f"CREATE TABLE edges AS SELECT * FROM read_parquet('{edges_path}')")
        conn.execute(f"CREATE TABLE nodes_p AS SELECT *, {epoch} AS epoch FROM read_parquet('{nodes_p_path}')")
        conn.execute(f"CREATE TABLE nodes_c AS SELECT *, {epoch + 1} AS epoch FROM read_parquet('{nodes_c_path}')")

        logger.info(f"🔗 Epoch {epoch:05d}: joining node step data")
        conn.execute("""
            CREATE TABLE step_edges AS
            SELECT e.*,
                   p1.exec_steps AS p1_steps,
                   p2.exec_steps AS p2_steps,
                   c1.exec_steps AS c1_steps,
                   c2.exec_steps AS c2_steps
            FROM edges e
            LEFT JOIN nodes_p p1 ON e.p1_idx = p1.tape_idx
            LEFT JOIN nodes_p p2 ON e.p2_idx = p2.tape_idx
            LEFT JOIN nodes_c c1 ON e.c1_idx = c1.tape_idx
            LEFT JOIN nodes_c c2 ON e.c2_idx = c2.tape_idx
        """)

        out_step = output_dir / f"step_edges_{epoch:05d}.parquet"
        conn.execute(f"COPY step_edges TO '{out_step}' (FORMAT PARQUET)")
        logger.info(f"✅ Wrote {out_step}")

        logger.info(f"📊 Epoch {epoch:05d}: binning step counts")
        conn.execute(f"""
            CREATE TABLE step_edges_binned AS
            SELECT parent_epoch,
                   CAST(p1_steps / {bin_size} AS INT) AS p1_bin,
                   CAST(p2_steps / {bin_size} AS INT) AS p2_bin,
                   child_epoch,
                   CAST(c1_steps / {bin_size} AS INT) AS c1_bin,
                   CAST(c2_steps / {bin_size} AS INT) AS c2_bin
            FROM step_edges
        """)

        out_binned = output_dir / f"step_edges_binned_{epoch:05d}.parquet"
        conn.execute(f"COPY step_edges_binned TO '{out_binned}' (FORMAT PARQUET)")
        logger.info(f"✅ Wrote {out_binned}")

    except Exception as e:
        logger.error(f"❌ Epoch {epoch:05d} failed: {e}")
    finally:
        conn.close()

def process_range(start_epoch: int, end_epoch: int, input_dir: Path, output_dir: Path, bin_size: int, download: bool = False):
    logger.info(f"🚀 Starting processing: epochs {start_epoch} to {end_epoch-1}")
    logger.info(f"📁 Input: {input_dir}")
    logger.info(f"📁 Output: {output_dir}")
    logger.info(f"📊 Bin size: {bin_size}")
    
    if download:
        logger.info(f"☁️ S3 downloads enabled: s3://{S3_BUCKET}/{S3_PREFIX}")
        # Download all required files up front
        download_all_required_files(start_epoch, end_epoch, input_dir)
        # Disable per-epoch downloads since we have everything now
        download = False
    
    for epoch in range(start_epoch, end_epoch):
        process_epoch(epoch, input_dir, output_dir, bin_size, download)
    
    logger.info(f"✅ Completed processing epochs {start_epoch} to {end_epoch-1}")

def main():
    parser = argparse.ArgumentParser(
        description="Process evolutionary lineage data by epoch, joining edge and node data and binning step counts",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--start-epoch", "-s",
        type=int,
        default=1,
        help="Starting epoch number (inclusive)"
    )
    
    parser.add_argument(
        "--end-epoch", "-e", 
        type=int,
        default=4096,
        help="Ending epoch number (exclusive)"
    )
    
    parser.add_argument(
        "--input-dir", "-i",
        type=Path,
        default=Path("./tmp_postprocess"),
        help="Input directory containing parquet files"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("./tmp_postprocess"),
        help="Output directory for processed files"
    )
    
    parser.add_argument(
        "--bin-size", "-b",
        type=int,
        default=25,
        help="Bin size for step count binning"
    )
    
    parser.add_argument(
        "--s3",
        action="store_true",
        help="Download required Parquet files from S3 before processing"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate arguments
    if args.start_epoch >= args.end_epoch:
        logger.error("start_epoch must be less than end_epoch")
        sys.exit(1)
    
    # Ensure directories exist
    args.input_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        process_range(args.start_epoch, args.end_epoch, args.input_dir, args.output_dir, args.bin_size, args.s3)
    except KeyboardInterrupt:
        logger.info("🛑 Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

# Example usage:
# python per_epoch_postprocess.py --start-epoch 1 --end-epoch 4096 --input-dir ./tmp_postprocess --output-dir ./tmp_postprocess --bin-size 25
# python per_epoch_postprocess.py -s 1 -e 128 -i ./tmp_postprocess -o ./tmp_postprocess -b 25
# python per_epoch_postprocess.py -s 1 -e 128 --s3 -v  # Download from S3 and process
