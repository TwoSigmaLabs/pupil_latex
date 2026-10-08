/// `canonicalize`: the write-time sanitiser for fresh Class A model output.
///
/// Backend `services/ai/helper/latex_rules.sanitize_latex_text` through
/// `python/pupiltree_latex/canonicalize.py`. Heuristic. Idempotent. Runs
/// ONCE, at the generation chokepoint. Never on the read path (Backend
/// #1595, the 14 September 2026 incident).
library;

import 'audit.dart';
import 'commands.dart';
import 'guarded_regexp.dart';
import 'mojibake.dart';
import 'normalize.dart' show isFormula;
import 'repair.dart';
import 'segment.dart';
import 'spans.dart';
import 'tables.g.dart';
import 'text_util.dart';
import 'unicode_math.dart';
import 'walk.dart';

// ---------------------------------------------------------------------------
// Delimiter rewrites
// ---------------------------------------------------------------------------

// Neither delimiter may follow a backslash (`\\(` is a line break then a
// parenthesis): the opener through the guard, the closer through the last
// character of the lazy body, `.*?[^\\]` (at least one character, as `.+?`).
final _parenInline =
    GuardedRegExp.notAfter(r'\\', r'\\\((.*?[^\\])\\\)', dotAll: true);
final _bracketDisplay =
    GuardedRegExp.notAfter(r'\\', r'\\\[(.*?[^\\])\\\]', dotAll: true);

// Inside a math segment, x^10 → x^{10}, a_12 → a_{12} (2+ digit runs only).
final _missingBrace = RegExp(r'([\^_])(-?[0-9]{2,})');
final _displaySpan = RegExp(r'\$\$(.+?)\$\$', dotAll: true);
final _inlineSpan = GuardedRegExp.notAfter(r'$', r'\$([^$]+?)\$(?!\$)');
// An identifier that ended up inside math (`$q_001_easy_2026$`): bracing its
// digit runs only produces a double-subscript error.
final _identifierInMath = RegExp(r'[A-Za-z0-9]+(?:_[A-Za-z0-9]+){2,}');

String _normalizeBracesInMath(String segment) {
  final protected = [
    for (final m in _identifierInMath.allMatches(segment)) (m.start, m.end),
  ];
  return segment.replaceAllMapped(_missingBrace, (m) {
    if (protected.any((p) => p.$1 <= m.start && m.start < p.$2)) return m[0]!;
    return '${m[1]}{${m[2]}}';
  });
}

String _normalizeBraces(String text) {
  text = text.replaceAllMapped(
    _displaySpan,
    (m) => '\$\$${_normalizeBracesInMath(m[1]!)}\$\$',
  );
  text = _inlineSpan.replaceAllMapped(
    text,
    (m) => '\$${_normalizeBracesInMath(m[1]!)}\$',
  );
  return text;
}

// ---------------------------------------------------------------------------
// Structural fixes
// ---------------------------------------------------------------------------

// An EVEN run of backslashes directly before a KaTeX command is JSON
// re-encoding damage (`\\frac`); an odd run (`\\\frac`) is a line break
// followed by a command and is left alone.
final _collapse = GuardedRegExp.notAfter(
  r'\\',
  '((?:\\\\\\\\)+)('
      '${(kCollapsibleCommands.toList()..sort((a, b) => b.length.compareTo(a.length))).map(regexEscape).join('|')}'
      ')(?![a-zA-Z])',
);

final _rowEnvironment = RegExp(r'\\begin\{|&');
const _twoArgumentCommands = {
  'frac',
  'dfrac',
  'tfrac',
  'cfrac',
  'binom',
  'dbinom',
  'tbinom',
};

/// `\\frac` → `\frac` everywhere EXCEPT inside a math span that holds an
/// environment or an alignment `&`: there `\\` is a row separator and
/// `a&b\\cos x` really is a row starting with `\cos`. Single-letter names
/// (`\c`, `\b`) are never collapsed: `\\c` is a row + "c".
String _collapseDoubleBackslashes(String text) {
  if (!text.contains(r'\\')) return text;
  String collapse(String chunk) => _collapse.replaceAllMapped(
        chunk,
        (m) => m[2]!.length == 1 ? m[0]! : '\\${m[2]}',
      );
  final out = StringBuffer();
  var pos = 0;
  for (final (start, end, _) in mathRanges(text)) {
    out.write(collapse(text.substring(pos, start)));
    final span = text.substring(start, end);
    out.write(_rowEnvironment.hasMatch(span) ? span : collapse(span));
    pos = end;
  }
  out.write(collapse(text.substring(pos)));
  return out.toString();
}

final _leftBrace = RegExp(r'\\left(?!\\)\{');
final _rightBrace = RegExp(r'\\right(?!\\)\}');

String _fixLeftRightBraces(String text) {
  text = text.replaceAll(_leftBrace, r'\left\{');
  text = text.replaceAll(_rightBrace, r'\right\}');
  return text;
}

// ---------------------------------------------------------------------------
// Currency (Backend rule: only when the unescaped `$` count is odd)
// ---------------------------------------------------------------------------

final _currency = GuardedRegExp.notAfter(
  r'\\',
  '\\\$([0-9][0-9,]*(?:\\.[0-9]+)?)(?=[$pyWs.,;!?)\\]\\-–—]|\$)',
);

/// True when an odd run of backslashes precedes `text[i]` (`\$` is an
/// escaped dollar, `\\$` a line break followed by a real one).
bool _dollarEscaped(String text, int i) {
  var k = i - 1;
  while (k >= 0 && text[k] == r'\') {
    k--;
  }
  return (i - 1 - k).isOdd;
}

int _countUnescapedDollars(String text) {
  var n = 0;
  for (var i = 0; i < text.length; i++) {
    if (text[i] == r'$' && !_dollarEscaped(text, i)) n++;
  }
  return n;
}

// `\$` preceded by an even run of backslashes (none, or `\\` line breaks):
// only that dollar is escaped. `\\$\frac{1}{2}$` is a line break followed by
// a span, and stashing its `\$` once broke the span into `\\$$…$$`.
final _escapedDollar = GuardedRegExp.notAfter(r'\\', r'((?:\\\\)*)\\\$');

String _stashEscapedDollars(String text) {
  if (!text.contains(r'\$')) return text;
  return _escapedDollar.replaceAllMapped(
    text,
    (m) => '${m[1]}$_escapedDollarSentinel',
  );
}

String _escapeCurrency(String text) {
  if (_countUnescapedDollars(text).isEven) return text;
  return _currency.replaceAllMapped(text, (m) => '\\\$${m[1]}');
}

// ---------------------------------------------------------------------------
// Bare-command wrapping
// ---------------------------------------------------------------------------

final _structuralCmd = RegExp(
  '\\\\(?:${kStructuralCommands.join('|')})(?![A-Za-z])',
);

/// Index one past the command at [start], its `[..]`/`{..}` arguments and
/// adjacent `_x` / `^x` scripts (nested braces handled).
int _findCommandExtent(String text, int start) {
  final n = text.length;
  var i = start + 1;
  while (i < n && isAlpha(text[i])) {
    i++;
  }
  while (i < n) {
    final ch = text[i];
    if (ch == '[' || ch == '{') {
      final opener = ch;
      final closer = opener == '[' ? ']' : '}';
      var depth = 1;
      i++;
      while (i < n && depth > 0) {
        if (text[i] == opener) {
          depth++;
        } else if (text[i] == closer) {
          depth--;
        }
        i++;
      }
    } else if (ch == '_' || ch == '^') {
      i++;
      if (i >= n) break;
      if (text[i] == '{') {
        var depth = 1;
        i++;
        while (i < n && depth > 0) {
          if (text[i] == '{') {
            depth++;
          } else if (text[i] == '}') {
            depth--;
          }
          i++;
        }
      } else if (text[i] == r'\') {
        i++;
        while (i < n && isAlpha(text[i])) {
          i++;
        }
      } else if (!isSpace(codePointAt(text, i))) {
        i += codePointAt(text, i).length;
      } else {
        break;
      }
    } else {
      break;
    }
  }
  return i;
}

final _anyLatexCmd = RegExp(r'\\[a-zA-Z]+');
final _scriptLabel = RegExp(r'\\[a-z][a-z_]*:');
final _textBrace = RegExp('\\\\text$pyS*\\{[^}]*\\}');
final _dollarSpan = RegExp(r'\$[^$]*\$');
final _proseWord = RegExp('[A-Za-z]{4,}');
// Python `[^\W\d_\x00-\x7f][^\W\d_]+`: a non-ASCII letter then letters.
final _nonAsciiWord = RegExp(r'(?![\x00-\x7F])\p{L}\p{L}+', unicode: true);
// Short function words that make a string prose even though they are under
// four letters (Backend's prose test was "a 4+ letter word", which let
// `3 \times 10^8 and \frac{a}{b}` be wrapped whole, italicising "and").
const _proseStopwords = {
  'a',
  'an',
  'and',
  'are',
  'as',
  'at',
  'be',
  'but',
  'by',
  'for',
  'if',
  'in',
  'is',
  'it',
  'of',
  'on',
  'or',
  'so',
  'the',
  'then',
  'to',
  'was',
  'we',
  'he',
  'she',
  'you',
  'all',
  'any',
  'can',
  'did',
  'do',
  'does',
  'get',
  'got',
  'had',
  'has',
  'how',
  'its',
  'let',
  'may',
  'not',
  'now',
  'one',
  'our',
  'out',
  'per',
  'put',
  'see',
  'set',
  'two',
  'use',
  'via',
  'who',
  'why',
  'yet',
};
final _shortWord =
    GuardedRegExp.notAfter('A-Za-z', '[A-Za-z]{1,3}(?![A-Za-z])');
// Every character kUnicodeMath maps to `^{…}` or `_{…}` (²³, ⁻, ₀, ⁿ, ₐ, …).
final _unicodeScript = RegExp(
  charClass([
    for (final e in kUnicodeMath.entries)
      if (e.value.startsWith('^{') || e.value.startsWith('_{')) e.key,
  ]),
);

bool _hasDollarInsideBraces(String text) {
  var depth = 0;
  for (var i = 0; i < text.length; i++) {
    final ch = text[i];
    final unescaped = i == 0 || text[i - 1] != r'\';
    if (ch == '{' && unescaped) {
      depth++;
    } else if (ch == '}' && unescaped && depth > 0) {
      depth--;
    } else if (ch == r'$' && unescaped && depth > 0) {
      return true;
    }
  }
  return false;
}

final _chemistryCmd = RegExp(r'\\(?:ce|pu)(?![A-Za-z])');

String _wrapPureMathShortStrings(String text, {bool chemistry = true}) {
  if (cpLength(text) > 200 ||
      text.contains(r'$$') ||
      !_anyLatexCmd.hasMatch(text)) {
    return text;
  }
  if (_hasDollarInsideBraces(text)) return text;
  // A lesson-script line (`\teacher: …`) is prose, however short.
  if (_scriptLabel.hasMatch(text)) return text;
  // `\ce`/`\pu` need KaTeX's mhchem extension; `chemistry: false` (a
  // renderer without it) leaves them as prose instead of a red error.
  if (!chemistry && _chemistryCmd.hasMatch(text)) return text;
  // An unpaired `$` means the author's spans are broken; stripping and
  // re-wrapping would not converge (`$ H₂` → `$ $…$` → …).
  if (_countUnescapedDollars(text).isOdd) return text;
  // At least one REAL command must sit outside a span: `\\cs` (a line
  // break followed by "cs") is not math and must not be wrapped.
  final mask = mathMask(text);
  final hasBareCmd = _anyLatexCmd.allMatches(text).any(
      (m) => !mask[m.start] && kKatexCommands.contains(m[0]!.substring(1)));
  if (!hasBareCmd) return text;
  // A command that needs an argument and has none (`\frac` alone) cannot
  // render however it is wrapped.
  if (detectCommandMissingArgument(text).isNotEmpty ||
      detectFracMissingArgs(text).isNotEmpty) {
    return text;
  }
  var stripped = text.replaceAll(_textBrace, '');
  stripped = stripped.replaceAll(_dollarSpan, '');
  stripped = stripped.replaceAll(_anyLatexCmd, '');
  if (_proseWord.hasMatch(stripped)) return text;
  // Prose in any other script (Devanagari, Tamil, …): a run of two or more
  // non-ASCII letters. Bare Greek was already wrapped by step 14, so what
  // is left is words.
  // Unicode super/subscripts (`10²³`) are letters/numbers to the regex
  // engine but are math, not letters of a word: they are blanked out first.
  if (_nonAsciiWord.hasMatch(stripped.replaceAll(_unicodeScript, ' '))) {
    return text;
  }
  if (_shortWord
      .allMatches(stripped)
      .any((m) => _proseStopwords.contains(m[0]!.toLowerCase()))) {
    return text;
  }
  var inner = pyStrip(text);
  if (inner.isEmpty) return text;
  inner = inner.replaceAll(r'$', '');
  if (inner.isEmpty) return text;
  final lead = text.substring(0, text.length - pyLstrip(text).length);
  final trail = text.substring(pyRstrip(text).length);
  return '$lead\$$inner\$$trail';
}

// Not right after the currency sentinel (its LAST char, U+E001), a
// backslash (`\log_{10}` is a command, not a bare script) or a `$`. Python
// `\b` before `[A-Za-z0-9]` is "no Unicode word character before", hence
// the guard on `pyW` (Dart's `\b` is ASCII-only).
final _bareScript = GuardedRegExp.notAfter(
  '${u(0xE001)}\\\\\$$pyW',
  '[A-Za-z0-9]+'
      r'(?:[_^](?:\{[^{}]*\}|\\[a-zA-Z]+|[A-Za-z0-9]+))+'
      r'[A-Za-z0-9]*',
  unicode: true,
);

final _digits = RegExp(r'^[0-9]+$');
final _shortCapitals = RegExp(r'^[A-Z]{1,4}$');
final _lowercaseWord = RegExp(r'^[a-z]{3,}$');
final _twoLowercase = RegExp(r'^[a-z]{2}$');

/// snake_case / ALL_CAPS / slug tokens the script regex matches by accident:
/// `MCQ_SINGLE`, `q_001_easy_2026`, `ahs_69e74f5e84fd`.
bool _looksLikeIdentifier(String s) {
  if (s.contains(r'\') ||
      s.contains('{') ||
      s.contains('}') ||
      s.contains('^')) {
    return false;
  }
  if (!s.contains('_')) return false;
  if ('_'.allMatches(s).length >= 2) return true;
  final cut = s.indexOf('_');
  final base = s.substring(0, cut);
  if (cpLength(base) >= 3) return true;
  // A two-letter lowercase base is a word or an id prefix (`lo_0` gap
  // titles), not a variable: math subscripts sit on one letter (`x_0`) and
  // chemistry on capitals (`H_2O`, `CO_2`).
  if (_twoLowercase.hasMatch(base)) return true;
  final rest = s.substring(cut + 1);
  // A class name: digits, underscore, 1–4 capital letters (`10_A`, `6_B`,
  // `12_PCM`). Math never writes a numeric base with a capital subscript.
  if (_digits.hasMatch(base) && _shortCapitals.hasMatch(rest)) return true;
  // `no_capture`, `ai_recreate`: a suffix that is a lowercase WORD (3+
  // letters, nothing else) is an enum, not a subscript (`v_avg` is the one
  // real-math casualty; `E_n`, `x_0`, `H_2O` keep their short suffixes).
  return _lowercaseWord.hasMatch(rest);
}

String _wrapBareScripts(String text) {
  if (!text.contains('^') && !text.contains('_')) return text;
  final inMathAt = mathMask(text);
  return _bareScript.replaceAllMapped(text, (m) {
    if (inMathAt[m.start] || _looksLikeIdentifier(m[0]!)) return m[0]!;
    return '\$${m[0]}\$';
  });
}

String _wrapBareLatexCommands(String text) {
  if (!text.contains(r'\') || !_structuralCmd.hasMatch(text)) return text;
  final n = text.length;
  // What is math is what the renderers will typeset (`segment`), not `$`
  // parity: `$ $\text{H}_{2}$` has one literal dollar and one span, and
  // parity once wrapped the span a second time into `$$…$$`.
  final mask = mathMask(text);
  final out = StringBuffer();
  var i = 0;
  while (i < n) {
    final ch = text[i];
    if (!mask[i] && ch == r'\') {
      final m = _structuralCmd.matchAsPrefix(text, i);
      if (m != null) {
        var end = _findCommandExtent(text, i);
        if (text.substring(i, end).contains(r'$') ||
            mask.sublist(i, end).contains(true)) {
          out.write(ch);
          i++;
          continue;
        }
        // A command that needs an argument but has none (`use \sqrt here`)
        // would become `$\sqrt$`, a parse error painted red; left as prose
        // it is at least readable and `audit` flags it.
        final name = text.substring(i + 1, m.end);
        if (kArgumentCommands.contains(name) && end == m.end) {
          out.write(ch);
          i++;
          continue;
        }
        // `\frac{x}` / `\tbinom{x}`: a two-argument command with one
        // argument fails in every renderer; leave it as prose.
        if (_twoArgumentCommands.contains(name) &&
            '{'.allMatches(text.substring(m.end, end)).length < 2) {
          out.write(ch);
          i++;
          continue;
        }
        // A number right after (`\sqrt{2}3`) joins the span: a closing `$`
        // followed by a digit is not a closer.
        if (end < n && _isAsciiDigitAt(text, end) && !mask[end]) {
          end = _numberAfterCommand.matchAsPrefix(text, end)!.end;
        }
        // A literal `$` right before or after (`$\frac{1}{2}` with no
        // closer): the author's delimiters are broken and a new span would
        // only make `$$`. Leave it as prose.
        if ((i > 0 && text[i - 1] == r'$' && !mask[i - 1]) ||
            (end < n && text[end] == r'$' && !mask[end])) {
          out.write(ch);
          i++;
          continue;
        }
        out.write(r'$');
        out.write(text.substring(i, end));
        out.write(r'$');
        if (end < n && isDigit(codePointAt(text, end)) && !mask[end]) {
          out.write(' ');
        }
        i = end;
        continue;
      }
    }
    out.write(ch);
    i++;
  }
  return out.toString();
}

final _numberAfterCommand = RegExp(r'[0-9]+(?:\.[0-9]+)?');

bool _isAsciiDigitAt(String s, int i) {
  final u = s.codeUnitAt(i);
  return u >= 0x30 && u <= 0x39;
}

// ---------------------------------------------------------------------------
// `$ x^2 + 1 = 0 $`: a span whose content is padded with spaces
// ---------------------------------------------------------------------------

final _paddedSpanHint = RegExp(r'\$[ \t]|[ \t]\$');
final _strongMath = RegExp(r'\\[A-Za-z]|[\^_]');
final _unicodeMathChar = RegExp(charClass(kUnicodeMath.keys));

/// True when the content of a `$ … $` pair is a formula, not prose between
/// two currency amounts (`$ 5 and got $`).
bool _looksLikePaddedMath(String core) {
  final strong = _strongMath.hasMatch(core) || _unicodeMathChar.hasMatch(core);
  if (!strong) {
    // `=` alone is enough unless the content starts like an amount.
    if (!core.contains('=') || isDigit(codePointAt(core, 0))) return false;
  }
  // A command that needs an argument and has none (`$5 \text $`) cannot
  // render; as prose it at least stays readable.
  final probe = '\$$core\$';
  if (detectCommandMissingArgument(probe).isNotEmpty ||
      detectFracMissingArgs(probe).isNotEmpty) {
    return false;
  }
  var words = core.replaceAll(_textBrace, '');
  words = words.replaceAll(_anyLatexCmd, '');
  if (_proseWord.hasMatch(words)) return false;
  return !_shortWord
      .allMatches(words)
      .any((m) => _proseStopwords.contains(m[0]!.toLowerCase()));
}

/// Python `str.strip(" \t")`.
String _stripBlanks(String s) {
  var a = 0;
  var b = s.length;
  while (a < b && (s[a] == ' ' || s[a] == '\t')) {
    a++;
  }
  while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\t')) {
    b--;
  }
  return s.substring(a, b);
}

/// The code point that ends at UTF-16 index [end] (exclusive).
String _codePointBefore(String s, int end) {
  if (end >= 2) {
    final low = s.codeUnitAt(end - 1);
    final high = s.codeUnitAt(end - 2);
    if (low >= 0xDC00 && low <= 0xDFFF && high >= 0xD800 && high <= 0xDBFF) {
      return s.substring(end - 2, end);
    }
  }
  return s[end - 1];
}

String _trimPaddedLine(String line) {
  if (line.contains(r'$$')) return line;
  final dollars = [
    for (var k = 0; k < line.length; k++)
      if (line[k] == r'$' && !_dollarEscaped(line, k)) k,
  ];
  // Unpaired: which dollar is currency is not ours to guess.
  if (dollars.length < 2 || dollars.length.isOdd) return line;
  final out = StringBuffer();
  var pos = 0;
  for (var p = 0; p + 1 < dollars.length; p += 2) {
    final a = dollars[p];
    final b = dollars[p + 1];
    final inner = line.substring(a + 1, b);
    final core = _stripBlanks(inner);
    if (core.isEmpty ||
        core == inner ||
        !(_looksLikePaddedMath(core) || isFormula(core)) ||
        // A dollar glued to a word or number outside the pair (`$x = $y`,
        // `wait$ … $now`) reads as currency or a typo.
        (b + 1 < line.length && isAlnum(codePointAt(line, b + 1))) ||
        (a > 0 && isAlnum(_codePointBefore(line, a)))) {
      continue;
    }
    out.write(line.substring(pos, a));
    out.write('\$$core\$');
    pos = b + 1;
  }
  out.write(line.substring(pos));
  return out.toString();
}

/// `Solve $ x^2 + 1 = 0 $ now` → `Solve $x^2 + 1 = 0$ now` (spec §3 step
/// 10a). The renderers do not open a span on `$` + space, so a padded
/// formula shows its dollars and the wrapping steps used to nest a second
/// span inside it. Text segments only, line by line; `I paid $ 5 and got
/// $ 3 back` is currency and stays.
String trimPaddedSpansInText(String text) {
  if (!text.contains(r'$') || !_paddedSpanHint.hasMatch(text)) return text;
  final out = StringBuffer();
  for (final seg in segment(text)) {
    var raw = seg.raw;
    if (!seg.isMath && '\$'.allMatches(raw).length >= 2) {
      raw = raw.split('\n').map(_trimPaddedLine).join('\n');
    }
    out.write(raw);
  }
  return out.toString();
}

// ---------------------------------------------------------------------------
// `$\frac{1}{2$`: a closed span whose last group was never closed
// ---------------------------------------------------------------------------

final _leftCmd = RegExp(r'\\left(?![A-Za-z])');
final _rightCmd = RegExp(r'\\right(?![A-Za-z])');
final _trailingCmd = RegExp('\\\\([A-Za-z]+)$pyS*\$');
// A group may not end right after these: the added `}` would leave them
// without their argument (`$\frac{1}{\sqrt$`, `$x^{2^$`).
final Set<String> _needsArgument = {
  ...kArgumentCommands,
  ..._twoArgumentCommands,
  'left',
  'right',
  'begin',
  'end',
  'sqrt',
  'cbrt',
};

/// How many `}` close [content], or 0 when it is balanced, has more `}`
/// than `{` at any point, or when closing it would guess: the innermost
/// open group is empty or ends in `\ ^ _ &` or in a command that needs an
/// argument. `\{` / `\}` do not count.
int _missingClosers(String content) {
  final stack = <int>[];
  var i = 0;
  final n = content.length;
  while (i < n) {
    final ch = content[i];
    if (ch == r'\') {
      i += 2;
      continue;
    }
    if (ch == '{') {
      stack.add(i);
    } else if (ch == '}') {
      if (stack.isEmpty) return 0;
      stack.removeLast();
    }
    i++;
  }
  if (stack.isEmpty) return 0;
  final inner = pyRstrip(content.substring(stack.last + 1));
  if (inner.isEmpty || r'\^_&{'.contains(inner[inner.length - 1])) return 0;
  final m = _trailingCmd.firstMatch(inner);
  if (m != null && _needsArgument.contains(m[1])) return 0;
  return stack.length;
}

String _closeBracesInLine(String line) {
  final dollars = <int>[];
  var backslashes = 0; // run of backslashes right before k
  for (var k = 0; k < line.length; k++) {
    final ch = line[k];
    if (ch == r'$' && backslashes.isEven) dollars.add(k);
    backslashes = ch == r'\' ? backslashes + 1 : 0;
  }
  if (dollars.length < 2 || dollars.length.isOdd) return line;
  final out = StringBuffer();
  var last = 0;
  var changed = false;
  for (var d = 0; d + 1 < dollars.length; d += 2) {
    final a = dollars[d];
    final b = dollars[d + 1];
    final content = line.substring(a + 1, b);
    if (content.isEmpty ||
        isSpace(content[0]) ||
        isSpace(content[content.length - 1]) ||
        (b + 1 < line.length && isDigit(codePointAt(line, b + 1))) ||
        !_strongMath.hasMatch(content)) {
      continue;
    }
    final missing = _missingClosers(content);
    if (missing == 0) continue;
    if (_leftCmd.allMatches(content).length !=
            _rightCmd.allMatches(content).length ||
        r'\begin{'.allMatches(content).length !=
            r'\end{'.allMatches(content).length) {
      continue;
    }
    final fixed = content + '}' * missing;
    final probe = '\$$fixed\$';
    if (detectCommandMissingArgument(probe).isNotEmpty ||
        detectFracMissingArgs(probe).isNotEmpty) {
      continue;
    }
    final segs = segment(probe);
    if (segs.length != 1 || !segs[0].isMath) continue;
    out.write(line.substring(last, a + 1));
    out.write(fixed);
    last = b;
    changed = true;
  }
  if (!changed) return line;
  out.write(line.substring(last));
  return out.toString();
}

/// `$\frac{1}{2$` → `$\frac{1}{2}$`; `$x^{2$` → `$x^{2}$` (spec §3 step
/// 10b).
///
/// A span whose last group was never closed is text to every renderer (the
/// closer is found at brace depth 0 only), so the formula shows its source.
/// In text segments only, line by line (a line with a `$$` or an odd count
/// of unescaped `$` is left alone), dollars are paired in order. A pair
/// gets the missing `}` appended to its content when all of: the content
/// does not start or end with whitespace and the closer is not followed by
/// a digit (the pandoc rules); it is math (a command, `^` or `_`); it has
/// more `{` than `}` and never more `}` than `{` (`\{` / `\}` do not
/// count); the innermost open group is not empty and does not end in
/// `\ ^ _ &` or a command that needs an argument (`$\frac{1}{$`, `$x^{$`
/// stay: never guess an argument); `\left` and `\right`, `\begin{` and
/// `\end{` are matched; and the result has no missing argument and is one
/// span. Idempotent: a balanced span is never touched.
String _closeUnbalancedBraces(String text) {
  if (!text.contains('{') || !text.contains(r'$')) return text;
  final out = StringBuffer();
  for (final seg in segment(text)) {
    var raw = seg.raw;
    if (!seg.isMath && raw.contains('{') && r'$'.allMatches(raw).length >= 2) {
      raw = raw
          .split('\n')
          .map((line) => line.contains(r'$$') ? line : _closeBracesInLine(line))
          .join('\n');
    }
    out.write(raw);
  }
  return out.toString();
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

final _escapedDollarSentinel = '${u(0xE000)}DOLLAR_ESC${u(0xE001)}';
final _url = RegExp(
  '^$pyS*(?:https?|gs|data|blob)://$pyNotS+$pyS*\$',
  caseSensitive: false,
);
final _imageMarker = RegExp(r'\{\{IMAGE:[^}]+\}\}');
// A URL must not swallow the math after it, hence the `$` exclusion.
final _embeddedUrl = RegExp(
  '(?:https?|gs)://[^$pyWs<>"\'\$]+',
  caseSensitive: false,
);

/// Stash token for image markers and embedded URLs: private-use characters
/// only (no letter, digit, `_` or brace, so no later step can read one as a
/// script — `IMG_10` once became `IMG_{10}`). The index is U+E100 + n.
String _stashToken(int idx) =>
    '${u(0xE002)}${String.fromCharCode(0xE100 + idx)}${u(0xE003)}';

/// Normalize a fresh model string to the canonical form (spec §3).
///
/// `chemistry: false` never puts a bare `\ce{…}` / `\pu{…}` into a new
/// math span (for renderers without mhchem).
String canonicalize(String text, {bool chemistry = true}) {
  if (text.isEmpty) return text;
  if (_url.hasMatch(text)) return text;

  final imageStash = <String>[];
  String stash(Match m) {
    imageStash.add(m[0]!);
    return _stashToken(imageStash.length - 1);
  }

  if (text.contains('{{IMAGE:')) {
    text = text.replaceAllMapped(_imageMarker, stash);
  }
  // A URL embedded in prose ("see https://…/a_b.png") is stashed the same
  // way: `_wrapBareScripts` would otherwise read `a_b` as a subscript.
  if (text.contains('://')) text = text.replaceAllMapped(_embeddedUrl, stash);

  text = repair(text);
  text = _stashEscapedDollars(text);
  text = _escapeCurrency(text);
  text = _stashEscapedDollars(text);
  text = fixMojibakeTable(text);
  text = normalizeHomoglyphs(text);
  text = _collapseDoubleBackslashes(text);
  text = _fixLeftRightBraces(text);
  text = _parenInline.replaceAllMapped(text, (m) => '\$${m[1]}\$');
  text = _bracketDisplay.replaceAllMapped(text, (m) => '\$\$${m[1]}\$\$');
  text = trimPaddedSpansInText(text);
  text = _closeUnbalancedBraces(text);
  text = _normalizeBraces(text);
  text = unicodeMathToLatex(text);
  text = convertCombiningVec(text);
  text = wrapBareUnicodeMath(text);
  text = _wrapBareLatexCommands(text);
  text = _wrapBareScripts(text);
  text = _wrapPureMathShortStrings(text, chemistry: chemistry);
  // Step 14 left the symbols inside bare script / command argument groups
  // (`e^{iπ}`, `\frac{π}{2}`) to steps 15–17, which put the whole group in
  // one span. A group none of them took is prose; its symbols are wrapped
  // now, on their own, as step 14 would have (step 17a).
  text = wrapBareUnicodeMath(text, skipAttachedGroups: false);
  // The wrapping steps create new spans whose content the span-only steps
  // (brace normalisation, Unicode → LaTeX) have not seen: `\text{H₂O}`
  // became `$\text{H₂O}$` and only a second run produced `$\text{H_{2}O}$`.
  // Running those two steps once more makes one pass equal to two.
  text = _normalizeBraces(text);
  text = unicodeMathToLatex(text);
  text = text.replaceAll(_escapedDollarSentinel, r'\$');
  // Restore last-stashed first: a URL stashed after an image marker may
  // contain that marker's token (`gs://{{IMAGE:x}}`).
  for (var idx = imageStash.length - 1; idx >= 0; idx--) {
    text = text.replaceAll(_stashToken(idx), imageStash[idx]);
  }
  return text;
}

/// [canonicalize] over every content string in a JSON-like document.
///
/// Skips non-content keys and URL-shaped values (CONTRACT §5); list items
/// inherit the parent key. Anything that is not a string, map or list is
/// returned as is.
Object? canonicalizeDeep(
  Object? obj, {
  String keyHint = '',
  bool chemistry = true,
}) {
  if (obj is String) {
    if (isNonContentKey(keyHint) || isUrlOrPathString(obj)) return obj;
    return canonicalize(obj, chemistry: chemistry);
  }
  if (obj is Map) {
    return mapValuesWithKey(
      obj,
      // A non-string key is never a non-content key (Python passes it to
      // `is_non_content_key`, which answers False).
      (k, v) => canonicalizeDeep(
        v,
        keyHint: k is String ? k : '',
        chemistry: chemistry,
      ),
    );
  }
  if (obj is List) {
    return <Object?>[
      for (final v in obj)
        canonicalizeDeep(v, keyHint: keyHint, chemistry: chemistry)
    ];
  }
  return obj;
}

/// [mapValues] with the key handed to the callback.
Map<Object?, Object?> mapValuesWithKey(
  Map<Object?, Object?> obj,
  Object? Function(Object? key, Object? value) f,
) {
  if (obj.keys.every((k) => k is String)) {
    return <String, Object?>{
      for (final e in obj.entries) e.key as String: f(e.key, e.value),
    };
  }
  return <Object?, Object?>{
    for (final e in obj.entries) e.key: f(e.key, e.value),
  };
}
