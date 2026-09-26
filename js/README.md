# @pupiltree/latex (JavaScript / TypeScript)

The JS/TS port of the shared LaTeX library. `python/pupiltree_latex` is the
reference implementation and `../corpus/*.json` is the executable spec; every
behaviour here must match the corpus.

```js
import {
  fix,
  normalize,
  canonicalize,
  segment,
  toPlain,
  audit,
} from "@pupiltree/latex";
import { MathText } from "@pupiltree/latex/react"; // needs react + katex
import { typesetMath } from "@pupiltree/latex/dom"; // needs katex auto-render
```

A plain-script bundle, `dist/pupiltree-latex.iife.js`, exposes the core API
plus `typesetMath` as `window.PupiltreeLatex`.

## Browser support

| Browser       | Minimum version |
| ------------- | --------------- |
| Safari / iOS  | 14              |
| Chrome / Edge | 80 / 80         |
| Firefox       | 78              |
| Node.js       | 18              |

What sets these floors (both the ESM files and the IIFE bundle):

- `??` and `?.` (Safari 13.1, Chrome 80, Firefox 72);
- `String.prototype.matchAll` (Safari 13, Chrome 73), `globalThis`
  (Safari 12.1, Chrome 71);
- Unicode property escapes `\p{L}` with the `u` flag (Safari 11.1,
  Chrome 64, Firefox 78).

The library uses **no regex lookbehind** (which Safari/iOS only gained in
16.4): the "not after a backslash" style checks live in code
(`src/lookbehind.ts`), and `test/no-lookbehind.test.mjs` fails the build if a
lookbehind appears in `dist/`. So iPads on iOS 14 to 16.3 run the library.
Nothing newer than Safari 13.1 is used; 14 is the supported floor.

The IIFE bundle is built with those engines as esbuild's `target` and is
wrapped in `try/catch`: if it fails while initialising on an engine below the
minimum, the script logs one `console.error` and leaves
`window.PupiltreeLatex` undefined instead of throwing. Pages should still
check for it (`if (window.PupiltreeLatex) PupiltreeLatex.typesetMath(root)`);
math then shows as its source.

## React

`<MathText text={...} />` runs `fix` (or `normalize` with `mode="normalize"`)
and `segment`, memoised on the text and mode. It renders each math span with
KaTeX (`throwOnError: true` inside a try, `strict: "ignore"`,
`trust: false`). If KaTeX cannot render a span, the span is shown as its
source in `<code class="pt-math-source">`, so it never renders as nothing or
as red `katex-error` text. Style that class (for example grey monospace) in
the host app.

## Development

```sh
npm install
npm run typecheck
npm run build   # tsc → dist/, then scripts/build-iife.mjs → the IIFE bundle
npm test        # builds first, then runs the corpus and adapter tests
npm run gen-tables  # regenerate src/tables.g.ts from ../corpus/tables
```

Do not hand-edit `src/tables.g.ts`.
