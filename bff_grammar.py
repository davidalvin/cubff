#!/usr/bin/env python
# === BFF Recursive Grammar Analysis (v5) ====================================
#  ▸ Only change from v4: every grammar rule must **start and end with an op**.
#    No-ops (∅) may appear inside but never at the boundaries.
#
#    – A single constant `NOOP_SYMBOL` defines the glyph.
#    – Helper `rhs_is_ok()` checks the boundary condition.
#    – The condition is enforced:
#        • while harvesting candidate phrases
#        • when creating a brand-new rule
#        • when replacing an existing rule during the recompression sweep
#
# ---------------------------------------------------------------------------

import struct
from collections import Counter, OrderedDict
from pathlib import Path
from typing import List, Tuple, Dict, Iterable, Set

# ----------------------------------------------------------------------------
# 0)  Global constants
# ----------------------------------------------------------------------------
NOOP_SYMBOL = '∅'                      # the canonical “non-operation” glyph
TAPE_SIZE   = 64                       # bytes per snapshot-program

BFF_COMMANDS = {                       # recognised BrainF*** opcodes
    0x00: '0', 0x5b: '[', 0x5d: ']', 0x2b: '+', 0x2d: '-',
    0x2e: '.', 0x2c: ',', 0x3c: '<', 0x3e: '>', 0x7b: '{', 0x7d: '}'
}

# ----------------------------------------------------------------------------
# 1)  I/O helpers – load a *.dat* soup and convert to symbol sequences
# ----------------------------------------------------------------------------
def load_soup(path: str, max_programs: int | None = None) -> bytes:
    """Return *raw bytes* for at most *max_programs* BFF programs."""
    with open(path, "rb") as f:
        header = f.read(24)                        # three 8-byte unsigned ints
        _, n_programs, _ = struct.unpack('<QQQ', header)
        n_read = min(max_programs or n_programs, n_programs)
        blob = f.read(n_read * TAPE_SIZE)
    print(f"Loaded {n_read} programs from {path}")
    return blob


def to_symbol_sequences(raw: bytes, normalize_noops: bool = False) -> List[List[str]]:
    """Split the raw byte blob into a list of **symbol** lists."""
    programs = []
    for i in range(0, len(raw), TAPE_SIZE):
        chunk = raw[i:i + TAPE_SIZE]
        syms = [
            BFF_COMMANDS.get(b, NOOP_SYMBOL if normalize_noops else chr(0x100 + b))
            for b in chunk
        ]
        programs.append(syms)
    return programs

# ----------------------------------------------------------------------------
# 2)  Mining frequent phrases (k-grams)
# ----------------------------------------------------------------------------
def mine_phrases(programs: List[List[str]], *,
                 min_len: int = 2, max_len: int = 12) -> Counter[Tuple[str, ...]]:
    """Return *all* substrings with frequency counts."""
    freq: Counter[Tuple[str, ...]] = Counter()
    for prog in programs:
        for k in range(min_len, max_len + 1):
            for i in range(len(prog) - k + 1):
                freq[tuple(prog[i:i + k])] += 1
    print(f"Extracted {len(freq)} unique phrases")
    return freq

# ----------------------------------------------------------------------------
# 3)  Grammar utilities
# ----------------------------------------------------------------------------
def rhs_is_ok(rhs: List[str]) -> bool:
    """True iff RHS starts and ends with a *real* op (never ∅)."""
    return rhs and rhs[0] != NOOP_SYMBOL and rhs[-1] != NOOP_SYMBOL


# ----------------------------------------------------------------------------
# 4)  Build a **recursive** grammar (v5)
# ----------------------------------------------------------------------------
from collections import Counter, OrderedDict
from typing import List, Tuple, Dict, Set

# ----------------------------------------------------------------------------
# 4)  Build a **recursive** grammar (v5) — updated
# ----------------------------------------------------------------------------
def build_recursive_grammar(
    freq: Counter[Tuple[str, ...]],
    *,
    min_freq: int = 20,
    start_id: int = 1
) -> Tuple[OrderedDict[str, List[str]], int]:
    """Return an *OrderedDict* of non-terminal → RHS (list of symbols), and next available ID."""
    
    grammar: OrderedDict[str, List[str]] = OrderedDict()
    canonical_to_sym: Dict[Tuple[str, ...], str] = {}
    next_id = start_id

    # ––– helper: fixed-point compression with *existing* rules –––
    def compress(seq: List[str], forbid: Set[str] | None = None) -> List[str]:
        forbid = forbid or set()
        if not grammar:
            return seq.copy()
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

    # ––– 4·1  Candidate phrase list – only ones that satisfy boundary rule *after compression* –––
    phrases = []
    for p, c in freq.items():
        if c >= min_freq:
            raw_rhs = list(p)
            rhs = compress(raw_rhs)
            if rhs_is_ok(rhs):
                phrases.append((tuple(rhs), c))
    phrases.sort(key=lambda pc: (len(pc[0]), -pc[1]))  # short → long, common first

    # ––– 4·2  Main loop –––
    for phrase, _ in phrases:
        raw_rhs = list(phrase)
        rhs = compress(raw_rhs)
        if not rhs_is_ok(rhs):
            continue
        canon = tuple(rhs)
        if canon in canonical_to_sym:
            continue

        # Avoid creating a rule that would be self-referential
        sym = f"G{next_id}"
        if sym in rhs:
            continue  # skip self-referencing rule

        grammar[sym] = rhs
        canonical_to_sym[canon] = sym
        next_id += 1
        print(f"Defined {sym} := {' '.join(rhs)}")

        # ––– 4·3  Re-compress *all previous* rules once –––
        for other_sym, other_rhs in list(grammar.items()):
            if other_sym == sym:
                continue
            new_rhs = compress(other_rhs, forbid={other_sym})
            if len(new_rhs) < len(other_rhs) and rhs_is_ok(new_rhs):
                grammar[other_sym] = new_rhs
                canonical_to_sym[tuple(new_rhs)] = other_sym

    return grammar, next_id

# ----------------------------------------------------------------------------
# 5)  Rewrite every program using the new grammar
# ----------------------------------------------------------------------------
def rewrite_with_grammar(programs: List[List[str]],
                         grammar: OrderedDict[str, List[str]]) -> List[List[str]]:
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
        print(f"Rewrote Program {pid:04d}: {' '.join(out)}")
        rewritten.append(out)
    return rewritten

# ----------------------------------------------------------------------------
# 6)  Pretty printers
# ----------------------------------------------------------------------------
def expand_rhs(rhs: List[str], grammar: Dict[str, List[str]]) -> List[str]:
    """Recursively expand a grammar RHS."""
    result: List[str] = []
    for token in rhs:
        if token in grammar:
            result.extend(expand_rhs(grammar[token], grammar))
        else:
            result.append(token)
    return result


def print_grammar(grammar: OrderedDict[str, List[str]]):
    print("\nGrammar Rules (recursive + expanded):")
    for sym, rhs in grammar.items():
        expanded = expand_rhs(rhs, grammar)
        print(f"{sym} := {' '.join(rhs):<30} | expanded: {' '.join(expanded)}")


def print_programs(programs: List[List[str]], grammar: Dict[str, List[str]]):
    print("\nPrograms (rewritten + expanded):")
    for i, prog in enumerate(programs):
        expanded = expand_rhs(prog, grammar)
        print(f"Program {i:04d}: {' '.join(prog)}")
        print(f"Expanded     : {' '.join(expanded)}\n")

# ----------------------------------------------------------------------------
# 7)  CLI entry point
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# 7)  CLI entry point
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mine a recursive grammar from a BFF soup")
    parser.add_argument("path", nargs="?",
                        default="runs/test_kgram_stats/0000002560.dat",
                        help="*.dat* soup file")
    parser.add_argument("--max", type=int, default=100,
                        help="max programs to read")
    parser.add_argument("--minfreq", type=int, default=25,
                        help="min phrase frequency")
    parser.add_argument("--normalize-noops", action="store_true",
                        help="Replace all non-opcode bytes with a single ∅ glyph")
    parser.add_argument("--maxpasses", type=int, default=10,
                        help="Maximum number of grammar refinement passes")
    args = parser.parse_args()

    # ––– Pass 0: load soup and extract initial sequences –––
    RAW = load_soup(args.path, max_programs=args.max)
    SEQS = to_symbol_sequences(RAW, normalize_noops=args.normalize_noops)

    # ––– Pass 1: mine from raw symbol sequences –––
    print("\n[Pass 1] Mining phrases on raw symbol sequences...")
    PHRASES_1 = mine_phrases(SEQS, min_len=2, max_len=24)
    GRAMMAR, next_id = build_recursive_grammar(PHRASES_1, min_freq=args.minfreq)
    REWRITTEN = rewrite_with_grammar(SEQS, GRAMMAR)

    # ––– Further passes: mine recursively from rewritten sequences –––
    for pass_id in range(2, args.maxpasses + 1):
        print(f"\n[Pass {pass_id}] Mining phrases on rewritten symbol sequences...")
        phrases = mine_phrases(REWRITTEN, min_len=2, max_len=8)
        if not phrases:
            print("No more phrases found.")
            break

        new_grammar, next_id = build_recursive_grammar(phrases, min_freq=args.minfreq, start_id=next_id)
        if not new_grammar:
            print("No new grammar rules added.")
            break

        REWRITTEN = rewrite_with_grammar(REWRITTEN, new_grammar)
        GRAMMAR.update(new_grammar)

    # ––– Final output –––
    print_grammar(GRAMMAR)
    print_programs(REWRITTEN, GRAMMAR)
