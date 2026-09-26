/// A small `\ce{…}` / `\pu{…}` (mhchem) → plain LaTeX translator for
/// flutter_math_fork, which has no mhchem. The web clients load the real
/// mhchem extension and never call this.
///
/// It covers the notation lesson text uses: formulas (`H2O`, `Ca(OH)2`,
/// `[Cu(NH3)4]^2+`), stoichiometric coefficients (`2H2`), charges (`SO4^2-`,
/// `Fe^{3+}`, `Na+`, `e-`), states (`(aq)`), hydrate dots (`CuSO4*5H2O`,
/// `·`), bonds (`-`, `=`, `#`), the four reaction arrows with optional
/// labels (`->[\Delta]`), and `\pu{3e8 m/s}` quantities. Anything outside
/// that grammar is left exactly as written, so the caller's parse-failure
/// fallback still shows the source.
library;

/// Rewrite every `\ce{…}` and `\pu{…}` in [tex] that the translator
/// understands into plain LaTeX; every other character is returned
/// unchanged.
String ceToLatex(String tex) {
  if (!tex.contains(r'\ce') && !tex.contains(r'\pu')) return tex;
  final out = StringBuffer();
  var i = 0;
  final n = tex.length;
  while (i < n) {
    final m = _command.matchAsPrefix(tex, i);
    if (m != null && (i == 0 || tex[i - 1] != r'\')) {
      final open = m.end - 1;
      final close = _matchingBrace(tex, open);
      if (close != -1) {
        final body = tex.substring(open + 1, close);
        final translated = m[1] == 'ce' ? ceBodyToLatex(body) : puBodyToLatex(body);
        if (translated != null) {
          out.write('{$translated}');
          i = close + 1;
          continue;
        }
      }
    }
    out.write(tex[i]);
    i++;
  }
  return out.toString();
}

final _command = RegExp(r'\\(ce|pu)(?![A-Za-z])\s*\{');

/// Index of the `}` closing the `{` at [open], or -1.
int _matchingBrace(String s, int open) {
  var depth = 0;
  for (var i = open; i < s.length; i++) {
    final c = s[i];
    if (c == r'\') {
      i++;
    } else if (c == '{') {
      depth++;
    } else if (c == '}') {
      depth--;
      if (depth == 0) return i;
    }
  }
  return -1;
}

bool _isUpper(String c) => c.compareTo('A') >= 0 && c.compareTo('Z') <= 0;
bool _isLower(String c) => c.compareTo('a') >= 0 && c.compareTo('z') <= 0;
bool _isLetter(String c) => _isUpper(c) || _isLower(c);
bool _isDigit(String c) => c.compareTo('0') >= 0 && c.compareTo('9') <= 0;
bool _isWs(String c) => c == ' ' || c == '\t' || c == '\n' || c == '\r';

/// `(arrow, plain, extensible)`; longer spellings first.
const _arrows = [
  ('<=>', r'\rightleftharpoons', r'\xrightleftharpoons'),
  ('<->', r'\leftrightarrow', r'\xleftrightarrow'),
  ('->', r'\rightarrow', r'\xrightarrow'),
  ('<-', r'\leftarrow', r'\xleftarrow'),
];

/// The argument of `^` / `_` starting at [i]: a braced group, or a digit
/// run with an optional sign (`2-`, `3+`), or a lone sign or letter.
/// Returns `(content, end)` or null.
(String, int)? _scriptArgument(String s, int i) {
  final n = s.length;
  if (i >= n) return null;
  if (s[i] == '{') {
    final close = _matchingBrace(s, i);
    if (close == -1) return null;
    return (s.substring(i + 1, close), close + 1);
  }
  var j = i;
  while (j < n && _isDigit(s[j])) {
    j++;
  }
  if (j < n && (s[j] == '+' || s[j] == '-')) j++;
  if (j > i) return (s.substring(i, j), j);
  if (_isLetter(s[i])) return (s[i], i + 1);
  return null;
}

/// The body of a `\ce{…}` as plain LaTeX, or null when it uses notation
/// outside the supported grammar.
String? ceBodyToLatex(String body) {
  final s = body.trim();
  if (s.isEmpty) return null;
  final out = StringBuffer();
  final n = s.length;
  var i = 0;
  // True right after something a subscript digit or a charge can attach to:
  // a letter run, `)` / `]`, or a script on one of those.
  var inFormula = false;
  var hasSub = false;
  var hasSup = false;

  void attach(String op, String content) {
    final taken = op == '_' ? hasSub : hasSup;
    if (taken) {
      out.write('{}');
      hasSub = false;
      hasSup = false;
    }
    out.write('$op{$content}');
    if (op == '_') {
      hasSub = true;
    } else {
      hasSup = true;
    }
  }

  void resetBase() {
    hasSub = false;
    hasSup = false;
  }

  bool chargeEnds(int j) =>
      j >= n || _isWs(s[j]) || s[j] == ')' || s[j] == ']';

  while (i < n) {
    final c = s[i];
    if (_isWs(c)) {
      out.write(' ');
      inFormula = false;
      resetBase();
      i++;
      continue;
    }

    // Reaction arrows, with up to two `[label]`s.
    (String, String, String)? arrow;
    for (final a in _arrows) {
      if (s.startsWith(a.$1, i)) {
        arrow = a;
        break;
      }
    }
    if (arrow != null) {
      var j = i + arrow.$1.length;
      final labels = <String>[];
      while (labels.length < 2 && j < n && s[j] == '[') {
        final close = s.indexOf(']', j);
        if (close == -1) return null;
        final inner = s.substring(j + 1, close);
        labels.add(
          inner.trim().isEmpty
              ? ''
              : ceBodyToLatex(inner) ?? '\\text{${inner.trim()}}',
        );
        j = close + 1;
      }
      if (labels.isEmpty) {
        out.write(' ${arrow.$2} ');
      } else if (labels.length == 1) {
        out.write(' ${arrow.$3}{${labels[0]}} ');
      } else {
        out.write(' ${arrow.$3}[${labels[1]}]{${labels[0]}} ');
      }
      inFormula = false;
      resetBase();
      i = j;
      continue;
    }

    if (c == '+' || c == '-') {
      if (inFormula && chargeEnds(i + 1)) {
        attach('^', c); // `Na+`, `Cl-`, `e-`
      } else if (c == '-' && inFormula) {
        out.write('-'); // single bond `C-C`
        inFormula = false;
        resetBase();
      } else {
        out.write(' $c ');
        inFormula = false;
        resetBase();
      }
      i++;
      continue;
    }

    if (c == '^' || c == '_') {
      final arg = _scriptArgument(s, i + 1);
      if (arg == null) return null;
      if (!inFormula) {
        // A prescript (`^{14}_{6}C`) or a script after an operator needs an
        // empty base.
        out.write('{}');
        resetBase();
      }
      attach(c, arg.$1);
      inFormula = true;
      i = arg.$2;
      continue;
    }

    if (_isLetter(c)) {
      var j = i;
      while (j < n && _isLetter(s[j])) {
        j++;
      }
      out.write('\\mathrm{${s.substring(i, j)}}');
      inFormula = true;
      resetBase();
      i = j;
      continue;
    }

    if (_isDigit(c)) {
      var j = i;
      if (inFormula) {
        while (j < n && _isDigit(s[j])) {
          j++;
        }
        attach('_', s.substring(i, j));
      } else {
        // A stoichiometric coefficient: `2`, `0.5`, `1/2`.
        while (j < n && (_isDigit(s[j]) || s[j] == '.' || s[j] == '/')) {
          j++;
        }
        out.write(s.substring(i, j));
        resetBase();
      }
      i = j;
      continue;
    }

    if (c == '(' || c == '[') {
      out.write(c);
      inFormula = false;
      resetBase();
      i++;
      continue;
    }
    if (c == ')' || c == ']') {
      out.write(c);
      inFormula = true;
      resetBase();
      i++;
      continue;
    }
    if (c == '*' || c == '·' || c == '•') {
      out.write(r' \cdot ');
      inFormula = false;
      resetBase();
      i++;
      continue;
    }
    if (c == '=') {
      out.write('=');
      inFormula = false;
      resetBase();
      i++;
      continue;
    }
    if (c == '#') {
      out.write(r'\equiv ');
      inFormula = false;
      resetBase();
      i++;
      continue;
    }
    if (c == r'\') {
      // A plain command (`\alpha`, `\Delta`) passes through.
      var j = i + 1;
      while (j < n && _isLetter(s[j])) {
        j++;
      }
      if (j == i + 1) return null;
      out.write('${s.substring(i, j)} ');
      inFormula = false;
      resetBase();
      i = j;
      continue;
    }
    return null;
  }
  return out.toString().replaceAll(RegExp(' {2,}'), ' ').trim();
}

final _puNumber = RegExp(r'^([-+]?\d+(?:\.\d+)?)(?:[eE]([-+]?\d+))?');

/// The body of a `\pu{…}` (`3e8 m/s`, `25 °C`, `8.314 J K^-1 mol^-1`) as
/// plain LaTeX, or null when it is outside the supported grammar.
String? puBodyToLatex(String body) {
  final s = body.trim();
  final m = _puNumber.firstMatch(s);
  final parts = <String>[];
  var rest = s;
  if (m != null) {
    final exponent = m[2];
    parts.add(
      exponent == null ? m[1]! : '${m[1]}\\times10^{${_stripPlus(exponent)}}',
    );
    rest = s.substring(m.end).trim();
  }
  if (rest.isEmpty) return parts.isEmpty ? null : parts.single;
  final units = <String>[];
  for (final token in rest.split(RegExp(r'\s+'))) {
    final unit = _unitToLatex(token);
    if (unit == null) return null;
    units.add(unit);
  }
  final unitTex = units.join(r'\ ');
  return parts.isEmpty ? unitTex : '${parts.single}\\ $unitTex';
}

String _stripPlus(String exponent) =>
    exponent.startsWith('+') ? exponent.substring(1) : exponent;

/// One unit token (`m/s`, `mol^-1`, `s-2`, `°C`, `kJ*mol^{-1}`).
String? _unitToLatex(String token) {
  final out = StringBuffer();
  final word = StringBuffer();
  void flush() {
    if (word.isNotEmpty) {
      out.write('\\mathrm{$word}');
      word.clear();
    }
  }

  final n = token.length;
  var i = 0;
  while (i < n) {
    final c = token[i];
    if (_isLetter(c) || c == '/') {
      word.write(c);
      i++;
    } else if (c == '%') {
      word.write(r'\%');
      i++;
    } else if (c == 'µ' || c == 'μ') {
      word.write(r'\mu ');
      i++;
    } else if (c == 'Ω') {
      word.write(r'\Omega ');
      i++;
    } else if (c == '°') {
      flush();
      out.write(r'{}^{\circ}');
      i++;
    } else if (c == '^' || _isDigit(c) || c == '-') {
      // `m^2`, `m2`, `s^-1`, `s-1`: an exponent on the unit before it.
      if (word.isEmpty && out.isEmpty) return null;
      var j = c == '^' ? i + 1 : i;
      String exponent;
      if (j < n && token[j] == '{') {
        final close = _matchingBrace(token, j);
        if (close == -1) return null;
        exponent = token.substring(j + 1, close);
        j = close + 1;
      } else {
        final start = j;
        if (j < n && (token[j] == '-' || token[j] == '+')) j++;
        while (j < n && _isDigit(token[j])) {
          j++;
        }
        exponent = token.substring(start, j);
        if (exponent.isEmpty || exponent == '-' || exponent == '+') {
          return null;
        }
      }
      flush();
      out.write('^{${_stripPlus(exponent)}}');
      i = j;
    } else if (c == '.' || c == '*' || c == '·') {
      flush();
      out.write(r'\cdot ');
      i++;
    } else {
      return null;
    }
  }
  flush();
  return out.isEmpty ? null : out.toString();
}
