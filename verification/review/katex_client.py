"""Python side of katex_server.js: `KaTeX().render(tex, display) -> (ok, error)`."""
import json, os, subprocess, atexit

HERE = os.path.dirname(os.path.abspath(__file__))


class KaTeX:
    def __init__(self):
        self.p = subprocess.Popen(
            ["node", os.path.join(HERE, "katex_server.js")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        self.cache = {}
        atexit.register(self.close)

    def render(self, tex, display=False):
        key = (tex, display)
        if key in self.cache:
            return self.cache[key]
        self.p.stdin.write(json.dumps({"tex": tex, "display": display}, ensure_ascii=False).replace("\u2028", "\u2028").replace("\u2029", "\u2029") + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        r = json.loads(line)
        res = (r["ok"], r.get("error", ""))
        self.cache[key] = res
        return res

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    k = KaTeX()
    for t in [r"\ce{H2O}", r"\pu{5 m/s}", r"\ce{SO4^{2-}}", r"\text{H_{2}O}", r"x^2", "a\nb", r"\text{a & b}", "😀", r"\frac12", r"\sqrt$2"]:
        print(k.render(t), repr(t))
