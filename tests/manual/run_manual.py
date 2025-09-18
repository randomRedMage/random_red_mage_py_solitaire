#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import subprocess


MODES = [
    {"id": "klondike", "label": "Klondike", "supports_tall": True},
    {"id": "freecell", "label": "FreeCell", "supports_tall": True},
    {"id": "yukon", "label": "Yukon", "supports_tall": True},
    {"id": "gate", "label": "Gate", "supports_tall": True},
    {"id": "beleaguered", "label": "Beleaguered Castle", "supports_tall": True},
    {"id": "bigben", "label": "Big Ben", "supports_tall": False},
]

CARD_SIZES = ["Small", "Medium", "Large"]


def pick(prompt, options):
    while True:
        print(prompt)
        for i, opt in enumerate(options, 1):
            print(f"  {i}) {opt}")
        sel = input("> ").strip()
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(options):
                return idx
        except Exception:
            pass
        print("Invalid selection, please try again.\n")


def yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        ans = input(f"{prompt} ({d}): ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"): return True
        if ans in ("n", "no"): return False
        print("Please answer y or n.")


def main():
    print("Manual Mode Launcher (developer-only)\n")
    mode_idx = pick("Select a game mode:", [m["label"] for m in MODES])
    mode = MODES[mode_idx]

    size_idx = pick("Select card size:", CARD_SIZES)
    card_size = CARD_SIZES[size_idx]

    tall_ok = mode["supports_tall"]
    tall_label = "Create tall/wide test layout for edge-pan" + (" (not applicable)" if not tall_ok else "")
    tall = False
    if tall_ok:
        tall = yes_no(tall_label + "?", default=True)
    else:
        print(tall_label)

    # Build environment for child process
    env = dict(os.environ)
    env["SOLI_DEBUG_SCENE"] = mode["id"]
    env["SOLI_CARD_SIZE"] = card_size
    env["SOLI_DEBUG_TALL"] = "1" if tall else "0"

    # Repo root is two levels up from this file: tests/manual/..
    repo_root = Path(__file__).resolve().parents[2]
    print("\nLaunching:")
    print(f"  Scene    : {mode['label']} ({mode['id']})")
    print(f"  CardSize : {card_size}")
    print(f"  TallTest : {'Yes' if tall else 'No'}")
    print("")
    try:
        subprocess.run([sys.executable, "-m", "solitaire"], cwd=str(repo_root), env=env, check=False)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

