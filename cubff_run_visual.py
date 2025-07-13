#!/usr/bin/env python3
import os
import sys
import tempfile
import json
import argparse
import random

# Add the bin directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bin'))

try:
    import cubff
    print("✅ Successfully imported cubff module")
except ImportError as e:
    print(f"❌ Failed to import cubff: {e}")
    print("Make sure you've built the Python bindings with: make PYTHON=1 CUDA=0")
    sys.exit(1)

parser = argparse.ArgumentParser()
parser.add_argument("--enable_async", action="store_true")
parser.add_argument("--ops_interval", type=int, default=1_000_000)
parser.add_argument("--show_programs", action="store_true", default=True)
parser.add_argument("--program_count", type=int, default=3)
args = parser.parse_args()

ENABLE_ASYNC = args.enable_async
OPS_INTERVAL = args.ops_interval
SHOW_PROGRAMS = args.show_programs
PROGRAM_COUNT = args.program_count

if ENABLE_ASYNC and not getattr(cubff, "HAVE_ASYNC", False):
    raise RuntimeError("cubff not built with async support")

# === CONFIGURATION ===
SAVE_TO_S3 = False
RUN_NAME = "visual_run"
SAVE_PATH = f"./runs/{RUN_NAME}"

# === PARAMETERS ===
NUM_PROGRAMS = 128*1024
TAPE_SIZE = 64
PROGRAM_SIZE = 128
SPLIT_AT = [64]
SEED = 0
MUTATION_PROB = 1 << 18
ZERO_INIT = False
EVAL_SELFREP = False
PERMUTE_PROGRAMS = True
FIXED_SHUFFLE = False
SAVE_INTERVAL = 1
CALLBACK_INTERVAL = 1
MAX_EPOCHS = 50  # Reduced for visualization
BIN_WIDTH = 25
LOG_EVERY = 8
CLEANUP_INTERVAL = 128

os.makedirs(SAVE_PATH, exist_ok=True)

print(f"🚀 Starting visual simulation: {RUN_NAME}")
print("📦 Output path:", SAVE_PATH)
print(f"🎨 Showing {PROGRAM_COUNT} programs every {LOG_EVERY} epochs")

language = cubff.GetLanguage("bff_noheads")

def callback(state):
    if state.epoch % LOG_EVERY == 0 or state.epoch == MAX_EPOCHS:
        print(f"\n🎯 Epoch {state.epoch} | Brotli size: {state.brotli_size}")
        
        if SHOW_PROGRAMS:
            print("📊 Sample Programs:")
            print("=" * 80)
            
            # Show a few random programs
            for i in range(PROGRAM_COUNT):
                # Pick a random program from the soup
                start_idx = random.randint(0, len(state.soup) - PROGRAM_SIZE)
                program = state.soup[start_idx:start_idx + PROGRAM_SIZE]
                
                print(f"\n🔬 Program {i+1} (offset {start_idx}):")
                print("-" * 40)
                language.PrintProgram(0, program, SPLIT_AT)
                print("-" * 40)
    
    dat_filename = f"soup_epoch_{state.epoch:05d}.dat"
    dat_path = os.path.join(params.save_to, dat_filename)
    
    with open(dat_path, "wb") as f:
        f.write(state.soup)
    print(f"📂 Saved {dat_filename} locally")

    # Always clean up .dat files in output_dir every CLEANUP_INTERVAL
    if state.epoch % CLEANUP_INTERVAL == 0:
        print(f"🪚 Cleaning up .dat files in {params.save_to}...")
        for f in os.listdir(params.save_to):
            if f.endswith(".dat"):
                try:
                    os.remove(os.path.join(params.save_to, f))
                except Exception as e:
                    print(f"⚠️ Could not delete {f}: {e}")

    if state.epoch >= MAX_EPOCHS:
        metadata = {
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
            "BIN_WIDTH": BIN_WIDTH,
            "ENABLE_ASYNC": ENABLE_ASYNC,
            "OPS_INTERVAL": OPS_INTERVAL
        }
        with open(os.path.join(SAVE_PATH, "run_metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        print("📄 Saved run metadata.")
        return True
    return False

print("🌱 Starting fresh simulation...")

params = cubff.SimulationParams()
params.num_programs = NUM_PROGRAMS
params.seed = SEED
params.mutation_prob = MUTATION_PROB
params.zero_init = ZERO_INIT
params.eval_selfrep = EVAL_SELFREP
params.permute_programs = PERMUTE_PROGRAMS
params.fixed_shuffle = FIXED_SHUFFLE
params.callback_interval = CALLBACK_INTERVAL
params.save_interval = SAVE_INTERVAL
params.save_to = SAVE_PATH

# Add ops_interval to params if async is enabled
if ENABLE_ASYNC:
    params.callback_ops_interval = OPS_INTERVAL

cubff.ResetColors()
print("▶️ Launching simulation...")
language.RunSimulation(params, None, callback)
print("✅ Simulation complete.")
print(f"📁 Results saved to: {SAVE_PATH}") 