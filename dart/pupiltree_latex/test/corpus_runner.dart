/// Run the conformance corpus without `package:test`:
///
///     dart run test/corpus_runner.dart [corpus_dir]
///
/// Prints pass/fail counts per function and the first 20 failures; exits 1
/// when anything fails.
library;

import 'dart:convert';
import 'dart:io';

import 'corpus_harness.dart';

String _show(Object? v) => v is String ? jsonEncode(v) : '$v';

void main(List<String> args) {
  final dir = args.isNotEmpty ? Directory(args[0]) : corpusDir();
  final failures = <String>[];
  var total = 0;
  void report(String function, int passed, int count) {
    stdout.writeln('${function.padRight(16)} $passed/$count');
  }

  for (final function in functions) {
    final cases = loadCases(dir, function);
    var passed = 0;
    for (final c in cases) {
      total++;
      final (ok, got) = check(function, c);
      if (ok) {
        passed++;
      } else {
        failures.add('FAIL $function/${c['id']}\n'
            '  input:    ${_show(c['input'])}\n'
            '  expected: ${_show(c['expected'])}\n'
            '  got:      ${_show(got)}');
      }
    }
    report(function, passed, cases.length);
  }
  var mncPassed = 0;
  var mncTotal = 0;
  for (final c in loadCases(dir, 'must_not_change')) {
    for (final fn in (c['functions'] as List).cast<String>()) {
      total++;
      mncTotal++;
      final (ok, got) = unchanged(fn, c['input'] as String);
      if (ok) {
        mncPassed++;
      } else {
        failures.add('FAIL must_not_change/${c['id']} via $fn\n'
            '  input: ${_show(c['input'])}\n'
            '  got:   ${_show(got)}');
      }
    }
  }
  report('must_not_change', mncPassed, mncTotal);
  for (final f in failures.take(20)) {
    stdout.writeln(f);
  }
  if (failures.length > 20) {
    stdout.writeln('... and ${failures.length - 20} more');
  }
  stdout.writeln('${total - failures.length}/$total corpus checks passed');
  exitCode = failures.isEmpty ? 0 : 1;
}
