"""dict版の探索API薄ラッパ。

cg.api.search_begin/search_step はdataclass変換を行うが、BC方策の特徴量は
生dict(エージェントが受け取るobs_dictと同形式)を要求するため、
JSONを直接dictで返す版を提供する。ロジックは cg/api.py の該当関数の移植。
"""

import ctypes
import json

from cg.api import lib

_agent_ptr = None


def _ptr():
    global _agent_ptr
    if _agent_ptr is None:
        _agent_ptr = lib.AgentStart()
    return _agent_ptr


def _parse(bs) -> dict:
    r = json.loads(bs.decode())
    if r.get("error", 0) != 0:
        raise ValueError(f"search api error {r.get('error')}")
    return r["state"]  # {"observation": {...}, "searchId": int}


def search_begin_dict(obs_dict: dict, your_deck, your_prize, opp_deck, opp_prize,
                      opp_hand, opp_active, manual_coin=False) -> dict:
    sbi = obs_dict.get("search_begin_input")
    if not sbi:
        raise ValueError("search_begin_input が無い")
    cur = obs_dict["current"]
    me = cur["yourIndex"]
    # 自分のデッキが公開中(山札サーチ等)の場合はエンジン側が実デッキを使う
    if (obs_dict.get("select") or {}).get("deck") is not None:
        your_deck = []
    active = (cur["players"][1 - me].get("active") or [])
    if not (active and active[0] is None):
        opp_active = []
    bs = lib.SearchBegin(_ptr(), sbi.encode("ascii"), len(sbi),
                         (ctypes.c_int * len(your_deck))(*your_deck),
                         (ctypes.c_int * len(your_prize))(*your_prize),
                         (ctypes.c_int * len(opp_deck))(*opp_deck),
                         (ctypes.c_int * len(opp_prize))(*opp_prize),
                         (ctypes.c_int * len(opp_hand))(*opp_hand),
                         (ctypes.c_int * len(opp_active))(*opp_active),
                         int(manual_coin))
    return _parse(bs)


def search_step_dict(search_id: int, select: list[int]) -> dict:
    bs = lib.SearchStep(_ptr(), search_id, (ctypes.c_int * len(select))(*select), len(select))
    return _parse(bs)


def search_end() -> None:
    lib.SearchEnd(_ptr())
