"""Hämtar svenska fotbollsspelare och deras nuvarande klubb från Wikidata (CC0).

Skriver data/generated/swedes.json. Om Wikidata inte svarar behålls den
gamla filen, så sidan fortsätter fungera.

Två lätta frågor i stället för en tung (den tunga tog över 60 s och fick 504):
först spelare -> klubb-id, sedan alla namn för just de klubbarna.
"""
import json
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "swedes.json"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "sportpatv/0.1 (https://github.com/luca5and/sportpatv)"

# Svenska medborgare (Q34), fotbollsspelare (Q937857), män (Q6581097),
# födda efter 1984. Alla klubbtillhörigheter (P54) till en fotbollsklubb
# (Q476028), dvs. inte landslag, med start- och sluttid.
PLAYERS_QUERY = """
SELECT ?player ?playerSv ?playerEn ?club ?start ?end WHERE {
  ?player wdt:P27 wd:Q34;
          wdt:P106 wd:Q937857;
          wdt:P21 wd:Q6581097;
          wdt:P569 ?born.
  FILTER(?born > "1984-01-01T00:00:00Z"^^xsd:dateTime)
  ?player p:P54 ?st.
  ?st ps:P54 ?club.
  OPTIONAL { ?st pq:P580 ?start }
  OPTIONAL { ?st pq:P582 ?end }
  ?club wdt:P31 wd:Q476028.
  OPTIONAL { ?player rdfs:label ?playerSv FILTER(LANG(?playerSv) = "sv") }
  OPTIONAL { ?player rdfs:label ?playerEn FILTER(LANG(?playerEn) = "en") }
}
"""

CLUB_NAMES_QUERY = """
SELECT ?club ?name WHERE {
  VALUES ?club { %s }
  { ?club rdfs:label ?name } UNION { ?club skos:altLabel ?name }
  FILTER(LANG(?name) IN ("en", "sv"))
}
"""


def sparql(query, attempts=3):
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp)["results"]["bindings"]
        except Exception as exc:
            if attempt == attempts:
                raise
            print(f"Wikidata försök {attempt} misslyckades ({exc}), försöker igen", file=sys.stderr)
            time.sleep(10 * attempt)


# Alla fotbolls- och ishockeyspelare med svenskt medborgarskap (P27) eller som representerar
# Sverige (P1532) och har en artikel på svenska eller engelska Wikipedia.
# Oberoende av klubbdata, som ofta saknas i Wikidata.
ARTICLES_QUERY = """
SELECT ?player ?name ?article ?sport ?born WHERE {
  VALUES ?sport { wd:Q937857 wd:Q11774891 }  # fotbollsspelare, ishockeyspelare
  ?player wdt:P106 ?sport.
  { ?player wdt:P27 wd:Q34 } UNION { ?player wdt:P1532 wd:Q34 }
  ?article schema:about ?player; schema:isPartOf <https://%s.wikipedia.org/>.
  OPTIONAL { ?player wdt:P569 ?born }
  FILTER(!BOUND(?born) || ?born > "1980-01-01T00:00:00Z"^^xsd:dateTime)
  ?player rdfs:label ?name.
  FILTER(LANG(?name) IN ("sv", "en"))
}
"""


def val(row, key):
    return row[key]["value"] if key in row else None


def qid(uri):
    return uri.rsplit("/", 1)[-1]


def fetch_club_names(club_ids, chunk=200):
    names = {}
    ids = sorted(club_ids)
    for i in range(0, len(ids), chunk):
        values = " ".join("wd:" + c for c in ids[i:i + chunk])
        for row in sparql(CLUB_NAMES_QUERY % values):
            names.setdefault(qid(val(row, "club")), set()).add(val(row, "name"))
    return names


SPORTS = {"Q937857": "fotboll", "Q11774891": "ishockey"}


def name_key(name):
    s = unicodedata.normalize("NFKD", name.replace("-", " "))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def people_index(rows_by_lang):
    """Namn (gemener, utan accenter) -> [{id, url, sport, born}] för svenska
    spelare med Wikipedia-artikel, svensk artikel före engelsk. Används för
    spelarlänkar, och för att känna igen svenskar i NHL som är födda utomlands
    (då måste sport och födelsedag stämma)."""
    urls, names, sports, born = {}, {}, {}, {}
    for lang in ("en", "sv"):  # sv sist så att den vinner
        for row in rows_by_lang.get(lang, []):
            pid = qid(val(row, "player"))
            urls[pid] = val(row, "article")
            names.setdefault(pid, set()).add(val(row, "name"))
            sport = qid(val(row, "sport") or "")
            if sport:
                sports.setdefault(pid, set()).add(SPORTS.get(sport, sport))
            if val(row, "born"):
                born[pid] = val(row, "born")[:10]
    index = {}
    for pid, labels in names.items():
        for label in labels:
            entries = index.setdefault(name_key(label), [])
            if not any(e["id"] == pid for e in entries):
                entries.append({"id": pid, "url": urls[pid], "sports": sorted(sports.get(pid, [])),
                                "born": born.get(pid)})
    return index


def current_clubs(rows):
    """Wikidata har många gamla klubbar som ingen har stängt. Därför räknas
    bara klubben spelaren gick till senast: har den en sluttid har spelaren
    ingen känd klubb nu (slutat, eller nytt klubbyte saknas). Har ingen rad
    starttid godtas en öppen klubb bara om den är den enda.
    Returnerar [(spelar-id, namn, klubb-id)]."""
    by_player = {}
    for row in rows:
        by_player.setdefault(val(row, "player"), []).append(row)

    result = set()
    for pid, prow in by_player.items():
        dated = [r for r in prow if val(r, "start")]
        if dated:
            latest = max(val(r, "start") for r in dated)
            keep = [r for r in dated if val(r, "start") == latest and not val(r, "end")]
        else:
            open_rows = [r for r in prow if not val(r, "end")]
            keep = open_rows if len({val(r, "club") for r in open_rows}) == 1 else []
        for r in keep:
            name = val(r, "playerSv") or val(r, "playerEn") or qid(pid)
            result.add((qid(pid), name, qid(val(r, "club"))))
    return sorted(result)


def fetch_players():
    rows = sparql(PLAYERS_QUERY)
    picks = current_clubs(rows)
    club_names = fetch_club_names({club for _, _, club in picks})
    players = []
    for pid, name, club in picks:
        names = sorted(club_names.get(club, []))
        if names:
            players.append({"id": pid, "name": name, "club": names[0], "club_id": club, "club_names": names})
    return sorted(players, key=lambda p: (p["club"], p["name"]))


def main():
    """Spelare och Wikipedia-länkar hämtas var för sig; misslyckas en del
    behålls den delen från förra körningen."""
    try:
        old = json.loads(OUT.read_text())
    except (FileNotFoundError, ValueError):
        old = {}

    try:
        players = fetch_players()
    except Exception as exc:  # nätverksfel, timeout, ändrat format
        print(f"Wikidata (spelare) misslyckades, behåller gamla: {exc}", file=sys.stderr)
        players = old.get("players", [])

    try:
        people = people_index({lang: sparql(ARTICLES_QUERY % lang) for lang in ("sv", "en")})
    except Exception as exc:
        print(f"Wikidata (Wikipedia-länkar) misslyckades, behåller gamla: {exc}", file=sys.stderr)
        people = old.get("people", {})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"players": players, "people": people}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(players)} svenska spelare, {len(people)} namn med Wikipedia-länk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
