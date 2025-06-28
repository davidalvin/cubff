import os
import csv
import time
import argparse
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.collections import LineCollection
import numpy as np
from collections import defaultdict

def get_epoch_range_from_file(save_path, bin_size):
    """Get the min and max epochs by scanning the file without loading everything."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    if not os.path.exists(edges_path):
        raise FileNotFoundError(f"Missing required file: {edges_path}")
    
    print(f"📖 Scanning epoch range from {edges_path}...")
    min_epoch = float('inf')
    max_epoch = 0
    
    # Get file size for progress reporting
    file_size = os.path.getsize(edges_path)
    print(f"   - File size: {file_size / (1024*1024):.1f} MB")
    
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        row_count = 0
        
        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                print(f"   - Processed {row_count:,} rows... (min: {min_epoch}, max: {max_epoch})")
            
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                min_epoch = min(min_epoch, pe, ce)
                max_epoch = max(max_epoch, pe, ce)
            except Exception as e:
                continue
    
    if min_epoch == float('inf'):
        min_epoch = 0
    
    print(f"✅ Epoch range: {min_epoch} to {max_epoch} (from {row_count:,} rows)")
    return min_epoch, max_epoch

def get_bin_range_from_file(save_path, bin_size):
    """Get the max bin by scanning the file without loading everything."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    if not os.path.exists(edges_path):
        raise FileNotFoundError(f"Missing required file: {edges_path}")
    
    print(f"📖 Scanning bin range from {edges_path}...")
    max_bin = 0
    
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        row_count = 0
        
        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                print(f"   - Processed {row_count:,} rows... (max bin: {max_bin})")
            
            try:
                pbins = [int(row["p1_bin"]), int(row["p2_bin"])]
                cbins = [int(row["c1_bin"]), int(row["c2_bin"])]
                
                for bin_val in pbins + cbins:
                    if bin_val >= 0:
                        max_bin = max(max_bin, bin_val)
            except Exception as e:
                continue
    
    print(f"✅ Max bin: {max_bin} (from {row_count:,} rows)")
    return max_bin

def load_edges_for_window(save_path, bin_size, start_epoch, end_epoch):
    """Load only the edges that fall within the specified epoch window."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    lines = []
    edge_count = 0
    processed_rows = 0
    
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            processed_rows += 1
            
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                
                # Only process edges within our window
                if start_epoch <= pe <= end_epoch and start_epoch <= ce <= end_epoch:
                    pbins = [int(row["p1_bin"]), int(row["p2_bin"])]
                    cbins = [int(row["c1_bin"]), int(row["c2_bin"])]
                    
                    for pb in pbins:
                        for cb in cbins:
                            if pb >= 0 and cb >= 0:
                                lines.append([(pe, pb), (ce, cb)])
                                edge_count += 1
            except Exception as e:
                continue
    
    return lines, edge_count, processed_rows

def create_lineage_animation(save_path, bin_size=25, window_size=32, fps=2, output_path=None):
    """
    Create an animated video of epoch lineage evolution using streaming approach.
    
    Args:
        save_path: Path containing the binned edge data
        bin_size: Bin size used for step binning
        window_size: Number of epochs to show in each frame
        fps: Frames per second for the animation
        output_path: Output path for the video (default: lineage_animation.mp4)
    """
    if output_path is None:
        output_path = os.path.join(save_path, "lineage_animation.mp4")
    
    print(f"🎬 Creating lineage animation (streaming mode)...")
    print(f"   - Window size: {window_size} epochs")
    print(f"   - FPS: {fps}")
    print(f"   - Output: {output_path}")
    
    # Get data ranges without loading everything
    start_time = time.time()
    min_epoch, max_epoch = get_epoch_range_from_file(save_path, bin_size)
    max_bin = get_bin_range_from_file(save_path, bin_size)
    scan_time = time.time() - start_time
    print(f"⏱️  File scanning completed in {scan_time:.2f}s")
    
    # Calculate animation parameters
    total_frames = max(1, max_epoch - window_size + 1)
    print(f"🎞️  Total frames: {total_frames}")
    estimated_duration = total_frames / fps
    print(f"⏱️  Estimated video duration: {estimated_duration:.1f}s")
    
    # Setup figure
    print("🎨 Setting up matplotlib figure...")
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlabel("Epoch")
    ax.set_ylabel(f"Step Bin ({bin_size} per bin)")
    ax.set_title("Lineage Evolution Over Time")
    
    # Set consistent axis limits
    ax.set_ylim(0, max_bin + 1)
    
    # Initialize empty collections
    scatter = ax.scatter([], [], s=1, color="black", alpha=0.1)
    line_collection = LineCollection([], colors="blue", linewidths=0.5, alpha=0.3)
    ax.add_collection(line_collection)
    
    # Track timing for progress reporting
    frame_times = []
    
    def animate(frame):
        frame_start = time.time()
        start_epoch = frame
        end_epoch = start_epoch + window_size
        
        # Load only the data for this window
        window_lines, edge_count, processed_rows = load_edges_for_window(save_path, bin_size, start_epoch, end_epoch)
        
        # Extract points for scatter plot
        window_points = []
        for line in window_lines:
            window_points.extend(line)
        
        # Update line collection
        if window_lines:
            line_collection.set_segments(window_lines)
        else:
            line_collection.set_segments([])
        
        # Update scatter points
        if window_points:
            x_coords = [pt[0] for pt in window_points]
            y_coords = [pt[1] for pt in window_points]
            scatter.set_offsets(np.column_stack([x_coords, y_coords]))
        else:
            scatter.set_offsets(np.empty((0, 2)))
        
        # Update axis limits and title
        ax.set_xlim(start_epoch, end_epoch)
        ax.set_title(f"Lineage Evolution - Epochs {start_epoch} to {end_epoch} ({edge_count} transitions)")
        
        # Progress reporting
        frame_time = time.time() - frame_start
        frame_times.append(frame_time)
        avg_frame_time = sum(frame_times) / len(frame_times)
        remaining_frames = total_frames - frame - 1
        eta = remaining_frames * avg_frame_time
        
        if (frame + 1) % 10 == 0 or frame == 0:
            print(f"   📹 Frame {frame + 1}/{total_frames} - Epochs {start_epoch}-{end_epoch} "
                  f"({edge_count} edges, {processed_rows:,} rows processed) "
                  f"- Frame time: {frame_time:.2f}s, ETA: {eta:.1f}s")
        
        return scatter, line_collection
    
    print("🎨 Creating animation...")
    anim_start = time.time()
    anim = animation.FuncAnimation(
        fig, animate, frames=total_frames, 
        interval=1000//fps, blit=False, repeat=True
    )
    
    print(f"💾 Saving animation to {output_path}...")
    save_start = time.time()
    anim.save(output_path, writer='ffmpeg', fps=fps, dpi=100)
    save_time = time.time() - save_start
    anim_time = time.time() - anim_start
    
    plt.close(fig)
    
    print(f"✅ Animation saved to {output_path}")
    print(f"⏱️  Total animation time: {anim_time:.2f}s")
    print(f"⏱️  File save time: {save_time:.2f}s")
    print(f"📊 Average frame processing time: {sum(frame_times)/len(frame_times):.2f}s")
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Create animated lineage visualization")
    parser.add_argument("data_path", help="Path to directory containing binned edge data")
    parser.add_argument("--bin-size", type=int, default=25, help="Bin size used for step binning")
    parser.add_argument("--window-size", type=int, default=32, help="Number of epochs to show in each frame")
    parser.add_argument("--fps", type=int, default=2, help="Frames per second for animation")
    parser.add_argument("--output", help="Output path for video file")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.data_path):
        print(f"❌ Data path does not exist: {args.data_path}")
        return
    
    print(f"🚀 Starting lineage animation generation...")
    print(f"   - Data path: {args.data_path}")
    print(f"   - Bin size: {args.bin_size}")
    print(f"   - Window size: {args.window_size}")
    print(f"   - FPS: {args.fps}")
    
    total_start = time.time()
    
    try:
        output_path = create_lineage_animation(
            args.data_path, 
            bin_size=args.bin_size,
            window_size=args.window_size,
            fps=args.fps,
            output_path=args.output
        )
        total_time = time.time() - total_start
        print(f"\n🎉 Animation complete!")
        print(f"   - File: {output_path}")
        print(f"   - Total time: {total_time:.2f}s")
    except Exception as e:
        print(f"❌ Error creating animation: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 