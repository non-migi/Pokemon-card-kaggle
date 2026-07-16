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

# 純BCの高速screen。結果はresults/arena.jsonlへ自動記録
.venv/bin/python scripts/evaluate.py build/<新BC> --vs build/<旧BC> \
  -n 300 -j 8 --profile standard --suite <実験名> --note "説明"

# searchの計算量固定A/B。両agentのfixed_search_worldsを同じ値にする
.venv/bin/python scripts/evaluate.py build/<新-fixed> --vs build/<旧-fixed> \
  -n 80 -j 8 --profile fixed-worlds --suite <実験名> --note "説明"

# 提出版wall-clock search。CPU競合を避けるため-j 1必須
.venv/bin/python scripts/evaluate.py build/<新-production> --vs build/<旧-production> \
  -n 2 -j 1 --profile production --suite <実験名> --note "安全性smoke"

# 複数相手ガントレット。まずdry-runでhash/config/総試合数を確認
.venv/bin/python scripts/gauntlet.py build/<候補> \
  --vs build/<相手1> build/<相手2> build/<相手3> \
  --weights 0.48 0.26 0.05 -n 80 -j 8 --profile fixed-worlds \
  --suite <実験名> --dry-run

# 敗因の内訳(reason: 1=サイド 2=山札切れ 3=ポケモン無し 4=効果)
.venv/bin/python scripts/diagnose.py 60 first

# arena回帰テスト
.venv/bin/python -m unittest discover -s tests -v

# Expert Rulesの強者行動監査（正規deck完全一致だけを対象）
.venv/bin/python scripts/audit_expert_rules.py data/bc/pairs_0715.jsonl.gz \
  --exact-deck decks/meta/snapshot_20260714_alakazam.csv
```

### Expert Rulesの開発ループ

agent設定例:

```json
{
  "config": {
    "algo": "bcs",
    "expert_rules": "alakazam_v1",
    "expert_rule_mode": "candidate",
    "enabled_rule_ids": ["AZ006_UNBLOCK_EXACT_KO"]
  }
}
```

- `shadow`: 発火を計測するだけで、既存候補・行動を変えない
- `candidate`: BC top-1を残し、BC top-5外のrule手を最大2つroot探索へ追加する
- `enforce`: candidateに加え、hardを直接適用し、`forbid`を全フォールバック段から除く
- `candidate/enforce`は`enabled_rule_ids`の明示が必須。最初は必ず1 ruleまたは因果が連続する最小rule組で測る
- 新ruleは `公開敗戦fixture → 強者decision監査 → shadow → fixed-worlds A/B → 二層meta → production`
  の順。強者一致率だけでhardへ昇格しない
- `expert_rule_errors` / `expert_rule_invalid` はarena strict failure。成功時もhit/injected/selected/
  guard-blockedを`agent_metrics_total`と`agent_metrics_by_seat`へ保存する

### 改善判定のルール

- 変更は1つずつアブレーションし、`docs/experiments.md` に記録する
- 採用基準: 旧版との直接対決300戦以上で、Wilson 95%CI下限 > 50%
- 測定前に`results/arena.jsonl`と`results/gauntlet.jsonl`を検索し、重複実験を避ける
- `n`は正の偶数。提出判定は既定のfresh process per seat pairを使い、`--reuse-agent`は使わない
- fresh pairの既定watchdogは1ペア3600秒。短いscreenでは`--pair-timeout-sec`で明示的に短縮できるが、
  productionは席反転2戦の合計時間を十分上回る値にする。timeout/crashは台帳記録後にstrict failureとなる
- searchはfixed-worldsで性能比較、production `-j 1`で本番設定の完走確認を分ける
- 大量ExIt生成・学習中はsearch評価を開始しない。進行中jobが参照する`build/`も再buildしない
- 採用する記録は`failure_count=0`、`run_failures=[]`、両席`DONE`を必須とする
- gauntletの加重値は収載対面内の点推定。`weight_sum<1`なら全環境EVではない
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
- [ ] 純BCまたはfixed-worldsで旧版に有意勝ち越し、複数対面の弱点も記録
- [ ] production profileを`-j 1`で完走し、failure 0を確認
- [ ] 1手あたりの最悪時間を確認(600秒/試合を超えない設計か)
- [ ] `fixed_search_worlds`入りの評価専用agentではないこと(buildはtar化を拒否する)

## 本番環境との同等性(Docker検討の結論、2026-07-12調査)

- **Mac勢がDockerを使っていた理由は歴史的なもの**: 6/30更新まではエンジンにmacOS/ARM64バイナリが
  無く、Linux x86_64のDocker/エミュレーションが必須だった。現在は`libcg.dylib`が公式提供され、
  ネイティブMacで動作(うちは最初からこの恩恵を受けている)
- **バージョン整合**: ローカルのkaggle-environments 1.32.0(7/8リリース)は6/30エンジン更新後の
  最新公開版で、ラダーと整合していると考えてよい。バージョン更新の告知(Discussionの
  Announcement)は週次で監視し、新版が出たら`pip install -U kaggle-environments`で追随する
- **結論: 日常開発にDockerは不要**(ネイティブが高速で並列自己対戦に有利)。
  本番同等性の確認が必要な場面(最終フリーズ前など)は、Dockerより正確な手段がある:
  **Kaggleノートブック上で提出tarをロードして両席検証**(本物のKaggleイメージ+Linux x86_64)。
  なお提出後の検証エピソード(vs自分)が通ること自体が最低限の本番検証になっている
- ローカルLinuxがどうしても必要になったら `brew install colima docker` で可能(Docker Desktop不要)

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
