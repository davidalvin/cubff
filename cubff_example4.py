from bin import cubff
import random

language = cubff.GetLanguage("bff_noheads")

PROGRAM_SIZE = 128
NUM_PROGRAMS_TO_PRINT = 10
SPLIT_AT = [64]  # logical split in the 128-byte tape

def callback(state):
    print(f"Epoch: {state.epoch}")
    print(f"Brotli size: {state.brotli_size}")
    print(f"Elapsed time (s): {state.elapsed_s:.2f}")
    print(f"Total ops: {state.total_ops}")
    print(f"MOPS/s: {state.mops_s:.2f}")
    print(f"Ops per run: {state.ops_per_run:.2f}")
    print(f"Brotli bits per byte: {state.brotli_bpb:.4f}")
    print(f"Bytes per program: {state.bytes_per_prog:.2f}")
    print(f"Entropy h0: {state.h0:.4f}")
    print(f"Higher entropy: {state.higher_entropy:.4f}")

    print("\nTop 5 frequent bytes:")
    for byte, freq in state.frequent_bytes[:5]:
        print(f"  {byte}: {freq:.4f}")

    print("\nTop 5 uncommon bytes:")
    for byte, freq in state.uncommon_bytes[:5]:
        print(f"  {byte}: {freq:.4f}")

    num_programs = len(state.soup) // PROGRAM_SIZE
    indices = random.sample(range(num_programs), min(NUM_PROGRAMS_TO_PRINT, num_programs))

    for i, idx in enumerate(indices):
        start = idx * PROGRAM_SIZE
        end = start + PROGRAM_SIZE
        program = state.soup[start:end]
        print(f"\nProgram {i} (index {idx}):")
        language.PrintProgram(0, program, SPLIT_AT)

    return state.epoch > 4096  # Run up to 1024 epochs

params = cubff.SimulationParams()
params.num_programs = 131072
params.seed = 0
params.mutation_prob = 0


cubff.ResetColors()
language.RunSimulation(params, None, callback)
