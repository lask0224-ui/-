#!/usr/bin/env bash
# study-guide 의 모든 책(Markdown)을 study-guide/pdf/ 아래 같은 폴더 구조의 PDF로 만든다.
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
