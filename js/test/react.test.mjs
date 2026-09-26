// The React adapter rendered with react-dom/server.

import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { MathText, TextPart, renderMath } from "../dist/react.js";

const render = (props) => renderToStaticMarkup(createElement(MathText, props));

test("a formula renders through KaTeX", () => {
  const html = render({ text: "Energy is $E = mc^2$." });
  assert.ok(html.startsWith("<span>"));
  assert.ok(html.includes('class="katex"'));
  assert.ok(html.includes("Energy is "));
  assert.ok(!html.includes("katex-error"));
});

test("currency stays text", () => {
  const html = render({ text: "Cost \\$60 and $60 more, then $x^2$" });
  assert.ok(html.includes("Cost $60 and $60 more, then "));
  assert.strictEqual(html.split('class="katex"').length - 1, 1);
});

test("display math, mhchem and legacy delimiters", () => {
  const html = render({
    text: "\\(\\ce{H2O}\\) and $$\\frac{a}{b}$$",
    as: "div",
    className: "q",
  });
  assert.ok(html.startsWith('<div class="q">'));
  assert.ok(html.includes("katex-display"));
  assert.strictEqual(html.split('class="katex"').length - 1, 2);
  assert.ok(!html.includes("katex-error"));
});

test("bold prose and a repaired control character", () => {
  const html = render({ text: "The **climax** is $\x0crac{1}{2}$" });
  assert.ok(html.includes("<strong>climax</strong>"));
  assert.ok(html.includes("mfrac"));
  assert.ok(!html.includes("\f"));
});

test("fix mode (default) renders Unicode chemistry and bare symbols through KaTeX", () => {
  for (const text of ["Water is H₂O.", "Rust needs Fe³⁺ ions", "angle θ"]) {
    const html = render({ text });
    assert.ok(html.includes('class="katex"'), text);
    assert.ok(!html.includes("katex-error"), text);
  }
  assert.ok(render({ text: "Water is H₂O." }).includes("Water is "));
  assert.ok(render({ text: "H₂O", mode: "fix" }).includes('class="katex"'));
});

test("normalize mode keeps chemistry and bare symbols as text", () => {
  for (const text of ["Water is H₂O.", "Fe³⁺", "angle θ"]) {
    assert.ok(
      !render({ text, mode: "normalize" }).includes('class="katex"'),
      text,
    );
  }
  assert.ok(
    render({ text: "$x^2$", mode: "normalize" }).includes('class="katex"'),
  );
});

test("the deprecated canonical prop is an alias for the mode", () => {
  assert.ok(
    render({ text: "angle θ", canonical: true }).includes('class="katex"'),
  );
  assert.ok(
    !render({ text: "angle θ", canonical: false }).includes('class="katex"'),
  );
  assert.ok(
    render({ text: "angle θ", canonical: false, mode: "fix" }).includes(
      'class="katex"',
    ),
  );
});

test("a formula KaTeX rejects shows its grey source, not red error text", () => {
  const html = render({ text: "Bad $\\frac{1}$ here" });
  assert.ok(!html.includes("katex-error"));
  assert.ok(html.includes('<code class="pt-math-source">'));
  assert.ok(html.includes("\\frac{1}"), "the source is still visible");
});

test("a formula KaTeX throws on shows its source", () => {
  // Nesting past the JS stack is not a ParseError either; it also lands in
  // the catch.
  const deep = "{".repeat(50000) + "x" + "}".repeat(50000);
  assert.strictEqual(renderMath(deep, false), null);
  const html = render({ text: `see $${deep}$ end` });
  assert.ok(html.includes('<code class="pt-math-source">'));
  assert.ok(html.includes("see "));
});

test("non-string text is tolerated", () => {
  assert.strictEqual(render({ text: null }), "<span></span>");
  assert.strictEqual(render({ text: 42 }), "<span>42</span>");
});

test("TextPart keeps everything but **bold** as written", () => {
  const html = renderToStaticMarkup(
    createElement(TextPart, { text: "a *b* **c** $d" }),
  );
  assert.strictEqual(html, "a *b* <strong>c</strong> $d");
});
