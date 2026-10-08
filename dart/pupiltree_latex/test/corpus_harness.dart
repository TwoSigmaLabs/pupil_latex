/// The shared conformance corpus (`corpus/*.json`) run against this
/// implementation. Mirrors `python/pupiltree_latex/corpus.py`: one check per
/// case, every assertion shape of spec §9.
///
/// Used by `corpus_test.dart` (one `test()` per case) and by
/// `corpus_runner.dart` (a plain script for machines without `package:test`).
library;

import 'dart:convert';
import 'dart:io';

import 'package:pupiltree_latex/pupiltree_latex.dart';

const functions = [
  'repair',
  'normalize',
  'canonicalize',
  'fix',
  'segment',
  'to_plain',
  'audit',
  'json_transport',
  'normalize_option_text',
  'needs_fix',
  'currency_spans',
  'is_plain_prose',
];
const stringFunctions = {
  'repair',
  'normalize',
  'canonicalize',
  'fix',
  'to_plain',
  'normalize_option_text',
};

/// A case's JSON object.
typedef Case = Map<String, Object?>;

/// Where `corpus/` lives: `$PUPILTREE_LATEX_CORPUS`, else two levels above
/// the package (`dart/pupiltree_latex/../../corpus`).
Directory corpusDir() {
  final env = Platform.environment['PUPILTREE_LATEX_CORPUS'];
  if (env != null && env.isNotEmpty) return Directory(env);
  final candidates = [
    Directory('../../corpus'),
    Directory('${Directory.current.path}/../../corpus'),
  ];
  for (final d in candidates) {
    if (d.existsSync()) return d;
  }
  throw StateError('corpus directory not found; set PUPILTREE_LATEX_CORPUS');
}

/// The cases of `<function>.json` this implementation must satisfy
/// (`impl` defaults to every implementation).
List<Case> loadCases(Directory dir, String function, {String impl = 'dart'}) {
  final file = File('${dir.path}/$function.json');
  if (!file.existsSync()) return const [];
  final data = jsonDecode(file.readAsStringSync()) as Map<String, Object?>;
  return [
    for (final c in (data['cases'] as List).cast<Case>())
      if (((c['impl'] as List?) ?? const ['python', 'dart', 'js'])
          .contains(impl))
        c,
  ];
}

class ParseError implements Exception {
  ParseError(this.message);
  final String message;
  @override
  String toString() => 'ParseError: $message';
}

/// The `opts.chemistry` call option of a case (default true).
bool _chemistryOpt(Case c) {
  final opts = c['opts'];
  return opts is Map ? (opts['chemistry'] as bool? ?? true) : true;
}

/// A boolean `opts` entry of a case.
bool _boolOpt(Case c, String name, bool fallback) {
  final opts = c['opts'];
  return opts is Map ? (opts[name] as bool? ?? fallback) : fallback;
}

/// The implementation's output for [c] (throws [ParseError] on failure).
Object? run(String function, Case c) {
  final inp = c['input'] as String;
  switch (function) {
    case 'repair':
      return repair(inp, guessWhitespace: c['variant'] != 'hard');
    case 'normalize':
      return normalize(
        inp,
        codeSpansAsMath: _boolOpt(c, 'code_spans_as_math', false),
      );
    case 'canonicalize':
      return canonicalize(inp, chemistry: _chemistryOpt(c));
    case 'fix':
      return fix(inp, chemistry: _chemistryOpt(c));
    case 'segment':
      return [for (final s in segment(inp)) s.toJson()];
    case 'to_plain':
      return toPlain(inp, style: (c['style'] as String?) ?? 'text');
    case 'audit':
      return auditKinds(inp);
    case 'json_transport':
      try {
        if ('${c['via'] ?? ''}'.contains('loads_model_json')) {
          return loadsModelJson(inp, lenient: _boolOpt(c, 'lenient', true));
        }
        return loadsLatexAware(inp);
      } on FormatException catch (e) {
        throw ParseError(e.message);
      }
    case 'normalize_option_text':
      return normalizeOptionText(inp, chemistry: _chemistryOpt(c));
    case 'needs_fix':
      return needsFix(inp, chemistry: _chemistryOpt(c));
    case 'currency_spans':
      return [for (final s in currencySpans(inp)) s.text];
    case 'is_plain_prose':
      return isPlainProse(inp);
  }
  throw ArgumentError.value(function, 'function');
}

/// Structural equality over decoded JSON values (maps, lists, scalars).
bool deepEquals(Object? a, Object? b) {
  if (a is Map && b is Map) {
    if (a.length != b.length) return false;
    for (final e in a.entries) {
      if (!b.containsKey(e.key) || !deepEquals(e.value, b[e.key])) return false;
    }
    return true;
  }
  if (a is List && b is List) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!deepEquals(a[i], b[i])) return false;
    }
    return true;
  }
  return a == b;
}

/// `(passed, got)` for one case.
(bool, Object?) check(String function, Case c) {
  if (c['expected_error'] == true) {
    try {
      final got = run(function, c);
      return (false, got);
    } on ParseError {
      return (true, '<error>');
    }
  }
  if (c['must_render'] == true) {
    final got = run('segment', c) as List;
    return (got.any((s) => (s as Map)['kind'] == 'math'), got);
  }
  if (c['property'] == 'idempotent') {
    final once = run(function, c);
    final twice = run(function, {...c, 'input': once});
    return (deepEquals(once, twice), (once, twice));
  }
  final Object? got;
  try {
    got = run(function, c);
  } on ParseError catch (e) {
    return (false, '<error: $e>');
  }
  if (c.containsKey('expected') && c['expected'] != null) {
    if (!deepEquals(got, c['expected'])) return (false, got);
    if (stringFunctions.contains(function) && got is String) {
      final again = run(function, {...c, 'input': got});
      if (again != got) return (false, ('not idempotent', got, again));
    }
    return (true, got);
  }
  var ok = true;
  if (c.containsKey('contains')) {
    ok = ok &&
        (c['contains'] as List)
            .every((s) => (got as String).contains(s as String));
  }
  if (c.containsKey('not_contains')) {
    ok = ok &&
        !(c['not_contains'] as List)
            .any((s) => (got as String).contains(s as String));
  }
  if (c.containsKey('kinds_include')) {
    ok = ok &&
        (c['kinds_include'] as List).every((k) => (got as List).contains(k));
  }
  if (c.containsKey('kinds_exclude')) {
    ok = ok &&
        !(c['kinds_exclude'] as List).any((k) => (got as List).contains(k));
  }
  if (c.containsKey('json_contains')) {
    for (final e in (c['json_contains'] as Map).entries) {
      final value = got is Map ? got[e.key] : null;
      ok = ok && value is String && value.contains(e.value as String);
    }
  }
  const predicateKeys = {
    'contains',
    'not_contains',
    'kinds_include',
    'kinds_exclude',
    'json_contains',
  };
  if (!predicateKeys.any(c.containsKey)) {
    return (false, '<no assertion in case>');
  }
  return (ok, got);
}

/// `must_not_change`: true when [function] leaves [inp] alone.
(bool, Object?) unchanged(String function, String inp) {
  if (function == 'segment') {
    final segs = segment(inp);
    return (
      segs.length == 1 && segs[0].kind == 'text' && segs[0].value == inp,
      [for (final s in segs) s.toJson()],
    );
  }
  if (function == 'audit') {
    final kinds = auditKinds(inp);
    return (kinds.isEmpty, kinds);
  }
  final got = run(function, {'input': inp});
  return (got == inp, got);
}
