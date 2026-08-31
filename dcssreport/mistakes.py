"""Post-mortem analysis: turn a parsed game into a list of mistakes.

Each rule is conservative — it only fires on what the morgue actually proves
(inventory at death, damage math, resists, action chart, notes), and every
finding carries the evidence behind it. Advice is short and actionable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import Game, normalize_branch

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_ARTICLE_RE = re.compile(r"^(a|an|the|some)\s+")
_PLURAL_RE = re.compile(r"^(scrolls|potions) of ")


def _item_name(name: str) -> str:
    name = _ARTICLE_RE.sub("", name.strip())
    return _PLURAL_RE.sub(lambda m: m.group(1)[:-1] + " of ", name)


def _pips(value: str) -> int:
    """Resist pips: '. . .' -> 0, '+...' -> 1, '++++' -> 4."""
    return value.count("+") - value.count("-")


@dataclass
class Mistake:
    rule: str
    label: str
    severity: str  # high | medium | low
    evidence: str
    advice: str


def _escape_items(g: Game) -> list[str]:
    out: list[str] = []
    for items in g.inventory.values():
        for it in items:
            name = _item_name(it["name"])
            if name.startswith(("scroll of blinking", "scroll of teleportation", "scroll of fear")):
                out.append(f"{it['count']}× {name}")
            elif name.startswith(("potion of haste", "potion of berserk rage")):
                out.append(f"{it['count']}× {name}")
    return out


def _healing_items(g: Game) -> list[str]:
    out: list[str] = []
    for items in g.inventory.values():
        for it in items:
            name = _item_name(it["name"])
            if name.startswith(("potion of curing", "potion of heal wounds")):
                out.append(f"{it['count']}× {name}")
    return out


def _wand_count(g: Game) -> int:
    return sum(it["count"] for it in g.inventory.get("Wands", []))


def _unknown_count(g: Game) -> int:
    n = 0
    for cat in ("Scrolls", "Potions"):
        for it in g.inventory.get(cat, []):
            if it["unknown"]:
                n += it["count"]
    return n


def _invoke_total(g: Game) -> int:
    return sum(v for k, v in g.action.items() if k.startswith("Invoke:"))


_RESIST_KEYWORDS = {
    "rFire": ("fire", "flame", "flames", "dragon", "ignite", "hellfire",
              "fireball", "magma", "cinder", "burn"),
    "rCold": ("cold", "frost", "ice", "glaciate", "freeze", "freezing"),
    "rPois": ("poison", "venom"),
    "rElec": ("electric", "lightning", "shock", "storm", "static"),
}


def _resist_gap(g: Game) -> tuple[str, str] | None:
    text = (g.cause + " " + g.killer).lower()
    for resist, words in _RESIST_KEYWORDS.items():
        if any(w in text for w in words) and _pips(g.resists.get(resist, ".")) == 0:
            return resist, words[0]
    return None


def analyze(g: Game) -> list[Mistake]:
    m: list[Mistake] = []
    if g.outcome != "death":
        return m

    def add(rule, label, severity, evidence, advice):
        m.append(Mistake(rule, label, severity, evidence, advice))

    max_hp = g.max_hp
    dmg = g.damage
    cause = g.cause.lower()
    killer = g.killer

    # --- Inventory at death ---------------------------------------------
    esc = _escape_items(g)
    if esc:
        add("unused-escape", "Unused escape items", "high",
            "died with " + ", ".join(esc) + " in inventory",
            "Read/quaff the escape item the moment a fight turns — it only "
            "works while you're alive.")

    heal = _healing_items(g)
    if heal:
        add("unused-healing", "Unused healing potions", "high",
            "died with " + ", ".join(heal) + " still in inventory",
            "Potions of curing/heal wounds exist for exactly this moment; "
            "drink when HP drops, not at zero.")

    if _wand_count(g) >= 2:
        add("unused-wands", "Charged wands unused", "low",
            f"died with {_wand_count(g)} wands still charged",
            "Wands of paralysis/roots/mindburst are free crowd control — "
            "zap before the enemy reaches melee range.")

    unknown = _unknown_count(g)
    if unknown >= 2:
        add("unknown-consumables", "Unidentified consumables", "medium",
            f"died with {unknown} unidentified scrolls/potions",
            "Identify early and often — a scroll of blinking only helps if "
            "it's identified.")

    # --- Damage math ------------------------------------------------------
    if dmg is not None and max_hp:
        ratio = dmg / max_hp
        if ratio >= 0.8:
            add("one-shot", "Killed at (near) full HP", "high",
                f"death blow was {dmg} damage of {max_hp} max HP",
                f"'{killer or 'it'}' hits harder than you respected — check "
                "resistances and avoid letting it reach you at full strength.")
        elif ratio < 0.3:
            add("chip-death", "Died to chip damage", "medium",
                f"death blow was only {dmg} damage (max HP {max_hp})",
                "You fought on while nearly dead. Retreat or use consumables "
                "when HP gets low, not when it hits zero.")

    # --- Resistances ------------------------------------------------------
    gap = _resist_gap(g)
    if gap:
        add("resist-gap", f"No {gap[0]} vs {gap[1]} damage", "medium",
            f"died to {gap[1]} damage with no {gap[0]}",
            f"{gap[0]} would have absorbed a big chunk of that hit — "
            "grab some before pushing deeper.")

    # --- Gear / jewellery -------------------------------------------------
    slots = sorted({s for s in g.empty_slots if "ring" in s or "amulet" in s})
    if slots:
        add("empty-jewellery", "Empty ring/amulet slots", "low",
            "died with " + " and ".join(slots) + " at death",
            "Unidentified jewellery is still better than an empty slot.")

    enchant_scrolls = any(
        it["count"] for items in g.inventory.values() for it in items
        if _item_name(it["name"]).startswith(("scroll of enchant weapon",
                                              "scroll of enchant armour"))
    )
    if enchant_scrolls:
        worn = [it for items in g.inventory.values() for it in items
                if it["equipped"] and it["name"].lower().startswith(
                    ("a +0", "an +0", "the +0"))]
        if worn:
            names = ", ".join(_item_name(it["name"]) for it in worn[:2])
            add("unenchanted-gear", "Unenchanted worn gear", "low",
                f"wore {names} with enchant scrolls in inventory",
                "Enchant your main weapon/armour — a few +s are cheap and "
                "stack into real survivability.")

    # --- God --------------------------------------------------------------
    if g.god and g.xl and g.xl >= 5 and _invoke_total(g) == 0:
        add("panic-unused", "God abilities never invoked", "medium",
            f"worshipped {g.god} for the whole run without invoking once",
            f"{g.god}'s panic ability (Berserk, Trog's Hand, …) is a "
            "get-out-of-jail card — use it before the death blow.")

    if not g.god and g.xl and g.xl >= 5:
        add("no-god", "No god", "low",
            f"died at XL {g.xl} without worshipping a god",
            "A god's panic abilities save runs. Take the first reasonable "
            "altar you find.")

    # --- Circumstance ------------------------------------------------------
    if g.death_branch == "Abyss" or "banish" in cause:
        add("banished", "Banished into the Abyss", "medium",
            "died in the Abyss (banished)",
            "Respect translocation threats; avoid fights with banish-capable "
            "monsters or leave the moment you're in the Abyss.")

    if killer == "divine providence":
        add("god-wrath", "Killed by your own god", "high",
            "divine wrath (you angered your god)",
            "You broke your religion's conduct (e.g. attacking followers). "
            "Respect the god's rules or expect to die by divine decree.")

    if "starved" in cause:
        add("starved", "Starved to death", "medium",
            "ran out of food",
            "Don't auto-explore forever — eat when hungry, and remember "
            "chunks vanish, goblins don't.")

    if g.xl and g.xl <= 3:
        add("early-death", "Very early death", "low",
            f"died at XL {g.xl}",
            "Before XL 4 the dungeon is deadly if rushed — slow down, don't "
            "tab through unexplored areas.")

    if g.turns and g.death_branch:
        entry = g.entered_turns.get(g.death_branch)
        if entry is not None and g.turns - entry < 60:
            add("died-on-entry", "Died right after entering a branch", "medium",
                f"died {g.turns - entry} turns after entering {g.death_branch}",
                f"You were not ready for {g.death_branch} — it usually pays "
                "to be deeper/stronger before entering.")

    # wins don't get post-mortem (outcome guard not needed; wins have no killer)
    m.sort(key=lambda x: SEVERITY_ORDER.get(x.severity, 9))
    return m


def run_all(games: list[Game]) -> None:
    """Attach mistakes to every game in place."""
    for g in games:
        g.mistakes = analyze(g)
