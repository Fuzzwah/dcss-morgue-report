"""Render a self-contained HTML report with inline SVG charts."""

from __future__ import annotations

import html
import json
import statistics
from collections import Counter
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
    return " ".join(parts) or "<1m"


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


_TITLE_SMALL = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}


def title_case(s: str) -> str:
    """'realm of zot' -> 'Realm of Zot'."""
    words = s.split()
    return " ".join(
        w.capitalize() if i == 0 or w.lower() not in _TITLE_SMALL else w.lower()
        for i, w in enumerate(words)
    ) or s


# --------------------------------------------------------------------------
# Tile-art rows
# --------------------------------------------------------------------------

#: Shown where a killer has no tile art anywhere in the crawl repo (gods
#: without altars, effects like "nerve-wracking pain", long-removed monsters).
SKULL_SVG = (
    '<svg viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M12 3.2a7 7 0 0 0-7 7c0 2.7 1.5 5 3.7 6.3l.5 3.3a1 1 0 0 0 1 .8'
    'h3.6a1 1 0 0 0 1-.8l.5-3.3A7.4 7.4 0 0 0 19 10.2a7 7 0 0 0-7-7z"'
    ' fill="none" stroke="currentColor" stroke-width="1.7"/>'
    '<rect x="9.1" y="8.4" width="2" height="2.6" rx="0.5" fill="currentColor"/>'
    '<rect x="12.9" y="8.4" width="2" height="2.6" rx="0.5" fill="currentColor"/>'
    '<path d="M9.6 15.6h4.8M11 13.6v2M13 13.6v2" stroke="currentColor"'
    ' stroke-width="1.2" fill="none"/></svg>'
)


def _tile_img(name: str, images: dict[str, str], cls: str = "tile", *,
              fallback: bool = False) -> str:
    """Token <img> for `name` when art exists; '' otherwise (layout holds).

    Images are embedded once in a JSON dictionary and referenced by token —
    the base64 payload must not repeat once per table row.  With `fallback`,
    artless death causes get the no-art glyph instead of nothing.
    """
    if name in images:
        return f'<img class="{cls}" data-img="{esc(name)}" alt="">'
    if fallback:
        small = " tile-sm" if cls == "tile-sm" else ""
        return (f'<span class="tile-unknown{small}" '
                f'title="no tile art in the crawl repo">{SKULL_SVG}</span>')
    return ""


def _char_sprite(game, images: dict[str, str], *, sm: bool = False) -> str:
    """Layered portrait: species body + the gear worn at death (approx).

    Parts share one aligned 32×32 canvas; each present layer stacks.  Without
    art the row keeps its space via the title-cell flex layout.
    """
    from . import tiles
    rels = tiles.gear_rels(game)
    keys = [game.species or ""] + ["part:" + r for r in rels]
    keys = [k for k in keys if k in images]
    if not keys:
        return ""
    imgs = "".join(f'<img data-img="{esc(k)}" alt="">' for k in keys)
    return f'<span class="{"charstack sm" if sm else "charstack"}">{imgs}</span>'


def _tile_rows(items: list[tuple], images: dict[str, str], *, color: str,
               limit: int = 12, fallback: bool = False,
               label_w: int = 170) -> str:
    """Name rows with optional tile art and an inline bar.

    items: (label, value) or (label, value, tooltip).  Rows without art keep
    their space so the column aligns.  This is the single row style for every
    name/count list in the report, so all lists share one typography.
    """
    # items: (label, value) | (label, value, tooltip) | (label, value,
    # tooltip, icon_key) — icon_key overrides the label for art lookup.
    items = [it if len(it) > 3 else (it[0], it[1], it[2] if len(it) > 2 else None,
                                     it[0]) for it in items[:limit]]
    if not items:
        return ""
    vmax = max(v for _, v, *_ in items) or 1
    lab = (f'<span class="tlab" style="flex-basis:{label_w}px;width:{label_w}px">'
           if label_w != 170 else '<span class="tlab">')
    parts = ['<div class="trows">']
    for label, value, tip, icon in items:
        tip = tip or f"{label}: {value:,}"
        lead = _tile_img(icon, images, fallback=fallback)
        if not lead:
            # keep the icon column so labels align across every list card
            lead = '<span class="tile-gap"></span>'
        # sqrt scaling keeps small-but-real counts visible next to outliers
        frac = (value / vmax) ** 0.5 * 100
        parts.append(
            '<div class="trow" title="' + esc(tip) + '">'
            + lead
            + lab + esc(label) + "</span>"
            + f'<div class="track"><div class="fill" style="width:{frac:.0f}%;'
            + f'background:{color}"></div></div>'
            + f'<span class="tval">{fmt_int(value)}</span></div>'
        )
    parts.append("</div>")
    return "".join(parts)


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
        f'<text x="4" y="{pad_t - 10}" class="hbar-label">species →</text>',
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


def render_html(rs: ReportStats, player: str, *, source_url: str = "",
                images: dict[str, str] | None = None,
                unique_deaths: dict[str, int] | None = None) -> str:
    """Render the report.

    images:        display name -> data-URI of its tile art (monsters, uniques
                   and species, as resolved by dcssreport.tiles).
    unique_deaths: killer name -> death count for unique monsters that killed
                   the player; shown as "Deaths vs uniques".
    """
    images = images or {}
    unique_deaths = unique_deaths or {}
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

    # ---- Monster / branch / death cards --------------------------------
    killers = rs.killers.most_common(15)
    branches = rs.death_branches.most_common(12)
    xl_hist = sorted(rs.xl_histogram.items())
    hours = [rs.hour_histogram.get(h, 0) for h in range(24)]

    killer_rows = [(k, v, f"{k}: {v} deaths") for k, v in killers]
    killer_card = ('<div class="card"><h3>Top killers</h3>'
                   + (_tile_rows(killer_rows, images, color=DEATH, fallback=True)
                      if any(images.get(k) for k, _ in killers)
                      else svg_hbars(killer_rows, color=DEATH))
                   + "</div>")

    branch_rows = [(title_case(k), v, f"{k}: {v} deaths", k) for k, v in branches]
    branch_card = ('<div class="card"><h3>Branch deaths</h3>'
                   + (_tile_rows(branch_rows, images, color=PURPLE)
                      if any(images.get(k) for k, _ in branches)
                      else svg_hbars(branch_rows, color=PURPLE))
                   + "</div>")

    # Branch visits: runs that entered each branch (death implies a visit).
    branch_visits: Counter = Counter()
    for gm in g:
        seen = set(gm.branches_visited)
        seen.update(gm.extra_branches)
        seen.update(k for k in gm.entered_turns)
        if gm.death_branch:
            seen.add(gm.death_branch)
        for b in seen:
            if b:
                branch_visits[b] += 1
    visit_rows = [(title_case(k), v, f"{k}: entered in {v} run(s)", k) for k, v in
                  branch_visits.most_common(12)]
    visit_card = ('<div class="card"><h3>Branch visits</h3>'
                  + (_tile_rows(visit_rows, images, color=BLUE)
                     if any(images.get(k) for k, *_ in visit_rows)
                     else svg_hbars(visit_rows, color=BLUE))
                  + "</div>")

    # ---- Deaths vs unique monsters --------------------------------------
    ud_total = sum(unique_deaths.values())
    ud = sorted(unique_deaths.items(), key=lambda kv: (-kv[1], kv[0]))
    death_runs = max(rs.total_games - rs.wins, 1)
    deadliest = ud[0] if ud else None

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

    species_rows = [(s, c, f"{s}: {c} game(s)") for s, c in species]
    species_card = ('<div class="card"><h3>Species played</h3>'
                    + (_tile_rows(species_rows, images, color=BLUE)
                       if any(images.get(s) for s, _ in species)
                       else svg_hbars(species_rows, color=BLUE))
                    + "</div>")

    bgs_rows = [(b, c, f"{b}: {c} game(s)") for b, c in bgs]
    bgs_card = ('<div class="card"><h3>Backgrounds</h3>'
                + _tile_rows(bgs_rows, images, color=ACCENT) + "</div>")
    gods_card = ('<div class="card"><h3>Gods worshipped</h3>'
                 + _tile_rows(god_rows, images, color=PURPLE) + "</div>")

    archetypes = "".join([
        _section("Archetypes", "archetypes", "Species, backgrounds and gods across the career."),
        '<div class="grid2">',
        species_card,
        bgs_card,
        '<div class="card"><h3>Species × background</h3>'
        + svg_heatmap(top_species, top_bgs, heat) + "</div>",
        gods_card,
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
        + _tile_rows([(label, cnt, f"{label}: {cnt} game(s)")
                      for label, cnt, _ in rec],
                     images, color=rec_color, label_w=235)
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
        killer_name = (game.killer or game.cause_short or "").strip()
        rows_html.append(
            "<tr>"
            f'<td data-sort="{i}" class="num">{i}</td>'
            f'<td data-sort="{game.game_date.strftime("%Y%m%d%H%M%S") if game.game_date else 0}">{fmt_date(game.game_date)}</td>'
            f'<td><span class="titlecell">{_char_sprite(game, images, sm=True)}{esc(game.title or "?")}</span></td>'
            f'<td>{esc(game.species or "—")}</td>'
            f'<td>{esc(game.background or "—")}</td>'
            f'<td class="num" data-sort="{game.xl or 0}">{game.xl or "—"}</td>'
            f'<td>{esc(game.god or "—")}</td>'
            f'<td class="num" data-sort="{game.runes}">{game.runes or "—"}</td>'
            f'<td class="num" data-sort="{game.turns or 0}">{fmt_int(game.turns)}</td>'
            f'<td class="num" data-sort="{game.duration or 0}">{fmt_dur(game.duration, short=True)}</td>'
            f'<td class="num" data-sort="{game.score or 0}">{fmt_int(game.score)}</td>'
            f'<td>{esc(game.depth_label or "—")}</td>'
            f'<td class="cause" data-sort="{esc(killer_name)}">'
            f'<span class="titlecell">{_tile_img(killer_name, images, "tile-sm", fallback=True)}{esc(killer_name or "—")}</span></td>'
            f'<td class="num">{fmt_int(game.damage) if game.damage is not None else "—"}</td>'
            f'<td class="num" data-sort="{len(game.uniques_killed)}">'
            f'{(fmt_int(len(game.uniques_killed)) if game.uniques_killed else "—")}</td>'
            + (f'<td class="num" data-sort="{len(mis)}" title="{esc(mis_title)}" '
               f'style="color:{DEATH if any(m.severity == "high" for m in mis) else ACCENT}">'
               f'{"⚠ " + str(len(mis)) if mis else "—"}</td>')
            + "</tr>"
        )
    table = "".join([
        _section("Every run", "runs", f"All {fmt_int(rs.total_games)} recorded games, newest first. Click a column to sort, type to filter."),
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
    mcard("Most uniques slain", fmt_int(len(most_uniques.uniques_killed)) if most_uniques else "—",
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

    uniq_rows = [(u, c, f"{u}: slain {c} time(s)") for u, c in uniques]
    uniques_card = ('<div class="card"><h3>Most-slain uniques</h3>'
                    + (_tile_rows(uniq_rows, images, color=WIN)
                       if any(images.get(u) for u, _ in uniques)
                       else svg_hbars(uniq_rows, color=WIN))
                    + "</div>")

    # ---- Section assembly ----------------------------------------------
    milestones = "".join([
        _section("Milestones", "milestones", "Firsts and records along the way."),
        '<div class="records">' + "".join(milestone_cards) + "</div>",
        _fin_section(),
    ])

    # Best runs = highest scores (rs.games is date-sorted, so pick explicitly).
    best_list = sorted((x for x in g if x.score is not None),
                       key=lambda x: x.score, reverse=True)[:8]
    best_rows = []
    for x in best_list:
        best_rows.append(
            "<tr>"
            f'<td>{fmt_date(x.game_date)}</td>'
            f'<td><span class="titlecell">{_char_sprite(x, images, sm=True)}'
            f'{esc(x.title or "?")}</span></td>'
            f'<td>{esc(x.species or "—")}</td>'
            f'<td>{esc(x.background or "—")}</td>'
            f'<td>{esc(x.god or "—")}</td>'
            f'<td class="num">{x.xl or "—"}</td>'
            f'<td class="num">{x.runes or "—"}</td>'
            f'<td class="num" data-sort="{x.score or 0}">'
            f'<b style="color:{WIN}">{fmt_int(x.score)}</b></td>'
            f'<td>{esc(x.depth_label or "—")}</td>'
            f'<td class="num">{fmt_dur(x.duration, short=True)}</td>'
            "</tr>"
        )
    best_section = "".join([
        _section("Best runs", "best", "The eight highest-scoring runs."),
        '<div class="card"><h3>Best runs</h3>',
        '<div class="table-wrap"><table>',
        "<thead><tr>"
        "<th>Date</th><th>Character</th><th>Species</th><th>Bg</th>"
        "<th>God</th><th>XL</th><th>Runes</th><th>Score</th>"
        "<th>Reached</th><th>Time</th>"
        "</tr></thead><tbody>",
        "".join(best_rows),
        "</tbody></table></div></div>",
        _fin_section(),
    ])

    monsters_extra = ""
    if images or unique_deaths:
        if ud:
            uni_deaths_card = ('<div class="card"><h3>Deaths vs uniques</h3>'
                               + _tile_rows(
                                   [(k, v, f"{k}: killed you {v} time(s)")
                                    for k, v in ud],
                                   images, color=DEATH)
                               + "</div>")
        else:
            uni_deaths_card = (
                '<div class="card"><h3>Deaths vs uniques</h3>'
                '<div class="note">No unique monster has ever killed you.</div>'
                "</div>")
        monsters_extra = "".join([
            '<div class="grid2">', uni_deaths_card,
            '<div class="card"><h3>Uniques vs you</h3>'
            f'<div class="big" style="color:{DEATH}">{fmt_int(ud_total)}</div>'
            f'<div class="note">{pct(ud_total, death_runs)} of all runs were ended '
            f'by a named unique'
            + (f' — deadliest: <b>{esc(deadliest[0])}</b> ({deadliest[1]})'
               if deadliest else "") + ".</div>",
            "</div>",
            "</div>",
        ])

    monsters = "".join([
        _section("Monsters", "monsters",
                 "Monster by monster: who killed you and which uniques you slew."),
        '<div class="grid2">',
        killer_card,
        uniques_card,
        "</div>",
        monsters_extra,
        _fin_section(),
    ])

    branches_section = "".join([
        _section("Branches", "branches",
                 "How often each branch was entered, and how many runs ended there."),
        '<div class="grid2">',
        visit_card,
        branch_card,
        "</div>",
        _fin_section(),
    ])

    death_charts = "".join([
        _section("Deaths", "deaths",
                 "At what XP level and what hour of day the runs ended."),
        '<div class="grid2">',
        '<div class="card"><h3>Deaths by XP level</h3>'
        + svg_vbars([str(x) for x, _ in xl_hist], [v for _, v in xl_hist], color=BLUE)
        + "</div>",
        '<div class="card"><h3>Deaths by hour of day (UTC)</h3>'
        + svg_vbars([str(h) for h in range(24)], hours, color=MUTED, value_labels=False)
        + "</div>",
        "</div>",
        _fin_section(),
    ])

    # ---- Page -----------------------------------------------------------
    nav = "".join(
        f'<a href="#{a}">{esc(t)}</a>'
        for a, t in [("milestones", "Milestones"), ("timeline", "Timeline"),
                     ("archetypes", "Characters"), ("best", "Best runs"),
                     ("monsters", "Monsters"), ("branches", "Branches"),
                     ("deaths", "Deaths"), ("postmortem", "Post-mortem"),
                     ("runs", "Every run")]
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
.nav {{ max-width:1180px; margin:24px auto 0; display:flex; flex-wrap:wrap; gap:14px 22px;
  font-size:14px; color:var(--muted); }}
.nav a {{ color:var(--muted); }}

main {{ max-width:1180px; margin:0 auto; padding:24px 32px 80px; }}
section {{ margin-top:56px; scroll-margin-top:24px; }}
main > section:first-child {{ margin-top:0; }}
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
.grid2 .card {{ display:flex; flex-direction:column; }}
.grid2 .card > .trows {{ flex:1 0 auto; justify-content:space-evenly; }}
.records {{ display:flex; flex-wrap:wrap; gap:14px; justify-content:center; }}
.records .kpi {{ flex:1 1 300px; }}
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

.tile {{ width:32px; height:32px; flex:0 0 auto; border-radius:6px;
  image-rendering:pixelated; image-rendering:crisp-edges; }}
.tile-sm {{ width:24px; height:24px; flex:0 0 auto; border-radius:4px;
  image-rendering:pixelated; image-rendering:crisp-edges; }}
.titlecell {{ display:inline-flex; align-items:center; gap:9px; }}
.charstack {{ position:relative; display:inline-block; width:32px; height:32px;
  flex:0 0 auto; }}
.charstack img {{ position:absolute; inset:0; width:32px; height:32px;
  image-rendering:pixelated; image-rendering:crisp-edges; }}
.charstack.sm {{ width:24px; height:24px; }}
.charstack.sm img {{ width:24px; height:24px; }}
.trows {{ display:flex; flex-direction:column; }}
.trow {{ display:flex; align-items:center; gap:10px; padding:3px 0; }}
.tlab {{ flex:0 0 170px; width:170px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; font-size:13px; }}
.track {{ flex:1 1 auto; height:8px; background:var(--panel2); border-radius:99px;
  overflow:hidden; min-width:40px; }}
.fill {{ height:100%; border-radius:99px; }}
.tval {{ flex:0 0 auto; min-width:44px; text-align:right; font-size:12px;
  color:var(--muted); }}
.big {{ font-size:42px; font-weight:800; letter-spacing:-1px; line-height:1.05; }}
.note {{ color:var(--muted); font-size:13px; }}
.tile-unknown {{ display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; flex:0 0 auto; color:var(--muted); opacity:0.55; }}
.tile-gap {{ width:32px; flex:0 0 auto; }}
.tile-unknown svg {{ width:22px; height:22px; display:block; }}
.tile-unknown.tile-sm {{ width:24px; height:24px; }}
.tile-unknown.tile-sm svg {{ width:16px; height:16px; }}

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
    <div class="hero-meta">{esc(span)} · {fmt_int(rs.total_games)} games · {fmt_int(rs.wins)} win(s) ·
      {fmt_int(rs.total_turns)} turns · {fmt_dur_long(rs.total_seconds)} · generated {datetime.utcnow().strftime("%b %d, %Y")}</div>
    <nav class="nav">{nav}</nav>
  </div>
</header>
<div class="kpis">{kpis}</div>
<main>
{milestones}
{timeline}
{archetypes}
{best_section}
{monsters}
{branches_section}
{death_charts}
{postmortem}
{table}
</main>
<footer>
  Generated from {source} · parsed {fmt_int(len(rs.games))} of {fmt_int(rs.total_games)} morgue files
  {f"({fmt_int(len(rs.unparsed))} unparsed)" if rs.unparsed else ""} ·
  versions: {", ".join(k for k, _ in rs.version_counts.most_common(4))}
</footer>
<script>
(function () {{
  const IMGS = {json.dumps(images, ensure_ascii=False)};
  document.querySelectorAll('img[data-img]').forEach(function (img) {{
    const k = img.getAttribute('data-img');
    if (Object.prototype.hasOwnProperty.call(IMGS, k)) img.src = IMGS[k];
  }});
}})();
</script>
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
