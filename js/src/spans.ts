/**
 * One math-span mask for every helper that asks "is this position math?".
 *
 * `$` parity is wrong for `$$…$$`, for `\$` currency and for a `$5 and $`
 * that no renderer treats as a span, and it is O(n) per query. This module
 * computes the answer once per call from `segment`, the tokenizer the
 * renderers use, so what the sanitiser believes is math is exactly what
 * will be typeset. Port of python/pupiltree_latex/spans.py.
 */

import { segment } from "./segment.js";

/**
 * `mask[i]` is true when `text[i]` lies inside a closed math span
 * (delimiters included). One entry per code unit, plus a trailing false so
 * `mask[text.length]` is safe.
 */
export function mathMask(text: string): boolean[] {
  const mask: boolean[] = new Array<boolean>(text.length + 1).fill(false);
  let pos = 0;
  for (const seg of segment(text)) {
    const length = seg.raw.length;
    if (seg.kind === "math") {
      for (let k = pos; k < pos + length; k++) mask[k] = true;
    }
    pos += length;
  }
  return mask;
}

export interface MathRange {
  start: number;
  end: number;
  display: boolean;
}

/** `[start, end)` of every closed math span, delimiters included, in order. */
export function mathRanges(text: string): MathRange[] {
  const out: MathRange[] = [];
  let pos = 0;
  for (const seg of segment(text)) {
    const length = seg.raw.length;
    if (seg.kind === "math")
      out.push({ start: pos, end: pos + length, display: seg.display });
    pos += length;
  }
  return out;
}

/** Width of the delimiter on each side of a raw math span (`$$`, `\[`, `\(` → 2; `$` → 1). */
export function delimiterWidth(raw: string): number {
  return raw.startsWith("$$") || raw.startsWith("\\") ? 2 : 1;
}
