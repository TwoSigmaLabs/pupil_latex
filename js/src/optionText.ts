/**
 * `normalizeOptionText`: one answer option, as the apps should show it.
 * Port of python/pupiltree_latex/option_text.py (tag `v140-b4`).
 */

import type { CanonicalizeOptions } from "./canonicalize.js";
import { isAlpha, isSpace, pyStrip } from "./chars.js";
import { fix } from "./fix.js";
import { segment } from "./segment.js";

// A plain `\text{…}` body: no maths specials, no braces, no dollar.
const WHOLE_TEXT_SPAN = String.raw`\\text\s*\{\s*([^{}\\$^_%&#]*?)\s*\}`;
const WHOLE_TEXT_SPAN_RE = new RegExp(WHOLE_TEXT_SPAN, "g");
const WHOLE_TEXT_SPAN_FULL_RE = new RegExp("^" + WHOLE_TEXT_SPAN + "$");
// An element sequence (`H`, `Na`, `NaCl`, `H2O`) is chemistry: kept.
const CHEMISTRY_BODY_RE = /^(?:[A-Z][a-z]?[0-9]*){1,4}$/;
// A whole span of plain words (`$Coulomb$`).
const PLAIN_WORDS_RE = /^[A-Za-z][A-Za-z .,'-]*$/;
const LONG_WORD_RE = /[A-Za-z][a-z]{3,}/;

const TEXT_CMD_RE = /\\text\s*\{\s*([^{}]*?)\s*\}/g;
const NEEDS_MATHS_RE = /[\\^_%&#]/;
const TEXT_WITH_SCRIPT_RE =
  /\\text\s*\{((?:[^{}]|\{[^{}]*\})*?[\^_]\{[^{}]*\}(?:[^{}]|\{[^{}]*\})*)\}/g;
const SCRIPT_GROUP_SPLIT_RE = /([\^_]\{[^{}]*\})/;
const SCRIPT_GROUP_FULL_RE = /^[\^_]\{[^{}]*\}$/;
const DOUBLE_SUPERSCRIPT_RE = /\^\{([^{}]*)\}\^\{([^{}]*)\}/;
const DOUBLE_SUPERSCRIPT_G_RE = /\^\{([^{}]*)\}\^\{([^{}]*)\}/g;

/** `%` `&` `#` not already escaped get a backslash (maths mode). */
function escapeSpecials(body: string): string {
  const out: string[] = [];
  for (let i = 0; i < body.length; i++) {
    const ch = body[i];
    if ("%&#".includes(ch) && (i === 0 || body[i - 1] !== "\\")) out.push("\\");
    out.push(ch);
  }
  return out.join("");
}

/** `\text{H_{2}O}` → `\text{H}_{2}\text{O}`; `^{-}^{1}` merges into `^{-1}`. */
function liftTextScripts(inner: string): string {
  const pieces: string[] = [];
  for (const run of inner.split(SCRIPT_GROUP_SPLIT_RE)) {
    if (SCRIPT_GROUP_FULL_RE.test(run)) pieces.push(run);
    else if (pyStrip(run)) pieces.push("\\text{" + run + "}");
  }
  let lifted = pieces.join("");
  while (DOUBLE_SUPERSCRIPT_RE.test(lifted))
    lifted = lifted.replace(DOUBLE_SUPERSCRIPT_G_RE, "^{$1$2}");
  return lifted;
}

function mathBody(body: string): string {
  if (!body.includes("\\text")) return body;
  body = body.replace(TEXT_WITH_SCRIPT_RE, (_m, inner: string) =>
    liftTextScripts(inner),
  );
  return body.replace(
    TEXT_CMD_RE,
    (m: string, inner: string, offset: number, whole: string) => {
      if (!NEEDS_MATHS_RE.test(inner)) return m;
      const before = offset > 0 ? whole[offset - 1] : " ";
      return (isSpace(before) ? "" : " ") + escapeSpecials(inner);
    },
  );
}

function textBody(raw: string): string {
  if (raw.includes("\\text")) {
    raw = raw.replace(
      WHOLE_TEXT_SPAN_RE,
      (m: string, inner: string, offset: number, whole: string) => {
        const next = whole.charAt(offset + m.length);
        return next === "_" || next === "^" ? m : inner;
      },
    );
  }
  return raw.split("\\{").join("{").split("\\}").join("}");
}

/** The words of a span that is only `\text{plain words}`, or null. */
function spanWord(value: string): string | null {
  const m = WHOLE_TEXT_SPAN_FULL_RE.exec(pyStrip(value));
  if (!m) return null;
  const word = m[1];
  if (word && [...word].some(isAlpha) && !CHEMISTRY_BODY_RE.test(word))
    return word;
  return null;
}

/** The plain word(s) of an option that is one inline span and nothing else. */
function wholeSpanWord(text: string): string | null {
  const segs = segment(pyStrip(text));
  if (segs.length !== 1 || segs[0].kind !== "math" || segs[0].display)
    return null;
  if (!segs[0].raw.startsWith("$")) return null;
  const body = pyStrip(segs[0].value);
  if (WHOLE_TEXT_SPAN_FULL_RE.test(body)) return spanWord(body);
  if (PLAIN_WORDS_RE.test(body) && LONG_WORD_RE.test(body))
    return pyStrip(body);
  return null;
}

/**
 * `fix`, then the option-field clean-ups (tag `v140-b4`): an option that is
 * one span of plain words loses the span (`$\text{Coulomb}$` → `Coulomb`);
 * outside maths `\text{word}` → `word` and `\{`/`\}` → `{`/`}`; inside maths
 * scripts move out of `\text{}` (`$\text{H_{2}O}$` →
 * `$\text{H}_{2}\text{O}$`) and a `\text{}` whose body needs maths mode is
 * unwrapped (`$50 \text{ %}$` → `$50 \%$`). Idempotent; non-strings pass
 * through.
 */
export function normalizeOptionText<T>(
  text: T,
  options?: CanonicalizeOptions,
): T;
export function normalizeOptionText(
  text: unknown,
  options: CanonicalizeOptions = {},
): unknown {
  if (typeof text !== "string" || !text) return text;
  const fixed: string = fix(text, options);
  const word = wholeSpanWord(fixed);
  if (word !== null) {
    const lead = fixed.slice(
      0,
      fixed.length - fixed.replace(/^\s+/, "").length,
    );
    const trail = fixed.slice(fixed.replace(/\s+$/, "").length);
    return lead + word + trail;
  }
  const out: string[] = [];
  for (const seg of segment(fixed)) {
    let raw = seg.raw;
    if (seg.kind === "math" && raw.startsWith("$")) {
      const k = raw.startsWith("$$") ? 2 : 1;
      const w = k === 1 ? spanWord(seg.value) : null;
      if (w !== null) raw = w;
      else
        raw =
          raw.slice(0, k) +
          mathBody(raw.slice(k, raw.length - k)) +
          raw.slice(raw.length - k);
    } else if (seg.kind === "text") {
      raw = textBody(raw);
    }
    out.push(raw);
  }
  return out.join("");
}
