"""Monster, unique and species art tiles for the report.

DCSS ships its monster art as individual small transparent PNGs in the crawl
repository under `crawl-ref/source/rltiles/`.  The `.txt` layout files there
name every tile and the monster it belongs to, but the mapping from *morgue*
display names ("ancient lich", "Roxanne") to tile names is not published, so we
derive it here:

1. parse the layout files (`dc-mon.txt` plus the files it includes) into an
   inventory of tile basename -> png path (+ whether the tile lives in the
   uniques directory);
2. resolve a display name to an inventory entry with a slug rule plus a small
   alias table for the names the rule cannot know (color adjectives, size
   words, renames, boss variants, possessive "…'s poison" causes);
3. download only the pngs the report actually needs, cached under the tile
   directory (default `data/tiles/`), and hand the renderer base64 data URIs
   so the report stays one self-contained file.

Species art is not in the layout files: characters are built from part layers.
The base layer is a full character sprite per species, so we use that alone,
resolving species names (as written in morgues, e.g. "Centaur") to current
repo base files with an alias table for renames.

Tile art in the crawl repo is public-domain/CC0 — see
`crawl-ref/source/rltiles/license.txt`.
"""

from __future__ import annotations

import base64
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

RAW_ROOT = (
    "https://raw.githubusercontent.com/crawl/crawl/master"
    "/crawl-ref/source/rltiles"
)
USER_AGENT = "dcss-morgue-report/1.2 (tiles)"

#: Layout files that together define every monster tile.  dc-mon.txt includes
#: the other three; each file sets its own `%sdir` so parsing order only
#: matters for duplicate basenames, which are rare.
LAYOUT_FILES = ("dc-mon.txt", "dc-demon.txt", "dc-tentacles.txt", "dc-zombie.txt")

_DELAY = 0.1
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    """'Bai Suzhen' -> 'bai_suzhen'; 'killer bee's poison' -> 'killer_bees_poison'."""
    return _SLUG_RE.sub("_", str(name).lower()).strip("_")


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _fetch(url: str) -> bytes | None:
    """GET `url`, returning None on 404 (tile not in the repo)."""
    try:
        return _http_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# --------------------------------------------------------------------------
# Monster catalog
# --------------------------------------------------------------------------

class Catalog:
    """Tile inventory: tile basename -> (rltiles-relative png path, is_unique)."""

    def __init__(self, entries: dict[str, tuple[str, bool]]):
        self.entries = entries

    @classmethod
    def parse(cls, texts: dict[str, str]) -> "Catalog":
        """Parse layout files into an inventory.

        A layout line is `<tile> MONS_<NAME>` where `<tile>` is either a bare
        name (relative to the current `%sdir`) or a repo-relative path such as
        `mon/unique/grinder`.  A following id-less line is an alternate look
        for the same monster and is skipped.  Tiles under `mon/unique` are
        uniques (named bosses).
        """
        entries: dict[str, tuple[str, bool]] = {}
        for fname in LAYOUT_FILES:
            if fname not in texts:
                continue
            sdir = ""
            for raw in texts[fname].splitlines():
                ln = raw.strip()
                if not ln or ln.startswith("#"):
                    continue
                if ln.startswith("%"):
                    parts = ln.split()
                    if parts and parts[0] == "%sdir":
                        sdir = parts[1] if len(parts) > 1 else ""
                    continue
                toks = ln.split()
                if len(toks) < 2:
                    continue  # variant look of the monster above; not primary
                name, token = toks[0], toks[1]
                if not token.startswith("MONS_"):
                    continue  # same: id-less alternates carry no MONS id
                rel = name if "/" in name else (f"{sdir}/{name}" if sdir else name)
                base = name.rsplit("/", 1)[-1]
                entries.setdefault(base, (rel, rel.startswith("mon/unique")))
        return cls(entries)

    def lookup(self, display: str) -> tuple[str, bool, str | None] | None:
        """Resolve a display name to (png relpath, is_unique, git ref).

        Tries, in order: the current tile inventory (slug rule plus color/size
        suffix rules, e.g. "cyan very ugly thing"); named specials — respelled
        or orphan art plus non-monster causes with real effect/feature art
        (clouds, god altars handled by the caller); monsters removed from the
        repo, resolved to the last release tag that still shipped their art;
        the head of a possessive cause ("killer bee's poison"); and, for
        unique names carrying a title ("Blorkula the Orcula"), the name before
        the title.  Returns None when no art exists anywhere in the repo.
        """
        name = str(display).strip()
        if not name:
            return None
        cands = [slug(name)]
        low = name.lower()
        for suffix, base in ((" very ugly thing", "very_ugly_thing"),
                             (" ugly thing", "ugly_thing"),
                             (" slime creature", "slime_creature")):
            if low.endswith(suffix):
                cands.append(base)
        for c in cands:
            hit = self.entries.get(c)
            if hit:
                return (hit[0], hit[1], None)
        spec = SPECIAL_TILES.get(low)
        if spec:
            return spec
        hist = HISTORIC_TILES.get(low)
        if hist:
            return hist
        m = re.search(r"'s\b", name)
        if m:
            cands.append(slug(name[: m.start()]))
        if " the " in name:
            cands.append(slug(name.split(" the ", 1)[0]))
        for c in cands:
            hit = self.entries.get(c)
            if hit:
                return (hit[0], hit[1], None)
        return None


#: Named tiles the inventory cannot provide: respelled names, orphan art
#: (pngs in the repo but unreferenced by the layout files), and non-monster
#: death causes that have real DCSS effect/feature art.  Values are
#: (relpath, is_unique, ref).
SPECIAL_TILES = {
    "bai suzhen": ("mon/unique/bai_suizhen", True, None),  # tile is respelled
    "lernaean hydra": ("mon/unique/lernaean_hydra01", True, None),
    "the lernaean hydra": ("mon/unique/lernaean_hydra01", True, None),
    "royal jelly": ("mon/unique/royal_jelly", True, None),
    # abstract causes of death with matching effect art (flame / miasma clouds)
    "cloud of flame": ("effect/cloud_fire0", False, None),
    "poison (dark miasma)": ("effect/cloud_miasma0", False, None),
}

#: Monsters whose art was deleted from the repo when they left the game, kept
#: in git history.  Ref is the newest release tag that still shipped the png.
HISTORIC_TILES = {
    "deep elf mage": ("mon/humanoids/elves/deep_elf_mage", False, "0.25.0"),
}


def fetch_layouts(cache_dir: Path) -> dict[str, str] | None:
    """Download the layout files once, returning {file name: text}.

    Returns None if the fetch fails (offline / upstream reorg); callers fall
    back to a report without tiles.
    """
    cache_dir = Path(cache_dir)
    texts: dict[str, str] = {}
    try:
        for fname in LAYOUT_FILES:
            target = cache_dir / fname
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                data = _http_get(f"{RAW_ROOT}/{fname}")
                target.write_bytes(data)
                time.sleep(_DELAY)
            texts[fname] = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    return texts


# --------------------------------------------------------------------------
# Species art
# --------------------------------------------------------------------------

#: Morgue species name -> current player/base file stem.  Renames across DCSS
#: versions (Centaur -> Gale Centaur, Dwarf -> Mountain Dwarf, …) plus species
#: whose base file is not `<name>_m`.  Species not listed fall back to the
#: slug rule.
SPECIES_STEMS = {
    "Centaur": "gale_centaur",
    "Gale Centaur": "gale_centaur",
    "Mountain Dwarf": "dwarf",
    "Deep Dwarf": "deep_dwarf",
    "Deep Elf": "deep_elf",
    "High Elf": "elf",
    "Hill Orc": "orc",
    "Vampire": "vampire",
    "Kobold": "kobold",
    "Tengu": "tengu_wingless",
    "Naga": "naga_green",
    "Barachi": "frog",
    "Djinni": "djinni_red",
    "Draconian": "draconian",
    "Black Draconian": "draconian_black",
    "Green Draconian": "draconian_green",
    "Grey Draconian": "draconian_grey",
    "Pale Draconian": "draconian_pale",
    "Purple Draconian": "draconian_purple",
    "Red Draconian": "draconian_red",
    "White Draconian": "draconian_white",
    "Yellow Draconian": "draconian_yellow",
    "Demonspawn": "demonspawn_pink",
    "Oni": "oni_red",
    "Vine Stalker": "vine_stalker_green",
    "Gargoyle": "gargoyle",
    "Octopode": "octopode1",
}


def species_relpath(species: str) -> str | None:
    """rltiles path of a character base tile for `species`, or None.

    Prefers the male variant (`<stem>_m`) when one exists; single-file species
    (formicid, coglin, octopode…) have no gender suffix and are found by the
    bare-stem probe.
    """
    stem = slug(SPECIES_STEMS.get(species, species))
    for cand in (f"{stem}_m", stem):
        if cand in _SPECIES_BASE_FILES:
            return f"player/base/{cand}.png"
    return None


#: player/base file inventory for species resolution, derived from the repo
#: (updated as DCSS changes).  Species with no entry here have no base art.
_SPECIES_BASE_FILES = frozenset(
    """
coglin deep_dwarf_f deep_dwarf_m deep_elf_f deep_elf_m demigod_f demigod_m
demonspawn_black_f demonspawn_black_m demonspawn_pink demonspawn_red_f
demonspawn_red_m djinni_blue_f djinni_blue_m djinni_gold_f djinni_gold_m
djinni_purple_f djinni_purple_m djinni_red_f djinni_red_m draconian
draconian_black draconian_green draconian_grey draconian_pale
draconian_purple draconian_red draconian_white draconian_yellow dwarf_f
dwarf_m elf_f elf_m formicid frog2_f frog2_m frog_f frog_m
gale_centaur_cloud_f gale_centaur_cloud_m gale_centaur_f gale_centaur_m
gale_centaur_sky_f gale_centaur_sky_m gargoyle_brown_f gargoyle_brown_m
gargoyle_f gargoyle_m gargoyle_red_f gargoyle_red_m ghoul2_f ghoul2_m
ghoul_m gnoll2_f gnoll2_m gnoll3_f gnoll3_m gnoll4_f gnoll4_m gnoll_f
gnoll_m gnome_f gnome_m halfling_f halfling_m human2_f human2_m human3_f
human3_m human_f human_m kobold2_f kobold2_m kobold_f kobold_m lorc_f0
lorc_f1 lorc_f2 lorc_f3 lorc_f4 lorc_f5 lorc_f6 lorc_m0 lorc_m1 lorc_m2
lorc_m3 lorc_m4 lorc_m5 lorc_m6 merfolk_f merfolk_m merfolk_water_f
merfolk_water_m meteoran_f meteoran_m minotaur_brown1_m minotaur_brown2_m
minotaur_f minotaur_m mummy_f mummy_m naga_blue_f naga_blue_m
naga_bushfire_f naga_bushfire_m naga_cave_f naga_cave_m naga_darkgreen_f
naga_darkgreen_m naga_deep_f naga_deep_m naga_dune_f naga_dune_m
naga_green_f naga_green_m naga_lightgreen_f naga_lightgreen_m
naga_milksnake_f naga_milksnake_m naga_orange_f naga_orange_m
naga_purple_f naga_purple_m naga_rattlesnake_f naga_rattlesnake_m
naga_red_f naga_red_m naga_river_f naga_river_m naga_shadow_f
naga_shadow_m naga_stream_f naga_stream_m naga_swamp_f naga_swamp_m
octopode1 octopode2 octopode3 octopode4 octopode5 oni_black_f oni_black_m
oni_blue_f oni_blue_m oni_green_f oni_green_m oni_red_f oni_red_m
oni_yellow_f oni_yellow_m orc_f orc_m poltergeist revenant revenant2
shadow spriggan_f spriggan_m tengu_winged_f tengu_winged_m
tengu_wingless_brown_f tengu_wingless_brown_m tengu_wingless_f
tengu_wingless_m troll_f troll_m vampire_f vampire_m
vine_stalker_green_f vine_stalker_green_m vine_stalker_purple_f
vine_stalker_purple_m vine_stalker_red_f vine_stalker_red_m
""".split()
)


# --------------------------------------------------------------------------
# Downloading and embedding
# --------------------------------------------------------------------------

def _raw_url(rel: str, ref: str | None) -> str:
    root = f"https://raw.githubusercontent.com/crawl/crawl/{ref or 'master'}/crawl-ref/source/rltiles"
    return f"{root}/{rel}"


def _png_data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _cached_relpath(cache_dir: Path, rel: str, ref: str | None) -> Path:
    # flatten the repo dirs; basenames are unique across the inventory, and a
    # git ref suffix keeps historic art apart should master gain the same name
    flat = rel.rsplit("/", 1)[-1]
    return cache_dir / "img" / flat.replace(".png", f"~{ref}.png" if ref else ".png")


def png_bytes(rel: str, cache_dir: Path, *, ref: str | None = None,
              force: bool = False) -> bytes | None:
    """Return cached (or freshly downloaded) png bytes for a tile path."""
    if not rel.endswith(".png"):
        rel = rel + ".png"
    target = _cached_relpath(cache_dir, rel, ref)
    if target.exists() and not force:
        return target.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = _fetch(_raw_url(rel, ref))
    if data is None:
        return None
    target.write_bytes(data)
    time.sleep(_DELAY)
    return data


def embed_relpath(rel: str, cache_dir: Path, *, ref: str | None = None
                  ) -> str | None:
    """Data URI for a tile path, or None when the art cannot be fetched."""
    try:
        data = png_bytes(rel, cache_dir, ref=ref)
    except Exception:
        return None
    return _png_data_uri(data) if data else None


def embed_monster_tiles(names: set[str], cache_dir: Path,
                        catalog: Catalog | None) -> dict[str, str]:
    """Download art for every catalog-resolvable monster/unique name."""
    out: dict[str, str] = {}
    if catalog is None:
        return out
    for name in sorted(names):
        hit = catalog.lookup(name)
        if hit is None:
            continue
        uri = embed_relpath(hit[0], cache_dir, ref=hit[2])
        if uri:
            out[name] = uri
    return out


def embed_species_tiles(species_names: set[str],
                        cache_dir: Path) -> dict[str, str]:
    """Download a character base tile for every resolvable species name.

    Species resolve against the player/base inventory, never the monster
    catalog (a species "Troll" must not get the monster troll's art).
    """
    out: dict[str, str] = {}
    for name in sorted(species_names):
        rel = species_relpath(name)
        if rel is None:
            continue
        uri = embed_relpath(rel, cache_dir)
        if uri:
            out[name] = uri
    return out


def is_unique_killer(catalog: Catalog | None, name: str,
                     slain_slugs: set[str]) -> bool:
    """Was the death caused by a named unique?

    True when the killer's tile lives in the uniques directory, or — for
    uniques with no current art — when the same monster appears in the
    career's slain-uniques list.
    """
    hit = catalog.lookup(name) if catalog else None
    if hit:
        return hit[1]
    return slug(name) in slain_slugs


# --------------------------------------------------------------------------
# God art (wrath deaths: "divine providence")
# --------------------------------------------------------------------------

#: Death-cause strings that mean the run ended in divine wrath rather than by
#: a monster.  The report shows the *worshipped god's* altar for these.
GOD_KILLER_CAUSES = ("divine providence",)

#: God (as written in morgues) -> dngn/altars file.  Animated altars have
#: numbered frames; the listed file is a stable frame.
_ALTAR_FILES = {
    "Ashenzari": "ashenzari", "Beogh": "beogh", "Cheibriados": "cheibriados",
    "Dithmenos": "dithmenos1", "Elyvilon": "elyvilon", "Fedhas": "fedhas",
    "Gozag": "gozag0", "Hepliaklqana": "hep0", "Ignis": "ignis",
    "Jiyva": "jiyva01", "Kikubaaqudgha": "kikubaaqudgha", "Lugonu": "lugonu",
    "Makhleb": "makhleb_flame1", "Nemelex Xobeh": "nemelex1",
    "Okawaru": "okawaru", "Pakellas": "pakellas0", "Qazlal": "qazlal0",
    "Ru": "ru", "Sif Muna": "sif_muna1", "the Shining One": "shining_one",
    "Trog": "trog", "Uskayaw": "uskayaw", "Vehumet": "vehumet1",
    "Wu Jian": "wu_jian", "Xom": "xom0", "Yredelemnul": "yredelemnul",
    "Zin": "zin1",
}


def altar_relpath(god: str) -> str | None:
    """dngn/altars tile for a god name, or None when there is no art."""
    stem = _ALTAR_FILES.get(god)
    if stem is None:
        stem = slug(god)  # gods not listed follow the file-naming convention
    return f"dngn/altars/{stem}.png"


# --------------------------------------------------------------------------
# Worn gear (character portraits)
# --------------------------------------------------------------------------
#
# DCSS draws a character from layered part tiles (species base, body armour,
# helm, weapon...).  Morgues do not record item colours, and several historic
# weapon types lost their part art, so the portrait is an approximation: the
# species body plus the canonical part for the body armour, helm and weapon
# that were equipped at death, when such a part exists.  All part pngs share
# one aligned 32×32 canvas, so layers can be stacked as-is.

#: weapon item phrases (lower-cased base name, longest first) -> hand1 part
_WEAPON_PARTS = (
    ("executioner's axe", "axe_executioner"), ("hand axe", "hand_axe"),
    ("war axe", "war_axe"), ("broad axe", "broad_axe"),
    ("battle axe", "battleaxe"), ("demon trident", "trident_demon"),
    ("demon whip", "randart_demon_whip"), ("demon blade", "demonblade"),
    ("triple sword", "triple_sword"), ("double sword", "double_sword"),
    ("great sword", "great_sword"), ("broad sword", "broadsword"),
    ("short sword", "short_sword"), ("quick blade", "quick_blade"),
    ("morning star", "morningstar"), ("evening star", "eveningstar"),
    ("quarterstaff", "quarterstaff"), ("triple crossbow", "triple_crossbow"),
    ("longbow", "bow"), ("shortbow", "shortbow"), ("arbalest", "arbalest"),
    ("giant club", "giant_club"), ("mace", "mace"), ("club", "club"),
    ("flail", "flail"), ("whip", "whip"), ("rapier", "rapier"),
    ("falchion", "falchion"), ("scimitar", "scimitar"),
    ("dagger", "dagger"), ("spear", "spear"), ("trident", "trident"),
    ("glaive", "glaive"), ("bardiche", "bardiche"), ("scythe", "scythe"),
    ("staff", "staff"),
)

#: body-armour item phrases -> player/body part (canonical look chosen where
#: the game randomises colours, e.g. robes)
_ARMOUR_PARTS = (
    ("crystal plate armour", "crystal_plate"), ("plate armour", "plate"),
    ("ring mail", "ringmail"), ("chain mail", "chainmail"),
    ("leather armour", "leather_armour"), ("animal skin", "animal_skin"),
    ("gold dragon armour", "dragonarm_golden"),
    ("pearl dragon armour", "dragonarm_pearl"),
    ("shadow dragon armour", "dragonarm_shadow"),
    ("quicksilver dragon armour", "dragonarm_quicksilver"),
    ("storm dragon armour", "dragonarm_blue"),
    ("ice dragon armour", "dragonarm_cyan"),
    ("fire dragon armour", "dragonarm_red"),
    ("swamp dragon armour", "dragonarm_yellow"),
    ("iron troll leather armour", "iron_troll_leather"),
    ("deep troll leather armour", "deep_troll_leather"),
    ("moon troll leather armour", "moon_troll_leather_armour"),
    ("troll leather armour", "iron_troll_leather"),
    ("robe", "robe_blue"),
)

#: helm item phrases -> player/head part
_HELM_PARTS = (
    ("helmet", "fhelm_gray3"), ("cap", "cap_blue"), ("hat", "hat_explorer"),
)


def _item_base(name: str) -> str:
    """'a +2 battleaxe of freezing' -> 'battleaxe' (roughly)."""
    n = name.lower()
    n = re.sub(r"^(?:an?|the|some)\s+", "", n)
    n = re.sub(r"^[+-]\d+\s+", "", n)
    n = re.sub(r"\s+\(.*?\)$", "", n)
    return n.split(" of ", 1)[0].strip()


def _match_part(base: str, table: tuple) -> str | None:
    for phrase, part in table:
        if phrase in base:
            return part
    return None


def gear_rels(game) -> list[str]:
    """rltiles part paths for the gear the character was wearing at death.

    Returns body-armour, helm and weapon parts (in back-to-front order); the
    species base is added by the caller.  Missing art falls out silently.
    """
    parts: list[str] = []
    armour_base = ""
    helm_base = ""
    weapon_base = ""
    for cat, items in getattr(game, "inventory", {}).items():
        for item in items:
            if not item.get("equipped") and cat not in ("Weapons", "Hand Weapons"):
                continue
            base = _item_base(str(item.get("name", "")))
            if not base:
                continue
            if cat in ("Armour",):
                hit = _match_part(base, _ARMOUR_PARTS)
                if hit and not armour_base:
                    armour_base = hit
                    continue
                hit = _match_part(base, _HELM_PARTS)
                if hit and not helm_base:
                    helm_base = hit
                    continue
            hit = _match_part(base, _WEAPON_PARTS)
            if hit and not weapon_base:
                weapon_base = hit
    if armour_base:
        parts.append(f"player/body/{armour_base}.png")
    if helm_base:
        parts.append(f"player/head/{helm_base}.png")
    if weapon_base:
        parts.append(f"player/hand1/{weapon_base}.png")
    return parts


# --------------------------------------------------------------------------
# Branch art (death-by-branch rows)
# --------------------------------------------------------------------------

#: Death-branch labels (as normalized by parse, including historic spellings)
#: -> dngn/gateways art.  Every named branch has its own entrance tile (the
#: staircase/portal that leads into it); anything else gets the plain
#: down-stairs icon.  A value containing "/" is a repo-relative path (orphan
#: art under UNUSED/); otherwise it names a file in dngn/gateways.  Animated
#: frames pick a stable one.
_BRANCH_ENTRANCES = {
    "dungeon": "enter",
    "lair": "enter_lair", "lair of beasts": "enter_lair",
    "orc": "enter_orc", "orcish mines": "enter_orc",
    "elf": "enter_elf", "elven halls": "enter_elf",
    "swamp": "enter_swamp", "shoals": "enter_shoals",
    "snake": "enter_snake", "snake pit": "enter_snake",
    "spider": "enter_spider", "slime": "enter_slime",
    "slime pits": "enter_slime", "pits of slime": "enter_slime",
    "crypt": "enter_crypt", "depths": "enter_depths",
    "vaults": "enter_vaults_open", "vault": "enter_vaults_open",
    "zot": "enter_zot_open", "realm of zot": "enter_zot_open",
    "tomb": "enter_tomb", "temple": "enter_temple",
    "ecumenical temple": "enter_temple",
    "abyss": "enter_abyss1", "pandemonium": "enter_pandemonium",
    "hell": "enter_hell1", "dis": "enter_dis1",
    "gehenna": "enter_gehenna1", "cocytus": "enter_cocytus1",
    "tartarus": "enter_tartarus1",
    # portal branches: their own portal art where it exists
    "bazaar": "bazaar_portal", "ossuary": "ossuary_portal",
    "ice cave": "ice_cave_portal", "bailey": "bailey_portal",
    # Hive (removed): art survives under UNUSED/features
    "hive": "UNUSED/features/hive_portal",
}


def branch_relpath(branch: str) -> str:
    """rltiles path for a death-branch name (stair image by default)."""
    stem = _BRANCH_ENTRANCES.get(str(branch).strip().lower(), "enter")
    if "/" in stem:
        return f"{stem}.png"
    return f"dngn/gateways/{stem}.png"
