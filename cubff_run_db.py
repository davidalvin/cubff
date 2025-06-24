import os
from bin import cubff  # Compiled C++ simulation bindings
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
MAX_EPOCHS = 128
BIN_WIDTH = 25

# === NODE FORMAT OPTIONS ===
LARGE_RUN = False
SAVE_FORMAT = "pretty" if LARGE_RUN else "both"

# === OUTPUT SETUP ===
RUN_NAME = "db_run"
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)

print(f"🚀 Starting simulation: {RUN_NAME}")
print(f"📁 Output path: {SAVE_PATH}")
print(f"🧪 Max epochs: {MAX_EPOCHS}, Bin width: {BIN_WIDTH}, Save interval: {SAVE_INTERVAL}")

# Optional: Initialize visual histogram tracker
language = cubff.GetLanguage("bff_noheads")
hist_tracker = HistogramTracker(
    save_path=SAVE_PATH,
    enabled=True,
    fps=5,
    batch_size=64,
    prefix=RUN_NAME,
    flush_interval=16
)

# === MAIN CALLBACK FUNCTION ===
def callback(state):
    print(f"📦 Epoch {state.epoch}: Saving node table...")
    write_node_table(
        epoch=state.epoch,
        soup=bytes(state.soup),
        exec_steps=state.steps_per_prog,
        save_path=SAVE_PATH,
        tape_size=TAPE_SIZE,
        save_format=SAVE_FORMAT
    )

    if state.epoch > 0:
        print(f"🔗 Epoch {state.epoch}: Appending edges...")
        append_edges(
            epoch=state.epoch,
            shuffle_idx=list(state.shuffle_idx),
            save_path=SAVE_PATH
        )

    if state.epoch >= MAX_EPOCHS:
        print(f"✅ Final epoch reached: Writing epoch table and metadata...")
        write_epoch_table(SAVE_PATH, MAX_EPOCHS)
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
            "BIN_WIDTH": BIN_WIDTH
        })
        return True

    return False

# === RUN SIMULATION ===
print("🧬 Initializing simulation parameters...")
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

cubff.ResetColors()
print("▶️ Launching simulation...\n")
language.RunSimulation(params, None, callback)

# === POST-RUN QUALITY CHECKS ===
print("\n📊 Post-run edge derivation...")

print("🧾 Writing step-based edges...")
write_step_edges(SAVE_PATH)

print("📊 Writing binned step-based edges...")
write_binned_step_edges(SAVE_PATH, bin_size=BIN_WIDTH)

print("📈 Writing Gephi edge weights...")
write_gephi_weighted_edges_from_binned_steps(SAVE_PATH, bin_size=BIN_WIDTH)

print("🧩 Writing Gephi node labels...")
write_gephi_nodes_from_bins(SAVE_PATH, bin_size=BIN_WIDTH)

# === VISUALIZATION ===
print("\n🖼️  Generating lineage visualization...")
plot_epoch_lineage_graph(SAVE_PATH, MAX_EPOCHS, BIN_WIDTH)

print("\n✅ Simulation and processing complete.")



# === POST-RUN QUALITY CHECKS ===
# check_node_vs_dat_size(epoch=10, save_path=SAVE_PATH)
# inspect_tape(epoch=10, tape_idx=0, save_path=SAVE_PATH)
# check_tape_matches(epoch=10, save_path=SAVE_PATH)
# check_children_steps_match(epoch=10, save_path=SAVE_PATH)
# trace_tape_interactive(start_epoch=1, start_idx=4, save_path=SAVE_PATH)


# === QC BIN TRACE ===
# validate_step_trace_interactive(
#     start_epoch=1,
#     start_idx=4,
#     save_path=SAVE_PATH,
#     bin_size=BIN_WIDTH
# )