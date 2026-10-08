/**
 * `fix`: the one call for people who do not want to learn the six.
 *
 *     import { fix, fixDeep } from "@pupiltree/latex";
 *     fix("Cost $5 and \\(\\theta\\) with \x0crac{1}{2} and π and H₂O")
 *     // -> 'Cost \\$5 and $\\theta$ with $\\frac{1}{2}$ and $\\pi$ and $\\text{H}_{2}\\text{O}$'
 *
 * `fix` = `normalize` → `canonicalize` → `wrapBareSymbolCommands` →
 * `wrapUnicodeChemistry` → `wrapUnicodeScripts` → `escapeTextSpecials` →
 * `mergeAdjacentMath`. Idempotent. Non-strings pass through. `fixDeep`
 * walks a JSON-like document and skips ids, URLs, paths, timestamps and
 * status enums (CONTRACT §5). Port of python/pupiltree_latex/fix.py.
 *
 * Where to call it: on fresh model output at the write path, once, then
 * store; or on whatever text is about to be displayed (the `MathText`
 * component and `typesetMath` do it for you). Not as a read-path rewrite of
 * stored content served back to other apps (CONTRACT §3).
 */

import {
  canonicalize,
  collapseDoubleGroups,
  mapContentStrings,
  openSurplusBraces,
} from "./canonicalize.js";
import type { CanonicalizeOptions } from "./canonicalize.js";
import { isAsciiDigit, matchAt } from "./chars.js";
import { padSpan, wrapUnicodeChemistry } from "./chemistry.js";
import { SYMBOL_COMMANDS } from "./commands.js";
import {
  after,
  afterCodePoint,
  matchAllAfter,
  replaceAfter,
} from "./lookbehind.js";
import { normalize } from "./normalize.js";
import { segment } from "./segment.js";
import { delimiterWidth } from "./spans.js";
import {
  DECLARATION_COMMANDS,
  SINGLE_LETTER_UNITS,
  UNIT_BASES,
} from "./tables.g.js";
import {
  clusterLeft,
  clusterRight,
  convertCluster,
  wrapCluster,
} from "./unicodeMath.js";

export { SINGLE_LETTER_UNITS, SYMBOL_COMMANDS, UNIT_BASES };

const AFTER_BACKSLASH = after("\\");
const AFTER_BACKSLASH_OR_DOLLAR = after("\\$");

// ---------------------------------------------------------------------------
// Bare symbol commands
// ---------------------------------------------------------------------------

// Not after a backslash (AFTER_BACKSLASH).
const BARE_SYMBOL_RE = new RegExp(
  "\\\\(" +
    [...SYMBOL_COMMANDS]
      .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0))
      .join("|") +
    ")(?![A-Za-z])",
  "g",
);

function applyToTextSegments(
  text: string,
  transform: (raw: string) => string,
): string {
  let out = "";
  for (const seg of segment(text))
    out += seg.kind === "text" ? transform(seg.raw) : seg.raw;
  return out;
}

function applyToMathSegments(
  text: string,
  transform: (value: string) => string,
): string {
  let out = "";
  for (const seg of segment(text)) {
    if (seg.kind === "math") {
      const raw = seg.raw;
      const k = delimiterWidth(raw);
      out +=
        raw.slice(0, k) +
        transform(raw.slice(k, raw.length - k)) +
        raw.slice(raw.length - k);
    } else {
      out += seg.raw;
    }
  }
  return out;
}

const SYMBOL_ALTERNATION = [...SYMBOL_COMMANDS]
  .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0))
  .join("|");
// A symbol command that a broken earlier pass left between two dollars which
// the renderers do not read as a span (`x$\leq$5`: a closer followed by a
// digit is not a closer). In a text segment its dollars are dropped first
// and it is then wrapped like any bare command.
// Not after a backslash or a `$` (AFTER_BACKSLASH_OR_DOLLAR).
const DELIMITED_SYMBOL_RE = new RegExp(
  "\\$(\\\\(?:" + SYMBOL_ALTERNATION + "))\\$(?![$A-Za-z])",
  "g",
);
// Inside a cluster: another bare symbol command (`3\times4\times5`).
const CLUSTER_COMMAND_RE = new RegExp(
  "\\\\(?:" + SYMBOL_ALTERNATION + ")(?![A-Za-z])",
  "y",
);

function wrapSymbolsInText(t: string): string {
  if (t.includes("$"))
    t = replaceAfter(
      t,
      DELIMITED_SYMBOL_RE,
      AFTER_BACKSLASH_OR_DOLLAR,
      (_m, cmd: string) => cmd,
    );
  const out: string[] = [];
  let last = 0;
  for (const m of matchAllAfter(BARE_SYMBOL_RE, t, AFTER_BACKSLASH)) {
    const at = m.index ?? 0;
    if (at < last) continue; // already inside the previous cluster
    const start = clusterLeft(t, at, last);
    const end = clusterRight(t, at, null, CLUSTER_COMMAND_RE);
    out.push(t.slice(last, start));
    out.push(wrapCluster(t, start, end, convertCluster(t.slice(start, end))));
    last = end;
  }
  out.push(t.slice(last));
  return out.join("");
}

/**
 * `3 \times 10` → `3 $\times$ 10`; `\alpha` → `$\alpha$` — for argument-less
 * symbol commands (`SYMBOL_COMMANDS`) outside math spans only. The span
 * takes the tight cluster around the command (`x\leq5` → `$x\leq5$`,
 * `\alpha_1` → `$\alpha_1$`, `3\times4\times5` → `$3\times4\times5$`), so it
 * never ends right before a digit; a command already between stray dollars
 * (`x$\leq$5`) is re-wrapped without them, never into `$$`.
 */
export function wrapBareSymbolCommands<T>(text: T): T;
export function wrapBareSymbolCommands(text: unknown): unknown {
  if (typeof text !== "string" || !text.includes("\\")) return text;
  return applyToTextSegments(text, wrapSymbolsInText);
}

// ---------------------------------------------------------------------------
// Unicode scripts (chemistry lives in chemistry.ts)
// ---------------------------------------------------------------------------

const SUB_DIGITS = "₀-₉";
const SUP_CHARS = "⁰¹²³⁴-⁹⁺⁻";
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
const SUP_FIRST_RE = new RegExp("^[" + SUP_CHARS + "]");
const ANY_SCRIPT_RE = new RegExp("[" + SUB_DIGITS + SUP_CHARS + "]");
// Any other base + Unicode scripts outside math (`10⁻³`, `mc²`, `x₁`, `s²`):
// a word of letters/digits followed by one run of scripts.
// Not after a letter, digit or `_` (SCRIPT_RUN_BLOCKED, a code-point test).
const SCRIPT_RUN_BLOCKED = afterCodePoint(/[\p{L}\p{N}_]/u);
const SCRIPT_RUN_RE = new RegExp(
  "([A-Za-z0-9]+(?:\\.[0-9]+)?)([" +
    SUP_CHARS +
    "]+|[" +
    SUB_DIGITS +
    "]+)(?![" +
    SUB_DIGITS +
    SUP_CHARS +
    "])",
  "gu",
);

function mapChars(s: string, table: Readonly<Record<string, string>>): string {
  let out = "";
  for (const ch of s) out += table[ch] ?? ch;
  return out;
}

function scriptsInText(text: string): string {
  return replaceAfter(
    text,
    SCRIPT_RUN_RE,
    SCRIPT_RUN_BLOCKED,
    (m: string, base: string, scripts: string, offset: number) => {
      const before = offset > 0 ? text[offset - 1] : "";
      if (before === "\\" || before === "{") return m;
      // A unit is set upright (`240 cm³`, `m/s²`, `mol⁻¹`, `per mm³`);
      // anything else (`mc²`, `x₁`, `10⁸`) is math.
      const afterNumber = numberOrSlashBefore(text, offset);
      if (
        UNIT_BASES.has(base) ||
        (/^[a-z]+$/.test(base) &&
          afterNumber &&
          (base.length > 1 ||
            SINGLE_LETTER_UNITS.has(base) ||
            text[offset - 1] !== "/"))
      )
        base = "\\text{" + base + "}";
      const span = SUP_FIRST_RE.test(scripts)
        ? "$" + base + "^{" + mapChars(scripts, SUP_MAP) + "}$"
        : "$" + base + "_{" + mapChars(scripts, SUB_MAP) + "}$";
      return padSpan(text, offset, offset + m.length, span);
    },
  );
}

/** True when `text.slice(0, start)` ends with `/` or a digit plus spaces/tabs. */
function numberOrSlashBefore(text: string, start: number): boolean {
  let k = start - 1;
  if (k >= 0 && text[k] === "/") return true;
  while (k >= 0 && (text[k] === " " || text[k] === "\t")) k--;
  return k >= 0 && isAsciiDigit(text[k]);
}

/**
 * `10⁻³` → `$10^{-3}$`, `mc²` → `$mc^{2}$`, `x₁` → `$x_{1}$` — a base of
 * letters/digits followed by one run of Unicode scripts, outside math spans,
 * after chemistry has taken its formulas.
 */
export function wrapUnicodeScripts<T>(text: T): T;
export function wrapUnicodeScripts(text: unknown): unknown {
  if (typeof text !== "string" || !text) return text;
  if (!ANY_SCRIPT_RE.test(text)) return text;
  return applyToTextSegments(text, scriptsInText);
}

// ---------------------------------------------------------------------------
// Specials inside math
// ---------------------------------------------------------------------------

const TEXT_GROUP_RE =
  /\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox)\s*\{/y;
// One-character matches: "not after a backslash" is checked in the callback.
const PERCENT_RE = /%/g;
const DOLLAR_RE = /\$/g;

function escapeSpecialsInMath(value: string): string {
  // `%` starts a TeX comment: `$50%$` renders nothing after it.
  value = value.replace(PERCENT_RE, (m: string, at: number, s: string) =>
    at > 0 && s[at - 1] === "\\" ? m : "\\%",
  );
  // A `$` inside a `\text{…}` group would end the span for the renderer.
  let out = "";
  let i = 0;
  const n = value.length;
  while (i < n) {
    const m = matchAt(TEXT_GROUP_RE, value, i);
    if (m) {
      let depth = 0;
      let j = i + m[0].length - 1;
      while (j < n) {
        if (value[j] === "\\") {
          j += 2;
          continue;
        }
        if (value[j] === "{") depth++;
        else if (value[j] === "}") {
          depth--;
          if (depth === 0) {
            j++;
            break;
          }
        }
        j++;
      }
      out += value
        .slice(i, j)
        .replace(DOLLAR_RE, (m: string, at: number, s: string) =>
          at > 0 && s[at - 1] === "\\" ? m : "\\$",
        );
      i = j;
      continue;
    }
    out += value[i];
    i++;
  }
  return out;
}

/**
 * Inside math spans: `%` → `\%`; a `$` inside `\text{…}` → `\$`. Both would
 * otherwise cut the formula short in every renderer.
 */
export function escapeTextSpecials<T>(text: T): T;
export function escapeTextSpecials(text: unknown): unknown {
  if (typeof text !== "string" || (!text.includes("%") && !text.includes("$")))
    return text;
  return applyToMathSegments(text, escapeSpecialsInMath);
}

// ---------------------------------------------------------------------------
// Adjacent spans
// ---------------------------------------------------------------------------

const ONLY_BLANKS_RE = /^[ \t]*$/;
const ENV_RE = /\\(begin|end)\{/g;
// Declaration-style switches: they change the scope of a merged span.
const DECLARATION_RE = new RegExp(
  "\\\\(?:" + DECLARATION_COMMANDS.join("|") + ")(?![A-Za-z])",
);

/**
 * A span is merged only when it is self-contained: balanced braces and
 * matched `\begin`/`\end`. Merging a broken span would break its neighbours
 * too.
 */
function mergeable(value: string): boolean {
  let depth = 0;
  for (let i = 0; i < value.length; i++) {
    const ch = value[i];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth < 0) return false;
    }
  }
  if (depth !== 0) return false;
  // A declaration-style switch (`\bf`, `\color{red}`, `\Large`) acts on
  // everything after it in its span: merged, `$\flat$ $\bf x$` would set
  // the neighbours in bold too.
  if (value.includes("\\") && DECLARATION_RE.test(value)) return false;
  let begins = 0;
  let ends = 0;
  for (const m of value.matchAll(ENV_RE)) {
    if (m[1] === "begin") begins++;
    else ends++;
  }
  return begins === ends;
}

/**
 * `$\times$ $10^8$` → `$\times 10^8$`: inline spans separated by nothing or
 * by spaces/tabs become one span. Display spans, spans with prose between
 * them and spans that are not self-contained are left alone. Linear: each
 * span's mergeability is computed once.
 */
export function mergeAdjacentMath<T>(text: T): T;
export function mergeAdjacentMath(text: unknown): unknown {
  if (typeof text !== "string") return text;
  let dollars = 0;
  for (let i = 0; i < text.length; i++) if (text[i] === "$") dollars++;
  if (dollars < 4) return text;
  const segs = segment(text);
  const out: string[] = [];
  let runValues: string[] = [];
  let runOk = false;
  const flush = (): void => {
    if (runValues.length) {
      out.push("$" + runValues.join(" ") + "$");
      runValues = [];
    }
  };
  const isInline = (i: number): boolean =>
    segs[i].kind === "math" && !segs[i].display && segs[i].raw.startsWith("$");
  let i = 0;
  const n = segs.length;
  while (i < n) {
    const seg = segs[i];
    if (isInline(i)) {
      const ok = mergeable(seg.value);
      if (runValues.length && runOk && ok) {
        runValues.push(seg.value);
      } else {
        flush();
        runValues.push(seg.value);
        runOk = ok;
      }
      i++;
      continue;
    }
    if (
      seg.kind === "text" &&
      ONLY_BLANKS_RE.test(seg.raw) &&
      runValues.length &&
      i + 1 < n &&
      isInline(i + 1) &&
      runOk &&
      mergeable(segs[i + 1].value)
    ) {
      i++; // the blank separator disappears into the merged span
      continue;
    }
    flush();
    out.push(seg.raw);
    i++;
  }
  flush();
  return out.join("");
}

// ---------------------------------------------------------------------------
// The one call
// ---------------------------------------------------------------------------

/**
 * Repair, normalise, canonicalise, wrap what is still bare, escape what
 * would cut a formula short and merge adjacent spans, in one call.
 */
export function fix<T>(text: T, options?: CanonicalizeOptions): T;
export function fix(text: unknown, options: CanonicalizeOptions = {}): unknown {
  if (typeof text !== "string" || !text) return text;
  let out: string = canonicalize(normalize(text), options);
  out = wrapBareSymbolCommands(out);
  out = wrapUnicodeChemistry(out);
  out = wrapUnicodeScripts(out);
  out = escapeTextSpecials(out);
  // Spans created after `canonicalize` get its span repairs too (tags
  // v140-b1, v140-b2), before merging, which joins balanced spans only.
  out = openSurplusBraces(out);
  out = collapseDoubleGroups(out);
  return mergeAdjacentMath(out);
}

/**
 * `fix` over every content string of a JSON-like document, skipping
 * non-content keys and URL-shaped values (CONTRACT §5). Unlike
 * `canonicalizeDeep`, a `Date` passes through unchanged (as in Python).
 * Values under `options.narrativeKeys` (Class B narration, tag `v140-b5`)
 * get `repairDeep` only; `name@sibling` matches `name` beside `sibling`.
 */
export function fixDeep<T>(obj: T, options: CanonicalizeOptions = {}): T {
  return mapContentStrings(obj, (s: string) => fix(s, options), {
    convertDates: false,
    narrativeKeys: options.narrativeKeys,
  });
}

/**
 * True when `fix` would change more than `normalize` does: it would add
 * LaTeX for Unicode or bare maths (`H₂O`, `√2`, `π`, `x × y`, `\frac{1}{2}`
 * in prose) or repair a formula (tag `v140-b9`). `false` for non-strings
 * and for text `fix` leaves as `normalize` does.
 */
export function needsFix(
  text: unknown,
  options: CanonicalizeOptions = {},
): boolean {
  if (typeof text !== "string" || !text) return false;
  if (/^[\x00-\x7f]*$/.test(text) && !/[\\^_${}%`]/.test(text)) return false;
  return fix(text, options) !== normalize(text);
}
