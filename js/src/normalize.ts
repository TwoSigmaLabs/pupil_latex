/**
 * `normalize`: display-safe, content-preserving preparation for a renderer.
 *
 * Port of python/pupiltree_latex/normalize.py. The order is load-bearing:
 * delimiters are normalised BEFORE prose escapes are decoded, so a `\theta`
 * still sitting inside `\(…\)` is recognised as math and not turned into a
 * TAB plus "heta". Nothing here wraps text in `$`, converts Unicode or
 * touches URLs.
 */

import {
  detectCommandMissingArgument,
  detectFracMissingArgs,
} from "./audit.js";
import { countOf, isAsciiDigit, matchAt, pyStrip } from "./chars.js";
import { KATEX_COMMANDS, PROSE_ESCAPE_COMMANDS } from "./commands.js";
import {
  after,
  matchAllAfter,
  replaceAfter,
  type Blocked,
} from "./lookbehind.js";
// `canonicalize` imports `isFormula` from here; the cycle is call-time only.
import { trimPaddedSpans as trimPaddedSpansInText } from "./canonicalize.js";
import { fixMojibakeTable } from "./mojibake.js";
import { repair } from "./repair.js";
import { segment } from "./segment.js";

// ---------------------------------------------------------------------------
// 3. delimiters
// ---------------------------------------------------------------------------

// Not after a backslash (AFTER_BACKSLASH), and the content does not end in
// one, so a LaTeX line break `\\[2pt]` inside a display block is not
// mistaken for an opening `\[`, and `\\)` is not a closer.
const DISPLAY_BRACKET_RE = /\\\[([\s\S]*?[^\\])\\\]/g;
const INLINE_PAREN_RE = /\\\(([\s\S]*?[^\\])\\\)/g;
const AFTER_BACKSLASH = after("\\");
const INNER_NEWLINE_RE = /\s*\n\s*/g;

/**
 * `\(…\)` → `$…$` and `\[…\]` → `$$…$$`. Newlines inside an inline span
 * collapse to one space: no inline matcher crosses lines.
 */
export function normalizeDelimiters(text: string): string {
  if (!text.includes("\\(") && !text.includes("\\[")) return text;
  text = replaceAfter(
    text,
    DISPLAY_BRACKET_RE,
    AFTER_BACKSLASH,
    (_m, inner: string) => "$$" + inner + "$$",
  );
  text = replaceAfter(
    text,
    INLINE_PAREN_RE,
    AFTER_BACKSLASH,
    (_m, inner: string) =>
      "$" + inner.replace(INNER_NEWLINE_RE, " ").trim() + "$",
  );
  return text;
}

// ---------------------------------------------------------------------------
// 4. orphan delimiters
// ---------------------------------------------------------------------------

// Not after a backslash (AFTER_BACKSLASH).
const ORPHAN_DELIMITER_RE = /\\[()[\]]/g;

/**
 * Remove any `\(` `\)` `\[` `\]` left after `normalizeDelimiters`; by
 * construction they have no partner.
 */
export function stripOrphanDelimiters(text: string): string {
  if (
    !text.includes("\\(") &&
    !text.includes("\\)") &&
    !text.includes("\\[") &&
    !text.includes("\\]")
  ) {
    return text;
  }
  return replaceAfter(text, ORPHAN_DELIMITER_RE, AFTER_BACKSLASH, () => "");
}

// ---------------------------------------------------------------------------
// 5. currency
// ---------------------------------------------------------------------------

function digitAt(s: string, i: number): boolean {
  return i >= 0 && i < s.length && isAsciiDigit(s[i]);
}

function spaceAt(s: string, i: number): boolean {
  return i >= 0 && i < s.length && (s[i] === " " || s[i] === "\t");
}

function escapedAt(s: string, i: number): boolean {
  return i > 0 && s[i - 1] === "\\";
}

const FORMULA_CHARS_RE = /^[0-9A-Za-z+\-*/=<>().,^_ \t]+$/;
const FORMULA_OPERATOR_RE = /[+\-*/=<>^_]/;
const FORMULA_COMMAND_RE = /\\[A-Za-z]+/g;
const TWO_LETTERS_RE = /[A-Za-z]{2,}/;

/**
 * True when the content of `$<digit>… $` (space before the closer) is
 * clearly a formula, not prose between two amounts: after removing command
 * names it is only digits, letters, operators, brackets and spaces, has an
 * operator and a letter or command, and no two letters in a row.
 */
export function isFormula(content: string): boolean {
  const core = content.replace(/[ \t]+$/, "");
  if (!core) return false;
  const hasCommand = /\\[A-Za-z]/.test(core);
  const bare = core.replace(FORMULA_COMMAND_RE, " ");
  if (!FORMULA_CHARS_RE.test(bare) || TWO_LETTERS_RE.test(bare)) return false;
  if (!FORMULA_OPERATOR_RE.test(bare) && !hasCommand) return false;
  if (!(hasCommand || /[A-Za-z]/.test(bare))) return false;
  // A command that needs an argument and has none (`$5 \text $`) cannot
  // render: as currency it at least stays readable.
  const probe = "$" + core + "$";
  return (
    detectCommandMissingArgument(probe).length === 0 &&
    detectFracMissingArgs(probe).length === 0
  );
}

/** Indices of the currency dollars in one line (the `$` that
 * `escapeCurrency` turns into `\$`). */
function currencyPositionsInLine(line: string): number[] {
  const found: number[] = [];
  if (!line.includes("$")) return found;
  const n = line.length;
  let i = 0;
  while (i < n) {
    const ch = line[i];
    if (ch !== "$" || escapedAt(line, i)) {
      i++;
      continue;
    }
    // `$$` display block: skip to its closing `$$` (or end of line).
    if (i + 1 < n && line[i + 1] === "$") {
      const close = line.indexOf("$$", i + 2);
      i = close === -1 ? n : close + 2;
      continue;
    }
    if (!digitAt(line, i + 1)) {
      // A math opener: skip the whole span through to its first closer (the
      // tokenizer's rule) so the closer is never re-examined as a currency
      // opener (`$\sqrt$2` must not become `$\sqrt\$2`).
      let j = i + 1;
      while (j < n && !(line[j] === "$" && !escapedAt(line, j))) j++;
      i = j < n ? j + 1 : i + 1;
      continue;
    }
    // `$<digit>`: currency unless the next single `$` is a valid closer.
    let j = i + 1;
    let closerValid = false;
    while (j < n) {
      if (line[j] === "$" && !escapedAt(line, j)) {
        // A `$` right after the closer is the NEXT span's opener
        // (`$1$$\\gamma$`), not a display delimiter: only whitespace
        // before and a digit after invalidate a closer.
        closerValid =
          !digitAt(line, j + 1) &&
          // `Compute $2x + 3 $.`: the renderers pair a closer after a
          // space, so a formula keeps its dollars.
          (!spaceAt(line, j - 1) || isFormula(line.slice(i + 1, j)));
        break;
      }
      j++;
    }
    if (closerValid) {
      i = j + 1;
    } else {
      found.push(i);
      i++;
    }
  }
  return found;
}

/**
 * Indices of the dollars `escapeCurrency` reads as money (pandoc's closer
 * rule, per line). `toPlain` uses it to keep amounts.
 */
export function currencyPositions(text: string): number[] {
  const found: number[] = [];
  if (!text.includes("$")) return found;
  let base = 0;
  for (const line of text.split("\n")) {
    for (const k of currencyPositionsInLine(line)) found.push(base + k);
    base += line.length + 1;
  }
  return found;
}

function escapeCurrencyInLine(line: string): string {
  const positions = currencyPositionsInLine(line);
  if (positions.length === 0) return line;
  const out: string[] = [];
  let pos = 0;
  for (const k of positions) {
    out.push(line.slice(pos, k), "\\$");
    pos = k + 1;
  }
  out.push(line.slice(pos));
  return out.join("");
}

/**
 * A `$` that is money becomes `\$` (pandoc's closer rule, per line).
 * `$5000 and $\frac14$` → `\$5000 and $\frac14$`; `$5-$10` → `\$5-\$10`;
 * `costs $5.` → `costs \$5.`; `$2x + 3$` unchanged.
 */
export function escapeCurrency(text: string): string {
  if (!text.includes("$")) return text;
  return text.split("\n").map(escapeCurrencyInLine).join("\n");
}

// ---------------------------------------------------------------------------
// 5a. padded spans
// ---------------------------------------------------------------------------

/**
 * `Solve $ x + 1 = 0 $` → `Solve $x + 1 = 0$` (tag `audit6-1`): the rule
 * `canonicalize` applies (pairs per line; content clearly math; neither
 * dollar glued to a letter or digit outside the pair, so a closer followed by
 * a digit stays). Run after `escapeCurrency`: an escaped amount is never
 * paired. `segment` keeps pandoc's rule, so without this a stored padded
 * formula displays as raw text.
 */
export function trimPaddedSpans(text: string): string {
  return trimPaddedSpansInText(text);
}

/** U+E000 (private use): never in content. */
const CURRENCY_MASK = "\ue000";

/**
 * `trimPaddedSpans` on text whose amounts are not escaped (`toPlain` input):
 * the dollars `currencyPositions` reads as money are masked first, so they
 * are never paired (`Rs $5 and $10 for $ x^2 $` → only the last pair is
 * trimmed).
 */
export function trimPaddedSpansKeepCurrency(text: string): string {
  if (!text.includes("$") || text.includes(CURRENCY_MASK)) return text;
  const money = currencyPositions(text);
  if (money.length) {
    const chars = text.split("");
    for (const k of money) chars[k] = CURRENCY_MASK;
    text = chars.join("");
  }
  return trimPaddedSpans(text).split(CURRENCY_MASK).join("$");
}

// ---------------------------------------------------------------------------
// 6. prose escapes
// ---------------------------------------------------------------------------

// A whole math span. Inline content may contain `\$` but no bare `$` and no
// newline — the shape every inline matcher accepts.
// The single-dollar alternative must not follow a backslash (MATH_SPAN_BLOCKED;
// only that alternative can match a `$` not followed by `$`).
const MATH_SPAN_RE = /\$\$[\s\S]*?\$\$|\$(?:\\[^\n]|[^$\n\\])+\$/g;
const MATH_SPAN_BLOCKED: Blocked = (text, m) =>
  m[0][1] !== "$" && m.index > 0 && text[m.index - 1] === "\\";
const PROSE_ESCAPE_RE = /\\r\\n|\\[nrt]/g;
const COMMAND_NAME_RE = /\\([A-Za-z]+)/y;
const SCRIPT_LABEL_RE = /\\[a-z][a-z_]*:/y;

function decodeProseEscapes(prose: string): string {
  return prose.replace(PROSE_ESCAPE_RE, (m: string, offset: number) => {
    const name = matchAt(COMMAND_NAME_RE, prose, offset);
    // Same vocabulary as the JSON transport: outside math `\\nu`, `\\ne`,
    // `\\ni`, `\\not` are line breaks (production prose proved it).
    if (name && PROSE_ESCAPE_COMMANDS.has(name[1])) return m;
    // A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an
    // escape, whatever the word.
    if (matchAt(SCRIPT_LABEL_RE, prose, offset)) return m;
    return m === "\\t" ? "\t" : "\n";
  });
}

/**
 * Literal two-character `\n` / `\r\n` / `\r` / `\t` in prose become real
 * whitespace. Math spans are left intact, and a known command (`\theta`,
 * `\neq`, `\text{…}`, `\right`) is never touched.
 */
export function decodeEscapesOutsideMath(text: string): string {
  if (!text.includes("\\")) return text;
  // Protected: every `segment` math span (what the renderers typeset; tag
  // `audit5-8`: in `a $ $\nu$ b` the regex pairs `$ $` and used to decode
  // the `\nu` that `segment` renders) and every regex span (a padded
  // `$ x \ne y $5` that `trimPaddedSpans` left). Decoding is lossy, so a position
  // either reader calls math is kept.
  const n = text.length;
  const isProtected = new Uint8Array(n);
  for (const m of matchAllAfter(MATH_SPAN_RE, text, MATH_SPAN_BLOCKED)) {
    isProtected.fill(1, m.index, m.index + m[0].length);
  }
  let pos = 0;
  for (const seg of segment(text)) {
    const end = pos + seg.raw.length;
    if (seg.kind === "math") isProtected.fill(1, pos, end);
    pos = end;
  }
  const out: string[] = [];
  let k = 0;
  while (k < n) {
    const flag = isProtected[k];
    let j = k;
    while (j < n && isProtected[j] === flag) j++;
    const part = text.slice(k, j);
    out.push(flag ? part : decodeProseEscapes(part));
    k = j;
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// currency spans (tag v140-b6)
// ---------------------------------------------------------------------------

/** One currency amount found by `currencySpans`. */
export interface CurrencySpan {
  start: number;
  end: number;
  text: string;
}

// An amount: digits with `,` groups (Indian or Western) and decimals.
const AMOUNT_RE = /[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?/y;
export const CURRENCY_SYMBOLS = "₹€£¥";
const AMOUNT_GAP = "  "; // one space or NBSP between a symbol and its amount

/**
 * Every currency amount in `text` with its position (tag `v140-b6`): an
 * escaped dollar `\$5` (odd run of backslashes before the `$`), a dollar
 * that `escapeCurrency` reads as money (`costs $5`; never a math span such
 * as `$5x+1=0$`), and `₹ € £ ¥` followed by at most one space and an
 * amount (`₹ 45,00,000`). Sorted by start. Positions are UTF-16 indices.
 */
export function currencySpans(text: unknown): CurrencySpan[] {
  if (typeof text !== "string" || !text) return [];
  const found: CurrencySpan[] = [];
  const money = new Set(text.includes("$") ? currencyPositions(text) : []);
  const n = text.length;
  for (let i = 0; i < n; i++) {
    const ch = text[i];
    let start = i;
    let j: number;
    if (ch === "$") {
      let k = i - 1;
      while (k >= 0 && text[k] === "\\") k--;
      const run = i - 1 - k;
      if (run % 2 === 1) start = i - 1;
      else if (!money.has(i)) continue;
      j = i + 1;
    } else if (CURRENCY_SYMBOLS.includes(ch)) {
      j = i + 1;
      if (
        j + 1 < n &&
        AMOUNT_GAP.includes(text[j]) &&
        isAsciiDigit(text[j + 1])
      )
        j++;
    } else {
      continue;
    }
    const m = matchAt(AMOUNT_RE, text, j);
    if (!m) continue;
    const end = j + m[0].length;
    found.push({ start, end, text: text.slice(start, end) });
  }
  return found;
}

// ---------------------------------------------------------------------------
// 2a. code spans as maths (opt-in, tag v140-b11)
// ---------------------------------------------------------------------------

const CODE_MATH_CHARS_RE = /^[0-9A-Za-z+\-*/=<>()[\]{}.,^_ \t|!']*$/;
const CODE_COMMAND_RE = /\\([A-Za-z]+)/g;
const CODE_WORD_RE = /[A-Za-z]{3,}/;

/**
 * True when an inline code body is clearly maths, not code: a KaTeX
 * command, `^` or `_`; after removing command names only maths characters
 * and no run of 3+ letters (`print`, `var`); and not an identifier (`lo_0`,
 * `a_b_c`).
 */
function codeBodyIsMath(body: string): boolean {
  if (!body || body !== pyStrip(body) || body.includes("$")) return false;
  const names = [...body.matchAll(CODE_COMMAND_RE)].map((m) => m[1]);
  if (names.some((name) => !KATEX_COMMANDS.has(name))) return false;
  if (names.length === 0 && !body.includes("^") && !body.includes("_"))
    return false;
  const bare = body.replace(CODE_COMMAND_RE, " ");
  if (!CODE_MATH_CHARS_RE.test(bare) || CODE_WORD_RE.test(bare)) return false;
  if (names.length === 0 && !body.includes("{") && !body.includes("^")) {
    const head = body.split("_", 1)[0];
    if (countOf(body, "_") >= 2 || head.length >= 2) return false;
  }
  return true;
}

/**
 * `` `x^2` `` → `$x^2$` when the single-backtick code body is clearly maths.
 * Fences and multi-backtick spans, bodies with a newline and a span followed
 * by a digit are left alone.
 */
export function codeSpansToMath(text: string): string {
  if (!text.includes("`")) return text;
  const out: string[] = [];
  const n = text.length;
  let i = 0;
  while (i < n) {
    if (text[i] !== "`") {
      out.push(text[i]);
      i++;
      continue;
    }
    let j = i;
    while (j < n && text[j] === "`") j++;
    if (j - i !== 1) {
      out.push(text.slice(i, j));
      i = j;
      continue;
    }
    const k = text.indexOf("`", j);
    if (k === -1) {
      out.push(text.slice(i));
      break;
    }
    const body = text.slice(j, k);
    if (
      body.includes("\n") ||
      (k + 1 < n && text[k + 1] === "`") ||
      (k + 1 < n && isAsciiDigit(text[k + 1])) ||
      !codeBodyIsMath(body)
    ) {
      out.push(text.slice(i, j));
      i = j;
      continue;
    }
    out.push("$" + body + "$");
    i = k + 1;
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// pipeline
// ---------------------------------------------------------------------------

/** Options of `normalize`. */
export interface NormalizeOptions {
  /**
   * Opt-in (tag `v140-b11`): an inline code span whose body is clearly
   * maths becomes a math span (`` `x^2` `` → `$x^2$`). Default `false`,
   * because code spans also hold real code.
   */
  codeSpansAsMath?: boolean;
}

/**
 * repair → mojibake table → (code spans) → delimiters → orphans → currency
 * → padded spans → escapes.
 * Idempotent, content-preserving. Non-strings are returned unchanged.
 */
export function normalize<T>(text: T, options?: NormalizeOptions): T;
export function normalize(
  text: unknown,
  options: NormalizeOptions = {},
): unknown {
  if (typeof text !== "string" || !text) return text;
  let out: string = repair(text);
  out = fixMojibakeTable(out);
  if (options.codeSpansAsMath === true) out = codeSpansToMath(out);
  out = normalizeDelimiters(out);
  out = stripOrphanDelimiters(out);
  out = escapeCurrency(out);
  out = trimPaddedSpans(out);
  out = decodeEscapesOutsideMath(out);
  return out;
}
