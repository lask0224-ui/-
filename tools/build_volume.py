"""한 분류(예: 구약/1_모세오경)의 모든 책을 한 권의 PDF로 묶는다.

usage: python3 tools/build_volume.py <분류 폴더> <out.pdf> --fonts <글꼴 폴더> [--chrome <path>]
예:    python3 tools/build_volume.py study-guide/구약/1_모세오경 study-guide/pdf/구약/1_모세오경_합본.pdf --fonts …

- 맨 앞: 묶음 표지, 전체 차례(책과 쪽)
- 책마다: 책 표지(그 책의 차례) + 본문 — md2pdf.py와 같은 모양
- 쪽 번호는 묶음 전체에 이어서 매긴다(PDF 뷰어의 쪽 번호와 같다). 표지·차례 쪽에는 번호를 찍지 않는다.
- PDF 책갈피: 책 → 장
"""
import argparse
import glob
import html
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import md2pdf  # noqa: E402

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def front_html(vol_title, series, books, pages, font_dir, size):
    """묶음 표지 + 전체 차례 (pages: 책마다 시작 쪽)."""
    rows = "".join(
        f'<div class="row"><span>{html.escape(t)}'
        + (f' <span class="toc-en">{html.escape(en)}</span>' if en and not re.search("[가-힣]", en) else "")
        + f'</span><span class="dots"></span><span>{pg}</span></div>'
        for (t, en), pg in zip(books, pages)
    )
    names = " · ".join(t for t, _ in books if not t.endswith("개관"))
    extra = (".toc-en{color:var(--muted);font-size:.85em;font-style:italic;margin-left:1.5mm}"
             ".vol .series{margin-top:60mm}.vol h1{font-size:40pt}"
             ".vol .motto{font-size:11pt}"
             ".contents{padding-top:20mm}"
             ".contents .tt{font-family:'Noto Sans KR',sans-serif;font-size:10pt;letter-spacing:.35em;"
             "color:var(--accent);border-bottom:1.2px solid var(--accent);padding-bottom:2mm;margin-bottom:5mm}"
             ".contents .row{display:flex;align-items:baseline;font-size:12pt;line-height:2.4}"
             ".contents .row .dots{flex:1;border-bottom:1px dotted var(--rule);margin:0 3mm;transform:translateY(-1.2mm)}")
    return (
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(vol_title)}</title>'
        f"<style>{md2pdf.font_css(font_dir)}\n{md2pdf.css_for(size)}\n{extra}</style></head><body>"
        f'<section class="cover vol"><div class="series">성경 학습 가이드 · {html.escape(series)}</div>'
        f'<div class="orn"></div><h1>{html.escape(vol_title)}</h1>'
        f'<div class="motto">{html.escape(names)}</div></section>'
        f'<section class="contents"><div class="tt">차례</div>{rows}</section>'
        "</body></html>"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("pdf")
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--size", default="A4")
    a = ap.parse_args()

    folder = a.folder.rstrip("/")
    testament = os.path.basename(os.path.dirname(folder))
    cat = os.path.basename(folder).split("_", 1)[-1]
    section = f"{testament} · {cat}"
    files = sorted(glob.glob(os.path.join(folder, "*.md")))
    if not files:
        sys.exit(f"{folder}: 책이 없음 — 건너뜀")
    tmp = os.path.splitext(a.pdf)[0] + ".parts"
    os.makedirs(tmp, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome) if a.chrome else p.chromium.launch()
        # 1) 본문을 먼저 만들어 쪽 수와 장의 위치를 잰다
        books = []
        for i, f in enumerate(files):
            src = open(f, encoding="utf-8").read()
            _, body_html, title, heads = md2pdf.build_html(src, section, a.fonts, size=a.size)
            en = md2pdf.prepare(src)[1]
            body_pdf = os.path.join(tmp, f"{i:02d}.body.pdf")
            md2pdf.to_pdf(browser, body_html, body_pdf, None, a.size)
            doc = pymupdf.open(body_pdf)
            rel = []
            for name in heads:
                key = re.sub(r"\s+", " ", name).strip()[:12]
                rel.append(next((j for j, pg in enumerate(doc) if pg.search_for(key)), 0))
            books.append(dict(src=src, title=title, en=en, heads=heads, rel=rel, n=doc.page_count, body=body_pdf))
            doc.close()
        # 2) 쪽 번호 매기기: 묶음 표지(1) + 차례(2) 다음부터
        page = 3
        for b in books:
            b["cover_page"] = page
            b["start"] = page + 1
            b["abs"] = [b["start"] + r for r in b["rel"]]
            page += 1 + b["n"]
        # 3) 표지들
        for i, b in enumerate(books):
            cover_html, _, _, _ = md2pdf.build_html(b["src"], section, a.fonts, b["abs"], a.size)
            b["cover"] = os.path.join(tmp, f"{i:02d}.cover.pdf")
            md2pdf.to_pdf(browser, cover_html, b["cover"], None, a.size)
        front = os.path.join(tmp, "front.pdf")
        md2pdf.to_pdf(browser, front_html(cat, testament, [(b["title"], b["en"]) for b in books],
                                          [b["cover_page"] for b in books], a.fonts, a.size), front, None, a.size)
        browser.close()

    # 4) 합치기, 쪽 번호 찍기, 책갈피
    out = pymupdf.open(front)
    assert out.page_count == 2, f"앞부분이 {out.page_count}쪽 — 차례가 한 쪽을 넘음"
    toc = []
    numbered = []
    for b in books:
        cov = pymupdf.open(b["cover"])
        assert cov.page_count == 1, f"{b['title']} 표지가 {cov.page_count}쪽"
        out.insert_pdf(cov)
        body = pymupdf.open(b["body"])
        out.insert_pdf(body)
        numbered += range(b["start"], b["start"] + b["n"])
        toc.append([1, b["title"], b["cover_page"]])
        toc += [[2, f"{k + 1}. " + re.sub(r"\s+", " ", h).strip(), pg] for k, (h, pg) in enumerate(zip(b["heads"], b["abs"]))]
    for n in numbered:
        pg = out[n - 1]
        w, h = pg.rect.width, pg.rect.height
        text = f"— {n} —"
        tw = pymupdf.Font(fontfile=SERIF).text_length(text, fontsize=7.5)
        pg.insert_text(((w - tw) / 2, h - 30), text, fontname="dvs", fontfile=SERIF, fontsize=7.5,
                       color=(0.467, 0.451, 0.416))
    out.set_toc(toc)
    out.set_metadata({"title": cat, "subject": f"성경 학습 가이드 · {section}"})
    out.save(a.pdf, garbage=3, deflate=True)
    print(a.pdf, out.page_count)
    for f in glob.glob(os.path.join(tmp, "*")):
        os.remove(f)
    os.rmdir(tmp)


if __name__ == "__main__":
    main()
