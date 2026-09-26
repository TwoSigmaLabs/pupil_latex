/**
 * Regex lookbehind without lookbehind syntax.
 *
 * Safari / iOS below 16.4 cannot parse a lookbehind group (positive or negative), and one such
 * literal is a SyntaxError that kills the whole bundle. Every pattern that
 * used a LEADING lookbehind is now written without it, and these helpers
 * apply the lookbehind as a check on the character before the match.
 *
 * Exactness: an engine tries start positions left to right; at a position
 * where the lookbehind fails, nothing can match there, so it moves on to the
 * next position. The helpers do the same: when the match found at `p` fails
 * the check, the search restarts at `p + 1` (not at the end of the rejected
 * match, which is what `replace` with a callback would do), so overlapping
 * candidates such as `\\(` after a rejected `\(` behave exactly as before.
 */

/**
 * True when the lookbehind FAILS for the match `m` found in `text` (the
 * match is rejected). Receives the whole match so a lookbehind that guarded
 * only one alternative can be checked.
 */
export type Blocked = (text: string, m: RegExpExecArray) => boolean;

/** The code point ending just before `index` ("" at the start), as `/u` sees it. */
export function codePointBefore(text: string, index: number): string {
  if (index <= 0) return "";
  const low = text.charCodeAt(index - 1);
  if (low >= 0xdc00 && low <= 0xdfff && index >= 2) {
    const high = text.charCodeAt(index - 2);
    if (high >= 0xd800 && high <= 0xdbff) return text.slice(index - 2, index);
  }
  return text[index - 1];
}

/** A negative lookbehind for `[chars]`: rejected when the previous UTF-16 unit is one of `chars`. */
export function after(chars: string): Blocked {
  return (text, m) => m.index > 0 && chars.includes(text[m.index - 1]);
}

/**
 * A negative lookbehind for a code-point class (`/u` patterns): rejected when the
 * previous code point matches `cls` (a non-global, non-sticky regex).
 */
export function afterCodePoint(cls: RegExp): Blocked {
  return (text, m) => {
    const prev = codePointBefore(text, m.index);
    return prev !== "" && cls.test(prev);
  };
}

/** Index one position (one code point under `/u`) after `i`. */
function advance(text: string, i: number, unicode: boolean): number {
  if (unicode && i + 1 < text.length) {
    const c = text.charCodeAt(i);
    const d = text.charCodeAt(i + 1);
    if (c >= 0xd800 && c <= 0xdbff && d >= 0xdc00 && d <= 0xdfff) return i + 2;
  }
  return i + 1;
}

/**
 * The first match of the global regex `re` at or after `from` that the
 * lookbehind accepts, or null. Leaves `re.lastIndex` just after the match.
 */
export function execFrom(
  re: RegExp,
  text: string,
  from: number,
  blocked: Blocked,
): RegExpExecArray | null {
  let pos = from;
  for (;;) {
    if (pos > text.length) return null;
    re.lastIndex = pos;
    const m = re.exec(text);
    if (m === null) return null;
    if (!blocked(text, m)) {
      if (m[0].length === 0) re.lastIndex = advance(text, m.index, re.unicode);
      return m;
    }
    pos = advance(text, m.index, re.unicode);
  }
}

/** Every accepted match, like `[...text.matchAll(re)]`. */
export function matchAllAfter(
  re: RegExp,
  text: string,
  blocked: Blocked,
): RegExpExecArray[] {
  const out: RegExpExecArray[] = [];
  let pos = 0;
  let m: RegExpExecArray | null;
  while ((m = execFrom(re, text, pos, blocked)) !== null) {
    out.push(m);
    pos = re.lastIndex;
  }
  re.lastIndex = 0;
  return out;
}

/**
 * `text.replace(re, replacer)` for a global `re` whose lookbehind is
 * `blocked`. The replacer gets the same arguments as with `String.replace`
 * (match, groups…, offset, string[, named groups]).
 */
export function replaceAfter(
  text: string,
  re: RegExp,
  blocked: Blocked,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  replacer: (...args: any[]) => string,
): string {
  const matches = matchAllAfter(re, text, blocked);
  if (matches.length === 0) return text;
  let out = "";
  let last = 0;
  for (const m of matches) {
    out += text.slice(last, m.index);
    const args: unknown[] = [...m, m.index, text];
    if (m.groups !== undefined) args.push(m.groups);
    out += replacer(...args);
    last = m.index + m[0].length;
  }
  return out + text.slice(last);
}
