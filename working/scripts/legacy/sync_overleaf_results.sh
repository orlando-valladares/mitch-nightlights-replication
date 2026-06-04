#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${OVERLEAF_PROJECT_ID:-6471871292xntzqtnzptkk}"
OVERLEAF_DIR="${OVERLEAF_DIR:-working/overleaf_ec64}"
DEST_DIR="${OVERLEAF_DEST_DIR:-results}"

FILES=("$@")
if [ "${#FILES[@]}" -eq 0 ]; then
  FILES=("out/results/figures/did_annual_combined_4slot.png")
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is not installed or not on PATH. Install git, then rerun this script." >&2
  exit 127
fi

if [ ! -d "$OVERLEAF_DIR/.git" ]; then
  mkdir -p "$(dirname "$OVERLEAF_DIR")"
  git clone "https://git.overleaf.com/${PROJECT_ID}" "$OVERLEAF_DIR"
fi

git -C "$OVERLEAF_DIR" pull --ff-only
mkdir -p "$OVERLEAF_DIR/$DEST_DIR"

changed=0
for src in "${FILES[@]}"; do
  if [ ! -f "$src" ]; then
    echo "Missing source file: $src" >&2
    exit 1
  fi
  dest="$OVERLEAF_DIR/$DEST_DIR/$(basename "$src")"
  cp "$src" "$dest"
  git -C "$OVERLEAF_DIR" add "$DEST_DIR/$(basename "$src")"
  changed=1
done

if [ "$changed" -eq 1 ] && ! git -C "$OVERLEAF_DIR" diff --cached --quiet; then
  git -C "$OVERLEAF_DIR" commit -m "Update generated ECON64 results"
  git -C "$OVERLEAF_DIR" push
else
  echo "No Overleaf changes to push."
fi
