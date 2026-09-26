import 'dart:convert';

import 'package:test/test.dart';

import 'corpus_harness.dart';

String _show(Object? v) => v is String ? jsonEncode(v) : '$v';

void main() {
  final dir = corpusDir();
  for (final function in functions) {
    group(function, () {
      for (final c in loadCases(dir, function)) {
        test(c['id'] as String, () {
          final (ok, got) = check(function, c);
          expect(
            ok,
            isTrue,
            reason: 'input: ${_show(c['input'])}\n'
                'expected: ${_show(c['expected'])}\n'
                'got: ${_show(got)}',
          );
        });
      }
    });
  }
  group('must_not_change', () {
    for (final c in loadCases(dir, 'must_not_change')) {
      for (final fn in (c['functions'] as List).cast<String>()) {
        test('${c['id']} via $fn', () {
          final (ok, got) = unchanged(fn, c['input'] as String);
          expect(
            ok,
            isTrue,
            reason: 'input: ${_show(c['input'])}\ngot: ${_show(got)}',
          );
        });
      }
    }
  });
}
