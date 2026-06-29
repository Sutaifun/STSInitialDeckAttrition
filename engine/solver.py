"""层 2：局面求解器 + 整场统计。"""

from __future__ import annotations

import gc
import time

from engine.combat import (
    ATTACKS,
    block_is_sufficient,
    can_kill_this_turn,
    end_player_turn,
    has_playable_attack,
    play_card,
)
from engine.deck import DEFEND
from engine.draw_scheduler import TurnPiles, count_draw_paths, enumerate_draw_paths
from engine.progress import NullProgress, ProgressCallback
from engine.types import MAX_DAMAGE, MAX_TURNS, Pile, SolveResult, State


def _combat_key(state: State) -> tuple:
    return (
        state.enemy_hp,
        state.enemy_block,
        state.enemy_strength,
        state.enemy_vulnerable,
        state.intent_index,
        state.player_block,
        state.player_vulnerable,
        state.player_weak,
        state.player_frail,
        state.player_strength,
        state.player_dexterity,
        state.damage_taken,
        state.turn_count,
    )


def _state_from(combat_key: tuple, piles: TurnPiles, energy: int, hand: Pile, hand_start: Pile) -> State:
    return State(
        combat_key[0],
        combat_key[1],
        combat_key[2],
        combat_key[3],
        combat_key[4],
        combat_key[5],
        combat_key[6],
        combat_key[7],
        combat_key[8],
        combat_key[9],
        combat_key[10],
        combat_key[11],
        combat_key[12],
        energy,
        hand,
        piles.draw,
        piles.discard,
        piles.exhaust,
        hand_start,
    )


def _is_terminal_combat(combat_key: tuple) -> bool:
    return (
        combat_key[0] <= 0
        or combat_key[12] > MAX_TURNS
        or combat_key[11] >= MAX_DAMAGE
    )


def _path_to_key(path: tuple[TurnPiles, ...]) -> tuple:
    return tuple((tp.hand, tp.draw, tp.discard, tp.exhaust) for tp in path)


def _play_candidates(state: State, *, lethal_possible: bool) -> tuple[str, ...]:
    if state.enemy_hp <= 0:
        return ()
    if lethal_possible:
        return ATTACKS
    if block_is_sufficient(state) and has_playable_attack(state):
        return ATTACKS
    if block_is_sufficient(state):
        return ()
    return ATTACKS + (DEFEND,)


def _may_end_turn(state: State, *, lethal_possible: bool) -> bool:
    if state.enemy_hp <= 0:
        return True
    if lethal_possible:
        return False
    if block_is_sufficient(state) and has_playable_attack(state):
        return False
    return True


class _PathSolver:
    """
    单条抽牌路径求解器。
    记忆化表仅在路径内有效，路径结束后随实例回收，避免全局 cache 撑爆内存。
    """

    __slots__ = ("suffix_key", "_memo", "_kill_memo")

    def __init__(self, suffix_key: tuple) -> None:
        self.suffix_key = suffix_key
        self._memo: dict[tuple, int] = {}
        self._kill_memo: dict[tuple, bool] = {}

    def _piles_at(self, turn_idx: int) -> TurnPiles:
        h, d, disc, exh = self.suffix_key[turn_idx]
        return TurnPiles(h, d, disc, exh)

    def _turn_start_state(
        self, combat_key: tuple, turn_idx: int, hand_start: Pile
    ) -> State:
        return _state_from(combat_key, self._piles_at(turn_idx), 3, hand_start, hand_start)

    def solve(self, enemy_hp: int, first_hand: Pile) -> int:
        ck = (
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
            0,
            1,
        )
        return self._solve_turn(ck, 0, 3, first_hand, first_hand)

    def _solve_turn(
        self,
        combat_key: tuple,
        turn_idx: int,
        energy: int,
        hand: tuple[int, int, int, int],
        hand_start: tuple[int, int, int, int],
    ) -> int:
        key = (combat_key, turn_idx, energy, hand, hand_start)
        cached = self._memo.get(key)
        if cached is not None:
            return cached

        if _is_terminal_combat(combat_key):
            self._memo[key] = combat_key[11]
            return combat_key[11]

        state = _state_from(combat_key, self._piles_at(turn_idx), energy, hand, hand_start)

        if state.enemy_hp <= 0:
            self._memo[key] = combat_key[11]
            return combat_key[11]

        turn_start = self._turn_start_state(combat_key, turn_idx, hand_start)
        lethal_possible = can_kill_this_turn(turn_start, self._kill_memo)

        best: int | None = None

        for card in _play_candidates(state, lethal_possible=lethal_possible):
            nxt = play_card(state, card)
            if nxt is not None:
                if nxt.enemy_hp <= 0:
                    self._memo[key] = combat_key[11]
                    return combat_key[11]
                d = self._solve_turn(
                    _combat_key(nxt),
                    turn_idx,
                    nxt.energy,
                    nxt.hand,
                    hand_start,
                )
                if best is None or d < best:
                    best = d
                    if best == 0:
                        self._memo[key] = 0
                        return 0

        if _may_end_turn(state, lethal_possible=lethal_possible):
            after = end_player_turn(state)
            if after.enemy_hp <= 0 or _is_terminal_combat(_combat_key(after)):
                end_dmg = after.damage_taken
            else:
                next_idx = turn_idx + 1
                if next_idx >= len(self.suffix_key):
                    end_dmg = after.damage_taken
                else:
                    np = self._piles_at(next_idx)
                    end_dmg = self._solve_turn(
                        _combat_key(after),
                        next_idx,
                        3,
                        np.hand,
                        np.hand,
                    )

            if best is None or end_dmg < best:
                best = end_dmg

        result = best if best is not None else combat_key[11]
        self._memo[key] = result
        return result


def solve_draw_path(enemy_hp: int, path: tuple[TurnPiles, ...]) -> int:
    if not path:
        return 0
    return _PathSolver(_path_to_key(path)).solve(enemy_hp, path[0].hand)


def solve_state(state: State) -> SolveResult:
    tp = TurnPiles(state.hand, state.draw, state.discard, state.exhaust)
    dmg = solve_draw_path(state.enemy_hp, (tp,))
    return SolveResult(min_damage=dmg, play_path=(), end_state=None, combat_over=False)


def solve_encounter(
    enemy_hp: int,
    max_turns: int = MAX_TURNS,
    *,
    progress: ProgressCallback | None = None,
    gc_interval: int = 500,
) -> dict:
    """
    枚举全部抽牌路径，统计 P(必伤)。

    内存策略：
    - 每条路径独立 _PathSolver，结束即释放 memo
    - 不保存全部战损列表，仅流式累计统计
    - 每 gc_interval 条路径触发一次 gc.collect()
    """
    reporter = progress or NullProgress()
    total = count_draw_paths(max_turns)

    label = f"HP={enemy_hp}"
    reporter.on_start(total, label)

    must = 0
    min_damage: int | None = None
    max_damage: int | None = None

    t0 = time.perf_counter()
    for i, path in enumerate(enumerate_draw_paths(max_turns), start=1):
        d = solve_draw_path(enemy_hp, path)
        if d > 0:
            must += 1
        min_damage = d if min_damage is None else min(min_damage, d)
        max_damage = d if max_damage is None else max(max_damage, d)
        reporter.on_step(i, total, label)
        if gc_interval > 0 and i % gc_interval == 0:
            gc.collect()

    elapsed = time.perf_counter() - t0
    reporter.on_finish(label, elapsed)
    gc.collect()

    return {
        "enemy_hp": enemy_hp,
        "max_turns": max_turns,
        "draw_paths": total,
        "must_damage": must,
        "zero_damage": total - must,
        "p_must_damage": must / total if total else 0.0,
        "min_damage": min_damage or 0,
        "max_damage": max_damage or 0,
    }
