"""Render a self-contained HTML report with inline SVG charts."""

from __future__ import annotations

import html
import statistics
from datetime import datetime

from .parse import Game
from .stats import ReportStats

# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

def fmt_int(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}"


def fmt_dur(seconds: int | None, *, short: bool = False) -> str:
    if not seconds:
        return "—"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if short:
        return f"{h}h {m:02d}m" if h else f"{m}m"
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fmt_dur_long(seconds: int | None) -> str:
    if not seconds:
        return "—"
    days, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")


def fmt_date(d: datetime | None) -> str:
    return d.strftime("%b %d, %Y") if d else "—"


def _fmt_days(days: int) -> str:
    y, rem = divmod(days, 365)
    m, d = divmod(rem, 30)
    if y and m:
        return f"{y}y {m}m"
    if y:
        return f"{y}y"
    if m:
        return f"{m}m {d}d"
    return f"{d}d"


def esc(s: str) -> str:
    return html.escape(str(s))


def pct(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "—"


# --------------------------------------------------------------------------
# SVG chart builders
# --------------------------------------------------------------------------

ACCENT = "#e3b04b"
DEATH = "#d95763"
WIN = "#6ecf7e"
BLUE = "#5b9bd5"
PURPLE = "#a78bfa"
GRID = "#232a38"
TEXT = "#c9d1d9"
MUTED = "#7d8590"


def _tooltip(title: str | None) -> str:
    return f"<title>{esc(title)}</title>" if title else ""


def svg_hbars(rows: list[tuple[str, int, str | None]], *,
              color: str = ACCENT, height: int = 340,
              label_w: int = 170, show_value: bool = True) -> str:
    """Horizontal bar chart. rows: (label, value, tooltip) or (label, value)."""
    if not rows:
        return ""
    rows = [
        (r[0], r[1], r[2]) if len(r) == 3 else (r[0], r[1], None) for r in rows
    ]
    W, H = 720, height
    val_w = 90 if show_value else 0
    chart_w = W - label_w - val_w
    vmax = max(v for _, v, _ in rows)
    pad = 8
    row_h = (H - pad * (len(rows) + 1)) / len(rows)
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img">']
    for i, (label, value, tip) in enumerate(rows):
        y = pad + i * (row_h + pad)
        bar_w = chart_w * (value / vmax) if vmax else 0
        tip = tip or f"{label}: {value:,}"
        parts.append(
            f'<g><text x="0" y="{y + row_h * 0.72}" class="hbar-label">{esc(label)}</text>'
            f'<rect x="{label_w}" y="{y}" width="{bar_w:.1f}" height="{row_h:.1f}" '
            f'rx="3" fill="{color}" opacity="0.92">{_tooltip(tip)}</rect>'
            f'<text x="{label_w + bar_w + 6:.1f}" y="{y + row_h * 0.72}" class="hbar-val">'
            f'{fmt_int(value)}</text></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def svg_vbars(labels: list[str], values: list[int], *,
              color: str = ACCENT, height: int = 260, value_labels: bool = True) -> str:
    """Vertical bar chart."""
    if not values:
        return ""
    W, H = 720, height
    pad_l, pad_b, pad_t = 8, 34, 22
    chart_w, chart_h = W - pad_l, H - pad_b - pad_t
    vmax = max(values) or 1
    n = len(values)
    slot = chart_w / n
    bar_w = slot * 0.62
    parts = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img">']
    for i, (lab, v) in enumerate(zip(labels, values)):
        x = pad_l + i * slot + (slot - bar_w) / 2
        bh = chart_h * (v / vmax)
        y = pad_t + chart_h - bh
        ly = (y - 6) if bh >= 12 else (y - 12)
        parts.append(
            f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
            f'rx="2" fill="{color}" opacity="0.92">{_tooltip(f"{lab}: {v:,}")}</rect>'
            + (f'<text x="{x + bar_w / 2:.1f}" y="{ly:.1f}" class="vbar-val">{v:,}</text>' if value_labels else "")
            + f'<text x="{x + bar_w / 2:.1f}" y="{H - 12}" class="vbar-lab">{esc(lab)}</text></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


def svg_area(points: list[tuple[float, float]], *, height: int = 240,
             color: str = BLUE, xlab0: str = "", xlab1: str = "") -> str:
    """Area chart; points are (x, y) in 0..1 space, x monotone."""
    if not points:
        return ""
    W, H = 720, height
    pad_l, pad_b, pad_t, pad_r = 70, 30, 16, 16
    cw, ch = W - pad_l - pad_r, H - pad_t - pad_b
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ymax = max(ys) or 1
    x0, x1 = min(xs), max(xs)
    span = (x1 - x0) or 1
    coords = []
    for x, y in points:
        px = pad_l + cw * (x - x0) / span
        py = pad_t + ch * (1 - y / ymax)
        coords.append(f"{px:.1f},{py:.1f}")
    poly = " ".join(coords)
    area = (
        f'{poly} {pad_l + cw * (x1 - x0) / span:.1f},{pad_t + ch:.1f} '
        f'{pad_l:.1f},{pad_t + ch:.1f}'
    )
    top = coords[-1]
    parts = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" role="img">',
        f'<polygon points="{area}" fill="{color}" opacity="0.16"/>',
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2"/>',
        f'<circle cx="{top.split(",")[0]}" cy="{top.split(",")[1]}" r="3.5" fill="{color}"/>',
        f'<text x="{pad_l}" y="{H - 8}" class="axis-lab">{esc(xlab0)}</text>',
        f'<text x="{W - pad_r}" y="{H - 8}" class="axis-lab" text-anchor="end">{esc(xlab1)}</text>',
        f'<text x="{pad_l - 8}" y="{pad_t + 4}" class="axis-lab" text-anchor="end">{fmt_int(ymax)}</text>',
        f'<text x="{pad_l - 8}" y="{pad_t + ch}" class="axis-lab" text-anchor="end">0</text>',
        "</svg>",
    ]
    return "".join(parts)


def svg_heatmap(rows: list[str], cols: list[str], data: dict[tuple[str, str], int], *,
                height: int = 320) -> str:
    """Species × background heatmap."""
    if not rows or not cols:
        return ""
    gap = 5
    pad_t = 26
    # Size labels and cells so the longest header fits without overlap.
    pad_l = max(14.0, max(len(r) for r in rows) * 6.4 + 16)
    cell = max(34.0, max(len(c) for c in cols) * 6.4 + 14)
    cw = len(cols) * (cell + gap)
    chh = len(rows) * (cell + gap)
    vmax = max(data.values()) or 1
    W, H = pad_l + cw + 14, pad_t + chh + 22
    parts = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" role="img">',
        f'<text x="{pad_l}" y="{pad_t - 12}" class="hbar-label">species →</text>',
        f'<text x="{pad_l}" y="{pad_t + chh + 16}" class="hbar-label">↑ background</text>',
    ]
    for ci, col in enumerate(cols):
        parts.append(
            f'<text x="{pad_l + ci * (cell + gap) + cell / 2}" y="{pad_t - 10}" '
            f'class="heat-col" text-anchor="middle">{esc(col)}</text>'
        )

    for ri, row in enumerate(rows):
        y = pad_t + ri * (cell + gap)
        parts.append(
            f'<text x="{pad_l - 10}" y="{y + cell / 2 + 4}" class="heat-row" '
            f'text-anchor="end">{esc(row)}</text>'
        )
        for ci, col in enumerate(cols):
            v = data.get((row, col), 0)
            if not v:
                continue
            x = pad_l + ci * (cell + gap)
            t = v / vmax
            r = int(0x1a + (0xe3 - 0x1a) * t)
            g = int(0x21 + (0xb0 - 0x21) * t)
            b = int(0x2f + (0x4b - 0x2f) * t)
            fill = "#0b0e14" if t > 0.55 else "#e8edf3"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" '
                f'fill="rgb({r},{g},{b})">{_tooltip(f"{row} {col}: {v} game(s)")}</rect>'
                f'<text x="{x + cell / 2}" y="{y + cell / 2 + 4}" class="heat-val" '
                f'text-anchor="middle" fill="{fill}">{v}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def svg_donut(value: int, total: int, color: str = WIN, label: str = "") -> str:
    """Small donut for win rate."""
    frac = (value / total) if total else 0.0
    r = 42
    circ = 2 * 3.14159 * r
    dash = circ * frac
    W = H = 120
    return (
        f'<svg class="donut" viewBox="0 0 {W} {H}" role="img">'
        f'<circle cx="{W/2}" cy="{H/2}" r="{r}" fill="none" stroke="{GRID}" stroke-width="10"/>'
        f'<circle cx="{W/2}" cy="{H/2}" r="{r}" fill="none" stroke="{color}" stroke-width="10" '
        f'stroke-dasharray="{dash:.1f} {circ:.1f}" stroke-linecap="round" '
        f'transform="rotate(-90 {W/2} {H/2})"/>'
        f'<text x="{W/2}" y="{H/2 + 5}" class="donut-val" text-anchor="middle">{pct(value, total)}</text>'
        f'<text x="{W/2}" y="{H/2 + 22}" class="donut-lab" text-anchor="middle">{esc(label)}</text>'
        "</svg>"
    )


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------

def _kpi(label: str, value: str, sub: str = "", color: str = ACCENT) -> str:
    return (
        f'<div class="kpi"><div class="kpi-value" style="color:{color}">{value}</div>'
        f'<div class="kpi-label">{esc(label)}</div>'
        f'<div class="kpi-sub">{esc(sub)}</div></div>'
    )


def _section(title: str, anchor: str, sub: str = "") -> str:
    sub_html = f'<div class="section-sub">{esc(sub)}</div>' if sub else ""
    return (
        f'<section id="{anchor}"><div class="section-head"><h2>{esc(title)}</h2>{sub_html}</div>'
    )


def _fin_section() -> str:
    return "</section>"


def render_html(rs: ReportStats, player: str, *, source_url: str = "") -> str:
    g = rs.games
    span = ""
    if rs.first_date and rs.last_date:
        span = f"{rs.first_date.year} – {rs.last_date.year}"

    best = rs.best_game
    deepest = rs.deepest_game
    longest = rs.longest_game

    # ---- KPIs -----------------------------------------------------------
    kpis = "".join([
        _kpi("Games played", fmt_int(rs.total_games), span, ACCENT),
        _kpi("Wins", fmt_int(rs.wins), pct(rs.wins, rs.total_games), WIN),
        _kpi("Best score", fmt_int(best.score if best else None),
             f"{best.title} · XL {best.xl}" if best else "", ACCENT),
        _kpi("Deepest run", f"XL {rs.best_xl}",
             deepest.depth_label if deepest else "", BLUE),
        _kpi("Total turns", fmt_int(rs.total_turns), "across all runs", TEXT),
        _kpi("Time played", fmt_dur_long(rs.total_seconds),
             f"avg {fmt_dur_long(statistics.fmean([x.duration for x in g if x.duration]) or 0)}" if any(x.duration for x in g) else "", TEXT),
        _kpi("Runes found", fmt_int(rs.total_runes),
             f"{len([x for x in g if x.runes])} rune runs", PURPLE),
        _kpi("Gold collected", fmt_int(rs.total_gold), "", "#c9b458"),
    ])

    # ---- Timeline -------------------------------------------------------
    years = rs.years
    year_labels = [str(y.year) for y in years]
    per_year = [y.games for y in years]
    avg_xl = [round(y.avg_xl, 1) for y in years]
    best_score_year = [max(y.scores) if y.scores else 0 for y in years]
    cum = rs.cumulative
    cum_dates = [c[0] for c in cum]
    cum_pts = [(i / max(len(cum) - 1, 1), c[2]) for i, c in enumerate(cum)]

    timeline = "".join([
        _section("Career timeline", "timeline",
                 "One bar per year of play — games, average XP level, and best score."),
        '<div class="grid2">',
        '<div class="card"><h3>Games per year</h3>' + svg_vbars(year_labels, per_year) + "</div>",
        '<div class="card"><h3>Best score per year</h3>' + svg_vbars(year_labels, best_score_year) + "</div>",
        '<div class="card"><h3>Average max XP level per year</h3>'
        + svg_vbars(year_labels, avg_xl) + "</div>",
        '<div class="card"><h3>Cumulative score</h3>'
        + svg_area(cum_pts, xlab0=fmt_date(cum_dates[0]) if cum_dates else "",
                   xlab1=fmt_date(cum_dates[-1]) if cum_dates else "") + "</div>",
        "</div>",
        _fin_section(),
    ])

    # ---- Deaths ---------------------------------------------------------
    killers = rs.killers.most_common(15)
    branches = rs.death_branches.most_common(12)
    xl_hist = sorted(rs.xl_histogram.items())
    hours = [rs.hour_histogram.get(h, 0) for h in range(24)]

    deaths = "".join([
        _section("The Reaper's ledger", "deaths",
                 "What ended the runs, and where. Every death since " + (str(rs.first_date.year) if rs.first_date else "the beginning") + "."),
        '<div class="grid2">',
        '<div class="card"><h3>Top killers</h3>'
        + svg_hbars([(k, v, f"{k}: {v} deaths") for k, v in killers], color=DEATH)
        + "</div>",
        '<div class="card"><h3>Death by branch</h3>'
        + svg_hbars([(k, v, f"{k}: {v} deaths") for k, v in branches], color=PURPLE)
        + "</div>",
        '<div class="card"><h3>Deaths by XP level</h3>'
        + svg_vbars([str(x) for x, _ in xl_hist], [v for _, v in xl_hist], color=BLUE)
        + "</div>",
        '<div class="card"><h3>Deaths by hour of day (UTC)</h3>'
        + svg_vbars([str(h) for h in range(24)], hours, color=MUTED, value_labels=False)
        + "</div>",
        "</div>",
        _fin_section(),
    ])

    # ---- Archetypes -----------------------------------------------------
    species = rs.species.most_common(10)
    bgs = rs.backgrounds.most_common(10)
    gods = rs.gods.most_common(12)
    top_species = [s for s, _ in species][:8]
    top_bgs = [b for b, _ in bgs][:8]
    heat = {(s, b): v for (s, b), v in rs.species_bg.items()
            if s in top_species and b in top_bgs}

    god_rows = []
    for name, cnt in gods:
        xs = rs.god_xl.get(name, [])
        god_rows.append((name, cnt, f"{name}: {cnt} game(s), avg XL {statistics.fmean(xs):.1f}"))

    archetypes = "".join([
        _section("Archetypes", "archetypes", "Species, backgrounds and gods across the career."),
        '<div class="grid2">',
        '<div class="card"><h3>Species played</h3>'
        + svg_hbars(species, color=BLUE) + "</div>",
        '<div class="card"><h3>Backgrounds</h3>'
        + svg_hbars(bgs, color=ACCENT) + "</div>",
        '<div class="card"><h3>Species × background</h3>'
        + svg_heatmap(top_species, top_bgs, heat) + "</div>",
        '<div class="card"><h3>Gods worshipped</h3>'
        + svg_hbars(god_rows, color=PURPLE) + "</div>",
        "</div>",
        _fin_section(),
    ])

    # ---- Post-mortem ----------------------------------------------------
    sev_color = {"high": DEATH, "medium": ACCENT, "low": MUTED}
    rec = [(rs.mistake_meta.get(r, (r, "low"))[0], c,
            rs.mistake_meta.get(r, (r, "low"))[1])
           for r, c in rs.mistake_counts.most_common(12)]
    rec_color = DEATH if rec and all(s == "high" for _, _, s in rec) else ACCENT
    offenders_html = []
    for og in rs.offenders:
        lis = "".join(
            f'<li class="sev-{mk.severity}"><b>{esc(mk.label)}</b> — '
            f'{esc(mk.evidence)}</li>' for mk in og.mistakes
        )
        offenders_html.append(
            f'<div class="offender"><div class="offender-head">'
            f'{fmt_date(og.game_date)} · {esc(og.title)} · XL {og.xl} · '
            f'<span class="sev-high">{esc(og.killer or og.cause_short or "—")}</span>'
            f'</div><ul class="mistake-list">{lis}</ul></div>'
        )
    offenders_block = ('<div class="card"><h3>Worst offenders</h3>'
                       + "".join(offenders_html) + "</div>")
    pm_chips = "".join([
        _kpi("Mistakes found", fmt_int(rs.mistakes_total), "across all runs", ACCENT),
        _kpi("Games with mistakes", fmt_int(rs.games_with_mistakes),
             pct(rs.games_with_mistakes, rs.total_games), TEXT),
        _kpi("Avg mistakes / game",
             f"{rs.mistakes_total / rs.total_games:.1f}" if rs.total_games else "—",
             "per death", TEXT),
        _kpi("Games with critical mistakes", fmt_int(rs.games_high),
             "≥1 high-severity", DEATH),
    ])
    postmortem = "".join([
        _section("Post-mortem", "postmortem",
                 "What the morgues say went wrong — evidence from inventory "
                 "at death, damage math, resists and the turn notes."),
        '<div class="kpis">' + pm_chips + "</div>",
        '<div class="grid2">',
        '<div class="card"><h3>Top recurring mistakes</h3>'
        + svg_hbars([(label, cnt, f"{label}: {cnt} game(s)") for label, cnt, _ in rec],
                    color=rec_color, label_w=235)
        + "</div>",
        offenders_block,
        "</div>",
        _fin_section(),
    ])

    # ---- Every run ------------------------------------------------------
    rows_html = []
    for i, game in enumerate(reversed(g), start=1):
        mis = game.mistakes
        mis_title = " · ".join(f"{mk.label}: {mk.evidence}" for mk in mis)
        rows_html.append(
            "<tr>"
            f'<td data-sort="{i}" class="num">{i}</td>'
            f'<td data-sort="{game.game_date.strftime("%Y%m%d%H%M%S") if game.game_date else 0}">{fmt_date(game.game_date)}</td>'
            f'<td>{esc(game.title or "?")}</td>'
            f'<td>{esc(game.species or "—")}</td>'
            f'<td>{esc(game.background or "—")}</td>'
            f'<td class="num" data-sort="{game.xl or 0}">{game.xl or "—"}</td>'
            f'<td>{esc(game.god or "—")}</td>'
            f'<td class="num" data-sort="{game.runes}">{game.runes or "—"}</td>'
            f'<td class="num" data-sort="{game.turns or 0}">{fmt_int(game.turns)}</td>'
            f'<td class="num" data-sort="{game.duration or 0}">{fmt_dur(game.duration, short=True)}</td>'
            f'<td class="num" data-sort="{game.score or 0}">{fmt_int(game.score)}</td>'
            f'<td>{esc(game.depth_label or "—")}</td>'
            f'<td class="cause" data-sort="{esc(game.killer or game.cause_short or "")}">{esc(game.killer or game.cause_short or "—")}</td>'
            f'<td class="num">{game.damage if game.damage is not None else "—"}</td>'
            f'<td class="num" data-sort="{len(game.uniques_killed)}">{len(game.uniques_killed) or "—"}</td>'
            + (f'<td class="num" data-sort="{len(mis)}" title="{esc(mis_title)}" '
               f'style="color:{DEATH if any(m.severity == "high" for m in mis) else ACCENT}">'
               f'{"⚠ " + str(len(mis)) if mis else "—"}</td>')
            + "</tr>"
        )
    table = "".join([
        _section("Every run", "runs", f"All {rs.total_games} recorded games, newest first. Click a column to sort, type to filter."),
        '<div class="card">',
        '<input id="run-filter" type="search" placeholder="Filter runs… (try \'Trog\', \'Minotaur\', \'giant\')" autocomplete="off">',
        '<div class="table-wrap"><table id="runs-table">',
        "<thead><tr>"
        "<th data-k=\"num\">#</th><th data-k=\"date\">Date</th><th data-k=\"text\">Title</th>"
        "<th data-k=\"text\">Species</th><th data-k=\"text\">Bg</th><th data-k=\"num\">XL</th>"
        "<th data-k=\"text\">God</th><th data-k=\"num\">Runes</th><th data-k=\"num\">Turns</th>"
        "<th data-k=\"num\">Time</th><th data-k=\"num\">Score</th><th data-k=\"text\">Reached</th>"
        "<th data-k=\"text\">Death</th><th data-k=\"num\">Dmg</th><th data-k=\"num\">Uniques</th>"
        '<th data-k="num" title="Mistakes found">⚠</th>'
        "</tr></thead><tbody>",
        "".join(rows_html),
        "</tbody></table></div></div>",
        _fin_section(),
    ])

    # ---- Milestones -----------------------------------------------------
    uniques = rs.uniques.most_common(15)
    first_rune = next((x for x in g if x.runes), None)
    deep10 = [x for x in g if x.xl and x.xl >= 10]
    deep15 = [x for x in g if x.xl and x.xl >= 15]
    first_10 = deep10[0] if deep10 else None
    first_15 = deep15[0] if deep15 else None
    most_uniques = max(g, key=lambda x: len(x.uniques_killed)) if g else None

    milestone_cards = []
    def mcard(label: str, value: str, sub: str = "", color: str = ACCENT) -> str:
        milestone_cards.append(
            f'<div class="kpi"><div class="kpi-value" style="color:{color}">{esc(value)}</div>'
            f'<div class="kpi-label">{esc(label)}</div><div class="kpi-sub">{esc(sub)}</div></div>'
        )
    mcard("First game", fmt_date(rs.first_date), g[0].title if g else "")
    mcard("First rune", fmt_date(first_rune.game_date) if first_rune else "none yet",
          first_rune.depth_label if first_rune else "", PURPLE)
    mcard("First XL ≥ 10", fmt_date(first_10.game_date) if first_10 else "—",
          first_10.title if first_10 else "", BLUE)
    mcard("First XL ≥ 15", fmt_date(first_15.game_date) if first_15 else "—",
          first_15.title if first_15 else "", BLUE)
    mcard("Longest game", fmt_dur(longest.duration, short=True) if longest else "—",
          f"{longest.title} · {fmt_date(longest.game_date)}" if longest else "", TEXT)
    mcard("Most uniques slain", str(len(most_uniques.uniques_killed)) if most_uniques else "—",
          most_uniques.title if most_uniques else "", WIN)
    mcard("Unique kills (total)", fmt_int(sum(rs.uniques.values())),
          f"{len(rs.uniques)} distinct", WIN)
    mcard("Career average XL", f"{statistics.fmean([x.xl or 0 for x in g]):.1f}" if g else "—",
          f"median {statistics.median([x.xl or 0 for x in g])}" if g else "", TEXT)

    hiatus_days, hiatus_span = 0, ""
    prev_d = None
    for game in g:
        if prev_d and game.game_date:
            gap = (game.game_date - prev_d).days
            if gap > hiatus_days:
                hiatus_days = gap
                hiatus_span = f"{fmt_date(prev_d)} → {fmt_date(game.game_date)}"
        prev_d = game.game_date or prev_d
    if hiatus_days:
        mcard("Longest hiatus", _fmt_days(hiatus_days), hiatus_span, MUTED)

    milestones = "".join([
        _section("Milestones", "milestones", "Firsts and records along the way."),
        '<div class="kpis">' + "".join(milestone_cards) + "</div>",
        '<div class="grid2">',
        '<div class="card"><h3>Most-slain uniques</h3>'
        + svg_hbars(uniques, color=WIN) + "</div>",
        '<div class="card"><h3>Worst runs</h3>'
        + svg_hbars([(f"{fmt_date(x.game_date)} · {x.title}", x.score or 0,
                      f"{x.title}, XL {x.xl}, {x.killer or x.cause_short}") for x in g[:4]],
                    color=MUTED) + "</div>",
        "</div>",
        _fin_section(),
    ])

    # ---- Page -----------------------------------------------------------
    nav = "".join(
        f'<a href="#{a}">{esc(t)}</a>'
        for a, t in [("timeline", "Timeline"), ("deaths", "Deaths"),
                     ("postmortem", "Post-mortem"), ("archetypes", "Archetypes"),
                     ("runs", "Every run"), ("milestones", "Milestones")]
    )
    source = (f'<a href="{esc(source_url)}">morgue files</a>' if source_url
              else "morgue files")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(player)} — DCSS Morgue Report</title>
<style>
:root {{
  --bg:#0b0e14; --panel:#12161f; --panel2:#161b26; --border:#232a38;
  --text:#c9d1d9; --muted:#7d8590; --accent:{ACCENT}; --death:{DEATH};
  --win:{WIN}; --blue:{BLUE}; --purple:{PURPLE};
}}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html {{ scroll-behavior:smooth; }}
body {{ background:var(--bg); color:var(--text);
  font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.num, .kpi-value, .hbar-val, .vbar-val, .vbar-lab, .axis-lab, .donut-val, td.num {{
  font-variant-numeric:tabular-nums; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
a {{ color:var(--accent); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}

.hero {{ background:linear-gradient(180deg,#10151f 0%,#0b0e14 100%);
  border-bottom:1px solid var(--border); padding:56px 32px 40px; }}
.hero-top {{ max-width:1180px; margin:0 auto; }}
.hero-title {{ font-size:56px; font-weight:800; letter-spacing:-1px;
  background:linear-gradient(90deg,#f2c96b,var(--accent) 55%,#b98a2f);
  -webkit-background-clip:text; background-clip:text; color:transparent; }}
.hero-sub {{ font-size:18px; color:var(--muted); margin-top:2px; }}
.hero-meta {{ font-size:14px; color:var(--muted); margin-top:8px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.nav {{ max-width:1180px; margin:24px auto 0; display:flex; gap:22px;
  font-size:14px; color:var(--muted); }}
.nav a {{ color:var(--muted); }}

main {{ max-width:1180px; margin:0 auto; padding:36px 32px 80px; }}
section {{ margin-top:56px; scroll-margin-top:24px; }}
.section-head {{ margin-bottom:18px; }}
.section-head h2 {{ font-size:26px; font-weight:700; letter-spacing:-0.3px; }}
.section-sub {{ color:var(--muted); font-size:14px; margin-top:4px; }}

.kpis {{ display:grid; grid-template-columns:repeat(4,1fr);
  gap:14px; max-width:1180px; margin:28px auto 0; }}
@media (max-width:1100px) {{ .kpis {{ grid-template-columns:repeat(2,1fr); }} }}
@media (max-width:560px) {{ .kpis {{ grid-template-columns:1fr; }} }}
.kpi {{ background:var(--panel); border:1px solid var(--border); border-radius:12px;
  padding:16px 18px; }}
.kpi-value {{ font-size:26px; font-weight:700; letter-spacing:-0.5px; }}
.kpi-label {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em;
  color:var(--muted); margin-top:4px; }}
.kpi-sub {{ font-size:12px; color:var(--muted); margin-top:2px; }}

.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
@media (max-width:900px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
.card {{ background:var(--panel); border:1px solid var(--border); border-radius:14px;
  padding:20px 22px; }}
.card h3 {{ font-size:15px; font-weight:600; color:#e6edf3; margin-bottom:12px; }}
.chart {{ width:100%; height:auto; display:block; }}
.hbar-label {{ font-size:12.5px; fill:var(--text); }}
.hbar-val {{ font-size:12.5px; fill:var(--muted); }}
.vbar-val {{ font-size:11px; fill:var(--muted); text-anchor:middle; }}
.vbar-lab {{ font-size:10.5px; fill:var(--muted); text-anchor:middle; }}
.axis-lab {{ font-size:11px; fill:var(--muted); }}
.heat-col, .heat-row {{ font-size:12px; fill:var(--text); }}
.heat-val {{ font-size:11px; font-weight:600; }}
.donut {{ width:150px; height:auto; display:block; margin:0 auto; }}
.donut-val {{ font-size:17px; fill:var(--text); font-weight:700; }}
.donut-lab {{ font-size:10px; fill:var(--muted); text-transform:uppercase;
  letter-spacing:.06em; }}

#run-filter {{ width:100%; background:var(--panel2); color:var(--text);
  border:1px solid var(--border); border-radius:10px; padding:10px 14px;
  font-size:14px; margin-bottom:14px; outline:none; }}
#run-filter:focus {{ border-color:var(--accent); }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
thead th {{ text-align:left; padding:8px 10px; color:var(--muted); font-weight:600;
  border-bottom:1px solid var(--border); cursor:pointer; white-space:nowrap;
  user-select:none; position:sticky; top:0; background:var(--panel); }}
thead th:hover {{ color:var(--text); }}
thead th.sorted-asc::after {{ content:" ▲"; font-size:9px; }}
thead th.sorted-desc::after {{ content:" ▼"; font-size:9px; }}
tbody td {{ padding:7px 10px; border-bottom:1px solid #1a2030; white-space:nowrap; }}
tbody tr:hover {{ background:var(--panel2); }}
td.cause {{ color:#e2a6ad; }}
tbody tr.row-hidden {{ display:none; }}
.offender {{ border:1px solid var(--border); border-radius:10px; padding:12px 14px;
  margin-bottom:10px; }}
.offender-head {{ font-size:13px; color:var(--muted); margin-bottom:6px; }}
.offender-head b {{ color:var(--text); }}
.mistake-list {{ list-style:none; margin:0; padding:0; }}
.mistake-list li {{ font-size:13px; padding:3px 0; line-height:1.45; }}
.mistake-list li b {{ font-weight:600; }}
.sev-high b {{ color:var(--death); }}
.sev-medium b {{ color:var(--accent); }}
.sev-low b {{ color:var(--text); }}

footer {{ border-top:1px solid var(--border); color:var(--muted); font-size:13px;
  padding:28px 32px 48px; text-align:center; }}
footer a {{ color:var(--muted); }}
</style>
</head>
<body>
<header class="hero">
  <div class="hero-top">
    <div class="hero-title">{esc(player)}</div>
    <div class="hero-sub">Dungeon Crawl Stone Soup — career morgue report</div>
    <div class="hero-meta">{esc(span)} · {rs.total_games} games · {rs.wins} win(s) ·
      {fmt_int(rs.total_turns)} turns · {fmt_dur_long(rs.total_seconds)} · generated {datetime.utcnow().strftime("%b %d, %Y")}</div>
    <nav class="nav">{nav}</nav>
  </div>
</header>
<div class="kpis">{kpis}</div>
<main>
{timeline}
{deaths}
{postmortem}
{archetypes}
{table}
{milestones}
</main>
<footer>
  Generated from {source} · parsed {len(rs.games)} of {rs.total_games} morgue files
  {f"({len(rs.unparsed)} unparsed)" if rs.unparsed else ""} ·
  versions: {", ".join(k for k, _ in rs.version_counts.most_common(4))}
</footer>
<script>
(function () {{
  const table = document.getElementById('runs-table');
  const filter = document.getElementById('run-filter');
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  let sortKey = null, sortDir = 1;

  function applyFilter() {{
    const q = (filter.value || '').toLowerCase();
    for (const r of rows) r.classList.toggle('row-hidden', q && !r.textContent.toLowerCase().includes(q));
  }}
  filter.addEventListener('input', applyFilter);

  function cmpNum(a, b) {{ return (parseFloat(a) || -1e18) - (parseFloat(b) || -1e18); }}
  function cmpText(a, b) {{ return a.localeCompare(b, undefined, {{numeric:true}}); }}

  table.querySelectorAll('th').forEach((th, idx) => {{
    th.addEventListener('click', () => {{
      const k = th.dataset.k;
      table.querySelectorAll('th').forEach(h => h.classList.remove('sorted-asc', 'sorted-desc'));
      if (sortKey === idx) sortDir *= -1; else {{ sortKey = idx; sortDir = 1; }}
      th.classList.add(sortDir === 1 ? 'sorted-asc' : 'sorted-desc');
      const cmp = k === 'num' ? cmpNum : cmpText;
      rows.sort((a, b) => sortDir * cmp(a.cells[idx].dataset.sort, b.cells[idx].dataset.sort));
      for (const r of rows) tbody.appendChild(r);
      applyFilter();
    }});
  }});
}})();
</script>
</body>
</html>
"""
