# cubff

cubff is a C++/CUDA simulation engine with optional Python bindings via pybind11.

This project supports both CUDA and non-CUDA builds and is compatible with Python 3.11+ through pyenv.

## Requirements

- C++17-compatible compiler (e.g. g++)
- pyenv
- pyenv-virtualenv
- Brotli development libraries (libbrotlienc, libbrotlicommon)
- Python 3.11.8 via pyenv

## Setup

1. Clone and enter the repo

2. Set up Python environment

    # First install pyenv and pyenv-virtualenv if you haven't
    source env.sh             # Initializes pyenv and activates virtualenv
    pyenv install 3.11.8      # if not already installed
    pyenv virtualenv 3.11.8 cubff-env
    pyenv shell cubff-env
    pip install -r requirements.txt

3. Build the project

    # CPU only (no CUDA)
    make PYTHON=1 CUDA=0

    # With CUDA
    make PYTHON=1 CUDA=1

## Usage

- Executable (C++ only): bin/main
- Python module: bin/cubff<suffix>.so

Python example:

    import cubff
    # use SimulationState and other bindings here

## Cleaning up

    make clean

## Files and Structure

main.cc         - C++ entry point (standalone sim)
cubff_py.cc     - Python bindings via pybind11
common.cc/h     - Shared simulation logic
bff_noheads.cc  - Custom component logic
Makefile        - Build system
requirements.txt- Python dependencies
.python-version - pyenv virtualenv selector
env.sh          - Pyenv bootstrap script

## Notes

- Uses pybind11 2.13+ for Python integration
- Makefile auto-detects platform and GPU availability
- C++17 is required


