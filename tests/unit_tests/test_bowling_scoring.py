from typing import List, Optional

import pytest

from solitaire.modes.bowling_scoring import calculate_frame_totals


@pytest.mark.parametrize(
    "rolls, expected",
    [
        ([10] * 12, [30, 60, 90, 120, 150, 180, 210, 240, 270, 300]),
        (
            [9, 1] * 9 + [9, 1, 9],
            [19, 38, 57, 76, 95, 114, 133, 152, 171, 190],
        ),
        (
            [0, 0] * 9 + [10, 10, 10],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 30],
        ),
        (
            [0, 0] * 8 + [7, 3] + [10, 10, 10],
            [0, 0, 0, 0, 0, 0, 0, 0, 20, 50],
        ),
        (
            [7, 3, 5, 4] + [0, 0] * 8,
            [15, 24, 24, 24, 24, 24, 24, 24, 24, 24],
        ),
        (
            [10, 7, 3, 7, 2] + [0, 0] * 7,
            [20, 37, 46, 46, 46, 46, 46, 46, 46, 46],
        ),
    ],
)
def test_calculate_frame_totals_complete_games(
    rolls: List[int], expected: List[Optional[int]]
) -> None:
    assert calculate_frame_totals(rolls) == expected


def test_calculate_frame_totals_requires_future_rolls() -> None:
    totals = calculate_frame_totals([10, 3])
    assert totals[0] is None
    assert all(total is None for total in totals[1:])

