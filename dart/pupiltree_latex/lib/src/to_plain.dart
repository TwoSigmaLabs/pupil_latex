/// `toPlain`: LaTeX to plain Unicode text for PDFs, canvases, grading and
/// TTS. Port of `python/pupiltree_latex/to_plain.py` (Backend
/// `services/baa_render_meta.latex_to_plain` for the `text` / `pdf` styles,
/// the agents' `_clean_script_for_tts` for `tts`).
library;

import 'guarded_regexp.dart';
import 'mojibake.dart'
    show fixMojibakeCore, fixMojibakeTable, unescapeHtmlEntities;
import 'nfc.dart';
import 'normalize.dart' show currencyPositions, trimPaddedSpansKeepCurrency;
import 'repair.dart';
import 'segment.dart';
import 'spans.dart';
import 'tables.g.dart';
import 'text_util.dart';

const _superscriptChars = '0123456789+-=()ni';
const _superscriptForms = '\u2070\u00B9\u00B2\u00B3\u2074\u2075\u2076\u2077'
    '\u2078\u2079\u207A\u207B\u207C\u207D\u207E\u207F\u2071';
const _subscriptChars = '0123456789+-=()aeoxhklmnpst';
const _subscriptForms = '\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087'
    '\u2088\u2089\u208A\u208B\u208C\u208D\u208E\u2090\u2091\u2092\u2093\u2095'
    '\u2096\u2097\u2098\u2099\u209A\u209B\u209C';

/// Python's `str.maketrans` tables as maps (code point → replacement).
Map<String, String> _translationTable(String from, String to) => {
      for (var i = 0; i < from.length; i++) from[i]: to[i],
    };

final _superscriptMap = _translationTable(_superscriptChars, _superscriptForms);
final _subscriptMap = _translationTable(_subscriptChars, _subscriptForms);

/// `str.translate`: untranslatable characters fall through.
String _translate(String s, Map<String, String> table) {
  final out = StringBuffer();
  for (final r in s.runes) {
    final ch = String.fromCharCode(r);
    out.write(table[ch] ?? ch);
  }
  return out.toString();
}

// `\{`, `\}` and `\$` are literal characters, not grouping or maths
// delimiters. They are parked as sentinels for the duration of the
// transform so neither the delimiter passes nor the brace scanner can
// consume them, then restored. Single private-use characters (U+E010 to
// U+E014): one code unit, so an argument reader can never take half of one.
const _lbraceSentinel = '\uE010';
const _rbraceSentinel = '\uE011';
const _dollarSentinel = '\uE012';
const _labelSentinelOpen = '\uE013';
const _labelSentinelClose = '\uE014';

// A lesson-script label at the start of a line (`\instruction:`): parked
// before the command scanner, which read `\instruction` as `\in` +
// "struction". `text` keeps it verbatim; `pdf` and `compare` drop the
// backslash.
final _scriptLabelLine = RegExp(r'(^|\n)([ \t]*)\\([a-z][a-z_]*):');
// Anywhere in a line, only a word in `kScriptLabels` is a label.
final _scriptLabelAny = RegExp(r'\\([a-z][a-z_]*):');

// Math spans for the prose-brace pass, display first.
final _plainSpan = RegExp(r'\$\$[\s\S]+?\$\$|\$[^$]+\$');
final _simpleFractionPart = RegExp(
  r'^(?:[0-9]+(?:\.[0-9]+)?|[\p{L}\p{Nl}\p{No}])$',
  unicode: true,
);
// A negative number is a simple NUMERATOR too: `\frac{-1}{4}` → `-1/4`
// (tag `v140-a5`); a negative denominator keeps its parentheses (`1/(-4)`).
final _signedNumber = RegExp('^[-−][0-9]+(?:\\.[0-9]+)?\$');

/// Index of the `}` closing the `{` at [k], or -1. Positions marked in
/// [skip] (math spans) are not counted.
int _matchingBrace(String s, int k, [List<bool>? skip]) {
  var depth = 0;
  for (var j = k; j < s.length; j++) {
    if (skip != null && skip[j]) continue;
    if (s[j] == '{') {
      depth++;
    } else if (s[j] == '}') {
      depth--;
      if (depth == 0) return j;
    }
  }
  return -1;
}

bool _isAsciiLetterUnit(int c) =>
    (c >= 0x61 && c <= 0x7A) || (c >= 0x41 && c <= 0x5A);

/// The name of the `\name` whose last letter is `s[end - 1]`, or null.
String? _commandNameEndingAt(String s, int end) {
  var j = end;
  while (j > 0 && _isAsciiLetterUnit(s.codeUnitAt(j - 1))) {
    j--;
  }
  if (j < end && j > 0 && s[j - 1] == r'\') return s.substring(j, end);
  return null;
}

/// True when the `{` at [k] is a command or script argument.
bool _attachedBrace(String s, int k, Set<int> closes) {
  if (k == 0) return false;
  final prev = s[k - 1];
  if (prev == '^' || prev == '_' || closes.contains(k - 1)) return true;
  if (prev == ']') {
    if (k < 2) return false;
    final opener = s.lastIndexOf('[', k - 2);
    return opener > 0 && _commandNameEndingAt(s, opener) != null;
  }
  if (prev == ' ' || prev == '\t') {
    var j = k - 1;
    while (j > 0 && (s[j - 1] == ' ' || s[j - 1] == '\t')) {
      j--;
    }
    return _argumentTakingCmds.contains(_commandNameEndingAt(s, j));
  }
  return _commandNameEndingAt(s, k) != null;
}

// A prose brace pair is a literal set / JSON object when its content holds
// one of these (a list or key separator).
const _literalBraceHints = ',:;|';

/// Braces in prose (outside `$…$`/`$$…$$`, not a command or script
/// argument) whose content is a list or object are text: parked as the
/// `\{`/`\}` sentinels. `1{,}000` and `{x}` stay grouping; an unclosed `{`
/// is kept.
String _protectProseBraces(String s) {
  if (!s.contains('{')) return s;
  final n = s.length;
  final inMath = List<bool>.filled(n, false);
  for (final m in _plainSpan.allMatches(s)) {
    for (var j = m.start; j < m.end; j++) {
      inMath[j] = true;
    }
  }
  final chars = s.split('');
  final closes = <int>{};
  var k = 0;
  while (k < n) {
    if (inMath[k] || s[k] != '{') {
      k++;
      continue;
    }
    final close = _matchingBrace(s, k, inMath);
    if (_attachedBrace(s, k, closes)) {
      if (close == -1) break;
      closes.add(close);
      k = close + 1;
      continue;
    }
    if (close == -1) {
      chars[k] = _lbraceSentinel;
      k++;
      continue;
    }
    final inner = s.substring(k + 1, close);
    if (cpLength(inner) <= 1 ||
        !inner.split('').any(_literalBraceHints.contains)) {
      k = close + 1; // `{,}`, `{x}`: grouping
      continue;
    }
    chars[k] = _lbraceSentinel;
    chars[close] = _rbraceSentinel;
    k++;
  }
  return chars.join();
}

/// A numerator or denominator: a single token (a number or one letter)
/// or one parenthesised group stays bare; anything compound gets
/// parentheses.
String _fractionPart(String part, {bool numerator = false}) {
  final core = pyStrip(part);
  if (numerator && _signedNumber.hasMatch(core)) return core;
  if (_simpleFractionPart.hasMatch(core) || _isWrapped(core)) return core;
  return '($part)';
}

/// The last code point of [s], or ''.
String _lastCodePoint(String s) {
  if (s.isEmpty) return '';
  final r = s.runes.last;
  return String.fromCharCode(r);
}

/// A fraction touching a term is parenthesised (`2(1/2)`, `(1/2)x`).
bool _fractionNeedsParens(String prev, String s, int i) {
  var nxt = i < s.length ? codePointAt(s, i) : '';
  // A closing `\)` / `\]` ends the formula; it is not a term (`v140-a3`).
  if (nxt == r'\' && i + 1 < s.length && (s[i + 1] == ')' || s[i + 1] == ']')) {
    nxt = '';
  }
  return (prev.isNotEmpty && (isAlnum(prev) || prev == '/')) ||
      (nxt.isNotEmpty && (isAlnum(nxt) || '(\\^_{'.contains(nxt)));
}

final _imageMarker = RegExp(r'\{\{IMAGE:[^}]+\}\}');
// `$5`, `$1,200.50`: a dollar before an amount that is not followed by a
// letter, a command or a script (`$45m`, `$4\sqrt{3}` are cut-off spans).
final _currencyAt = RegExp(r'\$[0-9]+(?:[.,][0-9]+)*(?![0-9A-Za-z\\^_{])');

/// Park the amounts (tag `audit5-1`): a dollar outside every `segment` math
/// span that `escapeCurrency` reads as money (`Rs $5 and $10`: the closer
/// is followed by a digit; `costs $5.`: no closer) and that is followed by
/// an amount, not by a letter or a command (`$45m`, `$4\sqrt3` are cut-off
/// spans). It becomes the literal-dollar sentinel, so the delimiter strip
/// can no longer pair it with another amount.
String _parkCurrencyDollars(String s) {
  if (!s.contains(r'$')) return s;
  final money = currencyPositions(s);
  if (money.isEmpty) return s;
  final inMath = mathMask(s);
  final chars = s.split('');
  for (final k in money) {
    if (!inMath[k] && _currencyAt.matchAsPrefix(s, k) != null) {
      chars[k] = _dollarSentinel;
    }
  }
  return chars.join();
}

// (`\$5\)` is an amount inside `\(…\)`: a closing delimiter is not a unit.)
final _escapedCutOffDollar =
    RegExp(r'\\\$(?=[0-9]+(?:[.,][0-9]+)*(?:[A-Za-z^_{]|\\[A-Za-z]))');

const _subscriptDigits = '₀₁₂₃₄₅₆₇'
    '₈₉';

bool _isAsciiWordChar(String ch) {
  if (ch.isEmpty) return false;
  final c = ch.codeUnitAt(0);
  return (c >= 0x61 && c <= 0x7A) ||
      (c >= 0x41 && c <= 0x5A) ||
      (c >= 0x30 && c <= 0x39) ||
      c == 0x5F;
}

bool _isDigitAt(String s, int i) {
  if (i >= s.length) return false;
  final c = s.codeUnitAt(i);
  return c >= 0x30 && c <= 0x39;
}

bool _isUpperAt(String s, int i) {
  if (i >= s.length) return false;
  final c = s.codeUnitAt(i);
  return c >= 0x41 && c <= 0x5A;
}

bool _isLowerAt(String s, int i) {
  if (i >= s.length) return false;
  final c = s.codeUnitAt(i);
  return c >= 0x61 && c <= 0x7A;
}

/// A digit subscript at [i] (`_2`, `_{12}`): its digits and the index after.
(String, int) _chemDigits(String s, int i) {
  if (i >= s.length || s[i] != '_') return ('', i);
  final j = i + 1;
  if (j < s.length && s[j] == '{') {
    var k = j + 1;
    while (_isDigitAt(s, k)) {
      k++;
    }
    if (k > j + 1 && k < s.length && s[k] == '}') {
      return (s.substring(j + 1, k), k + 1);
    }
    return ('', i);
  }
  var k = j;
  while (_isDigitAt(s, k)) {
    k++;
  }
  return k > j ? (s.substring(j, k), k) : ('', i);
}

/// Index after the element symbol at [i] (two letters first), or -1.
int _chemElement(String s, int i) {
  if (!_isUpperAt(s, i)) return -1;
  if (_isLowerAt(s, i + 1) && kElementSymbols.contains(s.substring(i, i + 2))) {
    return i + 2;
  }
  if (kElementSymbols.contains(s[i])) return i + 1;
  return -1;
}

/// Element symbols, `(…)` groups and digit subscripts from [i]: the
/// converted text, the end index and the number of subscripts.
(String, int, int) _chemToken(String s, int i, [int depth = 0]) {
  final out = StringBuffer();
  var subs = 0;
  while (i < s.length) {
    if (s[i] == '(' && depth == 0) {
      final (inner, j, innerSubs) = _chemToken(s, i + 1, 1);
      if (inner.isEmpty || j >= s.length || s[j] != ')') break;
      out.write('($inner)');
      subs += innerSubs;
      i = j + 1;
    } else {
      final j = _chemElement(s, i);
      if (j < 0) break;
      out.write(s.substring(i, j));
      i = j;
    }
    final (digits, j) = _chemDigits(s, i);
    if (digits.isNotEmpty) {
      for (final unit in digits.codeUnits) {
        out.write(_subscriptDigits[unit - 0x30]);
      }
      subs++;
      i = j;
    }
  }
  return (out.toString(), i, subs);
}

/// `H_2SO_4` → `H₂SO₄`, `Ca(OH)_2` → `Ca(OH)₂` in prose (tag `v140-a9`).
/// A run of element symbols ([kElementSymbols]) and `(…)` groups with digit
/// subscripts, at least one; no ASCII letter, digit, `_` or `\` before it,
/// no ASCII letter, digit or `_` after it, never inside a math span. So
/// `lo_0`, `v_avg`, `E_1`, `fallback_factual_error` and `XH_2O_id` stay.
String bareChemistryToUnicode(String text) {
  if (!text.contains('_')) return text;
  List<bool>? mask;
  final out = StringBuffer();
  var last = 0;
  var changed = false;
  var i = 0;
  final n = text.length;
  while (i < n) {
    if (!(_isUpperAt(text, i) || text[i] == '(')) {
      i++;
      continue;
    }
    final prev = i > 0 ? text[i - 1] : '';
    if (prev.isNotEmpty && (_isAsciiWordChar(prev) || prev == r'\')) {
      i++;
      continue;
    }
    final (converted, end, subs) = _chemToken(text, i);
    final nxt = end < n ? text[end] : '';
    if (subs == 0 || _isAsciiWordChar(nxt)) {
      i++;
      continue;
    }
    mask ??= mathMask(text);
    if (mask[i]) {
      i = end;
      continue;
    }
    out
      ..write(text.substring(last, i))
      ..write(converted);
    last = i = end;
    changed = true;
  }
  if (!changed) return text;
  out.write(text.substring(last));
  return out.toString();
}

final _displayDollar = RegExp(r'\$\$(.+?)\$\$', dotAll: true);
final _delim = RegExp(r'\$([^$]+)\$');
// A literal `\n` escape that survived into the stored string. Only fires
// before an uppercase letter or whitespace, so the real commands that start
// with "n" (\nu, \neq, \nabla, \notin) are untouched.
final _newlineEscape = RegExp('\\\\n(?=[A-Z$pyWs]|\$)');

// A control word. A run of backslashes before the letters is one command: a
// double-escaped `\\frac` is the same fraction, not a line break + "frac".
final _cmd = RegExp(r'\\+([A-Za-z]+)');
final _envToken = RegExp('\\\\(begin|end)$pyS*\\{([^{}]*)\\}');

const _fracCmds = {'frac', 'dfrac', 'tfrac', 'cfrac'};
const _binomCmds = {'binom', 'dbinom', 'tbinom'};
// Wrappers whose only job is styling or chemistry markup — the inner
// content is the answer.
const _wrapperCmds = {
  'text', 'textit', 'textbf', 'textrm', 'textsf', 'texttt', 'textsc',
  'textup', 'textnormal', 'mathrm', 'mathit', 'mathbf', 'mathsf', 'mathtt',
  'mathbb', 'mathcal', 'mathfrak', 'mathscr', 'boldsymbol', 'bm',
  'operatorname', 'emph', 'mbox', 'hbox', 'ce',
  // Boxes, strikes and braces around content: the content is the answer.
  'boxed', 'fbox', 'cancel', 'bcancel', 'xcancel', 'sout', 'underbrace',
  'overbrace', 'pu',
};
// `\color{red}{5}` / `\textcolor{red}{5}`: the colour name is styling and
// the second argument is the content. `\color{red} 5` keeps what follows.
const _colorCmds = {'color', 'textcolor', 'colorbox'};
// Layout with no reading value: the command AND its argument go.
const _dropWithArgCmds = {
  'hspace',
  'vspace',
  'phantom',
  'hphantom',
  'vphantom',
  'label',
  'tag',
  'kern',
  'mkern',
  'mspace',
  'hskip',
};
// Accents: (combining mark, name). By default the base symbol is kept and
// the accent dropped; the `pdf` style asks for `markAccents`.
final _accentCmds = <String, (String, String)>{
  'vec': (u(0x20D7), 'vec'),
  'overrightarrow': (u(0x20D7), 'vec'),
  'overleftarrow': (u(0x20D6), 'vec'),
  'hat': (u(0x0302), 'hat'),
  'widehat': (u(0x0302), 'hat'),
  'bar': (u(0x0304), 'bar'),
  'overline': (u(0x0305), 'bar'),
  'dot': (u(0x0307), 'dot'),
  'ddot': (u(0x0308), 'ddot'),
  'tilde': (u(0x0303), 'tilde'),
  'widetilde': (u(0x0303), 'tilde'),
};
const _plainAccentCmds = {
  'check',
  'breve',
  'acute',
  'grave',
  'underline',
  'mathring',
};
// `\left.` / `\right.` are invisible delimiters; every sizing command is
// dropped and the delimiter it sizes kept.
const _sizingCmds = {
  'left',
  'right',
  'big',
  'Big',
  'bigg',
  'Bigg',
  'bigl',
  'bigr',
  'Bigl',
  'Bigr',
  'biggl',
  'biggr',
  'Biggl',
  'Biggr',
  'middle',
};
const _dropCmds = {
  'hline',
  'nonumber',
  'notag',
  'textstyle',
  'scriptstyle',
  'displaystyle',
  'scriptscriptstyle',
};
// Commands whose `{…}` argument may follow after spaces (prose-brace pass).
final _argumentTakingCmds = <String?>{
  ..._fracCmds,
  ..._binomCmds,
  ..._wrapperCmds,
  ..._colorCmds,
  ..._dropWithArgCmds,
  ..._accentCmds.keys,
  ..._plainAccentCmds,
  'sqrt',
  'begin',
  'end',
};

const _matrixEnvs = <String, (String, String)>{
  'matrix': ('[', ']'),
  'pmatrix': ('[', ']'),
  'bmatrix': ('[', ']'),
  'Bmatrix': ('[', ']'),
  'smallmatrix': ('[', ']'),
  'array': ('[', ']'),
  'vmatrix': ('|', '|'),
  'Vmatrix': ('\u2016', '\u2016'),
};
// Characters that read correctly as a superscript without a Unicode script
// form: primes and the degree sign (`0^\circ` → `0°`).
const _scriptPassthrough = '\u00B0\u2032\u2033\u2034';
final _singleToken =
    RegExp(r'^(?:[0-9]+(?:\.[0-9]+)?|.)$', dotAll: true, unicode: true);
final _scriptSpace = RegExp('$pyS*([^$pyW$pyWs])$pyS*', unicode: true);

// NOT stripping the space after a command is deliberate: by the time this
// runs the `$...$` delimiters are already gone, so a space that was OUTSIDE
// the maths cannot be told from one inside it.

/// `s[i]` is `{`: the balanced inner text (any depth) and the index after
/// its closing brace. An unclosed group runs to the end.
(String, int) _readGroup(String s, int i) {
  var depth = 0;
  for (var j = i; j < s.length; j++) {
    if (s[j] == '{') {
      depth++;
    } else if (s[j] == '}') {
      depth--;
      if (depth == 0) return (s.substring(i + 1, j), j + 1);
    }
  }
  return (s.substring(i + 1), s.length);
}

/// One macro argument at [i] (leading spaces skipped, as in LaTeX): a
/// braced group, a control word, or a single character.
(String?, int) _readArg(String s, int i) {
  var j = i;
  while (j < s.length && (s[j] == ' ' || s[j] == '\t')) {
    j++;
  }
  if (j >= s.length || s[j] == '}') return (null, i);
  if (s[j] == '{') return _readGroup(s, j);
  final m = _cmd.matchAsPrefix(s, j);
  if (m != null) return (m[0], m.end);
  final cp = codePointAt(s, j);
  return (cp, j + cp.length);
}

/// True when [body] is one parenthesised group: "(a+b)", not "(a)/(b)".
bool _isWrapped(String body) {
  if (!(body.startsWith('(') && body.endsWith(')'))) return false;
  var depth = 0;
  for (var k = 0; k < body.length; k++) {
    final ch = body[k];
    if (ch == '(') depth++;
    if (ch == ')') depth--;
    if (depth == 0 && k < body.length - 1) return false;
  }
  return depth == 0;
}

bool _allIn(String body, String chars) =>
    body.runes.every((r) => chars.contains(String.fromCharCode(r)));

/// Render a converted sub/superscript body. Unicode script characters only
/// when EVERY character has one — a half-converted "vₐvg" reads as a
/// different word — otherwise `_x` / `_(avg)`.
String _script(String body, String marker) {
  body = pyStrip(body.replaceAllMapped(_scriptSpace, (m) => m[1]!));
  if (body.isEmpty) return '';
  final chars = marker == '^' ? _superscriptChars : _subscriptChars;
  final table = marker == '^' ? _superscriptMap : _subscriptMap;
  if (marker == '^' && _allIn(body, _scriptPassthrough)) return body;
  if (_allIn(body, chars)) return _translate(body, table);
  if (cpLength(body) == 1) return '$marker$body';
  return '$marker($body)';
}

/// Split an environment body into rows (`\\`) of cells (`&`) at the top
/// level — separators inside braces or a nested environment belong to that
/// inner construct.
List<List<String>> _splitTable(String content) {
  final rows = <List<String>>[];
  var cells = <String>[];
  var buf = StringBuffer();
  var depth = 0;
  var envDepth = 0;
  var i = 0;
  final n = content.length;
  while (i < n) {
    final c = content[i];
    if (c == r'\') {
      final m = _envToken.matchAsPrefix(content, i);
      if (m != null) {
        envDepth += m[1] == 'begin' ? 1 : -1;
        buf.write(m[0]);
        i = m.end;
        continue;
      }
      if (content.startsWith(r'\\', i) && depth == 0 && envDepth == 0) {
        cells.add(buf.toString());
        rows.add(cells);
        cells = <String>[];
        buf = StringBuffer();
        i += 2;
        continue;
      }
      // Copy the escape whole so an escaped "\&" is never split on.
      buf.write(content.substring(i, i + 2 > n ? n : i + 2));
      i += 2;
      continue;
    }
    if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth--;
    } else if (c == '&' && depth == 0 && envDepth == 0) {
      cells.add(buf.toString());
      buf = StringBuffer();
      i++;
      continue;
    }
    buf.write(c);
    i++;
  }
  cells.add(buf.toString());
  rows.add(cells);
  return rows;
}

/// `pmatrix` → `[a b; c d]`, `vmatrix` → `|a b; c d|`, `cases` →
/// `a, x>0; b, x≤0`; any other environment → rows joined by "; " with the
/// alignment points dropped.
String _environment(String name, String content, bool markAccents) {
  final base = name.replaceFirst(RegExp(r'\*+$'), '');
  if (base == 'array') {
    var k = 0;
    while (k < content.length && (content[k] == ' ' || content[k] == '\t')) {
      k++;
    }
    if (k < content.length && content[k] == '{') {
      content = content.substring(_readGroup(content, k).$2);
    }
  }
  final rows = <List<String>>[];
  for (final rawCells in _splitTable(content)) {
    final cells = [
      for (final cell in rawCells) pyStrip(_convert(cell, markAccents)),
    ];
    if (cells.any((c) => c.isNotEmpty)) rows.add(cells);
  }
  if (_matrixEnvs.containsKey(base)) {
    final (opener, closer) = _matrixEnvs[base]!;
    final body =
        rows.map((row) => row.where((c) => c.isNotEmpty).join(' ')).join('; ');
    return '$opener$body$closer';
  }
  final joiner = base == 'cases' ? ', ' : '';
  return rows
      .map((row) => row.where((c) => c.isNotEmpty).join(joiner))
      .join('; ');
}

/// Render control word `\name` whose arguments start at [j]. Returns the
/// text and the index after everything consumed.
(String, int) _command(String name, String s, int j, bool markAccents) {
  if (_fracCmds.contains(name) || _binomCmds.contains(name)) {
    final (num, j1) = _readArg(s, j);
    final (den, j2) = _readArg(s, j1);
    final a = _convert(num ?? '', markAccents);
    final b = _convert(den ?? '', markAccents);
    if (_fracCmds.contains(name)) {
      return ('${_fractionPart(a, numerator: true)}/${_fractionPart(b)}', j2);
    }
    return ('C($a, $b)', j2);
  }
  if (name == 'sqrt') {
    var k = j;
    while (k < s.length && (s[k] == ' ' || s[k] == '\t')) {
      k++;
    }
    var root = '\u221A';
    if (k < s.length && s[k] == '[') {
      final close = s.indexOf(']', k);
      if (close != -1) {
        final index = pyStrip(_convert(s.substring(k + 1, close), markAccents));
        j = close + 1;
        if (index.isNotEmpty && _allIn(index, _superscriptChars)) {
          root = '${_translate(index, _superscriptMap)}\u221A';
        } else if (index.isNotEmpty) {
          root = '($index)\u221A';
        }
      }
    }
    final (arg, j1) = _readArg(s, j);
    final body = _convert(arg ?? '', markAccents);
    if (body.isEmpty || _singleToken.hasMatch(body) || _isWrapped(body)) {
      return ('$root$body', j1);
    }
    return ('$root($body)', j1);
  }
  if (_wrapperCmds.contains(name)) {
    final (arg, j1) = _readArg(s, j);
    return (_convert(arg ?? '', markAccents), j1);
  }
  if (_colorCmds.contains(name)) {
    final (_, j1) = _readArg(s, j);
    var k = j1;
    while (k < s.length && (s[k] == ' ' || s[k] == '\t')) {
      k++;
    }
    if (k < s.length && s[k] == '{') {
      final (arg, j2) = _readArg(s, j1);
      return (_convert(arg ?? '', markAccents), j2);
    }
    return ('', j1);
  }
  if (_dropWithArgCmds.contains(name)) {
    final (_, j1) = _readArg(s, j);
    return ('', j1);
  }
  if (_accentCmds.containsKey(name) || _plainAccentCmds.contains(name)) {
    final (arg, j1) = _readArg(s, j);
    final body = _convert(arg ?? '', markAccents);
    if (!markAccents || _plainAccentCmds.contains(name) || body.isEmpty) {
      return (body, j1);
    }
    final (combining, label) = _accentCmds[name]!;
    if (cpLength(body) == 1) return ('$body$combining', j1);
    return ('$label($body)', j1);
  }
  if (_sizingCmds.contains(name)) {
    if (j < s.length && s[j] == '.') j++;
    return ('', j);
  }
  if (_dropCmds.contains(name)) return ('', j);
  if (name == 'begin') {
    final (arg, k) = _readArg(s, j);
    if (arg == null ||
        !s
            .substring(j, k)
            .replaceFirst(RegExp(r'^[ \t]+'), '')
            .startsWith('{')) {
      return ('', j);
    }
    final env = pyStrip(arg);
    var depth = 1;
    for (final m in _envToken.allMatches(s, k)) {
      if (pyStrip(m[2]!) != env) continue;
      depth += m[1] == 'begin' ? 1 : -1;
      if (depth == 0) {
        return (_environment(env, s.substring(k, m.start), markAccents), m.end);
      }
    }
    return (_environment(env, s.substring(k), markAccents), s.length);
  }
  if (name == 'end') {
    final (arg, k) = _readArg(s, j);
    return ('', arg != null ? k : j);
  }
  if (kLatexCmdMap.containsKey(name)) return (kLatexCmdMap[name]!, j);
  // A real KaTeX command that is not in the map keeps its name as text
  // (`\intercal` → "intercal"); it is never split (`\neg` is not `\ne` + g).
  if (kKatexCommands.contains(name)) return (name, j);
  // `\cmd` written without a separator before the next word runs into it,
  // because the command scanner is greedy: `\colonN` matches as one command
  // named "colonN". Peel the longest known command off the front and keep
  // the remainder as text. Minimum length 2 so a stray `\cm` isn't split on
  // a one-letter name. Unknown commands lose the backslash (\foo → foo).
  for (var cut = name.length - 1; cut > 1; cut--) {
    final head = name.substring(0, cut);
    if (kLatexCmdMap.containsKey(head)) {
      return ('${kLatexCmdMap[head]!}${name.substring(cut)}', j);
    }
  }
  return (name, j);
}

/// Single left-to-right pass over maths text. Arguments are read with a
/// balanced-brace scanner and converted recursively, so nesting depth is
/// unbounded.
/// Nesting deeper than this is pathological (Python raises `RecursionError`
/// at about the same point); [latexToPlain] then falls back to a flat strip.
const _maxDepth = 480;
var _depth = 0;

class _TooDeep implements Exception {}

/// Single left-to-right pass over maths text (see [_convertInner]); every
/// recursive entry is counted so unbounded nesting cannot overflow the
/// stack.
String _convert(String s, bool markAccents) {
  if (_depth >= _maxDepth) throw _TooDeep();
  _depth++;
  try {
    return _convertInner(s, markAccents);
  } finally {
    _depth--;
  }
}

String _convertInner(String s, bool markAccents) {
  final out = _TrackedBuffer();
  var i = 0;
  final n = s.length;
  while (i < n) {
    final c = s[i];
    if (c == r'\') {
      final m = _cmd.matchAsPrefix(s, i);
      if (m != null) {
        var (piece, next) = _command(m[1]!, s, m.end, markAccents);
        if (_fracCmds.contains(m[1]!) &&
            _fractionNeedsParens(out.lastChar, s, next)) {
          piece = '($piece)';
        }
        out.write(piece);
        i = next;
        continue;
      }
      final nxt = i + 1 < n ? s[i + 1] : '';
      if (nxt.isEmpty) {
        i++;
        continue;
      }
      if (',;:> '.contains(nxt) || nxt == r'\') {
        // Spacing commands and a `\\` line break read as one space.
        // `\!` is a NEGATIVE space and collapses to nothing.
        out.write(' ');
      } else if ('%&#_'.contains(nxt)) {
        out.write(nxt);
      }
      // `\(`, `\)`, `\[`, `\]` delimiters, `\!`, and an orphan backslash
      // ("\0.008Wb" residue) all render as nothing.
      i += r',;:> \%&#_!()[]'.contains(nxt) ? 2 : 1;
      continue;
    }
    if (c == '^' || c == '_') {
      var j = i + 1;
      final String raw;
      if (j < n && s[j] == '{') {
        (raw, j) = _readGroup(s, j);
      } else if (j < n && _cmd.matchAsPrefix(s, j) != null) {
        final m = _cmd.matchAsPrefix(s, j)!;
        (raw, j) = (m[0]!, m.end);
      } else if (j < n &&
          (isAlnum(codePointAt(s, j)) || s[j] == '+' || s[j] == '-')) {
        final cp = codePointAt(s, j);
        (raw, j) = (cp, j + cp.length);
      } else {
        out.write(c);
        i++;
        continue;
      }
      out.write(_script(_convert(raw, markAccents), c));
      i = j;
      continue;
    }
    if (c == '{') {
      final (raw, next) = _readGroup(s, i);
      out.write(_convert(raw, markAccents));
      i = next;
      continue;
    }
    if (c == '}') {
      // Unmatched closing brace: grouping residue, not content.
      i++;
      continue;
    }
    out.write(c);
    i++;
  }
  return out.toString();
}

/// A [StringBuffer] that remembers the last code point written (the
/// fraction rule looks at the character before a `\frac`).
class _TrackedBuffer {
  final _buf = StringBuffer();
  String lastChar = '';

  void write(String piece) {
    if (piece.isEmpty) return;
    _buf.write(piece);
    lastChar = _lastCodePoint(piece);
  }

  @override
  String toString() => _buf.toString();
}

final _multiSpace = RegExp(r'[ \t]{2,}');

/// Convert a LaTeX-math-laced string into plain text/Unicode (Backend
/// `latex_to_plain`). With [markAccents] a one-symbol accent argument gets
/// the combining mark (F⃗) and a longer one is named (vec(AB)).
String latexToPlain(
  String text, {
  bool markAccents = false,
  bool keepLabelBackslash = true,
  bool force = false,
  bool compare = false,
  bool bareChemistry = false,
}) {
  if (bareChemistry) text = bareChemistryToUnicode(text);
  if (!force &&
      !text.contains(r'$') &&
      !text.contains(r'\') &&
      !text.contains('{')) {
    return text;
  }

  var out = text;

  // `{{IMAGE:…}}` markers are not braces to strip: park them first.
  final imageStash = <String>[];
  if (out.contains('{{IMAGE:')) {
    out = out.replaceAllMapped(_imageMarker, (m) {
      imageStash.add(m[0]!);
      return '\x00IMG${imageStash.length - 1}\x00';
    });
  }

  // Amounts outside the `segment` math spans (`Rs $5 and $10`, `costs $5.`)
  // are literal dollars, never paired as a span (tag `audit5-1`).
  out = _parkCurrencyDollars(out);

  // `compare`: an escaped dollar before an amount that runs into a unit or
  // a command (`\$0.008Wb`, `\$4\sqrt{3}`) is a cut-off span's opener, not
  // money; `\$5`, `\$5 each` stay (tag `v140-a5`).
  if (compare && out.contains(r'\$')) {
    out = out.replaceAll(_escapedCutOffDollar, '');
  }

  // Literal `\n` escapes first — before the greedy command scanner can claim
  // them as `\nStatement`-style pseudo-commands.
  out = out.replaceAll(_newlineEscape, '\n');

  // Escaped braces and dollars are literal characters. Parked before the
  // delimiter passes and restored at the very end.
  out = out
      .replaceAll(r'\$', _dollarSentinel)
      .replaceAll(r'\{', _lbraceSentinel)
      .replaceAll(r'\}', _rbraceSentinel);

  // Lesson-script labels at a line start are not commands.
  final labels = <String>[];
  if (out.contains(r'\') && out.contains(':')) {
    out = out.replaceAllMapped(_scriptLabelLine, (m) {
      labels.add(m[3]!);
      return '${m[1]}${m[2]}$_labelSentinelOpen${labels.length - 1}'
          '$_labelSentinelClose:';
    });
    // A known label (`kScriptLabels`, the words `repair` restores) is a
    // label anywhere: `(<TAB>ool: timer)` became `\tool:`, which the
    // scanner read as `\to` + "ol" (tag `audit5-3`).
    out = out.replaceAllMapped(_scriptLabelAny, (m) {
      if (!kScriptLabels.contains(m[1])) return m[0]!;
      labels.add(m[1]!);
      return '$_labelSentinelOpen${labels.length - 1}$_labelSentinelClose:';
    });
  }

  // Braces in prose are text (`A = {1, 2, 3}`), not grouping.
  out = _protectProseBraces(out);

  // Pull maths out of `$$...$$` / `$...$` so the scanner below operates on
  // the inner content too. `\(...\)` / `\[...\]` are dropped by the scanner.
  out = out.replaceAllMapped(_displayDollar, (m) => m[1]!);
  out = out.replaceAllMapped(_delim, (m) => m[1]!);

  try {
    out = _convert(out, markAccents);
  } on _TooDeep {
    // Pathological nesting (hundreds of brace levels): fall back to a flat
    // strip so the caller still gets readable text.
    _depth = 0;
    out = out.replaceAll(_cmd, '').replaceAll('{', '').replaceAll('}', '');
  }

  // Collapse runs of spaces the substitutions introduced. Horizontal space
  // only: newlines carry meaning here.
  out = out.replaceAll(_multiSpace, ' ');

  // An UNPAIRED delimiter at either end ("$45m"). Bounded to a leading or
  // trailing dollar on an odd count, so a mid-string amount ("costs $5") is
  // left alone.
  if (r'$'.allMatches(out).length.isOdd) {
    if (out.startsWith(r'$')) {
      out = out.substring(1);
    } else if (out.endsWith(r'$')) {
      out = out.substring(0, out.length - 1);
    }
  }
  // `compare`: every span was stripped and amounts are parked, so a `$`
  // left now is an unpaired half (`3.2$ m` → `3.2 m`; tag `v140-a3`).
  if (compare) out = out.replaceAll(r'$', '');

  // Literal characters come back now that grouping and delimiters are done.
  out = out
      .replaceAll(_lbraceSentinel, '{')
      .replaceAll(_rbraceSentinel, '}')
      .replaceAll(_dollarSentinel, r'$');

  for (var idx = 0; idx < labels.length; idx++) {
    out = out.replaceAll(
      '$_labelSentinelOpen$idx$_labelSentinelClose',
      (keepLabelBackslash ? r'\' : '') + labels[idx],
    );
  }

  for (var idx = 0; idx < imageStash.length; idx++) {
    out = out.replaceAll('\x00IMG$idx\x00', imageStash[idx]);
  }

  // Compose accents where a precomposed character exists (`i` + U+0302 →
  // `î`) so PDF fonts draw one glyph; marks with no precomposed form (F⃗)
  // are left as they are.
  return nfcCompose(out);
}

// ---------------------------------------------------------------------------
// tts style (agents podcast_node / story_node `_clean_script_for_tts`)
// ---------------------------------------------------------------------------

const _spokenOperators = <(String, String)>[
  (r'\times', 'times'),
  (r'\div', 'divided by'),
  (r'\pm', 'plus or minus'),
  (r'\leq', 'less than or equal to'),
  (r'\geq', 'greater than or equal to'),
  (r'\neq', 'not equal to'),
  (r'\le', 'less than or equal to'),
  (r'\ge', 'greater than or equal to'),
  (r'\ne', 'not equal to'),
  (r'\cdot', 'times'),
  (r'\approx', 'approximately'),
  (r'\infty', 'infinity'),
  (r'\int', 'integral of'),
  (r'\sum', 'sum of'),
  // tag `v140-a8`
  (r'\ldots', 'dots'),
  (r'\cdots', 'dots'),
  (r'\dots', 'dots'),
  (r'\textellipsis', 'dots'),
  (r'\textmu', 'micro'),
];

final _spokenOperatorRe = RegExp(
  '\\\\(${_spokenOperators.map((e) => regexEscape(e.$1.substring(1))).join('|')})(?![A-Za-z])',
);
final _spokenOperatorWords = {
  for (final (cmd, word) in _spokenOperators) cmd.substring(1): word,
};
final _spokenCmd = RegExp(r'\\([A-Za-z]+)');
// Font and text wrappers: spoken as their content (`\text{cm}` → cm).
const _spokenWrappers = {
  'text',
  'textbf',
  'textit',
  'textrm',
  'textsf',
  'texttt',
  'textnormal',
  'textup',
  'textmd',
  'emph',
  'mathrm',
  'mathit',
  'mathbf',
  'mathsf',
  'mathtt',
  'mathbb',
  'mathcal',
  'mathfrak',
  'mathscr',
  'boldsymbol',
  'bm',
  'operatorname',
  'mbox',
  'hbox',
  'boxed',
  'fbox',
};
// mhchem: `\ce{H2O}` → "H 2 O".
const _spokenChemWrappers = {'ce', 'pu'};
// Sizing and style commands with nothing to say (`\left(` → "(").
const _spokenDropped = {
  'left',
  'right',
  'middle',
  'big',
  'Big',
  'bigg',
  'Bigg',
  'bigl',
  'bigr',
  'Bigl',
  'Bigr',
  'biggl',
  'biggr',
  'Biggl',
  'Biggr',
  'displaystyle',
  'textstyle',
  'scriptstyle',
  'scriptscriptstyle',
  'limits',
  'nolimits',
  'nonumber',
  'notag',
  'hline',
};
const _spokenSpaces = {'quad', 'qquad', 'enspace', 'thinspace', 'medspace'};
const _spokenDroppedWithArg = {
  'hspace',
  'vspace',
  'phantom',
  'hphantom',
  'vphantom',
  'label',
  'tag',
  'color',
};
const _spokenMatrixEnvs = {
  'matrix',
  'pmatrix',
  'bmatrix',
  'Bmatrix',
  'vmatrix',
  'Vmatrix',
  'smallmatrix',
};
final _chemText = RegExp(r'^[A-Z][A-Za-z()]*$');
final _chemCharge = RegExp(r'^([0-9]*)([+-])$');
final _chemCaret = RegExp(r'\^\{?([0-9]*)([+-])\}?');
final _chemSub = RegExp(r'_\{?([0-9]+)\}?');
final _chemCount = GuardedRegExp.after(r'A-Za-z)\]', '([0-9]+)');
final _needsParensRe = RegExp('[$pyWs+\\-=]');
final _commaRun = RegExp(',$pyS*,');

/// `H2O` / `H_2O` / `SO4^{2-}` → `H 2 O` / `SO 4 2 minus`.
String _spokenChem(String content) {
  content = content
      .replaceAll('<=>', ' is in equilibrium with ')
      .replaceAll('<->', ' is in equilibrium with ');
  content =
      content.replaceAll('->', ' gives ').replaceAll('<-', ' comes from ');
  content = content.replaceAllMapped(
    _chemCaret,
    (m) => ' ${m[1]!.isNotEmpty ? '${m[1]} ' : ''}'
        '${m[2] == '+' ? 'plus' : 'minus'} ',
  );
  content = content.replaceAllMapped(_chemSub, (m) => ' ${m[1]} ');
  content = _chemCount.replaceAllMapped(content, (m) => ' ${m[1]} ');
  return content.replaceAll('{', '').replaceAll('}', '');
}

bool _needsParens(String spoken) => _needsParensRe.hasMatch(pyStrip(spoken));

/// Python `str.isdigit()` for a whole string.
bool _allDigits(String s) =>
    s.isNotEmpty && s.runes.every((r) => isDigit(String.fromCharCode(r)));

/// Python `str.rstrip("*")`.
String _rstripStars(String s) {
  var e = s.length;
  while (e > 0 && s[e - 1] == '*') {
    e--;
  }
  return s.substring(0, e);
}

/// Spoken form of fractions, roots, wrappers, chemistry, environments and
/// escapes, read with balanced braces at any depth. Operators, Greek and
/// scripts are left for the word rules that run after.
String _spokenStructures(String s, {bool prose = false}) {
  final out = StringBuffer();
  var i = 0;
  final n = s.length;
  while (i < n) {
    final c = s[i];
    if (c == '&' && !prose) {
      out.write(' ');
      i++;
      continue;
    }
    if (c != r'\') {
      out.write(c);
      i++;
      continue;
    }
    if (s.startsWith(r'\\', i)) {
      out.write(' ');
      i += 2;
      continue;
    }
    final m = _spokenCmd.matchAsPrefix(s, i);
    if (m == null) {
      final nxt = i + 1 < n ? s[i + 1] : '';
      if (nxt == '%') {
        out.write(' percent ');
      } else if (nxt == '{') {
        out.write('(');
      } else if (nxt == '}') {
        out.write(')');
      } else if (nxt.isNotEmpty && '&#_\$'.contains(nxt)) {
        out.write(nxt);
      } else {
        out.write(' '); // \, \; \: \! \  and a lone backslash
      }
      i += 2;
      continue;
    }
    final name = m[1]!;
    var j = m.end;
    if (_fracCmds.contains(name)) {
      final (num, j1) = _readArg(s, j);
      j = j1;
      final (den, k) = _readArg(s, j);
      if (num == null || den == null) {
        out.write(' ');
        i = j;
        continue;
      }
      out.write(
        '(${pyStrip(_spokenStructures(num))} over '
        '${pyStrip(_spokenStructures(den))})',
      );
      i = k;
      continue;
    }
    if (name == 'sqrt') {
      var index = '';
      var k = j;
      while (k < n && (s[k] == ' ' || s[k] == '\t')) {
        k++;
      }
      if (k < n && s[k] == '[') {
        final close = s.indexOf(']', k);
        if (close != -1) {
          index = pyStrip(s.substring(k + 1, close));
          j = close + 1;
        }
      }
      final (arg, j1) = _readArg(s, j);
      j = j1;
      if (arg == null) {
        out.write(' square root ');
        i = j;
        continue;
      }
      var inner = pyStrip(_spokenStructures(arg));
      if (_needsParens(inner)) inner = '($inner)';
      final String phrase;
      if (index.isEmpty || index == '2') {
        phrase = 'square root of';
      } else if (index == '3') {
        phrase = 'cube root of';
      } else {
        phrase = '${index}th root of';
      }
      out.write('$phrase $inner');
      i = j;
      continue;
    }
    if (_spokenChemWrappers.contains(name)) {
      final (arg, j1) = _readArg(s, j);
      out.write(' ${_spokenChem(arg ?? '')} ');
      i = j1;
      continue;
    }
    if (_spokenWrappers.contains(name)) {
      final (rawArg, j1) = _readArg(s, j);
      j = j1;
      var arg = rawArg ?? '';
      if ((name == 'text' || name == 'mathrm') &&
          (arg.contains('_') || arg.contains('^'))) {
        arg = _spokenChem(arg); // `\mathrm{H_2O}`
      }
      final inner = _spokenStructures(arg);
      // `\text{H}_{2}\text{O}`, `\text{Fe}^{3+}`: an element read with its
      // count or charge.
      if (_chemText.hasMatch(pyStrip(inner))) {
        final spoken = <String>[pyStrip(inner)];
        while (j < n && (s[j] == '_' || s[j] == '^')) {
          final (script, k) = _readArg(s, j + 1);
          if (script == null) break;
          final charge = _chemCharge.firstMatch(script);
          if (s[j] == '_' && _allDigits(script)) {
            spoken.add(script);
          } else if (s[j] == '^' && charge != null) {
            if (charge[1]!.isNotEmpty) spoken.add(charge[1]!);
            spoken.add(charge[2] == '+' ? 'plus' : 'minus');
          } else {
            break;
          }
          j = k;
        }
        if (spoken.length > 1) {
          out.write(' ${spoken.join(' ')} ');
          i = j;
          continue;
        }
      }
      out.write(inner);
      i = j;
      continue;
    }
    if (name == 'begin') {
      final (envArg, j1) = _readArg(s, j);
      j = j1;
      final env = pyStrip(envArg ?? '');
      final endM = RegExp('\\\\end$pyS*\\{${regexEscape(env)}\\}')
          .allMatches(s, j)
          .firstOrNull;
      final bodyEnd = endM?.start ?? n;
      final after = endM?.end ?? n;
      if (env == 'array') {
        j = _readArg(s, j).$2; // column spec
      }
      final rows = [
        for (final row
            in _splitTable(s.substring(j, bodyEnd < j ? j : bodyEnd)))
          [
            for (final cell in row)
              if (pyStrip(_spokenStructures(cell)).isNotEmpty)
                pyStrip(_spokenStructures(cell)),
          ],
      ].where((row) => row.isNotEmpty).toList();
      final base = _rstripStars(env);
      if (_spokenMatrixEnvs.contains(base)) {
        out.write(
          ' matrix with rows ${rows.map((r) => r.join(', ')).join('; ')} ',
        );
      } else if (base == 'cases') {
        final cases = rows.map((r) => r.join(', ')).join('; ');
        out.write(' ${cases.replaceAll(_commaRun, ',')} ');
      } else {
        out.write(' ${rows.map((r) => r.join(' ')).join('; ')} ');
      }
      i = after;
      continue;
    }
    if (name == 'end') {
      i = _readArg(s, j).$2;
      continue;
    }
    if (_spokenDropped.contains(name)) {
      while (j < n && (s[j] == ' ' || s[j] == '\t')) {
        j++;
      }
      if (j < n && s[j] == '.') j++; // `\left.`
      i = j;
      continue;
    }
    if (_spokenSpaces.contains(name)) {
      out.write(' ');
      i = j;
      continue;
    }
    if (_spokenDroppedWithArg.contains(name)) {
      i = _readArg(s, j).$2;
      continue;
    }
    if (name == 'textcolor' || name == 'colorbox') {
      j = _readArg(s, j).$2;
      final (arg, j1) = _readArg(s, j);
      out.write(_spokenStructures(arg ?? ''));
      i = j1;
      continue;
    }
    // Operators, Greek, functions: the word rules below read them. A space
    // keeps `\alpha\text{x}` from becoming `\alphax`.
    out.write(m[0]!);
    if (j < n && s[j] == r'\') out.write(' ');
    i = j;
  }
  return out.toString();
}

/// `(a over b)` → `a over b` when ONE pair wraps the whole text.
String _stripOuterParens(String text) {
  if (!(text.startsWith('(') && text.endsWith(')'))) return text;
  var depth = 0;
  for (var k = 0; k < text.length; k++) {
    if (text[k] == '(') depth++;
    if (text[k] == ')') depth--;
    if (depth == 0 && k < text.length - 1) return text;
  }
  return text.substring(1, text.length - 1);
}

const _spokenBase = '([$pyW)\\]|])';
final _degrees = RegExp('\\^$pyS*\\{?$pyS*\\\\circ$pyS*\\}?');
final _squared = RegExp('$_spokenBase\\^(?:\\{2\\}|2)(?![0-9])', unicode: true);
final _cubed = RegExp('$_spokenBase\\^(?:\\{3\\}|3)(?![0-9])', unicode: true);
final _powerBraced = RegExp('$_spokenBase\\^\\{([^{}]+)\\}', unicode: true);
final _powerBare = RegExp('$_spokenBase\\^([$pyW])', unicode: true);
final _subBraced = RegExp('${_spokenBase}_\\{([^{}]+)\\}', unicode: true);
final _subBare = RegExp('${_spokenBase}_([$pyW])', unicode: true);
final _anyCommand = RegExp(r'\\([a-zA-Z]+)');
final _blanks = RegExp(r'[ \t]+');
final _openParenSpace = RegExp('\\($pyS+');
final _spaceCloseParen = RegExp('$pyS+\\)');
final _leftoverStructural = RegExp(
  '\\\\(?:frac|sqrt|sum|int|prod|lim|log|ln|sin|cos|tan)(?![$pyW])',
  unicode: true,
);
final _bold = RegExp(r'\*\*([^\n]+?)\*\*');
final _italic = RegExp(r'\*([^\n]+?)\*');
final _twoPlusSpaces = RegExp('  +');
final _threePlusNewlines = RegExp(r'\n{3,}');

final _spaceBeforeComma = RegExp(r' +([,;])');

String _latexToSpoken(String latex) {
  var text = _spokenStructures(pyStrip(latex));
  // `50^\circ C` → "50 degrees C": room on both sides (tag `v140-a8`).
  text = text.replaceAll(_degrees, ' degrees ');
  text = text.replaceAllMapped(_squared, (m) => '${m[1]} squared');
  text = text.replaceAllMapped(_cubed, (m) => '${m[1]} cubed');
  text = text.replaceAllMapped(
      _powerBraced, (m) => '${m[1]} to the power ${m[2]}');
  text =
      text.replaceAllMapped(_powerBare, (m) => '${m[1]} to the power ${m[2]}');
  text = text.replaceAllMapped(_subBraced, (m) => '${m[1]} sub ${m[2]}');
  text = text.replaceAllMapped(_subBare, (m) => '${m[1]} sub ${m[2]}');
  // Every command becomes a word with room around it (`4\pi` → "4 pi").
  text = text.replaceAllMapped(
    _spokenOperatorRe,
    (m) => ' ${_spokenOperatorWords[m[1]!]!} ',
  );
  text = text.replaceAllMapped(_anyCommand, (m) => ' ${m[1]} ');
  text = text.replaceAll('{', '').replaceAll('}', '').replaceAll(r'\', ' ');
  text = text.replaceAll(_blanks, ' ');
  text = text.replaceAll(_openParenSpace, '(');
  text = text.replaceAll(_spaceCloseParen, ')');
  // A word before a comma or semicolon (`\ldots,` → "dots,").
  text = text.replaceAllMapped(_spaceBeforeComma, (m) => m[1]!);
  return _stripOuterParens(pyStrip(text));
}

// A span whose whole body is typography is read as the character itself, so
// the voice pauses (`leukocytes$\ldots$` → "leukocytes…"; tag `v140-a8`).
const _spokenTypographicSpans = {
  r'\ldots': '…',
  r'\dots': '…',
  r'\cdots': '…',
  r'\textellipsis': '…',
  r'\textmu': 'micro',
};

// A bare single-letter subscript in prose (`x_{n}`, `a_1`): "x sub n". The
// base is one ASCII letter with no letter, digit, `_` or `\` before it, and
// the subscript must not run into a word, a superscript or a group (`v_avg`,
// `lo_0`, `H_2O`, `H_{2}O`, `x_0^2` and `fallback_factual_error` stay).
final _proseSubscript = RegExp(
  r'(^|[^A-Za-z0-9_\\])([A-Za-z])_(?:\{([A-Za-z0-9]+)\}|([A-Za-z0-9]))(?![A-Za-z0-9_^{])',
);

String _spokenProseSubscripts(String text) {
  if (!text.contains('_')) return text;
  return text.replaceAllMapped(
    _proseSubscript,
    (m) => '${m[1]}${m[2]} sub ${m[3] ?? m[4]}',
  );
}

// Bare `50^\circ C` / `50^{\circ}C` in prose (tag `v140-a8`).
final _proseDegrees = RegExp(r'\^[ \t]*\{?[ \t]*\\circ(?![A-Za-z])[ \t]*\}?');

String _spokenProseDegrees(String text) {
  if (!text.contains(r'\circ')) return text;
  return text.replaceAllMapped(
    _proseDegrees,
    (m) =>
        ' degrees'
        '${m.end < text.length && isAlnum(codePointAt(text, m.end)) ? ' ' : ''}',
  );
}

String _toSpoken(String text) {
  final parts = <String>[];
  for (final seg in segment(text)) {
    if (seg.isMath) {
      parts.add(_spokenTypographicSpans[pyStrip(seg.value)] ??
          _latexToSpoken(seg.value));
      continue;
    }
    var value = seg.value;
    // `$50^\circ$C`: a degrees span runs into a unit (tag `v140-a8`).
    if (parts.isNotEmpty &&
        parts.last.endsWith('degrees') &&
        value.isNotEmpty &&
        isAlnum(codePointAt(value, 0))) {
      value = ' $value';
    }
    value = _spokenProseDegrees(_spokenProseSubscripts(value));
    // Bare LaTeX in prose (`\frac{1}{2}` never wrapped): fractions, roots,
    // wrappers and environments are read the same way.
    parts.add(
      value.contains(r'\') ? _spokenStructures(value, prose: true) : value,
    );
  }
  var cleaned = parts.join();
  cleaned = cleaned.replaceAll(_leftoverStructural, '');
  cleaned = cleaned.replaceAllMapped(_anyCommand, (m) => m[1]!);
  cleaned = cleaned.replaceAllMapped(_bold, (m) => m[1]!);
  cleaned = cleaned.replaceAllMapped(_italic, (m) => m[1]!);
  cleaned = cleaned.replaceAll(_twoPlusSpaces, ' ');
  cleaned = cleaned.replaceAll(_threePlusNewlines, '\n\n');
  return pyStrip(cleaned);
}

/// The accepted [toPlain] styles.
const List<String> styles = ['text', 'pdf', 'tts', 'compare'];

final _superscriptToAscii = {
  for (var i = 0; i < _superscriptChars.length; i++)
    _superscriptForms[i]: _superscriptChars[i],
};
final _subscriptToAscii = {
  for (var i = 0; i < _subscriptChars.length; i++)
    _subscriptForms[i]: _subscriptChars[i],
};
final _superscriptRun = RegExp('[${_superscriptToAscii.keys.join()}]+');
final _subscriptRun = RegExp('[${_subscriptToAscii.keys.join()}]+');
final _compareSpace = RegExp(r'\s+');
final _compareOperatorSpace = RegExp(r' ?([+\-*/=<>^_(),{}\[\]]) ?');
// One leading option label (tag `v140-a4`): `A)`, `(B)`, `C.`, `D:`, `a)` —
// a letter A–H in either case — followed by whitespace and an answer.
final _optionLabel = RegExp(r'^\s*(?:\([A-Ha-h]\)|[A-Ha-h][).:])\s+(?=\S)');
final _loneLetter = RegExp(r'^[A-Za-z]\s*$');

bool _isAsciiDigitChar(String ch) =>
    ch.length == 1 && ch.codeUnitAt(0) >= 0x30 && ch.codeUnitAt(0) <= 0x39;

/// [kCompareFold] (the shared `compare_fold` table, tag `v140-a1`) per
/// character. A folded value that starts with a digit and holds a `/` (a
/// vulgar fraction) gets a space after a digit, so `1½` reads `1 1/2`.
String _applyCompareFold(String text) {
  final b = StringBuffer();
  var lastChar = '';
  for (var i = 0; i < text.length; i++) {
    final ch = text[i];
    var value = kCompareFold[ch];
    if (value == null) {
      b.write(ch);
      lastChar = ch;
      continue;
    }
    if (value.isNotEmpty &&
        _isAsciiDigitChar(value[0]) &&
        value.contains('/') &&
        _isAsciiDigitChar(lastChar)) {
      value = ' $value';
    }
    b.write(value);
    if (value.isNotEmpty) lastChar = value[value.length - 1];
  }
  return b.toString();
}

/// One ASCII-leaning form for answer comparison: a leading option label
/// dropped, compatibility characters folded, scripts as `^…`/`_…`, minus
/// signs and multiplication dots folded, whitespace collapsed and removed
/// around operators and brackets.
String _foldForCompare(String text) {
  // Never strip when a lone letter would remain: `a: b` must not compare as
  // the option letter `b` (tag `v140-a4`).
  final label = _optionLabel.firstMatch(text);
  if (label != null && !_loneLetter.hasMatch(text.substring(label.end))) {
    text = text.substring(label.end);
  }
  text = _applyCompareFold(text);
  text = text.replaceAllMapped(
    _superscriptRun,
    (m) => '^${m[0]!.split('').map((c) => _superscriptToAscii[c]).join()}',
  );
  text = text.replaceAllMapped(
    _subscriptRun,
    (m) => '_${m[0]!.split('').map((c) => _subscriptToAscii[c]).join()}',
  );
  text = text.replaceAll(_compareSpace, ' ').trim();
  return text.replaceAllMapped(_compareOperatorSpace, (m) => m[1]!);
}

/// LaTeX → plain text.
///
/// `style: 'text'`: accents dropped (grading, canvas, in-class report).
/// `style: 'pdf'`: accents marked (`\vec{F}` → `F⃗`, `\vec{AB}` → `vec(AB)`).
/// `style: 'tts'`: spoken English for a text-to-speech voice.
/// `style: 'compare'`: one form for answer comparison, so a typed answer
/// equals the same value in LaTeX (`1/3` = `$\frac{1}{3}$`, `x^2` =
/// `$x^2$`, `−3` = `-3`).
/// Throws an [ArgumentError] for any other style.
String toPlain(String text, {String style = 'text'}) {
  if (!styles.contains(style)) {
    throw ArgumentError.value(style, 'style', 'expected one of $styles');
  }
  // A form feed / backspace / TAB that was a command (`<FF>rac`,
  // `<TAB>imes`) is restored first, with the same `guessWhitespace` as `fix`
  // (`normalize`); tag `audit5-3`.
  text = repair(text);
  // Mojibake is repaired as `normalize` does (tag `v140-a6`). `compare`
  // decodes HTML entities the `html.unescape` way first, once (`v140-a2`).
  text = style == 'compare'
      ? fixMojibakeCore(unescapeHtmlEntities(text))
      : fixMojibakeTable(text);
  // A padded span (`$2x + 3 $`) is trimmed as `normalize` does, amounts
  // masked (tag `audit6-2`).
  text = trimPaddedSpansKeepCurrency(text);
  if (style == 'tts') return _toSpoken(text);
  if (style == 'compare') {
    return _foldForCompare(
      latexToPlain(
        text,
        keepLabelBackslash: false,
        force: true,
        compare: true,
      ),
    );
  }
  return latexToPlain(
    text,
    markAccents: style == 'pdf',
    keepLabelBackslash: style == 'text',
    bareChemistry: true,
  );
}
