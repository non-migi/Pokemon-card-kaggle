"""盤面特徴量 v0(価値関数の入力)。

設計制約: 実対戦のobsと探索内の仮想obsの両方で同一に計算できること。
→ 盤面(公開情報)と枚数(手札・山札はカウントのみ)だけを使う。

State(cg.api.State データクラス)と自分のプレイヤー番号から固定長ベクトルを返す。
"""

FEATURE_VERSION = 0


def _side(player) -> list[float]:
    active = player.active[0] if player.active and player.active[0] else None
    bench = [p for p in player.bench if p]
    return [
        float(len(player.prize)),                                  # 残りサイド
        float(active.hp) if active else 0.0,                       # バトル場HP
        float(active.maxHp) if active else 0.0,
        float(len(active.energies)) if active else 0.0,            # バトル場エネ数
        float(len(active.tools)) if active else 0.0,
        1.0 if active is None else 0.0,                            # バトル場不在
        float(len(bench)),                                         # ベンチ数
        float(sum(p.hp for p in bench)),                           # ベンチHP合計
        float(sum(len(p.energies) for p in bench)),                # ベンチエネ合計
        float(max((p.hp for p in bench), default=0)),              # ベンチ最大HP
        float(player.deckCount),                                   # 山札枚数
        float(player.handCount),                                   # 手札枚数
        float(len(player.discard)),                                # トラッシュ枚数
        1.0 if player.poisoned else 0.0,
        1.0 if player.burned else 0.0,
        1.0 if player.asleep else 0.0,
        1.0 if player.paralyzed else 0.0,
        1.0 if player.confused else 0.0,
    ]


def extract(cur, my_index: int) -> list[float]:
    """State → 特徴量ベクトル(自分視点)。"""
    me = cur.players[my_index]
    op = cur.players[1 - my_index]
    f = _side(me) + _side(op)
    f += [
        float(cur.turn),
        1.0 if cur.firstPlayer == my_index else 0.0,
        float(len(me.prize)) - float(len(op.prize)),   # サイド差(重要なので明示)
        1.0 if cur.stadium else 0.0,
    ]
    return f


N_FEATURES = 18 * 2 + 4
FEATURE_NAMES = (
    [f"my_{n}" for n in ["prize", "act_hp", "act_maxhp", "act_ene", "act_tool", "no_active",
                          "bench_n", "bench_hp", "bench_ene", "bench_maxhp", "deck", "hand",
                          "discard", "poison", "burn", "sleep", "para", "conf"]]
    + [f"op_{n}" for n in ["prize", "act_hp", "act_maxhp", "act_ene", "act_tool", "no_active",
                            "bench_n", "bench_hp", "bench_ene", "bench_maxhp", "deck", "hand",
                            "discard", "poison", "burn", "sleep", "para", "conf"]]
    + ["turn", "im_first", "prize_diff", "stadium"]
)
