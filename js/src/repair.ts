/**
 * `repair`: undo JSON-escape damage to LaTeX commands, drop other C0 bytes.
 *
 * A parser that reads `\frac` as the JSON escape `\f` stores form feed +
 * "rac"; `\times` becomes TAB + "imes". This is the one function that is
 * safe on ANY content: every DB write sink, every read path and every client
 * runs it. Port of python/pupiltree_latex/repair.py.
 */

import { charAt, isAlpha, matchAt } from "./chars.js";
import {
  JSON_WHITESPACE_COLLISION_COMMANDS,
  KATEX_COMMANDS,
  LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
  SCRIPT_LABELS,
} from "./commands.js";

const WHITESPACE_LETTER: Readonly<Record<string, string>> = {
  "\t": "t",
  "\n": "n",
  "\r": "r",
};
const ALPHA_RUN_RE = /[A-Za-z]+/y;
// Every C0 control except TAB, LF, CR — plus DEL.
const OTHER_CONTROL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const ANY_CONTROL_RE = /[\x00-\x1f\x7f]/;

/**
 * The one letter in n/t/r for which `letter + run` is a KaTeX command, or
 * "" when none or more than one fits (`ightarrow` → "r").
 */
function onlyCommandReading(run: string): string {
  const fits = [..."ntr"].filter((c) =>
    JSON_WHITESPACE_COLLISION_COMMANDS.has(c + run),
  );
  return fits.length === 1 ? fits[0] : "";
}

/** Positions of every unescaped `$`. */
function dollarPositions(text: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "$" && (i === 0 || text[i - 1] !== "\\")) out.push(i);
  }
  return out;
}

/**
 * Restore control characters that were LaTeX commands; drop the rest.
 *
 * - U+0008 → `\b` and U+000C → `\f` when a letter follows.
 * - U+000B → `\v` when `v` + the following letters is a KaTeX command.
 * - TAB / LF / CR → `\t` / `\n` / `\r` only when `guessWhitespace` and the
 *   following letters spell a command in `LATEX_COMMANDS_BEHIND_JSON_ESCAPES`,
 *   a lesson-script label (`<TAB>eacher:`), or — inside a closed `$…$` span
 *   (odd count of unescaped `$` before and one after) with three or more
 *   letters — a command under exactly one of the three letters; otherwise
 *   they are kept.
 * - Any other C0 control and DEL is removed.
 *
 * `guessWhitespace=false` is the read-path form (Backend #1595): stored bytes
 * are served with only the two unconditional repairs applied. Idempotent;
 * non-strings are returned unchanged.
 */
export function repair<T>(text: T, guessWhitespace?: boolean): T;
export function repair(text: unknown, guessWhitespace = true): unknown {
  if (typeof text !== "string" || !text) return text;
  if (!ANY_CONTROL_RE.test(text)) return text;
  const out: string[] = [];
  const n = text.length;
  let dollars: number[] | null = null;
  const inClosedSpan = (pos: number): boolean => {
    if (dollars === null) dollars = dollarPositions(text);
    let before = 0;
    let after = false;
    for (const k of dollars) {
      if (k < pos) before++;
      else after = true;
    }
    return before % 2 === 1 && after;
  };
  for (let i = 0; i < n; i++) {
    const ch = text[i];
    if (ch === "\x08" || ch === "\x0c") {
      // Restored only when a letter follows: a bare form feed has no command
      // to go back to and is dropped with the other C0 bytes.
      if (i + 1 < n && isAlpha(charAt(text, i + 1))) {
        out.push(ch === "\x08" ? "\\b" : "\\f");
      } else {
        out.push(ch);
      }
    } else if (ch === "\x0b") {
      const m = matchAt(ALPHA_RUN_RE, text, i + 1);
      if (m && KATEX_COMMANDS.has("v" + m[0])) {
        out.push("\\v");
      } else {
        out.push(ch); // dropped by the final strip
      }
    } else if (ch in WHITESPACE_LETTER && guessWhitespace) {
      const letter = WHITESPACE_LETTER[ch];
      const m = matchAt(ALPHA_RUN_RE, text, i + 1);
      const run = m ? m[0] : "";
      const runEnd = i + 1 + run.length;
      if (run && LATEX_COMMANDS_BEHIND_JSON_ESCAPES.has(letter + run)) {
        out.push("\\" + letter);
      } else if (
        run &&
        runEnd < n &&
        text[runEnd] === ":" &&
        SCRIPT_LABELS.has(letter + run)
      ) {
        // `<TAB>eacher:` / `<LF>ead:` — a decoded lesson-script label.
        out.push("\\" + letter);
      } else if (
        run &&
        run.length >= 3 &&
        inClosedSpan(i) &&
        onlyCommandReading(run)
      ) {
        // Inside a CLOSED `$…$` span a raw newline/tab is never content:
        // `$<LF>ightarrow$` can only have been `\rightarrow`. Three letters
        // minimum, as for the audit: `$<LF>o` is not `\to`.
        out.push("\\" + onlyCommandReading(run));
      } else {
        out.push(ch);
      }
    } else {
      out.push(ch);
    }
  }
  return out.join("").replace(OTHER_CONTROL_RE, "");
}

export function isPlainObject(
  value: unknown,
): value is Record<string, unknown> {
  if (value === null || typeof value !== "object") return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * `repair` over every string in a JSON-like document (plain objects and
 * arrays). No key skipping is needed: the repair cannot damage an id, a URL
 * or a timestamp. Anything else (numbers, Dates, class instances) is
 * returned as is.
 */
export function repairDeep<T>(obj: T, guessWhitespace = true): T {
  return repairDeepAny(obj, guessWhitespace) as T;
}

function repairDeepAny(obj: unknown, guessWhitespace: boolean): unknown {
  if (typeof obj === "string") return repair(obj, guessWhitespace);
  if (Array.isArray(obj))
    return obj.map((v) => repairDeepAny(v, guessWhitespace));
  if (isPlainObject(obj)) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj))
      out[k] = repairDeepAny(v, guessWhitespace);
    return out;
  }
  return obj;
}
