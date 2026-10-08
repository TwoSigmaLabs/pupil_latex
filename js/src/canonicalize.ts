/**
 * `canonicalize`: the write-time sanitiser for fresh Class A model output.
 * Port of python/pupiltree_latex/canonicalize.py. The mojibake step uses
 * the table fixer (Python prefers ftfy when installed; corpus cases that
 * need ftfy carry `"impl": ["python"]`).
 *
 * Heuristic. Idempotent. Runs ONCE, at the generation chokepoint. Never on
 * the read path (Backend #1595, the 14 September 2026 incident).
 */

import {
  detectCommandMissingArgument,
  detectFracMissingArgs,
} from "./audit.js";
import {
  codePointLength,
  countOf,
  escapeRegExp,
  charAt,
  isAlnum,
  isAlpha,
  isAsciiDigit,
  isDigit,
  isSpace,
  matchAt,
  pyLstrip,
  pyRstrip,
  pyStrip,
} from "./chars.js";
import {
  ARGUMENT_COMMANDS,
  COLLAPSIBLE_COMMANDS,
  KATEX_COMMANDS,
  STRUCTURAL_COMMANDS,
} from "./commands.js";
import { after, afterCodePoint, replaceAfter } from "./lookbehind.js";
import { fixMojibakeTable } from "./mojibake.js";
import { isFormula } from "./normalize.js";
import { isPlainObject, repair } from "./repair.js";
import { segment } from "./segment.js";
import { mathMask, mathRanges } from "./spans.js";
import {
  UNICODE_MATH,
  convertCombiningVec,
  normalizeHomoglyphs,
  unicodeMathToLatex,
  wrapBareUnicodeMath,
} from "./unicodeMath.js";
import { isNonContentKey, isUrlOrPathString } from "./walk.js";

// ---------------------------------------------------------------------------
// Delimiter rewrites
// ---------------------------------------------------------------------------

// Not after a backslash (AFTER_BACKSLASH); the content's last character is
// not a backslash either (`\\)` is not a closer).
const PAREN_INLINE_RE = /\\\(([\s\S]*?[^\\])\\\)/g;
const BRACKET_DISPLAY_RE = /\\\[([\s\S]*?[^\\])\\\]/g;
const AFTER_BACKSLASH = after("\\");

// Inside a math segment, x^10 → x^{10}, a_12 → a_{12} (2+ digit runs only).
const MISSING_BRACE_RE = /([\^_])(-?\d{2,})/g;
const DISPLAY_SPAN_RE = /\$\$([\s\S]+?)\$\$/g;
// Not after a `$` (AFTER_DOLLAR).
const INLINE_SPAN_RE = /\$([^$]+?)\$(?!\$)/g;
const AFTER_DOLLAR = after("$");
// An identifier that ended up inside math (`$q_001_easy_2026$`): bracing its
// digit runs only produces a double-subscript error.
const IDENTIFIER_IN_MATH_RE = /[A-Za-z0-9]+(?:_[A-Za-z0-9]+){2,}/g;

function normalizeBracesInMath(seg: string): string {
  const protectedRanges: Array<[number, number]> = [];
  for (const m of seg.matchAll(IDENTIFIER_IN_MATH_RE)) {
    protectedRanges.push([m.index, m.index + m[0].length]);
  }
  return seg.replace(
    MISSING_BRACE_RE,
    (m: string, marker: string, digits: string, offset: number) => {
      if (protectedRanges.some(([a, b]) => a <= offset && offset < b)) return m;
      return marker + "{" + digits + "}";
    },
  );
}

function normalizeBraces(text: string): string {
  text = text.replace(
    DISPLAY_SPAN_RE,
    (_m, inner: string) => "$$" + normalizeBracesInMath(inner) + "$$",
  );
  text = replaceAfter(
    text,
    INLINE_SPAN_RE,
    AFTER_DOLLAR,
    (_m, inner: string) => "$" + normalizeBracesInMath(inner) + "$",
  );
  return text;
}

// ---------------------------------------------------------------------------
// Structural fixes
// ---------------------------------------------------------------------------

// An EVEN run of backslashes directly before a KaTeX command is JSON
// re-encoding damage (`\\frac`); an odd run (`\\\frac`) is a line break
// followed by a command and is left alone.
// Not after a backslash (AFTER_BACKSLASH): the run is the whole run.
const COLLAPSE_RE = new RegExp(
  "((?:\\\\\\\\)+)(" +
    [...COLLAPSIBLE_COMMANDS]
      .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0))
      .map(escapeRegExp)
      .join("|") +
    ")(?![a-zA-Z])",
  "g",
);

const ROW_ENVIRONMENT_RE = /\\begin\{|&/;
const TWO_ARGUMENT_COMMANDS: ReadonlySet<string> = new Set([
  "frac",
  "dfrac",
  "tfrac",
  "cfrac",
  "binom",
  "dbinom",
  "tbinom",
]);

/**
 * `\\frac` → `\frac` everywhere EXCEPT inside a math span that holds an
 * environment or an alignment `&`: there `\\` is a row separator and
 * `a&b\\cos x` really is a row starting with `\cos`. Single-letter names
 * (`\c`, `\b`) are never collapsed: `\\c` is a row + "c".
 */
function collapseDoubleBackslashes(text: string): string {
  if (!text.includes("\\\\")) return text;
  const collapse = (chunk: string): string =>
    replaceAfter(
      chunk,
      COLLAPSE_RE,
      AFTER_BACKSLASH,
      (m: string, _run: string, name: string) =>
        name.length === 1 ? m : "\\" + name,
    );
  const out: string[] = [];
  let pos = 0;
  for (const { start, end } of mathRanges(text)) {
    out.push(collapse(text.slice(pos, start)));
    const span = text.slice(start, end);
    out.push(ROW_ENVIRONMENT_RE.test(span) ? span : collapse(span));
    pos = end;
  }
  out.push(collapse(text.slice(pos)));
  return out.join("");
}

function countChar(s: string, c: string): number {
  let n = 0;
  for (const ch of s) if (ch === c) n++;
  return n;
}

const LEFT_BRACE_RE = /\\left(?!\\)\{/g;
const RIGHT_BRACE_RE = /\\right(?!\\)\}/g;

function fixLeftRightBraces(text: string): string {
  text = text.replace(LEFT_BRACE_RE, () => "\\left\\{");
  text = text.replace(RIGHT_BRACE_RE, () => "\\right\\}");
  return text;
}

// ---------------------------------------------------------------------------
// Currency (Backend rule: only when the unescaped `$` count is odd)
// ---------------------------------------------------------------------------

// Not after a backslash (AFTER_BACKSLASH).
const CURRENCY_RE = /\$(\d[\d,]*(?:\.\d+)?)(?=[\s.,;!?)\]\-–—]|$)/g;

/**
 * True when an odd run of backslashes precedes `text[i]` (`\$` is an escaped
 * dollar, `\\$` a line break followed by a real one).
 */
function dollarEscaped(text: string, i: number): boolean {
  let k = i - 1;
  while (k >= 0 && text[k] === "\\") k--;
  return (i - 1 - k) % 2 === 1;
}

function countUnescapedDollars(text: string): number {
  let n = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "$" && !dollarEscaped(text, i)) n++;
  }
  return n;
}

// `\$` preceded by an even run of backslashes (none, or `\\` line breaks):
// only that dollar is escaped. `\\$\frac{1}{2}$` is a line break followed by
// a span, and stashing its `\$` once broke the span into `\\$$…$$`.
// Not after a backslash (AFTER_BACKSLASH).
const ESCAPED_DOLLAR_RE = /((?:\\\\)*)\\\$/g;

function stashEscapedDollars(text: string): string {
  if (!text.includes("\\$")) return text;
  return replaceAfter(
    text,
    ESCAPED_DOLLAR_RE,
    AFTER_BACKSLASH,
    (_m, run: string) => run + ESCAPED_DOLLAR_SENTINEL,
  );
}

function escapeCurrencyOddOnly(text: string): string {
  if (countUnescapedDollars(text) % 2 === 0) return text;
  return replaceAfter(
    text,
    CURRENCY_RE,
    AFTER_BACKSLASH,
    (_m, amount: string) => "\\$" + amount,
  );
}

// ---------------------------------------------------------------------------
// Bare-command wrapping
// ---------------------------------------------------------------------------

const STRUCTURAL_CMD_RE = new RegExp(
  "\\\\(?:" + STRUCTURAL_COMMANDS.join("|") + ")(?![A-Za-z])",
);
const STRUCTURAL_CMD_AT_RE = new RegExp(
  "\\\\(?:" + STRUCTURAL_COMMANDS.join("|") + ")(?![A-Za-z])",
  "y",
);

/**
 * Index one past the command at `start`, its `[..]`/`{..}` arguments and
 * adjacent `_x` / `^x` scripts (nested braces handled).
 */
function findCommandExtent(text: string, start: number): number {
  const n = text.length;
  let i = start + 1;
  while (i < n && isAlpha(charAt(text, i))) i += charAt(text, i).length;
  while (i < n) {
    const ch = text[i];
    if (ch === "[" || ch === "{") {
      const opener = ch;
      const closer = opener === "[" ? "]" : "}";
      let depth = 1;
      i++;
      while (i < n && depth > 0) {
        if (text[i] === opener) depth++;
        else if (text[i] === closer) depth--;
        i++;
      }
    } else if (ch === "_" || ch === "^") {
      i++;
      if (i >= n) break;
      if (text[i] === "{") {
        let depth = 1;
        i++;
        while (i < n && depth > 0) {
          if (text[i] === "{") depth++;
          else if (text[i] === "}") depth--;
          i++;
        }
      } else if (text[i] === "\\") {
        i++;
        while (i < n && isAlpha(charAt(text, i))) i += charAt(text, i).length;
      } else if (!isSpace(text[i])) {
        i += charAt(text, i).length;
      } else {
        break;
      }
    } else {
      break;
    }
  }
  return i;
}

const ANY_LATEX_CMD_RE = /\\[a-zA-Z]+/g;
// A lesson-script line (`\teacher: …`) is prose, however short.
const SCRIPT_LABEL_RE = /\\[a-z][a-z_]*:/;
const TEXT_BRACE_RE = /\\text\s*\{[^}]*\}/g;
const INLINE_DOLLAR_RE = /\$[^$]*\$/g;
const PROSE_WORD_RE = /[A-Za-z]{4,}/;
// Short function words that make a string prose even though they are under
// four letters (Backend's prose test was "a 4+ letter word", which let
// `3 \times 10^8 and \frac{a}{b}` be wrapped whole, italicising "and").
const PROSE_STOPWORDS: ReadonlySet<string> = new Set(
  (
    "a an and are as at be but by for if in is it of on or so the then to was " +
    "we he she you all any can did do does get got had has how its let may " +
    "not now one our out per put see set two use via was who why yet"
  ).split(" "),
);
// A whole ASCII letter run of 1-3 letters: see shortWords().
const LETTER_RUN_RE = /[A-Za-z]+/g;
function shortWords(s: string): string[] {
  return (s.match(LETTER_RUN_RE) ?? []).filter((w) => w.length <= 3);
}
// Prose in any other script (Devanagari, Tamil, …): a run of two or more
// non-ASCII letters (Python `[^\W\d_\x00-\x7f][^\W\d_]+`).
const NON_ASCII_WORD_RE =
  /(?![\x00-\x7f])[\p{L}\p{Nl}\p{No}][\p{L}\p{Nl}\p{No}]+/u;

// Every character UNICODE_MATH maps to `^{…}` or `_{…}` (²³, ⁻, ₀, ⁿ, ₐ, …).
const UNICODE_SCRIPT_RE = new RegExp(
  "[" +
    escapeRegExp(
      Object.keys(UNICODE_MATH)
        .filter(
          (k) =>
            UNICODE_MATH[k].startsWith("^{") ||
            UNICODE_MATH[k].startsWith("_{"),
        )
        .join(""),
    ) +
    "]",
  "g",
);

function hasDollarInsideBraces(text: string): boolean {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    const unescaped = i === 0 || text[i - 1] !== "\\";
    if (ch === "{" && unescaped) depth++;
    else if (ch === "}" && unescaped && depth > 0) depth--;
    else if (ch === "$" && unescaped && depth > 0) return true;
  }
  return false;
}

// `\ce` / `\pu` need KaTeX's mhchem extension.
const CHEMISTRY_CMD_RE = /\\(?:ce|pu)(?![A-Za-z])/;

function wrapPureMathShortStrings(text: string, chemistry = true): string {
  if (codePointLength(text) > 200 || text.includes("$$")) return text;
  ANY_LATEX_CMD_RE.lastIndex = 0;
  const commands = [...text.matchAll(ANY_LATEX_CMD_RE)];
  if (commands.length === 0) return text;
  if (hasDollarInsideBraces(text)) return text;
  if (SCRIPT_LABEL_RE.test(text)) return text;
  // A renderer without mhchem (Fillers: KaTeX core) asks for
  // `chemistry: false`: the command stays prose instead of a red error.
  if (!chemistry && CHEMISTRY_CMD_RE.test(text)) return text;
  // An unpaired `$` means the author's spans are broken; stripping and
  // re-wrapping would not converge (`$ H₂` → `$ $…$` → …).
  if (countUnescapedDollars(text) % 2 === 1) return text;
  // At least one REAL command must sit outside a span: `\\cs` (a line
  // break followed by "cs") is not math and must not be wrapped.
  const mask = mathMask(text);
  const hasBareCmd = commands.some(
    (m) => !mask[m.index] && KATEX_COMMANDS.has(m[0].slice(1)),
  );
  if (!hasBareCmd) return text;
  // A command that needs an argument and has none (`\frac` alone) cannot
  // render however it is wrapped.
  if (
    detectCommandMissingArgument(text).length > 0 ||
    detectFracMissingArgs(text).length > 0
  ) {
    return text;
  }
  let stripped = text.replace(TEXT_BRACE_RE, "");
  stripped = stripped.replace(INLINE_DOLLAR_RE, "");
  stripped = stripped.replace(ANY_LATEX_CMD_RE, "");
  if (PROSE_WORD_RE.test(stripped)) return text;
  // Prose in any other script: a run of two or more non-ASCII letters. Bare
  // Greek was already wrapped by step 14. Unicode super/subscripts (`10²³`)
  // are math, not letters of a word: they are blanked out first.
  if (NON_ASCII_WORD_RE.test(stripped.replace(UNICODE_SCRIPT_RE, " ")))
    return text;
  for (const w of shortWords(stripped)) {
    if (PROSE_STOPWORDS.has(w.toLowerCase())) return text;
  }
  let inner = pyStrip(text);
  if (!inner) return text;
  inner = inner.split("$").join("");
  if (!inner) return text;
  const lead = text.slice(0, text.length - pyLstrip(text).length);
  const trail = text.slice(pyRstrip(text).length);
  return lead + "$" + inner + "$" + trail;
}

// Not right after the currency sentinel (its LAST char, U+E001), a backslash
// (`\log_{10}` is a command, not a bare script) or a `$`. Python's `\b` is
// Unicode-aware; the run starts with `[A-Za-z0-9]`, so the boundary reduces
// to "the previous character is not a word character". Both checks are the
// code-point test BARE_SCRIPT_BLOCKED (no lookbehind: old Safari).
const BARE_SCRIPT_BLOCKED = afterCodePoint(/[\ue001\\$\p{L}\p{N}_]/u);
const BARE_SCRIPT_RE = new RegExp(
  "[A-Za-z0-9]+" +
    "(?:[_^](?:\\{[^{}]*\\}|\\\\[a-zA-Z]+|[A-Za-z0-9]+))+" +
    "[A-Za-z0-9]*",
  "gu",
);

/**
 * snake_case / ALL_CAPS / slug tokens the script regex matches by accident:
 * `MCQ_SINGLE`, `q_001_easy_2026`, `ahs_69e74f5e84fd`.
 */
function looksLikeIdentifier(s: string): boolean {
  for (const c of "\\{}^") if (s.includes(c)) return false;
  const first = s.indexOf("_");
  if (first === -1) return false;
  if (s.indexOf("_", first + 1) !== -1) return true;
  const base = s.slice(0, first);
  const rest = s.slice(first + 1);
  if (base.length >= 3) return true;
  // A two-letter lowercase base is a word or an id prefix (`lo_0` gap
  // titles), not a variable (`x_0`, `v_1`, `a_n`; chemistry is capitals).
  if (/^[a-z]{2}$/.test(base)) return true;
  // A class name: digits, underscore, 1–4 capital letters (`10_A`, `6_B`,
  // `12_PCM`). Math never writes a numeric base with a capital subscript.
  if (/^[0-9]+$/.test(base) && /^[A-Z]{1,4}$/.test(rest)) return true;
  // `no_capture`, `ai_recreate`: a suffix that is a lowercase WORD (3+
  // letters, nothing else) is an enum, not a subscript (`v_avg` is the one
  // real-math casualty; `E_n`, `x_0`, `H_2O` keep their short suffixes).
  return /^[a-z]{3,}$/.test(rest);
}

function wrapBareScripts(text: string): string {
  if (!text.includes("^") && !text.includes("_")) return text;
  const inMathAt = mathMask(text);
  return replaceAfter(
    text,
    BARE_SCRIPT_RE,
    BARE_SCRIPT_BLOCKED,
    (m: string, offset: number) => {
      if (inMathAt[offset] || looksLikeIdentifier(m)) return m;
      return "$" + m + "$";
    },
  );
}

function wrapBareLatexCommands(text: string): string {
  if (!text.includes("\\") || !STRUCTURAL_CMD_RE.test(text)) return text;
  const n = text.length;
  // What is math is what the renderers will typeset (`segment`), not `$`
  // parity: `$ $\text{H}_{2}$` has one literal dollar and one span, and
  // parity once wrapped the span a second time into `$$…$$`.
  const mask = mathMask(text);
  const out: string[] = [];
  let i = 0;
  while (i < n) {
    const ch = text[i];
    if (!mask[i] && ch === "\\") {
      const m = matchAt(STRUCTURAL_CMD_AT_RE, text, i);
      if (m) {
        let end = findCommandExtent(text, i);
        let touchesMath = false;
        for (let k = i; k < end; k++)
          if (mask[k]) {
            touchesMath = true;
            break;
          }
        if (text.slice(i, end).includes("$") || touchesMath) {
          out.push(ch);
          i++;
          continue;
        }
        // A command that needs an argument but has none (`use \sqrt here`)
        // would become `$\sqrt$`, a parse error painted red; left as prose
        // it is at least readable and `audit` flags it.
        const nameEnd = i + m[0].length;
        const name = text.slice(i + 1, nameEnd);
        if (ARGUMENT_COMMANDS.includes(name) && end === nameEnd) {
          out.push(ch);
          i++;
          continue;
        }
        // `\frac{x}` / `\tbinom{x}`: a two-argument command with one
        // argument fails in every renderer; leave it as prose.
        if (
          TWO_ARGUMENT_COMMANDS.has(name) &&
          countChar(text.slice(nameEnd, end), "{") < 2
        ) {
          out.push(ch);
          i++;
          continue;
        }
        // A number right after (`\sqrt{2}3`) joins the span: a closing `$`
        // followed by a digit is not a closer.
        if (end < n && isAsciiDigit(text[end]) && !mask[end])
          end += matchAt(NUMBER_AFTER_COMMAND_RE, text, end)![0].length;
        // A literal `$` right before or after (`$\frac{1}{2}` with no
        // closer): the author's delimiters are broken and a new span would
        // only make `$$`. Leave it as prose.
        if (
          (i > 0 && text[i - 1] === "$" && !mask[i - 1]) ||
          (end < n && text[end] === "$" && !mask[end])
        ) {
          out.push(ch);
          i++;
          continue;
        }
        out.push("$", text.slice(i, end), "$");
        if (end < n && isDigit(charAt(text, end)) && !mask[end]) out.push(" ");
        i = end;
        continue;
      }
    }
    out.push(ch);
    i++;
  }
  return out.join("");
}

const NUMBER_AFTER_COMMAND_RE = /[0-9]+(?:\.[0-9]+)?/y;

// ---------------------------------------------------------------------------
// `$ x^2 + 1 = 0 $`: a span whose content is padded with spaces
// ---------------------------------------------------------------------------

const PADDED_SPAN_HINT_RE = /\$[ \t]|[ \t]\$/;
const STRONG_MATH_RE = /\\[A-Za-z]|[\^_]/;
const WEAK_MATH_RE = /=/;
const UNICODE_MATH_CHAR_RE = new RegExp(
  "[" + escapeRegExp(Object.keys(UNICODE_MATH).join("")) + "]",
);

/**
 * True when the content of a `$ … $` pair is a formula, not prose between
 * two currency amounts (`$ 5 and got $`).
 */
function looksLikePaddedMath(core: string): boolean {
  const strong = STRONG_MATH_RE.test(core) || UNICODE_MATH_CHAR_RE.test(core);
  if (!strong) {
    // `=` alone is enough unless the content starts like an amount.
    if (!WEAK_MATH_RE.test(core) || isDigit(charAt(core, 0))) return false;
  }
  // A command that needs an argument and has none (`$5 \text $`) cannot
  // render; as prose it at least stays readable.
  const probe = "$" + core + "$";
  if (
    detectCommandMissingArgument(probe).length > 0 ||
    detectFracMissingArgs(probe).length > 0
  )
    return false;
  let words = core.replace(TEXT_BRACE_RE, "");
  words = words.replace(ANY_LATEX_CMD_RE, "");
  if (PROSE_WORD_RE.test(words)) return false;
  for (const w of shortWords(words))
    if (PROSE_STOPWORDS.has(w.toLowerCase())) return false;
  return true;
}

function stripSpacesTabs(s: string): string {
  let a = 0;
  let b = s.length;
  while (a < b && (s[a] === " " || s[a] === "\t")) a++;
  while (b > a && (s[b - 1] === " " || s[b - 1] === "\t")) b--;
  return s.slice(a, b);
}

/** The code point that ends right before index `i` ("" at the start). */
function charBefore(s: string, i: number): string {
  if (i <= 0) return "";
  const lo = s.charCodeAt(i - 1);
  if (lo >= 0xdc00 && lo <= 0xdfff && i >= 2) {
    const hi = s.charCodeAt(i - 2);
    if (hi >= 0xd800 && hi <= 0xdbff) return s.slice(i - 2, i);
  }
  return s[i - 1];
}

function trimPaddedLine(line: string): string {
  if (line.includes("$$")) return line;
  const dollars: number[] = [];
  for (let k = 0; k < line.length; k++)
    if (line[k] === "$" && !dollarEscaped(line, k)) dollars.push(k);
  // Unpaired: which dollar is currency is not ours to guess.
  if (dollars.length < 2 || dollars.length % 2) return line;
  const out: string[] = [];
  let pos = 0;
  for (let p = 0; p + 1 < dollars.length; p += 2) {
    const a = dollars[p];
    const b = dollars[p + 1];
    const inner = line.slice(a + 1, b);
    const core = stripSpacesTabs(inner);
    if (
      !core ||
      core === inner ||
      !(looksLikePaddedMath(core) || isFormula(core)) ||
      // A dollar glued to a word or number outside the pair (`$x = $y`,
      // `wait$ … $now`) reads as currency or a typo.
      (b + 1 < line.length && isAlnum(charAt(line, b + 1))) ||
      (a > 0 && isAlnum(charBefore(line, a)))
    )
      continue;
    out.push(line.slice(pos, a));
    out.push("$" + core + "$");
    pos = b + 1;
  }
  out.push(line.slice(pos));
  return out.join("");
}

/**
 * `Solve $ x^2 + 1 = 0 $ now` → `Solve $x^2 + 1 = 0$ now` (spec §3 step 10a).
 * The renderers do not open a span on `$` + space, so a padded formula shows
 * its dollars and the wrapping steps used to nest a second span inside it.
 * In text segments only, dollars are paired in order on each line; a pair is
 * trimmed when its padded content is math. `I paid $ 5 and got $ 3 back` is
 * currency and stays.
 */
export function trimPaddedSpans(text: string): string {
  if (!text.includes("$") || !PADDED_SPAN_HINT_RE.test(text)) return text;
  const out: string[] = [];
  for (const seg of segment(text)) {
    let raw = seg.raw;
    if (seg.kind === "text" && countChar(raw, "$") >= 2)
      raw = raw.split("\n").map(trimPaddedLine).join("\n");
    out.push(raw);
  }
  return out.join("");
}
// ---------------------------------------------------------------------------
// `$\frac{1}{2$`: a closed span whose last group was never closed
// ---------------------------------------------------------------------------

const LEFT_CMD_RE = /\\left(?![A-Za-z])/g;
const RIGHT_CMD_RE = /\\right(?![A-Za-z])/g;
// Python `\\([A-Za-z]+)\s*$` on an already right-stripped string.
const TRAILING_CMD_RE = /\\([A-Za-z]+)$/;
// A group may not end right after these: the added `}` would leave them
// without their argument (`$\frac{1}{\sqrt$`, `$x^{2^$`).
const NEEDS_ARGUMENT: ReadonlySet<string> = new Set([
  ...ARGUMENT_COMMANDS,
  ...TWO_ARGUMENT_COMMANDS,
  "left",
  "right",
  "begin",
  "end",
  "sqrt",
  "cbrt",
]);

function countMatches(re: RegExp, s: string): number {
  return (s.match(re) ?? []).length;
}

/**
 * How many `}` close `content`, or 0 when it is balanced, has more `}` than
 * `{` at any point, or when closing it would guess: the innermost open group
 * is empty or ends in `\ ^ _ &` or in a command that needs an argument.
 * `\{` / `\}` do not count.
 */
function missingClosers(content: string): number {
  const stack: number[] = [];
  let i = 0;
  const n = content.length;
  while (i < n) {
    const ch = content[i];
    if (ch === "\\") {
      i += 2;
      continue;
    }
    if (ch === "{") stack.push(i);
    else if (ch === "}") {
      if (stack.length === 0) return 0;
      stack.pop();
    }
    i++;
  }
  if (stack.length === 0) return 0;
  const inner = pyRstrip(content.slice(stack[stack.length - 1] + 1));
  if (!inner || "\\^_&{".includes(inner[inner.length - 1])) return 0;
  const m = TRAILING_CMD_RE.exec(inner);
  if (m && NEEDS_ARGUMENT.has(m[1])) return 0;
  return stack.length;
}

function closeBracesInLine(line: string): string {
  const dollars: number[] = [];
  for (let k = 0; k < line.length; k++) {
    if (line[k] !== "$") continue;
    let run = 0;
    while (k - 1 - run >= 0 && line[k - 1 - run] === "\\") run++;
    if (run % 2 === 0) dollars.push(k);
  }
  if (dollars.length < 2 || dollars.length % 2) return line;
  const out: string[] = [];
  let last = 0;
  for (let t = 0; t + 1 < dollars.length; t += 2) {
    const a = dollars[t];
    const b = dollars[t + 1];
    const content = line.slice(a + 1, b);
    if (
      !content ||
      isSpace(charAt(content, 0)) ||
      isSpace(charBefore(content, content.length)) ||
      (b + 1 < line.length && isDigit(charAt(line, b + 1))) ||
      !STRONG_MATH_RE.test(content)
    )
      continue;
    const missing = missingClosers(content);
    if (!missing) continue;
    if (
      countMatches(LEFT_CMD_RE, content) !==
        countMatches(RIGHT_CMD_RE, content) ||
      countOf(content, "\\begin{") !== countOf(content, "\\end{")
    )
      continue;
    const fixed = content + "}".repeat(missing);
    const probe = "$" + fixed + "$";
    if (
      detectCommandMissingArgument(probe).length > 0 ||
      detectFracMissingArgs(probe).length > 0
    )
      continue;
    const segs = segment(probe);
    if (segs.length !== 1 || segs[0].kind !== "math") continue;
    out.push(line.slice(last, a + 1));
    out.push(fixed);
    last = b;
  }
  if (out.length === 0) return line;
  out.push(line.slice(last));
  return out.join("");
}

/**
 * `$\frac{1}{2$` → `$\frac{1}{2}$`; `$x^{2$` → `$x^{2}$` (spec §3 step 10b).
 *
 * A span whose last group was never closed is text to every renderer (the
 * closer is found at brace depth 0 only), so the formula shows its source.
 * In text segments only, line by line (a line with a `$$` or an odd count of
 * unescaped `$` is left alone), dollars are paired in order. A pair gets the
 * missing `}` appended to its content when all of: the content does not
 * start or end with whitespace and the closer is not followed by a digit
 * (the pandoc rules); it is math (a command, `^` or `_`); it has more `{`
 * than `}` and never more `}` than `{` (`\{` / `\}` do not count); the
 * innermost open group is not empty and does not end in `\ ^ _ &` or a
 * command that needs an argument (`$\frac{1}{$`, `$x^{$` stay: never guess
 * an argument); `\left` and `\right`, `\begin{` and `\end{` are matched;
 * and the result has no missing argument and is one span. Idempotent: a
 * balanced span is never touched.
 */
function closeUnbalancedBraces(text: string): string {
  if (!text.includes("{") || !text.includes("$")) return text;
  const out: string[] = [];
  for (const seg of segment(text)) {
    let raw = seg.raw;
    if (seg.kind === "text" && raw.includes("{") && countChar(raw, "$") >= 2)
      raw = raw
        .split("\n")
        .map((line) => (line.includes("$$") ? line : closeBracesInLine(line)))
        .join("\n");
    out.push(raw);
  }
  return out.join("");
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

const ESCAPED_DOLLAR_SENTINEL = "DOLLAR_ESC";
const URL_RE = /^\s*(?:https?|gs|data|blob):\/\/\S+\s*$/i;
const IMAGE_MARKER_RE = /\{\{IMAGE:[^}]+\}\}/g;
// `$` is excluded so a URL never swallows the math that follows it.
const EMBEDDED_URL_RE = /(?:https?|gs):\/\/[^\s<>"'$]+/gi;
// Stash sentinels are made of private-use characters only: no letter, digit,
// `_` or brace, so no later step can read one as a script (`IMG_10` once
// became `IMG_{10}`). The index is encoded as characters U+E100 + n.
const STASH_BASE = 0xe100;

function stashToken(idx: number): string {
  return "" + String.fromCharCode(STASH_BASE + idx) + "";
}

/** Options of `canonicalize`, `fix` and their deep walkers. */
export interface CanonicalizeOptions {
  /**
   * `false` never puts a bare `\ce{…}` / `\pu{…}` into a new math span, for
   * renderers without KaTeX's mhchem extension. Default `true`.
   */
  chemistry?: boolean;
}

/** Normalize a fresh model string to the canonical form (spec §3). */
export function canonicalize<T>(text: T, options?: CanonicalizeOptions): T;
export function canonicalize(
  text: unknown,
  options: CanonicalizeOptions = {},
): unknown {
  if (typeof text !== "string" || !text) return text;
  if (URL_RE.test(text)) return text;

  const imageStash: string[] = [];
  const stash = (m: string): string => {
    imageStash.push(m);
    return stashToken(imageStash.length - 1);
  };

  let out: string = text;
  if (out.includes("{{IMAGE:")) out = out.replace(IMAGE_MARKER_RE, stash);
  // A URL embedded in prose ("see https://…/a_b.png") is stashed the same
  // way: `wrapBareScripts` would otherwise read `a_b` as a subscript.
  if (out.includes("://")) out = out.replace(EMBEDDED_URL_RE, stash);

  out = repair(out);
  out = stashEscapedDollars(out);
  out = escapeCurrencyOddOnly(out);
  out = stashEscapedDollars(out);
  out = fixMojibakeTable(out);
  out = normalizeHomoglyphs(out);
  out = collapseDoubleBackslashes(out);
  out = fixLeftRightBraces(out);
  out = replaceAfter(
    out,
    PAREN_INLINE_RE,
    AFTER_BACKSLASH,
    (_m, inner: string) => "$" + inner + "$",
  );
  out = replaceAfter(
    out,
    BRACKET_DISPLAY_RE,
    AFTER_BACKSLASH,
    (_m, inner: string) => "$$" + inner + "$$",
  );
  out = trimPaddedSpans(out);
  out = closeUnbalancedBraces(out);
  out = normalizeBraces(out);
  out = unicodeMathToLatex(out, true);
  out = convertCombiningVec(out);
  out = wrapBareUnicodeMath(out);
  out = wrapBareLatexCommands(out);
  out = wrapBareScripts(out);
  out = wrapPureMathShortStrings(out, options.chemistry !== false);
  // Step 14 left the symbols inside bare script / command argument groups
  // (`e^{iπ}`, `\frac{π}{2}`) to steps 15–17, which put the whole group in
  // one span. A group none of them took is prose; its symbols are wrapped
  // now, on their own, as step 14 would have (step 17a).
  out = wrapBareUnicodeMath(out, false);
  // The wrapping steps create new spans whose content the span-only steps
  // (brace normalisation, Unicode → LaTeX) have not seen: running those two
  // once more makes one pass equal to two.
  out = normalizeBraces(out);
  out = unicodeMathToLatex(out, true);
  out = out.split(ESCAPED_DOLLAR_SENTINEL).join("\\$");
  // Restore last-stashed first: a URL stashed after an image marker may
  // contain that marker's sentinel (`gs://{{IMAGE:x}}`).
  for (let idx = imageStash.length - 1; idx >= 0; idx--) {
    out = out.split(stashToken(idx)).join(imageStash[idx]);
  }
  return out;
}

/**
 * `canonicalize` over every content string in a JSON-like document.
 * Skips non-content keys and URL-shaped values (CONTRACT §5); list items
 * inherit the parent key. A `Date` becomes its ISO-8601 string so a
 * document can be handed straight to a JSON response.
 */
export function canonicalizeDeep<T>(
  obj: T,
  options: CanonicalizeOptions = {},
): T {
  return mapContentStrings(obj, (s: string) => canonicalize(s, options));
}

/**
 * Apply `fn` to every content string of a JSON-like document: plain objects
 * and arrays are walked, non-content keys and URL-shaped values are skipped
 * (list items inherit the parent key), a `Date` becomes its ISO-8601 string
 * (unless `convertDates: false`) and everything else passes through.
 */
export function mapContentStrings<T>(
  obj: T,
  fn: (text: string) => string,
  options: { convertDates?: boolean } = {},
): T {
  return mapContentAny(obj, "", fn, options.convertDates ?? true) as T;
}

function mapContentAny(
  obj: unknown,
  keyHint: string,
  fn: (text: string) => string,
  convertDates: boolean,
): unknown {
  if (typeof obj === "string") {
    if (isNonContentKey(keyHint) || isUrlOrPathString(obj)) return obj;
    return fn(obj);
  }
  if (Array.isArray(obj))
    return obj.map((item) => mapContentAny(item, keyHint, fn, convertDates));
  if (isPlainObject(obj)) {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj))
      out[k] = mapContentAny(v, k, fn, convertDates);
    return out;
  }
  if (convertDates && obj instanceof Date) return obj.toISOString();
  return obj;
}
