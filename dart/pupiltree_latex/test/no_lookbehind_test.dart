// Flutter web compiles `RegExp` to the browser's JS `RegExp`, and Safari/iOS
// before 16.4 throws a SyntaxError on any lookbehind. `lib/` must not use
// one; `GuardedRegExp` gives the same matches with lookahead only.
@TestOn('vm')
library;

import 'dart:io';
import 'dart:math';

import 'package:pupiltree_latex/src/guarded_regexp.dart';
import 'package:test/test.dart';

void main() {
  test('no regex lookbehind anywhere in lib/', () {
    final offenders = <String>[];
    final files = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'));
    for (final file in files) {
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].contains('(?<=') || lines[i].contains('(?<!')) {
          offenders.add('${file.path}:${i + 1}: ${lines[i].trim()}');
        }
      }
    }
    expect(offenders, isEmpty, reason: offenders.join('\n'));
  });

  // The VM supports lookbehind, so the rewrite can be checked against it.
  group('GuardedRegExp matches the lookbehind pattern', () {
    String sig(Iterable<Match> ms) => [
          for (final m in ms)
            '${m.start}-${m.end}:'
                '${[for (var i = 0; i <= m.groupCount; i++) m[i]].join('|')}',
        ].join(';');

    const atoms = [
      r'\', r'\', r'$', r'$', '(', ')', '[', ']', '%', '_', '^', '0', '12',
      'a', 'ab', 'H', 'O', '²', '₂', 'α', '𝑥', '\uD835', ' ', '\n', r'\(',
      r'\)', r'\[', r'\]', r'\$', r'$$', r'\frac', r'\\frac', //
    ];
    final cases = <String, (RegExp, GuardedRegExp)>{
      'escaped backslash run': (
        RegExp(r'(?<!\\)((?:\\\\)*)\\\$'),
        GuardedRegExp.notAfter(r'\\', r'((?:\\\\)*)\\\$'),
      ),
      'guarded closer': (
        RegExp(r'(?<!\\)\\\((.+?)(?<!\\)\\\)', dotAll: true),
        GuardedRegExp.notAfter(r'\\', r'\\\((.*?[^\\])\\\)', dotAll: true),
      ),
      'unicode word guard': (
        RegExp(r'(?<![\p{L}\p{N}_])([A-Za-z0-9]+)([²₂]+)', unicode: true),
        GuardedRegExp.notAfter(
          r'\p{L}\p{N}_',
          r'([A-Za-z0-9]+)([²₂]+)',
          unicode: true,
        ),
      ),
      'positive guard': (
        RegExp(r'(?<=[A-Za-z)\]])([0-9]+)'),
        GuardedRegExp.after(r'A-Za-z)\]', '([0-9]+)'),
      ),
      'guard on one alternative': (
        RegExp(r'\$\$[\s\S]*?\$\$|(?<!\\)\$(?:\\.|[^$\n\\])+\$'),
        GuardedRegExp.custom(
          r'\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n\\])+\$',
          r'(?:(?=\$\$)|[^\\](?=\$(?!\$)))'
              r'(?=(\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\n\\])+\$))',
          accept: (text, m) =>
              m[0]!.startsWith(r'$$') ||
              m.start == 0 ||
              text[m.start - 1] != r'\',
        ),
      ),
    };
    for (final MapEntry(key: name, value: (original, guarded))
        in cases.entries) {
      test(name, () {
        final rnd = Random(7);
        for (var k = 0; k < 3000; k++) {
          final s = [
            for (var j = rnd.nextInt(24); j >= 0; j--)
              atoms[rnd.nextInt(atoms.length)],
          ].join();
          final start = rnd.nextInt(s.length + 1);
          expect(sig(guarded.allMatches(s, start)),
              sig(original.allMatches(s, start)),
              reason: s);
          expect(guarded.replaceAllMapped(s, (m) => '<${m[0]}>'),
              s.replaceAllMapped(original, (m) => '<${m[0]}>'),
              reason: s);
        }
      });
    }
  });
}
