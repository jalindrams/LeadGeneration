"""
S5 - Newly registered domains (free daily list from whoisds.com). Keeps names
with shop/brand keywords; the qualifier then drops non-stores and non-India.
Tier C filler: new stores with no shipping partner locked in yet.
"""
import base64
import io
import re
import zipfile
from datetime import date, timedelta

import requests

SOURCE = "new_domains"
KEYWORDS = re.compile(
    r"(shop|store|mart|kart|cart|bazaar|bazar|fashion|wear|attire|kurti|saree|ethnic|jewel|"
    r"organic|ayurved|herbal|naturals|beauty|cosmetic|skin|candle|decor|craft|handloom|"
    r"spice|masala|foods|snack|tea|coffee|pet|toys|kids|baby|gift|footwear|bags|leather)", re.I)
URL = "https://www.whoisds.com/whois-database/newly-registered-domains/{token}/nrd"


def _download(day: date) -> list[str]:
    token = base64.b64encode(f"{day.isoformat()}.zip".encode()).decode()
    r = requests.get(URL.format(token=token), timeout=120,
                     headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200 or not r.content.startswith(b"PK"):
        raise RuntimeError(f"whoisds list for {day} unavailable (HTTP {r.status_code})")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return z.read(z.namelist()[0]).decode(errors="ignore").split()


def discover(db, limit: int = 800, source: str = SOURCE) -> list[dict]:
    for back in (1, 2, 3):
        try:
            doms = _download(date.today() - timedelta(days=back))
            break
        except RuntimeError:
            doms = []
    picks = [d.lower() for d in doms
             if d.lower().endswith((".in", ".co.in", ".com", ".store", ".shop")) and KEYWORDS.search(d)]
    # .in first: far more likely to be Indian
    picks.sort(key=lambda d: 0 if d.endswith((".in", ".co.in")) else 1)
    return [{"domain": d, "source_ref": "whoisds newly registered"} for d in picks[:limit]]
