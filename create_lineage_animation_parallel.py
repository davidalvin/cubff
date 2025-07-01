#!/usr/bin/env python3
"""
Multi‑core lineage‑animation generator for per‑epoch Parquet inputs.

* Incremental sliding window (no re‑scan)
* Vectorised edge aggregation with Pandas/NumPy
* OpenCV bucketed‑line rasteriser (fast) + **axis ticks / labels**
* Parallel frame production (`--workers`, default = logical CPU count)

The only change from the previous parallel version is cosmetic: we now add
X/Y tick‑marks and axis labels so the frames are self‑documenting.
"""

from __future__ import annotations

import os, gc, time, argparse, subprocess, math, tempfile
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, Tuple, List
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import cv2
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import boto3
from boto3.s3.transfer import S3Transfer, TransferConfig

PARQUET_PREFIX = "step_edges_binned_"
PARQUET_SUFFIX = ".parquet"
Edge = Tuple[int, int, int, int]  # (parent_epoch, p_bin, child_epoch, c_bin)

# ──────────────────── I/O helpers ─────────────────────

def list_parquet_epochs(dir_path: str) -> List[int]:
    files = [f for f in os.listdir(dir_path)
             if f.startswith(PARQUET_PREFIX) and f.endswith(PARQUET_SUFFIX)]
    if not files:
        raise FileNotFoundError("No step_edges_binned_<epoch>.parquet files found.")
    return sorted(int(f[len(PARQUET_PREFIX):-len(PARQUET_SUFFIX)]) for f in files)


def load_epoch_edges(dir_path: str, epoch: int) -> Counter[Edge]:
    fp = os.path.join(dir_path, f"{PARQUET_PREFIX}{epoch:05d}{PARQUET_SUFFIX}")
    df = pd.read_parquet(fp, columns=[
        "parent_epoch", "child_epoch",
        "p1_bin", "p2_bin", "c1_bin", "c2_bin",
    ])
    pe = np.repeat(df["parent_epoch"].values, 2).astype(np.int32)
    ce = np.repeat(df["child_epoch"].values, 2).astype(np.int32)
    p_bins = df[["p1_bin", "p2_bin"]].values.reshape(-1).astype(np.int32)
    c_bins = df[["c1_bin", "c2_bin"]].values.reshape(-1).astype(np.int32)
    mask = (p_bins >= 0) & (c_bins >= 0)
    arr = np.stack([pe[mask], p_bins[mask], ce[mask], c_bins[mask]], axis=1)
    df_edges = pd.DataFrame(arr, columns=["pe","pb","ce","cb"])
    return Counter({tuple(k): v for k, v in df_edges.value_counts().items()})


def get_bin_range(dir_path: str, epoch: int) -> int:
    fp = os.path.join(dir_path, f"{PARQUET_PREFIX}{epoch:05d}{PARQUET_SUFFIX}")
    df = pd.read_parquet(fp, columns=["p1_bin", "p2_bin", "c1_bin", "c2_bin"])
    return int(df.max().max())

# ────────────────── util ───────────────────

def update_window(window: Counter[Edge], add: Counter[Edge], drop: Counter[Edge]):
    for e,w in add.items():
        window[e] += w
    for e,w in drop.items():
        new = window[e] - w
        if new>0:
            window[e]=new
        else:
            del window[e]

# ───────────────── drawing ──────────────────

def draw_frame(edges: Counter[Edge], start_ep: int, end_ep: int, max_bin: int,
               idx: int, total: int, out_dir: str,
               width=1600, height=1000, margin=100):
    img = np.full((height, width, 3), 255, np.uint8)
    plot_w, plot_h = width-2*margin, height-2*margin
    span = end_ep - start_ep
    x_scale = plot_w / max(1, span)
    y_scale = plot_h / max(1, max_bin+1)

    # grid
    for i in range(0, span+1, max(1, span//10)):
        x = int(margin + i*x_scale)
        cv2.line(img, (x, margin), (x, height-margin), (240,240,240), 1)
    for i in range(0, max_bin+1, max(1, (max_bin+1)//10)):
        y = int(height-margin - i*y_scale)
        cv2.line(img, (margin, y), (width-margin, y), (240,240,240), 1)

    # axis ticks & labels (new)
    font = cv2.FONT_HERSHEY_SIMPLEX
    fs, th = 0.6, 1
    # X‑axis
    for i in range(0, span+1, max(1, span//10)):
        x = int(margin + i*x_scale)
        cv2.line(img, (x, height-margin), (x, height-margin+8), (100,100,100), 1)
        lbl = str(start_ep + i)
        tw, th_txt = cv2.getTextSize(lbl, font, fs, th)[0]
        cv2.putText(img, lbl, (x - tw//2, height-margin+25), font, fs, (70,70,70), th)
    # Y‑axis
    for i in range(0, max_bin+1, max(1, (max_bin+1)//10)):
        y = int(height-margin - i*y_scale)
        cv2.line(img, (margin-8, y), (margin, y), (100,100,100), 1)
        lbl = str(i)
        tw,_ = cv2.getTextSize(lbl, font, fs, th)[0]
        cv2.putText(img, lbl, (margin - 12 - tw, y + 5), font, fs, (70,70,70), th)
    # axis titles
    ft, ft_th = 0.8, 2
    # X
    txt = "Epoch"
    tw,_ = cv2.getTextSize(txt, font, ft, ft_th)[0]
    cv2.putText(img, txt, (width//2 - tw//2, height-10), font, ft, (50,50,50), ft_th)
    # Y (vertical)
    txt = "Step Bin"
    tw,_ = cv2.getTextSize(txt, font, ft, ft_th)[0]
    cv2.putText(img, txt, (10, height//2 + tw//2), font, ft, (50,50,50), ft_th)

    # edges
    if edges:
        max_w = max(edges.values())
        cmap, norm = cm.get_cmap('plasma'), mcolors.LogNorm(vmin=1, vmax=max_w)
        buckets: Dict[Tuple[int,int,int], List[np.ndarray]] = defaultdict(list)
        for (pe,pb,ce,cb), w in edges.items():
            x0 = int(margin + (pe-start_ep)*x_scale)
            y0 = int(height-margin - pb*y_scale)
            x1 = int(margin + (ce-start_ep)*x_scale)
            y1 = int(height-margin - cb*y_scale)
            if 0<=x0<width and 0<=x1<width and 0<=y0<height and 0<=y1<height:
                rgb = tuple(int(255*c) for c in cmap(norm(w))[:3])
                buckets[rgb].append(np.array([[x0,y0],[x1,y1]], np.int32))
        for col, segs in buckets.items():
            cv2.polylines(img, segs, False, (col[2],col[1],col[0]), 1)

    pad = len(str(total))
    cv2.imwrite(os.path.join(out_dir, f"frame_{idx:0{pad}d}.png"), img, [cv2.IMWRITE_PNG_COMPRESSION,3])

# ───────────────── worker ─────────────────

def render_slice(args):
    (dir_path, window, max_bin, min_ep, start_head, end_head, total, pad, tmp) = args
    try:
        print(f"🔄 Worker starting: epochs {start_head}–{end_head}")
        win_counts: Counter[Edge] = Counter(); cache: Dict[int,Counter[Edge]] = {}
        
        # Load initial window
        for ep in range(start_head, start_head+window):
            cnt = load_epoch_edges(dir_path, ep); cache[ep]=cnt; win_counts.update(cnt)
        
        frames_rendered = 0
        for head in range(start_head, end_head+1):
            tail = head+window-1
            idx = head - min_ep
            draw_frame(win_counts, head, tail, max_bin, idx, total, tmp)
            frames_rendered += 1
            
            if head < end_head:
                drop = cache.pop(head)
                add_ep = tail+1
                add = cache.get(add_ep)
                if add is None:
                    add = load_epoch_edges(dir_path, add_ep); cache[add_ep]=add
                update_window(win_counts, add, drop)
        
        print(f"✅ Worker completed: {frames_rendered} frames (epochs {start_head}–{end_head})")
        return frames_rendered
    except Exception as e:
        print(f"❌ Worker failed (epochs {start_head}–{end_head}): {e}")
        raise

# ───────────────── orchestrator ─────────────────

def is_s3_path(path: str) -> bool:
    return path.startswith("s3://")

def parse_s3_path(s3_path: str):
    # Returns (bucket, prefix)
    assert s3_path.startswith("s3://")
    path = s3_path[5:]
    parts = path.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return bucket, prefix

def download_step_edges_binned_from_s3(s3_path: str, epochs: list[int], local_dir: str):
    bucket, prefix = parse_s3_path(s3_path)
    s3 = boto3.client("s3")
    transfer = S3Transfer(s3, config=TransferConfig(max_concurrency=8))
    os.makedirs(local_dir, exist_ok=True)
    # List all files in the prefix
    paginator = s3.get_paginator("list_objects_v2")
    files_needed = {f"step_edges_binned_{epoch:05d}.parquet" for epoch in epochs}
    # Check which files already exist locally
    local_files = set(os.listdir(local_dir))
    files_to_download = files_needed - local_files
    found_files = set(local_files) & files_needed
    if files_to_download:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                fname = os.path.basename(obj["Key"])
                if fname in files_to_download:
                    dest_path = os.path.join(local_dir, fname)
                    print(f"⏬ Downloading {fname} from s3://{bucket}/{obj['Key']} ...")
                    transfer.download_file(bucket, obj["Key"], dest_path)
                    found_files.add(fname)
    missing = files_needed - found_files
    if missing:
        raise FileNotFoundError(f"Missing files in S3 or local: {missing}")
    print(f"✅ All {len(files_needed)} step_edges_binned parquet files are present in {local_dir} (downloaded {len(files_to_download)} new files).")

def animate(dir_path: str, window=32, fps=2,
            start_ep: int|None=None, end_ep: int|None=None,
            workers: int|None=None, output: str|None=None):
    print("🚀 Starting parallel lineage animation creation...")
    print(f"📁 Data path: {dir_path}")
    print(f"⚙️  Configuration: window_size={window}, fps={fps}")
    
    # S3 support: if dir_path is S3, download required files to ./tmp_postprocess
    if is_s3_path(dir_path):
        print("☁️  S3 path detected. Downloading required Parquet files to ./tmp_postprocess ...")
        # List epochs in S3 by scanning the prefix
        bucket, prefix = parse_s3_path(dir_path)
        s3 = boto3.client("s3")
        paginator = s3.get_paginator("list_objects_v2")
        epochs = set()
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                fname = os.path.basename(obj["Key"])
                if fname.startswith(PARQUET_PREFIX) and fname.endswith(PARQUET_SUFFIX):
                    try:
                        ep = int(fname[len(PARQUET_PREFIX):-len(PARQUET_SUFFIX)])
                        epochs.add(ep)
                    except Exception:
                        pass
        if not epochs:
            raise FileNotFoundError("No step_edges_binned_<epoch>.parquet files found in S3.")
        min_ep, max_ep = min(epochs), max(epochs)
        if start_ep is not None: min_ep = max(min_ep, start_ep)
        if end_ep   is not None: max_ep = min(max_ep, end_ep)
        if min_ep>max_ep: raise ValueError("Empty epoch range")
        selected_epochs = list(range(min_ep, max_ep+1))
        local_dir = './tmp_postprocess'
        os.makedirs(local_dir, exist_ok=True)
        download_step_edges_binned_from_s3(dir_path, selected_epochs, local_dir)
        dir_path = local_dir

    if output is None:
        output = os.path.join(dir_path, "lineage_animation.mp4")
    print(f"�� Output: {output}")

    print("🔍 Scanning epochs...")
    epochs = list_parquet_epochs(dir_path)
    min_ep, max_ep = epochs[0], epochs[-1]
    if start_ep is not None: min_ep = max(min_ep, start_ep)
    if end_ep   is not None: max_ep = min(max_ep, end_ep)
    if min_ep>max_ep: raise ValueError("Empty epoch range")
    
    if start_ep is not None or end_ep is not None:
        print(f"🎯 Using custom epoch range: {min_ep}–{max_ep} (available: {epochs[0]}–{epochs[-1]})")
    else:
        print(f"📊 Using full epoch range: {min_ep}–{max_ep}")

    print("🔬 Estimating max bin value...")
    max_bin = get_bin_range(dir_path, min_ep)
    print(f"📈 Max bin value: {max_bin}")

    total_frames = max_ep - min_ep - window + 2
    workers = workers or os.cpu_count()
    
    print(f"🎞️  Animation: {total_frames} frames, epochs {min_ep}–{max_ep}, max_bin={max_bin}")
    print(f"⚡ Parallel processing: {workers} workers")
    print("=" * 60)

    slice_sz = math.ceil(total_frames/workers)
    pad = len(str(total_frames))

    print("📂 Creating temporary directory for frame processing...")
    with tempfile.TemporaryDirectory() as tmp:
        print(f"📂 Using temporary directory: {tmp}")
        
        args = []
        for i in range(workers):
            h0 = min_ep + i*slice_sz
            h1 = min(min_ep + total_frames -1, h0 + slice_sz -1)
            if h0<=h1:
                args.append((dir_path, window, max_bin, min_ep, h0, h1, total_frames, pad, tmp))
                print(f"🔧 Worker {i+1}: epochs {h0}–{h1} ({h1-h0+1} frames)")
        
        print(f"🚀 Starting {len(args)} parallel workers...")
        t0=time.time()
        completed_frames = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(render_slice, a) for a in args]
            for f in as_completed(futures):
                frames_rendered = f.result()
                completed_frames += frames_rendered
                print(f"✅ Worker completed: {frames_rendered} frames (total: {completed_frames}/{total_frames})")
        
        render_time = time.time()-t0
        print(f"⏱️  Render time: {render_time:.2f}s ({total_frames/render_time:.1f} frames/sec)")
        
        print("🎬 Creating video with ffmpeg...")
        pattern = os.path.join(tmp, f"frame_%0{pad}d.png")
        cmd = ["ffmpeg","-y","-framerate",str(fps),"-i",pattern,
               "-c:v","libx264","-pix_fmt","yuv420p",output]
        print(f"🔧 Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    
    print("✅ video →", output)
    print(f"🎉 Animation complete! {total_frames} frames at {fps} FPS = {total_frames/fps:.1f}s video")
    print(f"⚡ Parallel speedup: {workers}x workers, {total_frames/render_time:.1f} frames/sec")

# ───────────────── CLI ─────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Parallel lineage animation with axis labels and S3 support")
    p.add_argument("data_path", help="Path to local directory or s3://bucket/prefix containing step_edges_binned_<epoch>.parquet files")
    p.add_argument("--window-size", type=int, default=32)
    p.add_argument("--fps", type=int, default=2)
    p.add_argument("--start-epoch", type=int)
    p.add_argument("--end-epoch", type=int)
    p.add_argument("--workers", type=int)
    p.add_argument("--output")
    a = p.parse_args()
    animate(a.data_path, a.window_size, a.fps,
            a.start_epoch, a.end_epoch, a.workers, a.output)
