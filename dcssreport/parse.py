"""Parse DCSS morgue files (0.18 through 0.35) into structured game records.

The morgue text format has stayed remarkably stable since 0.18; the parser
handles the known drift: `Health:` vs `HP:` stat lines, presence/absence of
the `Game seed:` and `You also visited:` lines, buffed-stat parentheses,
death-location dates, the action chart, and the vanquished-creatures
section (removed in 0.35).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

#: Ordered rough depth tiers used to rank how far a run got.
BRANCH_TIERS: dict[str, int] = {
    "Dungeon": 0,
    "Temple": 1,
    "Sewer": 1,
    "Ossuary": 1,
    "Bailey": 1,
    "Ice Cave": 1,
    "Volcano": 1,
    "Wizlab": 1,
    "Trove": 1,
    "Desolation": 1,
    "Gauntlet": 1,
    "Necropolis": 1,
    "Lair": 2,
    "Orc": 2,
    "Elven Halls": 2,
    "Swamp": 3,
    "Shoals": 3,
    "Snake": 3,
    "Spider": 3,
    "Slime": 3,
    "Vaults": 3,
    "Crypt": 3,
    "Depths": 4,
    "Zot": 5,
    "Tomb": 5,
    "Abyss": 5,
    "Pandemonium": 5,
    "Hells": 5,
    "Ziggurat": 5,
}

_BRANCH_LEVEL_MAX = {
    "Dungeon": 15, "Lair": 5, "Orc": 2, "Elven Halls": 3, "Swamp": 4,
    "Shoals": 4, "Snake": 4, "Spider": 4, "Slime": 5, "Vaults": 5,
    "Crypt": 3, "Depths": 4, "Zot": 5, "Tomb": 3, "Hells": 7, "Abyss": 5,
    "Ziggurat": 27,
}

#: Old-name branch aliases across DCSS versions.
_BRANCH_ALIASES = {
    "Lair of Beasts": "Lair",
    "Orcish Mines": "Orc",
    "Snake Pit": "Snake",
    "Spider Nest": "Spider",
    "Slime Pits": "Slime",
    "Hell": "Hells",
}


def normalize_branch(name: str | None) -> str | None:
    """Clean a branch name: strip punctuation/articles, unify old names."""
    if not name:
        return name
    name = name.strip().rstrip(".")
    name = re.sub(r"^(a|an|the)\s+", "", name)
    return _BRANCH_ALIASES.get(name, name)


def depth_score(branch: str | None, level: int | None) -> float:
    """Monotone-ish measure of how deep a run reached."""
    if not branch:
        return 0.0
    tier = BRANCH_TIERS.get(branch, 1)
    if not level:
        return float(tier)
    return float(tier) + (level - 1) / (_BRANCH_LEVEL_MAX.get(branch, 10) + 1)


def killer_of(cause_short: str) -> str:
    """Normalise a death cause to the responsible creature/thing.

    'an iguana' -> 'iguana'; 'a large rock thrown by a stone giant'
    -> 'stone giant'; 'an air elemental ... summoned by Sojobo' -> 'Sojobo'.
    """
    c = cause_short.strip()
    for marker in ("thrown by ", "shot by ", "fired by ", "cast by ",
                   "summoned by ", "breathed by ", "hurled by "):
        if marker in c:
            c = c.split(marker, 1)[-1]
            break
    else:
        if " by " in c:
            c = c.split(" by ", 1)[-1]
    c = re.sub(r"^(a|an|the)\s+", "", c)
    c = re.split(r",\s*(?:while|with|from)", c)[0]
    c = c.strip().rstrip(".")
    return c or cause_short.strip()


@dataclass
class Note:
    turn: int
    place: str
    text: str


@dataclass
class Game:
    source: str                       # file name
    score: int | None = None
    name: str = ""
    title: str = ""
    species: str = ""
    background: str = ""
    xl: int | None = None
    hp_at_end: str = ""
    god: str = ""
    outcome: str = "death"            # death | win
    cause: str = ""                   # full death/escape line
    cause_short: str = ""             # e.g. "fire crab" | "stone giant"
    killer: str = ""
    damage: int | None = None
    death_branch: str | None = None
    death_level: int | None = None
    death_date: datetime | None = None
    game_date: datetime | None = None  # from file name (canonical)
    began_date: datetime | None = None
    duration: int | None = None       # seconds
    turns: int | None = None
    gold: int | None = None
    gold_spent: int | None = None
    runes: int = 0
    rune_names: list[str] = field(default_factory=list)
    ac: int | None = None
    ev: int | None = None
    sh: int | None = None
    str_: int | None = None
    int_: int | None = None
    dex: int | None = None
    resists: dict[str, str] = field(default_factory=dict)
    skills: dict[str, float] = field(default_factory=dict)
    branches_visited: dict[str, int] = field(default_factory=dict)  # branch -> levels seen
    branches_total: dict[str, int] = field(default_factory=dict)
    extra_branches: list[str] = field(default_factory=list)
    vanquished: int | None = None
    notes: list[Note] = field(default_factory=list)
    version: str = ""
    seed: str | None = None
    uniques_killed: list[str] = field(default_factory=list)
    inventory: dict[str, list[dict]] = field(default_factory=dict)  # category -> items
    empty_slots: list[str] = field(default_factory=list)
    action: dict[str, int] = field(default_factory=dict)            # "Invoke: Berserk" -> total
    entered_turns: dict[str, int] = field(default_factory=dict)     # branch -> first turn entered
    mistakes: list = field(default_factory=list)

    @property
    def max_hp(self) -> int | None:
        """Max HP at death: '102' from '-10/102' or '180' from '-4/159 (180)'."""
        m = re.search(r"/(\d+)(?: \((\d+)\))?$", self.hp_at_end)
        if not m:
            return None
        return int(m.group(2) or m.group(1))

    @property
    def depth(self) -> float:
        """Deepest point reached, from branches visited or death location."""
        d = max(
            [depth_score(b, lvl) for b, lvl in self.branches_visited.items()]
            + [depth_score(self.death_branch, self.death_level)]
        )
        return d

    @property
    def depth_label(self) -> str:
        cands = []
        for b, lvl in self.branches_visited.items():
            cands.append((depth_score(b, lvl), f"{b}:{lvl}" if lvl else b))
        cands.append((depth_score(self.death_branch, self.death_level),
                      f"{self.death_branch}:{self.death_level}"
                      if self.death_level else (self.death_branch or "")))
        if not cands:
            return ""
        return max(cands, key=lambda t: t[0])[1]


# --------------------------------------------------------------------------
# Regexes
# --------------------------------------------------------------------------

_TITLE_RE = re.compile(
    r"^(\d+)\s+(\S+)\s+the\s+(.+?)\s+\(level\s+(\d+),\s+(.+?)\s*HPs\)$"
)
_BEGAN_RE = re.compile(r"^Began as an? (.+) on ([A-Z][a-z]+ \d+, \d+)\.")
_GOD_RE = re.compile(r"^Was (?:an?|the) (?:[\w ]+?) of (.+?)\.$")
_DEATH_RE = re.compile(
    r"^(?:"
    r"Slain by (.+?)|Mangled by (.+?)|Killed by (.+?)|Destroyed by (.+?)"
    r"|Demolished by (.+?)|Annihilated by (.+?)|Eviscerated by (.+?)"
    r"|Blasted by (.+?)|Burned by (.+?)|Frozen by (.+?)|Polymorphed by (.+?)"
    r"|Congealed by (.+?)|Stabbed by (.+?)|Shattered by (.+?)"
    r"|Hit by (.+?)|Shot by (.+?)|Shot with .+? by (.+?)"
    r"|Killed from afar by (.+?)|Splashed by (.+?)|Incinerated by (.+?)"
    r"|Impaled on (.+?)|Torn apart by (.+?)"
    r"|Devoured by (.+?)|Engulfed in (.+?)|Engulfed by (.+?)"
    r"|Frozen to death by (.+?)|Burned to death by (.+?)"
    r"|Blown up by (.+?)"
    r"|Fell into (.+?)"
    r"|Succumbed to (.+?)|Quaffed (.+?)|Bled out|Drowned|Starved"
    r"|Petrified by (.+?)|Asphyxiated|Was banished by (.+?)"
    r"|Spell-rotted|Was killed by (.+?)"
    r")(?: \((\d+) damage\))?$"
)
_WIN_RE = re.compile(
    r"^(Escaped with the Orb of Zot!|Got out of the dungeon alive\.|Was the champion of the Dungeon\.)"
)
_LASTED_RE = re.compile(r"The game lasted (\d+):(\d+):(\d+) \((\d+) turns\)\.")
_WHERE_RE = re.compile(r"^\.\.\. on (.+)$")
_LEVEL_LOC_RE = re.compile(r"^level (\d+) of (?:the )?(.+?)(?: on [A-Z][a-z]+ \d+, \d+\.)?$")
_PLAIN_DATE_RE = re.compile(r"^[A-Z][a-z]+ \d+, \d+\.$")
_FINAL_WHERE_RE = re.compile(r"^You were (?:on|in) (?:level (\d+) of )?(?:the )?(.+?)\.$")
_VISITED_RE = re.compile(r"^You visited (\d+) branch(?:es)? of the dungeon, and saw (\d+) of its levels\.$")
_ALSO_VISITED_RE = re.compile(r"^You also visited: (.+)$")
_NECRO_RE = re.compile(r"^You visited (?:the )?(.+?) \d+ times?\.$")
_GOLD_RE = re.compile(r"^You collected (\d+) gold pieces\.$")
_SPENT_RE = re.compile(r"^You spent (\d+) gold pieces at shops\.$")
_RUNES_RE = re.compile(r"^}: (\d+)/\d+ runes:? ?(.*)$")
_WORSHIP_RE = re.compile(r"^You worshipped (.+?)\.$")
_VANQUISHED_RE = re.compile(r"^(\d+) creatures? vanquished\.$")
_SKILL_RE = re.compile(r"^([+*-]) Level (\d+(?:\.\d+)?)(?:\((\d+(?:\.\d+)?)\))? (\w.*)$")
_VERSION_RE = re.compile(r"^Dungeon Crawl Stone Soup version (\S+)")
_SEED_RE = re.compile(r"^Game seed: (\d+)$")
_NOTE_RE = re.compile(r"^(\d+) \|\s*(\S+)\s*\| (.*)$")
_KILL_NOTE_RE = re.compile(r"^Killed (?!by\b)([A-Z]\w.*)$")
_ENTERED_RE = re.compile(r"^Entered (?:Level (\d+) of )?(?:the )?(.+)$")
_INV_CAT_RE = re.compile(
    r"^(Hand Weapons|Weapons|Missiles|Armour|Jewellery|Wands|Scrolls|Potions"
    r"|Comestibles|Miscellaneous|Magical Devices|Books|Food)$"
)
_INV_ITEM_RE = re.compile(r"^[a-z] - (.+)$")
_EMPTY_SLOT_RE = re.compile(r"\((no (?:ring|amulet|helmet|gloves|boots|shield|barding))\)")
_ACTION_RE = re.compile(r"^(\s*)(\w+): ([^|]*?)\s*\|.*\|\| *(\d+)\s*$")
_ENCHANT_RE = re.compile(r"^([+-]\d+) ")
_EQUIP_PARENS = {"worn", "weapon", "quivered", "left hand", "right hand", "around neck"}


def _parse_inv_item(rem: str) -> dict:
    """'2 scrolls of fog {unknown}' / 'a +2 battleaxe (weapon)' -> item dict."""
    item: dict = {"name": "", "count": 1, "unknown": False,
                  "equipped": False, "enchant": None}
    rem = rem.strip()
    m = re.match(r"^(\d+) (.+)$", rem)
    if m:
        item["count"] = int(m.group(1))
        rem = m.group(2)
    brace = ""
    if "{" in rem:
        rem, _, brace = rem.partition("{")
        rem = rem.rstrip()
        brace = brace.rstrip("}")
    paren = ""
    if "(" in rem:
        rem, _, paren = rem.partition("(")
        rem = rem.rstrip()
        paren = paren.rstrip(")")
    item["name"] = rem
    item["unknown"] = "unknown" in brace
    item["equipped"] = paren.strip() in _EQUIP_PARENS
    m = _ENCHANT_RE.match(rem)
    if m:
        item["enchant"] = int(m.group(1))
    return item
_XL_RE = re.compile(r"\bXL:\s*(\d+)")
_GOD_STAT_RE = re.compile(r"\bGod:\s*(\w[\w ]*?)\s*(?:\[[.\*]*\]\s*)?$")
_HP_RE = re.compile(r"^(?:Health|HP):\s*([-\d]+/\d+(?: \(\d+\))?)")
_AC_RE = re.compile(r"\bAC:\s*(\d+)")
_EV_RE = re.compile(r"\bEV:\s*(\d+)")
_SH_RE = re.compile(r"\bSH:\s*(\d+)")
_STR_RE = re.compile(r"\bStr:\s*(\d+)(?: \(\d+\))?")
_INT_RE = re.compile(r"\bInt:\s*(\d+)(?: \(\d+\))?")
_DEX_RE = re.compile(r"\bDex:\s*(\d+)(?: \(\d+\))?")
_RESIST_NAMES = (
    "rFire", "rCold", "rNeg", "rPois", "rElec", "rCorr", "SInv", "Will",
    "Stlth", "MR", "SustAt", "SeeInvis", "Gourm", "Faith", "Spirit",
    "Dismiss", "Reflect", "Harm",
)
_RESIST_RE = re.compile(
    r"^(rFire|rCold|rNeg|rPois|rElec|rCorr|SInv|Will|Stlth|MR|SustAt"
    r"|SeeInvis|Gourm|Faith|Spirit|Dismiss|Reflect|Harm)"
    r"\s+([.\-+ ]+?)\s*(?:\(100%\))?\s*(?:$|\[|\(|[a-z] - |[A-Z]\w+\s)"
)
_BRANCH_LINE_RE = re.compile(r"^(\w[\w ]*?)\s+\((\d+)/(\d+)\)")
_BRANCH_VISITED_RE = re.compile(r"^(\w[\w ]*?)\s+\(visited\)")
#: All species names that have appeared in DCSS 0.18–0.35, longest first.
_SPECIES = (
    "Vine Stalker", "Mountain Dwarf", "Sludge Elf", "Deep Dwarf",
    "Deep Elf", "High Elf", "Hill Orc", "Demigod", "Halfling",
    "Spriggan", "Minotaur", "Centaur", "Merfolk", "Octopode",
    "Gargoyle", "Formicid", "Barachi", "Djinni", "Draconian",
    "Armataur", "Vampire", "Kobold", "Tengu", "Naga", "Troll",
    "Ogre", "Ghoul", "Mummy", "Felid", "Gnoll", "Human",
)

_STATS_KEYS = {
    "Health:": True, "HP:": True, "Magic:": True, "MP:": True, "Gold:": True,
}


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse_morgue(text: str, source: str) -> Game:
    g = Game(source=source)
    m = _VERSION_RE.search(text)
    if m:
        g.version = m.group(1)
    m = _SEED_RE.search(text)
    if m:
        g.seed = m.group(1)

    lines = text.splitlines()

    # --- Header ---------------------------------------------------------
    title_idx, title_m = None, None
    for i, ln in enumerate(lines[:14]):
        m = _TITLE_RE.match(ln.strip())
        if m:
            title_idx, title_m = i, m
            break
    if title_m:
        g.score = int(title_m.group(1))
        g.name = title_m.group(2)
        g.title = title_m.group(3)
        g.xl = int(title_m.group(4))
        g.hp_at_end = title_m.group(5).strip()

    header_end = min((title_idx + 1) + 14, len(lines))
    for j in range((title_idx + 1) if title_idx is not None else 0, header_end):
        ln = lines[j].strip()
        if not ln:
            continue
        if ln.split(" ", 1)[0] in _STATS_KEYS:
            header_end = j
            break
        m = _BEGAN_RE.match(ln)
        if m:
            g.species, g.background = _split_species_background(m.group(1))
            g.began_date = _parse_date(m.group(2))
            if g.game_date is None:
                g.game_date = g.began_date
            continue
        m = _GOD_RE.match(ln)
        if m:
            g.god = m.group(1).strip()
            continue
        m = _WIN_RE.match(ln)
        if m:
            g.outcome = "win"
            g.cause = m.group(1)
            g.cause_short = "escaped with the Orb of Zot"
            g.killer = "the Orb of Zot"
            continue
        m = _DEATH_RE.match(ln)
        if m:
            parts = [p for p in m.groups() if p is not None]
            if parts and parts[-1].isdigit():
                g.damage = int(parts[-1])
                parts = parts[:-1]
            g.cause = ln
            g.cause_short = (" ".join(parts) or ln).strip()
            g.killer = killer_of(g.cause_short)
            continue
        m = _LASTED_RE.match(ln)
        if m:
            g.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            g.turns = int(m.group(4))
            continue
        m = _WHERE_RE.match(ln)
        if m:
            loc = m.group(1).strip()
            if _PLAIN_DATE_RE.match(loc):
                continue
            lm = _LEVEL_LOC_RE.match(loc)
            if lm:
                g.death_branch = normalize_branch(lm.group(2))
                g.death_level = int(lm.group(1))
            else:
                g.death_branch = normalize_branch(loc)
            dm = re.search(r"on ([A-Z][a-z]+ \d+, \d+)\.$", loc)
            if dm:
                g.death_date = _parse_date(dm.group(1))
            continue
        if ln.startswith("... ") and g.cause and g.death_branch is None:
            g.cause += ", " + ln[4:].strip()
            continue

    # --- Stats block + resists ------------------------------------------
    for j in range(header_end, min(header_end + 14, len(lines))):
        ln = lines[j]
        s = ln.strip()
        if not s:
            continue
        if s.split(" ", 1)[0] in _STATS_KEYS:
            _parse_stats_line(ln, g)
            continue
        g.empty_slots.extend(_EMPTY_SLOT_RE.findall(ln))
        if s.split(" ", 1)[0] in _RESIST_NAMES:
            m = _RESIST_RE.match(ln)
            if m:
                g.resists[m.group(1)] = m.group(2).strip()
            continue
        break

    section = ""
    inv_section = ""
    in_skills = False
    in_notes = False
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s == "Skills:":
            in_skills = True
            continue
        if s.startswith("Innate Abilities") or s == "Inventory:" or s.startswith("Dungeon Overview"):
            in_skills = False
            if s.startswith("Dungeon Overview"):
                section = "overview"
            elif s == "Inventory:":
                section = "inventory"
                inv_section = ""
            continue
        if s == "Notes":
            in_notes = True
            section = "notes"
            continue
        if s == "Message History" or s == "Vanquished Creatures":
            in_notes = False
            section = s
            continue
        if s.startswith("Skill      XL:"):
            section = "skillchart"
            in_skills = False
            continue
        if s.startswith("Action"):
            section = "action"
            continue

        if section == "inventory":
            if _INV_CAT_RE.match(s):
                inv_section = s
                continue
            g.empty_slots.extend(_EMPTY_SLOT_RE.findall(s))
            m = _INV_ITEM_RE.match(s)
            if m and inv_section:
                g.inventory.setdefault(inv_section, []).append(_parse_inv_item(m.group(1)))
            continue

        if section == "action":
            m = _ACTION_RE.match(ln)
            if m:
                sub = m.group(3).strip()
                g.action[f"{m.group(2)}: {sub}".strip()] = int(m.group(4))
            continue

        if in_skills and section != "skillchart":
            m = _SKILL_RE.match(s)
            if m:
                g.skills[m.group(4).strip()] = float(m.group(2))
                continue

        if section == "overview":
            m = _BRANCH_LINE_RE.match(s)
            if m:
                name = normalize_branch(m.group(1))
                g.branches_visited[name] = int(m.group(2))
                g.branches_total[name] = int(m.group(3))
                continue
            m = _BRANCH_VISITED_RE.match(s)
            if m:
                g.extra_branches.append(normalize_branch(m.group(1)))
                continue
            continue

        if section == "notes" and in_notes:
            m = _NOTE_RE.match(s)
            if m:
                note = Note(int(m.group(1)), m.group(2), m.group(3))
                g.notes.append(note)
                km = _KILL_NOTE_RE.match(note.text)
                if km:
                    g.uniques_killed.append(km.group(1).strip())
                em = _ENTERED_RE.match(note.text)
                if em:
                    branch = normalize_branch(em.group(2))
                    if branch:
                        prev = g.entered_turns.get(branch)
                        if prev is None or note.turn < prev:
                            g.entered_turns[branch] = note.turn
                continue

        m = _ALSO_VISITED_RE.match(s)
        if m:
            g.extra_branches.extend(normalize_branch(x.strip()) for x in m.group(1).split(","))
            continue
        m = _NECRO_RE.match(s)
        if m:
            phrase = m.group(1)
            g.extra_branches.append(normalize_branch(phrase.rsplit(" of the ", 1)[-1]))
            continue
        m = _GOLD_RE.match(s)
        if m:
            g.gold = int(m.group(1))
            continue
        m = _SPENT_RE.match(s)
        if m:
            g.gold_spent = int(m.group(1))
            continue
        m = _RUNES_RE.match(s)
        if m:
            g.runes = int(m.group(1))
            if m.group(2).strip():
                g.rune_names = [x.strip() for x in m.group(2).split(",")]
            continue
        m = _WORSHIP_RE.match(s)
        if m and not g.god:
            g.god = m.group(1).strip()
            continue
        m = _VANQUISHED_RE.match(s)
        if m:
            g.vanquished = int(m.group(1))
            continue
        m = _FINAL_WHERE_RE.match(s)
        if m and not g.death_branch:
            g.death_branch = normalize_branch(m.group(2))
            if m.group(1):
                g.death_level = int(m.group(1))
            continue

    return g

def _split_species_background(began: str) -> tuple[str, str]:
    """Split 'Minotaur Berserker' / 'Human Ice Elementalist' correctly."""
    for name in _SPECIES:
        if began.startswith(name + " "):
            return name, began[len(name) + 1:].strip()
    return began, ""

def _parse_date(s: str) -> datetime | None:
    s = s.replace("Sept", "Sep")
    try:
        return datetime.strptime(s, "%b %d, %Y")
    except ValueError:
        return None


def _parse_stats_line(ln: str, g: Game) -> None:
    for regex, attr in (
        (_HP_RE, "hp_at_end"), (_AC_RE, "ac"), (_EV_RE, "ev"), (_SH_RE, "sh"),
        (_STR_RE, "str_"), (_INT_RE, "int_"), (_DEX_RE, "dex"), (_XL_RE, "xl"),
    ):
        m = regex.search(ln)
        if m:
            setattr(g, attr, int(m.group(1)) if attr != "hp_at_end" else m.group(1))
    m = _GOD_STAT_RE.search(ln)
    if m and not g.god:
        g.god = m.group(1).strip()


def parse_file(path: str | Path) -> Game:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    g = parse_morgue(text, path.name)
    g.source = path.name
    m = re.search(r"(\d{8})-(\d{6})", path.name)
    if m:
        try:
            g.game_date = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return g


def parse_dir(dirpath: str | Path) -> list[Game]:
    dirpath = Path(dirpath)
    games = [parse_file(p) for p in sorted(dirpath.glob("morgue-*.txt"))]
    games.sort(key=lambda g: g.game_date or datetime.min)
    return games
