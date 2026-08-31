# dcss-morgue-report

Turn a [Dungeon Crawl Stone Soup](https://crawl.develz.org/) player's morgue files into a
self-contained, stats-heavy HTML career report — charts, death ledger, archetypes,
and a sortable/filterable table of every run.

Built with the Python standard library only. No dependencies, no build step, no
internet needed to view the report (charts are inline SVG).

![report preview](data/reports/Fuzzwah.html)

## Features

- **Career overview** — games, wins, best score, deepest run, turns, playtime, runes, gold
- **Timeline** — games per year, best score per year, average max XL per year, cumulative score
- **The Reaper's ledger** — top killers, deaths by branch, deaths by XL, deaths by hour
- **Archetypes** — species, backgrounds, species × background heatmap, gods worshipped
- **Every run** — sortable/filterable table of all 95+ games: character, XL, god, runes,
  turns, time, score, depth reached, cause of death, uniques slain
- **Milestones** — firsts, records, longest hiatus
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
4. **Render** (`dcssreport/render.py`) — one self-contained HTML page with hand-rolled
   SVG charts and a small vanilla-JS sortable table.

## Layout

```
dcssreport/
  __init__.py     version
  __main__.py     CLI
  fetch.py        morgue downloader
  parse.py        morgue → Game records
  stats.py        aggregation
  render.py       HTML + SVG report
data/
  raw/<player>/   downloaded morgues (gitignored)
  reports/        <player>.html + <player>.json (example report committed)
```

## Example

`data/reports/Fuzzwah.html` is a generated report for the author's own career:
95 games, 0 wins, best score 296,714 (XL 20), 87 of 95 games as a Trog worshipper,
737,164 turns across 2 days and 1 hour of play. Regenerate it any time with
`python -m dcssreport all Fuzzwah`.
