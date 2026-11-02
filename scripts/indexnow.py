"""Berättar för IndexNow (Bing, DuckDuckGo, Ecosia, Yandex m.fl.) vilka sidor som ändrats.

Läser data/generated/changed-urls.txt som render.py skriver: bara sidor vars innehåll
faktiskt ändrats sedan förra körningen. Nyckeln ligger i data/site.json och i
docs/<nyckel>.txt. Ett fel här ska aldrig stoppa nattens uppdatering.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = json.loads((ROOT / "data" / "site.json").read_text())
CHANGED_FILE = ROOT / "data" / "generated" / "changed-urls.txt"
FIRST_DONE = ROOT / "data" / "generated" / "indexnow-all-sent.txt"
SITEMAP = ROOT / "docs" / "sitemap.xml"
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS = 10000


def payload(urls, site=SITE):
    base = site["base_url"].rstrip("/")
    key = site["indexnow_key"]
    return {"host": urlparse(base).netloc, "key": key, "keyLocation": f"{base}/{key}.txt",
            "urlList": urls[:MAX_URLS]}


def main():
    key = SITE.get("indexnow_key")
    if not key or "github.io" in SITE["base_url"]:
        print("IndexNow: ingen egen domän eller nyckel, hoppar över")
        return 0
    if not (ROOT / "docs" / f"{key}.txt").exists():
        print("IndexNow: nyckelfilen saknas i docs/, hoppar över")
        return 0
    try:
        urls = [u for u in CHANGED_FILE.read_text().split() if u]
    except FileNotFoundError:
        urls = []
    first = not FIRST_DONE.exists()
    if first:  # första gången: skicka hela sitemap så att Bing lär sig alla sidor
        urls = re.findall(r"<loc>([^<]+)</loc>", SITEMAP.read_text())
    if not urls:
        print("IndexNow: inga ändrade sidor")
        return 0
    body = json.dumps(payload(urls)).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          # Pythons standard-User-Agent blockeras (403)
                                          "User-Agent": f"patv.se IndexNow (+{SITE['base_url']})"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"IndexNow: skickade {len(urls)} adresser, svar {resp.status}")
        if first:
            FIRST_DONE.write_text("Hela sitemap skickad till IndexNow en gång.\n")
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace").strip()
        print(f"IndexNow: svar {e.code} {e.reason} {detail} – försöker igen nästa natt")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"IndexNow: kunde inte nå tjänsten ({e}) – försöker igen nästa natt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
