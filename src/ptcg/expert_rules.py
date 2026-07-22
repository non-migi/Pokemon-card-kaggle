"""デッキ固有の専門家ルール。

ルールは学習方策を無条件に上書きしない。設定されたmodeに応じて、

- shadow: 発火と方策一致だけを計測
- candidate: BC top-k外の候補を探索へ注入
- enforce: candidateに加え、hardルールだけを直接適用

の順で段階的に検証する。カード固有ロジックをmain.pyへ散らさず、
各ルールをrule ID単位でA/Bできることを優先する。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping


# SelectType / OptionType / AreaType。コンペ中にenumが増えても未知intは非発火にする。
ST_MAIN, ST_CARD, ST_ENERGY = 0, 1, 4
OT_CARD, OT_PLAY, OT_EVOLVE, OT_ABILITY, OT_ATTACK, OT_END = 3, 7, 9, 10, 13, 14
AR_HAND, AR_DISCARD, AR_ACTIVE, AR_BENCH = 2, 3, 4, 5
CTX_TO_DECK = 9

# canonical Alakazamで使用するカード。
DUDUNSPARCE = 66
DUNSPARCE = 305
SHAYMIN = 343
ABRA, KADABRA, ALAKAZAM = 741, 742, 743
ENHANCED_HAMMER = 1081
SACRED_ASH = 1129
HAND_POWER = 1072
MIST_ENERGY, ROCK_FIGHTING_ENERGY = 11, 20
PSYCHIC_ENERGY_TYPE = 5
FIGHTING_ENERGY_TYPE = 6

KNOWN_MODES = {"shadow", "candidate", "enforce"}


@dataclass(frozen=True)
class RuleProposal:
    """1つのルールが推奨する合法行動。"""

    rule_id: str
    action: tuple[int, ...]
    priority: int
    kind: str  # candidate / hard / forbid
    reason: str
    equivalent_actions: tuple[tuple[int, ...], ...] = ()


RuleFn = Callable[[dict, Mapping[int, int]], RuleProposal | None]


def proposal_matches(proposal: RuleProposal, action: Iterable[int]) -> bool:
    """同価値の対象違いも含め、actionがルール推奨に沿うか判定する。"""
    try:
        chosen = tuple(action)
    except TypeError:
        return False
    return chosen == proposal.action or chosen in proposal.equivalent_actions


def legal_action(obs_dict: dict, action: Iterable[int]) -> bool:
    """actionが現在のselectに対して形式上合法かを副作用なしで確認する。"""
    try:
        values = tuple(action)
        sel = obs_dict.get("select") or {}
        options = sel.get("option") or []
        lo = int(sel.get("minCount", 0))
        hi = min(int(sel.get("maxCount", 0)), len(options))
    except (AttributeError, TypeError, ValueError):
        return False
    if not lo <= len(values) <= hi or len(set(values)) != len(values):
        return False
    return all(
        isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(options)
        for i in values
    )


def _players(obs: dict) -> tuple[dict, dict] | None:
    try:
        cur = obs["current"]
        yi = int(cur["yourIndex"])
        players = cur["players"]
        if yi not in (0, 1) or len(players) < 2:
            return None
        return players[yi], players[1 - yi]
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _field(player: dict) -> list[dict]:
    return [p for p in (player.get("active") or []) + (player.get("bench") or [])
            if isinstance(p, dict)]


def _active(player: dict) -> dict | None:
    active = player.get("active") or []
    return active[0] if active and isinstance(active[0], dict) else None


def _hand_card_id(player: dict, option: dict) -> int | None:
    if option.get("area", AR_HAND) != AR_HAND:
        return None
    try:
        card = (player.get("hand") or [])[int(option["index"])]
        cid = card.get("id") if isinstance(card, dict) else None
        return int(cid) if cid is not None else None
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _option_for_hand_card(obs: dict, card_ids: set[int], option_type: int) -> list[int]:
    players = _players(obs)
    if players is None:
        return []
    mine, _ = players
    options = (obs.get("select") or {}).get("option") or []
    return [
        i for i, option in enumerate(options)
        if isinstance(option, dict) and option.get("type") == option_type
        and _hand_card_id(mine, option) in card_ids
    ]


def _is_alakazam_deck(deck: Iterable[int]) -> bool:
    try:
        counts = Counter(int(x) for x in deck)
    except (TypeError, ValueError):
        return False
    return counts[ABRA] >= 3 and counts[KADABRA] >= 3 and counts[ALAKAZAM] >= 3


def _az001_empty_bench_basic(
    obs: dict, _card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """場が1体だけのとき、非exの展開先を探索候補へ残す。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, _ = players
    active = [p for p in (mine.get("active") or []) if isinstance(p, dict)]
    bench = [p for p in (mine.get("bench") or []) if isinstance(p, dict)]
    if len(active) != 1 or bench or int(mine.get("benchMax", 0) or 0) <= 0:
        return None

    field_ids = {p.get("id") for p in _field(mine)}
    # アタッカー→ドローエンジン→保護役。Fezandipiti exは2 prize liabilityなので
    # この安全則では強制候補にしない。
    preferred = []
    if not field_ids.intersection({ABRA, KADABRA, ALAKAZAM}):
        preferred.append(ABRA)
    if not field_ids.intersection({DUNSPARCE, DUDUNSPARCE}):
        preferred.append(DUNSPARCE)
    if SHAYMIN not in field_ids:
        preferred.append(SHAYMIN)
    preferred.extend((ABRA, DUNSPARCE, SHAYMIN))
    for cid in preferred:
        indices = _option_for_hand_card(obs, {cid}, OT_PLAY)
        if indices:
            return RuleProposal(
                "AZ001_EMPTY_BENCH_BASIC", (indices[0],), 120, "candidate",
                "場が1体だけなので非ex Basicを展開候補へ残す",
            )
    return None


def _az002_draw_evolution(
    obs: dict, _card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """Alakazam系とDudunsparceのドロー進化を探索候補へ残す。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, _ = players
    # 終盤のdeckout回避を優先し、残り3枚以下ではドロー進化を推さない。
    if int(mine.get("deckCount", 0) or 0) <= 3:
        return None
    for cid, label in (
        (ALAKAZAM, "Alakazam"),
        (KADABRA, "Kadabra"),
        (DUDUNSPARCE, "Dudunsparce"),
    ):
        indices = _option_for_hand_card(obs, {cid}, OT_EVOLVE)
        if indices:
            return RuleProposal(
                "AZ002_DRAW_EVOLUTION", (indices[0],), 100, "candidate",
                f"{label}の進化時ドローを探索候補へ残す",
            )
    return None


def _blocker_energy_indices(
    player: dict, card_energy_types: Mapping[int, int],
) -> list[int]:
    """Hand Powerを防ぐenergyの添字。

    Mist Energyは全ポケモンで有効だが、Rock Fighting Energyは闘ポケモンに
    付いている場合だけ有効。観測にはポケモンのタイプがないため、呼び手が
    card metadata由来のenergy typeを渡す。不明時は安全側でRockを非発火にする。
    """
    active = _active(player)
    if active is None:
        return []
    is_fighting = card_energy_types.get(active.get("id")) == FIGHTING_ENERGY_TYPE
    return [
        i for i, card in enumerate(active.get("energyCards") or [])
        if isinstance(card, dict) and (
            card.get("id") == MIST_ENERGY
            or (card.get("id") == ROCK_FIGHTING_ENERGY and is_fighting)
        )
    ]


def _effect_blocker_on_active(
    player: dict, card_energy_types: Mapping[int, int],
) -> bool:
    return bool(_blocker_energy_indices(player, card_energy_types))


def _alakazam_ready(player: dict) -> bool:
    active = _active(player)
    return bool(
        active and active.get("id") == ALAKAZAM
        and PSYCHIC_ENERGY_TYPE in (active.get("energies") or [])
    )


def _az003_hammer_blocker_play(
    obs: dict, card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """Hand Powerを無効化するenergyがactiveにあればHammerを候補化する。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, opp = players
    if not _alakazam_ready(mine) or not _effect_blocker_on_active(
        opp, card_energy_types,
    ):
        return None
    indices = _option_for_hand_card(obs, {ENHANCED_HAMMER}, OT_PLAY)
    if not indices:
        return None
    return RuleProposal(
        "AZ003_HAMMER_BLOCKER_PLAY", (indices[0],), 180, "candidate",
        "Hand Powerを無効化する特殊energyをEnhanced Hammerで外す",
    )


def _az004_hammer_blocker_target(
    obs: dict, card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """Hammer使用後は相手activeの効果無効energyを確実に選ぶ。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    effect = sel.get("effect") or {}
    if (sel.get("type") != ST_ENERGY or sel.get("maxCount") != 1
            or not isinstance(effect, dict) or effect.get("id") != ENHANCED_HAMMER
            or players is None):
        return None
    _, opp = players
    if not _effect_blocker_on_active(opp, card_energy_types):
        return None
    active = _active(opp)
    energy_cards = (active.get("energyCards") or []) if active else []
    blocker_indices = set(_blocker_energy_indices(opp, card_energy_types))
    try:
        your_index = int((obs.get("current") or {})["yourIndex"])
    except (KeyError, TypeError, ValueError):
        return None
    opp_index = 1 - your_index
    valid_actions = []
    for i, option in enumerate(sel.get("option") or []):
        if not isinstance(option, dict):
            continue
        if (option.get("playerIndex") != opp_index or option.get("area") != AR_ACTIVE
                or int(option.get("index", -1)) != 0):
            continue
        try:
            energy = energy_cards[int(option["energyIndex"])]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if (int(option["energyIndex"]) in blocker_indices
                and isinstance(energy, dict)):
            valid_actions.append((i,))
    if not valid_actions:
        return None
    return RuleProposal(
        "AZ004_HAMMER_BLOCKER_TARGET", valid_actions[0], 300, "hard",
        "Enhanced Hammerで相手activeの効果無効energyを選ぶ",
        tuple(valid_actions[1:]),
    )


def _az005_sole_dudun_guard(
    obs: dict, _card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """場の唯一のDudunsparceを山札へ戻して即敗北する手を禁止する。

    Run Away Drawは1枚以上引いた場合だけ自身を戻すためdeck残数を確認する。
    また禁止後も合法なターン終了を残し、negative guardだけで合法手を尽くさない。
    """
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, _ = players
    active = _active(mine)
    if active is None or active.get("id") != DUDUNSPARCE or len(_field(mine)) != 1:
        return None
    try:
        if int(mine.get("deckCount", 0) or 0) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    options = sel.get("option") or []
    has_legal_end = any(
        isinstance(option, dict) and option.get("type") == OT_END
        and legal_action(obs, (i,))
        for i, option in enumerate(options)
    )
    if not has_legal_end:
        return None
    for i, option in enumerate(options):
        if (isinstance(option, dict) and option.get("type") == OT_ABILITY
                and option.get("area") == AR_ACTIVE
                and int(option.get("index", -1)) == 0):
            return RuleProposal(
                "AZ005_SOLE_DUDUN_GUARD", (i,), 400, "forbid",
                "唯一のDudunsparceを戻すとactive不在で即敗北する",
            )
    return None


def _az006_unblock_exact_ko(
    obs: dict, card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """全blockerをHammerで剥がせばHand Power KOになる連鎖を候補化する。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, opp = players
    blockers = _blocker_energy_indices(opp, card_energy_types)
    if not _alakazam_ready(mine) or not blockers:
        return None
    hammer_options = _option_for_hand_card(obs, {ENHANCED_HAMMER}, OT_PLAY)
    if len(hammer_options) < len(blockers):
        return None
    target = _active(opp)
    hand_count = int(mine.get("handCount", len(mine.get("hand") or [])) or 0)
    hp = int((target or {}).get("hp", 0) or 0)
    if hp <= 0 or max(0, hand_count - len(blockers)) * 20 < hp:
        return None
    return RuleProposal(
        "AZ006_UNBLOCK_EXACT_KO", (hammer_options[0],), 240, "candidate",
        "全blockerを剥がした後のHand Powerでactiveを確定KOできる",
    )


def _az007_ash_zero_deck_max(
    obs: dict, _card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """山札0枚のSacred Ashで、全候補を戻せる局面をshadow監査する。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    effect = sel.get("effect") or {}
    if (sel.get("type") != ST_CARD or sel.get("context") != CTX_TO_DECK
            or not isinstance(effect, dict) or effect.get("id") != SACRED_ASH
            or players is None):
        return None
    mine, _ = players
    options = sel.get("option") or []
    try:
        max_count = int(sel.get("maxCount", 0))
    except (TypeError, ValueError):
        return None
    if (int(mine.get("deckCount", 0) or 0) != 0 or not options
            or len(options) > max_count):
        return None
    if any(
        not isinstance(option, dict) or option.get("type") != OT_CARD
        or option.get("area") != AR_DISCARD
        for option in options
    ):
        return None
    return RuleProposal(
        "AZ007_ASH_ZERO_DECK_MAX", tuple(range(len(options))), 280, "hard",
        "山札0枚でSacred Ashの全回収候補を山札へ戻す",
    )


def _az008_draw_to_exact_ko(
    obs: dict, card_energy_types: Mapping[int, int],
) -> RuleProposal | None:
    """Dudunsparceの3 drawでHand Power KOへ届くとき能力を候補化する。"""
    sel = obs.get("select") or {}
    players = _players(obs)
    if sel.get("type") != ST_MAIN or sel.get("maxCount") != 1 or players is None:
        return None
    mine, opp = players
    target = _active(opp)
    if (not _alakazam_ready(mine) or target is None
            or _effect_blocker_on_active(opp, card_energy_types)
            or int(mine.get("deckCount", 0) or 0) < 3):
        return None
    hand_count = int(mine.get("handCount", len(mine.get("hand") or [])) or 0)
    hp = int(target.get("hp", 0) or 0)
    if hp <= 0 or not hand_count * 20 < hp <= (hand_count + 3) * 20:
        return None
    if not any(
        isinstance(option, dict) and option.get("type") == OT_ATTACK
        and option.get("attackId") == HAND_POWER
        for option in sel.get("option") or []
    ):
        return None
    bench = mine.get("bench") or []
    for i, option in enumerate(sel.get("option") or []):
        if (not isinstance(option, dict) or option.get("type") != OT_ABILITY
                or option.get("area") != AR_BENCH):
            continue
        try:
            pokemon = bench[int(option["index"])]
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if isinstance(pokemon, dict) and pokemon.get("id") == DUDUNSPARCE:
            return RuleProposal(
                "AZ008_DRAW_TO_EXACT_KO", (i,), 230, "candidate",
                "3枚draw後のHand Powerでactiveを確定KOできる",
            )
    return None


RULES: dict[str, RuleFn] = {
    "AZ001_EMPTY_BENCH_BASIC": _az001_empty_bench_basic,
    "AZ002_DRAW_EVOLUTION": _az002_draw_evolution,
    "AZ003_HAMMER_BLOCKER_PLAY": _az003_hammer_blocker_play,
    "AZ004_HAMMER_BLOCKER_TARGET": _az004_hammer_blocker_target,
    "AZ005_SOLE_DUDUN_GUARD": _az005_sole_dudun_guard,
    "AZ006_UNBLOCK_EXACT_KO": _az006_unblock_exact_ko,
    "AZ007_ASH_ZERO_DECK_MAX": _az007_ash_zero_deck_max,
    "AZ008_DRAW_TO_EXACT_KO": _az008_draw_to_exact_ko,
}

PROFILES = {
    "alakazam_v1": tuple(RULES),
}


def validate_config(profile: str | None, mode: str,
                    enabled_rule_ids: Iterable[str] | None) -> tuple[str, ...]:
    """起動時に設定ミスを止め、正規化したrule ID列を返す。"""
    if not profile:
        if enabled_rule_ids not in (None, [], ()):
            raise ValueError("expert_rules未指定でenabled_rule_idsは使えない")
        return ()
    if profile not in PROFILES:
        raise ValueError(f"未知のexpert_rules profile: {profile}")
    if mode not in KNOWN_MODES:
        raise ValueError(f"expert_rule_modeは{sorted(KNOWN_MODES)}: {mode}")
    if enabled_rule_ids is None:
        if mode in {"candidate", "enforce"}:
            raise ValueError(f"{mode}ではenabled_rule_idsを明示する")
        return PROFILES[profile]
    if isinstance(enabled_rule_ids, (str, bytes)):
        raise ValueError("enabled_rule_idsは文字列の配列")
    ids = tuple(enabled_rule_ids)
    if (not ids or any(not isinstance(x, str) or not x for x in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("enabled_rule_idsは1件以上・重複なしの非空文字列配列")
    unknown = set(ids) - set(PROFILES[profile])
    if unknown:
        raise ValueError(f"profile外のrule ID: {sorted(unknown)}")
    return ids


def evaluate(obs_dict: dict, deck: Iterable[int], profile: str | None,
             enabled_rule_ids: Iterable[str] = (),
             card_energy_types: Mapping[int, int] | None = None,
             ) -> list[RuleProposal]:
    """現在局面で発火した合法ルールを優先度順に返す。例外は呼び手が救済する。"""
    if not profile or profile not in PROFILES or not _is_alakazam_deck(deck):
        return []
    enabled = tuple(enabled_rule_ids) or PROFILES[profile]
    energy_types = card_energy_types or {}
    proposals = []
    for rule_id in enabled:
        fn = RULES.get(rule_id)
        if fn is None:
            continue
        proposal = fn(obs_dict, energy_types)
        if proposal is not None and legal_action(obs_dict, proposal.action):
            proposals.append(proposal)
    return sorted(proposals, key=lambda p: (-p.priority, p.rule_id))


def best_hard(proposals: Iterable[RuleProposal]) -> RuleProposal | None:
    hard = [p for p in proposals if p.kind == "hard"]
    if not hard:
        return None
    # 異なるhard actionが競合したらpriorityで押し切らず、従来BCSへ戻す。
    if len({p.action for p in hard}) != 1:
        return None
    return min(hard, key=lambda p: (-p.priority, p.rule_id))


def forbidden_actions(proposals: Iterable[RuleProposal]) -> set[tuple[int, ...]]:
    """証明済みnegative guardが禁止する行動集合。"""
    return {p.action for p in proposals if p.kind == "forbid"}
