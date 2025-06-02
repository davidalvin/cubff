# build_grammar.py

import argparse
import os
import json
from collections import Counter
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences

# Phrase is valid if:
# - It does not start or end with "∅"
# - It’s not fully made from existing rules
def is_valid_phrase(phrase, existing_rules):
    if phrase[0] == "∅" or phrase[-1] == "∅":
        return False
    if all(tok in existing_rules for tok in phrase):
        return False
    return True

# Count all symbolic phrases between min_len and max_len in each sequence
def mine_phrases(sequences, min_len, max_len):
    phrases = Counter()
    for i, seq in enumerate(sequences):
        if i % 1000 == 0 and i > 0:
            print(f"⛏️  Mining sequence {i}/{len(sequences)}")
        for j in range(len(seq)):
            for ln in range(min_len, max_len + 1):
                if j + ln <= len(seq):
                    phrase = tuple(seq[j:j+ln])
                    phrases[phrase] += 1
    return phrases

# Rewrite a sequence using greedy left-to-right rule matching
def rewrite_sequence(seq, sorted_rules):
    i = 0
    out = []
    while i < len(seq):
        matched = False
        for sym, rhs in sorted_rules:
            ln = len(rhs)
            if seq[i:i+ln] == rhs:
                out.append(sym)
                i += ln
                matched = True
                break
        if not matched:
            out.append(seq[i])
            i += 1
    return out

# Fully expand a rule by recursively replacing symbols with their definitions
def fully_expand(rhs, grammar):
    result = []
    for tok in rhs:
        if tok in grammar:
            result.extend(fully_expand(grammar[tok], grammar))
        else:
            result.append(tok)
    return result

# Load the most recent grammar from a prior epoch, for continuity
def load_previous_grammar(output_dir, current_epoch, step):
    prev_epoch = current_epoch - step
    if prev_epoch < 0:
        return {}, 0
    path = os.path.join(output_dir, f"grammar_{prev_epoch:04}.json")
    if not os.path.exists(path):
        return {}, 0
    with open(path) as f:
        grammar = json.load(f)["rules"]
    rule_ids = [int(k[1:]) for k in grammar.keys() if k.startswith("G")]
    max_id = max(rule_ids) + 1 if rule_ids else 0
    return grammar, max_id

def main():
    parser = argparse.ArgumentParser(description="Build grammar from soup")
    parser.add_argument("--start", type=int)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--step", type=int)
    parser.add_argument("--minfreq", type=int, default=100)
    parser.add_argument("--minlen", type=int, default=2)
    parser.add_argument("--maxlen", type=int, default=8)
    parser.add_argument("--input-dir", type=str, required=True)
    parser.add_argument("--output-dir", type=str, required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    for epoch in range(args.start, args.stop + 1, args.step):
        grammar_path = os.path.join(args.output_dir, f"grammar_{epoch:04}.json")
        if os.path.exists(grammar_path):
            print(f"✅ Grammar already exists for epoch {epoch}, skipping")
            continue

        # Load previous grammar and get the next available rule ID
        grammar, rule_id = load_previous_grammar(args.output_dir, epoch, args.step)
        initial_rule_id = rule_id

        # Load and preprocess soup
        path = os.path.join(args.input_dir, f"{epoch:010}.dat")
        if not os.path.exists(path):
            print(f"⚠️ Skipping missing file: {path}")
            continue

        print(f"\n📂 Epoch {epoch}: Loading soup from {path}")
        soup = load_soup(path)
        print(f"📦 Loaded {len(soup)} programs from soup")

        sequences = to_symbol_sequences(soup, normalize_noops=True)
        print(f"🔠 Converted to {len(sequences)} symbol sequences")

        # Rewrite programs with existing grammar
        sorted_rules = sorted(grammar.items(), key=lambda kv: -len(kv[1]))
        rewritten_sequences = []
        for idx, seq in enumerate(sequences):
            if idx % 1000 == 0 and idx > 0:
                print(f"🔁 Rewriting sequence {idx}/{len(sequences)}")
            rewritten_sequences.append(rewrite_sequence(seq, sorted_rules))
        print("✅ All sequences rewritten")

        # Mine frequent phrases in rewritten code
        print("📊 Mining phrases...")
        phrases = mine_phrases(rewritten_sequences, args.minlen, args.maxlen)
        print(f"🔍 Found {len(phrases)} raw phrases; filtering for valid candidates...")

        candidates = [
            phrase for phrase, count in phrases.items()
            if count >= args.minfreq and is_valid_phrase(phrase, grammar)
        ]
        print(f"🎯 {len(candidates)} phrases passed filtering (minfreq={args.minfreq})")

        # Add new rules
        for phrase in candidates:
            rule_name = f"G{rule_id}"
            grammar[rule_name] = list(phrase)
            expanded = fully_expand(list(phrase), grammar)
            print(f"➕ {rule_name} := {' '.join(phrase)}   ⟶   {' '.join(expanded)}")
            rule_id += 1

        print(f"🧠 Added {rule_id - initial_rule_id} new rules this epoch")

        # Save updated grammar
        with open(grammar_path, "w") as f:
            json.dump({"rules": grammar}, f)
        print(f"📀 Saved grammar with {len(grammar)} total rules to {grammar_path}")

if __name__ == "__main__":
    main()
