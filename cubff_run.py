import os
import random
import csv
from bin import cubff  # Compiled C++ simulation bindings
from bff_grammar_package.grammar_core.io import (
    save_partial_soup_csv_raw,
    save_run_metadata,
)
from histogram_tracker import HistogramTracker
from trace_utils import trace_program_pair

# === PARAMETERS ===
NUM_PROGRAMS = 128 * 1024
PROGRAM_SIZE = 128
SPLIT_AT = [64]
SEED = 0
MUTATION_PROB = 1 << 18
ZERO_INIT = False
EVAL_SELFREP = False
PERMUTE_PROGRAMS = True
FIXED_SHUFFLE = False
SAVE_INTERVAL = 32
CALLBACK_INTERVAL = 1
MAX_EPOCHS = 4096
NUM_PROGRAMS_TO_PRINT = 10
NUM_PROGRAMS_TO_SAVE = 0
PRINT_EVERY = 16  # 👈 Only print to terminal every N epochs
DEBUG_EVERY = 8
DEBUG_SAMPLES = 3

# Name for the run (used in output directory and saved file prefixes)
RUN_NAME = "20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED"

# === Output directory setup ===
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)
DEBUG_LOG_DIR = os.path.join(SAVE_PATH, "debug_epoch_logs")
os.makedirs(DEBUG_LOG_DIR, exist_ok=True)

# === Load language + histogram tracker ===
language = cubff.GetLanguage("bff_noheads")
hist_tracker = HistogramTracker(
    save_path=SAVE_PATH,
    enabled=True,
    fps=5,
    batch_size=64,
    prefix=RUN_NAME,
    flush_interval=16  # Ensure this matches or divides evenly into MAX_EPOCHS
)

# === Callback executed every epoch ===
def callback(state):
    # Always track histogram frame
    hist_tracker.add_frame(state.steps_per_prog, state.epoch)

    # Save parent-child edges for this epoch
    edges_path = os.path.join(SAVE_PATH, f"edges_{state.epoch:04d}.csv")
    nodes_path = os.path.join(SAVE_PATH, f"nodes_{state.epoch:04d}.csv")
    with open(edges_path, "w", newline="") as ef:
        ew = csv.writer(ef)
        ew.writerow(["source", "target"])
        shuffle = state.shuffle_idx
        for i in range(0, len(shuffle), 2):
            p1 = shuffle[i]
            p2 = shuffle[i + 1] if i + 1 < len(shuffle) else None
            ew.writerow([p1, p1])
            if p2 is not None:
                ew.writerow([p2, p1])
                ew.writerow([p1, p2])
                ew.writerow([p2, p2])

    with open(nodes_path, "w", newline="") as nf:
        nw = csv.writer(nf)
        nw.writerow(["id", "epoch", "exec_time"])
        for idx, steps in enumerate(state.steps_per_prog):
            nw.writerow([idx, state.epoch, steps])

    # Only print every PRINT_EVERY epochs or at the final epoch
    if state.epoch % PRINT_EVERY == 0 or state.epoch == MAX_EPOCHS:
        print(f"\n📦 Epoch {state.epoch} | Brotli size: {state.brotli_size}")

        if state.steps_epoch_count:
            mean_steps = sum(state.total_steps_per_prog) / (
                len(state.total_steps_per_prog) * state.steps_epoch_count
            )
            max_steps = max(state.steps_per_prog)
            min_steps = min(state.steps_per_prog)
            print(f"📊 Mean steps: {mean_steps:.2f}, Range: {min_steps}–{max_steps}")

        # Display a few sample programs
        num_programs = len(state.soup) // PROGRAM_SIZE
        if num_programs > 0:
            indices = random.sample(range(num_programs), min(NUM_PROGRAMS_TO_PRINT, num_programs))
            for i, idx in enumerate(indices):
                start = idx * PROGRAM_SIZE
                end = start + PROGRAM_SIZE
                program = state.soup[start:end]
                print(f"\n🧬 Program {i} (index {idx}):")
                language.PrintProgram(0, program, SPLIT_AT)

        if state.epoch % DEBUG_EVERY == 0:
            pair_count = len(state.shuffle_idx) // 2
            samples = random.sample(range(pair_count), min(DEBUG_SAMPLES, pair_count))
            for p in samples:
                print(f"\n🔍 Pair {p} details:")
                trace_program_pair(state, p, PROGRAM_SIZE)

    # Finalize after last epoch
    if state.epoch >= MAX_EPOCHS:
        save_run_metadata(SAVE_PATH, state, {
            "NUM_PROGRAMS": NUM_PROGRAMS,
            "PROGRAM_SIZE": PROGRAM_SIZE,
            "SPLIT_AT": SPLIT_AT,
            "SEED": SEED,
            "MUTATION_PROB": MUTATION_PROB,
            "ZERO_INIT": ZERO_INIT,
            "EVAL_SELFREP": EVAL_SELFREP,
            "PERMUTE_PROGRAMS": PERMUTE_PROGRAMS,
            "FIXED_SHUFFLE": FIXED_SHUFFLE,
            "SAVE_INTERVAL": SAVE_INTERVAL,
            "CALLBACK_INTERVAL": CALLBACK_INTERVAL,
            "MAX_EPOCHS": MAX_EPOCHS,
            "PRINT_EVERY": PRINT_EVERY
        })

         # hist_tracker.save_gif()
        hist_tracker.plot_median_graph()
        hist_tracker.save_histogram_csv()  # ✅ Save histogram data to CSV

        return True  # Signal to stop simulation

    return False  # Keep going

# === Simulation setup and execution ===
params = cubff.SimulationParams()
params.num_programs = NUM_PROGRAMS
params.seed = SEED
params.mutation_prob = MUTATION_PROB
params.zero_init = ZERO_INIT
params.eval_selfrep = EVAL_SELFREP
params.permute_programs = PERMUTE_PROGRAMS
params.fixed_shuffle = FIXED_SHUFFLE
params.callback_interval = CALLBACK_INTERVAL
params.save_to = SAVE_PATH
params.save_interval = SAVE_INTERVAL

cubff.ResetColors()
language.RunSimulation(params, None, callback)
