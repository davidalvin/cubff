import os
import random
from bin import cubff
from bff_io_helpers import save_partial_soup_csv_raw, save_run_metadata

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
SAVE_INTERVAL = 128
CALLBACK_INTERVAL = 128
MAX_EPOCHS = 256
NUM_PROGRAMS_TO_PRINT = 10
NUM_PROGRAMS_TO_SAVE = 10

RUN_NAME = "example_run"
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)

language = cubff.GetLanguage("bff_noheads")

def callback(state):
    print(state.epoch, state.brotli_size)

    num_programs = len(state.soup) // PROGRAM_SIZE
    indices = random.sample(range(num_programs), min(NUM_PROGRAMS_TO_PRINT, num_programs))

    for i, idx in enumerate(indices):
        start = idx * PROGRAM_SIZE
        end = start + PROGRAM_SIZE
        program = state.soup[start:end]
        print(f"\nProgram {i} (index {idx}):")
        language.PrintProgram(0, program, SPLIT_AT)

    save_partial_soup_csv_raw(
        state, SAVE_PATH, state.epoch,
        replace_noops=True, as_characters=True,
        program_size=PROGRAM_SIZE, num_to_save=NUM_PROGRAMS_TO_SAVE
    )

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
        return True

    return False

# === Simulation Parameters ===
params = cubff.SimulationParams()
params.num_programs = NUM_PROGRAMS
params.seed = SEED
params.mutation_prob = MUTATION_PROB
params.zero_init = ZERO_INIT
params.eval_selfrep = EVAL_SELFREP
params.permute_programs = PERMUTE_PROGRAMS
params.fixed_shuffle = FIXED_SHUFFLE
params.callback_interval = CALLBACK_INTERVAL

cubff.ResetColors()
language.RunSimulation(params, None, callback)
