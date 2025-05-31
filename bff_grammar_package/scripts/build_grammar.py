import argparse
import os
import json
from collections import Counter
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences


def is_valid_phrase(phrase, existing_rules):
    if any(tok == "∅" for tok in phrase):
        return False
    if all(tok in existing_rules for tok in phrase):
        return False
    return True


def mine_phrases(sequences, min_len, max_len):
    phrases = Counter()
    for seq in sequences:
        for i in range(len(seq)):
            for ln in range(min_len, max_len + 1):
                if i + ln <= len(seq):
                    phrase = tuple(seq[i:i+ln])
                    phrases[phrase] += 1
    return phrases


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

    grammar = {}
    rule_id = 0

    for epoch in range(args.start, args.stop + 1, args.step):
        path = os.path.join(args.input_dir, f"{epoch:010}.dat")
        if not os.path.exists(path):
            print(f"⚠️ Skipping missing file: {path}")
            continue

        print(f"\n📂 Epoch {epoch}: Loading soup from {path}")
        soup = load_soup(path)
        sequences = to_symbol_sequences(soup, normalize_noops=True)

        # Apply existing rules to sequences
        sorted_rules = sorted(grammar.items(), key=lambda kv: -len(kv[1]))
        rewritten_sequences = [rewrite_sequence(seq, sorted_rules) for seq in sequences]

        print("📊 Mining phrases...")
        phrases = mine_phrases(rewritten_sequences, args.minlen, args.maxlen)
        print(f"🧠 Building grammar (current size: {len(grammar)})...")

        candidates = [
            phrase for phrase, count in phrases.items()
            if count >= args.minfreq and is_valid_phrase(phrase, grammar)
        ]

        for phrase in candidates:
            rule_name = f"G{rule_id}"
            grammar[rule_name] = list(phrase)
            print(f"➕ Added rule {rule_name} := {' '.join(phrase)}")
            rule_id += 1

        out_path = os.path.join(args.output_dir, f"grammar_{epoch:04}.json")
        with open(out_path, "w") as f:
            json.dump({"rules": grammar}, f)
        print(f"📀 Saved grammar with {len(grammar)} rules to {out_path}")


if __name__ == "__main__":
    main()
