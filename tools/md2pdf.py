"""학습 가이드 Markdown 한 권을 인쇄용 PDF(A4)로 만든다.

usage: python3 tools/md2pdf.py <book.md> <out.pdf> --fonts <fontsource 디렉터리> [--section "구약 · 역사서"]

필요한 것
- pip: markdown-it-py, playwright
- Chromium (PLAYWRIGHT_BROWSERS_PATH 또는 --chrome 경로)
- 글꼴: npm의 @fontsource/noto-serif-kr, @fontsource/noto-sans-kr 패키지를 풀어 둔 디렉터리
  (npm pack @fontsource/noto-serif-kr @fontsource/noto-sans-kr 후 tar xzf)

본문 내용은 바꾸지 않는다. 표시만 다르게 한다:
- 출처 태그 [룻] [룻 구조] 등은 작은 회색 글씨
- 〔정리자 해석〕 〔일반 해석〕 〔강의안 빈칸 …〕 〔확인 대기 …〕 등은 색 있는 꼬리표
- 저장소 안 경로를 가리키는 마지막 줄 “원자료 노트”는 인쇄본에서 뺀다
"""
import argparse
import datetime
import glob
import html
import os
import re
import sys

from markdown_it import MarkdownIt

MARKER_CLASSES = [
    ("정리자", "m-ed"),
    ("일반 해석", "m-gen"),
    ("강의안 빈칸", "m-blank"),
    ("강의 질문", "m-blank"),
    ("확인 대기", "m-wait"),
    ("교정", "m-wait"),
]

CSS = r"""
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
:root {
  --ink: #1d1d1f; --muted: #6b6b70; --rule: #d9d6cf; --head-bg: #f3efe6;
  --accent: #7a4b1f; --ed: #1f5f8b; --ed-bg: #e8f1f8; --gen: #2f6b3a; --gen-bg: #e9f4ea;
  --blank: #8a5a00; --blank-bg: #fbf1dc; --wait: #a1302b; --wait-bg: #fbe8e6;
}
html { font-size: 10pt; }
body { font-family: 'Noto Serif KR', serif; color: var(--ink); line-height: 1.62;
       margin: 0; word-break: keep-all; overflow-wrap: break-word; background: #fff; }
h1, h2, h3, h4, th, .cover-kicker, .legend, .src, .mk { font-family: 'Noto Sans KR', sans-serif; }
.cover-kicker { color: var(--accent); font-size: 9pt; letter-spacing: .08em; margin: 0 0 2mm; }
h1 { font-size: 22pt; line-height: 1.25; margin: 0 0 4mm; padding-bottom: 3mm; border-bottom: 2px solid var(--accent); }
h2 { font-size: 14pt; color: var(--accent); margin: 8mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1px solid var(--rule);
     break-after: avoid; }
h3 { font-size: 11.5pt; margin: 6mm 0 2mm; break-after: avoid; }
h4 { font-size: 10.5pt; margin: 4mm 0 1.5mm; break-after: avoid; }
p { margin: 1.5mm 0; }
ul, ol { margin: 1mm 0 2mm; padding-left: 6mm; }
li { margin: .6mm 0; }
li > ul, li > ol { margin: .5mm 0; }
strong { font-weight: 700; }
hr { display: none; }
blockquote { margin: 2mm 0; padding: 2mm 4mm; background: var(--head-bg); border-left: 3px solid var(--accent); }
blockquote p { margin: .8mm 0; }
code { font-family: 'Noto Sans KR', monospace; font-size: 8.5pt; color: var(--muted); }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm; font-size: 9pt; line-height: 1.5; }
th, td { border: 1px solid var(--rule); padding: 1.4mm 2mm; vertical-align: top; text-align: left; }
th { background: var(--head-bg); font-weight: 700; }
tr { break-inside: avoid; }
thead { display: table-header-group; }
.src { font-size: 7.5pt; color: var(--muted); white-space: nowrap; }
.mk { font-size: 7.5pt; padding: .2mm 1.2mm; border-radius: 1mm; white-space: nowrap; }
.m-ed { color: var(--ed); background: var(--ed-bg); }
.m-gen { color: var(--gen); background: var(--gen-bg); }
.m-blank { color: var(--blank); background: var(--blank-bg); }
.m-wait { color: var(--wait); background: var(--wait-bg); }
.m-other { color: var(--muted); background: #eeeeee; }
.legend { font-size: 8pt; color: var(--muted); border: 1px solid var(--rule); border-radius: 1.5mm;
          padding: 2mm 3mm; margin: 3mm 0 5mm; line-height: 1.8; }
.legend b { color: var(--ink); }
"""

SRC_RE = re.compile(r"\[(?:[가-힣A-Za-z0-9·\-]{1,8})(?: [가-힣]{1,6})?\]")
MARK_RE = re.compile(r"〔([^〕]{1,60})〕")


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


def decorate(html_text):
    """텍스트 노드 안의 출처 태그와 꼬리표에만 span을 씌운다."""
    out = []
    for piece in re.split(r"(<[^>]+>)", html_text):
        if piece.startswith("<"):
            out.append(piece)
            continue
        piece = SRC_RE.sub(lambda m: f'<span class="src">{m.group(0)}</span>', piece)

        def mark(m):
            label = m.group(1)
            cls = next((c for k, c in MARKER_CLASSES if label.startswith(k)), "m-other")
            return f'<span class="mk {cls}">{label}</span>'

        piece = MARK_RE.sub(mark, piece)
        out.append(piece)
    return "".join(out)


def build_html(md_text, section, font_dir):
    md_text = re.sub(r"\n> 원자료 노트:[^\n]*\n?", "\n", md_text)
    # CommonMark은 “**…)**의”처럼 닫는 ** 앞이 문장부호이고 뒤가 한글이면 굵게 처리하지 않는다.
    # 한 줄 안의 ** 쌍을 미리 <strong>으로 바꿔 둔다(코드 구간 `…`은 건드리지 않음).
    def bold(line):
        segs = re.split(r"(`[^`]*`)", line)
        return "".join(x if x.startswith("`") else re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", x) for x in segs)
    md_text = "\n".join(bold(l) for l in md_text.split("\n"))
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(md_text)
    body = decorate(body)
    legend = (
        '<div class="legend"><b>읽는 법</b> · '
        '<span class="src">[약칭]</span> 강의 자료 출처(맨 끝 ‘출처’ 표) · '
        '<span class="mk m-ed">정리자 해석</span> 강의안에 없는, 정리자의 연결·해석 · '
        '<span class="mk m-gen">일반 해석</span> 강의안 빈칸을 일반적인 해석으로 채운 곳 · '
        '<span class="mk m-blank">강의안 빈칸</span> 강의안에 답이 비어 있던 곳'
        "</div>"
    )
    # 첫 h1 바로 위에 분류, 첫 인용 블록 뒤에 범례
    body = body.replace("<h1>", f'<p class="cover-kicker">성경 학습 가이드 · {html.escape(section)}</p><h1>', 1)
    i = body.find("</blockquote>")
    if i != -1:
        i += len("</blockquote>")
        body = body[:i] + legend + body[i:]
    title = re.search(r"<h1>(.*?)</h1>", body, re.S)
    title = re.sub(r"<[^>]+>", "", title.group(1)) if title else "학습 가이드"
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
        f"<style>{font_css(font_dir)}\n{CSS}</style></head><body>{body}</body></html>",
        title,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("pdf")
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--section", default="구약")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    doc, title = build_html(open(a.md, encoding="utf-8").read(), a.section, a.fonts)
    html_path = os.path.splitext(a.pdf)[0] + ".html"
    open(html_path, "w", encoding="utf-8").write(doc)

    from playwright.sync_api import sync_playwright

    footer = (
        '<div style="width:100%;font-size:7pt;color:#6b6b70;font-family:\'WenQuanYi Zen Hei\',sans-serif;'
        'padding:0 16mm;display:flex;justify-content:space-between;">'
        f"<span>{html.escape(title)}</span>"
        f"<span>{datetime.date.today().isoformat()} · "
        '<span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        page = browser.new_page()
        page.goto("file://" + os.path.abspath(html_path))
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)
        page.pdf(path=a.pdf, format="A4", print_background=True, display_header_footer=True,
                 header_template="<span></span>", footer_template=footer,
                 margin={"top": "18mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
        browser.close()
    os.remove(html_path)
    print(a.pdf)


if __name__ == "__main__":
    main()
