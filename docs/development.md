# 開発ワークフロー

## 初回セットアップ(クローン直後)

```bash
# 1. Python環境(3.12必須。3.14はpygameがビルド不可)
python3.12 -m venv .venv
.venv/bin/pip install kaggle-environments

# 2. Kaggle CLI認証(ブラウザが開く)
pipx install kaggle
kaggle auth login

# 3. コンペ配布物の取得(git管理外)
kaggle competitions download -c pokemon-tcg-ai-battle -p data/simulation
kaggle competitions download -c pokemon-tcg-ai-battle-challenge-strategy -p data/strategy
(cd data/simulation && unzip -q *.zip && rm *.zip)
(cd data/strategy && unzip -q *.zip && rm *.zip)

# 4. 公式ライブラリをsrc/に復元(git管理外のため)
cp -r "data/simulation/sample_submission/sample_submission/cg" src/
```

## 日常の開発ループ

```bash
# エージェントの組立て+検証(agents/<name>.json から)
.venv/bin/python -m ptcglab.build v3.0g --no-tar

# A/B評価: 変更が本物か必ずここで判定(結果は results/arena.jsonl に自動記録)
.venv/bin/python scripts/evaluate.py build/<新> --vs build/<旧> -n 200 -j 8 --note "説明"

# 敗因の内訳(reason: 1=サイド 2=山札切れ 3=ポケモン無し 4=効果)
.venv/bin/python scripts/diagnose.py 60 first
```

### 改善判定のルール

- 変更は1つずつアブレーションし、`docs/experiments.md` に記録する
- 採用基準: 旧版との直接対決300戦以上で、Wilson 95%CI下限 > 50%
- 提出は**有意な改善があったときだけ**(1日5回制限)

## 提出手順

```bash
# 1. 組立て+ローダー互換検証+tar(必須! agents/<name>.json を定義してから)
.venv/bin/python -m ptcglab.build <name>

# 2. 提出(前に submissions で枠と「最新2提出」の状況を確認)
kaggle competitions submit -c pokemon-tcg-ai-battle -f build/<name>.tar.gz -m "説明"

# 3. 検証結果の確認(PENDING → COMPLETE/ERROR)→ versions.md と STATUS.md を更新
kaggle competitions submissions -c pokemon-tcg-ai-battle | head -5
```

### 提出前チェックリスト

- [ ] `ptcglab.build` の検証が通る(**ファイルパスロード検証込み**。importベースの評価だけでは不十分)
- [ ] evaluate.py で旧版に有意勝ち越し
- [ ] 1手あたりの最悪時間を確認(600秒/試合を超えない設計か)

### 既知の落とし穴

- **Kaggleローダーは`exec(code, {})`**: `__file__`/`__name__`が無い。「最後に定義されたcallable」がagentになるので、main.pyの最後の関数は必ず`agent`
- **CLI提出の500エラー**: 実は届いてERRORになっていることがある(枠を消費)。リトライ前に`submissions`で確認
- **enum追加**: SelectContext等はコンペ期間中に増えると公式明言。未知intで落ちない実装を維持

## レート・実戦成績の確認

```bash
kaggle competitions submissions -c pokemon-tcg-ai-battle   # 自分の提出とレート
kaggle competitions leaderboard -c pokemon-tcg-ai-battle --show | head -20
.venv/bin/python scripts/ladder_stats.py                   # 提出ごとのLB対戦数・勝率(リプレイ集計)
```

結果は `docs/versions.md` の表に観測日付きで反映する。レートと勝率は乖離しうる(マッチメイキング相手の強さで補正されるため)。
