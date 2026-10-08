/// `repair`: undo JSON-escape damage to LaTeX commands, drop other C0 bytes.
///
/// A parser that reads `\frac` as the JSON escape `\f` stores form feed +
/// "rac"; `\times` becomes TAB + "imes". This is the one function that is
/// safe on ANY content: every DB write sink, every read path and every
/// client runs it. Port of `python/pupiltree_latex/repair.py`.
library;

import 'normalize.dart' show currencyPositions;
import 'tables.g.dart';
import 'text_util.dart';

const _whitespaceLetter = <String, String>{
  '\x09': 't',
  '\x0A': 'n',
  '\x0D': 'r',
};

/// The one letter in n/t/r for which `letter + run` is a KaTeX command, or
/// `''` when none or more than one fits (`ightarrow` → `r`).
String _onlyCommandReading(String run) {
  final fits = [
    for (final c in const ['n', 't', 'r'])
      if (kJsonWhitespaceCollisionCommands.contains('$c$run')) c,
  ];
  return fits.length == 1 ? fits[0] : '';
}

final _alphaRun = RegExp(r'[A-Za-z]+');
// Every C0 control except TAB, LF, CR — plus DEL.
final _otherControl = RegExp(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]');
final _anyControl = RegExp(r'[\x00-\x1F\x7F]');
// A whole ANSI CSI sequence (terminal colour/bold codes copied from a log):
// ESC `[`, parameter bytes, intermediate bytes, one final byte.
final _ansiCsi = RegExp(r'\x1B\[[0-?]*[ -/]*[@-~]');

final _damagedWhitespace = RegExp('[\\t\\n\\r]');

/// Positions of the unescaped `$` in [text] that are not money.
/// Currency-aware (tag `v140-b7`): a dollar that `normalize` reads as money
/// is no span delimiter, so `costs $5.<LF>angle … $10` keeps its line break.
/// The damaged whitespace is read as a space for this, so a span cut by it
/// still pairs.
List<int> _dollarPositions(String text) {
  final money =
      currencyPositions(text.replaceAll(_damagedWhitespace, ' ')).toSet();
  return [
    for (var k = 0; k < text.length; k++)
      if (text[k] == r'$' &&
          (k == 0 || text[k - 1] != r'\') &&
          !money.contains(k))
        k,
  ];
}

/// Restore control characters that were LaTeX commands; drop the rest.
///
/// - U+0008 → `\b` and U+000C → `\f` when a letter follows.
/// - U+000B → `\v` when `v` + the following letters is a KaTeX command.
/// - TAB / LF / CR → `\t` / `\n` / `\r` only when [guessWhitespace] and the
///   following letters spell a command in [kLatexCommandsBehindJsonEscapes],
///   a lesson-script label (`<TAB>eacher:`), or, inside a closed `$…$`
///   span, a command under exactly one of the three letters
///   (`$x <LF>ightarrow y$`); otherwise they are kept.
/// - Any other C0 control and DEL is removed.
///
/// `guessWhitespace: false` is the read-path form (Backend #1595): stored
/// bytes are served with only the two unconditional repairs applied.
/// Idempotent.
String repair(String text, {bool guessWhitespace = true}) {
  if (text.isEmpty) return text;
  if (!_anyControl.hasMatch(text)) return text;
  if (text.contains('\x1B[')) text = text.replaceAll(_ansiCsi, '');
  final out = StringBuffer();
  final n = text.length;
  List<int>? dollars; // positions of unescaped `$`, on demand

  // An odd number of unescaped `$` before `pos` and one after it: the
  // corrupted span `$x <LF>ightarrow y$` still counts (the newline is the
  // very damage), an unterminated `$<LF>o` does not.
  bool inClosedSpan(int pos) {
    dollars ??= _dollarPositions(text);
    final before = dollars!.where((k) => k < pos).length;
    return before.isOdd && dollars!.any((k) => k > pos);
  }

  var i = 0;
  while (i < n) {
    final ch = text[i];
    if (ch == '\x08' || ch == '\x0C') {
      // Restored only when a letter follows: a bare form feed has no
      // command to go back to and is dropped with the other C0 bytes.
      if (i + 1 < n && isAlpha(codePointAt(text, i + 1))) {
        out.write(ch == '\x08' ? r'\b' : r'\f');
      } else {
        out.write(ch);
      }
    } else if (ch == '\x0B') {
      final m = _alphaRun.matchAsPrefix(text, i + 1);
      if (m != null && kKatexCommands.contains('v${m[0]}')) {
        out.write(r'\v');
      } else {
        out.write(ch); // dropped by the final strip
      }
    } else if (_whitespaceLetter.containsKey(ch) && guessWhitespace) {
      final letter = _whitespaceLetter[ch]!;
      final m = _alphaRun.matchAsPrefix(text, i + 1);
      final run = m?[0] ?? '';
      if (run.isNotEmpty &&
          kLatexCommandsBehindJsonEscapes.contains('$letter$run')) {
        out.write('\\$letter');
      } else if (run.isNotEmpty &&
          m!.end < n &&
          text[m.end] == ':' &&
          kScriptLabels.contains('$letter$run')) {
        // `<TAB>eacher:` / `<LF>ead:` — a decoded lesson-script label.
        out.write('\\$letter');
      } else if (run.length >= 3 &&
          inClosedSpan(i) &&
          _onlyCommandReading(run).isNotEmpty) {
        // Inside a CLOSED `$…$` span a raw newline/tab is never content:
        // `$<LF>ightarrow$` can only have been `\rightarrow`. Three letters
        // minimum, as for the audit: `$<LF>o` is not `\to`.
        out.write('\\${_onlyCommandReading(run)}');
      } else {
        out.write(ch);
      }
    } else {
      out.write(ch);
    }
    i++;
  }
  return out.toString().replaceAll(_otherControl, '');
}

/// [repair] over every string in a JSON-like document (maps, lists,
/// strings; anything else is returned as is). No key skipping is needed:
/// the repair cannot damage an id, a URL or a timestamp.
Object? repairDeep(Object? obj, {bool guessWhitespace = true}) {
  if (obj is String) return repair(obj, guessWhitespace: guessWhitespace);
  if (obj is Map) {
    return mapValues(
        obj, (v) => repairDeep(v, guessWhitespace: guessWhitespace));
  }
  if (obj is List) {
    return <Object?>[
      for (final v in obj) repairDeep(v, guessWhitespace: guessWhitespace),
    ];
  }
  return obj;
}

/// A new map with [f] applied to every value. String-keyed maps (every JSON
/// document) come back as `Map<String, Object?>` so a caller's
/// `as Map<String, dynamic>` still holds.
Map<Object?, Object?> mapValues(
  Map<Object?, Object?> obj,
  Object? Function(Object? value) f,
) {
  if (obj.keys.every((k) => k is String)) {
    return <String, Object?>{
      for (final e in obj.entries) e.key as String: f(e.value),
    };
  }
  return <Object?, Object?>{for (final e in obj.entries) e.key: f(e.value)};
}
