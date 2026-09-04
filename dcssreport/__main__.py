"""CLI: fetch morgues, build the report.

Usage:
    python -m dcssreport fetch  <player> [--base-url URL] [--force]
    python -m dcssreport report <player> [--raw DIR] [--out DIR] [--source-url URL]
    python -m dcssreport all    <player> [options for both]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__, tiles
from .fetch import download_morgues
from .mistakes import run_all as analyze_mistakes
from .parse import parse_dir
from .render import render_html
from .stats import build

DEFAULT_BASE = "https://crawl.project357.org"


def _serialize(game):
    d = asdict(game)
    for k in ("game_date", "death_date", "began_date"):
        v = d.get(k)
        d[k] = v.isoformat() if v else None
    return d


def cmd_fetch(args: argparse.Namespace) -> int:
    paths = download_morgues(args.base_url, args.player, args.raw, force=args.force)
    print(f"fetched {len(paths)} morgue files into {args.raw}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    raw = Path(args.raw)
    games = parse_dir(raw)
    if not games:
        print(f"no morgue files found in {raw}", file=sys.stderr)
        return 1
    analyze_mistakes(games)
    rs = build(games)

    # Tile art is best-effort: without it the report is text-only, which keeps
    # `report` usable offline (from an existing raw cache).
    images: dict[str, str] = {}
    unique_deaths: dict[str, int] = {}
    catalog = None
    if not args.no_tiles:
        tile_dir = Path(args.tiles)
        texts = tiles.fetch_layouts(tile_dir)
        if texts is None:
            print("warning: could not fetch tile art (offline?) — report will have no images",
                  file=sys.stderr)
        else:
            catalog = tiles.Catalog.parse(texts)
            monster_names = set(rs.killers) | set(rs.uniques)
            species_names = {s for s, _ in rs.species.items()}
            images = tiles.embed_monster_tiles(monster_names, tile_dir, catalog)
            images.update(tiles.embed_species_tiles(species_names, tile_dir))
            # branch rows get each branch's entrance (stair) art — for both
            # the visits card and the deaths card
            branch_names = set(rs.death_branches)
            for g in rs.games:
                branch_names.update(g.branches_visited)
                branch_names.update(g.extra_branches)
                branch_names.update(k for k in g.entered_turns)
                if g.death_branch:
                    branch_names.add(g.death_branch)
            branch_uri: dict[str, str | None] = {}
            for b in sorted(branch_names):
                rel = tiles.branch_relpath(b)
                if rel not in branch_uri:
                    branch_uri[rel] = tiles.embed_relpath(rel, tile_dir)
                if branch_uri[rel]:
                    images.setdefault(b, branch_uri[rel])
            # worn-gear part layers for the character portraits
            gear_parts: set[str] = set()
            for gm in rs.games:
                gear_parts.update(tiles.gear_rels(gm))
            for rel in gear_parts:
                uri = tiles.embed_relpath(rel, tile_dir)
                if uri:
                    images[f"part:{rel}"] = uri
            # god altars for the Gods-worshipped rows
            for god in rs.gods:
                rel = tiles.altar_relpath(god)
                if rel:
                    uri = tiles.embed_relpath(rel, tile_dir)
                    if uri:
                        images.setdefault(god, uri)
            # god-wrath deaths ("divine providence") carry the altar of the
            # god most often responsible
            wrath_gods: dict[str, int] = {}
            for g in rs.games:
                if (g.killer or "") in tiles.GOD_KILLER_CAUSES and g.god:
                    wrath_gods[g.god] = wrath_gods.get(g.god, 0) + 1
            if wrath_gods:
                god = max(wrath_gods, key=wrath_gods.get)
                uri = tiles.embed_relpath(tiles.altar_relpath(god), tile_dir)
                if uri:
                    images.setdefault("divine providence", uri)
            slain = {tiles.slug(u) for u in rs.uniques}
            unique_deaths = {k: c for k, c in rs.killers.items()
                             if tiles.is_unique_killer(catalog, k, slain)}
            print(f"tiles: {len(images)} image(s), "
                  f"{len(unique_deaths)} unique killer(s)")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{args.player}.html"
    json_path = out_dir / f"{args.player}.json"

    source_url = args.source_url or f"{args.base_url}/morgue/{args.player}/"
    html_path.write_text(
        render_html(rs, args.player, source_url=source_url,
                    images=images, unique_deaths=unique_deaths),
        encoding="utf-8")
    json_path.write_text(
        json.dumps({"player": args.player, "generated": __version__,
                    "games": [_serialize(g) for g in games]},
                   indent=1, ensure_ascii=False),
        encoding="utf-8")

    print(f"parsed {len(games)} games ({len(rs.unparsed)} unparsed)")
    print(f"  wins: {rs.wins}  best score: {rs.best_game.score if rs.best_game else 0}"
          f"  best XL: {rs.best_xl}")
    print(f"report: {html_path}")
    print(f"data:   {json_path}")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    rc = cmd_fetch(args)
    if rc:
        return rc
    return cmd_report(args)


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", default=DEFAULT_BASE,
                        help=f"DCSS morgue server root (default {DEFAULT_BASE})")
    common.add_argument("--raw", default=None, help="raw morgue directory")
    common.add_argument("--out", default=None, help="output directory")
    common.add_argument("--force", action="store_true", help="re-download morgues")
    common.add_argument("--source-url", default=None, help="link for the report footer")
    common.add_argument("--tiles", default=None,
                        help="tile cache directory (default data/tiles)")
    common.add_argument("--no-tiles", action="store_true",
                        help="skip monster/species tile images")

    p = argparse.ArgumentParser(prog="dcssreport", description=__doc__,
                                parents=[common])
    sub = p.add_subparsers(dest="command", required=True)
    for name, func in (("fetch", cmd_fetch), ("report", cmd_report), ("all", cmd_all)):
        sp = sub.add_parser(name, parents=[common], help=f"{name} step")
        sp.add_argument("player")
        sp.set_defaults(func=func)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.raw is None:
        args.raw = f"data/raw/{args.player}"
    if args.out is None:
        args.out = "data/reports"
    if args.tiles is None:
        args.tiles = "data/tiles"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
