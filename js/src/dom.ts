/**
 * Vanilla DOM adapter: `typesetMath(root)` on top of KaTeX auto-render.
 *
 * Port of the Fillers pipeline (period_content_renderer.js) on the shared
 * functions: every text node under `root` goes through `fix` (or `normalize`
 * only, per `options.mode`; both include the lossless `repair`, which
 * replaces Fillers' lossy control-character strip), `\$`
 * outside maths is masked with a private-use sentinel so auto-render's
 * unguarded left-delimiter scan cannot open maths at a currency dollar
 * (Fillers #273), auto-render runs with the four delimiter pairs, the
 * sentinels come back as `<span class="pt-esc-dollar">$</span>` (an element
 * boundary auto-render never scans across, so a second pass is idempotent),
 * and `auditRawMath` reports what is still raw.
 */

import { fix } from "./fix.js";
import { normalize } from "./normalize.js";

export interface MathDelimiter {
  left: string;
  right: string;
  display: boolean;
}

export interface AutoRenderOptions {
  delimiters: MathDelimiter[];
  ignoredClasses: string[];
  throwOnError: boolean;
}

export type RenderMathInElement = (
  root: Element,
  options: AutoRenderOptions,
) => void;

export type TypesetMode = "fix" | "normalize";

export interface TypesetOptions {
  /** Text-node preparation: `"fix"` (default) or `"normalize"` only. */
  mode?: TypesetMode;
  /** Delimiter pairs for auto-render; defaults to `MATH_DELIMITERS`. */
  delimiters?: MathDelimiter[];
  /** Extra classes to leave alone (in addition to `katex` and `pt-esc-dollar`). */
  ignoredClasses?: string[];
  /** Where to find auto-render; defaults to `window.renderMathInElement`. */
  katex?: { renderMathInElement: RenderMathInElement };
}

/** The four delimiter pairs every Pupiltree surface accepts, `$$` before `$`. */
export const MATH_DELIMITERS: readonly MathDelimiter[] = [
  { left: "$$", right: "$$", display: true },
  { left: "\\[", right: "\\]", display: true },
  { left: "$", right: "$", display: false },
  { left: "\\(", right: "\\)", display: false },
];

/** Private-use character that stands in for `\$` while auto-render runs. */
export const ESC_DOLLAR_SENTINEL = "";
/** Class of the `<span>` that carries a restored literal `$`. */
export const ESC_DOLLAR_CLASS = "pt-esc-dollar";

const SKIP_TAGS: ReadonlySet<string> = new Set([
  "SCRIPT",
  "STYLE",
  "TEXTAREA",
  "PRE",
  "CODE",
  "CANVAS",
  "IMG",
  "VIDEO",
  "IFRAME",
]);
const TEXT_NODE = 3;
const ELEMENT_NODE = 1;

// Same walk as auto-render's findEndOfMath: a backslash skips the next
// character, braces nest, the right delimiter closes at brace depth ≤ 0.
function findEndOfMath(
  delimiter: string,
  text: string,
  startIndex: number,
): number {
  let index = startIndex;
  let braceLevel = 0;
  while (index < text.length) {
    const ch = text[index];
    if (braceLevel <= 0 && text.startsWith(delimiter, index)) return index;
    else if (ch === "\\") index++;
    else if (ch === "{") braceLevel++;
    else if (ch === "}") braceLevel--;
    index++;
  }
  return -1;
}

/**
 * Replace every `\$` outside a maths span with `ESC_DOLLAR_SENTINEL`,
 * leaving maths spans (and any `\$` inside them, which is a KaTeX command)
 * untouched. Mirrors auto-render's own split so both agree on where maths
 * starts. Pure.
 */
export function maskEscapedDollars(
  text: string,
  delimiters: readonly MathDelimiter[] = MATH_DELIMITERS,
): string {
  const s = String(text ?? "");
  if (!s.includes("\\$")) return s;
  let out = "";
  let i = 0;
  while (i < s.length) {
    const d = delimiters.find((x) => s.startsWith(x.left, i));
    if (d) {
      const end = findEndOfMath(d.right, s, i + d.left.length);
      if (end === -1) {
        out += s.slice(i); // unterminated: auto-render leaves the rest as text
        break;
      }
      const stop = end + d.right.length;
      out += s.slice(i, stop);
      i = stop;
      continue;
    }
    if (s[i] === "\\") {
      if (s[i + 1] === "$") {
        out += ESC_DOLLAR_SENTINEL;
        i += 2;
        continue;
      }
      out += s.slice(i, i + 2); // `\x` — keep the pair, so `\\$…$` still opens maths
      i += 2;
      continue;
    }
    out += s[i];
    i++;
  }
  return out;
}

function skipsElement(el: Element, ignored: ReadonlySet<string>): boolean {
  if (SKIP_TAGS.has(el.tagName)) return true;
  const classes = el.classList;
  if (!classes) return false;
  for (const cls of ignored) if (classes.contains(cls)) return true;
  return false;
}

function walkTextNodes(
  root: Node,
  ignored: ReadonlySet<string>,
  visit: (node: Text) => void,
): void {
  const walk = (node: Node): void => {
    if (node.nodeType === TEXT_NODE) {
      visit(node as Text);
      return;
    }
    if (node.nodeType !== ELEMENT_NODE) return;
    if (skipsElement(node as Element, ignored)) return;
    for (const child of Array.from(node.childNodes)) walk(child);
  };
  walk(root);
}

// Prepare the text nodes under `root` for auto-render: `fix` (or `normalize`
// only) and mask escaped dollars. Skips anything KaTeX already produced and the restored `$` spans,
// so a second pass is idempotent.
function prepareTextForMath(
  root: Element,
  ignored: ReadonlySet<string>,
  delimiters: readonly MathDelimiter[],
  prepare: (text: string) => string,
): void {
  walkTextNodes(root, ignored, (node) => {
    const v = node.nodeValue;
    if (!v) return;
    const next = maskEscapedDollars(prepare(v), delimiters);
    if (next !== v) node.nodeValue = next;
  });
}

// Put each sentinel back as a literal `$` in its own element.
function restoreEscapedDollars(
  root: Element,
  ignored: ReadonlySet<string>,
): void {
  const doc = root.ownerDocument;
  const pending: Text[] = [];
  walkTextNodes(root, ignored, (node) => {
    if ((node.nodeValue ?? "").includes(ESC_DOLLAR_SENTINEL) && node.parentNode)
      pending.push(node);
  });
  for (const node of pending) {
    const frag = doc.createDocumentFragment();
    (node.nodeValue ?? "").split(ESC_DOLLAR_SENTINEL).forEach((part, idx) => {
      if (idx > 0) {
        const dollar = doc.createElement("span");
        dollar.className = ESC_DOLLAR_CLASS;
        dollar.textContent = "$";
        frag.appendChild(dollar);
      }
      if (part) frag.appendChild(doc.createTextNode(part));
    });
    node.parentNode!.replaceChild(frag, node);
  }
}

// A `$…$` span that still holds a command, or a `\(` / `\[` opener, in a
// text node after auto-render: maths the renderer did not typeset.
const RAW_MATH_RE = /\$[^$\n]*\\[a-zA-Z]+[^$\n]*\$|\\\(|\\\[/;

/**
 * Snippets (trimmed, ≤ 80 chars) of every text node under `root` that still
 * carries raw maths after typesetting. KaTeX output and the skipped tags are
 * not inspected.
 */
export function auditRawMath(
  root: Element | null | undefined,
  ignoredClasses: readonly string[] = [],
): string[] {
  if (!root) return [];
  const ignored = new Set<string>(["katex", ...ignoredClasses]);
  const hits: string[] = [];
  walkTextNodes(root, ignored, (node) => {
    const v = node.nodeValue ?? "";
    if (RAW_MATH_RE.test(v)) hits.push(v.trim().slice(0, 80));
  });
  return hits;
}

function resolveRenderer(options: TypesetOptions): RenderMathInElement {
  const fromOptions = options.katex?.renderMathInElement;
  if (typeof fromOptions === "function") return fromOptions;
  const g = globalThis as { renderMathInElement?: unknown };
  if (typeof g.renderMathInElement === "function")
    return g.renderMathInElement as RenderMathInElement;
  throw new Error(
    "typesetMath: KaTeX auto-render not found; load katex/dist/contrib/auto-render.js (or katex/contrib/auto-render) or pass options.katex.renderMathInElement",
  );
}

/**
 * Typeset every maths span under `root` with KaTeX auto-render, after the
 * shared `fix` (or `normalize`) and with currency dollars protected. Safe to call
 * repeatedly on the same root. Returns the raw-maths snippets that are still
 * left (also reported once with `console.warn`).
 */
export function typesetMath(
  root: Element | null | undefined,
  options: TypesetOptions = {},
): string[] {
  if (!root) return [];
  const renderMathInElement = resolveRenderer(options);
  const delimiters = options.delimiters ?? [...MATH_DELIMITERS];
  const extraIgnored = options.ignoredClasses ?? [];
  const ignored = new Set<string>(["katex", ESC_DOLLAR_CLASS, ...extraIgnored]);

  const prepare = (options.mode ?? "fix") === "fix" ? fix : normalize;
  prepareTextForMath(root, ignored, delimiters, prepare);
  try {
    renderMathInElement(root, {
      delimiters: [...delimiters],
      // ESC_DOLLAR_CLASS here is defence in depth only: auto-render never
      // scans across an element boundary, so a lone `$` in its own span
      // cannot pair with anything even when scanned.
      ignoredClasses: ["katex", ESC_DOLLAR_CLASS, ...extraIgnored],
      throwOnError: false,
    });
  } catch (e) {
    console.warn("[pupiltree-latex] KaTeX render error:", e);
  }
  restoreEscapedDollars(root, ignored);
  const hits = auditRawMath(root, extraIgnored);
  if (hits.length) {
    console.warn(
      "[pupiltree-latex] math left raw under",
      root.id || root.className,
      hits,
    );
  }
  return hits;
}
