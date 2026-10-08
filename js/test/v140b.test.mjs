// 1.4.0 Group B behaviour that the corpus cannot express (deep walks,
// positions, options). Translation of python/tests/test_v140_b.py.

import assert from "node:assert/strict";
import { test } from "node:test";

import * as L from "../dist/index.js";

const NARRATIVE = ["story_script", "transcript", "script@transcript"];

test("fixDeep: narrative keys get repair only", () => {
  const doc = {
    question: "Area = πr²",
    story_script: "Then π \x0crac{1}{2} and H₂O",
    podcast: { transcript: "x² is πr", script: "x² here" },
    lesson: { script: "x² here" },
    _id: "q_1",
  };
  const out = L.fixDeep(doc, { narrativeKeys: NARRATIVE });
  assert.strictEqual(out.question, "Area = $\\pi r^{2}$");
  assert.strictEqual(out.story_script, "Then π \\frac{1}{2} and H₂O");
  assert.strictEqual(out.podcast.transcript, "x² is πr");
  assert.strictEqual(out.podcast.script, "x² here");
  assert.strictEqual(out.lesson.script, "$x^{2}$ here");
  assert.strictEqual(out._id, "q_1");
});

test("fixDeep without narrative keys is unchanged behaviour", () => {
  const doc = { transcript: "x²", items: ["π", { story_script: "π" }] };
  assert.deepStrictEqual(L.fixDeep(doc), {
    transcript: "$x^{2}$",
    items: ["$\\pi$", { story_script: "$\\pi$" }],
  });
});

test("fixDeep: narrative lists and nested values", () => {
  const doc = { story_sections: [{ text: "π \x0crac{1}{2}" }, "x²"] };
  assert.deepStrictEqual(
    L.fixDeep(doc, { narrativeKeys: ["story_sections"] }),
    {
      story_sections: [{ text: "π \\frac{1}{2}" }, "x²"],
    },
  );
});

test("canonicalizeDeep: narrative keys", () => {
  const doc = { q: "π", transcript: "π", script: "π" };
  assert.deepStrictEqual(
    L.canonicalizeDeep(doc, { narrativeKeys: NARRATIVE }),
    {
      q: "$\\pi$",
      transcript: "π",
      script: "π",
    },
  );
});

test("currencySpans: positions", () => {
  const text = "Rs $5 and \\$10.50, ₹ 45,00,000 and $x^2$";
  const spans = L.currencySpans(text);
  assert.deepStrictEqual(
    spans.map((s) => s.text),
    ["$5", "\\$10.50", "₹ 45,00,000"],
  );
  for (const s of spans) assert.strictEqual(text.slice(s.start, s.end), s.text);
  assert.deepStrictEqual(L.currencySpans(null), []);
  assert.deepStrictEqual(L.currencySpans(""), []);
});

test("needsFix: non-strings and the chemistry option", () => {
  assert.strictEqual(L.needsFix(null), false);
  assert.strictEqual(L.needsFix(5), false);
  assert.strictEqual(L.needsFix("\\ce{H2O}"), true);
  assert.strictEqual(L.needsFix("\\ce{H2O}", { chemistry: false }), false);
});

test("normalizeOptionText: non-strings and idempotent", () => {
  assert.strictEqual(L.normalizeOptionText(null), null);
  assert.strictEqual(L.normalizeOptionText(""), "");
  for (const text of [
    "$\\text{H_{2}O}$",
    "$50 \\text{ %}$",
    "\\text{rises} when $x > 0$",
  ]) {
    const once = L.normalizeOptionText(text);
    assert.strictEqual(L.normalizeOptionText(once), once);
  }
});

test("normalize: code spans are off by default", () => {
  assert.strictEqual(L.normalize("`x^2`"), "`x^2`");
  assert.strictEqual(L.normalize("`x^2`", { codeSpansAsMath: true }), "$x^2$");
});

test("loadsModelJson: lenient flag", () => {
  assert.deepStrictEqual(L.loadsModelJson('{"a": "\\q"}'), { a: "\\q" });
  assert.deepStrictEqual(L.loadsModelJson('{"a": "\\q"}', { lenient: true }), {
    a: "\\q",
  });
  assert.throws(
    () => L.loadsModelJson('{"a": "\\q"}', { lenient: false }),
    SyntaxError,
  );
  assert.throws(
    () => L.loadsModelJson('{"a": "x\ny"}', { lenient: false }),
    SyntaxError,
  );
});

test("repair: currency-aware span", () => {
  const text = "costs $5.\nangle ABC costs $10";
  assert.strictEqual(L.repair(text, true), text);
  assert.strictEqual(L.repair(text, false), text);
});

test("lost_escape is not an error kind", () => {
  assert.ok(L.ALL_KINDS.includes("lost_escape"));
  assert.strictEqual(L.isError(["lost_escape"]), false);
  assert.strictEqual(L.isError(L.auditKinds("a\x7fb")), true);
});

test("fix is idempotent on the new repairs", () => {
  for (const text of [
    "$x}$",
    "${{x}}$ and $\\fre{a}{b}$",
    "What is $x + 1",
    "\\$1.56 \\text{ m}$",
    "$\\AA$ and \\text{\\AA}",
    "costs $5.\nangle ABC costs $10",
  ]) {
    const once = L.fix(text);
    assert.strictEqual(L.fix(once), once, text);
  }
});
