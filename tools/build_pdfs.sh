#!/usr/bin/env bash
# study-guide 의 모든 책(Markdown)을 study-guide/pdf/ 아래 같은 폴더 구조의 PDF로 만들고, 분류별 합본도 만든다.
# usage: tools/build_pdfs.sh <글꼴 폴더> [chrome 경로]
set -euo pipefail
FONTS="$1"; CHROME="${2:-}"
cd "$(dirname "$0")/.."
for f in study-guide/구약/*/*.md study-guide/신약/*/*.md; do
  [ -e "$f" ] || continue
  testament=$(basename "$(dirname "$(dirname "$f")")")
  cat=$(basename "$(dirname "$f")")
  out="study-guide/pdf/$testament/$cat/$(basename "${f%.md}").pdf"
  mkdir -p "$(dirname "$out")"
  python3 tools/md2pdf.py "$f" "$out" --fonts "$FONTS" --section "$testament · ${cat#*_}" ${CHROME:+--chrome "$CHROME"}
done
# 분류별 합본 (책이 있는 분류만)
for d in study-guide/구약/*/ study-guide/신약/*/; do
  [ -d "$d" ] && ls "$d"*.md >/dev/null 2>&1 || continue
  testament=$(basename "$(dirname "$d")")
  python3 tools/build_volume.py "$d" "study-guide/pdf/$testament/$(basename "$d")_합본.pdf" --fonts "$FONTS" ${CHROME:+--chrome "$CHROME"}
done
