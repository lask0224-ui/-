"""대한성서공회 사이트(www.bskorea.or.kr '성경읽기')에서 개역개정·개역한글 본문을 받아
`check_quotes.py`가 읽는 형식("삼상1:1 본문")의 txt로 저장한다.

usage:
  python3 tools/fetch_bskorea.py <out 폴더> --version GAE 삿 룻 삼상 삼하   # 책 전체
  python3 tools/fetch_bskorea.py <out 폴더> --version HAN 삿17 삼하15       # 장만
  --version: GAE = 개역개정(기준), HAN = 개역한글(강의안이 개역한글로 인용했는지 확인할 때)

- 저작권 자료이므로 받은 본문은 저장소에 넣지 않는다(작업 폴더에만 둔다).
- 사이트에 부담을 주지 않도록 장마다 2초 쉰다. 받은 장은 다시 받지 않는다(캐시).
- 각주 표시와 소제목은 본문에서 뺀다.
- 2026-10-14 확인: 사용자가 올린 개역개정 전수검증본과 이 사이트의 개역개정(GAE)이 299장 9,131절에서 글자가 같았다.
- 네트워크 정책에서 www.bskorea.or.kr 를 허용해야 한다. bible.bskorea.or.kr 는 사이트 쪽(CloudFront)에서 막는다.
"""
import argparse
import html
import os
import re
import subprocess
import time

BOOKS = [  # (약칭, 사이트 코드, 장 수)
    ("창", "gen", 50), ("출", "exo", 40), ("레", "lev", 27), ("민", "num", 36), ("신", "deu", 34),
    ("수", "jos", 24), ("삿", "jdg", 21), ("룻", "rut", 4), ("삼상", "1sa", 31), ("삼하", "2sa", 24),
    ("왕상", "1ki", 22), ("왕하", "2ki", 25), ("대상", "1ch", 29), ("대하", "2ch", 36), ("스", "ezr", 10),
    ("느", "neh", 13), ("에", "est", 10), ("욥", "job", 42), ("시", "psa", 150), ("잠", "pro", 31),
    ("전", "ecc", 12), ("아", "sng", 8), ("사", "isa", 66), ("렘", "jer", 52), ("애", "lam", 5),
    ("겔", "ezk", 48), ("단", "dan", 12), ("호", "hos", 14), ("욜", "jol", 3), ("암", "amo", 9),
    ("옵", "oba", 1), ("욘", "jnh", 4), ("미", "mic", 7), ("나", "nam", 3), ("합", "hab", 3),
    ("습", "zep", 3), ("학", "hag", 2), ("슥", "zec", 14), ("말", "mal", 4),
    ("마", "mat", 28), ("막", "mrk", 16), ("눅", "luk", 24), ("요", "jhn", 21), ("행", "act", 28),
    ("롬", "rom", 16), ("고전", "1co", 16), ("고후", "2co", 13), ("갈", "gal", 6), ("엡", "eph", 6),
    ("빌", "php", 4), ("골", "col", 4), ("살전", "1th", 5), ("살후", "2th", 3), ("딤전", "1ti", 6),
    ("딤후", "2ti", 4), ("딛", "tit", 3), ("몬", "phm", 1), ("히", "heb", 13), ("약", "jas", 5),
    ("벧전", "1pe", 5), ("벧후", "2pe", 3), ("요일", "1jn", 5), ("요이", "2jn", 1), ("요삼", "3jn", 1),
    ("유", "jud", 1), ("계", "rev", 22),
]
CODE = {a: (c, n) for a, c, n in BOOKS}


def parse(text):
    i = text.find("chapNum")
    if i < 0:
        return {}
    seg = text[i:]
    seg = re.sub(r"<div id='D_[^']*'[^>]*>.*?</div>", "", seg, flags=re.S)  # 각주 내용
    seg = re.sub(r'<a [^>]*class="?comment[^>]*>.*?</a>', "", seg, flags=re.S)  # 각주 번호
    end = seg.find("</div>")
    seg = seg[:end] if end > 0 else seg
    parts = re.split(r'<span class="number">(\d+)(?:&nbsp;)*\s*</span>', seg)
    out = {}
    for j in range(1, len(parts), 2):
        body = re.sub(r'<font class="smallTitle">.*?</font>', "", parts[j + 1], flags=re.S)
        body = html.unescape(re.sub(r"<[^>]+>", "", body))
        out[int(parts[j])] = re.sub(r"\s+", " ", body).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("targets", nargs="+", help="책 약칭(삿) 또는 장(삿17)")
    ap.add_argument("--version", default="GAE", choices=["GAE", "HAN"])
    a = ap.parse_args()
    cache = os.path.join(a.out, "_html", a.version)
    os.makedirs(cache, exist_ok=True)
    chapters = []
    for t in a.targets:
        m = re.match(r"(\D+)(\d*)$", t)
        b, c = m.group(1), m.group(2)
        if b not in CODE:
            raise SystemExit(f"모르는 책 약칭: {b}")
        chapters += [(b, int(c))] if c else [(b, k) for k in range(1, CODE[b][1] + 1)]
    lines = {}
    for b, c in chapters:
        path = os.path.join(cache, f"{b}{c}.html")
        if not (os.path.exists(path) and os.path.getsize(path) > 5000):
            url = f"https://www.bskorea.or.kr/bible/korbibReadpage.php?version={a.version}&book={CODE[b][0]}&chap={c}"
            for attempt in range(4):
                r = subprocess.run(["curl", "-sS", "-m", "40", "-o", path, "-w", "%{http_code}", url],
                                   capture_output=True, text=True)
                if r.stdout == "200" and os.path.getsize(path) > 5000:
                    break
                time.sleep(5 * (attempt + 1))
            else:
                print("받지 못함:", b, c)
                continue
            time.sleep(2)
        verses = parse(open(path, encoding="utf-8", errors="replace").read())
        lines.setdefault(b, []).extend(f"{b}{c}:{v} {t}" for v, t in sorted(verses.items()))
    for b, ls in lines.items():
        with open(os.path.join(a.out, f"{a.version}_{b}.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(ls) + "\n")
    print(a.version, len(chapters), "장 →", a.out)


if __name__ == "__main__":
    main()
