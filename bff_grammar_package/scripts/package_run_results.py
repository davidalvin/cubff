import os
import tarfile
import argparse
from pathlib import Path

def try_remove(file_path):
    if file_path.exists():
        print(f"  - {file_path.relative_to(file_path.parent)}")
        file_path.unlink()

def package_and_clean(output_dir, archive_name=None, full_clean=False):
    output_dir = Path(output_dir).resolve()
    if not output_dir.exists():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    if archive_name is None:
        archive_name = output_dir.name + "_results.tar.gz"
    archive_path = output_dir / archive_name

    # File types to archive and delete
    include_exts = {".json", ".gif", ".sh"}
    include_files = [
        f for f in output_dir.rglob("*")
        if f.suffix in include_exts and f.is_file()
    ]

    if not include_files:
        raise RuntimeError("No .json, .gif, or .sh files found to include in archive.")

    print(f"📦 Creating archive: {archive_path}")
    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in include_files:
            arcname = file_path.relative_to(output_dir)
            tar.add(file_path, arcname=arcname)
            print(f"  + {arcname}")

    print(f"✅ Archive created: {archive_path}")

    print(f"\n🧹 Deleting archived files:")
    for file_path in include_files:
        try_remove(file_path)

    # Clean pipeline-level files if requested
    if full_clean:
        parent_dir = output_dir.parent
        print(f"\n🧹 Deleting pipeline-level checkpoint and command files in: {parent_dir}")
        try_remove(parent_dir / "pipeline_checkpoint.json")
        try_remove(parent_dir / "pipeline_command.sh")
        try_remove(parent_dir / "rewrite_checkpoint.json")

    print(f"\n✅ Cleanup complete. Output directory is ready for a new run.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package and clean BFF run results")
    parser.add_argument("--output", type=str, required=True, help="Output directory from run_pipeline")
    parser.add_argument("--archive-name", type=str, help="Optional name for the output archive")
    parser.add_argument("--full-clean", action="store_true", help="Also delete pipeline-level checkpoint and command files")
    args = parser.parse_args()

    package_and_clean(args.output, args.archive_name, args.full_clean)
