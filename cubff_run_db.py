import os
import tempfile
import boto3
import shutil
import glob
from bin import cubff
from bff_grammar_package.grammar_core.io import save_run_metadata
from histogram_tracker import HistogramTracker
from db_helpers import (
    write_node_table,
    append_edges,
    write_epoch_table,
    write_step_edges,
    write_binned_step_edges,
    write_gephi_weighted_edges_from_binned_steps,
    write_gephi_nodes_from_bins,
    plot_epoch_lineage_graph
)
from db_qc import (
    check_node_vs_dat_size,
    inspect_tape,
    check_tape_matches,
    check_children_steps_match,
    trace_tape_interactive,
    validate_step_trace_interactive,
)

# === CONFIGURATION ===
SAVE_TO_S3 = True
RUN_NAME = "db_run_test"
SAVE_PATH = f"./runs/{RUN_NAME}"
S3_BUCKET = "bff-grammar"
S3_PREFIX = f"soup/{RUN_NAME}/"
s3 = boto3.client("s3")

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
MAX_EPOCHS = 4096
BIN_WIDTH = 25
LOG_EVERY = 16

if not SAVE_TO_S3:
    os.makedirs(SAVE_PATH, exist_ok=True)

print(f"🚀 Starting simulation: {RUN_NAME}")
print("📦 Output path:", f"s3://{S3_BUCKET}/{S3_PREFIX}" if SAVE_TO_S3 else SAVE_PATH)

language = cubff.GetLanguage("bff_noheads")

# === HISTOGRAM TRACKER ===
hist_tracker = None
if not SAVE_TO_S3:
    hist_tracker = HistogramTracker(
        save_path=SAVE_PATH,
        enabled=True,
        fps=5,
        batch_size=64,
        prefix=RUN_NAME,
        flush_interval=16
    )

def save_and_upload_csv(fn, *args, s3_key=None, **kwargs):
    if SAVE_TO_S3:
        with tempfile.TemporaryDirectory() as tmpdir:
            fn(*args, save_path=tmpdir, **kwargs)

            written_file = next(
                (f for f in os.listdir(tmpdir) if f.endswith(".csv")), None
            )
            if not written_file:
                raise FileNotFoundError("No CSV file was written by the function.")

            full_file_path = os.path.join(tmpdir, written_file)
            s3.upload_file(full_file_path, S3_BUCKET, s3_key)
    else:
        fn(*args, save_path=SAVE_PATH, **kwargs)

def callback(state):
    if state.epoch % LOG_EVERY == 0 or state.epoch == MAX_EPOCHS:
        print(f"🧬 Epoch {state.epoch} | Brotli size: {state.brotli_size}")

    dat_filename = f"soup_epoch_{state.epoch:05d}.dat"
    if SAVE_TO_S3:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(state.soup)
            tmp.flush()
            s3.upload_file(tmp.name, S3_BUCKET, os.path.join(S3_PREFIX, dat_filename))
        os.remove(tmp.name)
    else:
        with open(os.path.join(SAVE_PATH, dat_filename), "wb") as f:
            f.write(state.soup)

    save_and_upload_csv(
        write_node_table,
        epoch=state.epoch,
        soup=bytes(state.soup),
        exec_steps=state.steps_per_prog,
        tape_size=TAPE_SIZE,
        save_format="none",
        s3_key=os.path.join(S3_PREFIX, f"nodes_epoch_{state.epoch:05d}.csv")
    )

    if state.epoch > 0:
        save_and_upload_csv(
            append_edges,
            epoch=state.epoch,
            shuffle_idx=list(state.shuffle_idx),
            s3_key=os.path.join(S3_PREFIX, f"edges_epoch_{state.epoch:05d}.csv")
        )

    if state.epoch >= MAX_EPOCHS:
        if SAVE_TO_S3:
            save_and_upload_csv(
                write_epoch_table,
                max_epoch=MAX_EPOCHS,
                s3_key=os.path.join(S3_PREFIX, "epoch_table.csv")
            )
        else:
            write_epoch_table(SAVE_PATH, MAX_EPOCHS)

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
            "BIN_WIDTH": BIN_WIDTH
        }
        if SAVE_TO_S3:
            with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
                import json
                json.dump(metadata, tmp, indent=2)
                tmp.flush()
                s3.upload_file(tmp.name, S3_BUCKET, os.path.join(S3_PREFIX, "run_metadata.json"))
            os.remove(tmp.name)
        else:
            save_run_metadata(SAVE_PATH, state, metadata)

        return True

    return False

def download_simulation_outputs(prefix, local_dir):
    response = s3.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    edge_files = []

    for obj in response.get("Contents", []):
        key = obj["Key"]
        filename = os.path.basename(key)
        if filename.endswith(".csv"):
            dest_path = os.path.join(local_dir, filename)
            s3.download_file(S3_BUCKET, key, dest_path)

            if filename.startswith("edges_epoch_"):
                edge_files.append(dest_path)


def combine_edges_files(local_dir):
    edge_files = sorted(
        f for f in os.listdir(local_dir) if f.startswith("edges_epoch_") and f.endswith(".csv")
    )
    combined_path = os.path.join(local_dir, "edges.csv")

    with open(combined_path, "w") as f_out:
        for i, fname in enumerate(edge_files):
            with open(os.path.join(local_dir, fname), "r") as f_in:
                if i > 0:
                    next(f_in)  # skip header except on the first file
                f_out.writelines(f_in)


# === RUN ===
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
temp_output_dir = tempfile.mkdtemp() if SAVE_TO_S3 else SAVE_PATH
params.save_to = temp_output_dir

cubff.ResetColors()
print("▶️ Launching simulation...")
language.RunSimulation(params, None, callback)
print("✅ Simulation complete.")

print("\n📊 Post-run edge derivation...")
if SAVE_TO_S3:
    download_simulation_outputs(S3_PREFIX, temp_output_dir)
    combine_edges_files(temp_output_dir)

    print("🧾 Writing step-based edges...")
    write_step_edges(temp_output_dir)

    print("📊 Writing binned step-based edges...")
    write_binned_step_edges(temp_output_dir, bin_size=BIN_WIDTH)

    print("📈 Writing Gephi weighted edges...")
    write_gephi_weighted_edges_from_binned_steps(temp_output_dir, bin_size=BIN_WIDTH)

    print("🧩 Writing Gephi node labels...")
    write_gephi_nodes_from_bins(temp_output_dir, bin_size=BIN_WIDTH)

    # ✅ Upload post-processing outputs
    for fname in os.listdir(temp_output_dir):
        local_path = os.path.join(temp_output_dir, fname)
        if os.path.isfile(local_path) and fname.endswith(".csv"):
            s3_key = os.path.join(S3_PREFIX, fname)
            s3.upload_file(local_path, S3_BUCKET, s3_key)
            print(f"📤 Uploaded {fname} → s3://{S3_BUCKET}/{s3_key}")

    shutil.rmtree(temp_output_dir, ignore_errors=True)
    print(f"🧹 Cleaned up temp directory: {temp_output_dir}")
else:
    write_step_edges(SAVE_PATH)
    write_binned_step_edges(SAVE_PATH, bin_size=BIN_WIDTH)
    write_gephi_weighted_edges_from_binned_steps(SAVE_PATH, bin_size=BIN_WIDTH)
    write_gephi_nodes_from_bins(SAVE_PATH, bin_size=BIN_WIDTH)

    print("\n🖼️  Generating lineage visualization...")
    plot_epoch_lineage_graph(SAVE_PATH, MAX_EPOCHS, BIN_WIDTH)

    print("\n🔍 Running quality checks...")
    check_node_vs_dat_size(epoch=10, save_path=SAVE_PATH)
    inspect_tape(epoch=10, tape_idx=0, save_path=SAVE_PATH)
    check_tape_matches(epoch=10, save_path=SAVE_PATH)
    check_children_steps_match(epoch=10, save_path=SAVE_PATH)
    trace_tape_interactive(start_epoch=1, start_idx=4, save_path=SAVE_PATH)
    validate_step_trace_interactive(start_epoch=1, start_idx=4, save_path=SAVE_PATH, bin_size=BIN_WIDTH)
