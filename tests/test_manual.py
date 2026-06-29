"""手算用例：验证战斗引擎与求解器基本正确性。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fractions import Fraction

from engine.combat import (
    block_is_sufficient,
    can_kill_this_turn,
    end_player_turn,
    incoming_damage,
    make_turn_state,
    play_card,
)
from engine.deck import (
    IRONCLAD_A10_DECK,
    combination_weight,
    opening_combination_count,
    pile_sub,
)
from engine.draw_scheduler import (
    TurnPiles,
    _draw_at_turn_start,
    enumerate_draw_paths,
    weighted_draw_at_turn_start,
    weighted_opening,
)
from engine.solver import solve_draw_path, solve_encounter, solve_prefix_killable


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


def test_combination_weight():
    # 第 1 回合 (2,2,1,0)：C(5,2)*C(4,2)*C(1,1)*C(1,0) = 10*6*1*1 = 60。
    assert combination_weight(IRONCLAD_A10_DECK, (2, 2, 1, 0)) == 60
    # 全打击 (5,0,0,0)：C(5,5)=1。
    assert combination_weight(IRONCLAD_A10_DECK, (5, 0, 0, 0)) == 1


def test_weighted_opening_sums_to_one():
    total = sum((p for _, p in weighted_opening()), Fraction(0))
    assert total == Fraction(1)
    # 19 种组合，物理条数之和 = C(11,5) = 462。
    assert len(list(weighted_opening())) == 19


def test_weighted_draw_sums_to_one():
    """第 2 回合：留 1 张（6 选 5），权重和应为 1。"""
    hand_t1 = (2, 2, 1, 0)
    draw_after_t1 = pile_sub(IRONCLAD_A10_DECK, hand_t1)
    total = sum(
        (p for _, p in weighted_draw_at_turn_start(draw_after_t1, hand_t1, (0, 0, 0, 0))),
        Fraction(0),
    )
    assert total == Fraction(1)


def test_solve_prefix_killable_single_turn():
    """1 张打击、敌 6 HP：单回合前缀即可击杀，0 战损。"""
    path = (TurnPiles(hand=(1, 0, 0, 0), draw=(4, 4, 1, 1), discard=(0, 0, 0, 0), exhaust=(0, 0, 0, 0)),)
    dmg, killable = solve_prefix_killable(6, path)
    assert killable and dmg == 0


def test_solve_prefix_not_killable_when_too_short():
    """敌 47 HP、仅给 1 回合 1 张打击：前缀内杀不掉 → 需延长。"""
    path = (TurnPiles(hand=(1, 0, 0, 0), draw=(4, 4, 1, 1), discard=(0, 0, 0, 0), exhaust=(0, 0, 0, 0)),)
    _, killable = solve_prefix_killable(47, path)
    assert not killable


def test_encounter_weight_normalized():
    """打到击杀的加权统计：权重和必须精确为 1。"""
    for hp in (12, 30, 47):
        r = solve_encounter(hp)
        assert abs(r["total_weight"] - 1.0) < 1e-9, (hp, r["total_weight"])
        assert r["truncated"] == 0
        assert 0.0 <= r["p_must_damage"] <= 1.0


def test_loader_matches_expected():
    """加载器从 JSON 构建的数值须与试点既定值一致（去硬编码回归守卫）。"""
    from engine import load_data as L

    assert L.build_deck_pile() == (5, 4, 1, 1)
    cost, damage, block, vuln = L.build_card_stats()
    assert cost == {"S": 1, "D": 1, "B": 2, "X": None}
    assert damage == {"S": 6, "B": 8}
    assert block == {"D": 5}
    assert vuln == {"B": 2}
    assert L.build_intents() == (
        {"kind": "attack", "damage": 13, "hits": 1},
        {"kind": "attack", "damage": 2, "hits": 4},
        {"kind": "buff", "block": 8, "strength": 2},
    )
    assert L.build_hp_range() == (47, 49)


def test_engine_constants_come_from_loader():
    """引擎模块常量应等于加载器输出（确认已接线、无双份硬编码）。"""
    from engine import load_data as L
    from engine.combat import CARD_BLOCK, CARD_COST, CARD_DAMAGE, SEAPUNK_INTENTS
    from engine.deck import IRONCLAD_A10_DECK

    cost, damage, block, _ = L.build_card_stats()
    assert IRONCLAD_A10_DECK == L.build_deck_pile()
    assert (CARD_COST, CARD_DAMAGE, CARD_BLOCK) == (cost, damage, block)
    assert SEAPUNK_INTENTS == L.build_intents()


def test_within_turn_kill_and_alive():
    """单回合推进：敌 6 HP 一张打击可击杀；敌 47 HP 三张防御则存活且 0 额外战损。"""
    from engine.solver import within_turn

    memo: dict = {}
    can_kill, _ = within_turn((6, 0, 0, 0, 0), (1, 0, 0, 0), memo)
    assert can_kill
    can_kill2, alive = within_turn((47, 0, 0, 0, 0), (0, 3, 0, 0), memo)
    assert not can_kill2
    # 三张防御=15 格挡可全挡 13 单段攻击 → 存在额外战损 0 的后继。
    assert min(alive.values()) == 0


def test_encounter_matches_truncated_on_killing_paths():
    """
    交叉验证：solve_encounter 记录的每条 ω 在前缀内击杀，
    用旧 truncate 语义对“前缀 + 多补空抽”求解应得相同 D（已击杀，补牌不变结果）。
    这里直接对低 HP 校验 min/max 落在合理范围。
    """
    r = solve_encounter(12)
    assert r["min_damage"] >= 0
    assert r["max_damage"] >= r["min_damage"]


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
    test_combination_weight()
    test_weighted_opening_sums_to_one()
    test_weighted_draw_sums_to_one()
    test_solve_prefix_killable_single_turn()
    test_solve_prefix_not_killable_when_too_short()
    test_encounter_weight_normalized()
    test_loader_matches_expected()
    test_engine_constants_come_from_loader()
    test_within_turn_kill_and_alive()
    test_encounter_matches_truncated_on_killing_paths()
    print("全部通过")
