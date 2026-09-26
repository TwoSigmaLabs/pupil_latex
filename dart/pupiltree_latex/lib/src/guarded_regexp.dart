/// A leading one-character lookbehind, without a lookbehind.
///
/// On the web Dart's `RegExp` is the browser's JS `RegExp`, and Safari/iOS
/// before 16.4 throws a `SyntaxError` on any lookbehind — when the
/// top-level pattern is first used, which takes the whole call (`fix`,
/// `normalize`, …) down with it. [GuardedRegExp] gives the exact match
/// sequence of `X` behind a negative or positive lookbehind on one
/// character class `C`, using lookahead only (supported everywhere):
///
/// - a candidate at the search position itself is tried anchored
///   ([RegExp.matchAsPrefix]) and kept when the character before it passes
///   the guard — that character may belong to the previous match, which a
///   lookbehind can see but a consuming pattern could not;
/// - candidates further on come from a scan pattern that consumes the one
///   guard character and captures `X` in a lookahead (`[^C](?=(X))`), so a
///   position the lookbehind would reject fails on its first character,
///   as fast as the lookbehind did.
///
/// A lookahead cannot be backtracked into, and nothing follows it in the
/// scan pattern, so the captured `X` is the same first match the original
/// pattern takes at that position. `test/no_lookbehind_test.dart` keeps
/// `lib/` free of lookbehind.
library;

/// A pattern `X` whose matches must (or must not) follow a guard character.
class GuardedRegExp {
  /// `X` not preceded by a character of the class whose body is
  /// [notAfter] (a negative lookbehind).
  GuardedRegExp.notAfter(
    String notAfter,
    String pattern, {
    bool unicode = false,
    bool dotAll = false,
  }) : this._(
          pattern,
          '[^$notAfter](?=($pattern))',
          RegExp('[$notAfter]', unicode: unicode),
          negate: true,
          unicode: unicode,
          dotAll: dotAll,
        );

  /// `X` preceded by a character of the class whose body is [after] (a
  /// positive lookbehind).
  GuardedRegExp.after(
    String after,
    String pattern, {
    bool unicode = false,
    bool dotAll = false,
  }) : this._(
          pattern,
          '[$after](?=($pattern))',
          RegExp('[$after]', unicode: unicode),
          negate: false,
          unicode: unicode,
          dotAll: dotAll,
        );

  /// A general form: [pattern] is `X` without its lookbehind, [scan] finds
  /// every candidate after the search position (group 1 is the match of
  /// `X`, captured in a lookahead, and the consumed part ends where it
  /// starts), and [accept] decides a candidate found anchored at the search
  /// position itself.
  GuardedRegExp.custom(
    String pattern,
    String scan, {
    required bool Function(String text, Match candidate) accept,
    bool unicode = false,
    bool dotAll = false,
  })  : _x = RegExp(pattern, unicode: unicode, dotAll: dotAll),
        _scan = RegExp(scan, unicode: unicode, dotAll: dotAll),
        _guard = null,
        _negate = false,
        _accept = accept,
        _unicode = unicode;

  GuardedRegExp._(
    String pattern,
    String scan,
    RegExp guard, {
    required bool negate,
    required bool unicode,
    required bool dotAll,
  })  : _x = RegExp(pattern, unicode: unicode, dotAll: dotAll),
        _scan = RegExp(scan, unicode: unicode, dotAll: dotAll),
        _guard = guard,
        _negate = negate,
        _accept = null,
        _unicode = unicode;

  final RegExp _x;
  final RegExp _scan;
  final RegExp? _guard;
  final bool _negate;
  final bool Function(String text, Match candidate)? _accept;
  final bool _unicode;

  bool _isHigh(int u) => u >= 0xD800 && u <= 0xDBFF;
  bool _isLow(int u) => u >= 0xDC00 && u <= 0xDFFF;

  /// Index where the character (code point in unicode mode) before [i]
  /// starts.
  int _previous(String text, int i) {
    if (_unicode &&
        i >= 2 &&
        _isLow(text.codeUnitAt(i - 1)) &&
        _isHigh(text.codeUnitAt(i - 2))) {
      return i - 2;
    }
    return i - 1;
  }

  /// Index after the character (code point in unicode mode) at [i].
  int _next(String text, int i) {
    if (_unicode &&
        i + 1 < text.length &&
        _isHigh(text.codeUnitAt(i)) &&
        _isLow(text.codeUnitAt(i + 1))) {
      return i + 2;
    }
    return i + 1;
  }

  bool _acceptAt(String text, Match m) {
    final accept = _accept;
    if (accept != null) return accept(text, m);
    final pos = m.start;
    final guarded =
        pos > 0 && _guard!.matchAsPrefix(text, _previous(text, pos)) != null;
    return _negate ? !guarded : guarded;
  }

  /// The matches the lookbehind pattern would give for
  /// `allMatches(text, start)` (the guard may look before [start]).
  Iterable<Match> allMatches(String text, [int start = 0]) sync* {
    var pos = start;
    while (pos <= text.length) {
      final Match m;
      final here = _x.matchAsPrefix(text, pos);
      if (here != null && _acceptAt(text, here)) {
        m = here;
      } else {
        final it = _scan.allMatches(text, pos).iterator;
        if (!it.moveNext()) return;
        m = _Captured(it.current);
      }
      yield m;
      pos = m.end > m.start ? m.end : _next(text, m.end);
    }
  }

  /// Whether [text] has a match.
  bool hasMatch(String text) => allMatches(text).isNotEmpty;

  /// `text.replaceAllMapped(pattern, replace)`.
  String replaceAllMapped(String text, String Function(Match m) replace) =>
      splitMapJoin(text, onMatch: replace);

  /// `text.replaceAll(pattern, replacement)` (a literal replacement).
  String replaceAll(String text, String replacement) =>
      splitMapJoin(text, onMatch: (_) => replacement);

  /// `text.splitMapJoin(pattern, onMatch: …, onNonMatch: …)`.
  String splitMapJoin(
    String text, {
    String Function(Match m)? onMatch,
    String Function(String s)? onNonMatch,
  }) {
    final out = StringBuffer();
    var last = 0;
    for (final m in allMatches(text)) {
      final gap = text.substring(last, m.start);
      out.write(onNonMatch == null ? gap : onNonMatch(gap));
      out.write(onMatch == null ? m[0] : onMatch(m));
      last = m.end;
    }
    final tail = text.substring(last);
    out.write(onNonMatch == null ? tail : onNonMatch(tail));
    return out.toString();
  }
}

/// The match of `X` captured as group 1 of a scan match: group `i` of `X`
/// is group `i + 1` of the scan.
class _Captured implements Match {
  _Captured(this._scan)
      : start = _scan.end,
        end = _scan.end + _scan.group(1)!.length;

  final Match _scan;

  @override
  final int start;

  @override
  final int end;

  @override
  String? group(int group) => _scan.group(group + 1);

  @override
  String? operator [](int group) => this.group(group);

  @override
  List<String?> groups(List<int> groupIndices) =>
      [for (final i in groupIndices) group(i)];

  @override
  int get groupCount => _scan.groupCount - 1;

  @override
  String get input => _scan.input;

  @override
  Pattern get pattern => _scan.pattern;
}
