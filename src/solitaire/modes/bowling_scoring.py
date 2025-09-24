"""Scoring helpers for Bowling Solitaire."""

from __future__ import annotations

from typing import List, Optional, Sequence


def calculate_frame_totals(rolls: Sequence[int]) -> List[Optional[int]]:
    """Return cumulative frame totals following ten-pin bowling rules."""

    totals: List[Optional[int]] = [None] * 10
    cumulative = 0
    roll_index = 0

    for frame_index in range(10):
        if roll_index >= len(rolls):
            break

        first = rolls[roll_index]

        if frame_index < 9:
            if first == 10:
                if roll_index + 2 >= len(rolls):
                    break
                cumulative += 10 + rolls[roll_index + 1] + rolls[roll_index + 2]
                totals[frame_index] = cumulative
                roll_index += 1
                continue

            if roll_index + 1 >= len(rolls):
                break

            second = rolls[roll_index + 1]
            if first + second == 10:
                if roll_index + 2 >= len(rolls):
                    break
                cumulative += 10 + rolls[roll_index + 2]
            else:
                cumulative += first + second

            totals[frame_index] = cumulative
            roll_index += 2
            continue

        if roll_index + 1 >= len(rolls):
            break

        second = rolls[roll_index + 1]
        if first == 10:
            if roll_index + 2 >= len(rolls):
                break
            third = rolls[roll_index + 2]
            cumulative += 10 + second + third
        elif first + second == 10:
            if roll_index + 2 >= len(rolls):
                break
            third = rolls[roll_index + 2]
            cumulative += 10 + third
        else:
            cumulative += first + second

        totals[frame_index] = cumulative
        break

    return totals

