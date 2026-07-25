"""ロールアウト内で「相手」を操縦する専用BC方策(任意)。

背景(2026-07-25): bc_searchのロールアウトは両プレイヤーを単一の`policy`(bc_v2=Alakazam学習)で
回していた。相手がGrim等の他アーキタイプだと、シミュレーション内の相手が実物より大幅に弱くなる
(実測: bc_v2操縦Grim壁 52.8% vs bc_grim操縦Grim壁 35.5%、本番25.7%)。
その結果、探索は自分の勝率を系統的に過大評価しうる。

`opp_policy_params.npz` + `opp_policy_vocab.py` が ptcg/ にあるときだけ有効になり、
無ければ `ENABLED=False` で従来どおり`policy`が両席を操縦する(既存agentは設定なしでno-op)。
注入は `agents/*.json` の `opp_model` キー経由(ptcglab.build)。
"""

import os

import numpy as np

from . import policy
from . import policy_features as PF

ENABLED = False
_P = None
_CID2IDX = {}

try:
    from . import opp_policy_vocab as _V

    if _V.POLICY_FEATURE_VERSION == PF.POLICY_FEATURE_VERSION:
        _params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "opp_policy_params.npz")
        _P = np.load(_params_path)
        _CID2IDX = {cid: i + 1 for i, cid in enumerate(_V.CARD_VOCAB)}
        ENABLED = True
except Exception:
    ENABLED = False


def choose(obs_dict: dict) -> list[int] | None:
    """相手モデルの最善手。policy.chooseと同じ規約(対象外ならNone)。"""
    if not ENABLED:
        return None
    sel = obs_dict.get("select")
    cur = obs_dict.get("current")
    if not sel or not cur:
        return None
    opts = sel.get("option") or []
    if len(opts) < 2:
        return None
    s = policy.raw_scores_with(_P, _CID2IDX, sel, cur, opts)
    if s is None:
        return None
    max_count = int(sel.get("maxCount") or 1)
    if max_count <= 1:
        return [int(np.argmax(s))]
    return policy._multi_choose(s, int(sel.get("minCount") or 0), max_count)
