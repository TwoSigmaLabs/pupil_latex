/// Unicode math character → LaTeX command conversion, homoglyphs, the
/// combining vector arrow and bare-Unicode wrapping. Port of
/// `python/pupiltree_latex/unicode_math.py` (Backend
/// `services/ai/helper/unicode_to_latex.py`). Used by `canonicalize` only.
library;

import 'spans.dart';
import 'tables.g.dart';
import 'text_util.dart';

final _homoglyph = RegExp(charClass(kHomoglyphs.keys));

/// Replace visually-identical Unicode code points with their canonical form
/// (`µ` U+00B5 → `μ` U+03BC, …). Must run before [unicodeMathToLatex].
String normalizeHomoglyphs(String text) {
  if (text.isEmpty) return text;
  if (!_homoglyph.hasMatch(text)) return text;
  final out = StringBuffer();
  for (final r in text.runes) {
    final ch = String.fromCharCode(r);
    out.write(kHomoglyphs[ch] ?? ch);
  }
  return out.toString();
}

// Combining vector arrow (U+20D7) is the Unicode way to write `a⃗`. No
// precomposed form exists, so it survives NFC; it is unambiguous math
// notation (prose never uses it).
final _combiningVec = RegExp('([A-Za-z])${u(0x20D7)}');

/// Convert `X` + U+20D7 to `\vec{X}`; occurrences outside math spans are
/// wrapped in `$…$` so flutter_math_fork renders them (one mask per call).
String convertCombiningVec(String text) {
  if (text.isEmpty) return text;
  if (!text.contains(u(0x20D7))) return text;
  final mask = mathMask(text);
  return text.replaceAllMapped(_combiningVec, (m) {
    if (mask[m.start]) return '\\vec{${m[1]}}';
    return '\$\\vec{${m[1]}}\$';
  });
}

// Fast-path check: any character from kUnicodeMath present?
final _trigger = RegExp(charClass(kUnicodeMath.keys));

/// True when `\cmd` would run into a following letter.
bool _needsTerminator(String replacement, String? nextChar) {
  if (!replacement.startsWith(r'\')) return false;
  if (!isAlpha(replacement[replacement.length - 1])) return false;
  if (nextChar == null) return false;
  return isAlpha(nextChar);
}

// The radical glyphs map to `\sqrt`, the one command here that REQUIRES an
// argument (`$\sqrt$` is a KaTeX parse error, #1654). They are only
// converted together with their radicand; with none to take, the glyph
// stays, which both renderers display.
const _rootChars = {'√', '∛', '∜'};
final _rootNumber = RegExp('[-−]?[0-9]+(?:\\.[0-9]+)?');
const _closers = {'(': ')', '{': '}'};
// What may not follow a captured number or letter: more of the same word, a
// call, or a script.
const _scriptChars = '^_⁰¹²³⁴⁵⁶⁷⁸'
    '⁹⁺⁻ⁿ₀₁₂₃₄₅₆₇'
    '₈₉';

/// The radicand starting at [pos] as `(inner text, end index)`, or null.
///
/// Only shapes with a single reading are taken: a balanced `(…)` or `{…}`
/// group that stays inside one line and one math span, a number, or a
/// single letter.
(String, int)? _rootArgument(String text, int pos) {
  if (pos >= text.length) return null;
  final ch = text[pos];
  if (_closers.containsKey(ch)) {
    final closer = _closers[ch]!;
    var depth = 0;
    for (var end = pos; end < text.length; end++) {
      final c = text[end];
      if (c == r'$' || c == '\n') return null;
      if (c == ch) {
        depth++;
      } else if (c == closer) {
        depth--;
        if (depth == 0) {
          final inner = text.substring(pos + 1, end);
          return pyStrip(inner).isNotEmpty ? (inner, end + 1) : null;
        }
      }
    }
    return null;
  }
  final int end;
  final m = _rootNumber.matchAsPrefix(text, pos);
  final cp = codePointAt(text, pos);
  if (m != null) {
    end = m.end;
  } else if (isAlpha(cp)) {
    end = pos + cp.length;
  } else {
    return null;
  }
  final nxt = end < text.length ? codePointAt(text, end) : '';
  if (nxt.isNotEmpty &&
      (isAlnum(nxt) || nxt == '(' || _scriptChars.contains(nxt))) {
    return null;
  }
  return (text.substring(pos, end), end);
}

/// Inside math `\sqrt` takes the next token; false when there is none.
bool _rootHasNextToken(String segment, int pos) {
  final rest = pyLstrip(segment.substring(pos));
  return rest.isNotEmpty &&
      !'}&^_'.contains(rest[0]) &&
      !rest.startsWith(r'\\');
}

// Text-mode groups inside math: their content is prose, and KaTeX renders
// `\text{H₂O}` or `\text{→}` as written while `\text{H_{2}O}` is a parse
// error. The group is copied verbatim (balanced braces).
final _textGroup = RegExp(
  '\\\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|mathrm|mbox|hbox|ce|pu)$pyS*\\{',
);
final Set<String> _superscriptChars = {
  for (final e in kUnicodeMath.entries)
    if (e.value.startsWith('^{')) e.key,
};
final Set<String> _subscriptChars = {
  for (final e in kUnicodeMath.entries)
    if (e.value.startsWith('_{')) e.key,
};

/// Index just past the `}` matching the `{` at [i] (or the length on
/// imbalance); a backslash skips the next character.
int _skipGroup(String segment, int i) {
  var depth = 0;
  final n = segment.length;
  while (i < n) {
    final c = segment[i];
    if (c == r'\') {
      i += 2;
      continue;
    }
    if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth--;
      if (depth == 0) return i + 1;
    }
    i++;
  }
  return n;
}

/// Replace every Unicode math char in a segment with its LaTeX form.
///
/// Skips `\text{…}`-family groups (prose inside math), turns a RUN of
/// Unicode super/subscripts into one `^{…}` / `_{…}` (`10⁻³` → `10^{-3}`,
/// never `10^{-}^{3}`), and, when a replacement is a `\cmd` command and the
/// next character is a letter, appends a space so `a⋅b` → `a\cdot b`.
String replaceChars(String segment) {
  if (!_trigger.hasMatch(segment)) return segment;
  final out = StringBuffer();
  final n = segment.length;
  var i = 0;
  while (i < n) {
    final ch = segment[i];
    if (ch == r'\') {
      final m = _textGroup.matchAsPrefix(segment, i);
      if (m != null) {
        final end = _skipGroup(segment, m.end - 1);
        out.write(segment.substring(i, end));
        i = end;
        continue;
      }
    }
    if (_superscriptChars.contains(ch) || _subscriptChars.contains(ch)) {
      final table =
          _superscriptChars.contains(ch) ? _superscriptChars : _subscriptChars;
      var j = i;
      final inner = StringBuffer();
      while (j < n && table.contains(segment[j])) {
        final v = kUnicodeMath[segment[j]]!;
        inner.write(v.substring(2, v.length - 1));
        j++;
      }
      out.write(identical(table, _superscriptChars) ? '^{' : '_{');
      out.write(inner);
      out.write('}');
      i = j;
      continue;
    }
    if (_rootChars.contains(ch)) {
      final arg = _rootArgument(segment, i + 1);
      if (arg != null) {
        final (inner, end) = arg;
        out.write('${kUnicodeMath[ch]!}{${replaceChars(inner)}}');
        i = end;
        continue;
      }
      if (!_rootHasNextToken(segment, i + 1)) {
        out.write(ch);
        i++;
        continue;
      }
    }
    var replacement = kUnicodeMath[ch] ?? ch;
    if (replacement != ch) {
      final nextChar = i + 1 < n ? codePointAt(segment, i + 1) : null;
      if (_needsTerminator(replacement, nextChar)) replacement += ' ';
    }
    out.write(replacement);
    i++;
  }
  return out.toString();
}

/// Convert Unicode math characters to their LaTeX command form inside
/// existing math spans (spec §3 step 12). Spans come from the renderers'
/// tokenizer, so display math, escaped dollars and currency are read exactly
/// as they will be typeset. Unchanged when no target character is present.
String unicodeMathToLatex(String text) {
  if (text.isEmpty) return text;
  if (!_trigger.hasMatch(text)) return text;
  final out = StringBuffer();
  var pos = 0;
  for (final (start, end, _) in mathRanges(text)) {
    out.write(text.substring(pos, start));
    final raw = text.substring(start, end);
    final k = raw.startsWith(r'$$') || raw.startsWith(r'\') ? 2 : 1;
    out.write(raw.substring(0, k));
    out.write(replaceChars(raw.substring(k, raw.length - k)));
    out.write(raw.substring(raw.length - k));
    pos = end;
  }
  out.write(text.substring(pos));
  return out.toString();
}

final _wrappable = RegExp(charClass(kWrappableBareChars));

/// Index one past the `}` closing the `{` at [j] (a backslash skips the
/// next character), or null when it does not close before a newline, a
/// math span or the end of the text.
int? _groupEnd(String text, int j, List<bool> mask) {
  var depth = 0;
  final n = text.length;
  var k = j;
  while (k < n) {
    if (mask[k]) return null;
    final c = text[k];
    if (c == r'\') {
      k += 2;
      continue;
    }
    if (c == '\n') return null;
    if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth--;
      if (depth == 0) return k + 1;
    }
    k++;
  }
  return null;
}

/// True when `text[..k]` ends with an unescaped `\name`.
bool _commandNameEndsAt(String text, int k) {
  var q = k;
  while (q > 0 && _isAsciiLetter(text[q - 1])) {
    q--;
  }
  if (q == k || q == 0 || text[q - 1] != r'\') return false;
  var run = 0;
  while (q - 1 - run >= 0 && text[q - 1 - run] == r'\') {
    run++;
  }
  return run.isOdd;
}

/// `out[i]` is true when `text[i]` lies inside a closed brace group, outside
/// math, that belongs to a bare script (`e^{iπ}`, `x_{α}`) or to a bare
/// command's arguments (`\frac{π}{2}`, `\sqrt[3]{2π}`, `\text{π}`): the
/// character right before the `{` is `^` or `_`, the end of an unescaped
/// `\name`, the `]` of an optional argument that directly follows a
/// `\name`, or the `}` of another such group. The later wrapping steps put
/// the whole group in one span, so the characters inside must not get a
/// span of their own first (`$e^{i$\pi$}$`).
List<bool> attachedGroupMask(String text, [List<bool>? mask]) {
  mask ??= mathMask(text);
  final n = text.length;
  final out = List<bool>.filled(n + 1, false);
  final attachedClose = <int>{}; // end index of each attached group
  for (var i = 0; i < n; i++) {
    if (text[i] != '{' || mask[i]) continue;
    var run = 0;
    while (i - 1 - run >= 0 && text[i - 1 - run] == r'\') {
      run++;
    }
    final end = run.isEven ? _groupEnd(text, i, mask) : null;
    if (end == null) continue;
    final prev = i > 0 ? text[i - 1] : '';
    var attached = prev == '^' ||
        prev == '_' ||
        _commandNameEndsAt(text, i) ||
        (prev == '}' && attachedClose.contains(i));
    if (!attached && prev == ']') {
      final o = i - 2 >= 0 ? text.lastIndexOf('[', i - 2) : -1;
      attached = o > 0 &&
          !text.substring(o + 1, i - 1).contains(']') &&
          _commandNameEndsAt(text, o);
    }
    if (attached) {
      for (var k = i; k < end; k++) {
        out[k] = true;
      }
      attachedClose.add(end);
    }
  }
  return out;
}

/// Wrap each bare [kWrappableBareChars] symbol outside math, together with
/// its tight cluster (spec §0.1), in one `$…$` span: `ħω` →
/// `$\hbar\omega$`, `3×4×5` → `$3\times4\times5$`, `ε₀` → `$\epsilon_{0}$`.
/// A radical without a radicand stays as written (#1654).
///
/// A Greek math letter whose Greek word ([greekWordAt]) is accepted starts
/// its cluster at the word start (`2πr` → `$2\pi r$`). With
/// [skipAttachedGroups] a symbol inside a bare script or command argument
/// group (`e^{iπ}`, `\frac{π}{2}`, see [attachedGroupMask]) is left to the
/// step that wraps the whole group; canonicalize calls this again with the
/// skip off for the groups nothing wrapped.
String wrapBareUnicodeMath(String text, {bool skipAttachedGroups = true}) {
  if (text.isEmpty) return text;
  if (!_wrappable.hasMatch(text)) return text;
  final mask = mathMask(text);
  final inGroup = skipAttachedGroups ? attachedGroupMask(text, mask) : null;
  final out = StringBuffer();
  var last = 0; // text[..last] has been emitted
  var i = 0;
  final n = text.length;
  while (i < n) {
    final ch = text[i];
    if (kWrappableBareChars.contains(ch) &&
        !mask[i] &&
        (inGroup == null || !inGroup[i])) {
      if (_rootChars.contains(ch) && _rootArgument(text, i + 1) == null) {
        i++; // no radicand: the glyph stays as written (#1654)
        continue;
      }
      // The span takes the whole tight cluster around the symbol, so its
      // closing `$` is never followed by a digit (the closer rule).
      final word =
          kGreekMathLetters.contains(ch) ? greekWordAt(text, i, mask) : null;
      final int start;
      final int end;
      if (word != null && word.$1 >= last) {
        // `2πr`, `fλ`, `Δx`: the span takes the whole Greek word.
        start = word.$1;
        end = clusterRight(text, start, mask: mask);
      } else {
        start = clusterLeft(text, i, last, mask);
        end = clusterRight(text, i, mask: mask);
      }
      out.write(text.substring(last, start));
      out.write(
        wrapCluster(
          text,
          start,
          end,
          convertCluster(text.substring(start, end)),
          mask,
        ),
      );
      last = i = end;
      continue;
    }
    i++;
  }
  out.write(text.substring(last));
  return out.toString();
}

// ---------------------------------------------------------------------------
// Tight clusters (spec §0.1): what a new `$…$` span around a bare symbol
// must take with it
// ---------------------------------------------------------------------------

final Set<String> _allScriptChars = {..._superscriptChars, ..._subscriptChars};
final _asciiScript = RegExp(
  r'[_^](?:\{[^{}$\n]*\}|\\[A-Za-z]+|[A-Za-z0-9](?![A-Za-z]))',
);
final _number = RegExp(r'[0-9]+(?:[.,][0-9]+)*');
const _numberChars = '0123456789.,';

bool _isAsciiLetter(String c) {
  if (c.length != 1) return false;
  final u = c.codeUnitAt(0);
  return (u >= 0x61 && u <= 0x7A) || (u >= 0x41 && u <= 0x5A);
}

bool _isAsciiDigit(String c) {
  if (c.length != 1) return false;
  final u = c.codeUnitAt(0);
  return u >= 0x30 && u <= 0x39;
}

bool _isAsciiUpper(String c) {
  final u = c.codeUnitAt(0);
  return u >= 0x41 && u <= 0x5A;
}

bool _masked(List<bool>? mask, int k) => mask != null && mask[k];

bool _standaloneLetter(String text, int k) =>
    _isAsciiLetter(text[k]) &&
    (k == 0 || !_isAsciiLetter(text[k - 1])) &&
    (k + 1 >= text.length || !_isAsciiLetter(text[k + 1]));

/// Start of the number or standalone single letter that ends at [end], or
/// null when what ends there may not join a span.
int? _leftAtom(
  String text,
  int end,
  int floor,
  List<bool>? mask,
  bool beforeSubscript,
) {
  if (end <= floor || _masked(mask, end - 1)) return null;
  final c = text[end - 1];
  if (_isAsciiDigit(c)) {
    var q = end - 1;
    while (q - 1 >= floor &&
        _numberChars.contains(text[q - 1]) &&
        !_masked(mask, q - 1)) {
      q--;
    }
    while (text[q] == '.' || text[q] == ',') {
      q++;
    }
    final prev = q >= 1 ? text[q - 1] : '';
    // A script argument (`10^2`), an escaped or currency dollar (`\$5`, the
    // canonicalize sentinel ending in U+E001) or a word (`CO2`) owns the
    // number.
    if (prev.isNotEmpty &&
        ('\\^_\$${u(0xE001)}'.contains(prev) ||
            (_isAsciiLetter(prev) && !_standaloneLetter(text, q - 1)))) {
      return null;
    }
    return q;
  }
  if (_isAsciiLetter(c)) {
    final p = end - 1;
    final prev = p >= 1 ? text[p - 1] : '';
    if (_isAsciiLetter(prev) || (prev.isNotEmpty && r'\^_'.contains(prev))) {
      return null;
    }
    // An uppercase letter with a subscript digit is chemistry (`H₂`), which
    // wrapUnicodeChemistry sets upright later.
    if (beforeSubscript && _isAsciiUpper(c)) return null;
    return p;
  }
  return null;
}

final _joiningCommand = RegExp(
  '\\\\(?:${(kJoiningCommands.toList()..sort((a, b) => b.length.compareTo(a.length))).join('|')})(?![A-Za-z])',
);

/// True when a joining operator (character or command) starts at [p].
bool _joiningAt(String text, int p) {
  if (p >= text.length) return false;
  return kJoiningChars.contains(text[p]) ||
      (text[p] == r'\' && _joiningCommand.matchAsPrefix(text, p) != null);
}

// ---------------------------------------------------------------------------
// Greek words (spec §0.1): `2πr`, `fλ`, `hν`, `Δx`, `ωt` are one span
// ---------------------------------------------------------------------------

// A Greek word that is a unit keeps today's shape (`$\mu$s`, `k$\Omega$`):
// an optional number, then μ + a unit symbol, or an SI prefix + Ω (+ m/cm
// for ohm-metre), then optional Unicode scripts (`μm²`). Anchored: Python's
// `fullmatch`.
final _greekUnit = RegExp(
  '^(?:[0-9]*(?:[.,][0-9]+)*(?:[kMGTmμµnp]?Ω(?:c?m)?|[μµ](?:'
  '${(kGreekUnitSymbols.toList()..sort((a, b) => b.length.compareTo(a.length))).map(regexEscape).join('|')}'
  '|Ω)?)${charClass(_allScriptChars.toList()..sort())}*)\$',
);
final _threeAsciiLetters = RegExp('[A-Za-z]{3}');
final _threeGreek = RegExp('${charClass(kGreekMathLetters)}{3}');
final _chemInWord = RegExp('[A-Z]${charClass(_subscriptChars)}');
const _beforeWordRefusals = '\\^_{\$\u{E001}';

bool _isAsciiAlnum(String c) => _isAsciiLetter(c) || _isAsciiDigit(c);

bool _greekWordChar(String text, int k, List<bool>? mask) {
  if (k < 0 || k >= text.length || _masked(mask, k)) return false;
  final c = text[k];
  if (kGreekMathLetters.contains(c) || _allScriptChars.contains(c)) {
    return true;
  }
  if (_isAsciiAlnum(c)) return true;
  // `.` / `,` only inside a number (`2.5λ`)
  return (c == '.' || c == ',') &&
      0 < k &&
      k < text.length - 1 &&
      _isAsciiDigit(text[k - 1]) &&
      _isAsciiDigit(text[k + 1]) &&
      !_masked(mask, k - 1) &&
      !_masked(mask, k + 1);
}

/// The code point ending right before UTF-16 index [i] (`i > 0`).
String _codePointBefore(String s, int i) {
  final low = s.codeUnitAt(i - 1);
  if (low >= 0xDC00 && low <= 0xDFFF && i >= 2) {
    final high = s.codeUnitAt(i - 2);
    if (high >= 0xD800 && high <= 0xDBFF) return s.substring(i - 2, i);
  }
  return s[i - 1];
}

/// `(start, end)` of the Greek word containing `text[k]`, or null.
///
/// A Greek word is a maximal run, with no whitespace, of Greek math letters
/// ([kGreekMathLetters]), ASCII letters, digits (`.`/`,` between digits) and
/// Unicode scripts that contains at least one Greek letter and one ASCII
/// letter or digit: `2πr`, `fλ`, `Δx`, `ωt`, `πr²`. It is refused when it
/// has 3+ ASCII letters in a row (`αβγtest`, `Thetaα`, `sinθ`), 3+ Greek
/// letters in a row, an uppercase letter with a subscript (chemistry,
/// `ΔH₂O`), when it is a unit (`µs`, `kΩ`, `10Ω`, `5μm²`), or when it
/// touches another word or a script: the character before it is a letter
/// or digit of any script, `\ ^ _ { $` or the canonicalize dollar sentinel;
/// the character after it is a letter or digit of any script. A math-span
/// character on either side is a boundary, not a refusal.
(int, int)? greekWordAt(String text, int k, [List<bool>? mask]) {
  if (!_greekWordChar(text, k, mask)) return null;
  var s = k;
  while (_greekWordChar(text, s - 1, mask)) {
    s--;
  }
  var e = k + 1;
  while (_greekWordChar(text, e, mask)) {
    e++;
  }
  final word = text.substring(s, e);
  var greek = false;
  var ascii = false;
  for (var j = 0; j < word.length; j++) {
    final c = word[j];
    if (kGreekMathLetters.contains(c)) greek = true;
    if (_isAsciiAlnum(c)) ascii = true;
  }
  if (!greek || !ascii) return null;
  if (s > 0 && !_masked(mask, s - 1)) {
    final b = _codePointBefore(text, s);
    if (isAlnum(b) || _beforeWordRefusals.contains(b)) return null;
  }
  if (e < text.length && !_masked(mask, e) && isAlnum(codePointAt(text, e))) {
    return null;
  }
  if (_threeAsciiLetters.hasMatch(word) ||
      _threeGreek.hasMatch(word) ||
      _chemInWord.hasMatch(word) ||
      _greekUnit.hasMatch(word)) {
    return null;
  }
  return (s, e);
}

/// Move [start] left over the tight operands a new span must include, when
/// the cluster starts with a joining operator: numbers (`3.14`,
/// `1,00,000`), standalone single letters (`x` in `x≤5`, not `abc`) and
/// Unicode scripts attached to one of those. Never below [floor], never
/// into a math span, a word, a script argument (`10^2`) or a currency
/// amount (`\$5`).
int clusterLeft(String text, int start, int floor, [List<bool>? mask]) {
  if (!_joiningAt(text, start)) return start;
  while (start > floor && !_masked(mask, start - 1)) {
    final c = text[start - 1];
    int? b;
    if (_allScriptChars.contains(c)) {
      var q = start - 1;
      while (q - 1 >= floor &&
          _allScriptChars.contains(text[q - 1]) &&
          !_masked(mask, q - 1)) {
        q--;
      }
      b = _leftAtom(text, q, floor, mask, _subscriptChars.contains(text[q]));
    } else {
      b = _leftAtom(text, start, floor, mask, false);
    }
    if (b == null) break;
    start = b;
  }
  return start;
}

/// End of the tight cluster that starts at [pos]: a run of wrappable
/// symbols (a radical with its radicand), bare symbol commands matched by
/// [commandRe], numbers, ASCII scripts (`_1`, `^{2}`), Unicode script runs,
/// and a standalone single letter right after a joining operator (`x→y`),
/// with nothing between them.
int clusterRight(String text, int pos, {List<bool>? mask, RegExp? commandRe}) {
  final n = text.length;
  var p = pos;
  var afterJoining = false;
  while (p < n && !_masked(mask, p)) {
    final c = text[p];
    var joining = false;
    final word = kGreekMathLetters.contains(c) || _isAsciiAlnum(c)
        ? greekWordAt(text, p, mask)
        : null;
    if (word != null && word.$1 >= pos) {
      p = word.$2; // `2πr`, `Δx`: the whole Greek word
    } else if (kWrappableBareChars.contains(c)) {
      if (_rootChars.contains(c)) {
        final arg = _rootArgument(text, p + 1);
        if (arg == null) break;
        p = arg.$2;
      } else {
        joining = kJoiningChars.contains(c);
        p++;
      }
    } else if (_allScriptChars.contains(c)) {
      while (p < n && _allScriptChars.contains(text[p]) && !_masked(mask, p)) {
        p++;
      }
    } else if (c == r'\' && commandRe != null) {
      final m = commandRe.matchAsPrefix(text, p);
      if (m == null) break;
      joining = _joiningAt(text, p);
      p = m.end;
    } else if (c == '_' || c == '^') {
      if (p == pos) break;
      final m = _asciiScript.matchAsPrefix(text, p);
      if (m == null || m[0]!.contains(r'$')) break;
      p = m.end;
    } else if (_isAsciiDigit(c)) {
      p = _number.matchAsPrefix(text, p)!.end;
    } else if (_isAsciiLetter(c)) {
      final nxt = p + 1 < n ? text[p + 1] : '';
      if (!afterJoining || (p > 0 && _isAsciiLetter(text[p - 1]))) break;
      if (_isAsciiLetter(nxt) || nxt == '(') break;
      if (_isAsciiUpper(c) && nxt.isNotEmpty && _subscriptChars.contains(nxt)) {
        break; // chemistry (`5H₂O`): left to wrapUnicodeChemistry
      }
      p++;
    } else {
      break;
    }
    afterJoining = joining;
  }
  return p;
}

/// LaTeX for a cluster: symbols → commands (a radical takes its radicand),
/// a run of Unicode scripts → one `^{…}` / `_{…}`, anything else as
/// written; a space only where a command would run into a letter.
String convertCluster(String cluster) {
  final parts = <String>[];
  final n = cluster.length;
  var i = 0;
  while (i < n) {
    final c = cluster[i];
    var step = 1;
    String rep;
    final root = _rootChars.contains(c) ? _rootArgument(cluster, i + 1) : null;
    if (_allScriptChars.contains(c)) {
      final table =
          _superscriptChars.contains(c) ? _superscriptChars : _subscriptChars;
      var j = i;
      final inner = StringBuffer();
      while (j < n && table.contains(cluster[j])) {
        final v = kUnicodeMath[cluster[j]]!;
        inner.write(v.substring(2, v.length - 1));
        j++;
      }
      rep = '${identical(table, _superscriptChars) ? '^{' : '_{'}$inner}';
      step = j - i;
    } else if (root != null) {
      rep = '${kUnicodeMath[c]!}{${replaceChars(root.$1)}}';
      step = root.$2 - i;
    } else if (kWrappableBareChars.contains(c)) {
      rep = kUnicodeMath[c]!;
    } else {
      rep = c;
    }
    if (parts.isNotEmpty && _needsTerminator(parts.last, rep[0])) {
      parts.add(' ');
    }
    parts.add(rep);
    i += step;
  }
  return parts.join();
}

/// `$latex$` for `text[start..end]`, padded with one space where the
/// neighbour would break the span: a literal `$` right before or after
/// (`$$` would open display math) or a digit right after (a closer followed
/// by a digit is not a closer).
String wrapCluster(
  String text,
  int start,
  int end,
  String latex, [
  List<bool>? mask,
]) {
  var head = '';
  var tail = '';
  if (start > 0 && text[start - 1] == r'$' && !_masked(mask, start - 1)) {
    if (start < 2 || text[start - 2] != r'\') head = ' ';
  }
  if (end < text.length && !_masked(mask, end)) {
    final nxt = codePointAt(text, end);
    if (nxt == r'$' || isDigit(nxt)) tail = ' ';
  }
  return '$head\$$latex\$$tail';
}
