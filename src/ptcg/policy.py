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


def scores(obs_dict: dict) -> np.ndarray | None:
    """単数選択の各optionのスコア(logits)。対象外/無効ならNone。"""
    if not ENABLED:
        return None
    sel = obs_dict.get("select")
    cur = obs_dict.get("current")
    if not sel or not cur or sel.get("maxCount") != 1:
        return None
    opts = sel.get("option") or []
    if len(opts) < 2:
        return None
    try:
        sf = np.asarray(PF.state_features(sel, cur), np.float32)
        sv = _relu(sf @ _P["s_w1"].T + _P["s_b1"]) @ _P["s_w2"].T + _P["s_b2"]
        of, emb_idx = [], []
        for opt in opts:
            feats, cid = PF.option_features(sel, cur, opt)
            of.append(feats)
            emb_idx.append(_CID2IDX.get(cid, 0))
        om = np.concatenate([np.asarray(of, np.float32), _P["emb"][emb_idx]], axis=1)
        ov = _relu(om @ _P["o_w1"].T + _P["o_b1"]) @ _P["o_w2"].T + _P["o_b2"]
        return (ov @ sv) / np.sqrt(len(sv))
    except Exception:
        return None


def choose(obs_dict: dict) -> list[int] | None:
    """BC方策の最善手。対象外ならNone。"""
    s = scores(obs_dict)
    if s is None:
        return None
    return [int(np.argmax(s))]
