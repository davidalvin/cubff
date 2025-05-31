### === bff_grammar_package/scripts/build_grammar.py ===
import os
import json
import argparse
from collections import OrderedDict
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences
from bff_grammar_package.grammar_core.mining import mine_phrases, build_recursive_grammar

def build_grammar(args):
    os.makedirs(args.output_dir, exist_ok=True)
    existing_grammar = OrderedDict()
    next_id = 1

    for epoch in range(args.start, args.stop, args.step):
        path = os.path.join(args.input_dir, f"{epoch:010}.dat")
        if not os.path.exists(path):
            print(f"⚠️ Missing epoch {epoch}: {path}")
            continue

        print(f"\n📂 Epoch {epoch}: Loading soup from {path}")
        raw = load_soup(path)

        print(f"🔍 Converting to symbol sequences...")
        seqs = to_symbol_sequences(raw, normalize_noops=True)

        print(f"📈 Mining phrases...")
        phrases = mine_phrases(seqs, min_len=args.minlen, max_len=args.maxlen)

        print(f"🧠 Building grammar (current size: {len(existing_grammar)})...")
        new_grammar, next_id = build_recursive_grammar(
            phrases,
            existing_grammar,
            min_freq=args.minfreq,
            start_id=next_id
        )
        existing_grammar.update(new_grammar)

        save_path = os.path.join(args.output_dir, f"grammar_{epoch:04}.json")
        with open(save_path, "w") as f:
            json.dump({"rules": existing_grammar, "next_id": next_id}, f)
        print(f"💾 Saved grammar with {len(existing_grammar)} rules to {save_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=30)
    parser.add_argument("--stop", type=int, default=91)
    parser.add_argument("--step", type=int, default=30)
    parser.add_argument("--minfreq", type=int, default=500)
    parser.add_argument("--minlen", type=int, default=2)
    parser.add_argument("--maxlen", type=int, default=8)
    parser.add_argument("--input-dir", default="runs/test_grammar_100")
    parser.add_argument("--output-dir", default="bff_grammar_package/output/grammars")
    args = parser.parse_args()
    build_grammar(args)
