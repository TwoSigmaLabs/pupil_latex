/**
 * Character predicates with Python `str` semantics, so the ports stay
 * faithful where the reference uses `isalpha()`, `isdigit()`, `isspace()`
 * and `strip()` on single characters.
 */

const ALPHA_RE = /\p{L}/u;
// Python `isdigit()` is Unicode decimal digits plus the characters with
// Numeric_Type=Digit that lesson text can carry (super/subscript digits).
const DIGIT_RE = /[\p{Nd}²³¹⁰⁴-⁹₀-₉]/u;
const ALNUM_RE = /[\p{L}\p{N}]/u;
// Python `isspace()`: Unicode White_Space minus U+FEFF, plus the C0
// separators U+001C–U+001F and NEL (U+0085).
const SPACE_RE = /[^\S﻿]|[\x1c-\x1f\x85]/;

export function isAlpha(ch: string): boolean {
  return ch !== "" && ALPHA_RE.test(ch);
}

export function isDigit(ch: string): boolean {
  return ch !== "" && DIGIT_RE.test(ch);
}

export function isAsciiDigit(ch: string): boolean {
  return ch >= "0" && ch <= "9";
}

export function isAlnum(ch: string): boolean {
  return ch !== "" && ALNUM_RE.test(ch);
}

export function isSpace(ch: string): boolean {
  return ch !== "" && SPACE_RE.test(ch);
}

/** Python `str.strip()` (Unicode whitespace, both ends). */
export function pyStrip(s: string): string {
  return pyRstrip(pyLstrip(s));
}

export function pyLstrip(s: string): string {
  let i = 0;
  while (i < s.length && isSpace(s[i])) i++;
  return s.slice(i);
}

export function pyRstrip(s: string): string {
  let j = s.length;
  while (j > 0 && isSpace(s[j - 1])) j--;
  return s.slice(0, j);
}

/** Python `str.lstrip(chars)` with an explicit character set. */
export function lstripChars(s: string, chars: string): string {
  let i = 0;
  while (i < s.length && chars.includes(s[i])) i++;
  return s.slice(i);
}

/** Python `str.rstrip(chars)` with an explicit character set. */
export function rstripChars(s: string, chars: string): string {
  let j = s.length;
  while (j > 0 && chars.includes(s[j - 1])) j--;
  return s.slice(0, j);
}

/**
 * The whole code point starting at UTF-16 index `i` (Python `text[i]` when
 * `i` sits on a character boundary), or "" past the end. The predicates
 * above must see an astral letter/digit (`𝑥`, `𝟙`) whole: a lone surrogate
 * is neither.
 */
export function charAt(s: string, i: number): string {
  if (i < 0 || i >= s.length) return "";
  return String.fromCodePoint(s.codePointAt(i)!);
}

/** Number of code points (Python `len`), for the one-character checks. */
export function codePointLength(s: string): number {
  let n = 0;
  for (const _ of s) n++;
  return n;
}

/** Escape a string for use inside a `RegExp` source (any position). */
export function escapeRegExp(s: string): string {
  return s.replace(/[\\^$.*+?()[\]{}|/-]/g, "\\$&");
}

/** `re.match(pattern, s, pos)`: the match of a sticky regex at exactly `pos`. */
export function matchAt(
  re: RegExp,
  s: string,
  pos: number,
): RegExpExecArray | null {
  re.lastIndex = pos;
  return re.exec(s);
}

/** Python `str.count(sub)` for a non-empty, non-overlapping substring. */
export function countOf(s: string, sub: string): number {
  let n = 0;
  let i = s.indexOf(sub);
  while (i !== -1) {
    n++;
    i = s.indexOf(sub, i + sub.length);
  }
  return n;
}
