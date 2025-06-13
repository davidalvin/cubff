#!/bin/bash

# === Config ===
RUN_NAME="20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED"
RUNS_DIR="./runs"
PY_SCRIPT="cubff_run.py"

# === Run the simulation ===
echo "🚀 Running simulation: $PY_SCRIPT"
python "$PY_SCRIPT"

# === Paths ===
GIF_DIR="$RUNS_DIR/$RUN_NAME"
OUTPUT_GIF="$GIF_DIR/${RUN_NAME}_full.gif"
HISTOGRAM_CSV="$GIF_DIR/histogram_data.csv"

# === Stitch batch GIFs ===
echo "🧵 Stitching batch GIFs into: $OUTPUT_GIF"
GIFS=$(ls "$GIF_DIR"/${RUN_NAME}_batch*.gif 2>/dev/null | sort)

if [ -z "$GIFS" ]; then
    echo "⚠️  No batch GIFs found in $GIF_DIR"
    exit 1
fi

gifsicle --loop --delay=5 $GIFS > "$OUTPUT_GIF"
echo "✅ Successfully stitched all batches into: $OUTPUT_GIF"

# === Report saved histogram CSV ===
if [ -f "$HISTOGRAM_CSV" ]; then
    echo "📊 Histogram CSV saved at: $HISTOGRAM_CSV"
else
    echo "⚠️  Histogram CSV not found!"
fi
