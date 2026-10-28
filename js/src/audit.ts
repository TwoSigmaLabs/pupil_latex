/**
 * `audit`: detect raw or mangled LaTeX. Read-only, pure. Port of
 * python/pupiltree_latex/audit.py.
 */

import { lstripChars, matchAt } from "./chars.js";
import { after, execFrom, type Blocked } from "./lookbehind.js";
import {
  ARGUMENT_COMMANDS,
  AUDIT_EXTRA_ALLOWED_COMMANDS,
  JSON_WHITESPACE_COLLISION_COMMANDS,
  KATEX_COMMANDS,
  LATEX_COMMANDS_BEHIND_JSON_ESCAPES,
  UNSUPPORTED_COMMANDS,
} from "./commands.js";
import { isPlainObject } from "./repair.js";
import { mathMask, mathRanges } from "./spans.js";
import {
  isNonContentKey,
  isNotRenderedKey,
  isUrlOrPathString,
} from "./walk.js";

export const KIND_CONTROL_CHAR = "control_char";
export const KIND_LEGACY_DELIMITER = "legacy_delimiter";
export const KIND_UNBALANCED_DOLLAR = "unbalanced_dollar";
export const KIND_COMMAND_MISSING_ARGUMENT = "command_missing_argument";
export const KIND_FRAC_MISSING_ARGS = "frac_missing_args";
export const KIND_SCRIPT_MISSING_BRACES = "script_missing_braces";
export const KIND_MOJIBAKE = "mojibake";
export const KIND_DOUBLE_ESCAPED_COMMAND = "double_escaped_command";
export const KIND_UNSUPPORTED_COMMAND = "unsupported_command";
export const KIND_BARE_UNICODE_MATH = "bare_unicode_math";
export const KIND_UNICODE_CHEMISTRY = "unicode_chemistry";
export const KIND_BARE_LEFT_BRACE = "bare_left_brace";
export const KIND_LOST_ESCAPE = "lost_escape";

export type FindingKind =
  | typeof KIND_CONTROL_CHAR
  | typeof KIND_LEGACY_DELIMITER
  | typeof KIND_UNBALANCED_DOLLAR
  | typeof KIND_COMMAND_MISSING_ARGUMENT
  | typeof KIND_FRAC_MISSING_ARGS
  | typeof KIND_SCRIPT_MISSING_BRACES
  | typeof KIND_MOJIBAKE
  | typeof KIND_DOUBLE_ESCAPED_COMMAND
  | typeof KIND_UNSUPPORTED_COMMAND
  | typeof KIND_BARE_UNICODE_MATH
  | typeof KIND_UNICODE_CHEMISTRY
  | typeof KIND_BARE_LEFT_BRACE
  | typeof KIND_LOST_ESCAPE;

export const ALL_KINDS: readonly FindingKind[] = [
  KIND_CONTROL_CHAR,
  KIND_LEGACY_DELIMITER,
  KIND_UNBALANCED_DOLLAR,
  KIND_COMMAND_MISSING_ARGUMENT,
  KIND_FRAC_MISSING_ARGS,
  KIND_SCRIPT_MISSING_BRACES,
  KIND_MOJIBAKE,
  KIND_DOUBLE_ESCAPED_COMMAND,
  KIND_UNSUPPORTED_COMMAND,
  KIND_BARE_UNICODE_MATH,
  KIND_UNICODE_CHEMISTRY,
  KIND_BARE_LEFT_BRACE,
  KIND_LOST_ESCAPE,
];

// Control characters must be ZERO after the write-sink repair, so any hit is
// a regression of that fix (or a write path that bypasses it).
export const ERROR_KINDS: ReadonlySet<string> = new Set([KIND_CONTROL_CHAR]);

/** One defect at one position in one string. */
export interface Finding {
  kind: FindingKind;
  position: number;
  snippet: string;
}

export const SNIPPET_MAX_CHARS = 120;
const SNIPPET_RADIUS = 45;

function visible(ch: string): string {
  if (ch === "\n") return "↵";
  const code = ch.charCodeAt(0);
  if (code < 0x20 || code === 0x7f)
    return "<0x" + code.toString(16).toUpperCase().padStart(2, "0") + ">";
  return ch;
}

/** A short window around `position` with every control char visible. */
export function makeSnippet(
  text: string,
  position: number,
  radius = SNIPPET_RADIUS,
): string {
  const start = Math.max(0, position - radius);
  const end = Math.min(text.length, position + radius);
  let window = "";
  for (let i = start; i < end; i++) window += visible(text[i]);
  if (start > 0) window = "…" + window;
  if (end < text.length) window = window + "…";
  return window.slice(0, SNIPPET_MAX_CHARS);
}

function finding(kind: FindingKind, text: string, position: number): Finding {
  return { kind, position, snippet: makeSnippet(text, position) };
}

// ---------------------------------------------------------------------------
// Math-span tokenizer shared by several detectors
// ---------------------------------------------------------------------------

function unescapedDollarPositions(text: string): number[] {
  const positions: number[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "$" && (i === 0 || text[i - 1] !== "\\")) positions.push(i);
  }
  return positions;
}

/** `[inner_start, inner_end]` of each `$…$` / `$$…$$` span. */
function mathSpans(text: string, closedOnly = false): Array<[number, number]> {
  const spans: Array<[number, number]> = [];
  const positions = unescapedDollarPositions(text);
  let i = 0;
  let openKind: string | null = null;
  let openInnerStart = 0;
  while (i < positions.length) {
    const pos = positions[i];
    let width: number;
    let step: number;
    let token: string;
    if (i + 1 < positions.length && positions[i + 1] === pos + 1) {
      token = "$$";
      width = 2;
      step = 2;
    } else {
      token = "$";
      width = 1;
      step = 1;
    }
    if (openKind === null) {
      openKind = token;
      openInnerStart = pos + width;
    } else {
      spans.push([openInnerStart, pos]);
      openKind = null;
    }
    i += step;
  }
  if (openKind !== null && !closedOnly)
    spans.push([openInnerStart, text.length]);
  return spans;
}

function isInsideMathSpan(text: string, pos: number): boolean {
  let n = 0;
  for (let i = 0; i < pos; i++) {
    if (text[i] === "$" && (i === 0 || text[i - 1] !== "\\")) n++;
  }
  return n % 2 === 1;
}

/** Every match of a global regex that starts inside `[start, end)`. */
function matchesWithin(
  re: RegExp,
  text: string,
  start: number,
  end: number,
  blocked?: Blocked,
): RegExpExecArray[] {
  const out: RegExpExecArray[] = [];
  re.lastIndex = start;
  let m: RegExpExecArray | null;
  while (
    (m = blocked
      ? execFrom(re, text, re.lastIndex, blocked)
      : re.exec(text)) !== null
  ) {
    if (m.index >= end) break;
    out.push(m);
    if (!blocked && m[0].length === 0) re.lastIndex++;
  }
  return out;
}

function allMatches(
  re: RegExp,
  text: string,
  blocked?: Blocked,
): RegExpExecArray[] {
  return matchesWithin(re, text, 0, text.length, blocked);
}

// The patterns below used to open with a "not after a backslash"
// lookbehind; that check is now AFTER_BACKSLASH (see lookbehind.ts).
const AFTER_BACKSLASH = after("\\");

// ---------------------------------------------------------------------------
// Detectors
// ---------------------------------------------------------------------------

// Every C0 control except TAB/LF/CR, and DEL (tag `v140-b8`).
const OTHER_C0_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const ALPHA_RUN_RE = /[A-Za-z]+/y;
const WS_CTRL_LETTER: Readonly<Record<string, string>> = {
  "\t": "t",
  "\n": "n",
  "\r": "r",
};
const MIN_RUN_AFTER_NEWLINE = 3;

function detectControlChars(text: string): Finding[] {
  const findings = allMatches(OTHER_C0_RE, text).map((m) =>
    finding(KIND_CONTROL_CHAR, text, m.index),
  );
  if (!text.includes("\t") && !text.includes("\n") && !text.includes("\r"))
    return findings;
  let dollars: number[] | null = null;
  for (let i = 0; i < text.length; i++) {
    const letter = WS_CTRL_LETTER[text[i]];
    if (letter === undefined) continue;
    const m = matchAt(ALPHA_RUN_RE, text, i + 1);
    if (!m) continue;
    const run = m[0];
    if (text[i] === "\n" && run.length < MIN_RUN_AFTER_NEWLINE) continue;
    if (LATEX_COMMANDS_BEHIND_JSON_ESCAPES.has(letter + run)) {
      findings.push(finding(KIND_CONTROL_CHAR, text, i));
      continue;
    }
    // Inside a math span a raw newline/tab/CR is never content; when the
    // letters after it spell a command under ANY of the three escape letters
    // (`$<LF>ightarrow$`) the byte is a decoded backslash.
    if (dollars === null) dollars = unescapedDollarPositions(text);
    let before = 0;
    let after = false;
    for (const k of dollars) {
      if (k < i) before++;
      else after = true;
    }
    const inside = before % 2 === 1 && after;
    if (
      inside &&
      [..."ntr"].some((c) => JSON_WHITESPACE_COLLISION_COMMANDS.has(c + run))
    ) {
      findings.push(finding(KIND_CONTROL_CHAR, text, i));
    }
  }
  return findings;
}

const LEGACY_DELIM_RE = /\\[()[\]]/g;

function detectLegacyDelimiters(text: string): Finding[] {
  return allMatches(LEGACY_DELIM_RE, text, AFTER_BACKSLASH).map((m) =>
    finding(KIND_LEGACY_DELIMITER, text, m.index),
  );
}

function detectUnbalancedDollars(text: string): Finding[] {
  const positions = unescapedDollarPositions(text);
  if (positions.length % 2 === 0) return [];
  const last = positions[positions.length - 1];
  return [finding(KIND_UNBALANCED_DOLLAR, text, last)];
}

const CMD_THEN_CLOSE_RE = new RegExp(
  "\\\\(?:" + ARGUMENT_COMMANDS.join("|") + ")(?![A-Za-z])\\s*(?=\\$|$)",
  "g",
);

export function detectCommandMissingArgument(text: string): Finding[] {
  return allMatches(CMD_THEN_CLOSE_RE, text).map((m) =>
    finding(KIND_COMMAND_MISSING_ARGUMENT, text, m.index),
  );
}

const FRAC_RE = /\\[dt]?frac(?![A-Za-z])/g;
const SIMPLE_ARG_RE = /[A-Za-z0-9]/;

function skipBraceGroup(text: string, i: number): number | null {
  let depth = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (ch === "\\") {
      i += 2;
      continue;
    }
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return i + 1;
    }
    i++;
  }
  return null;
}

function consumeFracArgument(text: string, i: number): number | null {
  const n = text.length;
  while (i < n && (text[i] === " " || text[i] === "\t")) i++;
  if (i >= n) return null;
  const ch = text[i];
  if (ch === "{") return skipBraceGroup(text, i);
  if (ch === "\\") {
    const m = matchAt(ALPHA_RUN_RE, text, i + 1);
    return m ? i + 1 + m[0].length : i + 2;
  }
  if (SIMPLE_ARG_RE.test(ch)) return i + 1;
  return null;
}

export function detectFracMissingArgs(text: string): Finding[] {
  const findings: Finding[] = [];
  for (const m of allMatches(FRAC_RE, text)) {
    const afterCmd = m.index + m[0].length;
    const first = consumeFracArgument(text, afterCmd);
    if (first === null) {
      const rest = lstripChars(text.slice(afterCmd), " \t");
      if (rest === "" || rest.startsWith("$")) continue; // reported by command_missing_argument
      findings.push(finding(KIND_FRAC_MISSING_ARGS, text, m.index));
      continue;
    }
    if (consumeFracArgument(text, first) === null) {
      findings.push(finding(KIND_FRAC_MISSING_ARGS, text, m.index));
    }
  }
  return findings;
}

const SCRIPT_NO_BRACES_RE = /[\^_](?:\d{2,}|[+\-][A-Za-z0-9]|[A-Za-z]{2,})/g;
const MAX_SCRIPT_SPAN_CHARS = 400;

function detectScriptMissingBraces(text: string): Finding[] {
  const findings: Finding[] = [];
  for (const [start, end] of mathSpans(text, true)) {
    if (end - start > MAX_SCRIPT_SPAN_CHARS) continue;
    for (const m of matchesWithin(
      SCRIPT_NO_BRACES_RE,
      text,
      start,
      end,
      AFTER_BACKSLASH,
    )) {
      findings.push(finding(KIND_SCRIPT_MISSING_BRACES, text, m.index));
    }
  }
  return findings;
}

const MOJIBAKE_RE = /�|â€|[ÎÏ]|[âÂÃ][\x80-\xff]/g;

function detectMojibake(text: string): Finding[] {
  return allMatches(MOJIBAKE_RE, text).map((m) =>
    finding(KIND_MOJIBAKE, text, m.index),
  );
}

const DOUBLE_ESCAPED_RE = /(?:\\\\)+[A-Za-z]{2,}/g;
const JSON_OBJECT_HINT_RE = /\{\s*"[^"\n]{1,80}"\s*:/;

const ROW_ENVIRONMENT_RE = /\\begin\{|&/;

function detectDoubleEscapedCommands(text: string): Finding[] {
  if (JSON_OBJECT_HINT_RE.test(text)) return [];
  // Inside a matrix / aligned block `\\` is a row separator, so `a&b\\cos x`
  // is a row that starts with `\cos`, not a double-escaped command.
  const rowSpans = mathRanges(text).filter(({ start, end }) =>
    ROW_ENVIRONMENT_RE.test(text.slice(start, end)),
  );
  return allMatches(DOUBLE_ESCAPED_RE, text, AFTER_BACKSLASH)
    .filter(
      (m) =>
        !rowSpans.some(({ start, end }) => start <= m.index && m.index < end),
    )
    .map((m) => finding(KIND_DOUBLE_ESCAPED_COMMAND, text, m.index));
}

const COMMAND_NAME_RE = /\\([A-Za-z]+)/g;
const UNSUPPORTED_RE = new RegExp(
  "\\\\(?:" + UNSUPPORTED_COMMANDS.join("|") + ")(?![A-Za-z])",
  "g",
);

function detectUnsupportedCommands(text: string): Finding[] {
  const findings = allMatches(UNSUPPORTED_RE, text).map((m) =>
    finding(KIND_UNSUPPORTED_COMMAND, text, m.index),
  );
  const reported = new Set(findings.map((f) => f.position));
  for (const [start, end] of mathSpans(text, true)) {
    for (const m of matchesWithin(
      COMMAND_NAME_RE,
      text,
      start,
      end,
      AFTER_BACKSLASH,
    )) {
      const name = m[1];
      if (KATEX_COMMANDS.has(name) || AUDIT_EXTRA_ALLOWED_COMMANDS.has(name))
        continue;
      if (reported.has(m.index)) continue;
      findings.push(finding(KIND_UNSUPPORTED_COMMAND, text, m.index));
    }
  }
  return findings;
}

const BARE_UNICODE_MATH_RE =
  /[×÷±∓√∞∂∇≤≥≠≈≡∝→←↔⇌⇒⇐⇔∈∉⊂⊃⊆⊇∪∩∅∀∃∧∨αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]/g;

function detectBareUnicodeMath(text: string): Finding[] {
  if (!BARE_UNICODE_MATH_RE.test(text)) return [];
  BARE_UNICODE_MATH_RE.lastIndex = 0;
  const mask = mathMask(text);
  return allMatches(BARE_UNICODE_MATH_RE, text)
    .filter((m) => !mask[m.index])
    .map((m) => finding(KIND_BARE_UNICODE_MATH, text, m.index));
}

const UNICODE_CHEM_RE = /[A-Z][a-z]?[₀-₉]+/g;

function detectUnicodeChemistry(text: string): Finding[] {
  return allMatches(UNICODE_CHEM_RE, text).map((m) =>
    finding(KIND_UNICODE_CHEMISTRY, text, m.index),
  );
}

const BARE_BRACE_CMD_RE = /\\left(?!\\)\{|\\right(?!\\)\}/g;

function detectBareLeftBrace(text: string): Finding[] {
  return allMatches(BARE_BRACE_CMD_RE, text).map((m) =>
    finding(KIND_BARE_LEFT_BRACE, text, m.index),
  );
}

// `lost_escape` (tag `v140-b8`): a command whose first letter was eaten,
// the damage left after a form feed / tab / newline from a JSON escape was
// stripped (`\frac` → `rac`, `\times` → `imes`, `\text` → `ext`).
export const LOST_ESCAPE_RUNS: ReadonlySet<string> = new Set(
  (
    "rac orall inom oldsymbol arepsilon artheta arphi abla atural ewline " +
    "olimits onumber otin aisebox ight ightarrow ightharpoonup ightleftarrows " +
    "ightleftharpoons anh ext extbf extcolor extit extrm extsf extstyle exttt " +
    "herefore heta hinspace ilde imes riangle riangleleft riangleq"
  ).split(" "),
);
const LETTER_RUN_RE = /[A-Za-z]+/g;
const ANY_CONTROL_RE = /[\x00-\x1f\x7f]/;
const TEXT_GROUP_OPEN_RE =
  /\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|textup|mathrm|mbox|hbox)\s*\{/g;

/** `[a, b)` of every `\text{…}`-family group between start and end. */
function textGroupRanges(
  text: string,
  start: number,
  end: number,
): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  const region = text.slice(0, end);
  TEXT_GROUP_OPEN_RE.lastIndex = start;
  let m: RegExpExecArray | null;
  while ((m = TEXT_GROUP_OPEN_RE.exec(region)) !== null) {
    let depth = 0;
    let j = m.index + m[0].length - 1;
    while (j < end) {
      const ch = text[j];
      if (ch === "\\") {
        j += 2;
        continue;
      }
      if (ch === "{") depth++;
      else if (ch === "}") {
        depth--;
        if (depth === 0) break;
      }
      j++;
    }
    out.push([m.index, Math.min(j + 1, end)]);
  }
  return out;
}

/**
 * A run in `LOST_ESCAPE_RUNS` at a word start (no letter or backslash before
 * it): inside a math span (outside `\text{…}`), or anywhere when a `{`
 * follows (`ext{H}`, `rac{1}{2}`). A control character still in front of
 * it is a `control_char` finding instead.
 */
function detectLostEscapes(text: string): Finding[] {
  const candidates = allMatches(LETTER_RUN_RE, text).filter((m) =>
    LOST_ESCAPE_RUNS.has(m[0]),
  );
  if (candidates.length === 0) return [];
  const ranges = mathRanges(text);
  const groups: Array<[number, number]> = [];
  for (const r of ranges) groups.push(...textGroupRanges(text, r.start, r.end));
  const controls = ANY_CONTROL_RE.test(text)
    ? new Set(detectControlChars(text).map((f) => f.position))
    : new Set<number>();
  const findings: Finding[] = [];
  for (const m of candidates) {
    const i = m.index;
    if (i > 0 && (text[i - 1] === "\\" || controls.has(i - 1))) continue;
    const inMath = ranges.some((r) => r.start <= i && i < r.end);
    if (inMath && groups.some(([a, b]) => a <= i && i < b)) continue;
    const end = i + m[0].length;
    if (!inMath && !(end < text.length && text[end] === "{")) continue;
    findings.push(finding(KIND_LOST_ESCAPE, text, i));
  }
  return findings;
}

export const DETECTORS: ReadonlyArray<(text: string) => Finding[]> = [
  detectControlChars,
  detectLegacyDelimiters,
  detectUnbalancedDollars,
  detectCommandMissingArgument,
  detectFracMissingArgs,
  detectScriptMissingBraces,
  detectMojibake,
  detectDoubleEscapedCommands,
  detectUnsupportedCommands,
  detectBareUnicodeMath,
  detectUnicodeChemistry,
  detectBareLeftBrace,
  detectLostEscapes,
];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Every defect in one string, ordered by position then kind. */
export function audit(text: unknown): Finding[] {
  if (typeof text !== "string" || !text) return [];
  const findings: Finding[] = [];
  for (const detector of DETECTORS) findings.push(...detector(text));
  findings.sort(
    (a, b) =>
      a.position - b.position ||
      (a.kind < b.kind ? -1 : a.kind > b.kind ? 1 : 0),
  );
  return findings;
}

/** The kinds only, in finding order (what the corpus compares). */
export function auditKinds(text: unknown): FindingKind[] {
  return audit(text).map((f) => f.kind);
}

function decodeJsonLeaf(text: string): unknown {
  const head = text.trimStart()[0];
  if (head !== "{" && head !== "[") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  return Array.isArray(parsed) || isPlainObject(parsed) ? parsed : null;
}

function* contentLeaves(
  obj: unknown,
  keyHint: string,
  path: string,
): Generator<[string, string]> {
  if (typeof obj === "string") {
    if (isNonContentKey(keyHint) || isNotRenderedKey(keyHint)) return;
    if (isUrlOrPathString(obj)) return;
    const decoded = decodeJsonLeaf(obj);
    if (decoded !== null) {
      yield* contentLeaves(decoded, keyHint, path + "(json)");
      return;
    }
    yield [path, obj];
  } else if (Array.isArray(obj)) {
    for (let i = 0; i < obj.length; i++)
      yield* contentLeaves(obj[i], keyHint, path + "[" + i + "]");
  } else if (isPlainObject(obj)) {
    for (const [k, v] of Object.entries(obj)) {
      const child = path ? path + "." + k : k;
      yield* contentLeaves(v, k, child);
    }
  }
}

/** `[fieldPath, finding]` for every content string leaf of a document. */
export function auditDeep(obj: unknown): Array<[string, Finding]> {
  const out: Array<[string, Finding]> = [];
  for (const [path, text] of contentLeaves(obj, "", "")) {
    for (const f of audit(text)) out.push([path, f]);
  }
  return out;
}

export function countByKind(
  findings: Iterable<Finding>,
): Partial<Record<FindingKind, number>> {
  const counter = new Map<string, number>();
  for (const f of findings) counter.set(f.kind, (counter.get(f.kind) ?? 0) + 1);
  const out: Partial<Record<FindingKind, number>> = {};
  for (const kind of ALL_KINDS) {
    const n = counter.get(kind);
    if (n) out[kind] = n;
  }
  return out;
}

/** True when any kind is a regression class (log at ERROR). */
export function isError(kinds: Iterable<string>): boolean {
  for (const k of kinds) if (ERROR_KINDS.has(k)) return true;
  return false;
}
