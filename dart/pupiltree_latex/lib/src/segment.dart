/// `segment`: the one tokenizer every renderer uses.
///
/// Splits a string into prose and math segments. Escape-aware (`\$` is a
/// literal dollar, `\\$x$` opens math), brace-aware (the KaTeX auto-render
/// walk: a backslash skips the next character, `{`/`}` nest), and
/// currency-aware for inline `$…$` (pandoc's rule: content must not start
/// with whitespace or span a line, the closer must not be followed by a
/// digit). Port of `python/pupiltree_latex/segment.py`.
library;

import 'text_util.dart';

/// One piece of a string: prose (`kind == 'text'`) or math (`kind == 'math'`).
class Segment {
  const Segment({
    required this.kind,
    required this.display,
    required this.value,
    required this.raw,
  });

  /// `'text'` or `'math'`.
  final String kind;

  /// Display math (`$$…$$`, `\[…\]`); always false for text.
  final bool display;

  /// Inner content for math; for text the slice with `\$` unescaped to `$`.
  final String value;

  /// The exact source slice, delimiters included.
  final String raw;

  bool get isMath => kind == 'math';

  Map<String, Object?> toJson() =>
      {'kind': kind, 'display': display, 'value': value, 'raw': raw};

  @override
  bool operator ==(Object other) =>
      other is Segment &&
      other.kind == kind &&
      other.display == display &&
      other.value == value &&
      other.raw == raw;

  @override
  int get hashCode => Object.hash(kind, display, value, raw);

  @override
  String toString() => 'Segment(${toJson()})';
}

/// True when an odd number of backslashes immediately precedes [i].
bool _escaped(String s, int i) {
  var count = 0;
  var p = i - 1;
  while (p >= 0 && s[p] == r'\') {
    count++;
    p--;
  }
  return count.isOdd;
}

/// KaTeX auto-render's findEndOfMath: index of the closing delimiter at
/// brace depth ≤ 0, or -1.
int _findEnd(String delim, String s, int start) {
  var idx = start;
  var depth = 0;
  final n = s.length;
  while (idx < n) {
    if (depth <= 0 && s.startsWith(delim, idx)) return idx;
    final ch = s[idx];
    if (ch == r'\') {
      idx++;
    } else if (ch == '{') {
      depth++;
    } else if (ch == '}') {
      depth--;
    }
    idx++;
  }
  return -1;
}

/// Split [text] into [Segment]s.
///
/// Delimiter priority at each position: `$$`, `\[`, `$`, `\(`. Text `value`
/// has `\$` unescaped to `$`; `raw` is the exact source slice. Math `value`
/// is the inner content (`\(…\)` trimmed). The empty string yields `[]`.
List<Segment> segment(String text) {
  if (text.isEmpty) return const [];
  final s = text;
  final n = s.length;
  final out = <Segment>[];
  final textRaw = StringBuffer();
  final textVal = StringBuffer();

  void flush() {
    if (textRaw.isNotEmpty) {
      out.add(Segment(
        kind: 'text',
        display: false,
        value: textVal.toString(),
        raw: textRaw.toString(),
      ));
      textRaw.clear();
      textVal.clear();
    }
  }

  void pushMath(String raw, String value, bool display) {
    flush();
    out.add(Segment(kind: 'math', display: display, value: value, raw: raw));
  }

  var i = 0;
  while (i < n) {
    final ch = s[i];
    if (ch == r'\') {
      if (_escaped(s, i)) {
        textRaw.write(ch);
        textVal.write(ch);
        i++;
        continue;
      }
      final nxt = i + 1 < n ? s[i + 1] : '';
      if (nxt == r'$') {
        textRaw.write(r'\$');
        textVal.write(r'$');
        i += 2;
        continue;
      }
      if (nxt == '[') {
        final end = _findEnd(r'\]', s, i + 2);
        if (end != -1) {
          pushMath(s.substring(i, end + 2), s.substring(i + 2, end), true);
          i = end + 2;
          continue;
        }
      }
      if (nxt == '(') {
        final end = _findEnd(r'\)', s, i + 2);
        if (end != -1) {
          pushMath(
            s.substring(i, end + 2),
            pyStrip(s.substring(i + 2, end)),
            false,
          );
          i = end + 2;
          continue;
        }
      }
      textRaw.write(ch);
      textVal.write(ch);
      i++;
      continue;
    }
    if (ch == r'$') {
      if (s.startsWith(r'$$', i)) {
        final end = _findEnd(r'$$', s, i + 2);
        if (end > i + 2) {
          pushMath(s.substring(i, end + 2), s.substring(i + 2, end), true);
          i = end + 2;
          continue;
        }
      } else if (i + 1 < n && !isSpace(codePointAt(s, i + 1))) {
        final end = _findEnd(r'$', s, i + 1);
        if (end != -1) {
          final content = s.substring(i + 1, end);
          final closerOk = !isSpace(s[end - 1]) &&
              (end + 1 >= n || !isDigit(codePointAt(s, end + 1)));
          if (content.isNotEmpty && !content.contains('\n') && closerOk) {
            pushMath(s.substring(i, end + 1), content, false);
            i = end + 1;
            continue;
          }
        }
      }
      textRaw.write(r'$');
      textVal.write(r'$');
      i++;
      continue;
    }
    textRaw.write(ch);
    textVal.write(ch);
    i++;
  }
  flush();
  return out;
}

final _command = RegExp(r'\\[A-Za-z]');

/// True when the text has a math segment or a backslash command.
bool containsMath(String text) {
  if (text.isEmpty) return false;
  if (_command.hasMatch(text)) return true;
  return segment(text).any((seg) => seg.isMath);
}

// Anything that markdown or LaTeX would interpret. Mirrors script_editor's
// `ScriptEditorTex._markdownSyntaxRx` (the plain-prose fast path added in
// #428 after a 7.58 s ANR on 30 cards × 7 fields).
final _notPlain = RegExp(
  r'[\\$*~`|\[\]<>#\r⸻【]' // markup characters, ⸻, 【
  r'|\n\n' // blank line
  r'|--' // rule / em-dash marker
  '|(?:^|\\n)[ \\t]+$pyNotS' // leading indentation
  r'|(?:^|\n)(?:[-*+] |[0-9]+[.)] )' // list marker
  r'|\([xX ]\) ', // gpt_markdown radio button `(x) ` / `( ) ` (tag v140-b10)
);

/// Renderer fast path: true when the text can be shown as plain text.
bool isPlainProse(String text) => !_notPlain.hasMatch(text);
