import os
import io
import contextlib
import random
from bin import cubff

# === PARAMETERS ===
NUM_PROGRAMS = 128 * 1024  # 2^17 = 131072
PROGRAM_SIZE = 128
SPLIT_AT = [64]
SEED = 0
MUTATION_PROB = 1 << 18  # Default mutation probability (~0.0000038)
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

def format_program(language, program, split_at):
    # Display as characters with split indicator
    output = []
    for i, byte in enumerate(program):
        output.append(chr(byte) if 32 <= byte < 127 else f'\\x{byte:02x}')
        if (i + 1) in split_at:
            output.append(" | ")
    return ''.join(output)

def save_partial_soup(state, language, path, epoch):
    binary_sample = state.soup[:NUM_PROGRAMS_TO_SAVE * PROGRAM_SIZE]
    binary_path = os.path.join(path, f"partial_soup_epoch{epoch:04d}.bin")
    with open(binary_path, "wb") as f:
        f.write(bytearray(binary_sample))

    text_path = os.path.join(path, f"partial_soup_epoch{epoch:04d}.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        for i in range(NUM_PROGRAMS_TO_SAVE):
            start = i * PROGRAM_SIZE
            end = start + PROGRAM_SIZE
            program = state.soup[start:end]
            f.write(f"Program {i} (index {i}):\n")
            f.write(format_program(language, program, SPLIT_AT))
            f.write("\n\n")

def save_run_metadata(path, state):
    metadata_path = os.path.join(path, "run_metadata.txt")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write("=== Run Parameters ===\n")
        f.write(f"NUM_PROGRAMS = {NUM_PROGRAMS}\n")
        f.write(f"PROGRAM_SIZE = {PROGRAM_SIZE}\n")
        f.write(f"SPLIT_AT = {SPLIT_AT}\n")
        f.write(f"SEED = {SEED}\n")
        f.write(f"MUTATION_PROB = {MUTATION_PROB}\n")
        f.write(f"ZERO_INIT = {ZERO_INIT}\n")
        f.write(f"EVAL_SELFREP = {EVAL_SELFREP}\n")
        f.write(f"PERMUTE_PROGRAMS = {PERMUTE_PROGRAMS}\n")
        f.write(f"FIXED_SHUFFLE = {FIXED_SHUFFLE}\n")
        f.write(f"SAVE_INTERVAL = {SAVE_INTERVAL}\n")
        f.write(f"CALLBACK_INTERVAL = {CALLBACK_INTERVAL}\n")
        f.write(f"MAX_EPOCHS = {MAX_EPOCHS}\n\n")

        f.write("=== Runtime Metrics ===\n")
        f.write(f"Final Epoch = {state.epoch}\n")
        f.write(f"Total Ops = {state.total_ops}\n")
        f.write(f"MOPS/s = {state.mops_s:.2f}\n")
        f.write(f"Brotli Size = {state.brotli_size}\n")
        f.write(f"Bytes per Program = {state.bytes_per_prog:.2f}\n")
        f.write(f"h0 Entropy = {state.h0:.4f}\n")
        f.write(f"Brotli bpb = {state.brotli_bpb:.4f}\n")
        f.write(f"Entropy Gap = {state.higher_entropy:.4f}\n")

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

    
    save_partial_soup(state, language, SAVE_PATH, state.epoch)

    if state.epoch >= MAX_EPOCHS:
        save_run_metadata(SAVE_PATH, state)
        return True

    return False

params = cubff.SimulationParams()
params.num_programs = NUM_PROGRAMS
params.seed = SEED
params.mutation_prob = MUTATION_PROB
params.zero_init = ZERO_INIT
params.eval_selfrep = EVAL_SELFREP
params.permute_programs = PERMUTE_PROGRAMS
params.fixed_shuffle = FIXED_SHUFFLE
#params.save_to = SAVE_PATH
#params.save_interval = SAVE_INTERVAL
params.callback_interval = CALLBACK_INTERVAL

cubff.ResetColors()
language.RunSimulation(params, None, callback)
