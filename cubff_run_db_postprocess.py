import os
import boto3
import shutil
from collections import defaultdict
from db_helpers import (
    write_step_edges,
    write_binned_step_edges,
    write_gephi_weighted_edges_from_binned_steps,
    write_gephi_nodes_from_bins
)

# === CONFIGURATION ===
S3_BUCKET = "bff-grammar"
S3_PREFIX = "soup/db_run_test/"
LOCAL_TMP = "./tmp_postprocess"
BIN_WIDTH = 25

s3 = boto3.client("s3")
os.makedirs(LOCAL_TMP, exist_ok=True)

def summarize_s3_contents():
    print("📦 Scanning S3 bucket for contents...")
    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX)

    stats = defaultdict(int)
    other_csvs = []

    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
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

    print("\n📊 S3 Summary:")
    print(f"🔹 .dat files:         {stats['.dat']}")
    print(f"🔹 edges_epoch CSVs:  {stats['edges_epoch']}")
    print(f"🔹 nodes_epoch CSVs:  {stats['nodes_epoch']}")
    print(f"🔹 Other CSVs:        {stats['other_csv']}")
    if other_csvs:
        print("🧹 Other CSV files (likely stale or outdated):")
        for f in other_csvs:
            print(f"   - {f}")
        print("❗ You may want to delete these before uploading new versions.")

def download_all_edges():
    print("\n⏬ Downloading all edge CSVs from S3...")
    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX)

    count = 0
    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            fname = os.path.basename(key)
            if fname.startswith("edges_epoch_") and fname.endswith(".csv"):
                dest_path = os.path.join(LOCAL_TMP, fname)
                s3.download_file(S3_BUCKET, key, dest_path)
                count += 1
    print(f"✅ Downloaded {count} edge CSVs.")

def combine_edges():
    print("\n🔗 Combining edge files into a single CSV...")
    edge_files = sorted(
        f for f in os.listdir(LOCAL_TMP) if f.startswith("edges_epoch_") and f.endswith(".csv")
    )
    combined_path = os.path.join(LOCAL_TMP, "edges.csv")

    with open(combined_path, "w") as f_out:
        for i, fname in enumerate(edge_files):
            with open(os.path.join(LOCAL_TMP, fname), "r") as f_in:
                if i > 0:
                    next(f_in)  # skip header
                f_out.writelines(f_in)

    print(f"✅ Combined {len(edge_files)} files into edges.csv")

def run_postprocessing():
    print("\n🧾 Running post-processing steps...")
    print("➡️  Step 1: Writing step-based edges")
    write_step_edges(LOCAL_TMP)

    print("➡️  Step 2: Writing binned step-based edges")
    write_binned_step_edges(LOCAL_TMP, bin_size=BIN_WIDTH)

    print("➡️  Step 3: Writing Gephi weighted edges")
    write_gephi_weighted_edges_from_binned_steps(LOCAL_TMP, bin_size=BIN_WIDTH)

    print("➡️  Step 4: Writing Gephi node labels")
    write_gephi_nodes_from_bins(LOCAL_TMP, bin_size=BIN_WIDTH)

    print("✅ Post-processing complete.")

def upload_outputs():
    print("\n📤 Uploading outputs to S3...")
    for fname in os.listdir(LOCAL_TMP):
        if fname.endswith(".csv"):
            local_path = os.path.join(LOCAL_TMP, fname)
            s3_key = os.path.join(S3_PREFIX, fname)
            s3.upload_file(local_path, S3_BUCKET, s3_key)
            print(f"✅ Uploaded {fname} → s3://{S3_BUCKET}/{s3_key}")

def main():
    summarize_s3_contents()
    download_all_edges()
    combine_edges()
    run_postprocessing()
    upload_outputs()
    print("\n🏁 Done! You may now clean up ./tmp_postprocess if you wish.")

if __name__ == "__main__":
    main()
