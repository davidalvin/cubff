import os
import boto3
import shutil
import argparse
import logging
import hashlib
from collections import defaultdict
from boto3.s3.transfer import TransferConfig, S3Transfer
import pandas as pd
from pathlib import Path
import sys

# === CONFIGURATION ===
S3_BUCKET = "bff-grammar"
S3_PREFIX = "soup/db_run_test/"
LOCAL_TMP = "./tmp_postprocess"
BIN_SIZE = 25
MAX_EPOCHS = 16  # Set to 128 for testing, change to 4096 for full run

# Initialize S3 client and transfer
s3 = boto3.client("s3")
transfer_config = TransferConfig(max_concurrency=10)
transfer = S3Transfer(s3, config=transfer_config)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('postprocess.log')
    ]
)
logger = logging.getLogger(__name__)

# DuckDB is required - no fallback
try:
    import duckdb
    from db_postprocess_duckdb import (
        build_edges_steps_duckdb,
        export_gephi_csvs
    )
    logger.info("✅ DuckDB post-processing available")
except ImportError as e:
    logger.error(f"❌ DuckDB not available: {e}")
    logger.error("DuckDB is required for this script. Please install with: pip install duckdb>=0.10")
    sys.exit(1)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Post-process evolutionary lineage data from S3")
    parser.add_argument("--s3-prefix", default="soup/db_run_test/", 
                       help="S3 prefix for data files (default: soup/db_run_test/)")
    parser.add_argument("--bin-size", type=int, default=25,
                       help="Bin width for step binning (default: 25)")
    parser.add_argument("--max-epochs", type=int, default=4096,
                       help="Maximum epochs to process (default: 4096)")
    parser.add_argument("--local-tmp", default="./tmp_postprocess",
                       help="Local temporary directory (default: ./tmp_postprocess)")
    parser.add_argument("--skip-upload", action="store_true",
                       help="Skip uploading outputs to S3")
    parser.add_argument("--upload-threshold", type=int, default=100,
                       help="Minimum file size in bytes to upload (default: 100)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Update global variables
    global LOCAL_TMP
    LOCAL_TMP = args.local_tmp
    
    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    return args

def list_s3_keys(s3_prefix):
    """Cache S3 key list once to avoid multiple pagination calls"""
    logger.info(f"📦 Scanning S3 bucket for keys with prefix: {s3_prefix}")
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    
    for page_num, page in enumerate(paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix), 1):
        logger.debug(f"  - Processing S3 page {page_num}...")
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    
    logger.info(f"✅ Found {len(keys)} total files in S3")
    return keys

def summarize_s3_contents(s3_keys):
    """Summarize S3 contents using cached key list"""
    logger.info("📊 Analyzing S3 contents...")
    
    stats = defaultdict(int)
    other_csvs = []
    
    for key in s3_keys:
        fname = os.path.basename(key)
        
        if fname.endswith(".dat"):
            stats[".dat"] += 1
        elif fname.startswith("edges_epoch_") and fname.endswith(".csv"):
            stats["edges_epoch"] += 1
        elif fname.startswith("nodes_epoch_") and fname.endswith(".csv"):
            stats["nodes_epoch"] += 1
        elif fname.endswith(".csv"):
            stats["other_csv"] += 1
            other_csvs.append(fname)

    logger.info(f"📊 S3 Summary: (total files: {len(s3_keys)})")
    logger.info(f"🔹 .dat files:         {stats['.dat']}")
    logger.info(f"🔹 edges_epoch CSVs:  {stats['edges_epoch']}")
    logger.info(f"🔹 nodes_epoch CSVs:  {stats['nodes_epoch']}")
    logger.info(f"🔹 Other CSVs:        {stats['other_csv']}")
    
    if other_csvs:
        logger.warning("🧹 Other CSV files (likely stale or outdated):")
        for f in other_csvs:
            logger.warning(f"   - {f}")
        logger.warning("❗ You may want to delete these before uploading new versions.")

def download_files_parallel(s3_keys, file_pattern, max_epochs, file_type):
    """Download files in parallel using S3Transfer"""
    logger.info(f"⏬ Downloading {file_pattern} files from S3 (up to epoch {max_epochs})...")
    
    # Filter keys by pattern and epoch
    target_keys = []
    for key in s3_keys:
        fname = os.path.basename(key)
        if fname.startswith(file_pattern) and fname.endswith(".csv"):
            try:
                # Extract epoch number from filename
                epoch_str = fname.replace(file_pattern, "").replace(".csv", "")
                epoch_num = int(epoch_str)
                if epoch_num <= max_epochs:
                    target_keys.append(key)
                else:
                    logger.debug(f"    - Skipping {key} (epoch {epoch_num} > {max_epochs})")
            except ValueError:
                logger.warning(f"    - Skipping {key} (could not parse epoch number)")
    
    logger.info(f"  - Found {len(target_keys)} {file_type} files to download")
    
    # Download files in parallel
    count = 0
    errors = 0
    
    for i, key in enumerate(target_keys, 1):
        fname = os.path.basename(key)
        dest_path = os.path.join(LOCAL_TMP, fname)
        
        logger.info(f"    - [{i}/{len(target_keys)}] Downloading {key} → {dest_path} ...")
        try:
            transfer.download_file(S3_BUCKET, key, dest_path)
            logger.info(f"      ✅ Success")
            count += 1
        except Exception as e:
            logger.error(f"      ❌ Failed: {e}")
            errors += 1
    
    logger.info(f"✅ Downloaded {count} {file_type} files. {errors} errors.")
    return count, errors

def combine_edges_pandas():
    """Combine edge files efficiently using pandas"""
    logger.info("🔗 Combining edge files using pandas...")
    
    edge_files = sorted(
        f for f in os.listdir(LOCAL_TMP) if f.startswith("edges_epoch_") and f.endswith(".csv")
    )
    logger.info(f"  - Found {len(edge_files)} edge files to combine.")
    
    if not edge_files:
        logger.error("❌ No edge files found to combine")
        return False
    
    # Read all files with pandas
    dfs = []
    for i, fname in enumerate(edge_files, 1):
        logger.info(f"    - Reading {fname} ({i}/{len(edge_files)})")
        try:
            df = pd.read_csv(os.path.join(LOCAL_TMP, fname))
            dfs.append(df)
            logger.debug(f"      - {len(df)} rows")
        except Exception as e:
            logger.error(f"      - Error reading {fname}: {e}")
            return False
    
    # Combine all dataframes
    logger.info("  - Combining dataframes...")
    try:
        combined_df = pd.concat(dfs, ignore_index=True)
        combined_path = os.path.join(LOCAL_TMP, "edges.csv")
        combined_df.to_csv(combined_path, index=False)
        
        logger.info(f"✅ Combined {len(edge_files)} files into edges.csv ({len(combined_df):,} rows)")
        return True
    except Exception as e:
        logger.error(f"❌ Error combining files: {e}")
        return False

def get_file_hash(filepath):
    """Calculate MD5 hash of file for upload optimization"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def upload_outputs_optimized(s3_prefix, upload_threshold=100):
    """Upload outputs with optimization (skip small files and track hashes)"""
    logger.info("📤 Uploading outputs to S3 (with optimization)...")
    
    # Track uploads for optimization
    upload_log_path = os.path.join(LOCAL_TMP, ".upload_log.txt")
    previous_uploads = {}
    
    # Load previous upload hashes
    if os.path.exists(upload_log_path):
        try:
            with open(upload_log_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) == 2:
                        previous_uploads[parts[0]] = parts[1]
        except Exception as e:
            logger.warning(f"Could not load upload log: {e}")
    
    uploaded_count = 0
    skipped_count = 0
    
    for fname in os.listdir(LOCAL_TMP):
        if fname.endswith(".csv") or fname.endswith(".png"):
            local_path = os.path.join(LOCAL_TMP, fname)
            s3_key = os.path.join(s3_prefix, fname)
            
            # Check file size
            file_size = os.path.getsize(local_path)
            if file_size < upload_threshold:
                logger.info(f"  - Skipping {fname} (size {file_size} < {upload_threshold})")
                skipped_count += 1
                continue
            
            # Check if file has changed
            current_hash = get_file_hash(local_path)
            if fname in previous_uploads and previous_uploads[fname] == current_hash:
                logger.info(f"  - Skipping {fname} (unchanged)")
                skipped_count += 1
                continue
            
            # Upload file
            logger.info(f"  - Uploading {fname} ({file_size:,} bytes) to s3://{S3_BUCKET}/{s3_key} ...")
            try:
                s3.upload_file(local_path, S3_BUCKET, s3_key)
                logger.info(f"    ✅ Success")
                
                # Update upload log
                previous_uploads[fname] = current_hash
                uploaded_count += 1
            except Exception as e:
                logger.error(f"    ❌ Failed: {e}")
    
    # Save updated upload log
    try:
        with open(upload_log_path, 'w') as f:
            for fname, file_hash in previous_uploads.items():
                f.write(f"{fname},{file_hash}\n")
    except Exception as e:
        logger.warning(f"Could not save upload log: {e}")
    
    logger.info(f"✅ Upload complete: {uploaded_count} uploaded, {skipped_count} skipped")

def run_postprocessing(bin_size, max_epochs):
    logger.info("🧾 Running post-processing steps...")
    
    logger.info("🦆 Using DuckDB-based post-processing (memory efficient)")
    return run_postprocessing_duckdb(bin_size, max_epochs)

def run_postprocessing_duckdb(bin_size, max_epochs):
    """Run post-processing using DuckDB for memory efficiency"""
    logger.info("🦆 Running DuckDB post-processing...")
    
    # Check if required input files exist (individual epoch files)
    edge_files = [f for f in os.listdir(LOCAL_TMP) if f.startswith("edges_epoch_") and f.endswith(".csv")]
    node_files = [f for f in os.listdir(LOCAL_TMP) if f.startswith("nodes_epoch_") and f.endswith(".csv")]
    
    logger.info(f"🔍 Found {len(edge_files)} edge files and {len(node_files)} node files")
    
    if not edge_files:
        logger.error("❌ No edge files found")
        return False
    
    if not node_files:
        logger.error("❌ No node files found")
        return False
    
    tmp_dir = Path(LOCAL_TMP)
    
    try:
        logger.info("➡️  Step 1: Building edges_steps and binned edges via DuckDB")
        build_edges_steps_duckdb(tmp_dir, bin_size)
        
        # Verify outputs
        step_edges_path = tmp_dir / "edges_steps.csv"
        binned_edges_path = tmp_dir / f"edges_steps_binned_{bin_size}.csv"
        
        if not step_edges_path.exists():
            logger.error("❌ edges_steps.csv not created")
            return False
        if not binned_edges_path.exists():
            logger.error(f"❌ edges_steps_binned_{bin_size}.csv not created")
            return False
            
        logger.info(f"   ✅ Step-based edges: {step_edges_path.stat().st_size:,} bytes")
        logger.info(f"   ✅ Binned edges: {binned_edges_path.stat().st_size:,} bytes")
        
        logger.info("➡️  Step 2: Exporting Gephi CSVs")
        export_gephi_csvs(tmp_dir, bin_size)
        
        # Verify Gephi outputs
        gephi_edges_path = tmp_dir / f"gephi_edges_weighted_{bin_size}.csv"
        gephi_nodes_path = tmp_dir / f"gephi_nodes_{bin_size}.csv"
        
        if not gephi_edges_path.exists():
            logger.error("❌ Gephi edges file not created")
            return False
        if not gephi_nodes_path.exists():
            logger.error("❌ Gephi nodes file not created")
            return False
            
        logger.info(f"   ✅ Gephi edges: {gephi_edges_path.stat().st_size:,} bytes")
        logger.info(f"   ✅ Gephi nodes: {gephi_nodes_path.stat().st_size:,} bytes")
        
        logger.info("✅ DuckDB post-processing complete.")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in DuckDB post-processing: {e}")
        import traceback
        traceback.print_exc()
        return False

def qc_outputs(bin_size):
    """Quality control check of all outputs"""
    logger.info("🔍 Quality Control Check...")
    
    expected_outputs = [
        "edges_steps.csv",
        f"edges_steps_binned_{bin_size}.csv", 
        f"gephi_edges_weighted_{bin_size}.csv",
        f"gephi_nodes_{bin_size}.csv"
    ]
    
    all_good = True
    total_size = 0
    
    for fname in expected_outputs:
        filepath = os.path.join(LOCAL_TMP, fname)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            total_size += size
            logger.info(f"   ✅ {fname}: {size:,} bytes")
            
            # Check if file is not empty
            if size == 0:
                logger.warning(f"   ⚠️  {fname}: WARNING - file is empty")
                all_good = False
        else:
            logger.error(f"   ❌ {fname}: MISSING")
            all_good = False
    
    logger.info(f"📊 QC Summary:")
    logger.info(f"   - Total output size: {total_size:,} bytes")
    logger.info(f"   - All files present: {'✅' if all_good else '❌'}")
    
    return all_good

def list_local_files():
    """List all files in LOCAL_TMP for debugging"""
    logger.info(f"\n📁 Files in {LOCAL_TMP}:")
    if not os.path.exists(LOCAL_TMP):
        logger.info("   Directory does not exist")
        return
    
    files = os.listdir(LOCAL_TMP)
    if not files:
        logger.info("   Directory is empty")
        return
    
    for fname in sorted(files):
        filepath = os.path.join(LOCAL_TMP, fname)
        if os.path.isfile(filepath):
            size = os.path.getsize(filepath)
            logger.info(f"   📄 {fname}: {size:,} bytes")
        else:
            logger.info(f"   📁 {fname}: (directory)")

def upload_outputs():
    logger.info("\n📤 Uploading outputs to S3...")
    for fname in os.listdir(LOCAL_TMP):
        if fname.endswith(".csv"):
            local_path = os.path.join(LOCAL_TMP, fname)
            s3_key = os.path.join(S3_PREFIX, fname)
            logger.info(f"  - Uploading {fname} to s3://{S3_BUCKET}/{s3_key} ...")
            try:
                s3.upload_file(local_path, S3_BUCKET, s3_key)
                logger.info("✅ Success")
            except Exception as e:
                logger.error(f"❌ Failed: {e}")

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Create local directory
    os.makedirs(LOCAL_TMP, exist_ok=True)
    
    logger.info("\n=== cubff_run_db_postprocess.py: START ===")
    logger.info(f"Configuration:")
    logger.info(f"  - S3 Prefix: {args.s3_prefix}")
    logger.info(f"  - Bin Width: {args.bin_size}")
    logger.info(f"  - Max Epochs: {args.max_epochs}")
    logger.info(f"  - Local Temp: {LOCAL_TMP}")
    logger.info(f"  - Skip Upload: {args.skip_upload}")
    
    # Initial file listing
    list_local_files()
    
    # Cache S3 keys once
    s3_keys = list_s3_keys(args.s3_prefix)
    
    summarize_s3_contents(s3_keys)
    
    # Download files in parallel
    download_files_parallel(s3_keys, "edges_epoch_", args.max_epochs, "edge")
    download_files_parallel(s3_keys, "nodes_epoch_", args.max_epochs, "node")
    
    # DuckDB will use individual epoch files directly
    logger.info("🦆 DuckDB available - skipping edge file combination (will use individual files)")
    
    # Check files after download
    logger.info("\n📋 Files after download:")
    list_local_files()
    
    # Run post-processing with error handling
    success = run_postprocessing(args.bin_size, args.max_epochs)
    
    if success:
        # Quality control check
        qc_passed = qc_outputs(args.bin_size)
        
        if qc_passed and not args.skip_upload:
            upload_outputs_optimized(args.s3_prefix, args.upload_threshold)
            logger.info("\n🏁 Done! All outputs generated and uploaded successfully.")
        elif qc_passed:
            logger.info("\n🏁 Done! All outputs generated successfully (upload skipped).")
        else:
            logger.warning("\n⚠️  QC failed - some outputs are missing or empty.")
            logger.warning("   Check the error messages above and fix the issues.")
    else:
        logger.error("\n❌ Post-processing failed - check error messages above.")
    
    # Final file listing
    logger.info("\n📋 Final file listing:")
    list_local_files()
    
    logger.info("=== cubff_run_db_postprocess.py: END ===\n")

if __name__ == "__main__":
    main()
