/**
 * Mojibake repair: the deterministic table + context rules, identical in
 * Python, Dart and JS. Port of python/pupiltree_latex/mojibake.py
 * (`fix_mojibake_table`; the ftfy engine has no JS counterpart, so
 * `canonicalize` uses this fixer too). The table (including the generated
 * Latin-1 / cp1252 readings) comes from tables.g.ts.
 */

import { HTML_ENTITIES, MOJIBAKE_TABLE } from "./tables.g.js";

export { HTML_ENTITIES };

// HTML entities a model or an old export leaves in content (`a &amp; b`).
// ftfy unescapes these; the table path does the same with the small named
// set plus numeric references so every language agrees.
const ENTITY_RE = /&(?:#(\d{1,7})|#[xX]([0-9A-Fa-f]{1,6})|([A-Za-z]{2,8}));/g;

function entityReplace(m: string, dec?: string, hex?: string): string {
  let code: number;
  if (dec) code = parseInt(dec, 10);
  else if (hex) code = parseInt(hex, 16);
  else
    return Object.prototype.hasOwnProperty.call(HTML_ENTITIES, m)
      ? HTML_ENTITIES[m]
      : m;
  if (code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff)) {
    return String.fromCodePoint(code);
  }
  return m;
}

/**
 * `&amp;` → `&`, `&#960;` → `π`, `&#x3c0;` → `π`; unknown names stay.
 * Decodes to a fixed point (at most three rounds) so `&amp;amp;` → `&`.
 */
export function unescapeHtmlEntities(text: string): string {
  if (!text.includes("&")) return text;
  for (let round = 0; round < 3; round++) {
    const decoded = text.replace(ENTITY_RE, entityReplace);
    if (decoded === text) return text;
    text = decoded;
  }
  return text;
}

const TABLE_KEYS_LONGEST_FIRST: readonly string[] = Object.keys(
  MOJIBAKE_TABLE,
).sort((a, b) => b.length - a.length);
const NON_ASCII_RE = /[^\x00-\x7f]/;
const BAD_RE = /[�ÃÂ]/g;
const REPLACEMENT_RE = /�/g;
const C1_RE = /[\u0080-\u009f]/g;
// With the `u` flag a well-formed pair (one code point) does not match; only
// a lone half does, as in Python where a str never holds paired surrogates.
const LONE_SURROGATE_RE = /[\ud800-\udfff]/gu;
const GARBAGE = "[\\u0080-\\u009f\\u00a0-\\u00ff]";
const ROOT_DIGITS_RE = new RegExp("â" + GARBAGE + "{0,3}(\\d+)", "g");
const ROOT_PAREN_RE = new RegExp("â" + GARBAGE + "{0,3}\\(", "g");
const LETTER_ROOT_RE = new RegExp("([A-Za-z])â" + GARBAGE + "{0,3}(\\d)", "g");
const SLASH_ROOT_RE = new RegExp("/â" + GARBAGE + "{0,3}(\\d)", "g");
const DIGIT_PI_RE = new RegExp("(\\d)" + GARBAGE + "{0,2}Ï", "g");
const LEAD_PI_SLASH_RE = new RegExp(
  "(^|[\\s(,\\[])Ï" + GARBAGE + "{0,2}/",
  "g",
);
const SLASH_OMEGA_RE = /\/Ï(?=[\s,.)\]}]|$)/g;
const OP_PI_RE = /([+\-*×÷=/(])Ï(?=[+\-*×÷=/)\s,]|$)/g;
const LEAD_PI_RE = /(^|[\s(,])Ï(?=[\s),.]|$)/g;

let decoder: TextDecoder | null = null;

function countMatches(re: RegExp, text: string): number {
  re.lastIndex = 0;
  let n = 0;
  while (re.exec(text) !== null) n++;
  return n;
}

/**
 * Text that was UTF-8 bytes read as Latin-1: re-encode as Latin-1 and decode
 * as UTF-8 leniently. A character above U+00FF makes this a no-op (Python's
 * `encode("latin-1")` raises). Kept only when it has fewer bad characters.
 */
function tryFixDoubleEncoding(text: string): string {
  if (!text.includes("Ã") && !text.includes("Â")) return text;
  const bytes = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    if (c > 0xff) return text;
    bytes[i] = c;
  }
  if (decoder === null) decoder = new TextDecoder("utf-8");
  const decoded = decoder.decode(bytes);
  const originalBad = countMatches(BAD_RE, text);
  const decodedBad = countMatches(REPLACEMENT_RE, decoded);
  return decodedBad < originalBad ? decoded : text;
}

function applyTable(text: string): string {
  for (const key of TABLE_KEYS_LONGEST_FIRST) {
    if (text.includes(key)) text = text.split(key).join(MOJIBAKE_TABLE[key]);
  }
  return text;
}

// π, ω and √ present before the context rules run are hidden behind these
// private-use placeholders so the doubled-symbol cleanup never touches them.
const COLLAPSE_PLACEHOLDERS: ReadonlyArray<[string, string]> = [
  ["π", ""],
  ["ω", ""],
  ["√", ""],
];

function applyContextRules(text: string): string {
  for (const [ch, placeholder] of COLLAPSE_PLACEHOLDERS)
    text = text.split(ch).join(placeholder);
  // NBSP is a space, not garbage; C1 controls that survived the table are
  // garbage; a lone surrogate can never be encoded.
  text = text.split(" ").join(" ");
  text = text.replace(C1_RE, "");
  text = text.replace(LONE_SURROGATE_RE, "");
  text = text.replace(ROOT_DIGITS_RE, (_m, d: string) => "√" + d);
  text = text.replace(ROOT_PAREN_RE, () => "√(");
  text = text.replace(
    LETTER_ROOT_RE,
    (_m, l: string, d: string) => l + "√" + d,
  );
  text = text.replace(SLASH_ROOT_RE, (_m, d: string) => "/√" + d);
  text = text.replace(DIGIT_PI_RE, (_m, d: string) => d + "π");
  text = text.replace(LEAD_PI_SLASH_RE, (_m, lead: string) => lead + "π/");
  text = text.replace(SLASH_OMEGA_RE, () => "/ω");
  text = text.split("Ï/Ï").join("π/ω");
  text = text.replace(OP_PI_RE, (_m, op: string) => op + "π");
  text = text.replace(LEAD_PI_RE, (_m, lead: string) => lead + "π");
  // Collapse a doubled π / ω / √ only when a context rule above produced
  // one of the pair: `Ï€Ï` once became `ππ`. A genuine repeated letter
  // (`ππ`, `ωω`, `√√2`, or `Ï€Ï€` which the table maps to `ππ`) is kept:
  // the characters present before the rules are protected by placeholders.
  for (const [ch, placeholder] of COLLAPSE_PLACEHOLDERS) {
    text = text.split(ch + ch).join(ch);
    text = text.split(placeholder + ch).join(placeholder);
    text = text.split(ch + placeholder).join(placeholder);
    text = text.split(placeholder).join(ch);
  }
  return text;
}

/** Deterministic mojibake repair, identical in every language. */
export function fixMojibakeTable<T>(text: T): T;
export function fixMojibakeTable(text: unknown): unknown {
  if (typeof text !== "string" || !text) return text;
  let out = unescapeHtmlEntities(text);
  if (!NON_ASCII_RE.test(out)) return out;
  out = tryFixDoubleEncoding(out);
  out = applyTable(out);
  out = applyContextRules(out);
  return out;
}
