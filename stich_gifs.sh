#!/bin/bash

# Folder containing GIF batches
GIF_DIR="./gifs"
OUTPUT="$GIF_DIR/soup_4096_full.gif"

# Find and sort batch files
GIFS=$(ls "$GIF_DIR"/soup_4096_batch*.gif | sort)

# Stitch using gifsicle (streaming-safe)
gifsicle --loop --delay=5 $GIFS > "$OUTPUT"

echo "✅ Successfully stitched all batches into $OUTPUT"


