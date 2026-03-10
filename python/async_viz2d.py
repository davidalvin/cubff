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

"""Kinetic async simulation mode for CuBFF.

Programs are scheduled via a priority queue (min-heap) keyed on cumulative ops
consumed. Faster self-replicators stay near the front of the queue and get
evaluated more often, creating selection pressure for speed.

Usage (from the repo root):
  python3 python/async_viz2d.py --lang bff_noheads --num 1024 --K 64
"""

import argparse
import heapq
import math
import os
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bin import cubff


def _splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return x ^ (x >> 31)


def _build_image(soup_bytes, lut, grid_cols, grid_rows, num_programs):
    """Convert flat soup bytes into an RGB grid image."""
    soup = np.frombuffer(soup_bytes[: num_programs * 64], dtype=np.uint8)
    colored = lut[soup.reshape(num_programs, 64)]
    colored = colored.reshape(num_programs, 8, 8, 3)
    colored = colored.reshape(grid_rows, grid_cols, 8, 8, 3)
    return colored.transpose(0, 2, 1, 3, 4).reshape(grid_rows * 8, grid_cols * 8, 3)


def main():
    parser = argparse.ArgumentParser(
        description="Kinetic async CuBFF simulation with priority-queue scheduling."
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
        "--K",
        type=int,
        default=64,
        dest="K",
        help="Batch size: programs popped from heap per step, must be even (default: 64)",
    )
    parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    parser.add_argument(
        "--mutation-prob",
        type=int,
        default=0,
        help="Mutation probability numerator over 2^30 (default: library default)",
    )
    parser.add_argument(
        "--grid-width",
        type=int,
        default=0,
        help="Grid width in programs (default: sqrt(display_num))",
    )
    parser.add_argument(
        "--display-num",
        type=int,
        default=0,
        help="Number of programs to display (default: same as --num)",
    )
    parser.add_argument(
        "--selfrep",
        action="store_true",
        help="Sample and count self-replicators each epoch (slower)",
    )
    args = parser.parse_args()

    num_programs = args.num
    K = args.K
    if K % 2 != 0:
        print(f"Error: --K must be even, got {K}")
        sys.exit(1)
    if K > num_programs:
        print(f"Error: --K ({K}) cannot exceed --num ({num_programs})")
        sys.exit(1)

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

    # --- matplotlib setup ---
    fig, ax = plt.subplots(figsize=(8, 8))
    blank = np.zeros((grid_rows * 8, grid_cols * 8, 3), dtype=np.uint8)
    im = ax.imshow(blank, interpolation="nearest")
    ax.axis("off")
    title = ax.set_title(
        f"lang={args.lang}  |  {num_programs} programs (showing {display_num})"
        f"  |  K={K}  |  Initializing..."
    )
    plt.tight_layout()
    plt.ion()
    plt.show()

    # --- Run 1 sync epoch to initialize soup and byte_colors LUT ---
    params = cubff.SimulationParams()
    params.num_programs = num_programs
    params.seed = args.seed
    params.callback_interval = 1
    if args.mutation_prob > 0:
        params.mutation_prob = args.mutation_prob

    lut = None
    initial_soup_bytes = None

    def init_callback(state):
        nonlocal lut, initial_soup_bytes
        lut = np.frombuffer(state.byte_colors, dtype=np.uint8).reshape(256, 3)
        initial_soup_bytes = bytes(state.soup)
        return True  # Stop after one epoch.

    language.RunSimulation(params, None, init_callback)

    # --- Build mutable soup for EvaluatePairs ---
    soup = cubff.VectorUint8(list(initial_soup_bytes))

    # --- Initialize priority queue: (cumulative_ops, prog_idx) ---
    timestamps = [0] * num_programs
    heap = list(enumerate(range(num_programs)))
    heap = [(0, i) for i in range(num_programs)]
    heapq.heapify(heap)

    mutation_prob = params.mutation_prob
    steps_per_epoch = num_programs // K
    global_step = 0
    epoch = 1  # Already completed 1 sync epoch.
    start_time = time.time()

    while True:
        # Pop K lowest-timestamp programs and form K/2 pairs.
        batch = [heapq.heappop(heap) for _ in range(K)]
        pairs_flat = [idx for _, idx in batch]
        pairs_vec = cubff.VectorUint32(pairs_flat)

        seed_for_step = args.seed ^ _splitmix64(global_step)
        ops = language.EvaluatePairs(soup, pairs_vec, seed_for_step, mutation_prob)

        # Update timestamps and push back onto the heap.
        for i, (ts, idx) in enumerate(batch):
            new_ts = ts + ops[i // 2]
            heapq.heappush(heap, (new_ts, idx))
            timestamps[idx] = new_ts

        global_step += 1

        if global_step % steps_per_epoch == 0:
            epoch += 1
            soup_bytes = bytes(soup)

            # Brotli compression.
            compressed_size, bpb = cubff.ComputeBrotliBpb(soup)

            # Optional selfrep sample.
            selfrep_count = 0
            if args.selfrep:
                sample_n = min(64, num_programs)
                sample_seed = _splitmix64(epoch)
                for si in range(sample_n):
                    prog_idx = _splitmix64(sample_seed ^ si) % num_programs
                    prog_data = list(soup_bytes[prog_idx * 64 : (prog_idx + 1) * 64])
                    parsed = cubff.VectorUint8(prog_data)
                    rep = language.EvalParsedSelfrep(parsed, epoch, args.seed, False)
                    if rep >= cubff.kSelfrepThreshold:
                        selfrep_count += 1

            # Update display.
            image = _build_image(soup_bytes, lut, grid_cols, grid_rows, display_num)
            im.set_data(image)
            elapsed = time.time() - start_time
            title_text = (
                f"lang={args.lang}  |  epoch={epoch}  |  K={K}"
                f"  |  bpb={bpb:.3f}  |  elapsed={elapsed:.1f}s"
            )
            if args.selfrep:
                title_text += f"  |  self-rep≈{selfrep_count}"
            title.set_text(title_text)
            fig.canvas.draw_idle()
            plt.pause(0.001)


if __name__ == "__main__":
    main()
