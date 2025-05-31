#!/usr/bin/env python

import struct
from collections import Counter, OrderedDict
from typing import List, Tuple, Dict, Set
import plotly.graph_objects as go
# ============================================================================
# Configuration Constants
# ============================================================================

NOOP_SYMBOL = '∅'        # Used to represent non-operation bytes
TAPE_SIZE = 64           # Size of each program in bytes (could be made configurable)

# Mapping of recognized BFF (Brainfuck-Family) opcodes
BFF_COMMANDS = {
    0x00: '0', 0x5b: '[', 0x5d: ']', 0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',', 0x3c: '<', 0x3e: '>', 0x7b: '{', 0x7d: '}'
}

# ============================================================================
# Helpers for Loading and Decoding BFF Binary Soups
# ============================================================================

def load_soup(path: str, max_programs: int | None = None) -> bytes:
    """Reads a binary soup file and returns raw program bytes."""
    with open(path, "rb") as f:
        header = f.read(24)  # 3 unsigned 64-bit values
        _, n_programs, _ = struct.unpack('<QQQ', header)
        n_read = min(max_programs or n_programs, n_programs)
        blob = f.read(n_read * TAPE_SIZE)
    print(f"Loaded {n_read} programs from {path}")
    return blob

def to_symbol_sequences(raw: bytes, normalize_noops: bool = False) -> List[List[str]]:
    """Converts raw byte programs into symbolic opcode sequences."""
    programs = []
    for i in range(0, len(raw), TAPE_SIZE):
        chunk = raw[i:i + TAPE_SIZE]
        syms = [
            BFF_COMMANDS.get(b, NOOP_SYMBOL if normalize_noops else chr(0x100 + b))
            for b in chunk
        ]
        programs.append(syms)
    return programs

# ============================================================================
# Phrase Mining
# ============================================================================

def mine_phrases(programs: List[List[str]], *,
                 min_len: int = 2, max_len: int = 12) -> Counter[Tuple[str, ...]]:
    """Extracts all substrings of given lengths with frequency counts."""
    freq: Counter[Tuple[str, ...]] = Counter()
    for prog in programs:
        for k in range(min_len, max_len + 1):
            for i in range(len(prog) - k + 1):
                freq[tuple(prog[i:i + k])] += 1
    print(f"Extracted {len(freq)} unique phrases")
    return freq

def rhs_is_ok(rhs: List[str]) -> bool:
    """Check that a phrase starts and ends with an actual operation (not ∅)."""
    return rhs and rhs[0] != NOOP_SYMBOL and rhs[-1] != NOOP_SYMBOL

# ============================================================================
# Grammar Compression
# ============================================================================

def compress(seq: List[str],
             grammar: OrderedDict[str, List[str]],
             forbid: Set[str] | None = None) -> List[str]:
    """
    Compress a sequence using known grammar rules.

    Parameters:
        - seq: list of symbols to compress
        - grammar: dict of rules (symbol -> RHS)
        - forbid: optional set of rule names to exclude from compression

    Returns:
        - Compressed version of input sequence
    """
    forbid = forbid or set()
    if not grammar:
        return seq.copy()

    # Sort rules by length (longer rules have higher priority)
    rules = [kv for kv in sorted(grammar.items(), key=lambda kv: -len(kv[1]))
             if kv[0] not in forbid]
    changed = True
    current = seq.copy()

    while changed:
        changed = False
        out: List[str] = []
        i = 0
        while i < len(current):
            for sym, rhs in rules:
                ln = len(rhs)
                if current[i:i + ln] == rhs:
                    out.append(sym)
                    i += ln
                    changed = True
                    break
            else:
                out.append(current[i])
                i += 1
        current = out

    return current

# ============================================================================
# Recursive Grammar Construction
# ============================================================================

def build_recursive_grammar(
    freq: Counter[Tuple[str, ...]],
    existing_grammar: OrderedDict[str, List[str]] = None,
    *,
    min_freq: int = 20,
    start_id: int = 1
) -> Tuple[OrderedDict[str, List[str]], int]:
    """
    Builds a recursive grammar from frequent phrases.

    - Starts with optional existing grammar.
    - Adds only new rules with valid boundaries and no self-references.
    - Applies fixed-point compression and updates existing rules if shorter.

    Returns:
        - grammar: Updated OrderedDict of rules (symbol -> RHS list)
        - next_id: Next available rule ID
    """
    grammar: OrderedDict[str, List[str]] = OrderedDict(existing_grammar or {})
    canonical_to_sym: Dict[Tuple[str, ...], str] = {
        tuple(rhs): sym for sym, rhs in grammar.items()
    }
    next_id = start_id

    print(f"\n📘 Grammar mining: starting with {len(grammar)} existing rules")

    # Filter candidate phrases that are frequent and compress to valid boundaries
    phrases = []
    for p, c in freq.items():
        if c >= min_freq:
            raw_rhs = list(p)
            rhs = compress(raw_rhs, grammar)
            if rhs_is_ok(rhs):
                phrases.append((tuple(rhs), c))

    print(f"✅ {len(phrases)} candidate phrases to consider for new rules")

    # Sort: shorter phrases first, then more frequent
    phrases.sort(key=lambda pc: (len(pc[0]), -pc[1]))

    for phrase, _ in phrases:
        raw_rhs = list(phrase)
        rhs = compress(raw_rhs, grammar)
        if not rhs_is_ok(rhs):
            continue

        canon = tuple(rhs)
        if canon in canonical_to_sym:
            continue

        sym = f"G{next_id}"
        if sym in rhs:
            continue  # prevent self-reference

        # Register new rule
        grammar[sym] = rhs
        canonical_to_sym[canon] = sym
        print(f"➕ Added rule {sym} := {' '.join(rhs)}")
        next_id += 1

        # Re-compress existing rules using the new rule
        for other_sym, other_rhs in list(grammar.items()):
            if other_sym == sym:
                continue
            new_rhs = compress(other_rhs, grammar, forbid={other_sym})
            if len(new_rhs) < len(other_rhs) and rhs_is_ok(new_rhs):
                grammar[other_sym] = new_rhs
                canonical_to_sym[tuple(new_rhs)] = other_sym

    print(f"📦 Grammar now has {len(grammar)} rules\n")
    return grammar, next_id


# ============================================================================
# Program Rewriting and Pretty Printing
# ============================================================================

def rewrite_with_grammar(programs: List[List[str]],
                         grammar: OrderedDict[str, List[str]]) -> List[List[str]]:
    """Rewrites all programs using the current grammar rules."""
    rules = sorted(grammar.items(), key=lambda kv: -len(kv[1]))
    rewritten: List[List[str]] = []

    for pid, prog in enumerate(programs):
        out: List[str] = []
        i = 0
        while i < len(prog):
            for sym, rhs in rules:
                ln = len(rhs)
                if prog[i:i + ln] == rhs:
                    out.append(sym)
                    i += ln
                    break
            else:
                out.append(prog[i])
                i += 1
        rewritten.append(out)
    return rewritten

def expand_rhs(rhs: List[str], grammar: Dict[str, List[str]]) -> List[str]:
    """Expands grammar symbols recursively to their full underlying sequence."""
    result: List[str] = []
    for token in rhs:
        if token in grammar:
            result.extend(expand_rhs(grammar[token], grammar))
        else:
            result.append(token)
    return result

def print_grammar(programs: List[List[str]], grammar: Dict[str, List[str]]):
    """Prints how frequently each grammar rule is used across all programs."""
    usage = Counter()

    for prog in programs:
        for symbol in prog:
            if symbol in grammar:
                usage[symbol] += 1

    print("\nGrammar Rule Usage (sorted by frequency):")
    for sym, count in usage.most_common():
        expanded = expand_rhs([sym], grammar)
        print(f"{sym:5} used {count:5} times  | expands to: {' '.join(expanded)}")


def print_programs(programs: List[List[str]], grammar: Dict[str, List[str]], max_print: int = 20):
    """Prints the compressed and expanded forms of the first N programs."""
    print(f"\nPrograms (first {max_print} shown):")
    for i, prog in enumerate(programs[:max_print]):
        expanded = expand_rhs(prog, grammar)
        print(f"Program {i:04d}: {' '.join(prog)}")
        print(f"Expanded     : {' '.join(expanded)}\n")

# ============================================================================
# Output Visualization
# ============================================================================

def generate_grammar_usage_chart(
    grammar: OrderedDict[str, List[str]],
    programs: List[List[str]],
    output_path: str = "grammar_rule_usage.html"
) -> None:
    """
    Generate an interactive bar chart of grammar rule usage using a single color.
    """
    rule_usage = Counter()

    # Count how often each grammar rule appears in rewritten programs
    for prog in programs:
        for sym in prog:
            if sym in grammar:
                rule_usage[sym] += 1

    # Prepare chart data
    x_labels = []
    y_values = []
    tooltips = []

    for sym, count in rule_usage.most_common():
        x_labels.append(sym)
        y_values.append(count)
        expanded = expand_rhs([sym], grammar)
        rule_body = ' '.join(grammar[sym])
        expanded_str = ' '.join(expanded)

        tooltips.append(
            f"<b>{sym}</b><br>Used: {count} times<br><br>"
            f"<b>Defined as:</b> {rule_body}<br>"
            f"<b>Expands to:</b> {expanded_str}"
        )

    # Plot using a single color
    fig = go.Figure(data=[
        go.Bar(
            x=x_labels,
            y=y_values,
            text=tooltips,
            hoverinfo='text',
            marker=dict(color='steelblue')
        )
    ])

    fig.update_layout(
        title="Grammar Rule Usage Frequency",
        xaxis_title="Grammar Rule",
        yaxis_title="Usage Count",
        hovermode="closest"
    )

    fig.write_html(output_path)
    print(f"Interactive chart saved to {output_path}")



# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mine a recursive grammar from a BFF soup")
    parser.add_argument("path", nargs="?", default="runs/test_kgram_stats/0000002560.dat",
                        help="*.dat* soup file")
    parser.add_argument("--max-programs", type=int, default=100,
                        help="Max programs to read from the soup")
    parser.add_argument("--minfreq", type=int, default=25,
                        help="Minimum frequency to include a phrase as a rule")
    parser.add_argument("--normalize-noops", action="store_true",
                        help="Replace all non-opcode bytes with a single ∅ glyph")
    parser.add_argument("--maxpasses", type=int, default=10,
                        help="Maximum number of grammar refinement passes")
    parser.add_argument("--print-programs", type=int, default=20,
                        help="Number of programs to print (compressed + expanded)")
    parser.add_argument("--maxlen", type=int, default=16,
                        help="Maximum k-gram length to consider during mining")
    parser.add_argument("--minlen", type=int, default=2,
                        help="Minimum k-gram length to consider during mining")
    args = parser.parse_args()

    # Load and preprocess program data
    RAW = load_soup(args.path, max_programs=args.max_programs)
    SEQS = to_symbol_sequences(RAW, normalize_noops=args.normalize_noops)

    # Initialize grammar and start recursive mining loop
    working_set = SEQS
    GRAMMAR = OrderedDict()
    next_id = 1

    for pass_id in range(1, args.maxpasses + 1):
        print(f"\n[Pass {pass_id}] Mining phrases on symbol sequences...")
        phrases = mine_phrases(working_set, min_len=args.minlen, max_len=args.maxlen)
        if not phrases:
            print("No more phrases found.")
            break
        new_grammar, next_id = build_recursive_grammar(phrases, min_freq=args.minfreq, start_id=next_id)
        if not new_grammar:
            print("No new grammar rules added.")
            break
        GRAMMAR.update(new_grammar)
        working_set = rewrite_with_grammar(working_set, new_grammar)

    # Final output: grammar and programs
    print_grammar(working_set, GRAMMAR)
    print_programs(working_set, GRAMMAR, max_print=args.print_programs)

    generate_grammar_usage_chart(GRAMMAR, working_set, output_path="grammar_rule_usage.html")
    