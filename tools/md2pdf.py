"""학습 가이드 Markdown 한 권을 책 모양의 PDF(기본 A4, --size A5 가능)로 만든다.

usage: python3 tools/md2pdf.py <book.md> <out.pdf> --fonts <글꼴 폴더> [--section "구약 · 역사서"] [--size A4|A5] [--chrome <path>]

필요한 것
- pip: markdown-it-py, playwright, pymupdf
- Chromium (PLAYWRIGHT_BROWSERS_PATH 또는 --chrome 경로)
- 글꼴: npm의 @fontsource/noto-serif-kr, @fontsource/noto-sans-kr 패키지를 풀어 둔 폴더
  (npm pack @fontsource/noto-serif-kr @fontsource/noto-sans-kr 후 각 tgz를 tar xzf)

책으로 만들 때 원고에서 빼는 것 (사용자 결정 2026-10-08)
- 제목의 “ — N장”
- 머리 인용 가운데 표제(→ 표지)와 소개 줄(히브리 이름 등 → 본문 앞 상자)을 뺀 나머지: 구분, 사용자 지시, 원자료 노트 등
- ‘출처’·‘교정 기록’·‘확인 대기’·‘책별 파일’ 절, 표의 ‘출처’ 열
- 출처 태그 [룻] 등: 어느 강의의 견해인지를 나타내는 자리(항목·칸 맨 앞, 표 머리, 조사가 붙은 곳)는
  강의 이름(LABELS)으로 바꾸고, 문장 끝의 출처 표시는 지운다
- 저장소 파일 이름(`18_욥기.md`)은 책 이름(욥기)으로, README를 가리키는 줄은 뺀다
그 밖의 본문은 바꾸지 않는다.
"""
import argparse
import glob
import html
import os
import re
import sys

import pymupdf
from markdown_it import MarkdownIt

MARKER_CLASSES = [
    ("정리자", "m-ed"),
    ("일반 해석", "m-gen"),
    ("강의안 빈칸", "m-blank"),
    ("강의 질문", "m-blank"),
    ("확인 대기", "m-wait"),
]

MARK_RE = re.compile(r"〔([^〕]{1,60})〕")
REF_RE = re.compile(r"\d+:\d+[ab]?(?:[–\-~](?:[가-힣]{1,2} ?)?\d+(?::\d+)?[ab]?)?")

CSS_TEMPLATE = r"""
@page { size: @@size@@; margin: @@mt@@ @@ms@@ @@mb@@ @@ms@@; }
:root { --ink:#222019; --muted:#77736a; --rule:#d8d1c2; --accent:#6b3f1d; --tint:#f6f2ea;
        --ed:#2c5d82; --gen:#3b6b3f; --blank:#8a5a00; --wait:#9b2f2a; }
html { font-size: @@base@@; }
body { font-family:'Noto Serif KR',serif; color:var(--ink); line-height:1.78; margin:0; background:#fff;
       word-break:normal; line-break:strict; overflow-wrap:break-word; text-align:justify;
       orphans:2; widows:2; }
h2, h3, h4, th, .mk, .lead { font-family:'Noto Sans KR',sans-serif; }

/* 표지 */
.cover { height: @@cover_h@@; display:flex; flex-direction:column; break-after:page; text-align:center; }
.cover .series { margin-top: @@cover_top@@; font-family:'Noto Sans KR',sans-serif; font-size:7.5pt; letter-spacing:.35em; color:var(--muted); }
.cover .orn { margin: 6mm auto; width: 26mm; border-top: 1px solid var(--accent); position: relative; }
.cover .orn::after { content:"✦"; position:absolute; left:50%; top:-2.6mm; transform:translateX(-50%);
                     background:#fff; padding:0 1.5mm; color:var(--accent); font-size:7pt; }
.cover h1 { font-size: @@h1@@; font-weight:700; letter-spacing:.06em; margin:0; line-height:1.3; }
.cover .en { font-size: 11pt; color:var(--muted); font-style:italic; margin-top:1.5mm; letter-spacing:.08em; }
.cover .en.ko { font-style:normal; letter-spacing:.02em; }
.cover .motto { margin: 8mm @@toc_side@@ 0; font-size: 10.5pt; line-height:1.8; color:var(--accent); text-align:center; }
.cover .toc { margin: auto @@toc_side@@ 0; text-align:left; font-size:8.6pt; line-height:2.05; }
.cover .toc .tt { font-family:'Noto Sans KR',sans-serif; font-size:7.5pt; letter-spacing:.3em; color:var(--muted);
                  border-bottom:1px solid var(--rule); padding-bottom:1mm; margin-bottom:1.5mm; }
.cover .toc .row { display:flex; align-items:baseline; }
.cover .toc .row .dots { flex:1; border-bottom:1px dotted var(--rule); margin:0 2mm; transform:translateY(-1mm); }

/* 본문: 장 → 절 → 소제목 → 문단 순으로 간격이 줄어들게 */
h2 { font-size:13pt; font-weight:700; color:var(--accent); margin:9mm 0 4mm; padding-bottom:2mm;
     border-bottom:1.2px solid var(--accent); break-after:avoid; text-align:left; line-height:1.4; }
h2:first-child { margin-top:0; }
h2 .no { display:inline-block; min-width:7mm; font-family:'Noto Serif KR',serif; }
h2 .no.lec { min-width:0; margin-right:3mm; }
h3 { font-size:10.4pt; font-weight:700; margin:6.5mm 0 2.2mm; break-after:avoid; text-align:left; line-height:1.5; }
h3::before { content:"■"; color:var(--accent); font-size:6.5pt; vertical-align:1.5px; margin-right:1.6mm; }
h4 { font-size:9.6pt; margin:4mm 0 1.5mm; break-after:avoid; }
p { margin:1.6mm 0; }
/* 굵은 글씨만 있는 짧은 문단(“읽을 때 볼 점”, “내증 …”)은 작은 소제목으로 */
p.lead { font-size:8.4pt; font-weight:700; color:var(--accent); letter-spacing:.03em; margin:4.2mm 0 1.2mm;
         break-after:avoid; text-align:left; }
ul, ol { margin:1mm 0 2.4mm; padding-left:4.6mm; }
li { margin:.9mm 0; padding-left:.4mm; text-align:left; }  /* 목록은 왼쪽 정렬: 짧은 줄이 벌어지지 않게 */
li::marker { color:var(--accent); font-size:.85em; }
li > ul, li > ol { margin:.6mm 0 .8mm; padding-left:4.2mm; }
li li { font-size:.97em; }
strong { font-weight:700; }
hr { display:none; }
blockquote { margin:3mm 6mm; padding:0; border:none; text-align:center; color:var(--accent); }
code { font-family:'Noto Sans KR',monospace; font-size:7.6pt; color:var(--muted); }

/* 표: 위아래 선만, 본문보다 한 단계 작게 */
table { width:100%; border-collapse:collapse; margin:2.6mm 0 3.6mm; font-size:8.1pt; line-height:1.6; text-align:left;
        border-top:1.2px solid var(--ink); border-bottom:1.2px solid var(--ink);
        word-break:keep-all; }  /* 표 칸에서는 낱말을 쪼개지 않음 */
th { font-weight:700; font-size:7.8pt; border-bottom:.8px solid var(--ink); padding:1.3mm 1.6mm; vertical-align:bottom; }
td { border-bottom:.4px solid var(--rule); padding:1.3mm 1.6mm; vertical-align:top; }
td:first-child { white-space:normal; min-width:14mm; }
tr:last-child td { border-bottom:none; }
tr { break-inside:avoid; }
thead { display:table-header-group; }
table.keep { break-inside:avoid; }  /* 짧은 표는 쪽 사이에서 나누지 않음 */

/* 꼬리표: 작은 색 글씨 */
.mk { font-size:6.8pt; white-space:nowrap; letter-spacing:-.01em; }
.mk::before { content:"〔"; } .mk::after { content:"〕"; }
.m-ed { color:var(--ed); } .m-gen { color:var(--gen); } .m-blank { color:var(--blank); } .m-wait { color:var(--wait); }
.m-other { color:var(--muted); }
.ref { white-space:nowrap; }
/* 도식(``` 블록)은 본문 글씨로 가운데에 */
pre { display:table; margin:3mm auto; break-inside:avoid; font-family:'Noto Serif KR',serif; font-size:9.5pt; line-height:1.7; color:var(--ink); }
pre code { font-family:inherit; font-size:inherit; color:inherit; }
.intro { background:var(--tint); border-left:2px solid var(--accent); padding:2.5mm 4mm; margin:0 0 6mm; text-align:left; }
.intro p { margin:.8mm 0; }
"""

# 판형별 값. CSS의 pt 값은 모두 scale만큼 키운다(@@…@@ 자리는 그대로).
PRESETS = {
    "A4": dict(size="A4", mt="22mm", mb="24mm", ms="24mm", base="10.6pt", cover_h="250mm",
               cover_top="40mm", h1="34pt", toc_side="20mm", scale=1.13),
    "A5": dict(size="A5", mt="17mm", mb="19mm", ms="16mm", base="9.4pt", cover_h="172mm",
               cover_top="20mm", h1="27pt", toc_side="6mm", scale=1.0),
}


def css_for(size):
    v = PRESETS[size]
    # 모든 pt 값을 판형 비율만큼 키운 뒤, 판형별로 정한 값(@@…@@)을 넣는다
    css = re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * v['scale']:.2f}pt", CSS_TEMPLATE)
    return re.sub(r"@@(\w+)@@", lambda m: str(v[m.group(1)]), css)



def font_css(font_dir):
    parts = []
    for fam in ("noto-serif-kr", "noto-sans-kr"):
        hits = glob.glob(os.path.join(font_dir, f"fontsource-{fam}-*", "package"))
        if not hits:
            sys.exit(f"글꼴 패키지를 찾지 못함: {fam} in {font_dir}")
        base = "file://" + os.path.abspath(hits[0])
        for w in ("400", "700"):
            css = open(os.path.join(hits[0], f"{w}.css"), encoding="utf-8").read()
            parts.append(css.replace("url(./files/", f"url({base}/files/"))
    return "\n".join(parts)


# 출처 약칭 → 책에 쓸 강의 이름. 태그가 ‘어느 강의의 견해인지’를 나타내는 자리(항목·칸 맨 앞,
# 표 머리, 조사가 붙은 곳)에서만 이 이름으로 바꾸고, 문장 끝의 출처 표시는 지운다.
LABELS = {
    "창A": "2024 창세기 강의", "창B": "2025 창세기 강의",
    "출A": "출애굽기 강의(남영남)", "출B": "2025 출애굽기 강의",
    "레A": "2023 레위기 강의", "레B": "레위기 강의(더바미)", "레위": "레위 지파 도표",
    "민": "민수기 강의", "신": "신명기 표",
    "수A": "여호수아 슬라이드", "수B": "여호수아 유인물",
    "삿A": "2023 사사기 강의", "삿B": "2025 사사기 강의", "병행": "사사기·사무엘 병행 도표",
    "룻": "룻기 강의", "삼": "사무엘 강의",
    "왕A": "열왕기 BRI 강의", "왕B": "열왕기 ‘다윗과 솔로몬’ 강의", "왕학1": "열왕기 유인물 1", "왕학2": "열왕기 유인물 2",
    "대": "역대기 강의", "스느": "에스라·느헤미야 강의", "에": "에스더 강의",
    "욥": "욥기 강의", "시": "시편 유인물", "시25": "2025 시편 강의", "시1-3": "시편 1~3권 연구",
    "잠": "잠언 강의", "전": "전도서 강의", "아": "아가 강의", "아·손글씨": "아가 강의 손글씨 메모",
    "단": "다니엘 강의", "애": "예레미야애가 강의", "렘B": "예레미야 강의", "말": "말라기 강의",
    "마": "마태복음 강의", "막": "마가복음 강의", "TBS4": "사도행전 강의", "소개관": "소예언서 개관",
}
DROP_SECTIONS = r"(?:출처|교정 기록|확인 대기|책별 파일)"
# 출처 태그 = 알려진 약칭으로 시작하는 대괄호: [룻] [룻 구조] [창B p20] [창B p58, 창A p62] [출B 각 재앙 표 + 출A]
KEYS = "|".join(re.escape(k) for k in sorted(LABELS, key=len, reverse=True))
TAG = rf"\[(?:{KEYS})(?:[ ,·+][^\]\n]{{0,40}})?\]"
TAG_RE = re.compile(TAG)
KEY_RE = re.compile(rf"(?<![가-힣A-Za-z0-9])(?:{KEYS})(?![A-Za-z0-9가-힣])")


def labels(tags):
    """[창B p58, 창A p62] → ‘2025 창세기 강의·2024 창세기 강의’ (쪽 번호 등 뒤의 말은 버림)."""
    keys = []
    for t in TAG_RE.findall(tags):
        inner = t[1:-1]
        keys += [inner.split(" ")[0].split(",")[0]] + KEY_RE.findall(inner[len(inner.split(" ")[0]):])
    return "·".join(dict.fromkeys(LABELS.get(k, k) for k in keys if k))


def strip_sources(md_text):
    md_text = re.sub(rf"\n## \d+\. {DROP_SECTIONS}[^\n]*\n.*?(?=\n## |\Z)", "\n", md_text, flags=re.S)
    lines = md_text.split("\n")
    out = []
    for i, line in enumerate(lines):
        is_head = line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[-| :]+\|\s*$", lines[i + 1])
        if is_head:
            # 표 머리: 칸 맨 앞의 태그는 강의 이름, 칸 중간의 태그는 (강의 이름)
            def head_cell(c):
                c2 = re.sub(rf"^(\s*)((?:{TAG})+)", lambda m: m.group(1) + labels(m.group(2)), c)
                c2 = re.sub(rf"\s*\(((?:{TAG}\s*)+)\)", lambda m: f" ({labels(m.group(1))})", c2)
                c2 = re.sub(rf"\s*((?:{TAG})+)", lambda m: f" ({labels(m.group(1))})", c2)
                # “2025 창세기 강의 2025”처럼 연도가 겹치면 뒤의 것을 지움
                return re.sub(r"(\d{4})(.*?)\s+\1\s*$", r"\1\2 ", c2)
            out.append("|".join(head_cell(c) for c in line.split("|")))
            continue
        # 항목·칸 맨 앞, “/ ” 뒤의 태그 → “강의 이름:”
        line = re.sub(rf"(^\s*(?:[-*]|\d+\.)\s+|\|\s*|/\s+)((?:{TAG}[·, ]*)+)(?![가-힣])(:?)\s*(?=\S)",
                      lambda m: f"{m.group(1)}{labels(m.group(2))}: ", line)
        # 조사가 붙은 태그 → 강의 이름
        line = re.sub(rf"((?:{TAG})+)(?=[가-힣])", lambda m: labels(m.group(1)), line)
        # 나머지 태그는 지움
        line = re.sub(rf"\(((?:{TAG}\s*)+)", "(", line)
        line = re.sub(rf"[ \t]*(?:{TAG})+", "", line)
        line = re.sub(r"\s?\(\)", "", line)  # 태그를 지우고 남은 빈 괄호만 (원고의 빈칸 “( )”는 그대로)
        out.append(line)
    md_text = "\n".join(out)
    # 저장소 안의 파일 이름 → 책 이름, README를 가리키는 줄은 뺌
    md_text = re.sub(r"^.*README\.md.*\n?", "", md_text, flags=re.M)
    md_text = re.sub(r"`(?:[^`]*/)?(\d+)_([^`/]+?)\.md`", lambda m: book_name(m.group(1), m.group(2)), md_text)
    md_text = re.sub(r"\s?\(\)", "", md_text)
    # 책에서 뺀 절(교정 기록·확인 대기)을 가리키는 꼬리만 지운다. 앞의 내용(“강의안은 …으로 적었다”)은 남김
    md_text = re.sub(r"\s*—\s*교정 기록(?:\s*[①-⑳]+|\s*참고)", "", md_text)
    md_text = re.sub(r"\s*\(\s*교정 기록\s*[①-⑳]+\s*\)", "", md_text)
    md_text = re.sub(r"\s*\(‘\d+\. 확인 대기’[^()]*\)", "", md_text)
    # 제목 줄의 작업 메모 “(… 이미지로 확인)” 같은 괄호는 뺌
    md_text = re.sub(r"^(#+ .*?)\s*\([^()]*확인[^()]*\)", r"\1", md_text, flags=re.M)
    return md_text


def book_name(num, stem):
    if stem.endswith("_개관"):
        return stem[:-3].replace("_", " ") + " 개관"
    return stem.replace("_", "·")


def drop_source_columns(body_html):
    """머리칸이 ‘출처’인 표의 열을 뺀다."""
    def fix(table):
        heads = re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)
        idx = [i for i, h in enumerate(heads) if re.sub(r"<[^>]+>", "", h).strip() == "출처"]
        if not idx:
            return table
        def cut(row):
            cells = re.findall(r"<t[hd][^>]*>.*?</t[hd]>", row, re.S)
            keep = [c for i, c in enumerate(cells) if i not in idx]
            return re.sub(r"(<tr>).*(</tr>)", lambda m: m.group(1) + "\n" + "\n".join(keep) + "\n" + m.group(2), row, flags=re.S)
        return re.sub(r"<tr>.*?</tr>", lambda m: cut(m.group(0)), table, flags=re.S)
    return re.sub(r"<table>.*?</table>", lambda m: fix(m.group(0)), body_html, flags=re.S)


def decorate(html_text):
    out = []
    for piece in re.split(r"(<[^>]+>)", html_text):
        if piece.startswith("<"):
            out.append(piece)
            continue

        def mark(m):
            label = m.group(1)
            cls = next((c for k, c in MARKER_CLASSES if label.startswith(k)), "m-other")
            return f'<span class="mk {cls}">{label}</span>'

        piece = MARK_RE.sub(mark, piece)
        # 장절 표기(1:19–21, 4:17–22, 3:14b–15)는 줄 끝에서 끊지 않는다
        piece = REF_RE.sub(lambda m: f'<span class="ref">{m.group(0)}</span>', piece)
        out.append(piece)
    return "".join(out)


def bold_fix(md_text):
    # CommonMark은 “**…)**의”처럼 닫는 ** 앞이 문장부호이고 뒤가 한글이면 굵게 처리하지 않는다.
    def bold(line):
        segs = re.split(r"(`[^`]*`)", line)
        return "".join(x if x.startswith("`") else re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", x) for x in segs)
    return "\n".join(bold(l) for l in md_text.split("\n"))


MOTTO_LABELS = ("이 책의 표제", "이 책의 두 표제", "두 표제", "표제 구절", "표제")
INTRO_LABELS = ("히브리 이름", "이름", "네 동사로 읽는 책", "강의의 방식")


def prepare(md_text):
    """원고 → (제목, 부제, 표제, 머리 소개 줄들, 본문 Markdown)"""
    m = re.match(r"# (.+?)\n", md_text)
    title_line = m.group(1) if m else "학습 가이드"
    md_text = md_text[m.end():] if m else md_text
    # “ — 4장”, “ — 31장 + 24장”, “ — 150편”은 빼고, 개관의 “ — 여호수아 ~ 에스더 (12권)”는 부제로
    title_line = re.sub(r"\s*—\s*[\d\s장편+]+$", "", title_line)
    sub = ""
    if " — " in title_line:
        title_line, sub = title_line.split(" — ", 1)
    t = re.match(r"(.+?)\s*\(([A-Za-z0-9 &–\-]+)\)\s*$", title_line)
    title, en = (t.group(1), t.group(2)) if t else (title_line, sub)
    # 머리 인용: 표제는 표지로, 소개 줄은 본문 앞 상자로, 나머지(구분·사용자 지시·원자료 노트 등)는 뺌
    head = re.match(r"\A\s*((?:>[^\n]*\n|[ \t]*\n)+)\s*(?:---\s*\n)?", md_text)
    motto, intro = "", []
    if head:
        md_text = md_text[head.end():]
        for line in head.group(1).splitlines():
            body = line[1:].strip()
            lm = re.match(r"\*\*(.+?)\*\*\s*:\s*(.+)$", body)
            if not lm:
                continue
            key, val = lm.group(1).strip(), lm.group(2)
            if key in MOTTO_LABELS and not motto:
                motto = val
            elif key in INTRO_LABELS:
                intro.append(f"**{key}**: {val}")
    md_text = strip_sources(md_text)
    motto = strip_sources(motto).strip()
    intro = [strip_sources(x).strip() for x in intro]
    return title, en, motto, intro, md_text


def render_inline(md, s):
    return md.renderInline(bold_fix(s))


def build_html(md_text, section, font_dir, toc_pages=None, size="A4", series="성경 학습 가이드"):
    title, en, motto, intro, body_md = prepare(md_text)
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = md.render(bold_fix(body_md))
    if intro:
        body = '<div class="intro">' + "".join(f"<p>{render_inline(md, x)}</p>" for x in intro) + "</div>" + body
    body = drop_source_columns(body)
    body = re.sub(r"<table>(.*?)</table>",
                  lambda m: ('<table class="keep">' if m.group(1).count("<tr>") <= 11 else "<table>") + m.group(1) + "</table>",
                  body, flags=re.S)
    body = decorate(body)
    body = re.sub(r"<p>(<strong>[^<]{1,40}</strong>)</p>", r'<p class="lead">\1</p>', body)
    body = re.sub(r"<h2>(\d+)\.\s*", r'<h2><span class="no">\1</span>', body)
    body = re.sub(r"<h2>(\d+강)\s+", r'<h2><span class="no lec">\1</span>', body)
    heads = [re.sub(r"<span class=\"mk[^>]*>.*?</span>|<[^>]+>", " ", h).split(None, 1) for h in re.findall(r"<h2>(.*?)</h2>", body, re.S)]
    toc_rows = []
    for i, (no, name) in enumerate(heads):
        name = re.sub(r"\s+", " ", name).strip()
        pg = toc_pages[i] if toc_pages and i < len(toc_pages) else ""
        label_txt = f"{no}. {name}" if no.isdigit() else f"{no} {name}"
        toc_rows.append(f'<div class="row"><span>{html.escape(label_txt)}</span>'
                        f'<span class="dots"></span><span>{pg}</span></div>')
    cover = (
        '<section class="cover">'
        f'<div class="series">{html.escape(series)} · {html.escape(section)}</div>'
        '<div class="orn"></div>'
        f"<h1>{html.escape(title)}</h1>"
        + (f'<div class="en{" ko" if re.search("[가-힣]", en) else ""}">{html.escape(en)}</div>' if en else "")
        + (f'<div class="motto">{decorate(render_inline(md, motto))}</div>' if motto else "")
        + '<div class="toc"><div class="tt">차례</div>' + "".join(toc_rows) + "</div></section>"
    )
    head = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{font_css(font_dir)}\n{css_for(size)}</style></head><body>")
    return head + cover + "</body></html>", head + body + "</body></html>", title, [h[1] for h in heads]


def to_pdf(browser, html_doc, path, footer, size="A4"):
    tmp = os.path.splitext(path)[0] + ".tmp.html"
    open(tmp, "w", encoding="utf-8").write(html_doc)
    page = browser.new_page()
    page.goto("file://" + os.path.abspath(tmp))
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)
    v = PRESETS[size]
    opts = dict(path=path, format=size, print_background=True,
                margin={"top": v["mt"], "bottom": v["mb"], "left": v["ms"], "right": v["ms"]})
    if footer:
        opts.update(display_header_footer=True, header_template="<span></span>", footer_template=footer)
    page.pdf(**opts)
    page.close()
    os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("pdf")
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--section", default="구약")
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--size", choices=sorted(PRESETS), default="A4")
    ap.add_argument("--series", default="성경 학습 가이드")
    a = ap.parse_args()
    src = open(a.md, encoding="utf-8").read()

    from playwright.sync_api import sync_playwright

    footer = ('<div style="width:100%;text-align:center;font-size:7.5pt;color:#77736a;'
              'font-family:\'DejaVu Serif\',serif;">— <span class="pageNumber"></span> —</div>')
    base = os.path.splitext(a.pdf)[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        cover_html, body_html, title, heads = build_html(src, a.section, a.fonts, size=a.size, series=a.series)
        to_pdf(browser, body_html, base + ".body.pdf", footer, a.size)
        # 차례의 쪽 번호: 본문 PDF에서 각 절 제목이 처음 나오는 쪽
        body = pymupdf.open(base + ".body.pdf")
        pages = []
        for name in heads:
            key = re.sub(r"\s+", " ", name).strip()[:12]
            pages.append(next((i + 1 for i, pg in enumerate(body) if pg.search_for(key)), ""))
        cover_html, _, _, _ = build_html(src, a.section, a.fonts, pages, a.size, a.series)
        to_pdf(browser, cover_html, base + ".cover.pdf", None, a.size)
        browser.close()
    out = pymupdf.open(base + ".cover.pdf")
    out.insert_pdf(body)
    out.set_metadata({"title": title, "subject": f"성경 학습 가이드 · {a.section}"})
    out.save(a.pdf)
    body.close()
    for f in (base + ".body.pdf", base + ".cover.pdf"):
        os.remove(f)
    print(a.pdf, out.page_count if not out.is_closed else "")


if __name__ == "__main__":
    main()
