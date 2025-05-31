from typing import List, Dict, Tuple
from collections import Counter, OrderedDict

def rewrite_with_grammar(programs: List[List[str]],
                         grammar: OrderedDict[str, List[str]]) -> List[List[str]]:
    """Rewrites all programs using the current grammar rules."""
    rules = sorted(grammar.items(), key=lambda kv: -len(kv[1]))
    rewritten: List[List[str]] = []

    for prog in programs:
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
