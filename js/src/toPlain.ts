/**
 * `toPlain`: LaTeX to plain Unicode text for PDFs, canvases, grading and
 * TTS. Port of python/pupiltree_latex/to_plain.py (Backend
 * `latex_to_plain` for the `text` / `pdf` styles, the agents' TTS cleaner
 * for `tts`).
 */

import {
  charAt,
  codePointLength,
  escapeRegExp,
  isAlnum,
  isDigit,
  lstripChars,
  matchAt,
  pyStrip,
  rstripChars,
} from "./chars.js";
import { currencyPositions, trimPaddedSpansKeepCurrency } from "./normalize.js";
import { repair } from "./repair.js";
import { segment } from "./segment.js";
import { mathMask } from "./spans.js";
import {
  fixMojibakeCore,
  fixMojibakeTable,
  unescapeHtmlEntities,
} from "./mojibake.js";
import {
  COMPARE_FOLD,
  ELEMENT_SYMBOLS,
  KATEX_COMMANDS,
  LATEX_CMD_MAP,
  SCRIPT_LABELS,
} from "./tables.g.js";

export { COMPARE_FOLD, ELEMENT_SYMBOLS, LATEX_CMD_MAP };

function charMap(from: string, to: string): ReadonlyMap<string, string> {
  const a = [...from];
  const b = [...to];
  if (a.length !== b.length) throw new Error("charMap: length mismatch");
  return new Map(a.map((ch, i) => [ch, b[i]]));
}

// Python `str.maketrans` tables: untranslatable characters fall through.
const SUPERSCRIPT_MAP = charMap("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ");
const SUBSCRIPT_MAP = charMap(
  "0123456789+-=()aeoxhklmnpst",
  "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ",
);

function translate(s: string, table: ReadonlyMap<string, string>): string {
  let out = "";
  for (const ch of s) out += table.get(ch) ?? ch;
  return out;
}

// `\{`, `\}` and `\$` are literal characters, not grouping or maths
// delimiters. They are parked as sentinels for the duration of the
// transform and restored at the end.
// Single private-use characters (U+E010–U+E014): one code unit, so an
// argument reader can never take half of one (`$\binom$"}`).
const LBRACE_SENTINEL = "";
const RBRACE_SENTINEL = "";
const DOLLAR_SENTINEL = "";
const LABEL_SENTINEL_OPEN = "";
const LABEL_SENTINEL_CLOSE = "";

// A lesson-script label at the start of a line (`\instruction:`): parked
// before the command scanner, which read `\instruction` as `\in` +
// "struction". `text` keeps it verbatim; `pdf` and `compare` drop the
// backslash, as `tts` always did.
const SCRIPT_LABEL_LINE_RE = /(^|\n)([ \t]*)\\([a-z][a-z_]*):/g;
// Anywhere in a line, only a word in `SCRIPT_LABELS` is a label.
const SCRIPT_LABEL_ANY_RE = /\\([a-z][a-z_]*):/g;

// Math spans for the prose-brace pass, display first.
const PLAIN_SPAN_RE = /\$\$[\s\S]+?\$\$|\$[^$]+\$/g;

/** Index of the `}` closing the `{` at `k`, or -1 (math positions skipped). */
function matchingBrace(s: string, k: number, skip: Uint8Array): number {
  let depth = 0;
  for (let j = k; j < s.length; j++) {
    if (skip[j]) continue;
    if (s[j] === "{") depth++;
    else if (s[j] === "}") {
      depth--;
      if (depth === 0) return j;
    }
  }
  return -1;
}

/** The name of the `\name` whose last letter is `s[end - 1]`, or null. */
function commandNameEndingAt(s: string, end: number): string | null {
  let j = end;
  while (j > 0 && /[A-Za-z]/.test(s[j - 1])) j--;
  if (j < end && j > 0 && s[j - 1] === "\\") return s.slice(j, end);
  return null;
}

/**
 * True when the `{` at `k` is a command or script argument: right after
 * `^`/`_`, a `\name`, the `]` of an optional argument that follows a
 * `\name`, or the `}` of another argument; or after spaces when the command
 * takes arguments (`\frac {a}{b}`).
 */
function attachedBrace(s: string, k: number, closes: Set<number>): boolean {
  if (k === 0) return false;
  const prev = s[k - 1];
  if (prev === "^" || prev === "_" || closes.has(k - 1)) return true;
  if (prev === "]") {
    const opener = s.lastIndexOf("[", k - 2);
    return opener > 0 && commandNameEndingAt(s, opener) !== null;
  }
  if (prev === " " || prev === "\t") {
    let j = k - 1;
    while (j > 0 && (s[j - 1] === " " || s[j - 1] === "\t")) j--;
    const name = commandNameEndingAt(s, j);
    return name !== null && ARGUMENT_TAKING_CMDS.has(name);
  }
  return commandNameEndingAt(s, k) !== null;
}

// A prose brace pair is a literal set / JSON object when its content holds
// one of these (a list or key separator).
const LITERAL_BRACE_HINTS = /[,:;|]/;

/**
 * Braces in prose (outside `$…$`/`$$…$$` and not a command or script
 * argument) whose content is a list or object (`A = {1, 2, 3}`,
 * `{"central": …}`) are text: they are parked as the `\{`/`\}` sentinels.
 * `1{,}000` and `{x}` are still grouping, an unclosed `{` is kept, and a
 * `}` with no opener is dropped as before.
 */
function protectProseBraces(s: string): string {
  if (!s.includes("{")) return s;
  const n = s.length;
  const inMath = new Uint8Array(n);
  PLAIN_SPAN_RE.lastIndex = 0;
  for (const m of s.matchAll(PLAIN_SPAN_RE)) {
    for (let j = m.index!; j < m.index! + m[0].length; j++) inMath[j] = 1;
  }
  const chars = s.split("");
  const closes = new Set<number>();
  let k = 0;
  while (k < n) {
    if (inMath[k] || s[k] !== "{") {
      k++;
      continue;
    }
    const close = matchingBrace(s, k, inMath);
    if (attachedBrace(s, k, closes)) {
      if (close === -1) break;
      closes.add(close);
      k = close + 1;
      continue;
    }
    if (close === -1) {
      chars[k] = LBRACE_SENTINEL;
      k++;
      continue;
    }
    const inner = s.slice(k + 1, close);
    if (codePointLength(inner) <= 1 || !LITERAL_BRACE_HINTS.test(inner)) {
      k = close + 1; // `{,}`, `{x}`: grouping
      continue;
    }
    chars[k] = LBRACE_SENTINEL;
    chars[close] = RBRACE_SENTINEL;
    k++;
  }
  return chars.join("");
}

const LATEX_DISPLAY_DOLLAR_RE = /\$\$([\s\S]+?)\$\$/g;
const LATEX_DELIM_RE = /\$([^$]+)\$/g;
const IMAGE_MARKER_RE = /\{\{IMAGE:[^}]+\}\}/g;
// `$5`, `$1,200.50`: a dollar before an amount that is not followed by a
// letter, a command or a script (`$45m`, `$4\sqrt{3}` are cut-off spans).
const CURRENCY_AT_RE = /\$[0-9]+(?:[.,][0-9]+)*(?![0-9A-Za-z\\^_{])/y;

/**
 * Park the amounts (tag `audit5-1`): a dollar outside every `segment` math
 * span that `escapeCurrency` reads as money (`Rs $5 and $10`: the closer is
 * followed by a digit; `costs $5.`: no closer) and that is followed by an
 * amount, not by a letter or a command (`$45m`, `$4\sqrt3` are cut-off
 * spans). It becomes the literal-dollar sentinel, so the delimiter strip
 * can no longer pair it with another amount.
 */
function parkCurrencyDollars(s: string): string {
  if (!s.includes("$")) return s;
  const money = currencyPositions(s);
  if (money.length === 0) return s;
  const inMath = mathMask(s);
  const chars = s.split("");
  for (const k of money) {
    if (!inMath[k] && matchAt(CURRENCY_AT_RE, s, k)) chars[k] = DOLLAR_SENTINEL;
  }
  return chars.join("");
}
// (`\$5\)` is an amount inside `\(…\)`: a closing delimiter is not a unit.)
const ESCAPED_CUT_OFF_DOLLAR_RE =
  /\\\$(?=[0-9]+(?:[.,][0-9]+)*(?:[A-Za-z^_{]|\\[A-Za-z]))/g;

const ELEMENTS: ReadonlySet<string> = ELEMENT_SYMBOLS;
const SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉";

function isAsciiWordChar(ch: string): boolean {
  return (
    (ch >= "a" && ch <= "z") ||
    (ch >= "A" && ch <= "Z") ||
    (ch >= "0" && ch <= "9") ||
    ch === "_"
  );
}

function isDigitChar(ch: string | undefined): boolean {
  return ch !== undefined && ch >= "0" && ch <= "9";
}

/** A digit subscript at `i` (`_2`, `_{12}`): its digits and the index after it. */
function chemDigits(s: string, i: number): [string, number] {
  if (s[i] !== "_") return ["", i];
  const j = i + 1;
  if (s[j] === "{") {
    let k = j + 1;
    while (isDigitChar(s[k])) k++;
    if (k > j + 1 && s[k] === "}") return [s.slice(j + 1, k), k + 1];
    return ["", i];
  }
  let k = j;
  while (isDigitChar(s[k])) k++;
  return k > j ? [s.slice(j, k), k] : ["", i];
}

/** Index after the element symbol at `i` (two letters first), or -1. */
function chemElement(s: string, i: number): number {
  const c = s[i];
  if (c !== undefined && c >= "A" && c <= "Z") {
    const d = s[i + 1];
    if (d !== undefined && d >= "a" && d <= "z" && ELEMENTS.has(c + d))
      return i + 2;
    if (ELEMENTS.has(c)) return i + 1;
  }
  return -1;
}

/** Element symbols, `(…)` groups and digit subscripts from `i`. */
function chemToken(s: string, i: number, depth = 0): [string, number, number] {
  let out = "";
  let subs = 0;
  while (i < s.length) {
    if (s[i] === "(" && depth === 0) {
      const [inner, j, innerSubs] = chemToken(s, i + 1, 1);
      if (!inner || s[j] !== ")") break;
      out += "(" + inner + ")";
      subs += innerSubs;
      i = j + 1;
    } else {
      const j = chemElement(s, i);
      if (j < 0) break;
      out += s.slice(i, j);
      i = j;
    }
    const [digits, j] = chemDigits(s, i);
    if (digits) {
      for (const d of digits) out += SUBSCRIPT_DIGITS[d.charCodeAt(0) - 48];
      subs++;
      i = j;
    }
  }
  return [out, i, subs];
}

/**
 * `H_2SO_4` → `H₂SO₄`, `Ca(OH)_2` → `Ca(OH)₂` in prose (tag `v140-a9`).
 * A run of element symbols (`ELEMENT_SYMBOLS`) and `(…)` groups with digit
 * subscripts, at least one; no ASCII letter, digit, `_` or `\` before it,
 * no ASCII letter, digit or `_` after it, never inside a math span. So
 * `lo_0`, `v_avg`, `E_1`, `fallback_factual_error` and `XH_2O_id` stay.
 */
export function bareChemistryToUnicode(text: string): string {
  if (!text.includes("_")) return text;
  let mask: boolean[] | null = null;
  let out = "";
  let last = 0;
  let changed = false;
  let i = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (!((ch >= "A" && ch <= "Z") || ch === "(")) {
      i++;
      continue;
    }
    const prev = i > 0 ? text[i - 1] : "";
    if (prev && (isAsciiWordChar(prev) || prev === "\\")) {
      i++;
      continue;
    }
    const [converted, end, subs] = chemToken(text, i);
    const nxt = end < n ? text[end] : "";
    if (!subs || (nxt && isAsciiWordChar(nxt))) {
      i++;
      continue;
    }
    if (mask === null) mask = mathMask(text);
    if (mask[i]) {
      i = end;
      continue;
    }
    out += text.slice(last, i) + converted;
    last = i = end;
    changed = true;
  }
  return changed ? out + text.slice(last) : text;
}

// A literal `\n` escape that survived into the stored string. Only fires
// before an uppercase letter or whitespace, so the real commands that start
// with "n" (\nu, \neq, \nabla, \notin) are untouched.
const LATEX_NEWLINE_ESCAPE_RE = /\\n(?=[A-Z\s]|$)/g;

// A control word. A run of backslashes before the letters is one command.
const LATEX_CMD_RE = /\\+([A-Za-z]+)/y;
const LATEX_ENV_TOKEN_RE = /\\(begin|end)\s*\{([^{}]*)\}/y;
const LATEX_ENV_TOKEN_SCAN_RE = /\\(begin|end)\s*\{([^{}]*)\}/g;

const FRAC_CMDS = new Set(["frac", "dfrac", "tfrac", "cfrac"]);
const BINOM_CMDS = new Set(["binom", "dbinom", "tbinom"]);
// Wrappers whose only job is styling or chemistry markup — the inner
// content is the answer.
const WRAPPER_CMDS = new Set([
  "text",
  "textit",
  "textbf",
  "textrm",
  "textsf",
  "texttt",
  "textsc",
  "textup",
  "textnormal",
  "mathrm",
  "mathit",
  "mathbf",
  "mathsf",
  "mathtt",
  "mathbb",
  "mathcal",
  "mathfrak",
  "mathscr",
  "boldsymbol",
  "bm",
  "operatorname",
  "emph",
  "mbox",
  "hbox",
  "ce",
  "boxed",
  "fbox",
  "cancel",
  "bcancel",
  "xcancel",
  "sout",
  "underbrace",
  "overbrace",
  "pu",
]);
// `\color{red}{5}` / `\textcolor{red}{5}`: the colour name is styling and the
// second argument is the content. `\color{red} 5` (a switch) keeps what follows.
const COLOR_CMDS = new Set(["color", "textcolor", "colorbox"]);
// Layout with no reading value: the command AND its argument go.
const DROP_WITH_ARG_CMDS = new Set([
  "hspace",
  "vspace",
  "phantom",
  "hphantom",
  "vphantom",
  "label",
  "tag",
  "kern",
  "mkern",
  "mspace",
  "hskip",
]);
// Accents: [combining mark, name]. By default the base symbol is kept and
// the accent dropped; the `pdf` style asks for `markAccents`.
const ACCENT_CMDS: ReadonlyMap<string, [string, string]> = new Map([
  ["vec", ["⃗", "vec"]],
  ["overrightarrow", ["⃗", "vec"]],
  ["overleftarrow", ["⃖", "vec"]],
  ["hat", ["̂", "hat"]],
  ["widehat", ["̂", "hat"]],
  ["bar", ["̄", "bar"]],
  ["overline", ["̅", "bar"]],
  ["dot", ["̇", "dot"]],
  ["ddot", ["̈", "ddot"]],
  ["tilde", ["̃", "tilde"]],
  ["widetilde", ["̃", "tilde"]],
]);
const PLAIN_ACCENT_CMDS = new Set([
  "check",
  "breve",
  "acute",
  "grave",
  "underline",
  "mathring",
]);
// `\left.` / `\right.` are invisible delimiters; every sizing command is
// dropped and the delimiter it sizes kept.
const SIZING_CMDS = new Set([
  "left",
  "right",
  "big",
  "Big",
  "bigg",
  "Bigg",
  "bigl",
  "bigr",
  "Bigl",
  "Bigr",
  "biggl",
  "biggr",
  "Biggl",
  "Biggr",
  "middle",
]);
const DROP_CMDS = new Set([
  "hline",
  "nonumber",
  "notag",
  "textstyle",
  "scriptstyle",
  "displaystyle",
  "scriptscriptstyle",
]);
const MATRIX_ENVS: ReadonlyMap<string, [string, string]> = new Map([
  ["matrix", ["[", "]"]],
  ["pmatrix", ["[", "]"]],
  ["bmatrix", ["[", "]"]],
  ["Bmatrix", ["[", "]"]],
  ["smallmatrix", ["[", "]"]],
  ["array", ["[", "]"]],
  ["vmatrix", ["|", "|"]],
  ["Vmatrix", ["‖", "‖"]],
]);
// Characters that read correctly as a superscript without a Unicode script
// form: primes and the degree sign (`0^\circ` → `0°`).
// Commands whose `{…}` argument may follow after spaces (prose-brace pass).
const ARGUMENT_TAKING_CMDS: ReadonlySet<string> = new Set([
  ...FRAC_CMDS,
  ...BINOM_CMDS,
  ...WRAPPER_CMDS,
  ...COLOR_CMDS,
  ...DROP_WITH_ARG_CMDS,
  ...ACCENT_CMDS.keys(),
  ...PLAIN_ACCENT_CMDS,
  "sqrt",
  "begin",
  "end",
]);

const SCRIPT_PASSTHROUGH = new Set("°′″‴");
const SUPERSCRIPT_CHARS = new Set("0123456789+-=()ni");
const SUBSCRIPT_CHARS = new Set("0123456789+-=()aeoxhklmnpst");
const SINGLE_TOKEN_RE = /^(?:\d+(?:\.\d+)?|[\s\S])$/u;
const SCRIPT_SPACE_RE = /\s*([^\p{L}\p{N}_\s])\s*/gu;

function every(s: string, set: ReadonlySet<string>): boolean {
  for (const ch of s) if (!set.has(ch)) return false;
  return true;
}

/**
 * `s[i]` is `{`: return the balanced inner text (any depth) and the index
 * after its closing brace. An unclosed group runs to the end.
 */
function readGroup(s: string, i: number): [string, number] {
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "{") depth++;
    else if (s[j] === "}") {
      depth--;
      if (depth === 0) return [s.slice(i + 1, j), j + 1];
    }
  }
  return [s.slice(i + 1), s.length];
}

/**
 * One macro argument at `i` (leading spaces skipped, as in LaTeX): a braced
 * group, a control word, or a single character.
 */
function readArg(s: string, i: number): [string | null, number] {
  let j = i;
  while (j < s.length && (s[j] === " " || s[j] === "\t")) j++;
  if (j >= s.length || s[j] === "}") return [null, i];
  if (s[j] === "{") return readGroup(s, j);
  const m = matchAt(LATEX_CMD_RE, s, j);
  if (m) return [m[0], j + m[0].length];
  return [s[j], j + 1];
}

// A fraction part that stays bare: a number or one letter (`22`, `3.5`,
// `x`, `π`); Python `[0-9]+(?:\.[0-9]+)?|[^\W\d_]`.
const SIMPLE_FRACTION_PART_RE =
  /^(?:[0-9]+(?:\.[0-9]+)?|[\p{L}\p{Nl}\p{No}])$/u;

/**
 * A numerator or denominator: a single token or one parenthesised group
 * stays bare; anything compound gets parentheses (`(a+b)`).
 */
// A negative number is a simple NUMERATOR too: `\frac{-1}{4}` → `-1/4`
// (tag `v140-a5`); a negative denominator keeps its parentheses (`1/(-4)`).
const SIGNED_NUMBER_RE = /^[-−][0-9]+(?:\.[0-9]+)?$/;

function fractionPart(part: string, numerator = false): string {
  const core = pyStrip(part);
  if (numerator && SIGNED_NUMBER_RE.test(core)) return core;
  if (SIMPLE_FRACTION_PART_RE.test(core) || isWrapped(core)) return core;
  return "(" + part + ")";
}

/**
 * `2\frac{1}{2}` and `\frac{1}{2}x` read `2(1/2)` and `(1/2)x`: a fraction
 * touching a term (a letter or digit or `/` before it; a letter, digit, `(`,
 * `\`, `^`, `_` or `{` after it) is parenthesised.
 */
function fractionNeedsParens(out: string[], s: string, i: number): boolean {
  let prev = "";
  for (let k = out.length - 1; k >= 0; k--) {
    if (out[k]) {
      const cps = Array.from(out[k]);
      prev = cps[cps.length - 1];
      break;
    }
  }
  let nxt = charAt(s, i);
  // A closing `\)` / `\]` ends the formula; it is not a term (`v140-a3`).
  if (nxt === "\\" && (s[i + 1] === ")" || s[i + 1] === "]")) nxt = "";
  return (
    isAlnum(prev) ||
    prev === "/" ||
    isAlnum(nxt) ||
    (nxt !== "" && "(\\^_{".includes(nxt))
  );
}

/** True when `body` is one parenthesised group: "(a+b)", not "(a)/(b)". */
function isWrapped(body: string): boolean {
  if (!(body.startsWith("(") && body.endsWith(")"))) return false;
  let depth = 0;
  for (let k = 0; k < body.length; k++) {
    const ch = body[k];
    if (ch === "(") depth++;
    else if (ch === ")") depth--;
    if (depth === 0 && k < body.length - 1) return false;
  }
  return depth === 0;
}

/**
 * Render a converted sub/superscript body. Unicode script characters only
 * when EVERY character has one — a half-converted "vₐvg" reads as a
 * different word — otherwise `_x` / `_(avg)`.
 */
function script(body: string, marker: string): string {
  body = pyStrip(body.replace(SCRIPT_SPACE_RE, (_m, ch: string) => ch));
  if (!body) return "";
  const chars = marker === "^" ? SUPERSCRIPT_CHARS : SUBSCRIPT_CHARS;
  const table = marker === "^" ? SUPERSCRIPT_MAP : SUBSCRIPT_MAP;
  if (marker === "^" && every(body, SCRIPT_PASSTHROUGH)) return body;
  if (every(body, chars)) return translate(body, table);
  if (codePointLength(body) === 1) return marker + body;
  return marker + "(" + body + ")";
}

/**
 * Split an environment body into rows (`\\`) of cells (`&`) at the top
 * level — separators inside braces or a nested environment belong to that
 * inner construct.
 */
function splitTable(content: string): string[][] {
  const rows: string[][] = [];
  let cells: string[] = [];
  let buf: string[] = [];
  let depth = 0;
  let envDepth = 0;
  let i = 0;
  const n = content.length;
  while (i < n) {
    const c = content[i];
    if (c === "\\") {
      const m = matchAt(LATEX_ENV_TOKEN_RE, content, i);
      if (m) {
        envDepth += m[1] === "begin" ? 1 : -1;
        buf.push(m[0]);
        i += m[0].length;
        continue;
      }
      if (content.startsWith("\\\\", i) && depth === 0 && envDepth === 0) {
        cells.push(buf.join(""));
        rows.push(cells);
        cells = [];
        buf = [];
        i += 2;
        continue;
      }
      // Copy the escape whole so an escaped "\&" is never split on.
      buf.push(content.slice(i, i + 2));
      i += 2;
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") depth--;
    else if (c === "&" && depth === 0 && envDepth === 0) {
      cells.push(buf.join(""));
      buf = [];
      i++;
      continue;
    }
    buf.push(c);
    i++;
  }
  cells.push(buf.join(""));
  rows.push(cells);
  return rows;
}

/**
 * `pmatrix` → `[a b; c d]`, `vmatrix` → `|a b; c d|`, `cases` → `a, x>0; b,
 * x≤0`; any other environment (aligned, …) → rows joined by "; " with the
 * alignment points dropped.
 */
function environment(
  name: string,
  content: string,
  markAccents: boolean,
): string {
  const base = rstripChars(name, "*");
  if (base === "array") {
    let k = 0;
    while (k < content.length && (content[k] === " " || content[k] === "\t"))
      k++;
    if (k < content.length && content[k] === "{")
      content = content.slice(readGroup(content, k)[1]);
  }
  const rows: string[][] = [];
  for (const rawCells of splitTable(content)) {
    const cells = rawCells.map((cell) => pyStrip(convert(cell, markAccents)));
    if (cells.some((c) => c)) rows.push(cells);
  }
  const matrix = MATRIX_ENVS.get(base);
  if (matrix) {
    const [opener, closer] = matrix;
    const body = rows.map((row) => row.filter((c) => c).join(" ")).join("; ");
    return opener + body + closer;
  }
  const joiner = base === "cases" ? ", " : "";
  return rows.map((row) => row.filter((c) => c).join(joiner)).join("; ");
}

/**
 * Render control word `\name` whose arguments start at `j`. Returns the text
 * and the index after everything consumed.
 */
function command(
  name: string,
  s: string,
  j: number,
  markAccents: boolean,
): [string, number] {
  if (FRAC_CMDS.has(name) || BINOM_CMDS.has(name)) {
    let num: string | null;
    let den: string | null;
    [num, j] = readArg(s, j);
    [den, j] = readArg(s, j);
    const a = convert(num ?? "", markAccents);
    const b = convert(den ?? "", markAccents);
    if (FRAC_CMDS.has(name))
      return [fractionPart(a, true) + "/" + fractionPart(b), j];
    return ["C(" + a + ", " + b + ")", j];
  }
  if (name === "sqrt") {
    let k = j;
    while (k < s.length && (s[k] === " " || s[k] === "\t")) k++;
    let root = "√";
    if (k < s.length && s[k] === "[") {
      const close = s.indexOf("]", k);
      if (close !== -1) {
        const index = pyStrip(convert(s.slice(k + 1, close), markAccents));
        j = close + 1;
        if (index && every(index, SUPERSCRIPT_CHARS)) {
          root = translate(index, SUPERSCRIPT_MAP) + "√";
        } else if (index) {
          root = "(" + index + ")√";
        }
      }
    }
    let arg: string | null;
    [arg, j] = readArg(s, j);
    const body = convert(arg ?? "", markAccents);
    if (!body || SINGLE_TOKEN_RE.test(body) || isWrapped(body))
      return [root + body, j];
    return [root + "(" + body + ")", j];
  }
  if (WRAPPER_CMDS.has(name)) {
    let arg: string | null;
    [arg, j] = readArg(s, j);
    return [convert(arg ?? "", markAccents), j];
  }
  if (COLOR_CMDS.has(name)) {
    [, j] = readArg(s, j);
    let k = j;
    while (k < s.length && (s[k] === " " || s[k] === "\t")) k++;
    if (k < s.length && s[k] === "{") {
      let arg: string | null;
      [arg, j] = readArg(s, j);
      return [convert(arg ?? "", markAccents), j];
    }
    return ["", j];
  }
  if (DROP_WITH_ARG_CMDS.has(name)) {
    [, j] = readArg(s, j);
    return ["", j];
  }
  if (ACCENT_CMDS.has(name) || PLAIN_ACCENT_CMDS.has(name)) {
    let arg: string | null;
    [arg, j] = readArg(s, j);
    const body = convert(arg ?? "", markAccents);
    if (!markAccents || PLAIN_ACCENT_CMDS.has(name) || !body) return [body, j];
    const [combining, label] = ACCENT_CMDS.get(name)!;
    if (codePointLength(body) === 1) return [body + combining, j];
    return [label + "(" + body + ")", j];
  }
  if (SIZING_CMDS.has(name)) {
    if (j < s.length && s[j] === ".") j++;
    return ["", j];
  }
  if (DROP_CMDS.has(name)) return ["", j];
  if (name === "begin") {
    const [arg, k] = readArg(s, j);
    if (arg === null || !lstripChars(s.slice(j, k), " \t").startsWith("{"))
      return ["", j];
    const env = pyStrip(arg);
    let depth = 1;
    LATEX_ENV_TOKEN_SCAN_RE.lastIndex = k;
    let m: RegExpExecArray | null;
    while ((m = LATEX_ENV_TOKEN_SCAN_RE.exec(s)) !== null) {
      if (pyStrip(m[2]) !== env) continue;
      depth += m[1] === "begin" ? 1 : -1;
      if (depth === 0) {
        return [
          environment(env, s.slice(k, m.index), markAccents),
          m.index + m[0].length,
        ];
      }
    }
    return [environment(env, s.slice(k), markAccents), s.length];
  }
  if (name === "end") {
    const [arg, k] = readArg(s, j);
    return ["", arg !== null ? k : j];
  }
  if (Object.prototype.hasOwnProperty.call(LATEX_CMD_MAP, name))
    return [LATEX_CMD_MAP[name], j];
  // A real KaTeX command that is not in the map keeps its name as text
  // (`\\intercal` → "intercal"); it is never split (`\\neg` is not `\\ne` + g).
  if (KATEX_COMMANDS.has(name)) return [name, j];
  // `\cmd` written without a separator before the next word runs into it,
  // because the command scanner is greedy: `\colonN` matches as one command
  // named "colonN". Peel the longest known command off the front and keep
  // the remainder as text. Minimum length 2 so a stray `\cm` isn't split on
  // a one-letter name. Unknown commands lose the backslash (\foo → foo).
  for (let cut = name.length - 1; cut > 1; cut--) {
    const head = name.slice(0, cut);
    if (Object.prototype.hasOwnProperty.call(LATEX_CMD_MAP, head)) {
      return [LATEX_CMD_MAP[head] + name.slice(cut), j];
    }
  }
  return [name, j];
}

/**
 * Single left-to-right pass over maths text. Arguments are read with a
 * balanced-brace scanner and converted recursively, so nesting depth is
 * unbounded.
 */
function convert(s: string, markAccents: boolean): string {
  const out: string[] = [];
  let i = 0;
  const n = s.length;
  while (i < n) {
    const c = s[i];
    if (c === "\\") {
      const m = matchAt(LATEX_CMD_RE, s, i);
      if (m) {
        const [piece, next] = command(m[1], s, i + m[0].length, markAccents);
        out.push(
          FRAC_CMDS.has(m[1]) && fractionNeedsParens(out, s, next)
            ? "(" + piece + ")"
            : piece,
        );
        i = next;
        continue;
      }
      const nxt = i + 1 < n ? s[i + 1] : "";
      if (!nxt) {
        i++;
        continue;
      }
      if (",;:> ".includes(nxt) || nxt === "\\") {
        // Spacing commands and a `\\` line break read as one space.
        // `\!` is a NEGATIVE space and collapses to nothing.
        out.push(" ");
      } else if ("%&#_".includes(nxt)) {
        out.push(nxt);
      }
      // `\(`, `\)`, `\[`, `\]` delimiters, `\!`, and an orphan backslash
      // ("\0.008Wb" residue) all render as nothing.
      i += ",;:> \\%&#_!()[]".includes(nxt) ? 2 : 1;
      continue;
    }
    if (c === "^" || c === "_") {
      let j = i + 1;
      let raw: string;
      if (j < n && s[j] === "{") {
        [raw, j] = readGroup(s, j);
      } else if (j < n && matchAt(LATEX_CMD_RE, s, j)) {
        const m = matchAt(LATEX_CMD_RE, s, j)!;
        raw = m[0];
        j += m[0].length;
      } else if (j < n && (isAlnum(s[j]) || s[j] === "+" || s[j] === "-")) {
        raw = s[j];
        j++;
      } else {
        out.push(c);
        i++;
        continue;
      }
      out.push(script(convert(raw, markAccents), c));
      i = j;
      continue;
    }
    if (c === "{") {
      let raw: string;
      [raw, i] = readGroup(s, i);
      out.push(convert(raw, markAccents));
      continue;
    }
    if (c === "}") {
      // Unmatched closing brace: grouping residue, not content.
      i++;
      continue;
    }
    out.push(c);
    i++;
  }
  return out.join("");
}

/**
 * Convert a LaTeX-math-laced string into plain text/Unicode (Backend
 * `latex_to_plain`). With `markAccents` a one-symbol accent argument gets
 * the combining mark (F⃗) and a longer one is named (vec(AB)).
 */
export function latexToPlain(
  text: string,
  markAccents = false,
  keepLabelBackslash = true,
  force = false,
  compare = false,
  bareChemistry = false,
): string {
  if (typeof text !== "string") return text;
  if (bareChemistry) text = bareChemistryToUnicode(text);
  if (
    !force &&
    !text.includes("$") &&
    !text.includes("\\") &&
    !text.includes("{")
  )
    return text;

  let out = text;

  // `{{IMAGE:…}}` markers are not braces to strip: park them first.
  const imageStash: string[] = [];
  if (out.includes("{{IMAGE:")) {
    out = out.replace(IMAGE_MARKER_RE, (m: string) => {
      imageStash.push(m);
      return "\x00IMG" + (imageStash.length - 1) + "\x00";
    });
  }

  // Amounts outside the `segment` math spans (`Rs $5 and $10`, `costs $5.`)
  // are literal dollars, never paired as a span (tag `audit5-1`).
  out = parkCurrencyDollars(out);

  // `compare`: an escaped dollar before an amount that runs into a unit or
  // a command (`\$0.008Wb`, `\$4\sqrt{3}`) is a cut-off span's opener, not
  // money; `\$5`, `\$5 each` stay (tag `v140-a5`).
  if (compare && out.includes("\\$"))
    out = out.replace(ESCAPED_CUT_OFF_DOLLAR_RE, "");

  // Literal `\n` escapes first — before the greedy command scanner can claim
  // them as `\nStatement`-style pseudo-commands.
  out = out.replace(LATEX_NEWLINE_ESCAPE_RE, "\n");

  // Escaped braces and dollars are literal characters. Parked before the
  // delimiter passes and restored at the very end.
  out = out.split("\\$").join(DOLLAR_SENTINEL);
  out = out.split("\\{").join(LBRACE_SENTINEL);
  out = out.split("\\}").join(RBRACE_SENTINEL);

  // Lesson-script labels at a line start are not commands.
  const labels: string[] = [];
  if (out.includes("\\") && out.includes(":")) {
    out = out.replace(
      SCRIPT_LABEL_LINE_RE,
      (_m, start: string, indent: string, name: string) => {
        labels.push(name);
        return (
          start +
          indent +
          LABEL_SENTINEL_OPEN +
          (labels.length - 1) +
          LABEL_SENTINEL_CLOSE +
          ":"
        );
      },
    );
    // A known label (`SCRIPT_LABELS`, the words `repair` restores) is a
    // label anywhere: `(<TAB>ool: timer)` became `\tool:`, which the
    // scanner read as `\to` + "ol" (tag `audit5-3`).
    out = out.replace(SCRIPT_LABEL_ANY_RE, (m: string, name: string) => {
      if (!SCRIPT_LABELS.has(name)) return m;
      labels.push(name);
      return (
        LABEL_SENTINEL_OPEN + (labels.length - 1) + LABEL_SENTINEL_CLOSE + ":"
      );
    });
  }

  // Braces in prose are text (`A = {1, 2, 3}`), not grouping.
  out = protectProseBraces(out);

  // Pull maths out of `$$...$$` / `$...$` so the scanner below operates on
  // the inner content too. `\(...\)` / `\[...\]` are dropped by the scanner.
  out = out.replace(LATEX_DISPLAY_DOLLAR_RE, (_m, inner: string) => inner);
  out = out.replace(LATEX_DELIM_RE, (_m, inner: string) => inner);

  try {
    out = convert(out, markAccents);
  } catch (err) {
    if (!(err instanceof RangeError)) throw err;
    // Pathological nesting (hundreds of brace levels): fall back to a
    // flat strip so the caller still gets readable text.
    out = out
      .replace(/\\[A-Za-z]+/g, "")
      .split("{")
      .join("")
      .split("}")
      .join("");
  }

  // Collapse runs of spaces the substitutions introduced. Horizontal space
  // only: newlines carry meaning here.
  out = out.replace(/[ \t]{2,}/g, " ");

  // An UNPAIRED delimiter at either end ("$45m", "$4\sqrt{3}s"). Bounded to a
  // leading or trailing dollar on an odd count, so a mid-string amount
  // ("costs $5") is left alone.
  let dollars = 0;
  for (let i = 0; i < out.length; i++) if (out[i] === "$") dollars++;
  if (dollars % 2 === 1) {
    if (out.startsWith("$")) out = out.slice(1);
    else if (out.endsWith("$")) out = out.slice(0, -1);
  }
  // `compare`: every span was stripped and amounts are parked, so a `$`
  // left now is an unpaired half (`3.2$ m` → `3.2 m`; tag `v140-a3`).
  if (compare) out = out.split("$").join("");

  // Literal characters come back now that grouping and delimiters are done.
  out = out.split(LBRACE_SENTINEL).join("{");
  out = out.split(RBRACE_SENTINEL).join("}");
  out = out.split(DOLLAR_SENTINEL).join("$");

  for (let idx = 0; idx < labels.length; idx++) {
    out = out
      .split(LABEL_SENTINEL_OPEN + idx + LABEL_SENTINEL_CLOSE)
      .join((keepLabelBackslash ? "\\" : "") + labels[idx]);
  }

  // Compose accents where a precomposed character exists (`i` + U+0302 →
  // `î`) so PDF fonts draw one glyph.
  for (let idx = 0; idx < imageStash.length; idx++) {
    out = out.split("\x00IMG" + idx + "\x00").join(imageStash[idx]);
  }

  return out.normalize("NFC");
}

// ---------------------------------------------------------------------------
// tts style (agents podcast_node / story_node `_clean_script_for_tts`)
// ---------------------------------------------------------------------------

const SPOKEN_OPERATORS: ReadonlyArray<[string, string]> = [
  ["\\times", "times"],
  ["\\div", "divided by"],
  ["\\pm", "plus or minus"],
  ["\\leq", "less than or equal to"],
  ["\\geq", "greater than or equal to"],
  ["\\neq", "not equal to"],
  ["\\le", "less than or equal to"],
  ["\\ge", "greater than or equal to"],
  ["\\ne", "not equal to"],
  ["\\cdot", "times"],
  ["\\approx", "approximately"],
  ["\\infty", "infinity"],
  ["\\int", "integral of"],
  ["\\sum", "sum of"],
  // tag `v140-a8`
  ["\\ldots", "dots"],
  ["\\cdots", "dots"],
  ["\\dots", "dots"],
  ["\\textellipsis", "dots"],
  ["\\textmu", "micro"],
];

// Python's `\w` (Unicode word character).
const W = "[\\p{L}\\p{N}_]";
// The base a spoken script attaches to: a word character, `)`, `]` or `|`.
const SPOKEN_BASE = "([\\p{L}\\p{N}_)\\]|])";
const SPOKEN_DEGREES_RE = /\^\s*\{?\s*\\circ\s*\}?/g;
const SPOKEN_SQUARED_RE = new RegExp(
  SPOKEN_BASE + "\\^(?:\\{2\\}|2)(?![0-9])",
  "gu",
);
const SPOKEN_CUBED_RE = new RegExp(
  SPOKEN_BASE + "\\^(?:\\{3\\}|3)(?![0-9])",
  "gu",
);
const SPOKEN_POWER_BRACE_RE = new RegExp(
  SPOKEN_BASE + "\\^\\{([^{}]+)\\}",
  "gu",
);
const SPOKEN_POWER_RE = new RegExp(SPOKEN_BASE + "\\^(" + W + ")", "gu");
const SPOKEN_SUB_BRACE_RE = new RegExp(SPOKEN_BASE + "_\\{([^{}]+)\\}", "gu");
const SPOKEN_SUB_RE = new RegExp(SPOKEN_BASE + "_(" + W + ")", "gu");
const SPOKEN_OPERATOR_WORDS: ReadonlyMap<string, string> = new Map(
  SPOKEN_OPERATORS.map(([cmd, word]) => [cmd.slice(1), word]),
);
const SPOKEN_OPERATOR_RE = new RegExp(
  "\\\\(" +
    SPOKEN_OPERATORS.map(([cmd]) => escapeRegExp(cmd.slice(1))).join("|") +
    ")(?![A-Za-z])",
  "g",
);
const SPOKEN_CMD_RE = /\\([A-Za-z]+)/y;
const ANY_COMMAND_RE = /\\([a-zA-Z]+)/g;
const STRUCTURAL_WORD_RE = new RegExp(
  "\\\\(?:frac|sqrt|sum|int|prod|lim|log|ln|sin|cos|tan)(?!" + W + ")",
  "gu",
);
const BOLD_RE = /\*\*([^\n]+?)\*\*/g;
const ITALIC_RE = /\*([^\n]+?)\*/g;

// Font and text wrappers: spoken as their content (`\text{cm}` → cm).
const SPOKEN_WRAPPERS: ReadonlySet<string> = new Set(
  (
    "text textbf textit textrm textsf texttt textnormal textup textmd emph " +
    "mathrm mathit mathbf mathsf mathtt mathbb mathcal mathfrak mathscr " +
    "boldsymbol bm operatorname mbox hbox boxed fbox"
  ).split(" "),
);
// mhchem: `\ce{H2O}` → "H 2 O".
const SPOKEN_CHEM_WRAPPERS: ReadonlySet<string> = new Set(["ce", "pu"]);
// Sizing and style commands with nothing to say (`\left(` → "(").
const SPOKEN_DROPPED: ReadonlySet<string> = new Set(
  (
    "left right middle big Big bigg Bigg bigl bigr Bigl Bigr biggl biggr " +
    "Biggl Biggr displaystyle textstyle scriptstyle scriptscriptstyle " +
    "limits nolimits nonumber notag hline"
  ).split(" "),
);
const SPOKEN_SPACES: ReadonlySet<string> = new Set([
  "quad",
  "qquad",
  "enspace",
  "thinspace",
  "medspace",
]);
const SPOKEN_DROPPED_WITH_ARG: ReadonlySet<string> = new Set([
  "hspace",
  "vspace",
  "phantom",
  "hphantom",
  "vphantom",
  "label",
  "tag",
  "color",
]);
const SPOKEN_MATRIX_ENVS: ReadonlySet<string> = new Set([
  "matrix",
  "pmatrix",
  "bmatrix",
  "Bmatrix",
  "vmatrix",
  "Vmatrix",
  "smallmatrix",
]);
const CHEM_TEXT_RE = /^[A-Z][A-Za-z()]*$/;
const CHEM_CHARGE_RE = /^([0-9]*)([+-])$/;
const CHEM_SUP_RE = /\^\{?([0-9]*)([+-])\}?/g;
const CHEM_SUB_RE = /_\{?([0-9]+)\}?/g;
// A digit run right after a letter or closing bracket (kept in group 1).
const CHEM_COUNT_RE = /([A-Za-z)\]])([0-9]+)/g;

/** `H2O` / `H_2O` / `SO4^{2-}` → `H 2 O` / `SO 4 2 minus`. */
function spokenChem(content: string): string {
  content = content
    .split("<=>")
    .join(" is in equilibrium with ")
    .split("<->")
    .join(" is in equilibrium with ");
  content = content
    .split("->")
    .join(" gives ")
    .split("<-")
    .join(" comes from ");
  content = content.replace(
    CHEM_SUP_RE,
    (_m, count: string, sign: string) =>
      " " +
      (count ? count + " " : "") +
      (sign === "+" ? "plus" : "minus") +
      " ",
  );
  content = content.replace(CHEM_SUB_RE, (_m, d: string) => " " + d + " ");
  content = content.replace(
    CHEM_COUNT_RE,
    (_m, before: string, d: string) => before + " " + d + " ",
  );
  return content.split("{").join("").split("}").join("");
}

function needsParens(spoken: string): boolean {
  return /[\s+\-=]/.test(pyStrip(spoken));
}

function allDigits(s: string): boolean {
  if (!s) return false;
  for (const ch of s) if (!isDigit(ch)) return false;
  return true;
}

function rstripStars(s: string): string {
  let j = s.length;
  while (j > 0 && s[j - 1] === "*") j--;
  return s.slice(0, j);
}

/**
 * Spoken form of fractions, roots, wrappers, chemistry, environments and
 * escapes, read with balanced braces at any depth. Operators, Greek and
 * scripts are left for the word rules that run after.
 */
function spokenStructures(s: string, prose = false): string {
  const out: string[] = [];
  const n = s.length;
  let i = 0;
  while (i < n) {
    const c = s[i];
    if (c === "&" && !prose) {
      out.push(" ");
      i++;
      continue;
    }
    if (c !== "\\") {
      out.push(c);
      i++;
      continue;
    }
    if (s.startsWith("\\\\", i)) {
      out.push(" ");
      i += 2;
      continue;
    }
    const m = matchAt(SPOKEN_CMD_RE, s, i);
    if (!m) {
      const nxt = s.slice(i + 1, i + 2);
      if (nxt === "%") out.push(" percent ");
      else if (nxt === "{") out.push("(");
      else if (nxt === "}") out.push(")");
      else if (nxt && "&#_$".includes(nxt)) out.push(nxt);
      else out.push(" "); // \, \; \: \! \  and a lone backslash
      i += 2;
      continue;
    }
    const name = m[1];
    let j = i + m[0].length;
    if (FRAC_CMDS.has(name)) {
      const [num, afterNum] = readArg(s, j);
      j = afterNum;
      const [den, k] = readArg(s, j);
      if (num === null || den === null) {
        out.push(" ");
        i = j;
        continue;
      }
      out.push(
        "(" +
          pyStrip(spokenStructures(num)) +
          " over " +
          pyStrip(spokenStructures(den)) +
          ")",
      );
      i = k;
      continue;
    }
    if (name === "sqrt") {
      let index = "";
      let k = j;
      while (k < n && (s[k] === " " || s[k] === "\t")) k++;
      if (k < n && s[k] === "[") {
        const close = s.indexOf("]", k);
        if (close !== -1) {
          index = pyStrip(s.slice(k + 1, close));
          j = close + 1;
        }
      }
      const [arg, afterArg] = readArg(s, j);
      j = afterArg;
      if (arg === null) {
        out.push(" square root ");
        i = j;
        continue;
      }
      let inner = pyStrip(spokenStructures(arg));
      if (needsParens(inner)) inner = "(" + inner + ")";
      let phrase: string;
      if (!index || index === "2") phrase = "square root of";
      else if (index === "3") phrase = "cube root of";
      else phrase = index + "th root of";
      out.push(phrase + " " + inner);
      i = j;
      continue;
    }
    if (SPOKEN_CHEM_WRAPPERS.has(name)) {
      const [arg, afterArg] = readArg(s, j);
      out.push(" " + spokenChem(arg ?? "") + " ");
      i = afterArg;
      continue;
    }
    if (SPOKEN_WRAPPERS.has(name)) {
      const [rawArg, afterArg] = readArg(s, j);
      j = afterArg;
      let arg = rawArg ?? "";
      if (
        (name === "text" || name === "mathrm") &&
        (arg.includes("_") || arg.includes("^"))
      )
        arg = spokenChem(arg); // `\mathrm{H_2O}`
      const inner = spokenStructures(arg);
      // `\text{H}_{2}\text{O}`, `\text{Fe}^{3+}`: an element read with its
      // count or charge.
      if (CHEM_TEXT_RE.test(pyStrip(inner))) {
        const spoken: string[] = [pyStrip(inner)];
        while (j < n && (s[j] === "_" || s[j] === "^")) {
          const [scriptArg, k] = readArg(s, j + 1);
          if (scriptArg === null) break;
          const charge = CHEM_CHARGE_RE.exec(scriptArg);
          if (s[j] === "_" && allDigits(scriptArg)) {
            spoken.push(scriptArg);
          } else if (s[j] === "^" && charge) {
            if (charge[1]) spoken.push(charge[1]);
            spoken.push(charge[2] === "+" ? "plus" : "minus");
          } else {
            break;
          }
          j = k;
        }
        if (spoken.length > 1) {
          out.push(" " + spoken.join(" ") + " ");
          i = j;
          continue;
        }
      }
      out.push(inner);
      i = j;
      continue;
    }
    if (name === "begin") {
      const [envArg, afterEnv] = readArg(s, j);
      j = afterEnv;
      const env = pyStrip(envArg ?? "");
      const endRe = new RegExp(
        "\\\\end\\s*\\{" + escapeRegExp(env) + "\\}",
        "g",
      );
      endRe.lastIndex = j;
      const endM = endRe.exec(s);
      const bodyEnd = endM ? endM.index : n;
      const after = endM ? endM.index + endM[0].length : n;
      if (env === "array") j = readArg(s, j)[1]; // column spec
      const rows = splitTable(s.slice(j, bodyEnd))
        .map((row) =>
          row.map((cell) => pyStrip(spokenStructures(cell))).filter((c) => c),
        )
        .filter((row) => row.length > 0);
      const bare = rstripStars(env);
      if (SPOKEN_MATRIX_ENVS.has(bare)) {
        out.push(
          " matrix with rows " + rows.map((r) => r.join(", ")).join("; ") + " ",
        );
      } else if (bare === "cases") {
        const cases = rows.map((r) => r.join(", ")).join("; ");
        out.push(" " + cases.replace(/,\s*,/g, ",") + " ");
      } else {
        out.push(" " + rows.map((r) => r.join(" ")).join("; ") + " ");
      }
      i = after;
      continue;
    }
    if (name === "end") {
      i = readArg(s, j)[1];
      continue;
    }
    if (SPOKEN_DROPPED.has(name)) {
      while (j < n && (s[j] === " " || s[j] === "\t")) j++;
      if (j < n && s[j] === ".") j++; // `\left.`
      i = j;
      continue;
    }
    if (SPOKEN_SPACES.has(name)) {
      out.push(" ");
      i = j;
      continue;
    }
    if (SPOKEN_DROPPED_WITH_ARG.has(name)) {
      i = readArg(s, j)[1];
      continue;
    }
    if (name === "textcolor" || name === "colorbox") {
      j = readArg(s, j)[1];
      const [arg, afterArg] = readArg(s, j);
      out.push(spokenStructures(arg ?? ""));
      i = afterArg;
      continue;
    }
    // Operators, Greek, functions: the word rules below read them. A space
    // keeps `\alpha\text{x}` from becoming `\alphax`.
    out.push(m[0] + (j < n && s[j] === "\\" ? " " : ""));
    i = j;
  }
  return out.join("");
}

/** `(a over b)` → `a over b` when ONE pair wraps the whole text. */
function stripOuterParens(text: string): string {
  if (!(text.startsWith("(") && text.endsWith(")"))) return text;
  let depth = 0;
  for (let k = 0; k < text.length; k++) {
    if (text[k] === "(") depth++;
    else if (text[k] === ")") depth--;
    if (depth === 0 && k < text.length - 1) return text;
  }
  return text.slice(1, -1);
}

function latexToSpoken(latex: string): string {
  let text = spokenStructures(pyStrip(latex));
  // `50^\circ C` → "50 degrees C": room on both sides (tag `v140-a8`).
  text = text.replace(SPOKEN_DEGREES_RE, " degrees ");
  text = text.replace(SPOKEN_SQUARED_RE, (_m, a: string) => a + " squared");
  text = text.replace(SPOKEN_CUBED_RE, (_m, a: string) => a + " cubed");
  text = text.replace(
    SPOKEN_POWER_BRACE_RE,
    (_m, a: string, b: string) => a + " to the power " + b,
  );
  text = text.replace(
    SPOKEN_POWER_RE,
    (_m, a: string, b: string) => a + " to the power " + b,
  );
  text = text.replace(
    SPOKEN_SUB_BRACE_RE,
    (_m, a: string, b: string) => a + " sub " + b,
  );
  text = text.replace(
    SPOKEN_SUB_RE,
    (_m, a: string, b: string) => a + " sub " + b,
  );
  // Every command becomes a word with room around it (`4\pi` → "4 pi").
  text = text.replace(
    SPOKEN_OPERATOR_RE,
    (_m, name: string) => " " + (SPOKEN_OPERATOR_WORDS.get(name) ?? name) + " ",
  );
  text = text.replace(ANY_COMMAND_RE, (_m, name: string) => " " + name + " ");
  text = text.split("{").join("").split("}").join("").split("\\").join(" ");
  text = text.replace(/[ \t]+/g, " ");
  text = text.replace(/\(\s+/g, "(");
  text = text.replace(/\s+\)/g, ")");
  // A word before a comma or semicolon (`\ldots,` → "dots,").
  text = text.replace(/ +([,;])/g, "$1");
  return stripOuterParens(pyStrip(text));
}

// A span whose whole body is typography is read as the character itself, so
// the voice pauses (`leukocytes$\ldots$` → "leukocytes…"; tag `v140-a8`).
const SPOKEN_TYPOGRAPHIC_SPANS: ReadonlyMap<string, string> = new Map([
  ["\\ldots", "…"],
  ["\\dots", "…"],
  ["\\cdots", "…"],
  ["\\textellipsis", "…"],
  ["\\textmu", "micro"],
]);
// A bare single-letter subscript in prose (`x_{n}`, `a_1`): "x sub n". The
// base is one ASCII letter with no letter, digit, `_` or `\` before it, and
// the subscript must not run into a word, a superscript or a group (`v_avg`,
// `lo_0`, `H_2O`, `H_{2}O`, `x_0^2` and `fallback_factual_error` stay).
const PROSE_SUBSCRIPT_RE =
  /(^|[^A-Za-z0-9_\\])([A-Za-z])_(?:\{([A-Za-z0-9]+)\}|([A-Za-z0-9]))(?![A-Za-z0-9_^{])/g;

function spokenProseSubscripts(text: string): string {
  if (!text.includes("_")) return text;
  return text.replace(
    PROSE_SUBSCRIPT_RE,
    (
      _m,
      lead: string,
      base: string,
      braced: string | undefined,
      single: string | undefined,
    ) => lead + base + " sub " + (braced !== undefined ? braced : single),
  );
}

// Bare `50^\circ C` / `50^{\circ}C` in prose (tag `v140-a8`).
const PROSE_DEGREES_RE = /\^[ \t]*\{?[ \t]*\\circ(?![A-Za-z])[ \t]*\}?/g;

function spokenProseDegrees(text: string): string {
  if (!text.includes("\\circ")) return text;
  return text.replace(
    PROSE_DEGREES_RE,
    (m: string, offset: number) =>
      " degrees" + (isAlnum(charAt(text, offset + m.length)) ? " " : ""),
  );
}

function toSpoken(text: string): string {
  const parts: string[] = [];
  for (const seg of segment(text)) {
    if (seg.kind === "math") {
      const typographic = SPOKEN_TYPOGRAPHIC_SPANS.get(pyStrip(seg.value));
      parts.push(
        typographic !== undefined ? typographic : latexToSpoken(seg.value),
      );
      continue;
    }
    let value = seg.value;
    // `$50^\circ$C`: a degrees span runs into a unit (tag `v140-a8`).
    if (
      parts.length > 0 &&
      parts[parts.length - 1].endsWith("degrees") &&
      isAlnum(charAt(value, 0))
    )
      value = " " + value;
    value = spokenProseDegrees(spokenProseSubscripts(value));
    // Bare LaTeX in prose (`\frac{1}{2}` never wrapped): fractions, roots,
    // wrappers and environments are read the same way.
    parts.push(value.includes("\\") ? spokenStructures(value, true) : value);
  }
  let cleaned = parts.join("");
  cleaned = cleaned.replace(STRUCTURAL_WORD_RE, "");
  cleaned = cleaned.replace(ANY_COMMAND_RE, (_m, name: string) => name);
  cleaned = cleaned.replace(BOLD_RE, (_m, inner: string) => inner);
  cleaned = cleaned.replace(ITALIC_RE, (_m, inner: string) => inner);
  cleaned = cleaned.replace(/ {2,}/g, " ");
  cleaned = cleaned.replace(/\n{3,}/g, "\n\n");
  return pyStrip(cleaned);
}
export const STYLES = ["text", "pdf", "tts", "compare"] as const;
export type PlainStyle = (typeof STYLES)[number];

const SUPERSCRIPT_TO_ASCII = charMap("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ", "0123456789+-=()ni");
const SUBSCRIPT_TO_ASCII = charMap(
  "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ",
  "0123456789+-=()aeoxhklmnpst",
);
const SUPERSCRIPT_RUN_RE = /[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ]+/g;
const SUBSCRIPT_RUN_RE = /[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ]+/g;
const COMPARE_OPERATOR_SPACE_RE = / ?([+\-*/=<>^_(),{}[\]]) ?/g;
// One leading option label (tag `v140-a4`): `A)`, `(B)`, `C.`, `D:`, `a)` —
// a letter A–H in either case — followed by whitespace and an answer.
const OPTION_LABEL_RE = /^\s*(?:\([A-Ha-h]\)|[A-Ha-h][).:])\s+(?=\S)/u;
const LONE_LETTER_RE = /^[A-Za-z]\s*$/u;

function isAsciiDigitChar(ch: string): boolean {
  return ch.length === 1 && ch >= "0" && ch <= "9";
}

/**
 * `COMPARE_FOLD` (the shared `compare_fold` table, tag `v140-a1`) per
 * character. A folded value that starts with a digit and holds a `/` (a
 * vulgar fraction) gets a space after a digit, so `1½` reads `1 1/2`.
 */
function applyCompareFold(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    let value = Object.prototype.hasOwnProperty.call(COMPARE_FOLD, ch)
      ? COMPARE_FOLD[ch]
      : undefined;
    if (value === undefined) {
      out += ch;
      continue;
    }
    if (
      isAsciiDigitChar(value.charAt(0)) &&
      value.includes("/") &&
      out.length > 0 &&
      isAsciiDigitChar(out.charAt(out.length - 1))
    )
      value = " " + value;
    out += value;
  }
  return out;
}

/**
 * One ASCII-leaning form for answer comparison: a leading option label
 * dropped, compatibility characters folded, scripts as `^…`/`_…`, minus
 * signs and multiplication dots folded, whitespace collapsed and removed
 * around operators and brackets.
 */
function foldForCompare(text: string): string {
  // Never strip when a lone letter would remain: `a: b` must not compare as
  // the option letter `b` (tag `v140-a4`).
  const label = OPTION_LABEL_RE.exec(text);
  if (label && !LONE_LETTER_RE.test(text.slice(label[0].length)))
    text = text.slice(label[0].length);
  let out = applyCompareFold(text);
  out = out.replace(
    SUPERSCRIPT_RUN_RE,
    (m) => "^" + translate(m, SUPERSCRIPT_TO_ASCII),
  );
  out = out.replace(
    SUBSCRIPT_RUN_RE,
    (m) => "_" + translate(m, SUBSCRIPT_TO_ASCII),
  );
  out = pyStrip(out.replace(/\s+/gu, " "));
  return out.replace(COMPARE_OPERATOR_SPACE_RE, "$1");
}

/**
 * LaTeX → plain text.
 *
 * `style="text"`: accents dropped (grading, canvas, in-class report).
 * `style="pdf"`: accents marked (`\vec{F}` → `F⃗`, `\vec{AB}` → `vec(AB)`).
 * `style="tts"`: spoken English for a text-to-speech voice.
 * `style="compare"`: one form for answer comparison, so a typed answer
 * equals the same value in LaTeX (`1/3` = `$\frac{1}{3}$`, `x^2` = `$x^2$`,
 * `−3` = `-3`).
 * Non-strings are returned unchanged.
 */
export function toPlain<T>(text: T, style?: PlainStyle): T;
export function toPlain(text: unknown, style: PlainStyle = "text"): unknown {
  if (!(STYLES as readonly string[]).includes(style)) {
    throw new RangeError(
      `unknown style ${JSON.stringify(style)}; expected one of ${STYLES.join(", ")}`,
    );
  }
  if (typeof text !== "string") return text;
  // A form feed / backspace / TAB that was a command (`<FF>rac`,
  // `<TAB>imes`) is restored first, with the same `guessWhitespace` as `fix`
  // (`normalize`); tag `audit5-3`.
  let src: string = repair(text);
  // Mojibake is repaired as `normalize` does (tag `v140-a6`). `compare`
  // decodes HTML entities the `html.unescape` way first, once (`v140-a2`).
  src =
    style === "compare"
      ? fixMojibakeCore(unescapeHtmlEntities(src))
      : fixMojibakeTable(src);
  // A padded span (`$2x + 3 $`) is trimmed as `normalize` does, amounts
  // masked (tag `audit6-2`).
  src = trimPaddedSpansKeepCurrency(src);
  if (style === "tts") return toSpoken(src);
  if (style === "compare")
    return foldForCompare(latexToPlain(src, false, false, true, true));
  return latexToPlain(
    src,
    style === "pdf",
    style === "text",
    false,
    false,
    true,
  );
}
