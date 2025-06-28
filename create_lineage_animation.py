import os
import csv
import time
import argparse
import numpy as np
from collections import defaultdict
import subprocess
import tempfile
import shutil
import gc
from PIL import Image, ImageDraw, ImageFont
import math

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

def load_edges_for_window_streaming(save_path, bin_size, start_epoch, end_epoch):
    """Load edges for window using streaming approach - only keep minimal data in memory."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    # Use sets to avoid duplicates and minimize memory
    edge_coords = set()
    point_coords = set()
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
                                # Store as tuples for memory efficiency
                                edge_coords.add(((pe, pb), (ce, cb)))
                                point_coords.add((pe, pb))
                                point_coords.add((ce, cb))
            except Exception as e:
                continue
    
    # Convert to lists only at the end
    lines = list(edge_coords)
    edge_count = len(lines)
    
    # Clear sets to free memory
    del edge_coords, point_coords
    gc.collect()
    
    return lines, edge_count, processed_rows

def create_frame_pil_streaming(save_path, bin_size, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir):
    """Create a single frame using PIL with streaming data loading."""
    # Load data using streaming approach
    window_lines, edge_count, processed_rows = load_edges_for_window_streaming(save_path, bin_size, start_epoch, end_epoch)
    
    # Image dimensions
    width, height = 1600, 1000
    margin = 100
    
    # Create image
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Calculate plot area
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    # Scale factors
    epoch_range = end_epoch - start_epoch
    x_scale = plot_width / max(1, epoch_range)
    y_scale = plot_height / max(1, max_bin + 1)
    
    # Draw grid
    grid_color = (240, 240, 240)
    for i in range(0, epoch_range + 1, max(1, epoch_range // 10)):
        x = margin + i * x_scale
        draw.line([(x, margin), (x, height - margin)], fill=grid_color, width=1)
    
    for i in range(0, max_bin + 1, max(1, (max_bin + 1) // 10)):
        y = height - margin - i * y_scale
        draw.line([(margin, y), (width - margin, y)], fill=grid_color, width=1)
    
    # Draw edges (lines) - process in chunks to avoid memory spikes
    if window_lines:
        chunk_size = 10000  # Process 10k edges at a time
        for i in range(0, len(window_lines), chunk_size):
            chunk = window_lines[i:i+chunk_size]
            
            for line in chunk:
                x1 = margin + (line[0][0] - start_epoch) * x_scale
                y1 = height - margin - line[0][1] * y_scale
                x2 = margin + (line[1][0] - start_epoch) * x_scale
                y2 = height - margin - line[1][1] * y_scale
                
                # Only draw if both points are within bounds
                if (margin <= x1 <= width - margin and margin <= y1 <= height - margin and
                    margin <= x2 <= width - margin and margin <= y2 <= height - margin):
                    draw.line([(x1, y1), (x2, y2)], fill=(0, 100, 200, 100), width=1)
            
            # Clear chunk from memory
            del chunk
            gc.collect()
    
    # Draw points - use a more memory-efficient approach
    if window_lines:
        # Collect unique points
        points = set()
        for line in window_lines:
            points.add(line[0])
            points.add(line[1])
        
        # Draw points in chunks
        point_list = list(points)
        chunk_size = 5000
        for i in range(0, len(point_list), chunk_size):
            chunk = point_list[i:i+chunk_size]
            
            for point in chunk:
                x = margin + (point[0] - start_epoch) * x_scale
                y = height - margin - point[1] * y_scale
                
                if margin <= x <= width - margin and margin <= y <= height - margin:
                    draw.ellipse([x-1, y-1, x+1, y+1], fill=(0, 0, 0, 25))
            
            del chunk
            gc.collect()
        
        del points, point_list
    
    # Draw title
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
        except:
            font = ImageFont.load_default()
    
    title = f"Lineage Evolution - Epochs {start_epoch} to {end_epoch} ({edge_count} transitions)"
    draw.text((margin, 20), title, fill='black', font=font)
    
    # Draw axis labels
    draw.text((width//2, height - 30), "Epoch", fill='black', font=font)
    draw.text((20, height//2), "Step Bin", fill='black', font=font, angle=90)
    
    # Save frame
    frame_path = os.path.join(output_dir, f"frame_{frame_num:04d}.png")
    img.save(frame_path, 'PNG', optimize=True)
    
    # Explicitly delete objects to free memory
    del img, draw, window_lines
    gc.collect()
    
    return frame_path, edge_count, processed_rows

def create_epoch_index(save_path, bin_size):
    """Create an index mapping epochs to file positions for fast lookup."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    print(f"🔍 Creating epoch index for fast frame generation...")
    epoch_positions = defaultdict(list)
    row_count = 0
    
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                print(f"   - Indexed {row_count:,} rows...")
            
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                
                # Store file position for both parent and child epochs
                epoch_positions[pe].append(row_count - 1)
                epoch_positions[ce].append(row_count - 1)
            except Exception as e:
                continue
    
    print(f"✅ Created index for {len(epoch_positions)} epochs from {row_count:,} rows")
    return epoch_positions, row_count

def load_edges_for_window_indexed(save_path, bin_size, start_epoch, end_epoch, epoch_positions, total_rows):
    """Load edges for window using pre-built index for fast lookup."""
    edges_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    # Get all row positions that contain data for our epoch window
    relevant_rows = set()
    for epoch in range(start_epoch, end_epoch + 1):
        if epoch in epoch_positions:
            relevant_rows.update(epoch_positions[epoch])
    
    # Use sets to avoid duplicates and minimize memory
    edge_coords = set()
    processed_rows = 0
    
    # Read only the relevant rows
    with open(edges_path, newline="") as f:
        reader = csv.DictReader(f)
        
        for row_num, row in enumerate(reader):
            if row_num in relevant_rows:
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
                                    edge_coords.add(((pe, pb), (ce, cb)))
                except Exception as e:
                    continue
    
    lines = list(edge_coords)
    edge_count = len(lines)
    
    del edge_coords, relevant_rows
    gc.collect()
    
    return lines, edge_count, processed_rows

def draw_frame_from_edges(window_lines, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir, edge_count):
    """Draw a frame from edge data (separated from data loading logic)."""
    # Image dimensions
    width, height = 1600, 1000
    margin = 100
    
    # Create image
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # Calculate plot area
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    
    # Scale factors
    epoch_range = end_epoch - start_epoch
    x_scale = plot_width / max(1, epoch_range)
    y_scale = plot_height / max(1, max_bin + 1)
    
    # Draw grid
    grid_color = (240, 240, 240)
    for i in range(0, epoch_range + 1, max(1, epoch_range // 10)):
        x = margin + i * x_scale
        draw.line([(x, margin), (x, height - margin)], fill=grid_color, width=1)
    
    for i in range(0, max_bin + 1, max(1, (max_bin + 1) // 10)):
        y = height - margin - i * y_scale
        draw.line([(margin, y), (width - margin, y)], fill=grid_color, width=1)
    
    # Draw edges (lines) - process in chunks to avoid memory spikes
    if window_lines:
        chunk_size = 10000  # Process 10k edges at a time
        for i in range(0, len(window_lines), chunk_size):
            chunk = window_lines[i:i+chunk_size]
            
            for line in chunk:
                x1 = margin + (line[0][0] - start_epoch) * x_scale
                y1 = height - margin - line[0][1] * y_scale
                x2 = margin + (line[1][0] - start_epoch) * x_scale
                y2 = height - margin - line[1][1] * y_scale
                
                # Only draw if both points are within bounds
                if (margin <= x1 <= width - margin and margin <= y1 <= height - margin and
                    margin <= x2 <= width - margin and margin <= y2 <= height - margin):
                    draw.line([(x1, y1), (x2, y2)], fill=(0, 100, 200, 100), width=1)
            
            # Clear chunk from memory
            del chunk
            gc.collect()
    
    # Draw points - use a more memory-efficient approach
    if window_lines:
        # Collect unique points
        points = set()
        for line in window_lines:
            points.add(line[0])
            points.add(line[1])
        
        # Draw points in chunks
        point_list = list(points)
        chunk_size = 5000
        for i in range(0, len(point_list), chunk_size):
            chunk = point_list[i:i+chunk_size]
            
            for point in chunk:
                x = margin + (point[0] - start_epoch) * x_scale
                y = height - margin - point[1] * y_scale
                
                if margin <= x <= width - margin and margin <= y <= height - margin:
                    draw.ellipse([x-1, y-1, x+1, y+1], fill=(0, 0, 0, 25))
            
            del chunk
            gc.collect()
        
        del points, point_list
    
    # Draw title
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 16)
        except:
            font = ImageFont.load_default()
    
    title = f"Lineage Evolution - Epochs {start_epoch} to {end_epoch} ({edge_count} edges)"
    draw.text((margin, 20), title, fill='black', font=font)
    
    # Draw axis labels
    draw.text((width//2, height - 30), "Epoch", fill='black', font=font)
    draw.text((20, height//2), "Step Bin", fill='black', font=font, angle=90)
    
    # Save frame
    frame_path = os.path.join(output_dir, f"frame_{frame_num:04d}.png")
    img.save(frame_path, 'PNG', optimize=True)
    
    # Explicitly delete objects to free memory
    del img, draw
    gc.collect()
    
    return frame_path

def create_frame_pil_indexed(save_path, bin_size, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir, epoch_positions, total_rows):
    """Create a single frame using PIL with indexed data loading."""
    # Load data using indexed approach
    window_lines, edge_count, processed_rows = load_edges_for_window_indexed(
        save_path, bin_size, start_epoch, end_epoch, epoch_positions, total_rows
    )
    
    frame_path = draw_frame_from_edges(window_lines, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir, edge_count)
    
    # Explicitly delete objects to free memory
    del window_lines
    gc.collect()
    
    return frame_path, edge_count, processed_rows

def create_frame_pil_compressed(save_path, bin_size, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir):
    """Create a single frame using PIL with compressed data loading."""
    # Load data using compressed approach
    window_lines, edge_count, processed_rows = load_edges_for_window_compressed(
        save_path, bin_size, start_epoch, end_epoch
    )
    
    frame_path = draw_frame_from_edges(window_lines, start_epoch, end_epoch, max_bin, frame_num, total_frames, output_dir, edge_count)
    
    # Explicitly delete objects to free memory
    del window_lines
    gc.collect()
    
    return frame_path, edge_count, processed_rows

def compress_edges_file_by_epoch(save_path, bin_size):
    """Remove duplicate edges within each epoch and create a compressed version."""
    input_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    output_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}_compressed.csv")
    
    print(f"🗜️  Compressing edges file (by epoch)...")
    print(f"   - Input: {input_path}")
    print(f"   - Output: {output_path}")
    
    # Get original file size
    original_size = os.path.getsize(input_path)
    print(f"   - Original size: {original_size / (1024*1024):.1f} MB")
    
    # Group edges by epoch
    epoch_edges = defaultdict(lambda: defaultdict(int))
    row_count = 0
    
    print("   - Reading and grouping edges by epoch...")
    with open(input_path, newline="") as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            row_count += 1
            if row_count % 100000 == 0:
                print(f"     - Processed {row_count:,} rows...")
            
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                pbins = [int(row["p1_bin"]), int(row["p2_bin"])]
                cbins = [int(row["c1_bin"]), int(row["c2_bin"])]
                
                for pb in pbins:
                    for cb in cbins:
                        if pb >= 0 and cb >= 0:
                            # Create a unique key for this edge within the epoch
                            edge_key = (pe, pb, ce, cb)
                            epoch_edges[pe][edge_key] += 1
            except Exception as e:
                continue
    
    # Count totals
    total_original_edges = sum(sum(counts.values()) for counts in epoch_edges.values())
    total_unique_edges = sum(len(counts) for counts in epoch_edges.values())
    
    print(f"   - Original rows: {row_count:,}")
    print(f"   - Original edges: {total_original_edges:,}")
    print(f"   - Unique edges (by epoch): {total_unique_edges:,}")
    print(f"   - Compression ratio: {total_original_edges / total_unique_edges:.1f}x")
    
    # Write compressed file
    print("   - Writing compressed file...")
    compressed_count = 0
    with open(output_path, 'w', newline="") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["parent_epoch", "p1_bin", "p2_bin", "child_epoch", "c1_bin", "c2_bin", "count"])
        
        # Sort by epoch for consistent output
        for epoch in sorted(epoch_edges.keys()):
            for edge_key in sorted(epoch_edges[epoch].keys()):
                pe, pb, ce, cb = edge_key
                count = epoch_edges[epoch][edge_key]
                writer.writerow([pe, pb, pb, ce, cb, cb, count])
                compressed_count += 1
    
    # Get compressed file size
    compressed_size = os.path.getsize(output_path)
    print(f"   - Compressed size: {compressed_size / (1024*1024):.1f} MB")
    print(f"   - Size reduction: {original_size / compressed_size:.1f}x")
    print(f"   - Compressed rows: {compressed_count:,}")
    
    return output_path, total_unique_edges, compressed_count

def load_edges_for_window_compressed(save_path, bin_size, start_epoch, end_epoch):
    """Load edges from compressed file for a specific window."""
    compressed_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}_compressed.csv")
    
    if not os.path.exists(compressed_path):
        # Fall back to original file if compressed doesn't exist
        return load_edges_for_window_streaming(save_path, bin_size, start_epoch, end_epoch)
    
    edge_coords = set()
    processed_rows = 0
    
    with open(compressed_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            processed_rows += 1
            
            try:
                pe = int(row["parent_epoch"])
                ce = int(row["child_epoch"])
                
                # Only process edges within our window
                if start_epoch <= pe <= end_epoch and start_epoch <= ce <= end_epoch:
                    pb = int(row["p1_bin"])
                    cb = int(row["c1_bin"])
                    count = int(row.get("count", 1))
                    
                    if pb >= 0 and cb >= 0:
                        # Add the edge multiple times based on count
                        for _ in range(count):
                            edge_coords.add(((pe, pb), (ce, cb)))
            except Exception as e:
                continue
    
    lines = list(edge_coords)
    edge_count = len(lines)
    
    del edge_coords
    gc.collect()
    
    return lines, edge_count, processed_rows

def analyze_compression_potential(save_path, bin_size):
    """Analyze how much compression we can actually achieve."""
    input_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}.csv")
    
    print(f"🔍 Analyzing compression potential...")
    
    # Count total edges and unique edges by epoch
    total_edges = 0
    unique_edges_by_epoch = defaultdict(set)
    
    with open(input_path, newline="") as f:
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
                            total_edges += 1
                            edge_key = (pe, pb, ce, cb)
                            unique_edges_by_epoch[pe].add(edge_key)
            except Exception as e:
                continue
    
    unique_total = sum(len(edges) for edges in unique_edges_by_epoch.values())
    
    print(f"   - Total edges: {total_edges:,}")
    print(f"   - Unique edges (by epoch): {unique_total:,}")
    print(f"   - Compression ratio: {total_edges / unique_total:.1f}x")
    
    # Show top 10 epochs by edge count
    epoch_counts = [(epoch, len(edges)) for epoch, edges in unique_edges_by_epoch.items()]
    epoch_counts.sort(key=lambda x: x[1], reverse=True)
    
    print(f"   - Top 10 epochs by unique edge count:")
    for epoch, count in epoch_counts[:10]:
        print(f"     Epoch {epoch}: {count:,} unique edges")
    
    return total_edges, unique_total, unique_edges_by_epoch

def create_lineage_animation(save_path, bin_size=25, window_size=32, fps=2, output_path=None):
    """
    Create an animated video of epoch lineage evolution with compression analysis first.
    """
    if output_path is None:
        output_path = os.path.join(save_path, "lineage_animation.mp4")
    
    print(f"🎬 Creating lineage animation (with compression analysis)...")
    print(f"   - Window size: {window_size} epochs")
    print(f"   - FPS: {fps}")
    print(f"   - Output: {output_path}")
    
    # STEP 1: Run compression analysis first
    print("\n" + "="*60)
    print("STEP 1: COMPRESSION ANALYSIS")
    print("="*60)
    
    total_edges, unique_total, unique_edges_by_epoch = analyze_compression_potential(save_path, bin_size)
    compression_ratio = total_edges / unique_total
    
    print(f"\n📊 COMPRESSION ANALYSIS RESULTS:")
    print(f"   - Compression ratio: {compression_ratio:.1f}x")
    print(f"   - Original edges: {total_edges:,}")
    print(f"   - Unique edges: {unique_total:,}")
    
    # Decide whether to use compressed approach based on compression ratio
    use_compressed = compression_ratio >= 2.0
    
    if use_compressed:
        print(f"\n✅ Good compression ratio ({compression_ratio:.1f}x) - will use compressed file.")
        
        # Create compressed file if it doesn't exist
        compressed_path = os.path.join(save_path, f"edges_steps_binned_{bin_size}_compressed.csv")
        if not os.path.exists(compressed_path):
            print("\n🗜️  Creating compressed file...")
            compress_edges_file_by_epoch(save_path, bin_size)
    else:
        print(f"\n⚠️  Low compression ratio ({compression_ratio:.1f}x)")
        print(f"   This suggests most edges are already unique within epochs.")
        print(f"   Will use indexed approach instead.")
        
        proceed = input("\n❓ Do you want to proceed anyway? (y/n): ").strip().lower()
        if proceed != 'y':
            print("❌ Animation generation cancelled.")
            return None
    
    # STEP 2: Get data ranges
    print("\n" + "="*60)
    print("STEP 2: DATA RANGE ANALYSIS")
    print("="*60)
    
    start_time = time.time()
    min_epoch, max_epoch = get_epoch_range_from_file(save_path, bin_size)
    max_bin = get_bin_range_from_file(save_path, bin_size)
    scan_time = time.time() - start_time
    print(f"⏱️  File scanning completed in {scan_time:.2f}s")
    
    # STEP 3: Create epoch index (only if not using compressed)
    if not use_compressed:
        print("\n" + "="*60)
        print("STEP 3: INDEX CREATION")
        print("="*60)
        
        index_start = time.time()
        epoch_positions, total_rows = create_epoch_index(save_path, bin_size)
        index_time = time.time() - index_start
        print(f"⏱️  Index creation completed in {index_time:.2f}s")
    else:
        print("\n" + "="*60)
        print("STEP 3: USING COMPRESSED FILE")
        print("="*60)
        print("✅ Skipping index creation - will use compressed file directly.")
        epoch_positions = None
        total_rows = None
    
    # STEP 4: Calculate animation parameters
    total_frames = max(1, max_epoch - window_size + 1)
    print(f"\n🎞️  Animation parameters:")
    print(f"   - Total frames: {total_frames}")
    print(f"   - Epoch range: {min_epoch} to {max_epoch}")
    print(f"   - Estimated duration: {total_frames / fps:.1f}s")
    print(f"   - Approach: {'Compressed' if use_compressed else 'Indexed'}")
    print(f"   - Estimated total time: {total_frames * 15 / 60:.1f} minutes (assuming 15s per frame)")
    
    # Ask for confirmation before proceeding with frame generation
    print(f"\n⚠️  Frame generation will take approximately {total_frames * 15 / 60:.1f} minutes.")
    proceed = input("❓ Proceed with frame generation? (y/n): ").strip().lower()
    if proceed != 'y':
        print("❌ Frame generation cancelled.")
        return None
    
    # STEP 5: Generate frames (only if user confirms)
    print("\n" + "="*60)
    print("STEP 4: FRAME GENERATION")
    print("="*60)
    
    # Create temporary directory for frames
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"📁 Using temporary directory: {temp_dir}")
        
        # Generate frames one by one
        print("🎨 Generating frames...")
        frame_start = time.time()
        frame_times = []
        
        for frame in range(total_frames):
            frame_gen_start = time.time()
            start_epoch = frame
            end_epoch = start_epoch + window_size
            
            if use_compressed:
                frame_path, edge_count, processed_rows = create_frame_pil_compressed(
                    save_path, bin_size, start_epoch, end_epoch, 
                    max_bin, frame, total_frames, temp_dir
                )
            else:
                frame_path, edge_count, processed_rows = create_frame_pil_indexed(
                    save_path, bin_size, start_epoch, end_epoch, 
                    max_bin, frame, total_frames, temp_dir, epoch_positions, total_rows
                )
            
            frame_time = time.time() - frame_gen_start
            frame_times.append(frame_time)
            avg_frame_time = sum(frame_times) / len(frame_times)
            remaining_frames = total_frames - frame - 1
            eta = remaining_frames * avg_frame_time
            
            if (frame + 1) % 10 == 0 or frame == 0:
                print(f"   📹 Frame {frame + 1}/{total_frames} - Epochs {start_epoch}-{end_epoch} "
                      f"({edge_count} edges, {processed_rows:,} rows processed) "
                      f"- Frame time: {frame_time:.2f}s, ETA: {eta:.1f}s")
            
            # Force garbage collection every few frames
            if frame % 5 == 0:
                gc.collect()
        
        frame_gen_time = time.time() - frame_start
        print(f"⏱️  Frame generation completed in {frame_gen_time:.2f}s")
        
        # Combine frames into video using ffmpeg
        print(f"🎬 Combining frames into video...")
        combine_start = time.time()
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ ffmpeg not found. Please install ffmpeg to create the video.")
            print("   Frames are saved in the temporary directory.")
            return None
        
        # Build ffmpeg command
        frame_pattern = os.path.join(temp_dir, "frame_%04d.png")
        cmd = [
            'ffmpeg', '-y',  # Overwrite output file
            '-framerate', str(fps),
            '-i', frame_pattern,
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', '23',  # Good quality, reasonable file size
            output_path
        ]
        
        print(f"   Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ ffmpeg failed: {result.stderr}")
            return None
        
        combine_time = time.time() - combine_start
        print(f"⏱️  Video combination completed in {combine_time:.2f}s")
    
    total_time = time.time() - start_time
    print(f"✅ Animation saved to {output_path}")
    print(f"⏱️  Total processing time: {total_time:.2f}s")
    print(f"📊 Average frame generation time: {sum(frame_times)/len(frame_times):.2f}s")
    
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