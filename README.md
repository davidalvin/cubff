# CuBFF Experimental Fork

This repository is an experimental fork of [CuBFF](https://github.com/paradigms-of-intelligence/cubff), a CUDA-capable simulator for self-modifying soups of small programs that can exhibit the emergence of self-replicators.

The upstream project was used for experiments in the paper **“Life on Computational Substrates: How Self Replicators Arise from Simple Interactions.”** This fork keeps that foundation, while adding exploratory tooling for tracking execution dynamics, exporting program lineages, visualizing evolutionary transitions, and experimenting with asynchronous simulation.

## What this fork adds

This fork is primarily a research and experimentation workspace. In addition to the upstream simulator, it includes work on:

* **Per-program execution-step tracking**
  Simulation callbacks can expose how many evaluation steps each program used during a generation. This makes it easier to study which programs are computationally active, inert, expensive, or replication-relevant.

* **Program lineage and transition export**
  The simulation can export node and edge CSVs describing program-pair interactions over time. These outputs are useful for downstream graph analysis, debugging, and visualizing how program populations change.

* **Weighted transition visualization tools**
  Helper scripts compute edge weights across recent epochs and render frame sequences showing execution-time trajectories and transitions.

* **Debugging utilities for program pairs**
  The fork adds tools for inspecting interacting program pairs, including their indices, step counts, and raw bytes.

* **Experimental asynchronous execution support**
  A draft async scheduler branch adds an operation-based callback interval, async execution helpers, a `slice_id` field, and Python-facing async build flags. This is experimental and intended for testing alternative scheduling models.

* **Local-first run scripts**
  Additional Python scripts support small local runs, visual runs, async-vs-sync tests, and database/export workflows without requiring S3 by default.

## Repository status

`main` is still close to the original CuBFF codebase. Most of the newer work lives in feature branches and pull requests, including:

| Area                        | Branch / PR                                       |
| --------------------------- | ------------------------------------------------- |
| Step tracking               | `execution_steps`, PR #1                          |
| Program lineage export      | `track-transitions`, PR #2                        |
| Async scheduler experiments | `codex/add-asynchronous-execution-support`, PR #3 |
| Kinetic async experiments   | `kinetic-async-sim`                               |
| 2D visualization fixes      | `viz2d-display-num-and-selfrep-fix`               |
| Grammar analysis            | `analyze-grammar`                                 |

## Dependencies

On Debian or Ubuntu:

```bash
sudo apt install build-essential libbrotli-dev
```

Optional dependencies:

```bash
sudo apt install nvidia-cuda-toolkit
```

For Python bindings and analysis scripts, install Python dependencies such as:

```bash
pip install pybind11 pandas matplotlib
```

The repository also includes a Nix flake:

```bash
nix develop
```

## Building

Build the CUDA version:

```bash
make
```

Build the CPU-only version:

```bash
make CUDA=0
```

Build Python bindings:

```bash
make PYTHON=1 CUDA=0
```

Then import the compiled module from Python:

```python
from bin import cubff
```

## Basic usage

Run a standard simulation:

```bash
bin/main --lang bff_noheads
```

Run the Python example:

```bash
python cubff_example.py
```

A minimal Python simulation looks like:

```python
from bin import cubff

language = cubff.GetLanguage("bff_noheads")

params = cubff.SimulationParams()
params.num_programs = 131072
params.seed = 0

def callback(state):
    print(state.epoch, state.brotli_size)
    return state.epoch > 1024

cubff.ResetColors()
language.RunSimulation(params, None, callback)
```

## Analysis and visualization workflow

Feature branches include scripts for exporting and visualizing program evolution.

A typical lineage workflow is:

```bash
python cubff_run.py
python compute_edge_weights.py runs/<run-name> --context 10
python render_frames.py runs/<run-name>
```

This produces:

* `nodes_*.csv` — program nodes with epoch and execution-time data
* `edges_*.csv` — interaction edges between paired programs
* `edges_weighted_*.csv` — edge weights computed over a rolling context window
* `frames/frame_*.png` — rendered visualization frames

## Experimental async mode

The async branch adds an experimental scheduler path and Python controls such as:

```bash
python cubff_run_simple.py --enable_async --ops_interval 1000000
```

Async support is still experimental. It is intended for comparing synchronous epoch-based evolution with operation-sliced execution, callback intervals, and scheduling behavior.

## Project layout

```text
.
├── *.cu / *.cc / *.h          # Core C++ / CUDA simulator
├── cubff_py.cc                # Python bindings
├── cubff_example.py           # Minimal Python example
├── cubff_run*.py              # Experimental run scripts
├── compute_edge_weights.py    # Edge weighting utility
├── render_frames.py           # Visualization frame renderer
├── trace_utils.py             # Program-pair debug helpers
├── testdata/                  # Test data
├── flake.nix                  # Nix development environment
└── Makefile                   # Build configuration
```

## Attribution

This repository is a fork of the original CuBFF project by the Paradigms of Intelligence team. The core simulator, language implementations, and original experiment framework come from upstream CuBFF.

This fork adds experimental instrumentation, lineage export, visualization, debugging, and asynchronous-scheduling work on top of that foundation.

## License

Apache-2.0, following the upstream CuBFF license.
