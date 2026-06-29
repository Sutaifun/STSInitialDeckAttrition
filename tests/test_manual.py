"""手算用例：验证战斗引擎与求解器基本正确性。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.combat import (
    block_is_sufficient,
    can_kill_this_turn,
    end_player_turn,
    incoming_damage,
    make_turn_state,
    play_card,
)
from engine.deck import IRONCLAD_A10_DECK, opening_combination_count, pile_sub
from engine.draw_scheduler import TurnPiles, _draw_at_turn_start, enumerate_draw_paths
from engine.solver import solve_draw_path


def test_opening_count():
    assert opening_combination_count() == 19


def test_strike_kills_no_damage():
    """1 张打击，敌人 6 HP，T1 击杀 → 0 战损。"""
    path = (TurnPiles(hand=(1, 0, 0, 0), draw=(4, 4, 1, 1), discard=(0, 0, 0, 0), exhaust=(0, 0, 0, 0)),)
    assert solve_draw_path(6, path) == 0


def test_bash_then_strike_damage():
    state = make_turn_state(enemy_hp=20, hand=(1, 0, 1, 0), draw=(4, 4, 0, 1))
    s = play_card(state, "B")
    assert s is not None and s.enemy_hp == 12 and s.enemy_vulnerable == 2
    s = play_card(s, "S")
    assert s is not None and s.enemy_hp == 3


def test_defend_blocks_attack():
    hand = (0, 3, 0, 0)
    state = make_turn_state(enemy_hp=47, hand=hand, draw=(5, 1, 1, 1))
    s = state
    for _ in range(3):
        s = play_card(s, "D")
    assert s.player_block == 15
    after = end_player_turn(s)
    assert after.damage_taken == 0
    assert after.turn_count == 2


def test_bane_exhaust():
    hand = (0, 0, 0, 1)
    state = make_turn_state(enemy_hp=47, hand=hand, draw=(5, 4, 1, 0))
    after = end_player_turn(state)
    assert after.exhaust[3] == 1
    assert after.discard[3] == 0


def test_draw_scheduler_t2():
    hand_t1 = (2, 2, 1, 0)
    draw_after_t1 = pile_sub(IRONCLAD_A10_DECK, hand_t1)
    branches = list(_draw_at_turn_start(draw_after_t1, hand_t1, (0, 0, 0, 0)))
    assert len(branches) > 1
    for b in branches:
        assert sum(b.hand) == 5


def test_path_enumeration_starts_with_19():
    first_turn_hands = {p[0].hand for p in enumerate_draw_paths(1)}
    assert len(first_turn_hands) == 19


def test_can_kill_this_turn():
    state = make_turn_state(enemy_hp=6, hand=(1, 0, 0, 0), draw=(4, 4, 1, 1))
    assert can_kill_this_turn(state)


def test_block_sufficient_skips_extra_defend():
    """3 张防御 = 15 格挡，可挡 13 伤。"""
    state = make_turn_state(enemy_hp=47, hand=(0, 3, 0, 0), draw=(5, 1, 1, 1))
    s = state
    for _ in range(3):
        s = play_card(s, "D")
    assert s is not None and block_is_sufficient(s)
    assert incoming_damage(s) == 0


if __name__ == "__main__":
    test_opening_count()
    test_strike_kills_no_damage()
    test_bash_then_strike_damage()
    test_defend_blocks_attack()
    test_bane_exhaust()
    test_draw_scheduler_t2()
    test_path_enumeration_starts_with_19()
    test_can_kill_this_turn()
    test_block_sufficient_skips_extra_defend()
    print("全部通过")
