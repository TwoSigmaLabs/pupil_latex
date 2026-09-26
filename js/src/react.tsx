/**
 * React adapter: `<MathText text={…} />`.
 *
 * `fix` (or `normalize` only, per `mode`) → `segment` → prose parts
 * with `**bold**` support (worksheet.ai's `TextPart`), maths parts through
 * KaTeX (`throwOnError: true` inside a try, `strict: "ignore"`,
 * `trust: false`) with mhchem loaded for `\ce{}`. A span KaTeX cannot
 * render is shown as its source in `<code class="pt-math-source">` (grey,
 * readable), never as nothing and never as KaTeX's red error text.
 */

import katex from "katex";
import "katex/contrib/mhchem";
import { createElement, Fragment, useMemo, type ReactNode } from "react";

import { fix } from "./fix.js";
import { normalize } from "./normalize.js";
import { segment, type Segment } from "./segment.js";

export type MathTextMode = "fix" | "normalize";

export interface MathTextProps {
  /** The stored text, as it comes from the API. */
  text: unknown;
  /**
   * `"fix"` (default): `fix` = normalize → canonicalize → chemistry.
   * `"normalize"`: the content-preserving steps only.
   */
  mode?: MathTextMode;
  /** @deprecated alias for `mode="fix"` (`false` selects `"normalize"`); ignored when `mode` is given. */
  canonical?: boolean;
  className?: string;
  /** Wrapper element; defaults to `span`. */
  as?: keyof JSX.IntrinsicElements;
}

// **bold** marks keywords ("the **climax** of the story").
// Content starts and ends with a non-space (no lookbehind: old Safari).
const BOLD_RE = /\*\*(?=\S)(.*?\S)\*\*/g;

/** Prose with `**bold**` rendered as `<strong>`; everything else as written. */
export function TextPart({ text }: { text: string }): ReactNode {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(BOLD_RE)) {
    const index = m.index ?? 0;
    if (index > last) out.push(text.slice(last, index));
    out.push(createElement("strong", { key: index }, m[1]));
    last = index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return createElement(Fragment, null, ...out);
}

/**
 * KaTeX HTML for one maths segment, or null when KaTeX cannot render it.
 * `throwOnError: true` so a parse error reaches the catch: with `false`
 * KaTeX never throws and paints the source red (`katex-error`) instead.
 */
export function renderMath(value: string, display: boolean): string | null {
  try {
    return katex.renderToString(value, {
      displayMode: display,
      throwOnError: true,
      strict: "ignore",
      trust: false,
      output: "html",
    });
  } catch {
    return null;
  }
}

function renderSegment(seg: Segment, key: number): ReactNode {
  if (seg.kind === "text")
    return createElement(TextPart, { key, text: seg.value });
  const html = renderMath(seg.value, seg.display);
  if (html === null)
    return createElement("code", { key, className: "pt-math-source" }, seg.raw);
  return createElement(seg.display ? "div" : "span", {
    key,
    className: seg.display ? "pt-math pt-math-display" : "pt-math",
    // KaTeX output from question-bank text; trust is off, so \href and
    // \includegraphics are not honoured.
    dangerouslySetInnerHTML: { __html: html },
  });
}

/**
 * Text as it should read: LaTeX rendered as maths, `**bold**` as bold. A
 * formula KaTeX cannot parse shows its source, so a typo in one question
 * never blanks the page.
 */
export function MathText({
  text,
  mode,
  canonical,
  className,
  as = "span",
}: MathTextProps): ReactNode {
  const resolved: MathTextMode =
    mode ?? (canonical === undefined ? "fix" : canonical ? "fix" : "normalize");
  const raw: string =
    typeof text === "string" ? text : text == null ? "" : String(text);
  // `fix` + `segment` are pure; recompute only when the input changes.
  const segments = useMemo(
    () => segment(resolved === "fix" ? fix(raw) : normalize(raw)),
    [raw, resolved],
  );
  const children = segments.map(renderSegment);
  return createElement(as, { className }, ...children);
}

export default MathText;
