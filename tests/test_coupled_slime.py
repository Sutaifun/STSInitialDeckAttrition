"""耦合抽牌：粘液写回、模式开关、small_slimes A 权重不变量。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fractions import Fraction

from engine.coupled import inject_slimed_to_discard, piles_after_slime_choice, solve_encounter_coupled
from engine.encounter import (
    build_encounter_spec,
    default_pilot_spec,
    small_slimes_variant_a_spec,
)
from engine.solver import solve_encounter

WEIGHT_TOLERANCE = 1e-9


def test_seapunk_uses_independent_mode():
    spec = default_pilot_spec()
    assert spec.draw_mode == "independent"
    assert spec.encounter_id == "seapunk"


def test_small_slimes_a_uses_coupled_mode():
    spec = small_slimes_variant_a_spec(ascension="low")
    assert spec.draw_mode == "coupled"
    assert spec.fixed_enemy_turns is not None
    assert len(spec.fixed_enemy_turns) >= 1


def test_pilot_golden_still_independent():
    spec = build_encounter_spec(encounter_id="seapunk", game="sts2")
    assert spec.draw_mode == "independent"


def test_slime_not_played_goes_to_discard():
    """§5(i)：塞 1 粘液，不打 → 回合末进弃牌堆，exhaust 不变。"""
    hand = (0, 0, 0, 0, 1)
    draw = (5, 4, 1, 1, 0)
    discard = (0, 0, 0, 0, 0)
    exhaust = (0, 0, 0, 0, 0)
    d, disc, exh = piles_after_slime_choice(
        hand, draw, discard, exhaust, play_slime=False
    )
    assert d == draw
    assert disc[4] == 1
    assert exh == exhaust


def test_slime_played_goes_to_exhaust():
    """§5(ii)：打出粘液 → exhaust +1，与「不打」后继三堆不同。"""
    hand = (0, 0, 0, 0, 1)
    draw = (5, 4, 1, 1, 0)
    discard = (0, 0, 0, 0, 0)
    exhaust = (0, 0, 0, 0, 0)
    d0, disc0, exh0 = piles_after_slime_choice(
        hand, draw, discard, exhaust, play_slime=False
    )
    d1, disc1, exh1 = piles_after_slime_choice(
        hand, draw, discard, exhaust, play_slime=True
    )
    assert d0 == d1 == draw
    assert disc0[4] == 1 and exh0[4] == 0
    assert disc1[4] == 0 and exh1[4] == 1
    assert (d0, disc0, exh0) != (d1, disc1, exh1)


def test_inject_slimed_to_discard():
    base = (0, 0, 0, 0, 0)
    got = inject_slimed_to_discard(base, 2)
    assert got[4] == 2


def test_coupled_small_slimes_weight_sums_to_one():
    spec = small_slimes_variant_a_spec(ascension="low")
    hp = 36
    r = solve_encounter(hp, spec=spec)
    assert r["draw_mode"] == "coupled"
    assert r["truncated"] == 0, r["truncated"]
    assert abs(r["total_weight"] - 1.0) < WEIGHT_TOLERANCE, r["total_weight"]
    assert r["leaves"] > 0


def test_coupled_entry_direct():
    spec = small_slimes_variant_a_spec(ascension="low")
    r = solve_encounter_coupled(spec, 36)
    assert abs(r["total_weight"] - 1.0) < WEIGHT_TOLERANCE


def test_weighted_opening_independent_unchanged():
    from engine.draw_scheduler import weighted_opening

    spec = default_pilot_spec()
    total = sum(
        (p for _, p in weighted_opening(spec.starting_deck, spec.hand_size)),
        Fraction(0),
    )
    assert total == Fraction(1)


if __name__ == "__main__":
    test_seapunk_uses_independent_mode()
    test_small_slimes_a_uses_coupled_mode()
    test_slime_not_played_goes_to_discard()
    test_slime_played_goes_to_exhaust()
    test_coupled_small_slimes_weight_sums_to_one()
    print("coupled tests: 全部通过")
