import os
import random
from bin import cubff  # Provides access to compiled C++ simulation code
from bff_grammar_package.grammar_core.io import save_partial_soup_csv_raw, save_run_metadata
from histogram_tracker import HistogramTracker


# === PARAMETERS ===
NUM_PROGRAMS = 128*1024               # Total number of programs in the soup; 128 * 1024 is good default
PROGRAM_SIZE = 128               # Each "program" = 128 bytes = 2 × 64-byte tapes
SPLIT_AT = [64]                  # Tape boundary (used for visualization)
SEED = 0                         # Random seed for reproducibility; seed = 0 is good default
MUTATION_PROB = 1 << 18          # Mutation rate: 1 in 2^18 chance per byte per epoch; 1<< 18 is a good default
ZERO_INIT = False                # If True, initialize soup with zeros instead of random bytes
EVAL_SELFREP = False             # If True, run self-replication detection
PERMUTE_PROGRAMS = True          # Randomly shuffle pairings each epoch
FIXED_SHUFFLE = False            # Use deterministic shuffling scheme
SAVE_INTERVAL = 32                # Save full soup snapshot every N epochs
CALLBACK_INTERVAL = 1            # How often the callback runs
MAX_EPOCHS = 4096                   # Stop after this many epochs; 4096 is good default
NUM_PROGRAMS_TO_PRINT = 10       # Show a few programs in the console each epoch
NUM_PROGRAMS_TO_SAVE = 10        # Save a few programs to CSV each epoch

# Create output directory for saved data
RUN_NAME = "throwaway_run"
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)

# Load the BFF language interface (variant without explicit head encodings)
language = cubff.GetLanguage("bff_noheads")

# Initialize the histogram tracker to visualize step distributions
hist_tracker = HistogramTracker(SAVE_PATH)

def callback(state):
    """Called at the end of every `callback_interval` epochs."""

    print(state.epoch, state.brotli_size)  # Print epoch number and compressed size for debugging

    if state.steps_epoch_count:
        mean_steps = sum(state.total_steps_per_prog) / (
            len(state.total_steps_per_prog) * state.steps_epoch_count
        )
        max_steps = max(state.steps_per_prog)
        min_steps = min(state.steps_per_prog)
        print(f"Mean steps per program over epochs: {mean_steps:.2f}")
        print(f"Current epoch steps range: {min_steps} - {max_steps}")
        from collections import Counter

        dist = Counter(state.steps_per_prog)
        most_common = list(dist.items())[:5]
        print("Sample distribution (step_count: occurrences):", most_common)

    # Pick random programs to display
    num_programs = len(state.soup) // PROGRAM_SIZE
    indices = random.sample(range(num_programs), min(NUM_PROGRAMS_TO_PRINT, num_programs))

    for i, idx in enumerate(indices):
        start = idx * PROGRAM_SIZE
        end = start + PROGRAM_SIZE
        program = state.soup[start:end]

        print(f"\nProgram {i} (index {idx}):")
        language.PrintProgram(0, program, SPLIT_AT)  # Show nicely-formatted tape contents

    # Save a few programs as raw characters (for inspecting motifs)
    # save_partial_soup_csv_raw(
    #     state, SAVE_PATH, state.epoch,
    #     replace_noops=True, as_characters=True,
    #     program_size=PROGRAM_SIZE, num_to_save=NUM_PROGRAMS_TO_SAVE
    # )

    # Add a histogram frame for the current epoch
    hist_tracker.add_frame(state.steps_per_prog, state.epoch)

    # Stop simulation when reaching the epoch limit
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
            "MAX_EPOCHS": MAX_EPOCHS
        })

        # Save the histogram as an animated GIF
        hist_tracker.save_gif()

        return True  # signal termination

    return False  # keep running

# === Set up simulation parameters ===
params = cubff.SimulationParams()
params.num_programs = NUM_PROGRAMS
params.seed = SEED
params.mutation_prob = MUTATION_PROB
params.zero_init = ZERO_INIT
params.eval_selfrep = EVAL_SELFREP
params.permute_programs = PERMUTE_PROGRAMS
params.fixed_shuffle = FIXED_SHUFFLE
params.callback_interval = CALLBACK_INTERVAL
params.save_to = SAVE_PATH         # Save full soup snapshot files (for offline analysis)
params.save_interval = SAVE_INTERVAL

# === Run the simulation ===
cubff.ResetColors()  # Optional: reset color output for terminal
language.RunSimulation(params, None, callback)
