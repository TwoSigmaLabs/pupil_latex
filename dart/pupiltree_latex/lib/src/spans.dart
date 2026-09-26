/// One math-span mask for every helper that asks "is this position math?".
///
/// Every earlier implementation answered that question with `$` parity,
/// which is wrong for `$$…$$` (two `$` per delimiter), for `\$` currency,
/// and for a `$5 and $` that no renderer treats as a span, and it was O(n)
/// per query. This module computes the mask once per call from [segment],
/// the tokenizer the renderers use, so what the sanitiser believes is math
/// is exactly what will be typeset. Port of `python/pupiltree_latex/spans.py`.
library;

import 'segment.dart';

/// `mask[i]` is true when `text[i]` lies inside a closed math span
/// (delimiters included); one entry per UTF-16 unit plus a trailing false so
/// `mask[text.length]` is safe.
List<bool> mathMask(String text) {
  final mask = List<bool>.filled(text.length + 1, false);
  var pos = 0;
  for (final seg in segment(text)) {
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

/// `(start, end, display)` of every closed math span, delimiters included,
/// in order.
List<(int, int, bool)> mathRanges(String text) {
  final out = <(int, int, bool)>[];
  var pos = 0;
  for (final seg in segment(text)) {
    final length = seg.raw.length;
    if (seg.isMath) out.add((pos, pos + length, seg.display));
    pos += length;
  }
  return out;
}
