# visualize_soup.py
# This script creates an animated GIF from BFF simulation `.dat` files
# Each frame shows a sample of programs from a specific epoch as colored grids
# Supports both local and S3-based `.dat` files and batch-wise rendering with optional final stitching

import argparse
import os
import boto3
from typing import List
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from python.bff_interpreter import BffOp, get_op_kind  # Adjust this import if needed

BFF_COMMANDS = {
    0x00: '0', 0x5b: '[', 0x5d: ']', 0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',', 0x3c: '<', 0x3e: '>', 0x7b: '{', 0x7d: '}'
}

COLOR_MAP = {
    BffOp.LOOP_START: (230, 25, 75),
    BffOp.LOOP_END: (60, 180, 75),
    BffOp.PLUS: (255, 225, 25),
    BffOp.MINUS: (0, 130, 200),
    BffOp.COPY01: (245, 130, 48),
    BffOp.COPY10: (145, 30, 180),
    BffOp.DEC0: (70, 240, 240),
    BffOp.INC0: (240, 50, 230),
    BffOp.DEC1: (210, 245, 60),
    BffOp.INC1: (250, 190, 190),
    BffOp.NULL: (255, 0, 0),
    BffOp.NOOP: (128, 128, 128),
}

def download_dat_from_s3(bucket: str, key: str) -> bytes:
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()

def programs_to_image(programs: List[bytes], epoch: int, cell_size: int = 12) -> Image.Image:
    rows = len(programs)
    cols = 64
    margin = cell_size + 4
    img = Image.new("RGB", (cols * cell_size, rows * cell_size + margin), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    draw.text((4, 2), f"Epoch {epoch}", fill=(255, 255, 255), font=font)

    for row, program in enumerate(programs):
        for col, byte in enumerate(program):
            kind = get_op_kind(byte)
            color = COLOR_MAP.get(kind, COLOR_MAP[BffOp.NOOP])
            symbol = BFF_COMMANDS.get(byte, '?')
            x0 = col * cell_size
            y0 = row * cell_size + margin
            x1 = x0 + cell_size - 1
            y1 = y0 + cell_size - 1
            draw.rectangle([(x0, y0), (x1, y1)], fill=color)
            draw.text((x0 + 2, y0 + 1), symbol, fill=(0, 0, 0), font=font)
    return img

def process_batch(batch_epochs, args, batch_index):
    frames = []
    for epoch in batch_epochs:
        try:
            if args.s3_bucket and args.s3_prefix:
                key = os.path.join(args.s3_prefix, f"{epoch:010}.dat")
                data = download_dat_from_s3(args.s3_bucket, key)
            else:
                path = os.path.join(args.folder, f"{epoch:010}.dat")
                with open(path, "rb") as f:
                    data = f.read()
            data = data[24:]  # Skip header
            programs = [data[i*64:(i+1)*64] for i in range(min(args.num_programs, len(data)//64))]
        except Exception as e:
            print(f"⚠️ Epoch {epoch}: Failed to load → {e}")
            continue
        if not programs:
            print(f"⚠️ Epoch {epoch}: No programs found.")
            continue
        print(f"✅ Epoch {epoch}: {len(programs)} programs")
        frames.append(programs_to_image(programs, epoch, args.cell_size))

    if frames:
        output_dir = os.path.dirname(args.output)
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(args.output))[0]
        gif_path = os.path.join(output_dir, f"{base}_batch{batch_index:04d}.gif")
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / args.fps),
            loop=0,
        )
        print(f"💾 Saved batch {batch_index + 1} to {gif_path}")

def stitch_gifs(gif_paths, output_path):
    frames = []
    for path in gif_paths:
        try:
            with Image.open(path) as img:
                frames.extend([frame.copy() for frame in ImageSequence.Iterator(img)])
        except Exception as e:
            print(f"⚠️ Could not read {path}: {e}")
    if frames:
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0
        )
        print(f"🎬 Final stitched GIF saved to {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Visualize BFF soup as animated colored-symbol grid")
    parser.add_argument("folder", nargs="?", default=".", help="Folder containing .dat files (ignored if using S3)")
    parser.add_argument("-n", "--num-programs", type=int, default=8, help="Number of programs from each epoch")
    parser.add_argument("--fps", type=float, default=2.0, help="Frames per second for the GIF")
    parser.add_argument("-o", "--output", default="soup.gif", help="Final output GIF filename")
    parser.add_argument("--cell-size", type=int, default=12, help="Pixel size for each cell")
    parser.add_argument("--start", type=int, default=0, help="Start epoch (inclusive)")
    parser.add_argument("--stop", type=int, required=True, help="Stop epoch (inclusive)")
    parser.add_argument("--step", type=int, default=32, help="Epoch step size")
    parser.add_argument("--batch-size", type=int, default=128, help="Epochs per batch")
    parser.add_argument("--s3-bucket", type=str, help="S3 bucket containing .dat files")
    parser.add_argument("--s3-prefix", type=str, help="S3 prefix path")
    args = parser.parse_args()

    all_epochs = list(range(args.start, args.stop + 1, args.step))
    output_dir = os.path.dirname(args.output) or '.'
    base = os.path.splitext(os.path.basename(args.output))[0]

    batch_paths = []
    for i in range(0, len(all_epochs), args.batch_size):
        batch_epochs = all_epochs[i:i + args.batch_size]
        print(f"\n🚚 Processing batch {i // args.batch_size + 1}: epochs {batch_epochs[0]}–{batch_epochs[-1]}")
        process_batch(batch_epochs, args, batch_index=i // args.batch_size)
        batch_path = os.path.join(output_dir, f"{base}_batch{i // args.batch_size:04d}.gif")
        batch_paths.append(batch_path)

    response = input("\n❓ Stitch all batches into a final GIF? [y/N]: ")
    if response.strip().lower() == 'y':
        stitch_gifs(batch_paths, args.output)

if __name__ == "__main__":
    main()

