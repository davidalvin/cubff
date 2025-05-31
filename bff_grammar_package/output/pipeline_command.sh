#!/bin/bash
python3 -m bff_grammar_package.scripts.run_pipeline --soup-path runs/20250531-4096E-128xSoup --output-dir bff_grammar_package/output --start-epoch 0 --stop-epoch 4096 --step-size 256 --max-programs 5000 --min-frequency 100
