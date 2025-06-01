# bff_grammar_package/scripts/print_expanded_rules.py

import os
import json
import argparse

def load_grammar(grammar_dir, target_epoch, step):
    # Find nearest grammar <= target_epoch
    while target_epoch >= 0:
        path = os.path.join(grammar_dir, f"grammar_{target_epoch:04}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)["rules"]
        target_epoch -= step
    return {}

def fully_expand(rhs, grammar):
    result = []
    for tok in rhs:
        if tok in grammar:
            result.extend(fully_expand(grammar[tok], grammar))
        else:
            result.append(tok)
    return result

def main():
    parser = argparse.ArgumentParser(description="Print grammar rules, expansions, and usage at a given epoch")
    parser.add_argument("--epoch", type=int, required=True, help="Target epoch to inspect")
    parser.add_argument("--grammar-dir", type=str, required=True)
    parser.add_argument("--usage-file", type=str, required=True)
    parser.add_argument("--step", type=int, default=256, help="Grammar epoch step")
    parser.add_argument("--top", type=int, default=None, help="Only show top N most-used rules")
    args = parser.parse_args()

    print(f"🔍 Loading grammar for epoch {args.epoch}...")
    grammar = load_grammar(args.grammar_dir, args.epoch, args.step)
    print(f"✅ Loaded {len(grammar)} rules")

    print(f"\n📊 Loading rule usage from {args.usage_file}...")
    with open(args.usage_file) as f:
        usage_data = json.load(f)
    usage = usage_data.get(str(args.epoch), {})
    print(f"✅ Found usage data for {len(usage)} rules at epoch {args.epoch}")

    # Pair rule name with count and sort
    sorted_rules = sorted(grammar.items(), key=lambda item: usage.get(item[0], 0), reverse=True)
    if args.top is not None:
        sorted_rules = sorted_rules[:args.top]
        print(f"\n📈 Showing top {args.top} rules by usage:\n")
    else:
        print("\n📄 Rule Summary:\n")

    for rule_name, rhs in sorted_rules:
        expanded = fully_expand(rhs, grammar)
        count = usage.get(rule_name, 0)
        print(f"{rule_name} := {' '.join(rhs)}   ⟶   {' '.join(expanded)}   [freq={count}]")

if __name__ == "__main__":
    main()
