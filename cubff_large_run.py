import os
import random
import argparse
import tempfile
import json
import boto3

from bin import cubff
from bff_grammar_package.grammar_core.io import save_run_metadata

# === CLI ARGUMENTS ===
parser = argparse.ArgumentParser(description="Run BFF simulation and stream .dat files to S3")

parser.add_argument("--run-name", type=str, default="20250531-4096E-128xSoup")
parser.add_argument("--num-programs", type=int, default=128 * 1024)
parser.add_argument("--program-size", type=int, default=128)
parser.add_argument("--max-epochs", type=int, default=4096)
parser.add_argument("--save-interval", type=int, default=1)
parser.add_argument("--callback-interval", type=int, default=1)
parser.add_argument("--mutation-prob", type=int, default=1 << 18)
parser.add_argument("--zero-init", action="store_true", default=False)
parser.add_argument("--eval-selfrep", action="store_true", default=False)
parser.add_argument("--permute-programs", action="store_true", default=True)
parser.add_argument("--fixed-shuffle", action="store_true", default=False)
parser.add_argument("--s3-bucket", type=str, required=True)
parser.add_argument("--s3-prefix", type=str, default="soups/")
parser.add_argument("--num-to-print", type=int, default=10)
parser.add_argument("--log-every", type=int, default=16,
                    help="Print verbose output every N epochs")

args = parser.parse_args()

# === CONFIG ===
RUN_NAME = args.run_name
SPLIT_AT = [64]
SEED = 0

# === S3 SETUP ===
S3_BUCKET = args.s3_bucket
S3_PREFIX = os.path.join(args.s3_prefix, RUN_NAME + "/")
s3 = boto3.client("s3")

# === Save run metadata immediately ===
metadata = {
    "NUM_PROGRAMS": args.num_programs,
    "PROGRAM_SIZE": args.program_size,
    "SPLIT_AT": SPLIT_AT,
    "SEED": SEED,
    "MUTATION_PROB": args.mutation_prob,
    "ZERO_INIT": args.zero_init,
    "EVAL_SELFREP": args.eval_selfrep,
    "PERMUTE_PROGRAMS": args.permute_programs,
    "FIXED_SHUFFLE": args.fixed_shuffle,
    "SAVE_INTERVAL": args.save_interval,
    "CALLBACK_INTERVAL": args.callback_interval,
    "MAX_EPOCHS": args.max_epochs,
    "RUN_NAME": args.run_name
}
with tempfile.NamedTemporaryFile("w", delete=False) as f:
    json.dump(metadata, f, indent=2)
    meta_path = f.name
meta_key = os.path.join(S3_PREFIX, "run_metadata.json")
s3.upload_file(meta_path, S3_BUCKET, meta_key)
os.remove(meta_path)
print(f"📝 Uploaded run metadata → s3://{S3_BUCKET}/{meta_key}")

# === CALLBACK ===
def callback(state):
    should_log = state.epoch % args.log_every == 0 or state.epoch == args.max_epochs
    print(f"Epoch {state.epoch} ✔", end="")

    if should_log:
        print(f" | Brotli size: {state.brotli_size}")
        num_programs = len(state.soup) // args.program_size
        indices = random.sample(range(num_programs), min(args.num_to_print, num_programs))
        for i, idx in enumerate(indices):
            start = idx * args.program_size
            end = start + args.program_size
            program = state.soup[start:end]
            print(f"\n🧬 Program {i} (index {idx}):")
            language.PrintProgram(0, program, SPLIT_AT)
    else:
        print()

    # Upload .dat to S3
    filename = f"{state.epoch:010}.dat"
    s3_key = os.path.join(S3_PREFIX, filename)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(state.soup)
        tmp.flush()
        s3.upload_file(tmp.name, S3_BUCKET, s3_key)
    os.remove(tmp.name)

    if should_log:
        print(f"📤 Uploaded → s3://{S3_BUCKET}/{s3_key}")

    if state.epoch >= args.max_epochs:
        print("\n🧪 Max epochs reached — simulation complete.")
        return True
    return False

# === LANGUAGE + PARAM SETUP ===
language = cubff.GetLanguage("bff_noheads")
params = cubff.SimulationParams()
params.num_programs = args.num_programs
params.seed = SEED
params.mutation_prob = args.mutation_prob
params.zero_init = args.zero_init
params.eval_selfrep = args.eval_selfrep
params.permute_programs = args.permute_programs
params.fixed_shuffle = args.fixed_shuffle
params.callback_interval = args.callback_interval
params.save_to = "/tmp/sim-dump"  # disables local .dat saves
params.save_interval = args.save_interval

# === RUN ===
print(f"\n🔁 Starting BFF simulation: {RUN_NAME}")
print(f"Max epochs: {args.max_epochs}, Log every {args.log_every} epochs")
print(f"Streaming .dat files to s3://{S3_BUCKET}/{S3_PREFIX}\n")

cubff.ResetColors()
language.RunSimulation(params, None, callback)

print("\n✅ Simulation complete.")
