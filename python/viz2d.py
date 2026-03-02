# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Real-time 2D visualization of CuBFF soup evolution.

Each program in the soup is rendered as an 8x8 pixel block colored by byte
value (using the language-specific byte color map). Programs are arranged in
a grid and the matplotlib window updates live as the simulation runs.

Usage (from the repo root):
  python3 python/viz2d.py
  python3 python/viz2d.py --lang bff --num 1024 --grid-width 32
"""

import argparse
import math
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

# Allow running from the repo root or from the python/ subdirectory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bin import cubff


def _build_image(soup_bytes, lut, grid_cols, grid_rows, num_programs):
    """Convert flat soup bytes into an RGB grid image."""
    soup = np.frombuffer(soup_bytes[: num_programs * 64], dtype=np.uint8)
    # (N, 64) → colorize → (N, 64, 3)
    colored = lut[soup.reshape(num_programs, 64)]
    # Each program is 8 rows × 8 cols of pixels: (N, 8, 8, 3)
    colored = colored.reshape(num_programs, 8, 8, 3)
    # Tile programs into the full grid: (grid_rows, grid_cols, 8, 8, 3)
    colored = colored.reshape(grid_rows, grid_cols, 8, 8, 3)
    # Interleave program-rows and pixel-rows: (grid_rows*8, grid_cols*8, 3)
    return colored.transpose(0, 2, 1, 3, 4).reshape(grid_rows * 8, grid_cols * 8, 3)


def main():
    parser = argparse.ArgumentParser(
        description="Real-time 2D visualization of CuBFF soup evolution."
    )
    parser.add_argument(
        "--lang",
        default="bff_noheads",
        help="Language to simulate (default: bff_noheads)",
    )
    parser.add_argument(
        "--num",
        type=int,
        default=4096,
        help="Number of programs in the soup (default: 4096)",
    )
    parser.add_argument(
        "--grid-width",
        type=int,
        default=0,
        help="Grid width in programs (default: sqrt(num))",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    parser.add_argument(
        "--mutation-prob",
        type=int,
        default=0,
        help="Mutation probability numerator over 2^30 (default: library default)",
    )
    parser.add_argument(
        "--display-num",
        type=int,
        default=0,
        help="Number of programs to display (default: same as --num)",
    )
    args = parser.parse_args()

    num_programs = args.num
    display_num = args.display_num if args.display_num > 0 else num_programs
    if display_num > num_programs:
        print(f"Error: --display-num {display_num} cannot exceed --num {num_programs}")
        sys.exit(1)

    grid_cols = args.grid_width if args.grid_width > 0 else int(math.isqrt(display_num))
    grid_rows = display_num // grid_cols
    if grid_rows * grid_cols != display_num:
        print(
            f"Error: --display-num {display_num} is not evenly divisible by "
            f"--grid-width {grid_cols}. Choose values where display_num = grid_width * k."
        )
        sys.exit(1)

    language = cubff.GetLanguage(args.lang)

    params = cubff.SimulationParams()
    params.num_programs = num_programs
    params.seed = args.seed
    params.eval_selfrep = True
    if args.mutation_prob > 0:
        params.mutation_prob = args.mutation_prob

    # --- matplotlib setup ---
    fig, ax = plt.subplots(figsize=(8, 8))
    blank = np.zeros((grid_rows * 8, grid_cols * 8, 3), dtype=np.uint8)
    im = ax.imshow(blank, interpolation="nearest")
    ax.axis("off")
    title = ax.set_title(
        f"lang={args.lang}  |  {num_programs} programs (showing {display_num})  |  Initializing..."
    )
    plt.tight_layout()
    plt.ion()
    plt.show()

    lut = None  # Populated from state.byte_colors on the first callback.

    def callback(state):
        nonlocal lut
        if lut is None:
            lut = np.frombuffer(state.byte_colors, dtype=np.uint8).reshape(256, 3)

        image = _build_image(bytes(state.soup), lut, grid_cols, grid_rows, display_num)

        selfrep_count = sum(
            1 for x in state.replication_per_prog if x >= cubff.kSelfrepThreshold
        )
        im.set_data(image)
        title.set_text(
            f"lang={args.lang}  |  epoch={state.epoch}"
            f"  |  bpb={state.brotli_bpb:.3f}"
            f"  |  self-rep={selfrep_count}"
        )
        fig.canvas.draw_idle()
        plt.pause(0.001)
        return False  # Return True to stop the simulation early.

    language.RunSimulation(params, None, callback)

    plt.ioff()
    plt.show()


if __name__ == "__main__":
    main()
