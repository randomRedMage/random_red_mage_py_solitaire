"""Localized help content for solitaire modes."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, Mapping, Optional, Tuple

DEFAULT_HELP_LOCALE = "en"
_HELP_FILENAME_TEMPLATE = "help_{locale}.json"
_HELP_DIR = os.path.join(os.path.dirname(__file__), "assets", "help")


@dataclass(frozen=True)
class HelpContent:
    """Immutable container for help metadata for a solitaire mode."""

    title: str
    lines: Tuple[str, ...]
    max_width: Optional[int] = None

    def as_modal_args(self) -> Tuple[str, Tuple[str, ...], Optional[int]]:
        """Return positional arguments for :class:`solitaire.ui.ModalHelp`."""

        return self.title, self.lines, self.max_width


def _help_file_path(locale: str) -> str:
    filename = _HELP_FILENAME_TEMPLATE.format(locale=locale)
    return os.path.join(_HELP_DIR, filename)


@lru_cache()
def _load_locale(locale: str) -> Dict[str, HelpContent]:
    path = _help_file_path(locale)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise FileNotFoundError(f"Help locale '{locale}' not found at {path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError(f"Help file {path} must contain an object mapping game ids to entries")

    entries: Dict[str, HelpContent] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            raise TypeError(f"Help entry for '{key}' must be a mapping")
        title = value.get("title")
        lines = value.get("lines")
        max_width = value.get("max_width")
        if not isinstance(title, str):
            raise TypeError(f"Help entry for '{key}' is missing a string 'title'")
        if not isinstance(lines, Iterable) or isinstance(lines, (str, bytes)):
            raise TypeError(f"Help entry for '{key}' must provide a list of help lines")
        normalised_lines = []
        for line in lines:
            if not isinstance(line, str):
                raise TypeError(f"Help entry for '{key}' contains a non-string line: {line!r}")
            normalised_lines.append(line)
        if max_width is not None and not isinstance(max_width, int):
            raise TypeError(f"Help entry for '{key}' has non-integer max_width")
        entries[key] = HelpContent(title=title, lines=tuple(normalised_lines), max_width=max_width)
    return entries


def get_help_content(game_id: str, *, locale: str = DEFAULT_HELP_LOCALE) -> HelpContent:
    """Return the help content for the given solitaire mode."""

    entries = _load_locale(locale)
    try:
        return entries[game_id]
    except KeyError as exc:
        raise KeyError(f"No help content defined for game id '{game_id}' and locale '{locale}'") from exc


def available_help_ids(*, locale: str = DEFAULT_HELP_LOCALE) -> Tuple[str, ...]:
    """Return all game ids with help available for the requested locale."""

    return tuple(_load_locale(locale).keys())


def create_modal_help(game_id: str, *, locale: str = DEFAULT_HELP_LOCALE):
    """Construct a :class:`solitaire.ui.ModalHelp` using stored help content."""

    from solitaire.ui import ModalHelp

    content = get_help_content(game_id, locale=locale)
    kwargs = {"max_width": content.max_width} if content.max_width is not None else {}
    return ModalHelp(content.title, list(content.lines), **kwargs)
