import os
import random
from bin import cubff  # Compiled C++ simulation bindings
from bff_grammar_package.grammar_core.io import save_partial_soup_csv_raw, save_run_metadata
from histogram_tracker import HistogramTracker

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

# Name for the run (used in output directory and saved file prefixes)
RUN_NAME = "20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED"

# === Output directory setup ===
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)

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
