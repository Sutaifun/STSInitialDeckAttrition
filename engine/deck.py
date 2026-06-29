"""牌组多重集：用各牌种张数表示牌堆，枚举「选 k 张」的组合。"""

from __future__ import annotations

import math
from typing import Iterator

STRIKE = "S"
DEFEND = "D"
BASH = "B"
BANE = "X"

CARD_ORDER = (STRIKE, DEFEND, BASH, BANE)
CARD_INDEX = {c: i for i, c in enumerate(CARD_ORDER)}

# 铁甲战士 A10：5 打 4 防 1 痛击 1 诅咒
IRONCLAD_A10_DECK: tuple[int, int, int, int] = (5, 4, 1, 1)

Pile = tuple[int, int, int, int]


def pile_total(p: Pile) -> int:
    return sum(p)


def pile_add(a: Pile, b: Pile) -> Pile:
    return tuple(x + y for x, y in zip(a, b))


def pile_sub(a: Pile, b: Pile) -> Pile:
    return tuple(x - y for x, y in zip(a, b))


def pile_valid(p: Pile) -> bool:
    return all(x >= 0 for x in p)


def draw_one_card(p: Pile, card: str) -> Pile | None:
    i = CARD_INDEX[card]
    if p[i] <= 0:
        return None
    parts = list(p)
    parts[i] -= 1
    return tuple(parts)


def combinations_draw(pool: Pile, k: int) -> Iterator[tuple[Pile, Pile]]:
    """
    从 pool 中选出 k 张牌的所有组合（不计顺序）。
    产出 (抽中的张数, 抽牌堆剩余)。
    """
    if k < 0 or pile_total(pool) < k:
        return
    if k == 0:
        yield ((0, 0, 0, 0), pool)
        return

    limits = list(pool)

    def rec(idx: int, remaining: int, picked: list[int]) -> Iterator[tuple[Pile, Pile]]:
        if idx == 4:
            if remaining == 0:
                drawn = tuple(picked)
                left = pile_sub(pool, drawn)
                if pile_valid(left):
                    yield (drawn, left)
            return
        max_take = min(remaining, limits[idx])
        for take in range(max_take + 1):
            picked.append(take)
            yield from rec(idx + 1, remaining - take, picked)
            picked.pop()

    yield from rec(0, k, [])


def opening_hand_combinations() -> Iterator[tuple[Pile, Pile]]:
    """第 1 回合：从 11 张中选 5 张上手（所有不同组合）。"""
    yield from combinations_draw(IRONCLAD_A10_DECK, 5)


def opening_combination_count() -> int:
    return sum(1 for _ in opening_hand_combinations())


def distinct_perm_count(deck: tuple[str, ...]) -> int:
    """保留兼容：与组合数不同，旧脚本勿用。"""
    n = len(deck)
    num = math.factorial(n)
    for k in CARD_ORDER:
        num //= math.factorial(deck.count(k))
    return num
