# Kaggle Writeup 提出手順(Strategy部門、ユーザー操作用)

🚨 **締切 2026-09-13 23:59 UTC = 09-14 08:59 JST(残りわずか)。今日中に Submit まで完了させること。**

## 事前に揃っているもの(このディレクトリ)
- `writeup_en.md` — 本文(英語)。Kaggleエディタに貼る。**見出し・本文のみ貼る**(冒頭の Subtitle/Track 行と末尾の語数メモは貼らない)
- `writeup_ja.md` — 日本語対訳(レビュー用。提出しない)
- `figures/fig1..fig10*.png` — Media Gallery に添付する図(10点)
- `deck_ogerpon.csv` / `deck_grimmsnarl.csv` — デッキリスト(添付。語数外)

## 手順
1. https://www.kaggle.com/competitions/pokemon-tcg-ai-battle-challenge-strategy/projects を開く
2. **New Writeup** をクリック
3. Title(**80文字制限**、現行78文字): `The Ladder Is an Ecosystem: Deck-Policy Co-adaptation and a Two-Slot Portfolio`
4. Subtitle: `writeup_en.md` 冒頭の短い版(135文字)を貼る。文字数制限に余裕があれば長い版(272文字)でもよい
5. **Track**: 本コンペはトラックが1つ(Main Track)だけなので**自動選択済み**。確認するだけでよい
6. 本文: `writeup_en.md` の `## 1. What this report claims` 以降を貼り付け。Markdown対応。図は本文中に画像として挿入するか、
   Media Gallery に添付して本文で "Fig. N" と参照する(どちらでも可。両方やるのが安全)
7. Media Gallery: `figures/` の10枚を fig1→fig10 の順で追加。キャプションは下の一覧をそのまま貼る
   (先頭の画像がカバー画像になる。番号順のままでよい)
8. 添付(Attachments / Links):
   - GitHub: https://github.com/non-migi/Pokemon-card-kaggle (公開済み、MIT)
   - デッキCSV 2本(Kaggle Dataset として上げる場合は Public で作る。Private だと締切後に自動公開される)
9. **Save** → 右上に **Submit** ボタンが出る → **Submit** を押す(下書きのままは審査対象外)
10. 提出後、ページに "Submitted" 表示があることを確認し、URLを `docs/versions.md` に記録

## Media Gallery のキャプション(コピペ用)

```
Fig. 1  Post-deadline rating trajectories of the two final submissions (Aug 17 - Sep 5).
Fig. 2  Per-opponent-archetype win rates, 1,000 ladder games per agent, Wilson 95% CI.
Fig. 3  Final leaderboard distribution (6,807 teams) with medal lines and our rank.
Fig. 4  Same deck, same weights: pure imitation vs imitation + determinized search.
Fig. 5  Behaviour-cloning model family: data, vocabulary, holdout accuracy, key evidence.
Fig. 6  Pipeline: winner-side imitation, deck and policy shipped together, runtime fallbacks.
Fig. 7  Metagame drift in the official Daily Top during the competition.
Fig. 8  Final 60-card deck lists (card IDs in the attached CSVs).
Fig. 9  Rating-band ecology: opponent composition and our win rate by the opponent's final rating band.
Fig. 10 Band composition x per-archetype win rate reproduces each agent's win rate per band.
```

## 図を作り直したいとき

```bash
.venv/bin/python scripts/make_writeup_figures.py            # 10点すべて
.venv/bin/python scripts/make_writeup_figures.py --only 1,9 # 指定のみ
```

## 注意
- 語数: 本文2,000語以下(現状 約1751語)。図表内の文字・デッキリスト・Galleryは語数外
- 画像: 自作グラフのみ使用。カード画像を使う場合は配布物の画像をそのまま(改変不可)
- 一度 Submit しても締切前なら編集可。ただし編集後に再度 Submit 状態になっているか必ず確認
