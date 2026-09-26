/**
 * `wrapUnicodeChemistry`: Unicode chemistry in prose (`H₂O`, `SO₄²⁻`,
 * `Fe³⁺`) becomes the canonical `$\text{H}_{2}\text{O}$` form.
 *
 * Runs on TEXT segments only (math segments are left untouched). A run is a
 * maximal `[A-Za-z0-9()]` / script-character sequence that starts with an
 * uppercase letter (after an optional coefficient) at a word boundary and
 * carries a subscript digit or a charge (a superscript run ending in ⁺ or
 * ⁻), so `10⁸`, `mc²`, `x₁` and `H2O` are not touched while `2H₂O` is.
 */

import { charAt, isDigit } from "./chars.js";
import { afterCodePoint, replaceAfter } from "./lookbehind.js";
import { segment } from "./segment.js";

const SUB_DIGITS = "₀-₉";
const SUP_DIGITS = "⁰¹²³⁴-⁹";
const SUP_SIGNS = "⁺⁻";
const SCRIPT = SUB_DIGITS + SUP_DIGITS + SUP_SIGNS;

// Not after a letter, digit or `_` (RUN_BLOCKED, a code-point test).
const RUN_BLOCKED = afterCodePoint(/[\p{L}\p{N}_]/u);
const RUN_RE = new RegExp(
  "[0-9]*[a-z]?(?=[A-Z])[A-Za-z0-9()]*[" +
    SCRIPT +
    "][A-Za-z0-9()" +
    SCRIPT +
    "]*",
  "gu",
);
const SUB_RE = new RegExp("[" + SUB_DIGITS + "]");
// A charge: any ⁺ / ⁻ in the run (Python `[⁰¹²³⁴⁵⁶⁷⁸⁹]*[⁺⁻]`, searched).
const CHARGE_RE = new RegExp("[" + SUP_SIGNS + "]");
const PIECE_RE = new RegExp(
  "[A-Za-z0-9()]+|[" + SUB_DIGITS + "]+|[" + SUP_DIGITS + SUP_SIGNS + "]+",
  "gu",
);
const TRIGGER_RE = new RegExp("[" + SCRIPT + "]");

const SUB_MAP: Readonly<Record<string, string>> = {
  "₀": "0",
  "₁": "1",
  "₂": "2",
  "₃": "3",
  "₄": "4",
  "₅": "5",
  "₆": "6",
  "₇": "7",
  "₈": "8",
  "₉": "9",
};
const SUP_MAP: Readonly<Record<string, string>> = {
  "⁰": "0",
  "¹": "1",
  "²": "2",
  "³": "3",
  "⁴": "4",
  "⁵": "5",
  "⁶": "6",
  "⁷": "7",
  "⁸": "8",
  "⁹": "9",
  "⁺": "+",
  "⁻": "-",
};

function mapChars(s: string, table: Readonly<Record<string, string>>): string {
  let out = "";
  for (const ch of s) out += table[ch] ?? ch;
  return out;
}

function countChar(s: string, ch: string): number {
  let n = 0;
  for (const c of s) if (c === ch) n++;
  return n;
}

function convertRun(run: string): string {
  let out = "";
  for (const piece of run.match(PIECE_RE) ?? []) {
    const first = piece[0];
    if (first in SUB_MAP) out += "_{" + mapChars(piece, SUB_MAP) + "}";
    else if (first in SUP_MAP) out += "^{" + mapChars(piece, SUP_MAP) + "}";
    else out += "\\text{" + piece + "}";
  }
  return "$" + out + "$";
}

function isChemistryRun(run: string): boolean {
  return SUB_RE.test(run) || CHARGE_RE.test(run);
}

/**
 * One space around a new span where a neighbour would break it (spec §0.1):
 * a literal `$` right before or after (`$$` opens display math), or a digit
 * right after (a closer followed by a digit is not a closer). `end` null
 * pads the front only.
 */
export function padSpan(
  text: string,
  start: number,
  end: number | null,
  span: string,
): string {
  if (
    start > 0 &&
    text[start - 1] === "$" &&
    (start < 2 || text[start - 2] !== "\\")
  )
    span = " " + span;
  if (end !== null && end < text.length) {
    const nxt = charAt(text, end);
    if (nxt === "$" || isDigit(nxt)) span += " ";
  }
  return span;
}

function wrapInProse(text: string): string {
  if (!TRIGGER_RE.test(text)) return text;
  return replaceAfter(
    text,
    RUN_RE,
    RUN_BLOCKED,
    (match: string, offset: number) => {
      let run = match;
      const before = offset > 0 ? text[offset - 1] : "";
      if (before === "\\" || before === "{") return run; // defensive: never inside a command or group
      if (!isChemistryRun(run)) return run;
      // A closing paren that belongs to the prose (`(H₂O)`) is not part of
      // the formula: unbalanced trailing `)` go back after the span.
      let trailing = "";
      while (run.endsWith(")") && countChar(run, ")") > countChar(run, "(")) {
        run = run.slice(0, -1);
        trailing += ")";
      }
      const span = convertRun(run);
      if (trailing) return padSpan(text, offset, null, span) + trailing;
      return padSpan(text, offset, offset + match.length, span);
    },
  );
}

/**
 * Wrap Unicode chemistry outside math in `$…$` with `\text{}`, `_{}` and
 * `^{}`: `H₂O` → `$\text{H}_{2}\text{O}$`, `Fe³⁺` → `$\text{Fe}^{3+}$`.
 * Idempotent; non-strings and the empty string pass through.
 */
export function wrapUnicodeChemistry<T>(text: T): T;
export function wrapUnicodeChemistry(text: unknown): unknown {
  if (typeof text !== "string" || !text) return text;
  if (!TRIGGER_RE.test(text)) return text;
  let out = "";
  for (const seg of segment(text)) {
    // Text segments are rewritten on their raw slice so `\$` stays escaped.
    out += seg.kind === "math" ? seg.raw : wrapInProse(seg.raw);
  }
  return out;
}
