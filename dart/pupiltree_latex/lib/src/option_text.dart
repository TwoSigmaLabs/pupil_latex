/// `normalizeOptionText`: one answer option, as the apps should show it.
/// Port of `python/pupiltree_latex/option_text.py` (tag `v140-b4`).
library;

import 'fix.dart';
import 'segment.dart';
import 'text_util.dart';

// A plain `\text{…}` body: no maths specials, no braces, no dollar.
final String _wholeTextSpan =
    '\\\\text$pyS*\\{$pyS*([^{}\\\\\$^_%&#]*?)$pyS*\\}';
final _wholeTextSpanRe = RegExp(_wholeTextSpan);
final _wholeTextSpanFullRe = RegExp('^$_wholeTextSpan\$');
// An element sequence (`H`, `Na`, `NaCl`, `H2O`) is chemistry: kept.
final _chemistryBody = RegExp(r'^(?:[A-Z][a-z]?[0-9]*){1,4}$');
// A whole span of plain words (`$Coulomb$`).
final _plainWords = RegExp(r"^[A-Za-z][A-Za-z .,'\-]*$");
final _longWord = RegExp('[A-Za-z][a-z]{3,}');

final _textCmd = RegExp('\\\\text$pyS*\\{$pyS*([^{}]*?)$pyS*\\}');
final _needsMaths = RegExp(r'[\\^_%&#]');
final _textWithScript = RegExp(
  r'\\text'
  '$pyS*'
  r'\{((?:[^{}]|\{[^{}]*\})*?[\^_]\{[^{}]*\}(?:[^{}]|\{[^{}]*\})*)\}',
);
final _scriptGroup = RegExp(r'[\^_]\{[^{}]*\}');
final _scriptGroupFull = RegExp(r'^[\^_]\{[^{}]*\}$');
final _doubleSuperscript = RegExp(r'\^\{([^{}]*)\}\^\{([^{}]*)\}');

/// `%` `&` `#` not already escaped get a backslash (maths mode).
String _escapeSpecials(String body) {
  final out = StringBuffer();
  for (var i = 0; i < body.length; i++) {
    final ch = body[i];
    if ('%&#'.contains(ch) && (i == 0 || body[i - 1] != r'\')) out.write(r'\');
    out.write(ch);
  }
  return out.toString();
}

/// Python `re.split` with one capture group: the pieces and the separators.
List<String> _splitKeeping(String s, RegExp re) {
  final out = <String>[];
  var last = 0;
  for (final m in re.allMatches(s)) {
    out
      ..add(s.substring(last, m.start))
      ..add(m[0]!);
    last = m.end;
  }
  out.add(s.substring(last));
  return out;
}

/// `\text{H_{2}O}` → `\text{H}_{2}\text{O}`; `^{-}^{1}` merges into `^{-1}`.
String _liftTextScripts(String inner) {
  final pieces = StringBuffer();
  for (final run in _splitKeeping(inner, _scriptGroup)) {
    if (_scriptGroupFull.hasMatch(run)) {
      pieces.write(run);
    } else if (pyStrip(run).isNotEmpty) {
      pieces.write('\\text{$run}');
    }
  }
  var lifted = pieces.toString();
  while (_doubleSuperscript.hasMatch(lifted)) {
    lifted =
        lifted.replaceAllMapped(_doubleSuperscript, (m) => '^{${m[1]}${m[2]}}');
  }
  return lifted;
}

String _mathBody(String body) {
  if (!body.contains(r'\text')) return body;
  body = body.replaceAllMapped(_textWithScript, (m) => _liftTextScripts(m[1]!));
  final whole = body;
  return whole.replaceAllMapped(_textCmd, (m) {
    final inner = m[1]!;
    if (!_needsMaths.hasMatch(inner)) return m[0]!;
    final before = m.start > 0 ? whole[m.start - 1] : ' ';
    return (isSpace(before) ? '' : ' ') + _escapeSpecials(inner);
  });
}

String _textBody(String raw) {
  if (raw.contains(r'\text')) {
    final whole = raw;
    raw = whole.replaceAllMapped(_wholeTextSpanRe, (m) {
      final next = m.end < whole.length ? whole[m.end] : '';
      return next == '_' || next == '^' ? m[0]! : m[1]!;
    });
  }
  return raw.replaceAll(r'\{', '{').replaceAll(r'\}', '}');
}

/// The words of a span that is only `\text{plain words}`, or null.
String? _spanWord(String value) {
  final m = _wholeTextSpanFullRe.firstMatch(pyStrip(value));
  if (m == null) return null;
  final word = m[1]!;
  if (word.isNotEmpty &&
      word.runes.any((r) => isAlpha(String.fromCharCode(r))) &&
      !_chemistryBody.hasMatch(word)) {
    return word;
  }
  return null;
}

/// The plain word(s) of an option that is one inline span and nothing else.
String? _wholeSpanWord(String text) {
  final segs = segment(pyStrip(text));
  if (segs.length != 1 || !segs.first.isMath || segs.first.display) {
    return null;
  }
  if (!segs.first.raw.startsWith(r'$')) return null;
  final body = pyStrip(segs.first.value);
  if (_wholeTextSpanFullRe.hasMatch(body)) return _spanWord(body);
  if (_plainWords.hasMatch(body) && _longWord.hasMatch(body)) {
    return pyStrip(body);
  }
  return null;
}

/// [fix], then the option-field clean-ups (tag `v140-b4`): an option that is
/// one span of plain words loses the span (`$\text{Coulomb}$` → `Coulomb`);
/// outside maths `\text{word}` → `word` and `\{`/`\}` → `{`/`}`; inside
/// maths scripts move out of `\text{}` (`$\text{H_{2}O}$` →
/// `$\text{H}_{2}\text{O}$`) and a `\text{}` whose body needs maths mode is
/// unwrapped (`$50 \text{ %}$` → `$50 \%$`). Idempotent.
String normalizeOptionText(String text, {bool chemistry = true}) {
  if (text.isEmpty) return text;
  final fixed = fix(text, chemistry: chemistry);
  final word = _wholeSpanWord(fixed);
  if (word != null) {
    final lead = fixed.substring(0, fixed.length - pyLstrip(fixed).length);
    final trail = fixed.substring(pyRstrip(fixed).length);
    return '$lead$word$trail';
  }
  final out = StringBuffer();
  for (final seg in segment(fixed)) {
    var raw = seg.raw;
    if (seg.isMath && raw.startsWith(r'$')) {
      final k = raw.startsWith(r'$$') ? 2 : 1;
      final w = k == 1 ? _spanWord(seg.value) : null;
      if (w != null) {
        raw = w;
      } else {
        raw = raw.substring(0, k) +
            _mathBody(raw.substring(k, raw.length - k)) +
            raw.substring(raw.length - k);
      }
    } else if (!seg.isMath) {
      raw = _textBody(raw);
    }
    out.write(raw);
  }
  return out.toString();
}
