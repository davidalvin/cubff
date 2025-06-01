import argparse
import json
import os

def fully_expand(rhs, grammar, _cache={}):
    expanded = []
    for tok in rhs:
        if tok in grammar:
            # Use cache to avoid repeated work and infinite loops
            if tok not in _cache:
                _cache[tok] = fully_expand(grammar[tok], grammar, _cache)
            expanded.extend(_cache[tok])
        else:
            expanded.append(tok)
    return expanded

def main():
    parser = argparse.ArgumentParser(description="Print fully expanded grammar rules")
    parser.add_argument("--grammar", type=str, required=True, help="Path to grammar_XXXX.json")
    parser.add_argument("--top", type=int, default=None, help="Show only top N longest rules")
    args = parser.parse_args()

    if not os.path.exists(args.grammar):
        print(f"❌ File not found: {args.grammar}")
        return

    with open(args.grammar) as f:
        grammar = json.load(f)["rules"]

    print(f"📘 Loaded {len(grammar)} grammar rules")

    expansions = []
    for name, rhs in grammar.items():
        expanded = fully_expand(rhs, grammar)
        expansions.append((name, rhs, expanded))

    # Sort by length of expansion if requested
    if args.top:
        expansions.sort(key=lambda x: len(x[2]), reverse=True)
        expansions = expansions[:args.top]

    for name, rhs, expanded in expansions:
        print(f"{name} := {' '.join(rhs)}")
        print(f"      ⟶ {' '.join(expanded)}")
        print()

if __name__ == "__main__":
    main()
