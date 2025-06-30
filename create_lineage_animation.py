#!/usr/bin/env python3
"""
Create an animated lineage-evolution video from per-epoch Parquet files
named  step_edges_binned_<epoch:05d>.parquet.

Designed for very large runs (e.g. 4 096 epochs × 100 k rows each):
• Loads at most one epoch file at a time → constant memory
• No CSV compression/indexing logic needed
• Same colour-mapped rendering you used before
"""

import os
import gc
import time
import argparse
import subprocess
from pathlib import Path
from collections import defaultdict

import pandas as pd
from PIL import Image, ImageDraw
import matplotlib.cm as cm
import matplotlib.colors as mcolors


# ──────────────────────────── helpers ────────────────────────────

def get_epoch_range_from_parquet(save_path: str) -> tuple[int, int]:
    """Determine min/max epoch numbers from filenames."""
    print(f"🔍 Scanning for Parquet files in: {save_path}")
    files = sorted(
        f for f in os.listdir(save_path)
        if f.startswith("step_edges_binned_") and f.endswith(".parquet")
    )
    if not files:
        raise FileNotFoundError("No step_edges_binned_<epoch>.parquet files found.")
    
    epochs = [int(f.split("_")[-1].replace(".parquet", "")) for f in files]
    min_epoch, max_epoch = min(epochs), max(epochs)
    print(f"📊 Found {len(files)} files spanning epochs {min_epoch}–{max_epoch}")
    return min_epoch, max_epoch


def get_bin_range_from_parquet(save_path: str,
                               min_epoch: int,
                               max_epoch: int,
                               sample: int = 10) -> int:
    """Estimate the maximum step-bin value by sampling a handful of files."""
    print(f"🔬 Sampling {sample} files to estimate max bin value...")
    max_bin = 0
    step = max(1, (max_epoch - min_epoch) // sample)
    sampled_files = 0
    
    for epoch in range(min_epoch, max_epoch + 1, step):
        fpath = os.path.join(save_path, f"step_edges_binned_{epoch:05d}.parquet")
        if not os.path.exists(fpath):
            print(f"⚠️  Skipping missing file: {fpath}")
            continue
        try:
            df = pd.read_parquet(
                fpath, columns=["p1_bin", "p2_bin", "c1_bin", "c2_bin"]
            )
            sampled_files += 1
            for col in df.columns:
                col_max = int(df[col].max(skipna=True))
                if col_max > max_bin:
                    max_bin = col_max
                    print(f"📈 New max bin {max_bin} found in epoch {epoch} ({col})")
        except Exception as e:
            print(f"❌ Error reading {fpath}: {e}")
            continue
    
    print(f"✅ Sampled {sampled_files} files, max bin value: {max_bin}")
    return max_bin


def load_edges_for_window_parquet(save_path: str,
                                  start_epoch: int,
                                  end_epoch: int) -> tuple[list, int, int]:
    """Aggregate edges for a sliding window of epochs, one file at a time."""
    edge_counts = defaultdict(int)
    processed_rows = 0
    processed_files = 0
    total_files = end_epoch - start_epoch + 1
    
    print(f"📂 Processing {total_files} files for epochs {start_epoch}–{end_epoch}...")
    
    for epoch in range(start_epoch, end_epoch + 1):
        fpath = os.path.join(save_path, f"step_edges_binned_{epoch:05d}.parquet")
        if not os.path.exists(fpath):
            print(f"⚠️  Missing file for epoch {epoch}: {fpath}")
            continue
        try:
            df = pd.read_parquet(fpath)
            processed_files += 1
            file_rows = len(df)
            processed_rows += file_rows
            
            print(f"📄 Epoch {epoch:5d}: {file_rows:6,} rows → ", end="")
            
            valid_edges = 0
            for _, row in df.iterrows():
                try:
                    pe, ce = int(row["parent_epoch"]), int(row["child_epoch"])
                    pbins = [int(row["p1_bin"]), int(row["p2_bin"])]
                    cbins = [int(row["c1_bin"]), int(row["c2_bin"])]
                    for pb in pbins:
                        for cb in cbins:
                            if pb >= 0 and cb >= 0:
                                edge_counts[((pe, pb), (ce, cb))] += 1
                                valid_edges += 1
                except Exception:
                    continue
            
            print(f"{valid_edges:6,} valid edges")
            
        except Exception as e:
            print(f"❌ Error reading epoch {epoch}: {e}")
            continue

    lines = list(edge_counts.items())         # [(edge_tuple, weight), …]
    print(f"✅ Processed {processed_files}/{total_files} files, {processed_rows:,} total rows, {len(lines):,} unique edges")
    return lines, len(lines), processed_rows


# ─────────────────────── drawing / rendering ─────────────────────

def draw_frame_from_edges(window_lines,
                          start_epoch,
                          end_epoch,
                          max_bin,
                          frame_num,
                          total_frames,
                          output_dir,
                          edge_count):
    """Rasterise one lineage frame."""
    print(f"🎨 Rendering frame {frame_num+1}/{total_frames} (epochs {start_epoch}–{end_epoch})...")
    
    width, height = 1600, 1000
    margin = 100
    plot_w = width - 2 * margin
    plot_h = height - 2 * margin

    epoch_span = end_epoch - start_epoch
    x_scale = plot_w / max(1, epoch_span)
    y_scale = plot_h / max(1, max_bin + 1)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # grid
    grid = (240, 240, 240)
    for i in range(0, epoch_span + 1, max(1, epoch_span // 10)):
        x = margin + i * x_scale
        draw.line([(x, margin), (x, height - margin)], fill=grid)
    for i in range(0, max_bin + 1, max(1, (max_bin + 1) // 10)):
        y = height - margin - i * y_scale
        draw.line([(margin, y), (width - margin, y)], fill=grid)

    # edges
    drawn_edges = 0
    if window_lines:
        max_weight = max(w for _, w in window_lines)
        cmap = cm.get_cmap("plasma")
        norm = mcolors.LogNorm(vmin=1, vmax=max_weight)

        for (p, c), w in window_lines:
            x0 = margin + (p[0] - start_epoch) * x_scale
            y0 = height - margin - p[1] * y_scale
            x1 = margin + (c[0] - start_epoch) * x_scale
            y1 = height - margin - c[1] * y_scale
            if (margin <= x0 <= width - margin and
                    margin <= x1 <= width - margin and
                    margin <= y0 <= height - margin and
                    margin <= y1 <= height - margin):
                rgb = tuple(int(255 * c) for c in cmap(norm(w))[:3])
                draw.line([(x0, y0), (x1, y1)], fill=rgb)
                drawn_edges += 1

    # save
    pad = len(str(total_frames))
    fname = f"frame_{frame_num:0{pad}d}.png"
    fpath = os.path.join(output_dir, fname)
    img.save(fpath, "PNG", optimize=True)
    del img, draw
    gc.collect()
    
    print(f"💾 Saved frame with {drawn_edges:,} drawn edges → {fname}")
    return fpath


def create_frame_pil_parquet(save_path,
                             start_epoch,
                             end_epoch,
                             max_bin,
                             frame_num,
                             total_frames,
                             output_dir):
    """Wrapper used by main loop."""
    lines, edge_cnt, row_cnt = load_edges_for_window_parquet(
        save_path, start_epoch, end_epoch
    )
    path = draw_frame_from_edges(
        lines, start_epoch, end_epoch, max_bin,
        frame_num, total_frames, output_dir, edge_cnt
    )
    return path, edge_cnt, row_cnt


# ──────────────────────────── main driver ─────────────────────────

def create_lineage_animation(save_path: str,
                             window_size: int = 32,
                             fps: int = 2,
                             output_path: str | None = None,
                             batch_size: int = 512,
                             start_epoch: int | None = None,
                             end_epoch: int | None = None):
    """End-to-end: frames → ffmpeg video."""
    print("🚀 Starting lineage animation creation...")
    print(f"📁 Data path: {save_path}")
    print(f"⚙️  Configuration: window_size={window_size}, fps={fps}")
    
    if output_path is None:
        output_path = os.path.join(save_path, "lineage_animation.mp4")
    print(f"🎬 Output: {output_path}")

    # detect min/max on disk
    min_ep_disk, max_ep_disk = get_epoch_range_from_parquet(save_path)

    # use caller-supplied subset if provided
    min_ep = start_epoch if start_epoch is not None else min_ep_disk
    max_ep = end_epoch   if end_epoch   is not None else max_ep_disk

    if min_ep < min_ep_disk or max_ep > max_ep_disk or min_ep > max_ep:
        raise ValueError("Requested epoch range is outside available data.")
    
    if start_epoch is not None or end_epoch is not None:
        print(f"🎯 Using custom epoch range: {min_ep}–{max_ep} (available: {min_ep_disk}–{max_ep_disk})")
    else:
        print(f"📊 Using full epoch range: {min_ep}–{max_ep}")

    max_bin = get_bin_range_from_parquet(save_path, min_ep, max_ep)
    total_frames = max(1, max_ep - window_size + 1)

    print(f"🎞️  Animation: {total_frames} frames, epochs {min_ep}–{max_ep}, max_bin={max_bin}")
    print("=" * 60)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        print(f"📂 Using temporary directory: {tmp}")
        times = []
        for frame in range(total_frames):
            s_ep = frame
            e_ep = s_ep + window_size
            t0 = time.time()
            _, edges, rows = create_frame_pil_parquet(
                save_path, s_ep, e_ep, max_bin, frame, total_frames, tmp
            )
            frame_time = time.time() - t0
            times.append(frame_time)
            
            if frame % 50 == 0 or frame == total_frames - 1:
                avg = sum(times) / len(times)
                eta = avg * (total_frames - frame - 1)
                print(f"📊 Progress: {frame+1}/{total_frames} frames "
                      f"({(frame+1)/total_frames*100:.1f}%) "
                      f"– avg {avg:.2f}s/frame, ETA: {eta/60:.1f}min")

        print("=" * 60)
        print("🎬 Creating video with ffmpeg...")
        pad = len(str(total_frames))
        pattern = os.path.join(tmp, f"frame_%0{pad}d.png")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path
        ]
        print(f"🔧 Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    
    print(f"✅ Video written → {output_path}")
    print(f"🎉 Animation complete! {total_frames} frames at {fps} FPS = {total_frames/fps:.1f}s video")


# ────────────────────────── CLI wrapper ───────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Animate lineage evolution from per-epoch Parquet files"
    )
    p.add_argument("data_path", type=Path,
                   help="Directory containing step_edges_binned_<epoch>.parquet")
    p.add_argument("--window-size", type=int, default=32,
                   help="Epochs visible per frame")
    p.add_argument("--fps", type=int, default=2, help="Frames per second")
    p.add_argument("--batch-size", type=int, default=512,
                   help="(reserved) frame batch size")
    p.add_argument("--output", type=Path,
                   help="Output .mp4 path (default: lineage_animation.mp4 in data dir)")
    p.add_argument("--start-epoch", type=int,
                   help="First epoch to include (inclusive)")
    p.add_argument("--end-epoch", type=int,
                   help="Last  epoch to include (inclusive)")
    args = p.parse_args()

    create_lineage_animation(
        save_path=str(args.data_path),
        window_size=args.window_size,
        fps=args.fps,
        output_path=str(args.output) if args.output else None,
        batch_size=args.batch_size,
        start_epoch=args.start_epoch,
        end_epoch=args.end_epoch
    )


if __name__ == "__main__":
    main()