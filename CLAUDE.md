# Pokemon TCG AI Battle Challenge

Kaggleコンペで上位入賞を狙う。**AI主導開発・ポケカのドメイン知識に頼らない**(学習・探索・データ駆動)。

以下のインポートで共通マニュアルと現在の状態が自動ロードされる(正はこの2ファイル。編集はそちらへ):

@AGENTS.md

@STATUS.md

## Claude Code固有の注意

- このプロジェクトのメモリ(~/.claude/projects/...)は補助。**正は常にリポジトリ内**(上記2ファイルとdocs/)
  — Codex等の他エージェントはClaudeのメモリを読めない
- scratchpadは揮発する。恒久的な成果物(エージェント定義・モデル・測定結果)は
  agents/ models/ results/ に置く
- バックグラウンドジョブの結果は、終了時に必ず docs/experiments.md か results/ へ反映してから
  セッションを終える(通知はセッションをまたがない)

## 環境メモ

- venvはPython 3.12(3.14はpygameビルド不可)。`make("cabt")`がシミュレータ(1試合数十ms)
- 締切: Simulation 2026-08-16 / Strategy Writeup 2026-09-13
