"""Aggregate parsed games into report statistics."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .parse import Game, depth_score, killer_of

NUMERICS = ("score", "xl", "turns", "duration", "gold", "vanquished", "runes")


@dataclass
class YearStats:
    year: int
    games: int = 0
    wins: int = 0
    turns: int = 0
    seconds: int = 0
    score: int = 0
    runes: int = 0
    xls: list[int] = field(default_factory=list)
    scores: list[int] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)

    @property
    def avg_xl(self) -> float:
        return statistics.fmean(self.xls) if self.xls else 0.0

    @property
    def avg_duration_min(self) -> float:
        return (statistics.fmean(self.durations) / 60.0) if self.durations else 0.0


@dataclass
class ReportStats:
    games: list[Game] = field(default_factory=list)
    total_games: int = 0
    wins: int = 0
    win_rate: float = 0.0
    total_turns: int = 0
    total_seconds: int = 0
    total_score: int = 0
    total_runes: int = 0
    total_gold: int = 0
    first_date: datetime | None = None
    last_date: datetime | None = None
    best_game: Game | None = None
    deepest_game: Game | None = None
    longest_game: Game | None = None
    best_xl: int = 0
    years: list[YearStats] = field(default_factory=list)
    species: Counter = field(default_factory=Counter)
    backgrounds: Counter = field(default_factory=Counter)
    species_bg: Counter = field(default_factory=Counter)
    gods: Counter = field(default_factory=Counter)
    god_xl: dict[str, list[int]] = field(default_factory=dict)
    killers: Counter = field(default_factory=Counter)
    causes: Counter = field(default_factory=Counter)
    death_branches: Counter = field(default_factory=Counter)
    xl_histogram: Counter = field(default_factory=Counter)
    hour_histogram: Counter = field(default_factory=Counter)
    uniques: Counter = field(default_factory=Counter)
    cumulative: list[tuple[datetime, int, int]] = field(default_factory=list)  # (date, turns, score)
    version_counts: Counter = field(default_factory=Counter)
    unparsed: list[str] = field(default_factory=list)
    mistake_counts: Counter = field(default_factory=Counter)
    mistakes_total: int = 0
    games_with_mistakes: int = 0
    games_high: int = 0
    offenders: list = field(default_factory=list)  # games with most mistakes
    mistake_meta: dict[str, tuple[str, str]] = field(default_factory=dict)  # rule -> (label, severity)


def build(games: list[Game]) -> ReportStats:
    rs = ReportStats(games=sorted(games, key=lambda g: g.game_date or datetime.min))
    rs.total_games = len(rs.games)
    rs.unparsed = [g.source for g in rs.games if g.score is None]

    years: dict[int, YearStats] = {}
    run_turns = run_score = 0

    for g in rs.games:
        d = g.game_date
        if d:
            rs.first_date = rs.first_date or d
            rs.last_date = d
        if g.outcome == "win":
            rs.wins += 1
        rs.total_turns += g.turns or 0
        rs.total_seconds += g.duration or 0
        rs.total_score += g.score or 0
        rs.total_runes += g.runes or 0
        rs.total_gold += g.gold or 0
        rs.best_xl = max(rs.best_xl, g.xl or 0)
        if g.score and (rs.best_game is None or g.score > (rs.best_game.score or 0)):
            rs.best_game = g
        if rs.deepest_game is None or g.depth > rs.deepest_game.depth:
            rs.deepest_game = g
        if g.duration and (rs.longest_game is None or g.duration > rs.longest_game.duration):
            rs.longest_game = g

        if g.species:
            rs.species[g.species] += 1
        if g.background:
            rs.backgrounds[g.background] += 1
        if g.species and g.background:
            rs.species_bg[(g.species, g.background)] += 1
        if g.god:
            rs.gods[g.god] += 1
            rs.god_xl.setdefault(g.god, []).append(g.xl or 0)
        if g.killer:
            rs.killers[killer_of(g.killer)] += 1
        if g.cause_short:
            rs.causes[g.cause_short] += 1
        if g.death_branch:
            rs.death_branches[g.death_branch] += 1
        if g.xl:
            rs.xl_histogram[g.xl] += 1
        if d:
            rs.hour_histogram[d.hour] += 1
        for u in g.uniques_killed:
            rs.uniques[u] += 1
        if g.version:
            rs.version_counts[g.version] += 1

        if d:
            run_turns += g.turns or 0
            run_score += g.score or 0
            rs.cumulative.append((d, run_turns, run_score))

        y = d.year if d else 0
        ys = years.setdefault(y, YearStats(year=y))
        ys.games += 1
        if g.outcome == "win":
            ys.wins += 1
        ys.turns += g.turns or 0
        ys.seconds += g.duration or 0
        ys.score += g.score or 0
        ys.runes += g.runes or 0
        if g.xl:
            ys.xls.append(g.xl)
        if g.score:
            ys.scores.append(g.score)
        if g.duration:
            ys.durations.append(g.duration)

    for g in rs.games:
        for mk in g.mistakes:
            rs.mistake_counts[mk.rule] += 1
            rs.mistake_meta.setdefault(mk.rule, (mk.label, mk.severity))
        if g.mistakes:
            rs.games_with_mistakes += 1
            if any(mk.severity == "high" for mk in g.mistakes):
                rs.games_high += 1
        rs.mistakes_total += len(g.mistakes)
    rs.offenders = sorted(rs.games, key=lambda g: len(g.mistakes), reverse=True)[:5]

    if rs.total_games:
        rs.win_rate = rs.wins / rs.total_games * 100.0
    rs.years = [years[y] for y in sorted(y for y in years if y)]
    return rs
