import argparse
import os
import re
from typing import List

from PIL import Image, ImageDraw, ImageFont

from python.bff_interpreter import BffOp, get_op_kind

# Map byte values to printable BFF symbols
BFF_COMMANDS = {
    0x00: '0', 0x5b: '[', 0x5d: ']', 0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',', 0x3c: '<', 0x3e: '>', 0x7b: '{', 0x7d: '}'
}

# Mapping from BFF operations to RGB colors
COLOR_MAP = {
    BffOp.LOOP_START: (230, 25, 75),   # red
    BffOp.LOOP_END: (60, 180, 75),     # green
    BffOp.PLUS: (255, 225, 25),        # yellow
    BffOp.MINUS: (0, 130, 200),        # blue
    BffOp.COPY01: (245, 130, 48),      # orange
    BffOp.COPY10: (145, 30, 180),      # purple
    BffOp.DEC0: (70, 240, 240),        # cyan
    BffOp.INC0: (240, 50, 230),        # magenta
    BffOp.DEC1: (210, 245, 60),        # lime
    BffOp.INC1: (250, 190, 190),       # pink
    BffOp.NULL: (255, 0, 0),           # bright red for NULL
    BffOp.NOOP: (128, 128, 128),       # grey for comments / noops
}


def load_programs(path: str, limit: int) -> List[bytes]:
    """Read up to `limit` programs from a .dat soup file."""
    with open(path, "rb") as f:
        data = f.read()[24:]  # skip header
    programs = []
    for i in range(min(limit, len(data) // 64)):
        start = i * 64
        programs.append(data[start:start + 64])
    return programs


def programs_to_image(programs: List[bytes], epoch: int, cell_size: int = 12) -> Image.Image:
    """Convert a list of programs to an image with colored blocks + symbols + epoch label."""
    rows = len(programs)
    cols = 64
    margin = cell_size + 4

    img = Image.new("RGB", (cols * cell_size, rows * cell_size + margin), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Draw epoch label
    epoch_text = f"Epoch {epoch}"
    draw.text((4, 2), epoch_text, fill=(255, 255, 255), font=font)

    # Draw colored squares with symbols
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

            # Center the symbol in the square
            text_x = x0 + 2
            text_y = y0 + 1
            draw.text((text_x, text_y), symbol, fill=(0, 0, 0), font=font)

    return img


def extract_epoch(filename: str) -> int:
    match = re.match(r"^(\d+)\.dat$", filename)
    return int(match.group(1)) if match else -1


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize BFF soup as animated colored-symbol grid")
    parser.add_argument("folder", help="Folder containing .dat files")
    parser.add_argument("-n", "--num-programs", type=int, default=8,
                        help="Number of programs from each epoch")
    parser.add_argument("--fps", type=float, default=2.0,
                        help="Frames per second for the GIF")
    parser.add_argument("-o", "--output", default="soup.gif",
                        help="Output GIF filename")
    parser.add_argument("--cell-size", type=int, default=12,
                        help="Pixel size for each cell")
    parser.add_argument("--start", type=int, default=0,
                        help="Start epoch (inclusive)")
    parser.add_argument("--stop", type=int, required=True,
                        help="Stop epoch (inclusive)")
    parser.add_argument("--step", type=int, default=32,
                        help="Epoch step size (e.g., 32)")
    args = parser.parse_args()

    all_files = os.listdir(args.folder)
    dat_files = []
    for fname in all_files:
        if fname.endswith(".dat"):
            epoch = extract_epoch(fname)
            if epoch != -1 and args.start <= epoch <= args.stop and (epoch - args.start) % args.step == 0:
                dat_files.append((epoch, os.path.join(args.folder, fname)))

    if not dat_files:
        raise SystemExit("No matching .dat files found in specified range")

    dat_files.sort()
    frames = []

    for epoch, dat_path in dat_files:
        programs = load_programs(dat_path, args.num_programs)
        if not programs:
            print(f"Warning: no programs found in {dat_path}")
            continue
        print(f"Loaded {len(programs)} programs from epoch {epoch}")
        frames.append(programs_to_image(programs, epoch, args.cell_size))

    if not frames:
        raise SystemExit("No programs extracted from any .dat files")

    duration = int(1000 / args.fps) if args.fps > 0 else 100
    frames[0].save(
        args.output,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
    )
    print(f"Saved animation to {args.output}")


if __name__ == "__main__":
    main()
