/**
 * Decode model JSON without turning its LaTeX into control characters.
 * Port of python/pupiltree_latex/json_transport.py.
 *
 * `JSON.parse` accepts a single-backslash `\frac` as the JSON escape form
 * feed + `rac` and returns the corrupted string without raising.
 * `escapeLatexForJson` doubles the backslashes that are LaTeX before the
 * parser sees them. Where a string value is "in math" is decided with the
 * same tokenizer every renderer uses (`segment`), not by `$` parity.
 */

import { matchAt } from "./chars.js";
import {
  JSON_WHITESPACE_COLLISION_COMMANDS,
  PROSE_ESCAPE_COMMANDS,
} from "./commands.js";
import { segment } from "./segment.js";

const ALPHA_RUN_RE = /[A-Za-z]+/y;

export { PROSE_ESCAPE_COMMANDS };

/**
 * True if the letters starting at `pos` form a command. Inside math the
 * whole KaTeX vocabulary decides; outside math the same vocabulary minus the
 * four names that production prose proved to be line breaks.
 */
function spellsLatexCommand(
  jsonText: string,
  pos: number,
  inMath: boolean,
): boolean {
  const m = matchAt(ALPHA_RUN_RE, jsonText, pos);
  if (!m) return false;
  // A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an escape.
  const end = pos + m[0].length;
  if (
    end < jsonText.length &&
    jsonText[end] === ":" &&
    m[0] === m[0].toLowerCase()
  )
    return true;
  const vocabulary = inMath
    ? JSON_WHITESPACE_COLLISION_COMMANDS
    : PROSE_ESCAPE_COMMANDS;
  return vocabulary.has(m[0]);
}

/**
 * Index of the closing quote of the JSON string opened at `start` (or
 * `jsonText.length` when unterminated).
 */
function stringEnd(jsonText: string, start: number): number {
  let i = start + 1;
  const n = jsonText.length;
  while (i < n) {
    const c = jsonText[i];
    if (c === "\\") {
      i += 2;
      continue;
    }
    if (c === '"') return i;
    i++;
  }
  return n;
}

/**
 * `mask[i]` is true when `body[i]` lies inside a math span, using `segment`
 * on the raw (still JSON-escaped) body: `$` positions are the same in either
 * form, and `segment` already handles `\$`.
 */
function mathMask(body: string): boolean[] {
  const mask: boolean[] = new Array<boolean>(body.length).fill(false);
  let pos = 0;
  for (const seg of segment(body)) {
    const length = seg.raw.length;
    if (seg.kind === "math") {
      for (let k = pos; k < pos + length; k++) mask[k] = true;
    }
    pos += length;
  }
  return mask;
}

const HEX = "0123456789abcdefABCDEF";

function isHexRun(s: string, from: number, to: number): boolean {
  for (let k = from; k < to; k++) if (!HEX.includes(s[k])) return false;
  return true;
}

/**
 * Escape LaTeX backslash sequences inside JSON string values.
 *
 * Inside a string value:
 *   - `\"`, `\\`, `\/`, `\uXXXX` are kept;
 *   - `\n` `\t` `\r` stay JSON escapes unless the letters after the
 *     backslash spell a command (see `spellsLatexCommand`);
 *   - `\b` and `\f` are ALWAYS LaTeX (backspace and form feed never occur in
 *     lesson text);
 *   - any other backslash + letter is doubled; backslash + digit or space is
 *     kept; anything else is doubled.
 */
export function escapeLatexForJson(jsonText: string): string {
  const out: string[] = [];
  const n = jsonText.length;
  let i = 0;
  while (i < n) {
    const c = jsonText[i];
    if (c !== '"') {
      out.push(c);
      i++;
      continue;
    }
    // A string value: copy the opening quote, then walk the body with a
    // precomputed math mask.
    const end = stringEnd(jsonText, i);
    const body = jsonText.slice(i + 1, end);
    const mask = mathMask(body);
    out.push('"');
    let j = 0;
    const m = body.length;
    while (j < m) {
      const b = body[j];
      if (b !== "\\") {
        out.push(b);
        j++;
        continue;
      }
      const nextC = j + 1 < m ? body[j + 1] : "";
      if (nextC === '"' || nextC === "\\" || nextC === "/") {
        out.push(b, nextC);
        j += 2;
        continue;
      }
      if (nextC === "u" && j + 5 < m && isHexRun(body, j + 2, j + 6)) {
        out.push(body.slice(j, j + 6));
        j += 6;
        continue;
      }
      const inMath = j < m ? mask[j] : false;
      if (
        (nextC === "n" || nextC === "t" || nextC === "r") &&
        !spellsLatexCommand(body, j + 1, inMath)
      ) {
        out.push(b, nextC);
        j += 2;
        continue;
      }
      // Every other backslash is LaTeX (`\\ ` is a spacing command, `\\1`
      // a macro argument, `\\{` a brace); neither is a JSON escape, so
      // leaving them would make the parser raise.
      out.push("\\\\");
      j++;
    }
    if (end < n) out.push('"');
    i = end + 1;
  }
  return out.join("");
}

const RAW_CONTROL_RE = /[\x00-\x1f]/;

/**
 * Python's `json.loads(strict=False)` accepts raw control characters inside
 * string values (models emit raw newlines and tabs, and those are content).
 * `JSON.parse` does not, so they are re-escaped before parsing. Outside a
 * string value nothing is touched: a control character there is a syntax
 * error in both parsers.
 */
function escapeRawControlsInStrings(jsonText: string): string {
  if (!RAW_CONTROL_RE.test(jsonText)) return jsonText;
  const out: string[] = [];
  const n = jsonText.length;
  let i = 0;
  while (i < n) {
    const c = jsonText[i];
    if (c !== '"') {
      out.push(c);
      i++;
      continue;
    }
    const end = stringEnd(jsonText, i);
    out.push('"');
    for (let j = i + 1; j < end; j++) {
      const ch = jsonText[j];
      const code = ch.charCodeAt(0);
      if (code < 0x20) {
        if (ch === "\n") out.push("\\n");
        else if (ch === "\t") out.push("\\t");
        else if (ch === "\r") out.push("\\r");
        else out.push("\\u" + code.toString(16).padStart(4, "0"));
      } else {
        out.push(ch);
      }
    }
    if (end < n) out.push('"');
    i = end + 1;
  }
  return out.join("");
}

function parseLenient(jsonText: string): unknown {
  return JSON.parse(escapeRawControlsInStrings(jsonText));
}

/**
 * `JSON.parse` for model output that may carry single-backslash LaTeX.
 * Lenient like Python's `strict=False`: raw newlines and tabs inside string
 * values are content, not errors. Falls back to the plain decode and throws
 * what that throws (`SyntaxError`).
 */
export function loadsLatexAware(jsonText: string): unknown {
  try {
    return parseLenient(escapeLatexForJson(jsonText));
  } catch (err) {
    if (!(err instanceof SyntaxError)) throw err;
    return parseLenient(jsonText);
  }
}

/** Options of `loadsModelJson`. */
export interface LoadsModelJsonOptions {
  /**
   * `true` (the default, tag `v140-b12`): `escapeLatexForJson` first, so a
   * backslash that is not a JSON escape (`\q`, `\frac`, `\alpha`) is doubled
   * and read as a literal backslash instead of failing, and raw newlines and
   * tabs inside string values are content. `false`: a plain strict
   * `JSON.parse`.
   */
  lenient?: boolean;
}

/**
 * Transport-only decode for model JSON. No fallback, no sanitiser — invalid
 * JSON throws `SyntaxError` either way.
 */
export function loadsModelJson(
  jsonText: string,
  options: LoadsModelJsonOptions = {},
): unknown {
  if (options.lenient === false) return JSON.parse(jsonText);
  return parseLenient(escapeLatexForJson(jsonText));
}
