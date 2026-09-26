"""One math-span mask for every helper that asks "is this position math?".

Every earlier implementation answered that question with `$` parity, which
is wrong for `$$…$$` (two `$` per delimiter), for `\\$` currency, and for a
`$5 and $` that no renderer treats as a span. It was also O(n) per query,
which made whole passes O(n²) on long inputs. This module computes the mask
once per call from `segment`, the tokenizer the renderers use, so what the
sanitiser believes is math is exactly what will be typeset.
"""

from __future__ import annotations

from .segment import segment


def math_mask(text: str) -> list[bool]:
    """``mask[i]`` is True when ``text[i]`` lies inside a closed math span
    (delimiters included). One entry per code point, plus a trailing False
    so ``mask[len(text)]`` is safe."""
    mask = [False] * (len(text) + 1)
    pos = 0
    for seg in segment(text):
        length = len(seg["raw"])
        if seg["kind"] == "math":
            for k in range(pos, pos + length):
                mask[k] = True
        pos += length
    return mask


def math_ranges(text: str) -> list[tuple[int, int, bool]]:
    """``(start, end, display)`` of every closed math span, delimiters
    included, in order."""
    out: list[tuple[int, int, bool]] = []
    pos = 0
    for seg in segment(text):
        length = len(seg["raw"])
        if seg["kind"] == "math":
            out.append((pos, pos + length, seg["display"]))
        pos += length
    return out
