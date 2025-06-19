import os
import random
import csv
from bin import cubff  # Compiled C++ simulation bindings
from bff_grammar_package.grammar_core.io import save_run_metadata
from histogram_tracker import HistogramTracker

# === PARAMETERS ===
NUM_PROGRAMS = 128 * 1024
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
NUM_QC_PROGRAMS = 5
BIN_WIDTH = 25

# === Output paths ===
RUN_NAME = "bin_run"
SAVE_PATH = f"./runs/{RUN_NAME}"
os.makedirs(SAVE_PATH, exist_ok=True)
DEBUG_LOG_DIR = os.path.join(SAVE_PATH, "debug_epoch_logs")
os.makedirs(DEBUG_LOG_DIR, exist_ok=True)

# === Language and Histogram Setup ===
language = cubff.GetLanguage("bff_noheads")
hist_tracker = HistogramTracker(
    save_path=SAVE_PATH,
    enabled=True,
    fps=5,
    batch_size=64,
    prefix=RUN_NAME,
    flush_interval=16
)

# === Cross-epoch tracking ===
previous_soup = None
tracked_p1_indices = None  # Fixed across epochs

def callback(state):
    global previous_soup, tracked_p1_indices

    # Bin current execution steps
    current_bins = [steps // BIN_WIDTH for steps in state.steps_per_prog]

    # Load previous steps if possible
    prev_steps_list = []
    prev_bins = None
    prev_steps_path = os.path.join(SAVE_PATH, f"steps_{state.epoch - 1:04d}.csv")
    if state.epoch > 0 and os.path.exists(prev_steps_path):
        with open(prev_steps_path) as pf:
            reader = csv.DictReader(pf)
            prev_steps_list = [int(row["exec_steps"]) for row in reader]
            prev_bins = [steps // BIN_WIDTH for steps in prev_steps_list]

    # === Bin edges ===
    bin_edge_counts = {}
    if prev_bins:
        for i in range(0, len(state.shuffle_idx), 2):
            p1 = state.shuffle_idx[i]
            p2 = state.shuffle_idx[i + 1] if i + 1 < len(state.shuffle_idx) else None
            parents = [p1, p2] if p2 is not None else [p1]
            children = [p1, p2] if p2 is not None else [p1]
            for parent, child in zip(parents, children):
                src_bin = prev_bins[parent]
                tgt_bin = current_bins[child]
                key = (src_bin, tgt_bin)
                bin_edge_counts[key] = bin_edge_counts.get(key, 0) + 1

    with open(os.path.join(SAVE_PATH, f"bin_edges_{state.epoch:04d}.csv"), "w", newline="") as bf:
        bw = csv.writer(bf)
        bw.writerow(["epoch", "source_bin", "target_bin", "count"])
        for (src_bin, tgt_bin), count in sorted(bin_edge_counts.items()):
            bw.writerow([state.epoch, src_bin, tgt_bin, count])

    # === Node metadata ===
    with open(os.path.join(SAVE_PATH, f"nodes_{state.epoch:04d}.csv"), "w", newline="") as nf:
        nw = csv.writer(nf)
        nw.writerow(["id", "epoch", "exec_time", "bin"])
        for idx, steps in enumerate(state.steps_per_prog):
            nw.writerow([idx, state.epoch, steps, current_bins[idx]])

    # === Raw program edges ===
    with open(os.path.join(SAVE_PATH, f"edges_{state.epoch:04d}.csv"), "w", newline="") as ef:
        ew = csv.writer(ef)
        ew.writerow(["source", "target"])
        for i in range(0, len(state.shuffle_idx), 2):
            p1 = state.shuffle_idx[i]
            p2 = state.shuffle_idx[i + 1] if i + 1 < len(state.shuffle_idx) else None
            ew.writerow([p1, p1])
            if p2 is not None:
                ew.writerow([p2, p1])
                ew.writerow([p1, p2])
                ew.writerow([p2, p2])

    # === QC lineage check ===
    if state.epoch > 0 and previous_soup is not None:
        shuffle_list = list(state.shuffle_idx)

        if tracked_p1_indices is None:
            tracked_p1_indices = random.sample(shuffle_list, NUM_QC_PROGRAMS)

        print(f"\n🧪 QC: Epoch {state.epoch} — Tracking {len(tracked_p1_indices)} fixed P1s")
        for i, p1_idx in enumerate(tracked_p1_indices):
            try:
                pair_idx = shuffle_list.index(p1_idx)
                p2_idx = shuffle_list[pair_idx + 1] if pair_idx + 1 < len(shuffle_list) else None
            except ValueError:
                print(f"P1 index {p1_idx} not found in shuffle list")
                continue

            # Step counts
            steps_p1 = prev_steps_list[p1_idx]
            steps_p2 = prev_steps_list[p2_idx] if p2_idx is not None else None
            steps_c1 = state.steps_per_prog[p1_idx]
            steps_c2 = state.steps_per_prog[p2_idx] if p2_idx is not None else None

            # Tapes
            parent1 = cubff.VectorUint8(previous_soup[p1_idx * TAPE_SIZE:(p1_idx + 1) * TAPE_SIZE])
            child1 = cubff.VectorUint8(state.soup[p1_idx * TAPE_SIZE:(p1_idx + 1) * TAPE_SIZE])
            parent2 = cubff.VectorUint8(previous_soup[p2_idx * TAPE_SIZE:(p2_idx + 1) * TAPE_SIZE]) if p2_idx is not None else None
            child2 = cubff.VectorUint8(state.soup[p2_idx * TAPE_SIZE:(p2_idx + 1) * TAPE_SIZE]) if p2_idx is not None else None

            # Print info
            print(f"\n--- Pair {i} ---")
            print(f"P1 @ {p1_idx} | Steps: {steps_p1}")
            language.PrintProgram(0, parent1, SPLIT_AT)
            if parent2:
                print(f"P2 @ {p2_idx} | Steps: {steps_p2}")
                language.PrintProgram(0, parent2, SPLIT_AT)

            print(f"C1 @ {p1_idx} | Steps: {steps_c1}")
            language.PrintProgram(0, child1, SPLIT_AT)
            print("✅ P1 == C1" if parent1 == child1 else "🔁 P1 ≠ C1")

            if child2:
                print(f"C2 @ {p2_idx} | Steps: {steps_c2}")
                language.PrintProgram(0, child2, SPLIT_AT)
                print("✅ P2 == C2" if parent2 == child2 else "🔁 P2 ≠ C2")

    # === Save exec steps ===
    with open(os.path.join(SAVE_PATH, f"steps_{state.epoch:04d}.csv"), "w", newline="") as sf:
        sw = csv.writer(sf)
        sw.writerow(["program_idx", "exec_steps"])
        for idx, steps in enumerate(state.steps_per_prog):
            sw.writerow([idx, steps])

    # === Cache soup for next epoch ===
    previous_soup = list(state.soup)

    # === Stop condition ===
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
            "BIN_WIDTH": BIN_WIDTH
        })
        return True

    return False

# === Start Simulation ===
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

