# dcss-morgue-report

Turn a [Dungeon Crawl Stone Soup](https://crawl.develz.org/) player's morgue files into a
self-contained, stats-heavy HTML career report — charts, milestone records, per-monster
and per-branch breakdowns, layered character portraits wearing the gear they had on, and
a sortable/filterable table of every run.

Built with the Python standard library only. No dependencies, no build step, no
internet needed to view the report (charts are inline SVG, tiles are embedded).

![report preview](data/reports/Fuzzwah.html)

## Features

- **Career overview** — games, wins, best score, deepest run, turns, playtime, runes, gold
- **Milestone records** — first game/rune/XL, longest game, most uniques slain, longest hiatus
- **Timeline** — games per year, best score per year, average max XL per year, cumulative score
- **Archetypes** — species (each with its character portrait), backgrounds, species ×
  background heatmap, gods worshipped (with their altar art)
- **Best runs** — a detail table of the highest-scoring runs: layered character portrait,
  species, background, god, XL, runes, score, depth reached and playtime
- **Monsters** — monster by monster, kills and deaths: top killers with their sprites,
  most-slain uniques, and **deaths vs uniques** (every named unique that ended a run,
  its art, and how many times it got you)
- **Branches** — how often each branch was entered and how many runs ended there, each
  branch shown with its own entrance/portal art (historic names included)
- **Death patterns** — deaths by XP level and by hour of day
- **Post-mortem** — what went wrong, per run and across the career: unused escape/healing
  consumables, unidentified items, chip-death vs one-shot damage math, resist gaps,
  empty ring/amulet slots, unenchanted gear, god abilities never invoked, god wrath,
  banishes, deaths right after entering a branch. Every finding carries the evidence
  and one line of advice, tagged high/medium/low severity.
- **Every run** — sortable/filterable table of every game at the bottom of the page:
  a layered character portrait with the gear worn at death, XL, god, runes, turns, time,
  score, depth reached, cause of death (with the killer's sprite), uniques slain,
  mistake count
- **Sprite art** — real DCSS tiles for monsters, uniques, species and more, fetched from
  the crawl repository (public-domain/CC0 art) and embedded once so the report stays one
  file. Characters are drawn layered from the parts they were wearing (species body +
  armour/helm/weapon), god-wrath deaths show the responsible god's altar, cloud deaths
  their effect art, branch rows their entrance tiles; monsters removed from the repo
  fall back to their last released art (or rescued `UNUSED` art), and anything with no
  art anywhere (e.g. "nerve-wracking pain") gets a subtle no-art glyph. `--no-tiles`
  builds the text-only report offline
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
   parentheses, `Sept` dates, and the removed vanquished-creatures section. Also copes
   with the era quirks this exposes: 0.19-era two-line win banners, dev-fork morgues that
   report a bogus XL on rune-wins, player-ghost kills that are not uniques, and species
   renames/splits (`Gale Centaur`, coloured Draconians).
3. **Aggregate** (`dcssreport/stats.py`) — roll-ups per year, species/background/god,
   killer/death-branch/XL/hour distributions, uniques slain, cumulative totals.
4. **Tiles** (`dcssreport/tiles.py`) — parses the crawl repo's `rltiles` layout files into
   a monster-tile inventory, resolves every killer / slain-unique / species / branch / god
   name that appears in the data (slug rules plus aliases for renames, colors and boss
   variants; historic release tags and `UNUSED` art for removed monsters), and maps each
   character's equipped inventory to the layered gear parts (body armour, helm, weapon)
   drawn over the species body. Only the sprites a report needs are downloaded into a
   cache. Best-effort: if the tile fetch fails the report is generated without images.
5. **Render** (`dcssreport/render.py`) — one self-contained HTML page: hand-rolled SVG
   charts, layered character sprites, image art embedded once in a token dictionary
   (repeated rows reference it instead of re-embedding megabytes of base64), and a small
   vanilla-JS sortable table.

## Layout

```
dcssreport/
  __init__.py     version
  __main__.py     CLI
  fetch.py        morgue downloader
  parse.py        morgue → Game records
  mistakes.py     per-run mistake analysis (post-mortem rules)
  stats.py        aggregation
  tiles.py        tile-art catalog, gear parts, download cache
  render.py       HTML + SVG report
data/
  raw/<player>/   downloaded morgues (gitignored)
  tiles/          tile art + layout cache (gitignored)
  reports/        <player>.html + <player>.json (example report committed)
```

## Example

`data/reports/Fuzzwah.html` is a generated report for the author's own career:
104 games (2016–2026), 0 wins, best score 296,714 (XL 20), 96 of 104 runs as a Trog
worshipper, 805,474 turns across 2 days and 5 hours of play. Named uniques ended 9 of
those runs (Terence and Rupert twice each) and the morgues record 55 distinct uniques
slain. Regenerate it any time with `python -m dcssreport all Fuzzwah`.
