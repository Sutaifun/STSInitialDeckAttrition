"""耦合抽牌：出牌 / 回合末 / 敌人回写三堆，与独立快路径共享 draw_scheduler。"""

from __future__ import annotations

import gc
import time
from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from typing import TYPE_CHECKING

from engine.combat import (
    ATTACKS,
    BASH_VULNERABLE,
    CARD_BLOCK,
    CARD_COST,
    CARD_DAMAGE,
    _calc_attack_damage,
    _calc_block,
    _deal_damage_to_enemy,
    _deal_damage_to_player,
    block_is_sufficient,
    can_kill_this_turn,
    has_playable_attack,
)
from engine.deck import BASH, CARD_INDEX, DEFEND, Pile, SLIMED, STRIKE, pile_add
from engine.draw_scheduler import weighted_draw_at_turn_start, weighted_opening
from engine.encounter import EncounterSpec, fixed_enemy_turn_for
from engine.progress import NullProgress, ProgressCallback
from engine.types import EMPTY_PILE, ENERGY_PER_TURN, MAX_DAMAGE, State

if TYPE_CHECKING:
    pass

INF_DAMAGE = 10**9
HARD_TURN_CAP = 40

COUPLED_PLAYABLE = (STRIKE, DEFEND, BASH, SLIMED)


def play_card_coupled(state: State, card: str) -> State | None:
    """打出一张牌；粘液进 exhaust，其余进 discard。"""
    if state.energy <= 0:
        return None
    cost = CARD_COST.get(card)
    if cost is None or state.energy < cost:
        return None

    idx = CARD_INDEX[card]
    if state.hand[idx] <= 0:
        return None

    hand = list(state.hand)
    hand[idx] -= 1
    discard = list(state.discard)
    exhaust = list(state.exhaust)
    if card == SLIMED:
        exhaust[idx] += 1
    else:
        discard[idx] += 1

    nxt = replace(
        state,
        energy=state.energy - cost,
        hand=tuple(hand),
        discard=tuple(discard),
        exhaust=tuple(exhaust),
    )

    if card == STRIKE:
        dmg = _calc_attack_damage(
            CARD_DAMAGE[STRIKE], nxt.player_strength, nxt.player_weak, nxt.enemy_vulnerable
        )
        nxt = _deal_damage_to_enemy(nxt, dmg)
    elif card == BASH:
        dmg = _calc_attack_damage(
            CARD_DAMAGE[BASH], nxt.player_strength, nxt.player_weak, nxt.enemy_vulnerable
        )
        nxt = _deal_damage_to_enemy(nxt, dmg)
        nxt = replace(nxt, enemy_vulnerable=nxt.enemy_vulnerable + BASH_VULNERABLE)
    elif card == DEFEND:
        block = _calc_block(CARD_BLOCK[DEFEND], nxt.player_dexterity, nxt.player_frail)
        nxt = replace(nxt, player_block=nxt.player_block + block)
    return nxt

def _finalize_remaining_hand(state: State) -> State:
    """回合末：未打出的手牌进弃牌堆；诅咒虚无 → 消耗。"""
    discard = pile_add(state.discard, state.hand)
    exhaust = state.exhaust
    bane = state.hand[3]
    if bane > 0:
        discard = (
            discard[0],
            discard[1],
            discard[2],
            discard[3] - bane,
            discard[4],
        )
        exhaust = (
            exhaust[0],
            exhaust[1],
            exhaust[2],
            exhaust[3] + bane,
            exhaust[4],
        )
    return replace(state, hand=EMPTY_PILE, discard=discard, exhaust=exhaust, energy=0)


def _incoming_fixed_damage(state: State, turn_spec: dict) -> int:
    per_hit = _calc_attack_damage(
        turn_spec["damage"], 0, 0, state.player_vulnerable
    )
    block = state.player_block
    total = 0
    for _ in range(turn_spec.get("hits", 1)):
        absorbed = min(block, per_hit)
        block -= absorbed
        total += per_hit - absorbed
    return total


def block_is_sufficient_coupled(state: State, turn_spec: dict) -> bool:
    return _incoming_fixed_damage(state, turn_spec) == 0


def has_playable_attack_coupled(state: State) -> bool:
    for card in ATTACKS:
        cost = CARD_COST[card]
        idx = CARD_INDEX[card]
        if cost is not None and state.energy >= cost and state.hand[idx] > 0:
            return True
    return False


def _play_candidates_coupled(state: State, *, lethal_possible: bool, turn_spec: dict) -> tuple[str, ...]:
    if state.enemy_hp <= 0:
        return ()
    if lethal_possible:
        return ATTACKS
    if block_is_sufficient_coupled(state, turn_spec) and has_playable_attack_coupled(state):
        return ATTACKS
    if block_is_sufficient_coupled(state, turn_spec):
        return (SLIMED,) if _can_play_slimed(state) else ()
    out = list(ATTACKS) + [DEFEND]
    if _can_play_slimed(state):
        out.append(SLIMED)
    return tuple(out)


def _can_play_slimed(state: State) -> bool:
    cost = CARD_COST.get(SLIMED)
    return (
        cost is not None
        and state.energy >= cost
        and state.hand[CARD_INDEX[SLIMED]] > 0
    )


def _may_end_turn_coupled(state: State, *, lethal_possible: bool, turn_spec: dict) -> bool:
    if state.enemy_hp <= 0:
        return True
    if lethal_possible:
        return False
    if block_is_sufficient_coupled(state, turn_spec) and has_playable_attack_coupled(state):
        return False
    return True


def apply_fixed_enemy_turn(state: State, spec: EncounterSpec) -> State:
    """固定 AI 表：伤害、debuff、塞粘液进弃牌堆。"""
    turn_spec = fixed_enemy_turn_for(spec, state.turn_count)
    state = replace(
        state,
        enemy_block=0,
        enemy_vulnerable=max(0, state.enemy_vulnerable - 1),
    )
    if state.enemy_hp <= 0:
        return state

    if turn_spec.get("frail", 0):
        state = replace(state, player_frail=state.player_frail + turn_spec["frail"])
    if turn_spec.get("weak", 0):
        state = replace(state, player_weak=state.player_weak + turn_spec["weak"])

    per_hit = _calc_attack_damage(
        turn_spec["damage"], 0, 0, state.player_vulnerable
    )
    for _ in range(turn_spec.get("hits", 1)):
        state = _deal_damage_to_player(state, per_hit)

    add_slimed = turn_spec.get("add_slimed", 0)
    if add_slimed:
        discard = list(state.discard)
        discard[CARD_INDEX[SLIMED]] += add_slimed
        state = replace(state, discard=tuple(discard))

    return replace(
        state,
        intent_index=(state.intent_index + 1) % max(1, len(spec.intents)),
    )


def end_player_turn_coupled(state: State, spec: EncounterSpec) -> State:
    state = _finalize_remaining_hand(state)
    if state.enemy_hp <= 0:
        return state
    state = apply_fixed_enemy_turn(state, spec)
    if state.enemy_hp <= 0 or state.damage_taken >= MAX_DAMAGE:
        return state
    return replace(
        state,
        player_block=0,
        player_vulnerable=max(0, state.player_vulnerable - 1),
        player_weak=max(0, state.player_weak - 1),
        player_frail=max(0, state.player_frail - 1),
        turn_count=state.turn_count + 1,
        energy=ENERGY_PER_TURN,
        hand=EMPTY_PILE,
        hand_at_turn_start=EMPTY_PILE,
    )


def inject_slimed_to_discard(discard: Pile, amount: int = 1) -> Pile:
    d = list(discard)
    d[CARD_INDEX[SLIMED]] += amount
    return tuple(d)


def piles_after_slime_choice(
    hand: Pile,
    draw: Pile,
    discard: Pile,
    exhaust: Pile,
    *,
    play_slime: bool,
) -> tuple[Pile, Pile, Pile]:
    """
    验收用例：手牌含 1 粘液，选择打或不打后回合末三堆（无其它牌、无诅咒）。
    返回 (draw, discard, exhaust)。
    """
    state = State(
        enemy_hp=999,
        enemy_block=0,
        enemy_strength=0,
        enemy_vulnerable=0,
        intent_index=0,
        player_block=0,
        player_vulnerable=0,
        player_weak=0,
        player_frail=0,
        player_strength=0,
        player_dexterity=0,
        damage_taken=0,
        turn_count=1,
        energy=ENERGY_PER_TURN,
        hand=hand,
        draw=draw,
        discard=discard,
        exhaust=exhaust,
        hand_at_turn_start=hand,
    )
    if play_slime:
        played = play_card_coupled(state, SLIMED)
        assert played is not None
        state = played
    else:
        state = replace(state, energy=0)
    state = _finalize_remaining_hand(state)
    return state.draw, state.discard, state.exhaust


CoupledFrontierKey = tuple


def _frontier_key(state: State) -> CoupledFrontierKey:
    return (
        state.enemy_hp,
        state.enemy_block,
        state.enemy_strength,
        state.enemy_vulnerable,
        state.intent_index,
        state.player_vulnerable,
        state.player_weak,
        state.player_frail,
        state.player_strength,
        state.player_dexterity,
        state.damage_taken,
        state.turn_count,
        state.draw,
        state.discard,
        state.exhaust,
    )


def _state_from_frontier(key: CoupledFrontierKey, hand: Pile) -> State:
    return State(
        enemy_hp=key[0],
        enemy_block=key[1],
        enemy_strength=key[2],
        enemy_vulnerable=key[3],
        intent_index=key[4],
        player_block=0,
        player_vulnerable=key[5],
        player_weak=key[6],
        player_frail=key[7],
        player_strength=key[8],
        player_dexterity=key[9],
        damage_taken=key[10],
        turn_count=key[11],
        energy=ENERGY_PER_TURN,
        hand=hand,
        draw=key[12],
        discard=key[13],
        exhaust=key[14],
        hand_at_turn_start=hand,
    )


def coupled_within_turn(
    state: State,
    spec: EncounterSpec,
    memo: dict,
) -> tuple[bool, dict[CoupledFrontierKey, int]]:
    """
    单回合：枚举出牌，结束回合 + 固定敌人行动。
    返回 (can_kill, {下一回合初 frontier_key → 本回合额外战损})。
    """
    turn_spec = fixed_enemy_turn_for(spec, state.turn_count)
    key = (
        _frontier_key(state),
        state.hand,
        state.energy,
    )
    cached = memo.get(key)
    if cached is not None:
        return cached

    alive: dict[CoupledFrontierKey, int] = {}
    can_kill = False
    seen: set = set()

    def rec(s: State) -> None:
        nonlocal can_kill
        if s.enemy_hp <= 0:
            can_kill = True
            return
        sig = (
            s.enemy_hp,
            s.enemy_block,
            s.enemy_vulnerable,
            s.player_block,
            s.energy,
            s.hand,
            s.discard,
            s.exhaust,
        )
        if sig in seen:
            return
        seen.add(sig)

        if _may_end_turn_coupled(
            s, lethal_possible=can_kill_this_turn(s), turn_spec=turn_spec
        ):
            after = end_player_turn_coupled(s, spec)
            extra = after.damage_taken - state.damage_taken
            fk = _frontier_key(after)
            if fk not in alive or extra < alive[fk]:
                alive[fk] = extra

        lethal = can_kill_this_turn(s)
        for card in _play_candidates_coupled(s, lethal_possible=lethal, turn_spec=turn_spec):
            ns = play_card_coupled(s, card)
            if ns is not None:
                rec(ns)

    rec(state)
    result = (can_kill, alive)
    memo[key] = result
    return result


def solve_encounter_coupled(
    spec: EncounterSpec,
    enemy_hp: int,
    *,
    progress: ProgressCallback | None = None,
    gc_interval: int = 500,
    hard_turn_cap: int = HARD_TURN_CAP,
) -> dict:
    """耦合模式 DFS：前沿键含 (战斗 CS, draw, discard, exhaust)。"""
    assert spec.draw_mode == "coupled" and spec.fixed_enemy_turns is not None
    reporter = progress or NullProgress()
    label = f"{spec.encounter_id} HP={enemy_hp}"
    reporter.on_start(0, label)

    total_w = Fraction(0)
    must_w = Fraction(0)
    sum_wd = Fraction(0)
    hist: dict[int, Fraction] = defaultdict(Fraction)
    min_damage: int | None = None
    max_damage: int | None = None
    leaves = 0
    truncated = 0

    wt_memo: dict = {}

    def record(weight: Fraction, damage: int) -> None:
        nonlocal total_w, must_w, sum_wd, min_damage, max_damage, leaves
        total_w += weight
        sum_wd += weight * damage
        hist[damage] += weight
        if damage > 0:
            must_w += weight
        min_damage = damage if min_damage is None else min(min_damage, damage)
        max_damage = damage if max_damage is None else max(max_damage, damage)
        leaves += 1
        reporter.on_step(leaves, 0, label)
        if gc_interval > 0 and leaves % gc_interval == 0:
            gc.collect()

    def dfs(
        turn_idx: int,
        frontier: dict[CoupledFrontierKey, int],
        weight: Fraction,
        best_kill: int,
    ) -> None:
        nonlocal truncated
        sample = next(iter(frontier))
        draw = sample[12]
        discard = sample[13]
        exhaust = sample[14]

        if turn_idx == 1:
            branches = weighted_opening(spec.starting_deck, spec.hand_size)
        else:
            branches = weighted_draw_at_turn_start(
                draw, discard, exhaust, spec.hand_size
            )

        for tp, step_p in branches:
            w = weight * step_p
            nf: dict[CoupledFrontierKey, int] = {}
            bk = best_kill
            for fk, dmg in frontier.items():
                st = _state_from_frontier(fk, tp.hand)
                st = replace(
                    st,
                    draw=tp.draw,
                    discard=tp.discard,
                    exhaust=tp.exhaust,
                )
                can_kill, alive = coupled_within_turn(st, spec, wt_memo)
                if can_kill and dmg < bk:
                    bk = dmg
                for nfk, extra in alive.items():
                    nd = dmg + extra
                    if nfk not in nf or nd < nf[nfk]:
                        nf[nfk] = nd

            surv = min(nf.values()) if nf else INF_DAMAGE
            if bk <= surv:
                record(w, bk)
            elif turn_idx >= hard_turn_cap:
                truncated += 1
                record(w, bk if bk < INF_DAMAGE else surv)
            else:
                dfs(turn_idx + 1, nf, w, bk)

    t0 = time.perf_counter()
    init_key: CoupledFrontierKey = (
        enemy_hp,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        spec.starting_deck,
        EMPTY_PILE,
        EMPTY_PILE,
    )
    try:
        dfs(1, {init_key: 0}, Fraction(1), INF_DAMAGE)
    finally:
        pass
    elapsed = time.perf_counter() - t0
    reporter.on_finish(label, elapsed)
    gc.collect()

    p_must = float(must_w / total_w) if total_w else 0.0
    e_damage = float(sum_wd / total_w) if total_w else 0.0
    distribution = {
        d: float(w / total_w) for d, w in sorted(hist.items())
    } if total_w else {}

    return {
        "enemy_hp": enemy_hp,
        "encounter_id": spec.encounter_id,
        "draw_mode": spec.draw_mode,
        "leaves": leaves,
        "total_weight": float(total_w),
        "p_must_damage": p_must,
        "e_damage": e_damage,
        "min_damage": min_damage or 0,
        "max_damage": max_damage or 0,
        "distribution": distribution,
        "truncated": truncated,
    }
