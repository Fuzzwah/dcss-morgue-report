"""Download a player's morgue files from a DCSS server.

Fetches the morgue index page, finds every `morgue-<player>-*.txt` link,
and downloads any file not already present locally. Re-runnable for
incremental updates.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "dcss-morgue-report/1.0 (personal stats tool)"
_DELAY_SECONDS = 0.15

_TXT_RE = re.compile(r'href="(morgue-[^"]+\.txt)"')


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def list_morgue_urls(base_url: str, player: str) -> list[str]:
    """Return the full URLs of every morgue .txt on the server."""
    index_url = f"{base_url.rstrip('/')}/morgue/{player}/"
    html = _http_get(index_url).decode("utf-8", errors="replace")
    names = sorted(set(_TXT_RE.findall(html)))
    return [f"{index_url}{name}" for name in names]


def download_morgues(
    base_url: str,
    player: str,
    dest_dir: str | Path,
    *,
    force: bool = False,
) -> list[Path]:
    """Download all morgues for `player` into `dest_dir`.

    Returns the local paths of the morgue files (all that were found).
    Files already present are skipped unless `force` is set.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    urls = list_morgue_urls(base_url, player)
    local: list[Path] = []
    for url in urls:
        name = url.rsplit("/", 1)[-1]
        target = dest_dir / name
        if target.exists() and not force:
            local.append(target)
            continue
        for attempt in range(3):
            try:
                target.write_bytes(_http_get(url))
                break
            except urllib.error.URLError:
                if attempt == 2:
                    raise
                time.sleep(1.0)
        local.append(target)
        time.sleep(_DELAY_SECONDS)
    return local
