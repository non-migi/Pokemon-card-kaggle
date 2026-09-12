#!/bin/zsh
# Kaggle Writeup の各パーツをクリップボードに入れる(macOS)。
#   zsh scripts/writeup_clip.sh          # 対話モードで順に進む
#   zsh scripts/writeup_clip.sh body     # 指定パーツだけコピー
# パーツ: title / subtitle / body / captions / repo
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)/docs/writeup/paste"
FIGS="$(cd "$(dirname "$0")/.." && pwd)/docs/writeup/figures"
URL="https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/projects"

copy() { pbcopy < "$DIR/$1"; print -r -- "  → クリップボードにコピーしました: $1 ($(wc -c < "$DIR/$1" | tr -d ' ') bytes)"; }

case "${1:-}" in
  title)    copy 01_title.txt ;;
  subtitle) copy 02_subtitle_short.txt ;;
  body)     copy 03_body.md ;;
  captions) copy 04_captions.txt ;;
  repo)     copy 05_repo_link.txt ;;
  "")
    if [[ ! -t 0 ]]; then
      # 対話端末でない(Claude Code の ! 実行など)。read で止まるのでステップ表示に切り替える
      print -r -- "対話モードは使えない環境です。以下を1つずつ実行してください。"
      print -r -- ""
      print -r -- "  open '$URL' ; open '$FIGS'      # Kaggleと図フォルダを開く"
      print -r -- "  zsh scripts/writeup_clip.sh title      # 1. Title を Cmd+V"
      print -r -- "  zsh scripts/writeup_clip.sh subtitle   # 2. Subtitle を Cmd+V"
      print -r -- "  zsh scripts/writeup_clip.sh body       # 3. 本文を Cmd+V"
      print -r -- "  zsh scripts/writeup_clip.sh captions   # 4. 図10枚をD&D後、キャプションを貼る"
      print -r -- "  zsh scripts/writeup_clip.sh repo       # 5. GitHubリンクを Links 欄へ"
      print -r -- ""
      print -r -- "最後に Save → Submit。ページに Submitted と出れば完了。"
      exit 0
    fi
    print -r -- "Kaggle Writeup 提出ウィザード"
    print -r -- "各ステップで Enter を押すと次の文字列がクリップボードに入ります。Kaggle 側で Cmd+V。"
    print -r -- ""
    print -r -- "[0] Kaggle のページと図フォルダを開きます..."
    open "$URL"; open "$FIGS"
    read -r "?    Enter で次へ(New Writeup をクリックしてから) > "

    print -r -- "[1] Title(78文字)"
    copy 01_title.txt
    read -r "?    Title 欄に貼ったら Enter > "

    print -r -- "[2] Subtitle(134文字)"
    copy 02_subtitle_short.txt
    read -r "?    Subtitle 欄に貼ったら Enter > "

    print -r -- "[3] 本文(1,751語)"
    copy 03_body.md
    read -r "?    本文エディタに貼ったら Enter > "

    print -r -- "[4] Media Gallery: 開いた Finder から fig1→fig10 の順に10枚をドラッグ&ドロップ"
    print -r -- "    キャプション一覧をコピーします"
    copy 04_captions.txt
    read -r "?    10枚の添付とキャプション入力が終わったら Enter > "

    print -r -- "[5] GitHub リンク(Attachments / Links 欄へ)"
    copy 05_repo_link.txt
    print -r -- "    デッキCSV: docs/writeup/deck_ogerpon.csv / deck_grimmsnarl.csv も添付"
    read -r "?    添付が終わったら Enter > "

    print -r -- ""
    print -r -- "[6] 最終チェック"
    print -r -- "    □ Track が Main Track になっている"
    print -r -- "    □ Save を押した"
    print -r -- "    □ 右上の Submit を押した"
    print -r -- "    □ ページに Submitted と表示されている  ← ここまでやらないと審査対象外"
    print -r -- ""
    print -r -- "提出できたら URL を教えてください。docs/versions.md に記録します。"
    ;;
  *) print -r -- "使い方: zsh scripts/writeup_clip.sh [title|subtitle|body|captions|repo]"; exit 1 ;;
esac
