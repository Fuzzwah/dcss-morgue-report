#!/usr/bin/env python3
"""Rebuild docs/ for GitHub Pages.

Copies the example reports from data/reports/ into docs/examples/ and
regenerates docs/index.html (the project overview) with a gallery card per
example.  Run after regenerating any example report:

    python3 build_docs.py
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "data" / "reports"
DOCS = ROOT / "docs"
EXAMPLES = DOCS / "examples"

#: (report file stem, player display name, one-line description)
GALLERY = [
    ("Fuzzwah", "Fuzzwah",
     "The author's career — 104 Minotaur/Trog runs across a decade."),
    ("PurpleRed", "PurpleRed",
     "1,188 games and 57 wins: a Deep Elf Conjurer specialist with nine "
     "15-rune victories, including a 75-million-point Archmage win."),
    ("Wizard1ke", "Wizard1ke",
     "Modern speedrunner — currently #1 on the dcss-stats highscores."),
]

_TITLE_SMALL = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}


def title_case(s: str) -> str:
    words = s.split()
    return " ".join(
        w.capitalize() if i == 0 or w.lower() not in _TITLE_SMALL else w.lower()
        for i, w in enumerate(words)
    ) or s


def card(stem: str, name: str, blurb: str) -> str:
    path = REPORTS / f"{stem}.json"
    meta = ""
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        games = d["games"]
        wins = sum(1 for g in games if g.get("outcome") == "win")
        best = max((g.get("score") or 0) for g in games)
        years = [g.get("game_date", "")[:4] for g in games if g.get("game_date")]
        span = f"{years[0]}–{years[-1]}" if years else "?"
        hl = ""
        if games:
            top = max(games, key=lambda g: g.get("score") or 0)
            hl = f"{title_case(top.get('species') or '?')} {title_case(top.get('background') or '')} · " \
                 f"{top.get('runes', 0)} runes · {top.get('score', 0):,}"
        meta = (f'<div class="meta">{span} · <b>{len(games):,}</b> games · '
                f'<b>{wins}</b> win(s) · best <b>{best:,}</b><br>{html.escape(hl)}</div>')
    return (f'<a class="example" href="examples/{stem}.html">'
            f"<h3>{html.escape(name)}</h3>{meta}"
            f'<p class="blurb">{html.escape(blurb)}</p></a>')


def build() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    cards = []
    for stem, name, blurb in GALLERY:
        src = REPORTS / f"{stem}.html"
        if not src.exists():
            print(f"skip {stem}: {src} missing (run the report first)")
            continue
        (EXAMPLES / f"{stem}.html").write_bytes(src.read_bytes())
        cards.append(card(stem, name, blurb))
    if not cards:
        raise SystemExit("no example reports found")

    index = DOCS / "index.html"
    template = index.read_text(encoding="utf-8")
    import re
    marker_re = re.compile(
        r"<!-- exs:begin -->.*?<!-- exs:end -->", re.S)
    if not marker_re.search(template):
        raise SystemExit("docs/index.html gallery markers not found")
    block = "<!-- exs:begin -->\n    " + "\n    ".join(cards) + "\n    <!-- exs:end -->"
    out = marker_re.sub(lambda _: block, template, count=1)
    index.write_text(out, encoding="utf-8")
    print(f"docs rebuilt: {len(cards)} example(s), updated {len(out)}-byte index")


if __name__ == "__main__":
    build()
