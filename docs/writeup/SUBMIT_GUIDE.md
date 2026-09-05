# Kaggle Writeup 提出手順(Strategy部門、ユーザー操作用)

締切 **2026-09-13 23:59 UTC = 09-14 08:59 JST**。計画上の提出日は **09-11**。

## 事前に揃っているもの(このディレクトリ)
- `writeup_en.md` — 本文(英語)。Kaggleエディタに貼る。**見出し・本文のみ貼る**(冒頭の Subtitle/Track 行と末尾の語数メモは貼らない)
- `writeup_ja.md` — 日本語対訳(レビュー用。提出しない)
- `figures/fig1..fig8*.png` — Media Gallery に添付する図(8点)
- `deck_ogerpon.csv` / `deck_grimmsnarl.csv` — デッキリスト(添付。語数外)

## 手順
1. https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/projects を開く
2. **New Writeup** をクリック
3. Title: `Imitate the Winners of the Deck You Play: Deck–Policy Co-adaptation for the PTCG AI Battle Challenge`
4. Subtitle: `writeup_en.md` 冒頭の Subtitle 行の文
5. **Track を選択**(必須。選択しないと Submit できない)
6. 本文: `writeup_en.md` の `## 1. Summary` 以降を貼り付け。Markdown対応。図は本文中に画像として挿入するか、
   Media Gallery に添付して本文で "Fig. N" と参照する(どちらでも可。両方やるのが安全)
7. Media Gallery: `figures/` の8枚を fig1→fig8 の順で追加。各図のキャプションは本文の図番号に合わせる
8. 添付(Attachments / Links):
   - GitHub: https://github.com/non-migi/Pokemon-card-kaggle (公開済み、MIT)
   - デッキCSV 2本(Kaggle Dataset として上げる場合は Public で作る。Private だと締切後に自動公開される)
9. **Save** → 右上に **Submit** ボタンが出る → **Submit** を押す(下書きのままは審査対象外)
10. 提出後、ページに "Submitted" 表示があることを確認し、URLを `docs/versions.md` に記録

## 注意
- 語数: 本文2,000語以下(現状 約1,910語、余裕は約90語)。図表内の文字・デッキリスト・Galleryは語数外
- 画像: 自作グラフのみ使用。カード画像を使う場合は配布物の画像をそのまま(改変不可)
- 一度 Submit しても締切前なら編集可。ただし編集後に再度 Submit 状態になっているか必ず確認
