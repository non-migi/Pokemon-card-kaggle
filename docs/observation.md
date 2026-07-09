# cabt Engine エージェントAPI仕様

出典: `data/simulation/sample_submission/sample_submission/cg/api.py`(公式型定義)。
C++エンジンソースは `data/simulation/ptcg_engine/` にあり(非OSS・コンペ限定利用、再配布禁止)。

## プロトコル

```
agent(obs_dict) -> list[int]
```

1. **初回**: `obs["select"] is None` → 60枚のカードIDリスト(=デッキ)を返す
2. **以降**: `obs["select"]["option"]` のインデックスを `minCount`〜`maxCount` 個、重複なしで返す

obsのトップレベル: `select` / `logs`(前回選択以降のイベント) / `current`(盤面) / `search_begin_input`(探索API用) / `remainingOverageTime`(残り持ち時間、初期600秒)

## 選択の種類 (SelectData)

- `type: SelectType` — 何を選ぶ形式か
- `context: SelectContext` — なぜ選ぶのか(49種。今後追加されうる)
- `minCount`/`maxCount` — 選択数の範囲(minCount=0もある)
- `deck` — 山札から選ぶときだけ非None
- `contextCard`/`effect` — 選択の対象・発生源カード

### SelectType → 対応するOptionType

| SelectType | 意味 | OptionType |
|---|---|---|
| MAIN(0) | メインフェーズの行動 | PLAY(7), ATTACH(8), EVOLVE(9), ABILITY(10), DISCARD(11), RETREAT(12), ATTACK(13), END(14) |
| CARD(1) | カード選択 | CARD(3) |
| ATTACHED_CARD(2) | 付いているカード選択 | TOOL_CARD(4), ENERGY_CARD(5) |
| CARD_OR_ATTACHED_CARD(3) | 上2つの複合 | CARD, TOOL_CARD, ENERGY_CARD |
| ENERGY(4) | エネルギー選択(`remainEnergyCost`参照) | ENERGY(6) |
| SKILL(5) | 効果の発動順 | SKILL(15) |
| ATTACK(6) | ワザ選択 | ATTACK(13) |
| EVOLVE(7) | 進化元+進化先の組 | EVOLVE(9) |
| COUNT(8) | 数の選択 | NUMBER(0) |
| YES_NO(9) | はい/いいえ | YES(1), NO(2) |
| SPECIAL_CONDITION(10) | 特殊状態の選択 | SPECIAL_CONDITION(16) |

### 主要なSelectContext(抜粋)

- `MAIN(0)` メイン行動 / `ATTACK(35)` ワザ選択
- セットアップ: `SETUP_ACTIVE_POKEMON(1)`, `SETUP_BENCH_POKEMON(2)`, `MULLIGAN(42)`, `IS_FIRST(41)`(先攻を取るか)
- 対象選択: `DAMAGE(15)`, `DAMAGE_COUNTER(13/14)`, `HEAL(17)`, `EFFECT_TARGET(25)`
- 移動系: `TO_HAND(7)`, `DISCARD(8)`, `TO_DECK(9/10)`, `TO_BENCH(5)`, `SWITCH(3)`, `TO_ACTIVE(4)`
- エネルギー: `DISCARD_ENERGY(30)`, `ATTACH_FROM(21)`, `ATTACH_TO(22)`
- YES/NO系: `ACTIVATE(43)`(効果を使うか), `COIN_HEAD(46)`, `MORE_DEVOLVE(45)`

## 盤面 (State / PlayerState / Pokemon)

- `State`: `turn`(1=先攻の1ターン目, 0=開始前), `yourIndex`, `firstPlayer`, `supporterPlayed`, `stadiumPlayed`, `energyAttached`, `retreated`, `result`(-1=対戦中), `stadium`, `players[2]`
- `PlayerState`: `active[0..1]`(裏向きはNone), `bench[]`, `benchMax`, `deckCount`, `discard[]`, `prize[]`(裏はNone), `handCount`, `hand`(相手はNone), 特殊状態フラグ5種
- `Pokemon`: `id`, `serial`(対戦内ユニーク), `hp`, `maxHp`, `appearThisTurn`, `energies[]`, `energyCards[]`, `tools[]`, `preEvolution[]`
- **見えないもの**: 相手の手札の中身・山札・裏向きサイド。`handCount`/`deckCount`と`logs`(DRAW_REVERSE等)から推測する

## カードデータAPI

```python
from cg.api import all_card_data, all_attack
cards = all_card_data()   # CardData: hp, weakness, resistance, basic/stage1/stage2, ex, megaEx, tera, aceSpec, evolvesFrom, skills, attacks
attacks = all_attack()    # Attack: attackId, name, text, damage, energies(必要エネルギー)
```

ワザの`damage`と`energies`が構造化データで取れるため、**カード知識なしで期待ダメージ計算が可能**。
効果テキスト(`text`)は自然文 — 効果の意味論はエンジン内部にのみ実装されている。

## 公式探索API(決定化シミュレーション)— 最重要

エージェント内から、**予測した隠れ情報を与えて仮想対局を進められる**:

```python
from cg.api import search_begin, search_step, search_end, search_release

st = search_begin(obs, your_deck, your_prize, opp_deck, opp_prize, opp_hand, opp_active, manual_coin=False)
# st.observation = 仮想盤面のObservation(自分と相手両方の手番が来る)
st2 = search_step(st.searchId, [action_index])   # 1手進める(分岐可能 = 木探索できる)
search_end()  # メモリ再利用
```

- 相手の非公開ゾーンは**自分でサンプリングして埋める**(自分のデッキリストは既知なので、見えたカードを引けば残りは確定)
- `search_step`は任意の`searchId`から分岐できる → **そのままMCTS/ミニマックスの木になる**
- `manual_coin=True`でコイントスの結果も制御可能(期待値計算に使える)
- 勝敗判定: LogType.RESULT の reason = 1:サイド取り切り 2:山札切れ(ターン開始時0枚) 3:バトル場に出せるポケモンなし 4:カード効果

## 勝敗と報酬

- 報酬: 勝ち+1 / 負け-1 / 引き分け0
- 不正行動(範囲外インデックス・枚数違反・60枚でないデッキ)は即INVALID負け
- 持ち時間`remainingOverageTime`=600秒/試合を使い切ると負け

## 提出形式

`sample_submission/` と同構成: `main.py`(`agent`関数) + `deck.csv`(60行のカードID) + `cg/`(公式ライブラリ同梱)。
※ enum・クラスへの**要素追加がコンペ期間中にありうる**と明記されている — unknown値に耐える実装にすること。
