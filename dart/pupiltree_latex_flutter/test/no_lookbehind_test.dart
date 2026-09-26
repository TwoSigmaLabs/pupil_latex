// Flutter web compiles `RegExp` to the browser's JS `RegExp`, and Safari/iOS
// before 16.4 throws a SyntaxError on any lookbehind. `lib/` must not use
// one (the core package has the same check for its own `lib/`).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

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
    expect(files, isNotEmpty);
    expect(offenders, isEmpty, reason: offenders.join('\n'));
  });
}
