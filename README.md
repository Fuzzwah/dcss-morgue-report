# dcss-morgue-report

Turn a [Dungeon Crawl Stone Soup](https://crawl.develz.org/) player's morgue files into a
self-contained, stats-heavy HTML career report — charts, death ledger, archetypes,
a sortable/filterable table of every run, and the game's own sprite art for the
monsters, uniques and species that show up.

Built with the Python standard library only. No dependencies, no build step, no
internet needed to view the report (charts are inline SVG, tiles are embedded).

![report preview](data/reports/Fuzzwah.html)

## Features

- **Career overview** — games, wins, best score, deepest run, turns, playtime, runes, gold
- **Timeline** — games per year, best score per year, average max XL per year, cumulative score
- **The Reaper's ledger** — top killers with their sprites, deaths by branch, deaths by XL,
  deaths by hour, and **deaths vs uniques**: every named unique that ended a run, its art
  and how many times it got you
- **Post-mortem** — what went wrong, per run and across the career: unused escape/healing
  consumables, unidentified items, chip-death vs one-shot damage math, resist gaps,
  empty ring/amulet slots, unenchanted gear, god abilities never invoked, god wrath,
  banishes, deaths right after entering a branch. Every finding carries the evidence
  and one line of advice, tagged high/medium/low severity.
- **Archetypes** — species (each with its character portrait), backgrounds, species ×
  background heatmap, gods worshipped
- **Every run** — sortable/filterable table of every game: character portrait, XL, god,
  runes, turns, time, score, depth reached, cause of death (with the killer's sprite),
  uniques slain, mistake count
- **Milestones** — firsts, records, longest hiatus
- **Sprite art** — real DCSS tiles for monsters, uniques and species, fetched from the
  crawl repository (public-domain/CC0 art) and embedded as data URIs so the report stays
  one file. God-wrath deaths show the responsible god's altar, cloud deaths show their
  effect art, monsters removed from the repo fall back to their last released art, and
  anything with no art anywhere (e.g. "nerve-wracking pain") gets a subtle no-art glyph;
  `--no-tiles` builds the text-only report offline
- **JSON export** — the full parsed dataset for your own analysis

## Requirements

- Python 3.10+ (stdlib only)
- A DCSS morgue server (default: `https://crawl.project357.org`)

## Quick start

```bash
# install (optional; running from the repo works too)
pip install -e .

# download a player's morgues and build the report in one go
python -m dcssreport all Fuzzwah
```

Open `data/reports/Fuzzwah.html` in a browser. The raw morgues land in
`data/raw/<player>/` and the report + JSON in `data/reports/`.

Re-run anytime to pick up new games — the fetcher skips files it already has.

## CLI

```
python -m dcssreport fetch  <player> [--base-url URL] [--force]
python -m dcssreport report <player> [--raw DIR] [--out DIR] [--source-url URL]
python -m dcssreport all    <player> [options for both]
```

| Option | Default | Meaning |
|---|---|---|
| `--base-url` | `https://crawl.project357.org` | morgue server root |
| `--raw` | `data/raw/<player>` | local morgue cache dir |
| `--out` | `data/reports` | report + JSON output dir |
| `--tiles` | `data/tiles` | tile art + layout cache dir |
| `--no-tiles` | off | skip sprite images (text-only report, works offline) |
| `--force` | off | re-download morgues already present |
| `--source-url` | server index | link shown in the report footer |

## How it works

1. **Fetch** (`dcssreport/fetch.py`) — scrapes the server's morgue index and downloads every
   `morgue-<player>-*.txt` not already cached.
2. **Parse** (`dcssreport/parse.py`) — extracts score, character, species/background, XL, god,
   death cause/killer/damage, branch reached, duration, turns, gold, runes, skills, resists,
   and the turn-by-turn notes into a typed `Game` record. Handles morgues from DCSS 0.18
   (2016) through 0.35: `Health:`/`HP:` stat lines, renamed branches
   (`Orcish Mines` → `Orc`, `Lair of Beasts` → `Lair`, …), 20+ death verb forms
   (`Killed from afar by …`, `Frozen to death by …`, `Blown up by …`), buffed-stat
   parentheses, `Sept` dates, and the removed vanquished-creatures section.
3. **Aggregate** (`dcssreport/stats.py`) — roll-ups per year, species/background/god,
   killer/death-branch/XL/hour distributions, uniques slain, cumulative totals.
4. **Tiles** (`dcssreport/tiles.py`) — parses the crawl repo's `rltiles` layout files into
   a monster-tile inventory, resolves every killer / slain-unique / species name that
   appears in the data (slug rules plus aliases for renames, colors and boss variants),
   downloads just those 32×32 sprites into a cache, and hands the renderer data URIs.
   Best-effort: if the tile fetch fails the report is generated without images.
5. **Render** (`dcssreport/render.py`) — one self-contained HTML page with hand-rolled
   SVG charts, embedded sprites and a small vanilla-JS sortable table.

## Layout

```
dcssreport/
  __init__.py     version
  __main__.py     CLI
  fetch.py        morgue downloader
  parse.py        morgue → Game records
  mistakes.py     per-run mistake analysis (post-mortem rules)
  stats.py        aggregation
  render.py       HTML + SVG report
data/
  raw/<player>/   downloaded morgues (gitignored)
  tiles/          tile art + layout cache (gitignored)
  reports/        <player>.html + <player>.json (example report committed)
```

## Example

`data/reports/Fuzzwah.html` is a generated report for the author's own career:
104 games (2016–2025), 0 wins, best score 296,714 (XL 20), 96 of 104 runs as a Trog
worshipper, 805,474 turns across 2 days and 5 hours of play. Named uniques ended 9 of
those runs (Terence and Rupert twice each) and the morgues record 55 distinct uniques
slain. Regenerate it any time with `python -m dcssreport all Fuzzwah`.
