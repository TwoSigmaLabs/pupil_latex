/**
 * Unicode math character → LaTeX command conversion, homoglyph
 * normalisation, combining-vector conversion and bare-character wrapping.
 * Port of python/pupiltree_latex/unicode_math.py; the tables come from
 * tables.g.ts and math spans from spans.ts.
 */

import {
  charAt,
  escapeRegExp,
  isAlnum,
  isAlpha,
  isDigit,
  matchAt,
  pyLstrip,
} from "./chars.js";
import { codePointBefore } from "./lookbehind.js";
import { delimiterWidth, mathMask, mathRanges } from "./spans.js";
import {
  GREEK_MATH_LETTERS,
  GREEK_UNIT_SYMBOLS,
  HOMOGLYPHS,
  JOINING_CHARS,
  JOINING_COMMANDS,
  UNICODE_MATH,
  WRAPPABLE_BARE_CHARS,
} from "./tables.g.js";

export {
  GREEK_MATH_LETTERS,
  GREEK_UNIT_SYMBOLS,
  HOMOGLYPHS,
  JOINING_CHARS,
  JOINING_COMMANDS,
  UNICODE_MATH,
  WRAPPABLE_BARE_CHARS,
};

const HOMOGLYPH_RE = new RegExp(
  "[" + escapeRegExp(Object.keys(HOMOGLYPHS).join("")) + "]",
);

/**
 * Replace visually identical Unicode code points with their canonical form
 * (`µ` → `μ`). Idempotent; no-op when no targets are present.
 */
export function normalizeHomoglyphs(text: string): string {
  if (typeof text !== "string" || !text) return text;
  if (!HOMOGLYPH_RE.test(text)) return text;
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    out += Object.prototype.hasOwnProperty.call(HOMOGLYPHS, ch)
      ? HOMOGLYPHS[ch]
      : ch;
  }
  return out;
}

// Combining vector arrow (U+20D7) is the Unicode way to write `a⃗`.
const COMBINING_VEC_RE = /([A-Za-z])⃗/g;

/**
 * Convert `X⃗` (letter + U+20D7) to `\vec{X}`. With `wrapBare` (default),
 * occurrences outside math spans are wrapped in `$…$`.
 */
export function convertCombiningVec(text: string, wrapBare = true): string {
  if (typeof text !== "string" || !text) return text;
  if (!text.includes("⃗")) return text;
  if (!wrapBare)
    return text.replace(
      COMBINING_VEC_RE,
      (_m, l: string) => "\\vec{" + l + "}",
    );
  const mask = mathMask(text);
  return text.replace(COMBINING_VEC_RE, (_m, l: string, offset: number) =>
    mask[offset] ? "\\vec{" + l + "}" : "$\\vec{" + l + "}$",
  );
}

// Fast-path check: any character from UNICODE_MATH present?
const TRIGGER_RE = new RegExp(
  "[" + escapeRegExp(Object.keys(UNICODE_MATH).join("")) + "]",
);

/** True when `\cmd` would run into a following letter. */
function needsTerminator(
  replacement: string,
  nextChar: string | null,
): boolean {
  if (!replacement.startsWith("\\")) return false;
  if (!isAlpha(replacement[replacement.length - 1])) return false;
  if (nextChar === null) return false;
  return isAlpha(nextChar);
}

// The radical glyphs map to `\sqrt`, the one command here that REQUIRES an
// argument. They are only converted together with their radicand; with none
// to take, the glyph stays (#1654).
const ROOT_CHARS = new Set(["√", "∛", "∜"]);
const ROOT_NUMBER_RE = /[-−]?\d+(?:\.\d+)?/y;
const CLOSERS: Readonly<Record<string, string>> = { "(": ")", "{": "}" };
// What may not follow a captured number or letter: more of the same word, a
// call, or a script.
const SCRIPT_CHARS = new Set("^_⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ₀₁₂₃₄₅₆₇₈₉");

/**
 * The radicand starting at `pos` as `[inner text, end index]`, or null.
 * Only shapes with a single reading are taken: a balanced `(…)` or `{…}`
 * group that stays inside one line and one math span, a number, or a single
 * letter.
 */
function rootArgument(text: string, pos: number): [string, number] | null {
  if (pos >= text.length) return null;
  const ch = text[pos];
  if (ch in CLOSERS) {
    const closer = CLOSERS[ch];
    let depth = 0;
    for (let end = pos; end < text.length; end++) {
      const c = text[end];
      if (c === "$" || c === "\n") return null;
      if (c === ch) depth++;
      else if (c === closer) {
        depth--;
        if (depth === 0) {
          const inner = text.slice(pos + 1, end);
          return inner.trim() ? [inner, end + 1] : null;
        }
      }
    }
    return null;
  }
  let end: number;
  const m = matchAt(ROOT_NUMBER_RE, text, pos);
  if (m) end = pos + m[0].length;
  else if (isAlpha(charAt(text, pos))) end = pos + charAt(text, pos).length;
  else return null;
  const nxt = charAt(text, end);
  if (isAlnum(nxt) || nxt === "(" || SCRIPT_CHARS.has(nxt)) return null;
  return [text.slice(pos, end), end];
}

/** Inside math `\sqrt` takes the next token; false when there is none. */
function rootHasNextToken(seg: string, pos: number): boolean {
  const rest = pyLstrip(seg.slice(pos));
  return (
    rest.length > 0 && !"}&^_".includes(rest[0]) && !rest.startsWith("\\\\")
  );
}

// Text-mode groups inside math: their content is prose, and KaTeX renders
// `\text{H₂O}` as written while `\text{H_{2}O}` is a parse error. The group
// is copied verbatim (balanced braces).
const TEXT_GROUP_RE =
  /\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox|hbox|ce|pu)\s*\{/y;
const SUPERSCRIPT_CHARS: ReadonlySet<string> = new Set(
  Object.keys(UNICODE_MATH).filter((k) => UNICODE_MATH[k].startsWith("^{")),
);
const SUBSCRIPT_CHARS: ReadonlySet<string> = new Set(
  Object.keys(UNICODE_MATH).filter((k) => UNICODE_MATH[k].startsWith("_{")),
);

/** Index just past the `}` matching the `{` at `i` (or the length on imbalance). */
function skipGroup(seg: string, i: number): number {
  let depth = 0;
  const n = seg.length;
  while (i < n) {
    const c = seg[i];
    if (c === "\\") {
      i += 2;
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return i + 1;
    }
    i++;
  }
  return n;
}

/**
 * Replace every Unicode math char in a segment with its LaTeX form. Skips
 * `\text{…}`-family groups (prose inside math), turns a RUN of Unicode
 * super/subscripts into one `^{…}` / `_{…}` (`10⁻³` → `10^{-3}`), and, when
 * a replacement is a `\cmd` and the next character is a letter, appends a
 * space so `a⋅b` → `a\cdot b`.
 */
export function replaceChars(seg: string): string {
  if (!TRIGGER_RE.test(seg)) return seg;
  const out: string[] = [];
  const n = seg.length;
  let i = 0;
  while (i < n) {
    const ch = seg[i];
    if (ch === "\\") {
      const m = matchAt(TEXT_GROUP_RE, seg, i);
      if (m) {
        const end = skipGroup(seg, i + m[0].length - 1);
        out.push(seg.slice(i, end));
        i = end;
        continue;
      }
    }
    if (SUPERSCRIPT_CHARS.has(ch) || SUBSCRIPT_CHARS.has(ch)) {
      const table = SUPERSCRIPT_CHARS.has(ch)
        ? SUPERSCRIPT_CHARS
        : SUBSCRIPT_CHARS;
      let j = i;
      let inner = "";
      while (j < n && table.has(seg[j])) {
        inner += UNICODE_MATH[seg[j]].slice(2, -1);
        j++;
      }
      out.push((table === SUPERSCRIPT_CHARS ? "^{" : "_{") + inner + "}");
      i = j;
      continue;
    }
    if (ROOT_CHARS.has(ch)) {
      const arg = rootArgument(seg, i + 1);
      if (arg !== null) {
        const [inner, end] = arg;
        out.push(UNICODE_MATH[ch] + "{" + replaceChars(inner) + "}");
        i = end;
        continue;
      }
      if (!rootHasNextToken(seg, i + 1)) {
        out.push(ch);
        i++;
        continue;
      }
    }
    let replacement = Object.prototype.hasOwnProperty.call(UNICODE_MATH, ch)
      ? UNICODE_MATH[ch]
      : ch;
    if (replacement !== ch) {
      const nextChar = i + 1 < n ? seg[i + 1] : null;
      if (needsTerminator(replacement, nextChar)) replacement += " ";
    }
    out.push(replacement);
    i++;
  }
  return out.join("");
}

/**
 * Convert Unicode math characters to their LaTeX command form. With
 * `insideMathOnly` (default) only the closed math spans (as the renderers'
 * tokenizer sees them) are converted.
 */
export function unicodeMathToLatex(
  text: string,
  insideMathOnly = true,
): string {
  if (typeof text !== "string" || !text) return text;
  if (!TRIGGER_RE.test(text)) return text;
  if (!insideMathOnly) return replaceChars(text);
  let out = "";
  let pos = 0;
  for (const { start, end } of mathRanges(text)) {
    out += text.slice(pos, start);
    const raw = text.slice(start, end);
    const k = delimiterWidth(raw);
    out +=
      raw.slice(0, k) +
      replaceChars(raw.slice(k, raw.length - k)) +
      raw.slice(raw.length - k);
    pos = end;
  }
  out += text.slice(pos);
  return out;
}

const WRAPPABLE_RE = new RegExp(
  "[" + escapeRegExp([...WRAPPABLE_BARE_CHARS].join("")) + "]",
);

/**
 * Index one past the `}` closing the `{` at `j` (a backslash skips the next
 * character), or null when it does not close before a newline, a math span
 * or the end of the text.
 */
function groupEnd(
  text: string,
  j: number,
  mask: readonly boolean[],
): number | null {
  let depth = 0;
  const n = text.length;
  let k = j;
  while (k < n) {
    if (mask[k]) return null;
    const c = text[k];
    if (c === "\\") {
      k += 2;
      continue;
    }
    if (c === "\n") return null;
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return k + 1;
    }
    k++;
  }
  return null;
}

/** True when `text.slice(0, k)` ends with an unescaped `\name`. */
function commandNameEndsAt(text: string, k: number): boolean {
  let q = k;
  while (q > 0 && isAsciiLetter(text[q - 1])) q--;
  if (q === k || q === 0 || text[q - 1] !== "\\") return false;
  let run = 0;
  while (q - 1 - run >= 0 && text[q - 1 - run] === "\\") run++;
  return run % 2 === 1;
}

/**
 * `out[i]` is true when `text[i]` lies inside a closed brace group, outside
 * math, that belongs to a bare script (`e^{iπ}`, `x_{α}`) or to a bare
 * command's arguments (`\frac{π}{2}`, `\sqrt[3]{2π}`, `\text{π}`): the
 * character right before the `{` is `^` or `_`, the end of an unescaped
 * `\name`, the `]` of an optional argument that directly follows a `\name`,
 * or the `}` of another such group. The later wrapping steps put the whole
 * group in one span, so the characters inside must not get a span of their
 * own first (`$e^{i$\pi$}$`).
 */
export function attachedGroupMask(
  text: string,
  mask?: readonly boolean[] | null,
): boolean[] {
  const m: readonly boolean[] = mask ?? mathMask(text);
  const n = text.length;
  const out: boolean[] = new Array<boolean>(n + 1).fill(false);
  const attachedClose = new Set<number>(); // end index of each attached group
  for (let i = 0; i < n; i++) {
    if (text[i] !== "{" || m[i]) continue;
    let run = 0;
    while (i - 1 - run >= 0 && text[i - 1 - run] === "\\") run++;
    const end = run % 2 === 0 ? groupEnd(text, i, m) : null;
    if (end === null) continue;
    const prev = i > 0 ? text[i - 1] : "";
    let attached =
      prev === "^" ||
      prev === "_" ||
      commandNameEndsAt(text, i) ||
      (prev === "}" && attachedClose.has(i));
    if (!attached && prev === "]") {
      const o = i >= 2 ? text.lastIndexOf("[", i - 2) : -1;
      attached =
        o > 0 &&
        !text.slice(o + 1, i - 1).includes("]") &&
        commandNameEndsAt(text, o);
    }
    if (attached) {
      for (let k = i; k < end; k++) out[k] = true;
      attachedClose.add(end);
    }
  }
  return out;
}

/**
 * Wrap any bare Unicode math char (outside math spans) in `$…$`, together
 * with its tight cluster (spec §0.1): `ħω` → `$\hbar\omega$`, `3×4×5` →
 * `$3\times4\times5$`, `ε₀` → `$\epsilon_{0}$`, and a Greek word whole
 * (`2πr` → `$2\pi r$`). A radical without a radicand stays as written
 * (#1654). The span's closing `$` is never followed by a digit (the
 * renderers' closer rule would drop it). With `skipAttachedGroups` (the
 * default) a symbol inside a bare script or command argument group
 * (`e^{iπ}`, `\frac{π}{2}`) is left to the step that wraps the whole group;
 * canonicalize calls this again with it off for groups nothing wrapped.
 */
export function wrapBareUnicodeMath(
  text: string,
  skipAttachedGroups = true,
): string {
  if (typeof text !== "string" || !text) return text;
  if (!WRAPPABLE_RE.test(text)) return text;
  const mask = mathMask(text);
  const inGroup = skipAttachedGroups ? attachedGroupMask(text, mask) : null;
  const out: string[] = [];
  let last = 0; // text.slice(0, last) has been emitted
  let i = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (
      WRAPPABLE_BARE_CHARS.has(ch) &&
      !mask[i] &&
      (inGroup === null || !inGroup[i])
    ) {
      if (ROOT_CHARS.has(ch) && rootArgument(text, i + 1) === null) {
        i++; // no radicand: the glyph stays as written (#1654)
        continue;
      }
      const word = GREEK_MATH_LETTERS.has(ch)
        ? greekWordAt(text, i, mask)
        : null;
      let start: number;
      let end: number;
      if (word !== null && word[0] >= last) {
        // `2πr`, `fλ`, `Δx`: the span takes the whole Greek word.
        start = word[0];
        end = clusterRight(text, start, mask);
      } else {
        start = clusterLeft(text, i, last, mask);
        end = clusterRight(text, i, mask);
      }
      out.push(text.slice(last, start));
      out.push(
        wrapCluster(
          text,
          start,
          end,
          convertCluster(text.slice(start, end)),
          mask,
        ),
      );
      last = i = end;
      continue;
    }
    i++;
  }
  out.push(text.slice(last));
  return out.join("");
}

// ---------------------------------------------------------------------------
// Tight clusters: what a new `$…$` span around a bare symbol must take with it
// ---------------------------------------------------------------------------

const ALL_SCRIPT_CHARS: ReadonlySet<string> = new Set([
  ...SUPERSCRIPT_CHARS,
  ...SUBSCRIPT_CHARS,
]);
const ASCII_SCRIPT_RE =
  /[_^](?:\{[^{}$\n]*\}|\\[A-Za-z]+|[A-Za-z0-9](?![A-Za-z]))/y;
const NUMBER_RE = /[0-9]+(?:[.,][0-9]+)*/y;
const NUMBER_CHARS = "0123456789.,";

function isAsciiLetter(c: string): boolean {
  return (c >= "a" && c <= "z") || (c >= "A" && c <= "Z");
}

function isAsciiUpper(c: string): boolean {
  return c >= "A" && c <= "Z";
}

function masked(
  mask: readonly boolean[] | null | undefined,
  k: number,
): boolean {
  return mask != null && mask[k] === true;
}

function standaloneLetter(text: string, k: number): boolean {
  return (
    isAsciiLetter(text[k]) &&
    (k === 0 || !isAsciiLetter(text[k - 1])) &&
    (k + 1 >= text.length || !isAsciiLetter(text[k + 1]))
  );
}

/**
 * Start of the number or standalone single letter that ends at `end`, or
 * null when what ends there may not join a span.
 */
function leftAtom(
  text: string,
  end: number,
  floor: number,
  mask: readonly boolean[] | null | undefined,
  beforeSubscript: boolean,
): number | null {
  if (end <= floor || masked(mask, end - 1)) return null;
  const c = text[end - 1];
  if (c >= "0" && c <= "9") {
    let q = end - 1;
    while (
      q - 1 >= floor &&
      NUMBER_CHARS.includes(text[q - 1]) &&
      !masked(mask, q - 1)
    )
      q--;
    while (text[q] === "." || text[q] === ",") q++;
    const prev = q >= 1 ? text[q - 1] : "";
    // A script argument (`10^2`), an escaped or currency dollar (`\$5`, the
    // canonicalize sentinel ending in U+E001) or a word (`CO2`) owns the
    // number.
    if (
      prev &&
      ("\\^_$\ue001".includes(prev) ||
        (isAsciiLetter(prev) && !standaloneLetter(text, q - 1)))
    )
      return null;
    return q;
  }
  if (isAsciiLetter(c)) {
    const p = end - 1;
    const prev = p >= 1 ? text[p - 1] : "";
    if (isAsciiLetter(prev) || (prev && "\\^_".includes(prev))) return null;
    // An uppercase letter with a subscript digit is chemistry (`H₂`), which
    // `wrapUnicodeChemistry` sets upright later.
    if (beforeSubscript && isAsciiUpper(c)) return null;
    return p;
  }
  return null;
}

// Operators and relations whose operands are pulled into the span: `3×4`,
// `x≤5`, `n→∞`, `a∈A`. Letters next to other symbols stay outside (`µs`,
// `kΩ` and `J·s` are units; `2√3` and `2π` keep their Backend #1654 shape).
const JOINING_COMMAND_RE = new RegExp(
  "\\\\(?:" +
    [...JOINING_COMMANDS]
      .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0))
      .join("|") +
    ")(?![A-Za-z])",
  "y",
);

/** True when a joining operator (character or command) starts at `p`. */
function joiningAt(text: string, p: number): boolean {
  if (p >= text.length) return false;
  return (
    JOINING_CHARS.has(text[p]) ||
    (text[p] === "\\" && matchAt(JOINING_COMMAND_RE, text, p) !== null)
  );
}

// ---------------------------------------------------------------------------
// Greek words: `2πr`, `fλ`, `hν`, `Δx`, `ωt` are one span (audit round 3)
// ---------------------------------------------------------------------------

// A Greek word that is a unit keeps its earlier shape (`$\mu$s`,
// `k$\Omega$`): an optional number, then μ + a unit symbol, or an SI prefix +
// Ω (+ m/cm for ohm-metre), then optional Unicode scripts (`μm²`). Anchored:
// Python `fullmatch`.
const GREEK_UNIT_RE = new RegExp(
  "^[0-9]*(?:[.,][0-9]+)*(?:[kMGTmμµnp]?Ω(?:c?m)?|[μµ](?:" +
    [...GREEK_UNIT_SYMBOLS].sort((a, b) => b.length - a.length).join("|") +
    "|Ω)?)[" +
    escapeRegExp([...ALL_SCRIPT_CHARS].join("")) +
    "]*$",
);
const THREE_ASCII_LETTERS_RE = /[A-Za-z]{3}/;
const THREE_GREEK_RE = new RegExp(
  "[" + escapeRegExp([...GREEK_MATH_LETTERS].join("")) + "]{3}",
);
const CHEM_IN_WORD_RE = new RegExp(
  "[A-Z][" + escapeRegExp([...SUBSCRIPT_CHARS].join("")) + "]",
);
const WORD_BLOCKED_BEFORE = "\\^_{$\ue001";

function isAsciiAlnum(c: string): boolean {
  return isAsciiLetter(c) || (c >= "0" && c <= "9");
}

function greekWordChar(
  text: string,
  k: number,
  mask: readonly boolean[] | null | undefined,
): boolean {
  if (k < 0 || k >= text.length || masked(mask, k)) return false;
  const c = text[k];
  if (
    GREEK_MATH_LETTERS.has(c) ||
    SUPERSCRIPT_CHARS.has(c) ||
    SUBSCRIPT_CHARS.has(c) ||
    isAsciiAlnum(c)
  )
    return true;
  // `.` / `,` only inside a number (`2.5λ`)
  return (
    (c === "." || c === ",") &&
    k > 0 &&
    k < text.length - 1 &&
    text[k - 1] >= "0" &&
    text[k - 1] <= "9" &&
    text[k + 1] >= "0" &&
    text[k + 1] <= "9" &&
    !masked(mask, k - 1) &&
    !masked(mask, k + 1)
  );
}

/**
 * `[start, end]` of the Greek word containing `text[k]`, or null (spec §0.1
 * "Greek words"). A Greek word is a maximal run, with no whitespace, of
 * Greek math letters (`GREEK_MATH_LETTERS`), ASCII letters, digits (`.`/`,`
 * between digits) and Unicode scripts that contains at least one Greek
 * letter and one ASCII letter or digit: `2πr`, `fλ`, `Δx`, `ωt`, `πr²`. It
 * is refused when it has 3+ ASCII letters in a row (`αβγtest`, `Thetaα`,
 * `sinθ`), 3+ Greek letters in a row, an uppercase letter with a subscript
 * (chemistry, `ΔH₂O`), when it is a unit (`µs`, `kΩ`, `10Ω`, `5μm²`), or
 * when it touches another word or a script: the character before it is a
 * letter or digit of any script, `\ ^ _ { $` or the canonicalize dollar
 * sentinel; the character after it is a letter or digit of any script. A
 * math character on either side is a boundary.
 */
export function greekWordAt(
  text: string,
  k: number,
  mask?: readonly boolean[] | null,
): [number, number] | null {
  if (!greekWordChar(text, k, mask)) return null;
  let s = k;
  while (greekWordChar(text, s - 1, mask)) s--;
  let e = k + 1;
  while (greekWordChar(text, e, mask)) e++;
  const word = text.slice(s, e);
  let greek = false;
  let ascii = false;
  for (const c of word) {
    if (GREEK_MATH_LETTERS.has(c)) greek = true;
    else if (isAsciiAlnum(c)) ascii = true;
  }
  if (!greek || !ascii) return null;
  if (s > 0 && !masked(mask, s - 1)) {
    const b = codePointBefore(text, s);
    if (isAlnum(b) || WORD_BLOCKED_BEFORE.includes(b)) return null;
  }
  if (e < text.length && !masked(mask, e) && isAlnum(charAt(text, e)))
    return null;
  if (
    THREE_ASCII_LETTERS_RE.test(word) ||
    THREE_GREEK_RE.test(word) ||
    CHEM_IN_WORD_RE.test(word) ||
    GREEK_UNIT_RE.test(word)
  )
    return null;
  return [s, e];
}

/**
 * Move `start` left over the tight operands a new span must include, when
 * the cluster starts with a joining operator (`JOINING_CHARS` /
 * `JOINING_COMMANDS`): numbers (`3.14`, `1,00,000`), standalone single
 * letters (`x` in `x≤5`, not `abc`) and Unicode scripts attached to one of
 * those. Never below `floor`, never into a math span, a word, a script
 * argument (`10^2`) or a currency amount (`\$5`).
 */
export function clusterLeft(
  text: string,
  start: number,
  floor: number,
  mask?: readonly boolean[] | null,
): number {
  if (!joiningAt(text, start)) return start;
  while (start > floor && !masked(mask, start - 1)) {
    const c = text[start - 1];
    let b: number | null;
    if (ALL_SCRIPT_CHARS.has(c)) {
      let q = start - 1;
      while (
        q - 1 >= floor &&
        ALL_SCRIPT_CHARS.has(text[q - 1]) &&
        !masked(mask, q - 1)
      )
        q--;
      b = leftAtom(text, q, floor, mask, SUBSCRIPT_CHARS.has(text[q]));
    } else {
      b = leftAtom(text, start, floor, mask, false);
    }
    if (b === null) break;
    start = b;
  }
  return start;
}

/**
 * End of the tight cluster that starts at `pos`: a run of wrappable symbols
 * (a radical with its radicand), bare symbol commands matched by
 * `commandRe` (a sticky regex), numbers, ASCII scripts (`_1`, `^{2}`),
 * Unicode script runs, and a standalone single letter right after a joining
 * operator (`x→y`), with nothing between them.
 */
export function clusterRight(
  text: string,
  pos: number,
  mask?: readonly boolean[] | null,
  commandRe?: RegExp | null,
): number {
  const n = text.length;
  let p = pos;
  let afterJoining = false;
  while (p < n && !masked(mask, p)) {
    const c = text[p];
    let joining = false;
    const word =
      GREEK_MATH_LETTERS.has(c) || isAsciiAlnum(c)
        ? greekWordAt(text, p, mask)
        : null;
    if (word !== null && word[0] >= pos) {
      p = word[1]; // `2πr`, `Δx`: the whole Greek word
    } else if (WRAPPABLE_BARE_CHARS.has(c)) {
      if (ROOT_CHARS.has(c)) {
        const arg = rootArgument(text, p + 1);
        if (arg === null) break;
        p = arg[1];
      } else {
        joining = JOINING_CHARS.has(c);
        p++;
      }
    } else if (ALL_SCRIPT_CHARS.has(c)) {
      while (p < n && ALL_SCRIPT_CHARS.has(text[p]) && !masked(mask, p)) p++;
    } else if (c === "\\" && commandRe != null) {
      const m = matchAt(commandRe, text, p);
      if (!m) break;
      joining = joiningAt(text, p);
      p += m[0].length;
    } else if (c === "_" || c === "^") {
      if (p === pos) break;
      const m = matchAt(ASCII_SCRIPT_RE, text, p);
      if (!m || m[0].includes("$")) break;
      p += m[0].length;
    } else if (c >= "0" && c <= "9") {
      p += matchAt(NUMBER_RE, text, p)![0].length;
    } else if (isAsciiLetter(c)) {
      const nxt = p + 1 < n ? text[p + 1] : "";
      if (!afterJoining || (p > 0 && isAsciiLetter(text[p - 1]))) break;
      if (isAsciiLetter(nxt) || nxt === "(") break;
      // Chemistry (`5H₂O`): left to wrapUnicodeChemistry.
      if (isAsciiUpper(c) && nxt && SUBSCRIPT_CHARS.has(nxt)) break;
      p++;
    } else {
      break;
    }
    afterJoining = joining;
  }
  return p;
}

/**
 * LaTeX for a cluster: symbols → commands (a radical takes its radicand), a
 * run of Unicode scripts → one `^{…}` / `_{…}`, anything else as written; a
 * space only where a command would run into a letter.
 */
export function convertCluster(cluster: string): string {
  const parts: string[] = [];
  const n = cluster.length;
  let i = 0;
  while (i < n) {
    const c = cluster[i];
    let step = 1;
    let rep: string;
    const arg =
      ROOT_CHARS.has(c) && !ALL_SCRIPT_CHARS.has(c)
        ? rootArgument(cluster, i + 1)
        : null;
    if (ALL_SCRIPT_CHARS.has(c)) {
      const table = SUPERSCRIPT_CHARS.has(c)
        ? SUPERSCRIPT_CHARS
        : SUBSCRIPT_CHARS;
      let j = i;
      let inner = "";
      while (j < n && table.has(cluster[j])) {
        inner += UNICODE_MATH[cluster[j]].slice(2, -1);
        j++;
      }
      rep = (table === SUPERSCRIPT_CHARS ? "^{" : "_{") + inner + "}";
      step = j - i;
    } else if (arg !== null) {
      rep = UNICODE_MATH[c] + "{" + replaceChars(arg[0]) + "}";
      step = arg[1] - i;
    } else if (WRAPPABLE_BARE_CHARS.has(c)) {
      rep = UNICODE_MATH[c];
    } else {
      rep = c;
    }
    if (parts.length > 0 && needsTerminator(parts[parts.length - 1], rep[0]))
      parts.push(" ");
    parts.push(rep);
    i += step;
  }
  return parts.join("");
}

/**
 * `$latex$` for `text.slice(start, end)`, padded with one space where the
 * neighbour would break the span: a literal `$` right before or after (`$$`
 * would open display math) or a digit right after (a closer followed by a
 * digit is not a closer).
 */
export function wrapCluster(
  text: string,
  start: number,
  end: number,
  latex: string,
  mask?: readonly boolean[] | null,
): string {
  let head = "";
  let tail = "";
  if (start > 0 && text[start - 1] === "$" && !masked(mask, start - 1)) {
    if (start < 2 || text[start - 2] !== "\\") head = " ";
  }
  if (end < text.length && !masked(mask, end)) {
    const nxt = charAt(text, end);
    if (nxt === "$" || isDigit(nxt)) tail = " ";
  }
  return head + "$" + latex + "$" + tail;
}
