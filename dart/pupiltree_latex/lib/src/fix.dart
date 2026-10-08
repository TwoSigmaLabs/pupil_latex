/// `fix`: the one call for people who do not want to learn the six.
///
/// ```dart
/// fix('Cost $5 and \(\theta\) with H₂O and π')
/// // -> r'Cost \$5 and $\theta$ with $\text{H}_{2}\text{O}$ and $\pi$'
/// ```
///
/// `fix` = [normalize] (lossless repair, mojibake, delimiters, orphans,
/// currency, prose escapes) → [canonicalize] (Unicode math → LaTeX, bare
/// structural commands and scripts wrapped in `$…$`, brace fixes) →
/// [wrapBareSymbolCommands] (a bare `\times` / `\pi` / `\leq` in prose →
/// `$\times$`) → [wrapUnicodeChemistry] (`H₂O` → `$\text{H}_{2}\text{O}$`)
/// → [wrapUnicodeScripts] (`10⁻³` → `$10^{-3}$`, `mc²` → `$mc^{2}$`) →
/// [escapeTextSpecials] (`%` and a `$` inside `\text{}` escaped inside
/// math) → [mergeAdjacentMath] (`$\times$ $10^8$` → `$\times 10^8$`).
/// Idempotent. Port of `python/pupiltree_latex/fix.py`.
///
/// Where to call it: on fresh model output at the write chokepoint, once,
/// then store; or on whatever text is about to be displayed (`MathText`
/// does it for you). Not as a read-path rewrite of stored content served
/// back to other apps (CONTRACT §3).
library;

import 'canonicalize.dart';
import 'guarded_regexp.dart';
import 'normalize.dart';
import 'segment.dart';
import 'tables.g.dart';
import 'text_util.dart';
import 'unicode_math.dart';
import 'walk.dart';

// ---------------------------------------------------------------------------
// Bare symbol commands
// ---------------------------------------------------------------------------

// [kSymbolCommands]: commands that take no argument and stand alone (every
// plain `\name` a Unicode math character maps to, minus `\sqrt`, plus the
// common aliases). A bare one in prose (`3 \times 10^8`) renders as the
// literal backslash text; wrapping it is always right because these
// commands mean nothing outside math. Longest names first so `\leq` is not
// read as `\le` + `q`.
final _bareSymbol = GuardedRegExp.notAfter(
  r'\\',
  '\\\\('
      '${(kSymbolCommands.toList()..sort((a, b) => b.length.compareTo(a.length))).join('|')}'
      ')(?![A-Za-z])',
);

String _applyToTextSegments(String text, String Function(String) transform) {
  final out = StringBuffer();
  for (final seg in segment(text)) {
    out.write(seg.isMath ? seg.raw : transform(seg.raw));
  }
  return out.toString();
}

String _applyToMathSegments(String text, String Function(String) transform) {
  final out = StringBuffer();
  for (final seg in segment(text)) {
    if (seg.isMath) {
      final raw = seg.raw;
      final k = raw.startsWith(r'$$') || raw.startsWith(r'\') ? 2 : 1;
      out.write(raw.substring(0, k));
      out.write(transform(raw.substring(k, raw.length - k)));
      out.write(raw.substring(raw.length - k));
    } else {
      out.write(seg.raw);
    }
  }
  return out.toString();
}

final String _symbolAlternation = (kSymbolCommands.toList()
      ..sort((a, b) => b.length.compareTo(a.length)))
    .join('|');

// A symbol command that a broken earlier pass left between two dollars which
// the renderers do not read as a span (`x$\leq$5`: a closer followed by a
// digit is not a closer). In a text segment its dollars are dropped first
// and it is then wrapped like any bare command.
final _delimitedSymbol = GuardedRegExp.notAfter(
  r'\\$',
  '\\\$(\\\\(?:$_symbolAlternation))\\\$(?![\$A-Za-z])',
);
// Inside a cluster: another bare symbol command (`3\times4\times5`).
final _clusterCommand = RegExp('\\\\(?:$_symbolAlternation)(?![A-Za-z])');

String _wrapSymbolsInText(String t) {
  if (t.contains(r'$')) {
    t = _delimitedSymbol.replaceAllMapped(t, (m) => m[1]!);
  }
  final out = StringBuffer();
  var last = 0;
  for (final m in _bareSymbol.allMatches(t)) {
    if (m.start < last) continue; // already inside the previous cluster
    final start = clusterLeft(t, m.start, last);
    final end = clusterRight(t, m.start, commandRe: _clusterCommand);
    out.write(t.substring(last, start));
    out.write(
      wrapCluster(t, start, end, convertCluster(t.substring(start, end))),
    );
    last = end;
  }
  out.write(t.substring(last));
  return out.toString();
}

/// `3 \times 10` → `3 $\times$ 10`; `\alpha` → `$\alpha$` — for
/// argument-less symbol commands outside math spans only. The span takes
/// the tight cluster around the command (`x\leq5` → `$x\leq5$`,
/// `\alpha_1` → `$\alpha_1$`, `3\times4\times5` → `$3\times4\times5$`), so
/// it never ends right before a digit; a command already between stray
/// dollars (`x$\leq$5`) is re-wrapped without them, never into `$$`.
String wrapBareSymbolCommands(String text) {
  if (!text.contains(r'\')) return text;
  return _applyToTextSegments(text, _wrapSymbolsInText);
}

// ---------------------------------------------------------------------------
// Unicode chemistry and scripts
// ---------------------------------------------------------------------------

// Subscript digits U+2080–U+2089; superscript digits ⁰ (U+2070), ¹²³
// (U+00B9, U+00B2, U+00B3 — outside the U+2070–U+2079 range, so they are
// listed one by one), ⁴–⁹ (U+2074–U+2079); charge signs ⁺ U+207A, ⁻ U+207B.
const _subDigits = '₀₁₂₃₄₅₆₇₈₉';
const _supChars = '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻';
const _scriptClass = '$_subDigits$_supChars';

const _scriptToAscii = <String, String>{
  '₀': '0',
  '₁': '1',
  '₂': '2',
  '₃': '3',
  '₄': '4',
  '₅': '5',
  '₆': '6',
  '₇': '7',
  '₈': '8',
  '₉': '9',
  '⁰': '0',
  '¹': '1',
  '²': '2',
  '³': '3',
  '⁴': '4',
  '⁵': '5',
  '⁶': '6',
  '⁷': '7',
  '⁸': '8',
  '⁹': '9',
  '⁺': '+',
  '⁻': '-',
};

/// A chemistry-shaped run: an optional coefficient and hydrate prefix, then
/// a capital letter, then element letters, digits and parentheses, with at
/// least one Unicode sub/superscript. Not preceded by a letter, digit or
/// `_` (`TRUE_FALSE⁻` stays); Python's negative lookbehind on `\w`.
final _chemRun = GuardedRegExp.notAfter(
  pyW,
  '[0-9]*[a-z]?(?=[A-Z])[A-Za-z0-9()]*[$_scriptClass]'
  '[A-Za-z0-9()$_scriptClass]*',
  unicode: true,
);
final _charge = RegExp('[⁰¹²³⁴⁵⁶⁷⁸⁹]*[⁺⁻]');
final _anyScript = RegExp('[$_scriptClass]');
final _chemToken = RegExp('[$_subDigits]+|[$_supChars]+|[^$_scriptClass]+');
// Any other base + Unicode scripts outside math (`10⁻³`, `mc²`, `x₁`, `s²`):
// a word of letters/digits followed by one run of scripts.
final _scriptRun = GuardedRegExp.notAfter(
  pyW,
  '([A-Za-z0-9]+(?:\\.[0-9]+)?)([$_supChars]+|[$_subDigits]+)'
  '(?![$_scriptClass])',
  unicode: true,
);

/// `H₂O)` → (`H₂O`, `)`): a closing parenthesis that has no opener inside
/// the run belongs to the prose around it.
(String, String) _trimUnbalancedParens(String run) {
  var tail = '';
  while (run.endsWith(')') &&
      ')'.allMatches(run).length > '('.allMatches(run).length) {
    run = run.substring(0, run.length - 1);
    tail = ')$tail';
  }
  return (run, tail);
}

String _ascii(String scripts) =>
    scripts.split('').map((c) => _scriptToAscii[c]!).join();

String _convertChemRun(String run) {
  final out = StringBuffer(r'$');
  for (final m in _chemToken.allMatches(run)) {
    final t = m[0]!;
    if (_subDigits.contains(t[0])) {
      out.write('_{${_ascii(t)}}');
    } else if (_supChars.contains(t[0])) {
      out.write('^{${_ascii(t)}}');
    } else {
      out.write('\\text{$t}');
    }
  }
  out.write(r'$');
  return out.toString();
}

/// One space around a new span where a neighbour would break it: a literal
/// `$` right before or after (`$$` opens display math), or a digit right
/// after (a closer followed by a digit is not a closer).
String _padSpan(String text, int start, int? end, String span) {
  if (start > 0 &&
      text[start - 1] == r'$' &&
      (start < 2 || text[start - 2] != r'\')) {
    span = ' $span';
  }
  if (end != null && end < text.length) {
    final nxt = codePointAt(text, end);
    if (nxt == r'$' || isDigit(nxt)) span = '$span ';
  }
  return span;
}

String _chemInText(String text) {
  return _chemRun.replaceAllMapped(text, (m) {
    final (run, tail) = _trimUnbalancedParens(m[0]!);
    final start = m.start;
    if (start > 0 && (text[start - 1] == r'\' || text[start - 1] == '{')) {
      return '$run$tail';
    }
    final hasSubscript = run.split('').any(_subDigits.contains);
    if (!hasSubscript && !_charge.hasMatch(run)) return '$run$tail';
    final span = _convertChemRun(run);
    if (tail.isNotEmpty) return '${_padSpan(text, start, null, span)}$tail';
    return _padSpan(text, start, m.end, span);
  });
}

/// `H₂O` → `$\text{H}_{2}\text{O}$`, `SO₄²⁻` → `$\text{SO}_{4}^{2-}$`,
/// `Fe³⁺` → `$\text{Fe}^{3+}$` — outside existing math spans only.
///
/// A run must start with a capital letter (after an optional coefficient
/// and hydrate prefix) and carry a subscript digit or a superscript charge;
/// `10⁸`, `mc²` and `x₁` are left to [wrapUnicodeScripts].
String wrapUnicodeChemistry(String text) {
  if (text.isEmpty) return text;
  if (!_anyScript.hasMatch(text)) return text;
  return _applyToTextSegments(text, _chemInText);
}

final _letters = RegExp(r'^\p{L}+$', unicode: true);

/// Python `str.islower()` for a string of letters: at least one cased
/// letter and no uppercase one.
bool _isLower(String s) => s == s.toLowerCase() && s != s.toUpperCase();

/// True when `text[..start]` ends with `/` or with a digit followed by
/// spaces or tabs.
bool _numberOrSlashBefore(String text, int start) {
  var k = start - 1;
  if (k >= 0 && text[k] == '/') return true;
  while (k >= 0 && (text[k] == ' ' || text[k] == '\t')) {
    k--;
  }
  if (k < 0) return false;
  final u = text.codeUnitAt(k);
  return u >= 0x30 && u <= 0x39;
}

String _scriptsInText(String text) {
  return _scriptRun.replaceAllMapped(text, (m) {
    final start = m.start;
    if (start > 0 && (text[start - 1] == r'\' || text[start - 1] == '{')) {
      return m[0]!;
    }
    var base = m[1]!;
    final scripts = m[2]!;
    // A unit is set upright (`240 cm³`, `m/s²`, `mol⁻¹`, `per mm³`);
    // anything else (`mc²`, `x₁`, `10⁸`) is math.
    final afterNumber = _numberOrSlashBefore(text, start);
    if (kUnitBases.contains(base) ||
        (_letters.hasMatch(base) &&
            _isLower(base) &&
            afterNumber &&
            (base.length > 1 ||
                kSingleLetterUnits.contains(base) ||
                text[start - 1] != '/'))) {
      base = '\\text{$base}';
    }
    final String span;
    if (_supChars.contains(scripts[0])) {
      span = '\$$base^{${_ascii(scripts)}}\$';
    } else {
      span = '\$${base}_{${_ascii(scripts)}}\$';
    }
    return _padSpan(text, start, m.end, span);
  });
}

/// `10⁻³` → `$10^{-3}$`, `mc²` → `$mc^{2}$`, `x₁` → `$x_{1}$` — a base of
/// letters/digits followed by one run of Unicode scripts, outside math
/// spans, after chemistry has taken its formulas.
String wrapUnicodeScripts(String text) {
  if (text.isEmpty) return text;
  if (!_anyScript.hasMatch(text)) return text;
  return _applyToTextSegments(text, _scriptsInText);
}

// ---------------------------------------------------------------------------
// Specials inside math
// ---------------------------------------------------------------------------

final _textGroup = RegExp(
  '\\\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox)$pyS*\\{',
);
final _unescapedPercent = GuardedRegExp.notAfter(r'\\', '%');
final _unescapedDollar = GuardedRegExp.notAfter(r'\\', r'\$');

String _escapeSpecialsInMath(String value) {
  // `%` starts a TeX comment: `$50%$` renders nothing after it.
  value = _unescapedPercent.replaceAll(value, r'\%');
  // A `$` inside a `\text{…}` group would end the span for the renderer.
  final out = StringBuffer();
  var i = 0;
  final n = value.length;
  while (i < n) {
    final m = _textGroup.matchAsPrefix(value, i);
    if (m != null) {
      var depth = 0;
      var j = m.end - 1;
      while (j < n) {
        if (value[j] == r'\') {
          j += 2;
          continue;
        }
        if (value[j] == '{') {
          depth++;
        } else if (value[j] == '}') {
          depth--;
          if (depth == 0) {
            j++;
            break;
          }
        }
        j++;
      }
      if (j > n) j = n;
      out.write(_unescapedDollar.replaceAll(value.substring(i, j), r'\$'));
      i = j;
      continue;
    }
    out.write(value[i]);
    i++;
  }
  return out.toString();
}

/// Inside math spans: `%` → `\%`; a `$` inside `\text{…}` → `\$`. Both would
/// otherwise cut the formula short in every renderer.
String escapeTextSpecials(String text) {
  if (!text.contains('%') && !text.contains(r'$')) return text;
  return _applyToMathSegments(text, _escapeSpecialsInMath);
}

// ---------------------------------------------------------------------------
// Adjacent spans
// ---------------------------------------------------------------------------

final _onlyBlanks = RegExp(r'^[ \t]*$');
final _env = RegExp(r'\\(begin|end)\{');
// Declaration-style switches (`\bf`, `\color{red}`, `\Large`): they act on
// everything after them in their span, so merging changes their scope.
final _declaration = RegExp(
  '\\\\(?:${kDeclarationCommands.join('|')})(?![A-Za-z])',
);

/// A span is merged only when it is self-contained: balanced braces and
/// matched `\begin`/`\end`. Merging a broken span would break its
/// neighbours too.
bool _mergeable(String value) {
  var depth = 0;
  for (var i = 0; i < value.length; i++) {
    if (value[i] == '{') {
      depth++;
    } else if (value[i] == '}') {
      depth--;
      if (depth < 0) return false;
    }
  }
  if (depth != 0) return false;
  if (value.contains(r'\') && _declaration.hasMatch(value)) return false;
  final envs = _env.allMatches(value).map((m) => m[1]).toList();
  return envs.where((e) => e == 'begin').length ==
      envs.where((e) => e == 'end').length;
}

bool _isInline(Segment seg) =>
    seg.isMath && !seg.display && seg.raw.startsWith(r'$');

/// `$\times$ $10^8$` → `$\times 10^8$`: inline spans separated by nothing or
/// by spaces/tabs become one span. Display spans, spans with prose between
/// them and spans that are not self-contained are left alone. Linear: each
/// span's mergeability is computed once.
String mergeAdjacentMath(String text) {
  if (r'$'.allMatches(text).length < 4) return text;
  final segs = segment(text);
  final out = StringBuffer();
  final runValues = <String>[]; // values of the inline spans being merged
  var runOk = false;

  void flush() {
    if (runValues.isNotEmpty) {
      out.write('\$${runValues.join(' ')}\$');
      runValues.clear();
    }
  }

  var i = 0;
  final n = segs.length;
  while (i < n) {
    final seg = segs[i];
    if (_isInline(seg)) {
      final ok = _mergeable(seg.value);
      if (runValues.isNotEmpty && runOk && ok) {
        runValues.add(seg.value);
      } else {
        flush();
        runValues.add(seg.value);
        runOk = ok;
      }
      i++;
      continue;
    }
    if (!seg.isMath &&
        _onlyBlanks.hasMatch(seg.raw) &&
        runValues.isNotEmpty &&
        i + 1 < n &&
        _isInline(segs[i + 1]) &&
        runOk &&
        _mergeable(segs[i + 1].value)) {
      i++; // the blank separator disappears into the merged span
      continue;
    }
    flush();
    out.write(seg.raw);
    i++;
  }
  flush();
  return out.toString();
}

// ---------------------------------------------------------------------------
// The one call
// ---------------------------------------------------------------------------

/// A span whose whole body is one of these is typography, not maths (tag
/// `v140-a7`): `leukocytes$\ldots$` → `leukocytes…`. `\textmu` becomes
/// `$\mu$`, not a bare `µ`: `canonicalize` wraps a bare `µ` as `$\mu$`, so
/// that is the fixed point (`$\cdots$` stays for the same reason).
const Map<String, String> kTypographicSpans = {
  r'\ldots': '…',
  r'\dots': '…',
  r'\textellipsis': '…',
  r'\textmu': r'$\mu$',
};

/// Replace each math span whose trimmed body is a key of
/// [kTypographicSpans] (inline or display) by its value; every other span
/// and all prose are copied as written.
String unwrapTypographicSpans(String text) {
  if (!text.contains(r'\')) return text;
  if (!kTypographicSpans.keys.any(text.contains)) return text;
  final out = StringBuffer();
  var changed = false;
  for (final seg in segment(text)) {
    if (seg.isMath) {
      final value = kTypographicSpans[pyStrip(seg.value)];
      if (value != null) {
        out.write(value);
        changed = true;
        continue;
      }
    }
    out.write(seg.raw);
  }
  return changed ? out.toString() : text;
}

/// Repair, normalise, canonicalise, wrap what is still bare, escape what
/// would cut a formula short and merge adjacent spans, in one call.
/// Idempotent; the empty string passes through.
///
/// `chemistry: false` is for renderers without KaTeX's mhchem extension: a
/// bare `\ce{…}` / `\pu{…}` is never put into a new math span.
String fix(String text, {bool chemistry = true}) {
  if (text.isEmpty) return text;
  text = canonicalize(
    unwrapTypographicSpans(normalize(text)),
    chemistry: chemistry,
  );
  text = wrapBareSymbolCommands(text);
  text = wrapUnicodeChemistry(text);
  text = wrapUnicodeScripts(text);
  text = escapeTextSpecials(text);
  return mergeAdjacentMath(text);
}

/// [fix] over every content string of a JSON-like document, skipping
/// non-content keys and URL-shaped values (CONTRACT §5); list items inherit
/// the parent key.
Object? fixDeep(Object? obj, {String keyHint = '', bool chemistry = true}) {
  if (obj is String) {
    if (isNonContentKey(keyHint) || isUrlOrPathString(obj)) return obj;
    return fix(obj, chemistry: chemistry);
  }
  if (obj is Map) {
    return mapValuesWithKey(
      obj,
      (k, v) => fixDeep(v, keyHint: k is String ? k : '', chemistry: chemistry),
    );
  }
  if (obj is List) {
    return <Object?>[
      for (final v in obj) fixDeep(v, keyHint: keyHint, chemistry: chemistry),
    ];
  }
  return obj;
}
