/// Decode model JSON without turning its LaTeX into control characters.
///
/// `jsonDecode` accepts a single-backslash `\frac` as the JSON escape form
/// feed + `rac` and returns the corrupted string without complaint (Backend
/// #1651, #1654; agents #516, #531). [escapeLatexForJson] doubles the
/// backslashes that are LaTeX before the parser sees them. Port of
/// `python/pupiltree_latex/json_transport.py`.
library;

import 'dart:convert';

import 'commands.dart';
import 'segment.dart';
import 'tables.g.dart';

final _alphaRun = RegExp(r'[A-Za-z]+');

/// True if the letters starting at [pos] form a command. Inside math the
/// whole KaTeX vocabulary decides (`\nu` is LaTeX, `\nnext` is a newline);
/// outside math the same vocabulary minus the four names production prose
/// proved to be line breaks.
bool _spellsLatexCommand(String jsonText, int pos, bool inMath) {
  final m = _alphaRun.matchAsPrefix(jsonText, pos);
  if (m == null) return false;
  // A lesson-script label (`\teacher:`, `\type:`, `\read:`) is never an
  // escape.
  if (m.end < jsonText.length &&
      jsonText[m.end] == ':' &&
      m[0] == m[0]!.toLowerCase()) {
    return true;
  }
  final vocabulary =
      inMath ? kJsonWhitespaceCollisionCommands : kProseEscapeCommands;
  return vocabulary.contains(m[0]);
}

/// Index of the closing quote of the JSON string opened at [start] (or the
/// text length when unterminated).
int _stringEnd(String jsonText, int start) {
  var i = start + 1;
  final n = jsonText.length;
  while (i < n) {
    final c = jsonText[i];
    if (c == r'\') {
      i += 2;
      continue;
    }
    if (c == '"') return i;
    i++;
  }
  return n;
}

/// `mask[i]` is true when `body[i]` lies inside a math span, using
/// [segment] on the raw (still JSON-escaped) body: `$` positions are the
/// same in either form, and `segment` already handles `\$`.
List<bool> _mathMask(String body) {
  final mask = List<bool>.filled(body.length, false);
  var pos = 0;
  for (final seg in segment(body)) {
    final length = seg.raw.length;
    if (seg.isMath) {
      for (var k = pos; k < pos + length; k++) {
        mask[k] = true;
      }
    }
    pos += length;
  }
  return mask;
}

final _hex4 = RegExp(r'^[0-9a-fA-F]{4}$');

/// Escape LaTeX backslash sequences inside JSON string values.
///
/// Inside a string value:
///   - `\"`, `\\`, `\/`, `\uXXXX` are kept;
///   - `\n` `\t` `\r` stay JSON escapes unless the letters after the
///     backslash spell a command (see [kProseEscapeCommands]);
///   - `\b` and `\f` are ALWAYS LaTeX (backspace and form feed never occur
///     in lesson text);
///   - any other backslash (letter, digit, space, brace, …) is doubled:
///     none of those is a JSON escape, so keeping it would make the parser
///     throw.
String escapeLatexForJson(String jsonText) {
  final out = StringBuffer();
  var i = 0;
  final n = jsonText.length;
  while (i < n) {
    final c = jsonText[i];
    if (c != '"') {
      out.write(c);
      i++;
      continue;
    }
    // A string value: copy the opening quote, then walk the body with a
    // precomputed math mask.
    final end = _stringEnd(jsonText, i);
    final body = jsonText.substring(i + 1, end);
    final mask = _mathMask(body);
    out.write('"');
    var j = 0;
    final m = body.length;
    while (j < m) {
      final b = body[j];
      if (b != r'\') {
        out.write(b);
        j++;
        continue;
      }
      final nextC = j + 1 < m ? body[j + 1] : '';
      if (nextC == '"' || nextC == r'\' || nextC == '/') {
        out.write(b);
        out.write(nextC);
        j += 2;
        continue;
      }
      if (nextC == 'u' &&
          j + 5 < m &&
          _hex4.hasMatch(body.substring(j + 2, j + 6))) {
        out.write(body.substring(j, j + 6));
        j += 6;
        continue;
      }
      final inMath = j < m ? mask[j] : false;
      if ((nextC == 'n' || nextC == 't' || nextC == 'r') &&
          !_spellsLatexCommand(body, j + 1, inMath)) {
        out.write(b);
        out.write(nextC);
        j += 2;
        continue;
      }
      // Every other backslash is LaTeX (`\ ` is a spacing command, `\1` a
      // macro argument, `\{` a brace); none is a JSON escape, so leaving
      // them would make the parser throw.
      out.write(r'\\');
      j++;
    }
    if (end < n) out.write('"');
    i = end + 1;
  }
  return out.toString();
}

/// Python's `json.loads(strict=False)`: raw control characters inside string
/// values are content, not errors. Dart's `jsonDecode` rejects them, so they
/// are written as `\uXXXX` escapes first (only inside string bodies, with
/// the same quote/escape walk as [escapeLatexForJson]).
Object? _decodeLenient(String jsonText) {
  final out = StringBuffer();
  var i = 0;
  final n = jsonText.length;
  while (i < n) {
    final c = jsonText[i];
    if (c != '"') {
      out.write(c);
      i++;
      continue;
    }
    final end = _stringEnd(jsonText, i);
    out.write('"');
    for (var j = i + 1; j < end; j++) {
      final unit = jsonText.codeUnitAt(j);
      if (unit < 0x20) {
        out.write('\\u${unit.toRadixString(16).padLeft(4, '0')}');
      } else {
        out.writeCharCode(unit);
      }
    }
    if (end < n) out.write('"');
    i = end + 1;
  }
  return jsonDecode(out.toString());
}

/// `jsonDecode` for model output that may carry single-backslash LaTeX.
/// Raw newlines and tabs inside string values are accepted (models emit
/// them, and they are content). Falls back to the plain decode and throws
/// what that throws ([FormatException]).
Object? loadsLatexAware(String jsonText) {
  try {
    return _decodeLenient(escapeLatexForJson(jsonText));
  } on FormatException {
    return _decodeLenient(jsonText);
  }
}

/// Transport-only decode for model JSON. No fallback, no sanitiser —
/// invalid JSON throws a [FormatException] either way.
///
/// [lenient] (the default, tag `v140-b12`): [escapeLatexForJson] first, so
/// a backslash that is not a JSON escape (`\q`, `\frac`, `\alpha`) is
/// doubled and read as a literal backslash instead of failing, and raw
/// newlines and tabs inside string values are content. `lenient: false` is
/// a plain strict `jsonDecode`.
Object? loadsModelJson(String jsonText, {bool lenient = true}) => lenient
    ? _decodeLenient(escapeLatexForJson(jsonText))
    : jsonDecode(jsonText);
