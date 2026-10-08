/**
 * `segment`: the one tokenizer every renderer uses. Port of
 * python/pupiltree_latex/segment.py.
 *
 * Splits a string into prose and math segments. Escape-aware (`\$` is a
 * literal dollar, `\\$x$` opens math), brace-aware (the KaTeX auto-render
 * walk: a backslash skips the next character, `{`/`}` nest), and
 * currency-aware for inline `$…$` (pandoc's rule: content must not start
 * with whitespace or span a line, the closer must not be followed by a
 * digit). Unlike pandoc, an inline span never runs past a rejected closer —
 * the first candidate closer decides — so `$60 and $x^2$` keeps `$60`
 * literal and renders `$x^2$`.
 */

import { charAt, isDigit, isSpace, pyStrip } from "./chars.js";

export interface Segment {
  kind: "text" | "math";
  display: boolean;
  value: string;
  raw: string;
}

/** True when an odd number of backslashes immediately precedes `i`. */
function escaped(s: string, i: number): boolean {
  let count = 0;
  let p = i - 1;
  while (p >= 0 && s[p] === "\\") {
    count++;
    p--;
  }
  return count % 2 === 1;
}

/**
 * KaTeX auto-render's findEndOfMath: index of the closing delimiter at brace
 * depth ≤ 0, or -1.
 */
function findEnd(delim: string, s: string, start: number): number {
  let idx = start;
  let depth = 0;
  const n = s.length;
  while (idx < n) {
    if (depth <= 0 && s.startsWith(delim, idx)) return idx;
    const ch = s[idx];
    if (ch === "\\") idx++;
    else if (ch === "{") depth++;
    else if (ch === "}") depth--;
    idx++;
  }
  return -1;
}

/**
 * Split `text` into `{kind, display, value, raw}` segments.
 *
 * Delimiter priority at each position: `$$`, `\[`, `$`, `\(`. Text `value`
 * has `\$` unescaped to `$`; `raw` is the exact source slice. Math `value`
 * is the inner content (`\(…\)` trimmed). Non-strings and the empty string
 * yield `[]`.
 */
export function segment(text: unknown): Segment[] {
  if (typeof text !== "string" || !text) return [];
  const s = text;
  const n = s.length;
  const out: Segment[] = [];
  let textRaw: string[] = [];
  let textVal: string[] = [];

  const flush = (): void => {
    if (textRaw.length) {
      out.push({
        kind: "text",
        display: false,
        value: textVal.join(""),
        raw: textRaw.join(""),
      });
      textRaw = [];
      textVal = [];
    }
  };

  const pushMath = (raw: string, value: string, display: boolean): void => {
    flush();
    out.push({ kind: "math", display, value, raw });
  };

  let i = 0;
  while (i < n) {
    const ch = s[i];
    if (ch === "\\") {
      if (escaped(s, i)) {
        textRaw.push(ch);
        textVal.push(ch);
        i++;
        continue;
      }
      const nxt = i + 1 < n ? s[i + 1] : "";
      if (nxt === "$") {
        textRaw.push("\\$");
        textVal.push("$");
        i += 2;
        continue;
      }
      if (nxt === "[") {
        const end = findEnd("\\]", s, i + 2);
        if (end !== -1) {
          pushMath(s.slice(i, end + 2), s.slice(i + 2, end), true);
          i = end + 2;
          continue;
        }
      }
      if (nxt === "(") {
        const end = findEnd("\\)", s, i + 2);
        if (end !== -1) {
          pushMath(s.slice(i, end + 2), pyStrip(s.slice(i + 2, end)), false);
          i = end + 2;
          continue;
        }
      }
      textRaw.push(ch);
      textVal.push(ch);
      i++;
      continue;
    }
    if (ch === "$") {
      if (s.startsWith("$$", i)) {
        const end = findEnd("$$", s, i + 2);
        if (end > i + 2) {
          pushMath(s.slice(i, end + 2), s.slice(i + 2, end), true);
          i = end + 2;
          continue;
        }
      } else if (i + 1 < n && !isSpace(s[i + 1])) {
        const end = findEnd("$", s, i + 1);
        if (end !== -1) {
          const content = s.slice(i + 1, end);
          const closerOk =
            !isSpace(s[end - 1]) &&
            (end + 1 >= n || !isDigit(charAt(s, end + 1)));
          if (content && !content.includes("\n") && closerOk) {
            pushMath(s.slice(i, end + 1), content, false);
            i = end + 1;
            continue;
          }
        }
      }
      textRaw.push("$");
      textVal.push("$");
      i++;
      continue;
    }
    textRaw.push(ch);
    textVal.push(ch);
    i++;
  }
  flush();
  return out;
}

const COMMAND_RE = /\\[A-Za-z]/;

/** True when the text has a math segment or a backslash command. */
export function containsMath(text: unknown): boolean {
  if (typeof text !== "string" || !text) return false;
  if (COMMAND_RE.test(text)) return true;
  return segment(text).some((seg) => seg.kind === "math");
}

// Anything that markdown or LaTeX would interpret. Mirrors script_editor's
// `ScriptEditorTex._markdownSyntaxRx` (the plain-prose fast path).
const NOT_PLAIN_RE = new RegExp(
  "[\\\\$*~`|\\[\\]<>#\\r⸻【]" + // markup characters, ⸻, 【
    "|\\n\\n" + // blank line
    "|--" + // rule / em-dash marker
    "|(?:^|\\n)[ \\t]+\\S" + // leading indentation
    "|(?:^|\\n)(?:[-*+] |\\d+[.)] )" + // list marker
    "|\\([xX ]\\) ", // gpt_markdown radio button `(x) ` / `( ) ` (tag v140-b10)
);

/** Renderer fast path: true when the text can be shown as plain text. */
export function isPlainProse(text: unknown): boolean {
  if (typeof text !== "string") return false;
  return !NOT_PLAIN_RE.test(text);
}
