/**
 * `normalize`: display-safe, content-preserving preparation for a renderer.
 *
 * Port of python/pupiltree_latex/normalize.py. The order is load-bearing:
 * delimiters are normalised BEFORE prose escapes are decoded, so a `\theta`
 * still sitting inside `\(…\)` is recognised as math and not turned into a
 * TAB plus "heta". Nothing here wraps text in `$`, converts Unicode or
 * touches URLs.
 */

import { isAsciiDigit, matchAt } from "./chars.js";
import { PROSE_ESCAPE_COMMANDS } from "./commands.js";
import {
  after,
  matchAllAfter,
  replaceAfter,
  type Blocked,
} from "./lookbehind.js";
import { fixMojibakeTable } from "./mojibake.js";
import { repair } from "./repair.js";

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
  return hasCommand || /[A-Za-z]/.test(bare);
}

function escapeCurrencyInLine(line: string): string {
  if (!line.includes("$")) return line;
  const out: string[] = [];
  const n = line.length;
  let i = 0;
  while (i < n) {
    const ch = line[i];
    if (ch !== "$" || escapedAt(line, i)) {
      out.push(ch);
      i++;
      continue;
    }
    // `$$` display block: copy through to its closing `$$` (or end of line).
    if (i + 1 < n && line[i + 1] === "$") {
      const close = line.indexOf("$$", i + 2);
      const end = close === -1 ? n : close + 2;
      out.push(line.slice(i, end));
      i = end;
      continue;
    }
    if (!digitAt(line, i + 1)) {
      // A math opener: copy the whole span through to its first closer (the
      // tokenizer's rule) so the closer is never re-examined as a currency
      // opener (`$\sqrt$2` must not become `$\sqrt\$2`).
      let j = i + 1;
      while (j < n && !(line[j] === "$" && !escapedAt(line, j))) j++;
      if (j < n) {
        out.push(line.slice(i, j + 1));
        i = j + 1;
        continue;
      }
      out.push(ch);
      i++;
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
      out.push(line.slice(i, j + 1));
      i = j + 1;
    } else {
      out.push("\\$");
      i++;
    }
  }
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
  const out: string[] = [];
  let pos = 0;
  for (const m of matchAllAfter(MATH_SPAN_RE, text, MATH_SPAN_BLOCKED)) {
    out.push(decodeProseEscapes(text.slice(pos, m.index)));
    out.push(m[0]);
    pos = m.index + m[0].length;
  }
  out.push(decodeProseEscapes(text.slice(pos)));
  return out.join("");
}

// ---------------------------------------------------------------------------
// pipeline
// ---------------------------------------------------------------------------

/**
 * repair → mojibake table → delimiters → orphans → currency → escapes.
 * Idempotent, content-preserving. Non-strings are returned unchanged.
 */
export function normalize<T>(text: T): T;
export function normalize(text: unknown): unknown {
  if (typeof text !== "string" || !text) return text;
  let out: string = repair(text);
  out = fixMojibakeTable(out);
  out = normalizeDelimiters(out);
  out = stripOrphanDelimiters(out);
  out = escapeCurrency(out);
  out = decodeEscapesOutsideMath(out);
  return out;
}
