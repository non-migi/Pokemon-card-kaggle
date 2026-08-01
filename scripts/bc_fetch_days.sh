#!/bin/zsh
# Daily Top Episodes を日別に DL → 抽出 → 生データ削除(ディスク節約ループ)
# 使い方: zsh scripts/bc_fetch_days.sh 2026-07-01 2026-07-02 ...
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# セッション固有のscratchpadは揮発するので固定パスを使う(生データはループ内で毎回消す)
WORK="/private/tmp/ptcg-bc-daily"
mkdir -p "$WORK" "$ROOT/data/bc"
for DATE in "$@"; do
  TAG="${DATE//-/}"
  OUT="$ROOT/data/bc/pairs_${TAG:4}.jsonl.gz"   # pairs_0701.jsonl.gz 形式
  if [ -f "$OUT" ]; then
    echo "skip $DATE (既存: $OUT)"
    continue
  fi
  DIR="$WORK/$TAG"
  rm -rf "$DIR"; mkdir -p "$DIR"
  echo "=== $DATE: ダウンロード ==="
  kaggle datasets download "kaggle/pokemon-tcg-ai-battle-episodes-$DATE" -p "$DIR" --unzip >/dev/null 2>&1
  N=$(ls "$DIR" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$N" -lt 100 ]; then
    echo "!!! $DATE: ダウンロード失敗またはデータセット未公開 (files=$N)"
    rm -rf "$DIR"
    continue
  fi
  echo "=== $DATE: 抽出 ($N files) ==="
  "$ROOT/.venv/bin/python" "$ROOT/scripts/bc_extract.py" "$DIR" --out "$OUT"
  rm -rf "$DIR"
done
echo "ALL DONE"
ls -lh "$ROOT/data/bc/"
