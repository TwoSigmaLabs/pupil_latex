// Behavioural tests the JSON corpus cannot express: deep walkers, non-string
// passthrough, fast paths, audit paths, mojibake, JSON transport.
// Translation of python/tests/test_api.py.

import assert from "node:assert/strict";
import { test } from "node:test";

import * as L from "../dist/index.js";
import { DETECTORS } from "../dist/audit.js";

test("string functions pass non-strings through", () => {
  const values = [null, undefined, 5, 2.5, true, { a: 1 }, ["x"]];
  for (const fn of [L.repair, L.normalize, L.canonicalize, L.toPlain]) {
    for (const value of values) assert.strictEqual(fn(value), value);
  }
});

test("segment and audit on non-strings", () => {
  assert.deepStrictEqual(L.segment(null), []);
  assert.deepStrictEqual(L.segment(undefined), []);
  assert.deepStrictEqual(L.segment(""), []);
  assert.deepStrictEqual(L.segment(7), []);
  assert.deepStrictEqual(L.audit(null), []);
  assert.deepStrictEqual(L.audit(7), []);
  assert.deepStrictEqual(L.auditKinds({}), []);
  assert.strictEqual(L.containsMath(null), false);
});

test("repairDeep touches every string and nothing else", () => {
  const when = new Date(Date.UTC(2026, 8, 25, 10, 0));
  const doc = {
    question: "Area \x0crac{1}{2}",
    options: ["\x08eta decay", { text: "\times" }], // TAB + "imes" is a decoded \times
    url: "https://x/\x0crac.png", // repair is safe even on URLs
    n: 3,
    when,
  };
  const out = L.repairDeep(doc);
  assert.strictEqual(out.question, "Area \\frac{1}{2}");
  assert.strictEqual(out.options[0], "\\beta decay");
  assert.strictEqual(out.options[1].text, "\\times");
  assert.strictEqual(out.url, "https://x/\\frac.png");
  assert.strictEqual(out.n, 3);
  assert.strictEqual(out.when, when);
  assert.strictEqual(
    doc.question,
    "Area \x0crac{1}{2}",
    "input is not mutated",
  );
});

test("canonicalizeDeep skips non-content keys and URLs", () => {
  const doc = {
    _id: "ahs_69e74f5e84fd",
    audioUrl: "https://s/ahs_69e74f5e84fd_vocab_20260425.wav",
    className: "10_A",
    status: "in_progress",
    question: "Water is H_{2}O at 3 \u00d7 10^8",
    options: [{ id: "opt_a_1", text: "\u03c0" }],
    createdAt: new Date(Date.UTC(2026, 8, 25, 10, 0)),
    nested: { description: "see https://a/b_c.png here" },
  };
  const out = L.canonicalizeDeep(doc);
  assert.strictEqual(out._id, doc._id);
  assert.strictEqual(out.audioUrl, doc.audioUrl);
  assert.strictEqual(out.className, "10_A");
  assert.strictEqual(out.status, "in_progress");
  assert.strictEqual(out.question, "Water is $H_{2}O$ at 3 $\\times$ $10^8$");
  assert.strictEqual(out.options[0].id, "opt_a_1");
  assert.strictEqual(out.options[0].text, "$\\pi$");
  assert.strictEqual(out.createdAt, "2026-09-25T10:00:00.000Z");
  assert.strictEqual(out.nested.description, "see https://a/b_c.png here");
});

test("canonicalizeDeep leaves class instances and scalars alone", () => {
  class ObjectId {
    toString() {
      return "69e74f5e84fd";
    }
  }
  const oid = new ObjectId();
  const out = L.canonicalizeDeep({
    ref: oid,
    n: 1,
    flag: false,
    nothing: null,
    list: [oid],
  });
  assert.strictEqual(out.ref, oid);
  assert.strictEqual(out.list[0], oid);
  assert.deepStrictEqual(
    { n: out.n, flag: out.flag, nothing: out.nothing },
    { n: 1, flag: false, nothing: null },
  );
});

test("canonicalize is idempotent on typical content", () => {
  const samples = [
    "The price is $50 and the ratio is 1/\\sqrt{2}",
    "Cost $60 and $x^2$",
    "\\left[ $\\frac12$ \\right] $\\frac{q^2}{a^2}$",
    "H_{2}O and MCQ_SINGLE and 3^{\\circ}C",
    "\u221a2 and \u0127\u03c9 and \u03c0 and 3 \u00d7 10^8",
    "{{IMAGE:59_1}} then \\frac{a}{b}",
  ];
  for (const s of samples) {
    const once = L.canonicalize(s);
    assert.strictEqual(L.canonicalize(once), once, s);
  }
});

test("normalize is idempotent on typical content", () => {
  const samples = [
    "\\(\\theta\\) costs $5000 and $\\frac14$ then \\nNext",
    "Cost \\$60 and $x^2$ end \\( orphan",
    "\u00cf\u20ac is \u00c3\u2014 fun with \u00e2\u02c6\u0161 2",
    "$5-$10 and $2x + 3$",
  ];
  for (const s of samples) {
    const once = L.normalize(s);
    assert.strictEqual(L.normalize(once), once, s);
  }
});

test("normalize never wraps or converts", () => {
  assert.strictEqual(
    L.normalize("\u221a2 and \u03c0 and \\frac{1}{2} and H_{2}O"),
    "\u221a2 and \u03c0 and \\frac{1}{2} and H_{2}O",
  );
  assert.strictEqual(
    L.normalize("https://a/b_c.png {{IMAGE:59_1}}"),
    "https://a/b_c.png {{IMAGE:59_1}}",
  );
});

test("step order: theta inside paren delimiters", () => {
  // B5: decoding prose escapes before normalising delimiters turned
  // `\(\theta\)` into TAB + "heta" (script_editor #420, tutor #383).
  assert.strictEqual(
    L.normalize("\\(\\theta\\) and \\(\\times 2\\)"),
    "$\\theta$ and $\\times 2$",
  );
});

test("repair fast path returns the same string instance", () => {
  const s = "no control characters here $x^2$";
  assert.strictEqual(L.repair(s), s);
  assert.strictEqual(L.repair(""), "");
});

test("auditDeep paths and skips", () => {
  const doc = {
    question: "Area \x0crac{1}{2}",
    raw_response: "\\(ignored\\)",
    audio_url: "https://x/\\(y\\).wav",
    options: [{ text: "$x^10$" }, { text: "fine" }],
    meta: JSON.stringify({ explanation: "\\(json leaf\\)" }),
  };
  const found = L.auditDeep(doc);
  const paths = Object.fromEntries(found.map(([p, f]) => [p, f.kind]));
  assert.strictEqual(paths["question"], "control_char");
  assert.strictEqual(paths["options[0].text"], "script_missing_braces");
  assert.strictEqual(paths["meta(json).explanation"], "legacy_delimiter");
  assert.ok(
    !Object.keys(paths).some(
      (p) => p.startsWith("raw_response") || p.startsWith("audio_url"),
    ),
  );
});

test("audit snippet makes control chars visible", () => {
  const findings = L.audit("Area \x0crac{1}{2}").filter(
    (x) => x.kind === "control_char",
  );
  assert.strictEqual(findings.length, 1);
  assert.ok(findings[0].snippet.includes("<0x0C>"));
  assert.strictEqual(L.isError(["control_char"]), true);
  assert.strictEqual(L.isError(["mojibake"]), false);
  assert.deepStrictEqual(L.countByKind(L.audit("\\(a\\) \\[b\\]")), {
    legacy_delimiter: 4,
  });
});

test("audit findings carry kind, position and snippet, sorted", () => {
  const findings = L.audit("\\[b\\] and \\(a\\)");
  assert.deepStrictEqual(
    findings.map((f) => f.position),
    [0, 3, 10, 13],
  );
  for (const f of findings) {
    assert.strictEqual(f.kind, "legacy_delimiter");
    assert.strictEqual(typeof f.snippet, "string");
  }
});

test("audit unsupported command inside math only", () => {
  assert.deepStrictEqual(L.auditKinds("$\\frac{1}{2}$"), []);
  assert.deepStrictEqual(L.auditKinds("$\\ce{H2O}$"), []);
  assert.deepStrictEqual(L.auditKinds("$\\notacommand{x}$"), [
    "unsupported_command",
  ]);
  assert.deepStrictEqual(L.auditKinds("prose \\notacommand{x}"), []);
  assert.deepStrictEqual(L.auditKinds("$\\mathscr{L}$"), [
    "unsupported_command",
  ]);
  assert.deepStrictEqual(L.auditKinds("\\mathfrak{g}"), [
    "unsupported_command",
  ]);
});

test("isPlainProse fast path", () => {
  assert.strictEqual(L.isPlainProse("Water boils at 100 degrees."), true);
  assert.strictEqual(L.isPlainProse("Water is $H_2O$"), false);
  assert.strictEqual(L.isPlainProse("Use \\frac here"), false);
  assert.strictEqual(L.isPlainProse("**bold**"), false);
  assert.strictEqual(L.isPlainProse("- item"), false);
  assert.strictEqual(L.isPlainProse("a\n\nb"), false);
  assert.strictEqual(L.isPlainProse(null), false);
});

test("containsMath", () => {
  assert.strictEqual(L.containsMath("$x$"), true);
  assert.strictEqual(L.containsMath("\\frac{1}{2}"), true);
  assert.strictEqual(L.containsMath("costs $5 and $10"), false);
  assert.strictEqual(L.containsMath("plain"), false);
});

test("toPlain rejects an unknown style", () => {
  assert.throws(() => L.toPlain("$x$", "html"), RangeError);
});

test("toPlain styles", () => {
  assert.strictEqual(L.toPlain("$\\vec{F} = m\\vec{a}$"), "F = ma");
  assert.strictEqual(
    L.toPlain("$\\vec{F} = m\\vec{a}$", "pdf"),
    "F\u20d7 = ma\u20d7",
  );
  assert.strictEqual(
    L.toPlain("Speed is $\\frac{d}{t}$ **fast**", "tts"),
    "Speed is d over t fast",
  );
});

test("mojibake table fixes the common patterns", () => {
  for (const [bad, good] of [
    ["\u00cf\u20ac", "\u03c0"],
    ["\u00c3\u2014", "\u00d7"],
    ["\u00e2\u02c6\u0161" + "2", "\u221a2"],
    ["\u00e2\u2030\u00a4", "\u2264"],
  ]) {
    assert.strictEqual(L.fixMojibakeTable(bad), good);
  }
});

test("mojibake leaves legitimate accents alone", () => {
  assert.strictEqual(
    L.fixMojibakeTable("\u00c5ngstr\u00f6m and caf\u00e9"),
    "\u00c5ngstr\u00f6m and caf\u00e9",
  );
  assert.strictEqual(L.fixMojibakeTable("plain ascii"), "plain ascii");
  assert.strictEqual(L.fixMojibakeTable(null), null);
});

test("loadsModelJson throws on invalid JSON and keeps LaTeX", () => {
  assert.deepStrictEqual(L.loadsModelJson('{"a": "\\frac{1}{2}"}'), {
    a: "\\frac{1}{2}",
  });
  assert.throws(() => L.loadsModelJson('{"a": '), SyntaxError);
});

test("loadsLatexAware accepts raw newlines and tabs inside strings, falls back, throws SyntaxError", () => {
  assert.deepStrictEqual(
    L.loadsLatexAware('{"q": "line one\nline two\ttab"}'),
    { q: "line one\nline two\ttab" },
  );
  assert.deepStrictEqual(L.loadsLatexAware('{"q": "Find $\\frac{1}{2}$"}'), {
    q: "Find $\\frac{1}{2}$",
  });
  assert.deepStrictEqual(L.loadsLatexAware('{"path": "C:\\\\dir"}'), {
    path: "C:\\dir",
  });
  assert.throws(() => L.loadsLatexAware("not json at all"), SyntaxError);
  assert.throws(() => L.loadsLatexAware('{"q": '), SyntaxError);
});

test("escapeLatexForJson keeps JSON escapes and doubles LaTeX", () => {
  assert.strictEqual(
    L.escapeLatexForJson('{"q": "a\\nb \\theta \\"x\\" \\u00e9 \\/"}'),
    '{"q": "a\\nb \\\\theta \\"x\\" \\u00e9 \\/"}',
  );
  assert.strictEqual(
    L.escapeLatexForJson('{"q": "$\\nu$ and \\nu = 5"}'),
    '{"q": "$\\\\nu$ and \\nu = 5"}',
  );
  assert.strictEqual(
    L.escapeLatexForJson('{"q": "\\frac \\beta \\5"}'),
    '{"q": "\\\\frac \\\\beta \\\\5"}',
  );
});

test("all kinds are produced by some detector", () => {
  assert.deepStrictEqual(
    new Set(L.ALL_KINDS),
    new Set([
      "control_char",
      "legacy_delimiter",
      "unbalanced_dollar",
      "command_missing_argument",
      "frac_missing_args",
      "script_missing_braces",
      "mojibake",
      "double_escaped_command",
      "unsupported_command",
      "bare_unicode_math",
      "unicode_chemistry",
      "bare_left_brace",
    ]),
  );
  assert.strictEqual(DETECTORS.length, L.ALL_KINDS.length);
});

test("constants are exported in their documented shapes", () => {
  assert.strictEqual(L.VERSION, "1.3.0");
  assert.ok(L.KATEX_COMMANDS instanceof Set && L.KATEX_COMMANDS.has("frac"));
  assert.ok(
    L.LATEX_COMMANDS_BEHIND_JSON_ESCAPES instanceof Set &&
      L.LATEX_COMMANDS_BEHIND_JSON_ESCAPES.has("theta"),
  );
  assert.ok(!L.LATEX_COMMANDS_BEHIND_JSON_ESCAPES.has("nu"));
  assert.ok(L.JSON_WHITESPACE_COLLISION_COMMANDS.has("nu"));
  assert.ok(
    L.WRAPPABLE_BARE_CHARS instanceof Set &&
      L.WRAPPABLE_BARE_CHARS.has("\u03c0"),
  );
  assert.ok([...L.WRAPPABLE_BARE_CHARS].every((c) => c.length === 1));
  assert.strictEqual(L.UNICODE_MATH["\u03c0"], "\\pi");
  assert.strictEqual(L.HOMOGLYPHS["\u00b5"], "\u03bc");
  assert.ok(
    Array.isArray(L.COLLAPSE_COMMANDS) && L.COLLAPSE_COMMANDS.includes("frac"),
  );
  assert.ok(
    Array.isArray(L.STRUCTURAL_COMMANDS) &&
      L.STRUCTURAL_COMMANDS.includes("sqrt"),
  );
  assert.strictEqual(L.LATEX_CMD_MAP["alpha"], "\u03b1");
  assert.strictEqual(L.MOJIBAKE_TABLE["\u00cf\u20ac"], "\u03c0");
  assert.ok(L.NON_CONTENT_KEYS instanceof Set && L.NON_CONTENT_KEYS.has("_id"));
  assert.ok(
    Array.isArray(L.NON_CONTENT_KEY_SUFFIXES) &&
      L.NON_CONTENT_KEY_SUFFIXES.includes("_url"),
  );
});
