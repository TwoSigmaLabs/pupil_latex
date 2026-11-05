/// `audit`: detect raw or mangled LaTeX. Read-only, pure.
///
/// Backend `services/ai/helper/latex_audit.py` (the eight production
/// signatures found the week of 2026-09-07) plus the four log-only checks
/// from Backend `validate_latex_text`, expressed as finding kinds. Port of
/// `python/pupiltree_latex/audit.py`. Precision over recall: a finding may
/// page someone, so each detector prefers to miss an ambiguous case rather
/// than flag a legitimate one.
library;

import 'dart:convert';

import 'guarded_regexp.dart';
import 'spans.dart';
import 'tables.g.dart';
import 'text_util.dart';
import 'walk.dart';

const kindControlChar = 'control_char';
const kindLegacyDelimiter = 'legacy_delimiter';
const kindUnbalancedDollar = 'unbalanced_dollar';
const kindCommandMissingArgument = 'command_missing_argument';
const kindFracMissingArgs = 'frac_missing_args';
const kindScriptMissingBraces = 'script_missing_braces';
const kindMojibake = 'mojibake';
const kindDoubleEscapedCommand = 'double_escaped_command';
const kindUnsupportedCommand = 'unsupported_command';
const kindBareUnicodeMath = 'bare_unicode_math';
const kindUnicodeChemistry = 'unicode_chemistry';
const kindBareLeftBrace = 'bare_left_brace';
const kindLostEscape = 'lost_escape';

/// Every finding kind, in detector order.
const List<String> allKinds = [
  kindControlChar,
  kindLegacyDelimiter,
  kindUnbalancedDollar,
  kindCommandMissingArgument,
  kindFracMissingArgs,
  kindScriptMissingBraces,
  kindMojibake,
  kindDoubleEscapedCommand,
  kindUnsupportedCommand,
  kindBareUnicodeMath,
  kindUnicodeChemistry,
  kindBareLeftBrace,
  kindLostEscape,
];

/// Control characters must be ZERO after the write-sink repair, so any hit
/// is a regression of that fix (or a write path that bypasses it).
const Set<String> errorKinds = {kindControlChar};

const snippetMaxChars = 120;
const _snippetRadius = 45;

/// One defect at one position in one string. [position] is a UTF-16 index.
class Finding {
  const Finding(this.kind, this.position, this.snippet);

  final String kind;
  final int position;
  final String snippet;

  @override
  bool operator ==(Object other) =>
      other is Finding &&
      other.kind == kind &&
      other.position == position &&
      other.snippet == snippet;

  @override
  int get hashCode => Object.hash(kind, position, snippet);

  @override
  String toString() => 'Finding($kind, $position, ${jsonEncode(snippet)})';
}

String _visible(int unit) {
  if (unit == 0x0A) return '↵';
  if (unit < 0x20 || unit == 0x7F) {
    return '<0x${unit.toRadixString(16).toUpperCase().padLeft(2, '0')}>';
  }
  return String.fromCharCode(unit);
}

/// A short window around [position] with every control char visible.
String makeSnippet(String text, int position, {int radius = _snippetRadius}) {
  final start = position - radius < 0 ? 0 : position - radius;
  final end = position + radius > text.length ? text.length : position + radius;
  var window = text.codeUnits.sublist(start, end).map(_visible).join();
  if (start > 0) window = '…$window';
  if (end < text.length) window = '$window…';
  return window.length > snippetMaxChars
      ? window.substring(0, snippetMaxChars)
      : window;
}

// ---------------------------------------------------------------------------
// Math-span tokenizer shared by several detectors
// ---------------------------------------------------------------------------

List<int> _unescapedDollarPositions(String text) => [
      for (var i = 0; i < text.length; i++)
        if (text[i] == r'$' && (i == 0 || text[i - 1] != r'\')) i,
    ];

/// `(innerStart, innerEnd)` of each `$…$` / `$$…$$` span.
List<(int, int)> _mathSpans(String text, {bool closedOnly = false}) {
  final spans = <(int, int)>[];
  final positions = _unescapedDollarPositions(text);
  var i = 0;
  String? openKind;
  var openInnerStart = 0;
  while (i < positions.length) {
    final pos = positions[i];
    final String token;
    final int width;
    final int step;
    if (i + 1 < positions.length && positions[i + 1] == pos + 1) {
      (token, width, step) = (r'$$', 2, 2);
    } else {
      (token, width, step) = (r'$', 1, 1);
    }
    if (openKind == null) {
      openKind = token;
      openInnerStart = pos + width;
    } else {
      spans.add((openInnerStart, pos));
      openKind = null;
    }
    i += step;
  }
  if (openKind != null && !closedOnly) spans.add((openInnerStart, text.length));
  return spans;
}

// ---------------------------------------------------------------------------
// Detectors
// ---------------------------------------------------------------------------

typedef _Detector = List<Finding> Function(String text);

List<Finding> _fromMatches(String kind, String text, Iterable<Match> matches) =>
    [
      for (final m in matches)
        Finding(kind, m.start, makeSnippet(text, m.start))
    ];

// Every C0 control except TAB/LF/CR, and DEL (tag `v140-b8`).
final _otherC0 = RegExp(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]');
final _alphaRun = RegExp(r'[A-Za-z]+');
const _wsCtrlLetter = {'\t': 't', '\n': 'n', '\r': 'r'};
const _minRunAfterNewline = 3;

List<Finding> _detectControlChars(String text) {
  final findings =
      _fromMatches(kindControlChar, text, _otherC0.allMatches(text));
  if (!_wsCtrlLetter.keys.any(text.contains)) return findings;
  List<int>? dollars;
  for (var i = 0; i < text.length; i++) {
    final letter = _wsCtrlLetter[text[i]];
    if (letter == null) continue;
    final m = _alphaRun.matchAsPrefix(text, i + 1);
    if (m == null) continue;
    final run = m[0]!;
    if (text[i] == '\n' && run.length < _minRunAfterNewline) continue;
    if (kLatexCommandsBehindJsonEscapes.contains('$letter$run')) {
      findings.add(Finding(kindControlChar, i, makeSnippet(text, i)));
      continue;
    }
    // Inside a math span a raw newline/tab/CR is never content; when the
    // letters after it spell a command under ANY of the three escape
    // letters (`$<LF>ightarrow$`) the byte is a decoded backslash. "Inside"
    // is `$` parity with a closer after (the newline is the very damage
    // that breaks the span, so the segment mask cannot be used).
    dollars ??= _unescapedDollarPositions(text);
    final inside =
        dollars.where((k) => k < i).length.isOdd && dollars.any((k) => k > i);
    if (inside &&
        const ['n', 't', 'r']
            .any((c) => kJsonWhitespaceCollisionCommands.contains('$c$run'))) {
      findings.add(Finding(kindControlChar, i, makeSnippet(text, i)));
    }
  }
  return findings;
}

final _legacyDelim = GuardedRegExp.notAfter(r'\\', r'\\[()\[\]]');

List<Finding> _detectLegacyDelimiters(String text) =>
    _fromMatches(kindLegacyDelimiter, text, _legacyDelim.allMatches(text));

List<Finding> _detectUnbalancedDollars(String text) {
  final positions = _unescapedDollarPositions(text);
  if (positions.length.isEven) return [];
  final last = positions.last;
  return [Finding(kindUnbalancedDollar, last, makeSnippet(text, last))];
}

final _cmdThenClose = RegExp(
  '\\\\(?:${kArgumentCommands.join('|')})(?![A-Za-z])$pyS*(?=\\\$|\$)',
);

/// `command_missing_argument` findings (also used by `canonicalize`).
List<Finding> detectCommandMissingArgument(String text) => _fromMatches(
      kindCommandMissingArgument,
      text,
      _cmdThenClose.allMatches(text),
    );

final _frac = RegExp(r'\\[dt]?frac(?![A-Za-z])');
final _simpleArg = RegExp(r'[A-Za-z0-9]');

int? _skipBraceGroup(String text, int i) {
  var depth = 0;
  final n = text.length;
  while (i < n) {
    final ch = text[i];
    if (ch == r'\') {
      i += 2;
      continue;
    }
    if (ch == '{') {
      depth++;
    } else if (ch == '}') {
      depth--;
      if (depth == 0) return i + 1;
    }
    i++;
  }
  return null;
}

int? _consumeFracArgument(String text, int i) {
  final n = text.length;
  while (i < n && (text[i] == ' ' || text[i] == '\t')) {
    i++;
  }
  if (i >= n) return null;
  final ch = text[i];
  if (ch == '{') return _skipBraceGroup(text, i);
  if (ch == r'\') {
    final m = _alphaRun.matchAsPrefix(text, i + 1);
    return m != null ? m.end : i + 2;
  }
  if (_simpleArg.hasMatch(ch)) return i + 1;
  return null;
}

/// `frac_missing_args` findings (also used by `canonicalize`).
List<Finding> detectFracMissingArgs(String text) {
  final findings = <Finding>[];
  for (final m in _frac.allMatches(text)) {
    final afterCmd = m.end;
    final first = _consumeFracArgument(text, afterCmd);
    if (first == null) {
      final rest =
          text.substring(afterCmd).replaceFirst(RegExp(r'^[ \t]+'), '');
      if (rest.isEmpty || rest.startsWith(r'$')) {
        continue; // reported by command_missing_argument
      }
      findings.add(
          Finding(kindFracMissingArgs, m.start, makeSnippet(text, m.start)));
      continue;
    }
    if (_consumeFracArgument(text, first) == null) {
      findings.add(
          Finding(kindFracMissingArgs, m.start, makeSnippet(text, m.start)));
    }
  }
  return findings;
}

final _scriptNoBraces = GuardedRegExp.notAfter(
  r'\\',
  r'[\^_](?:[0-9]{2,}|[+\-][A-Za-z0-9]|[A-Za-z]{2,})',
);
const _maxScriptSpanChars = 400;

/// Python `pattern.finditer(text, start, end)`: the pattern sees a string
/// that ends at [end] but can still look behind [start].
Iterable<Match> _matchesBetween(
  GuardedRegExp re,
  String text,
  int start,
  int end,
) =>
    re.allMatches(text.substring(0, end), start);

List<Finding> _detectScriptMissingBraces(String text) {
  final findings = <Finding>[];
  for (final (start, end) in _mathSpans(text, closedOnly: true)) {
    if (end - start > _maxScriptSpanChars) continue;
    for (final m in _matchesBetween(_scriptNoBraces, text, start, end)) {
      findings.add(
        Finding(kindScriptMissingBraces, m.start, makeSnippet(text, m.start)),
      );
    }
  }
  return findings;
}

final _mojibake = RegExp(
  '${u(0xFFFD)}|â€|[ÎÏ]|[âÂÃ][\x80-\xFF]',
);

List<Finding> _detectMojibake(String text) =>
    _fromMatches(kindMojibake, text, _mojibake.allMatches(text));

final _doubleEscaped = GuardedRegExp.notAfter(r'\\', r'(?:\\\\)+[A-Za-z]{2,}');
final _jsonObjectHint = RegExp('\\{$pyS*"[^"\\n]{1,80}"$pyS*:');

List<Finding> _detectDoubleEscapedCommands(String text) {
  if (_jsonObjectHint.hasMatch(text)) return [];
  // Inside a matrix / aligned block `\\` is a row separator, so `a&b\\cos x`
  // is a row that starts with `\cos`, not a double-escaped command.
  final rowSpans = [
    for (final (s, e, _) in mathRanges(text))
      if (_rowEnvironment.hasMatch(text.substring(s, e))) (s, e),
  ];
  return _fromMatches(
    kindDoubleEscapedCommand,
    text,
    _doubleEscaped
        .allMatches(text)
        .where((m) => !rowSpans.any((r) => r.$1 <= m.start && m.start < r.$2)),
  );
}

final _rowEnvironment = RegExp(r'\\begin\{|&');

final _commandName = GuardedRegExp.notAfter(r'\\', r'\\([A-Za-z]+)');
final _unsupported = RegExp(
  '\\\\(?:${kUnsupportedCommands.join('|')})(?![A-Za-z])',
);

List<Finding> _detectUnsupportedCommands(String text) {
  final findings = _fromMatches(
    kindUnsupportedCommand,
    text,
    _unsupported.allMatches(text),
  );
  final reported = {for (final f in findings) f.position};
  for (final (start, end) in _mathSpans(text, closedOnly: true)) {
    for (final m in _matchesBetween(_commandName, text, start, end)) {
      final name = m[1]!;
      if (kKatexCommands.contains(name) ||
          kAuditExtraAllowedCommands.contains(name)) {
        continue;
      }
      if (reported.contains(m.start)) continue;
      findings.add(
        Finding(kindUnsupportedCommand, m.start, makeSnippet(text, m.start)),
      );
    }
  }
  return findings;
}

final _bareUnicodeMath = RegExp(
  '[×÷±∓√∞∂∇≤≥≠≈'
  '≡∝→←↔⇌⇒⇐⇔∈∉⊂'
  '⊃⊆⊇∪∩∅∀∃∧∨'
  'αβγδεζηθικλμ'
  'νξπρστυφχψω'
  'ΓΔΘΛΞΠΣΦΨΩ]',
);

List<Finding> _detectBareUnicodeMath(String text) {
  if (!_bareUnicodeMath.hasMatch(text)) return [];
  final mask = mathMask(text);
  return [
    for (final m in _bareUnicodeMath.allMatches(text))
      if (!mask[m.start])
        Finding(kindBareUnicodeMath, m.start, makeSnippet(text, m.start)),
  ];
}

final _unicodeChem = RegExp('[A-Z][a-z]?[₀-₉]+');

List<Finding> _detectUnicodeChemistry(String text) =>
    _fromMatches(kindUnicodeChemistry, text, _unicodeChem.allMatches(text));

final _bareBraceCmd = RegExp(r'\\left(?!\\)\{|\\right(?!\\)\}');

List<Finding> _detectBareLeftBrace(String text) =>
    _fromMatches(kindBareLeftBrace, text, _bareBraceCmd.allMatches(text));

// `lost_escape` (tag `v140-b8`): a command whose first letter was eaten,
// the damage left after a form feed / tab / newline from a JSON escape was
// stripped (`\frac` → `rac`, `\times` → `imes`, `\text` → `ext`).
const Set<String> kLostEscapeRuns = {
  'rac', 'orall', 'inom', 'oldsymbol', 'arepsilon', 'artheta', 'arphi', //
  'abla', 'atural', 'ewline', 'olimits', 'onumber', 'otin', 'aisebox', //
  'ight', 'ightarrow', 'ightharpoonup', 'ightleftarrows', //
  'ightleftharpoons', 'anh', 'ext', 'extbf', 'extcolor', 'extit', 'extrm', //
  'extsf', 'extstyle', 'exttt', 'herefore', 'heta', 'hinspace', 'ilde', //
  'imes', 'riangle', 'riangleleft', 'riangleq', //
};
final _letterRun = RegExp('[A-Za-z]+');
final _anyControlChar = RegExp(r'[\x00-\x1F\x7F]');
final _textGroupOpen = RegExp(
  '\\\\(?:text|textbf|textit|textrm|textsf|texttt|textnormal|textup|mathrm|mbox|hbox)$pyS*\\{',
);

/// `[a, b)` of every `\text{…}`-family group between [start] and [end].
List<(int, int)> _textGroupRanges(String text, int start, int end) {
  final out = <(int, int)>[];
  final region = text.substring(0, end);
  for (final m in _textGroupOpen.allMatches(region, start)) {
    var depth = 0;
    var j = m.end - 1;
    while (j < end) {
      final ch = text[j];
      if (ch == r'\') {
        j += 2;
        continue;
      }
      if (ch == '{') {
        depth++;
      } else if (ch == '}') {
        depth--;
        if (depth == 0) break;
      }
      j++;
    }
    out.add((m.start, j + 1 < end ? j + 1 : end));
  }
  return out;
}

/// A run in [kLostEscapeRuns] at a word start (no letter or backslash
/// before it): inside a math span (outside `\text{…}`), or anywhere when a
/// `{` follows (`ext{H}`, `rac{1}{2}`). A control character still in front
/// of it is a `control_char` finding instead.
List<Finding> _detectLostEscapes(String text) {
  final candidates = [
    for (final m in _letterRun.allMatches(text))
      if (kLostEscapeRuns.contains(m[0])) m,
  ];
  if (candidates.isEmpty) return const [];
  final ranges = mathRanges(text);
  final groups = <(int, int)>[
    for (final r in ranges) ..._textGroupRanges(text, r.$1, r.$2),
  ];
  final controls = _anyControlChar.hasMatch(text)
      ? {for (final f in _detectControlChars(text)) f.position}
      : <int>{};
  final findings = <Finding>[];
  for (final m in candidates) {
    final i = m.start;
    if (i > 0 && (text[i - 1] == r'\' || controls.contains(i - 1))) continue;
    final inMath = ranges.any((r) => r.$1 <= i && i < r.$2);
    if (inMath && groups.any((g) => g.$1 <= i && i < g.$2)) continue;
    if (!inMath && !(m.end < text.length && text[m.end] == '{')) continue;
    findings.add(Finding(kindLostEscape, i, makeSnippet(text, i)));
  }
  return findings;
}

const List<_Detector> _detectors = [
  _detectControlChars,
  _detectLegacyDelimiters,
  _detectUnbalancedDollars,
  detectCommandMissingArgument,
  detectFracMissingArgs,
  _detectScriptMissingBraces,
  _detectMojibake,
  _detectDoubleEscapedCommands,
  _detectUnsupportedCommands,
  _detectBareUnicodeMath,
  _detectUnicodeChemistry,
  _detectBareLeftBrace,
  _detectLostEscapes,
];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Every defect in one string, ordered by position then kind.
List<Finding> audit(String text) {
  if (text.isEmpty) return const [];
  final findings = <Finding>[];
  for (final detector in _detectors) {
    findings.addAll(detector(text));
  }
  // Stable sort on (position, kind), like Python's `list.sort`.
  final indexed = findings.indexed.toList();
  indexed.sort((a, b) {
    final byPos = a.$2.position.compareTo(b.$2.position);
    if (byPos != 0) return byPos;
    final byKind = a.$2.kind.compareTo(b.$2.kind);
    return byKind != 0 ? byKind : a.$1.compareTo(b.$1);
  });
  return [for (final (_, f) in indexed) f];
}

/// The kinds only, in finding order (what the corpus compares).
List<String> auditKinds(String text) => [for (final f in audit(text)) f.kind];

Object? _decodeJsonLeaf(String text) {
  final head = pyLstrip(text);
  if (head.isEmpty || (head[0] != '{' && head[0] != '[')) return null;
  final Object? parsed;
  try {
    parsed = jsonDecode(text);
  } on FormatException {
    return null;
  }
  return (parsed is Map || parsed is List) ? parsed : null;
}

Iterable<(String, String)> _contentLeaves(
  Object? obj,
  String keyHint,
  String path,
) sync* {
  if (obj is String) {
    if (isNonContentKey(keyHint) || isNotRenderedKey(keyHint)) return;
    if (isUrlOrPathString(obj)) return;
    final decoded = _decodeJsonLeaf(obj);
    if (decoded != null) {
      yield* _contentLeaves(decoded, keyHint, '$path(json)');
      return;
    }
    yield (path, obj);
  } else if (obj is Map) {
    for (final e in obj.entries) {
      final k = '${e.key}';
      final child = path.isNotEmpty ? '$path.$k' : k;
      yield* _contentLeaves(e.value, k, child);
    }
  } else if (obj is List) {
    for (var i = 0; i < obj.length; i++) {
      yield* _contentLeaves(obj[i], keyHint, '$path[$i]');
    }
  }
}

/// `(fieldPath, finding)` for every content string leaf of a document.
/// Raw/prompt fields and non-content keys are skipped; a string leaf that
/// is itself a JSON document is audited decoded (path suffix `(json)`).
List<({String path, Finding finding})> auditDeep(Object? obj) => [
      for (final (path, text) in _contentLeaves(obj, '', ''))
        for (final finding in audit(text)) (path: path, finding: finding),
    ];

/// Finding counts per kind, in [allKinds] order, zero counts omitted.
Map<String, int> countByKind(Iterable<Finding> findings) {
  final counter = <String, int>{};
  for (final f in findings) {
    counter[f.kind] = (counter[f.kind] ?? 0) + 1;
  }
  return {
    for (final k in allKinds)
      if (counter[k] != null) k: counter[k]!,
  };
}

/// True when any kind is a regression class (log at ERROR).
bool isError(Iterable<String> kinds) => kinds.any(errorKinds.contains);
