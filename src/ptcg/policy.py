"""BC方策のnumpy推論(2タワー内積)。

policy_params.npz + policy_vocab.py(train_bc.py生成)をロードする。
無い/バージョン不一致なら ENABLED=False(呼び手はヒューリスティックへフォールバック)。
"""

import os

import numpy as np

from . import policy_features as PF

ENABLED = False
_P = None
_CID2IDX = {}

try:
    from . import policy_vocab as _V

    if _V.POLICY_FEATURE_VERSION == PF.POLICY_FEATURE_VERSION:
        _params_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_params.npz")
        _P = np.load(_params_path)
        _CID2IDX = {cid: i + 1 for i, cid in enumerate(_V.CARD_VOCAB)}
        ENABLED = True
except Exception:
    ENABLED = False


def _relu(x):
    return np.maximum(x, 0.0)


def raw_scores_with(P, cid2idx: dict, sel: dict, cur: dict, opts: list) -> np.ndarray | None:
    """任意のパラメタ束で各optionのスコア(logits)を計算する。

    相手モデル(opp_policy)が同じ推論を別の重みで使うため、重みを引数に外だしした。
    """
    try:
        sf = np.asarray(PF.state_features(sel, cur), np.float32)
        sv = _relu(sf @ P["s_w1"].T + P["s_b1"]) @ P["s_w2"].T + P["s_b2"]
        of, emb_idx = [], []
        for opt in opts:
            feats, cid = PF.option_features(sel, cur, opt)
            of.append(feats)
            emb_idx.append(cid2idx.get(cid, 0))
        om = np.concatenate([np.asarray(of, np.float32), P["emb"][emb_idx]], axis=1)
        ov = _relu(om @ P["o_w1"].T + P["o_b1"]) @ P["o_w2"].T + P["o_b2"]
        return (ov @ sv) / np.sqrt(len(sv))
    except Exception:
        return None


def _raw_scores(sel: dict, cur: dict, opts: list) -> np.ndarray | None:
    """各optionのスコア(logits)を計算。maxCountに依存しない共通処理。"""
    return raw_scores_with(_P, _CID2IDX, sel, cur, opts)


def scores(obs_dict: dict) -> np.ndarray | None:
    """単数選択の各optionのスコア(logits)。対象外/無効ならNone。

    探索(bc_search)が単数選択専用に呼ぶため、maxCount==1のゲートは維持する。
    複数選択のスコアが要るときは _raw_scores を直接使う(choose内)。
    """
    if not ENABLED:
        return None
    sel = obs_dict.get("select")
    cur = obs_dict.get("current")
    if not sel or not cur or sel.get("maxCount") != 1:
        return None
    opts = sel.get("option") or []
    if len(opts) < 2:
        return None
    return _raw_scores(sel, cur, opts)


def _multi_choose(s: np.ndarray, min_count: int, max_count: int) -> list[int]:
    """複数選択: スコア上位を選ぶ。
    - ちょうどN(min==max, データの約50%): 上位N。
    - 「N個まで」(min<max): 必須min個 + 平均超えのoptionを任意枠でmaxまで。
      単数学習モデルのスコアは相対順位のみ有効なので、絶対閾値でなく平均を相対閾値に使う。
    """
    n = len(s)
    max_count = min(max_count, n)
    min_count = max(0, min(min_count, max_count))
    order = [int(i) for i in np.argsort(-s)]
    if min_count == max_count:
        return order[:max_count]
    chosen = order[:min_count]
    thr = float(np.mean(s))
    for i in order[min_count:max_count]:
        if s[i] >= thr:
            chosen.append(i)
        else:
            break  # 降順なので以降も閾値未満
    return chosen


def choose(obs_dict: dict) -> list[int] | None:
    """BC方策の最善手。単数=argmax、複数=上位選択。対象外ならNone。"""
    if not ENABLED:
        return None
    sel = obs_dict.get("select")
    cur = obs_dict.get("current")
    if not sel or not cur:
        return None
    opts = sel.get("option") or []
    if len(opts) < 2:
        return None
    s = _raw_scores(sel, cur, opts)
    if s is None:
        return None
    max_count = int(sel.get("maxCount") or 1)
    if max_count <= 1:
        return [int(np.argmax(s))]
    return _multi_choose(s, int(sel.get("minCount") or 0), max_count)
