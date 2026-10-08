"""학습 가이드 Markdown 한 권을 책 모양의 PDF(A4)로 만든다.

usage: python3 tools/md2pdf.py <book.md> <out.pdf> --fonts <글꼴 폴더> [--section "구약 · 역사서"] [--chrome <path>]

필요한 것
- pip: markdown-it-py, playwright, pymupdf
- Chromium (PLAYWRIGHT_BROWSERS_PATH 또는 --chrome 경로)
- 글꼴: npm의 @fontsource/noto-serif-kr, @fontsource/noto-sans-kr 패키지를 풀어 둔 폴더
  (npm pack @fontsource/noto-serif-kr @fontsource/noto-sans-kr 후 각 tgz를 tar xzf)

책으로 만들 때 원고에서 빼는 것 (사용자 결정 2026-10-08)
- 제목의 “ — N장”
- 머리 인용의 ‘구분’ 줄, ‘원자료 노트’ 줄
- ‘출처’ 절과 본문의 출처 태그 [룻] 등, 표의 ‘출처’ 열
  - 태그가 문장의 주어로 쓰인 곳([아]는)은 출처 표의 파일 이름으로 바꾼다(“아가서 강의는”)
  - 항목 앞의 이름표([룻]·[삼]: …)는 지운다
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

TAG = r"\[(?:[가-힣A-Za-z0-9·\-]{1,8})(?: [가-힣]{1,6}){0,3}\]"
TAG_RE = re.compile(TAG)
MARK_RE = re.compile(r"〔([^〕]{1,60})〕")

CSS = r"""
@page { size: A4; margin: 24mm 22mm 24mm 22mm; }
:root { --ink:#222019; --muted:#77736a; --rule:#cfc8b8; --accent:#6b3f1d; --tint:#f6f2ea;
        --ed:#2c5d82; --gen:#3b6b3f; --blank:#8a5a00; --wait:#9b2f2a; }
html { font-size: 10.5pt; }
body { font-family:'Noto Serif KR',serif; color:var(--ink); line-height:1.8; margin:0; background:#fff;
       word-break:normal; line-break:strict; overflow-wrap:break-word; text-align:justify; }
h2, h3, h4, th, .mk { font-family:'Noto Sans KR',sans-serif; }

/* 표지 */
.cover { height: 247mm; display:flex; flex-direction:column; break-after:page; text-align:center; }
.cover .series { margin-top: 38mm; font-family:'Noto Sans KR',sans-serif; font-size:9pt; letter-spacing:.35em; color:var(--muted); }
.cover .orn { margin: 9mm auto; width: 34mm; border-top: 1px solid var(--accent); position: relative; }
.cover .orn::after { content:"✦"; position:absolute; left:50%; top:-3.2mm; transform:translateX(-50%);
                     background:#fff; padding:0 2mm; color:var(--accent); font-size:8pt; }
.cover h1 { font-size: 34pt; font-weight:700; letter-spacing:.06em; margin:0; line-height:1.3; }
.cover .en { font-size: 13pt; color:var(--muted); font-style:italic; margin-top:2mm; letter-spacing:.08em; }
.cover .motto { margin: 10mm 18mm 0; font-size: 12pt; line-height:1.9; color:var(--accent); text-align:center; }
.cover .toc { margin: auto 22mm 6mm; text-align:left; font-size:9.5pt; line-height:2.1; }
.cover .toc .tt { font-family:'Noto Sans KR',sans-serif; font-size:8.5pt; letter-spacing:.3em; color:var(--muted);
                  border-bottom:1px solid var(--rule); padding-bottom:1mm; margin-bottom:2mm; }
.cover .toc .row { display:flex; align-items:baseline; }
.cover .toc .row .dots { flex:1; border-bottom:1px dotted var(--rule); margin:0 2mm; transform:translateY(-1mm); }

/* 본문 */
h2 { font-size:15pt; font-weight:700; color:var(--accent); margin:12mm 0 5mm; padding-bottom:2.5mm;
     border-bottom:1.5px solid var(--accent); break-after:avoid; text-align:left; }
h2 .no { display:inline-block; min-width:9mm; font-family:'Noto Serif KR',serif; }
h3 { font-size:11.5pt; font-weight:700; margin:7mm 0 2.5mm; break-after:avoid; text-align:left; }
h3::before { content:"■ "; color:var(--accent); font-size:8pt; vertical-align:2px; }
h4 { font-size:10.5pt; margin:5mm 0 1.5mm; break-after:avoid; }
p { margin:1.8mm 0; }
ul, ol { margin:1.2mm 0 2.5mm; padding-left:6mm; }
li { margin:.8mm 0; }
li::marker { color:var(--accent); }
li > ul, li > ol { margin:.6mm 0; }
strong { font-weight:700; }
hr { display:none; }
blockquote { margin:3mm 8mm; padding:0; border:none; text-align:center; color:var(--accent); }
code { font-family:'Noto Sans KR',monospace; font-size:8.5pt; color:var(--muted); }

/* 표: 위아래 선만 */
table { width:100%; border-collapse:collapse; margin:3mm 0 4mm; font-size:9.2pt; line-height:1.6; text-align:left;
        border-top:1.5px solid var(--ink); border-bottom:1.5px solid var(--ink); }
th { font-weight:700; font-size:8.8pt; border-bottom:1px solid var(--ink); padding:1.6mm 2mm; vertical-align:bottom; }
td { border-bottom:.5px solid var(--rule); padding:1.6mm 2mm; vertical-align:top; }
tr:last-child td { border-bottom:none; }
tr { break-inside:avoid; }
thead { display:table-header-group; }

/* 꼬리표: 작은 글씨, 색만 */
.mk { font-size:7.6pt; white-space:nowrap; }
.mk::before { content:"〔"; } .mk::after { content:"〕"; }
.m-ed { color:var(--ed); } .m-gen { color:var(--gen); } .m-blank { color:var(--blank); } .m-wait { color:var(--wait); }
.m-other { color:var(--muted); }
"""


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


def source_names(md_text):
    """‘출처’ 표에서 약칭 → 읽을 수 있는 이름(“아가서 강의”)."""
    names = {}
    for m in re.finditer(r"^\| (\[[^\]]+\]) \| (.+?) \|", md_text, re.M):
        cell = m.group(2)
        f = re.search(r"`([^`]+)`", cell)
        if not f:
            continue
        stem = os.path.splitext(os.path.basename(f.group(1)))[0]
        stem = re.sub(r"^\d+\.", "", stem).split("&")[0].strip()
        names[m.group(1)] = f"{stem} 강의"
    return names


def strip_sources(md_text):
    names = source_names(md_text)
    # ‘출처’ 절 통째로 (다음 ## 또는 끝까지)
    md_text = re.sub(r"\n## \d+\. 출처\n.*?(?=\n## |\Z)", "\n", md_text, flags=re.S)
    # 항목 앞 이름표: “- [룻]·[삼]: …”
    md_text = re.sub(rf"(^\s*[-*]\s+|^\s*\d+\.\s+)(?:{TAG}[·, ]*)+:\s*", r"\1", md_text, flags=re.M)
    # 주어로 쓰인 태그: “[아]는”
    md_text = re.sub(rf"({TAG})(?=[가-힣])", lambda m: names.get(m.group(1), m.group(1)), md_text)
    # 나머지 태그(앞 공백 포함). 괄호 안 맨 앞이면 뒤 공백도 지움.
    md_text = re.sub(rf"\(({TAG}\s*)+", "(", md_text)
    md_text = re.sub(rf"[ \t]*(?:{TAG})+", "", md_text)
    return md_text


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

        out.append(MARK_RE.sub(mark, piece))
    return "".join(out)


def bold_fix(md_text):
    # CommonMark은 “**…)**의”처럼 닫는 ** 앞이 문장부호이고 뒤가 한글이면 굵게 처리하지 않는다.
    def bold(line):
        segs = re.split(r"(`[^`]*`)", line)
        return "".join(x if x.startswith("`") else re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", x) for x in segs)
    return "\n".join(bold(l) for l in md_text.split("\n"))


def prepare(md_text):
    """원고 → (제목, 영문 제목, 표제, 본문 Markdown)"""
    md_text = re.sub(r"\n> 원자료 노트:[^\n]*\n?", "\n", md_text)
    m = re.match(r"# (.+?)\n", md_text)
    title_line = m.group(1) if m else "학습 가이드"
    md_text = md_text[m.end():] if m else md_text
    title_line = re.sub(r"\s*—\s*\d+\s*장\s*$", "", title_line)
    t = re.match(r"(.+?)\s*\((.+?)\)\s*$", title_line)
    title, en = (t.group(1), t.group(2)) if t else (title_line, "")
    motto = ""
    mm = re.search(r"^> \*\*이 책의 표제\*\*:\s*(.+)$", md_text, re.M)
    if mm:
        motto = mm.group(1)
    # 머리 인용(구분·표제) 줄과 그 뒤 첫 구분선 제거
    md_text = re.sub(r"\A\s*(?:>[^\n]*\n)+\s*(?:---\s*\n)?", "", md_text)
    md_text = strip_sources(md_text)
    motto = re.sub(rf"\s*{TAG}", "", motto)
    return title, en, motto, md_text


def render_inline(md, s):
    return md.renderInline(bold_fix(s))


def build_html(md_text, section, font_dir, toc_pages=None):
    title, en, motto, body_md = prepare(md_text)
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body = md.render(bold_fix(body_md))
    body = drop_source_columns(body)
    body = decorate(body)
    body = re.sub(r"<h2>(\d+)\.\s*", r'<h2><span class="no">\1</span>', body)
    heads = [re.sub(r"<[^>]+>", " ", h).split(None, 1) for h in re.findall(r"<h2>(.*?)</h2>", body, re.S)]
    toc_rows = []
    for i, (no, name) in enumerate(heads):
        name = re.sub(r"\s+", " ", name).strip()
        pg = toc_pages[i] if toc_pages and i < len(toc_pages) else ""
        toc_rows.append(f'<div class="row"><span>{html.escape(no)}. {html.escape(name)}</span>'
                        f'<span class="dots"></span><span>{pg}</span></div>')
    cover = (
        '<section class="cover">'
        f'<div class="series">성경 학습 가이드 · {html.escape(section)}</div>'
        '<div class="orn"></div>'
        f"<h1>{html.escape(title)}</h1>"
        + (f'<div class="en">{html.escape(en)}</div>' if en else "")
        + (f'<div class="motto">{decorate(render_inline(md, motto))}</div>' if motto else "")
        + '<div class="toc"><div class="tt">차례</div>' + "".join(toc_rows) + "</div></section>"
    )
    head = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{font_css(font_dir)}\n{CSS}</style></head><body>")
    return head + cover + "</body></html>", head + body + "</body></html>", title, [h[1] for h in heads]


def to_pdf(browser, html_doc, path, footer):
    tmp = os.path.splitext(path)[0] + ".tmp.html"
    open(tmp, "w", encoding="utf-8").write(html_doc)
    page = browser.new_page()
    page.goto("file://" + os.path.abspath(tmp))
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(500)
    opts = dict(path=path, format="A4", print_background=True,
                margin={"top": "24mm", "bottom": "24mm", "left": "22mm", "right": "22mm"})
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
    a = ap.parse_args()
    src = open(a.md, encoding="utf-8").read()

    from playwright.sync_api import sync_playwright

    footer = ('<div style="width:100%;text-align:center;font-size:8pt;color:#77736a;'
              'font-family:\'DejaVu Serif\',serif;">— <span class="pageNumber"></span> —</div>')
    base = os.path.splitext(a.pdf)[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        cover_html, body_html, title, heads = build_html(src, a.section, a.fonts)
        to_pdf(browser, body_html, base + ".body.pdf", footer)
        # 차례의 쪽 번호: 본문 PDF에서 각 절 제목이 처음 나오는 쪽
        body = pymupdf.open(base + ".body.pdf")
        pages = []
        for name in heads:
            key = re.sub(r"\s+", " ", name).strip()[:12]
            pages.append(next((i + 1 for i, pg in enumerate(body) if pg.search_for(key)), ""))
        cover_html, _, _, _ = build_html(src, a.section, a.fonts, pages)
        to_pdf(browser, cover_html, base + ".cover.pdf", None)
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
