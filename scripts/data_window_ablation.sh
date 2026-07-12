#!/bin/zsh
# データ窓のアブレーション: 「最新から何日分が最適か」「直近と古い日でどちらが効くか」を調べる。
# 各窓でBCを学習し、共通基準 v3.3g(bc_v2=10日, multi-select, オーロンゲ)に対してA/B。
# 全モデルmulti-select込み・bc-mode・同デッキ(meta_01)なので、差は「データ窓」だけに帰着する。
#
# 使い方: zsh scripts/data_window_ablation.sh
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
ABL="/private/tmp/claude-501/-Users-non-git-Pokemon-card-kaggle/b1969d4e-1f95-4647-9a92-c80a416a00ba/scratchpad/abl"
mkdir -p "$ABL"
cd "$ROOT"

# 窓の定義: 名前 → 日付リスト(最新=0711)。直近N日 と 古い側の対照。
typeset -A WINDOWS
WINDOWS[last2]="0710 0711"
WINDOWS[last4]="0708 0709 0710 0711"
WINDOWS[last6]="0706 0707 0708 0709 0710 0711"
WINDOWS[first4]="0701 0702 0703 0704"   # last4と同サイズ・古い側 = 直近性の対照

REF="build/v3.3g"   # 基準: bc_v2(10日) + multi-select + オーロンゲ
N=300

echo "=== データ窓アブレーション (基準=$REF, 各${N}戦) ==="
for name in last2 last4 last6 first4; do
  days=(${=WINDOWS[$name]})
  files=()
  for d in $days; do files+=("data/bc/pairs_${d}.jsonl.gz"); done
  echo "\n--- 窓 $name: ${days} (${#days}日) ---"
  feat="$ABL/feat_$name"
  model="bc_abl_$name"
  if [ ! -f "models/$model/policy_params.npz" ]; then
    $PY scripts/bc_featurize.py $files --out "$feat" >/dev/null 2>&1
    $PY scripts/train_bc2.py --feat "$feat" --epochs 6 --name "$model" 2>&1 | grep -E "epoch 5|exported"
    rm -rf "$feat"   # シャードは即削除(ディスク節約)
  fi
  # エージェント化してビルド
  echo "{\"label\": \"アブレーション窓 $name\", \"deck\": \"decks/meta/meta_01.csv\", \"model\": \"$model\", \"config\": {\"algo\": \"bc\"}}" > "agents/abl_$name.json"
  $PY -m ptcglab.build "abl_$name" >/dev/null 2>&1
  # A/B(基準に対して)
  $PY scripts/evaluate.py "build/abl_$name" --vs "$REF" -n $N -j 8 \
      --note "データ窓アブレーション $name (${#days}日) vs bc_v2(10日)" 2>&1 | grep -E "勝率"
done
echo "\n=== ABLATION DONE ==="
