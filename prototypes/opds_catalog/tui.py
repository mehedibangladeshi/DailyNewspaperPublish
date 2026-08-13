#!/usr/bin/env python3
"""PROTOTYPE — throwaway, see NOTES.md.

Run: .venv/bin/python prototypes/opds_catalog/tui.py

Thin terminal shell over logic.py. All the actual behavior being tested
(rolling-window expiry, multi-source feed shape, idempotent same-day
rebuilds) lives in logic.py as pure functions — this file only renders
state and dispatches keystrokes.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logic

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"

SOURCES = {
    "1": ("jugantor", "Jugantor"),
    "2": ("prothomalo", "Prothom Alo (hypothetical 2nd source)"),
}


def clear():
    print("\033[2J\033[H", end="")


def render(state, last_removed):
    clear()
    print(f"{BOLD}OPDS catalog prototype{RESET}")
    print(f"{DIM}today={state['today'].isoformat()}  retention_days={state['retention_days']}{RESET}")
    print()

    if not state["sources"]:
        print(f"{DIM}(no sources registered yet — press 1 or 2){RESET}")
    for slug, editions in state["sources"].items():
        name = editions[0]["source_name"] if editions else slug
        print(f"{BOLD}{slug}{RESET} {DIM}({name}){RESET}")
        if not editions:
            print(f"  {DIM}no active editions{RESET}")
        for e in editions:
            age = (state["today"] - e["date"]).days
            print(f"  {e['date'].isoformat()}  age={age}d  {DIM}{e['filename']}{RESET}")
        print()

    if last_removed:
        print(f"{BOLD}expired this tick (delete from storage):{RESET}")
        for e in last_removed:
            print(f"  {DIM}{e['source_slug']}/{e['filename']}{RESET}")
        print()

    print(f"{BOLD}[1]{RESET}{DIM} build jugantor today  {RESET}"
          f"{BOLD}[2]{RESET}{DIM} build prothomalo today  {RESET}"
          f"{BOLD}[f]{RESET}{DIM} simulate failed build  {RESET}")
    print(f"{BOLD}[t]{RESET}{DIM} advance day + expire  {RESET}"
          f"{BOLD}[v]{RESET}{DIM} view rendered OPDS XML  {RESET}"
          f"{BOLD}[q]{RESET}{DIM} quit{RESET}")


def main():
    state = logic.initial_state(today=date.today(), retention_days=7)
    last_removed = []
    render(state, last_removed)

    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "q":
            break
        elif cmd in SOURCES:
            slug, name = SOURCES[cmd]
            state = logic.register_source(state, slug, name)
            state = logic.add_edition(state, slug, name)
            last_removed = []
        elif cmd == "f":
            last_removed = []  # no-op: a failed build adds nothing, mirrors main.py's per-article/source skip
        elif cmd == "t":
            state = logic.advance_day(state)
            state, last_removed = logic.expire(state)
        elif cmd == "v":
            clear()
            print(logic.render_opds_xml(state))
            input(f"\n{DIM}-- press enter to go back --{RESET}")
            last_removed = []
        else:
            last_removed = []

        render(state, last_removed)

    print("bye")


if __name__ == "__main__":
    main()
