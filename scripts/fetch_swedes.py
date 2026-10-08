"""Hämtar svenska fotbollsspelare och deras nuvarande klubb från Wikidata (CC0).

Skriver data/generated/swedes.json. Om Wikidata inte svarar behålls den
gamla filen, så sidan fortsätter fungera.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "swedes.json"
ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "sportpatv/0.1 (https://github.com/luca5and/sportpatv)"

# Svenska medborgare (Q34), fotbollsspelare (Q937857), män (Q6581097),
# födda efter 1984 och levande. Klubbtillhörighet (P54) utan sluttid (P582)
# till en fotbollsklubb (Q476028), dvs. inte landslag.
QUERY = """
SELECT ?player ?playerSv ?playerEn ?club ?clubLabelEn ?clubLabelSv ?start
       (GROUP_CONCAT(DISTINCT ?alias; separator="|") AS ?aliases)
WHERE {
  ?player wdt:P27 wd:Q34;
          wdt:P106 wd:Q937857;
          wdt:P21 wd:Q6581097;
          wdt:P569 ?born.
  FILTER(?born > "1984-01-01T00:00:00Z"^^xsd:dateTime)
  FILTER NOT EXISTS { ?player wdt:P570 [] }
  ?player p:P54 ?st.
  ?st ps:P54 ?club.
  FILTER NOT EXISTS { ?st pq:P582 [] }
  OPTIONAL { ?st pq:P580 ?start }
  ?club wdt:P31 wd:Q476028.
  OPTIONAL { ?club rdfs:label ?clubLabelEn FILTER(LANG(?clubLabelEn) = "en") }
  OPTIONAL { ?club rdfs:label ?clubLabelSv FILTER(LANG(?clubLabelSv) = "sv") }
  OPTIONAL { ?club skos:altLabel ?alias FILTER(LANG(?alias) IN ("en", "sv")) }
  OPTIONAL { ?player rdfs:label ?playerSv FILTER(LANG(?playerSv) = "sv") }
  OPTIONAL { ?player rdfs:label ?playerEn FILTER(LANG(?playerEn) = "en") }
}
GROUP BY ?player ?playerSv ?playerEn ?club ?clubLabelEn ?clubLabelSv ?start
"""


def fetch():
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": QUERY, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["results"]["bindings"]


def val(row, key):
    return row[key]["value"] if key in row else None


def current_clubs(rows):
    """En spelare kan ha flera öppna klubbrader i Wikidata (gamla som ingen
    stängt). Behåll bara raden med senast starttid; saknas starttid helt
    behålls alla."""
    by_player = {}
    for row in rows:
        by_player.setdefault(val(row, "player"), []).append(row)

    players = []
    for pid, prow in by_player.items():
        dated = [r for r in prow if val(r, "start")]
        keep = [max(dated, key=lambda r: val(r, "start"))] if dated else prow
        for r in keep:
            names = {val(r, "clubLabelEn"), val(r, "clubLabelSv")}
            names.update((val(r, "aliases") or "").split("|"))
            players.append({
                "id": pid.rsplit("/", 1)[-1],
                "name": val(r, "playerSv") or val(r, "playerEn") or pid.rsplit("/", 1)[-1],
                "club": val(r, "clubLabelSv") or val(r, "clubLabelEn"),
                "club_names": sorted(n for n in names if n),
            })
    return sorted(players, key=lambda p: (p["club"] or "", p["name"]))


def main():
    try:
        rows = fetch()
    except Exception as exc:  # nätverksfel, timeout, ändrat format
        print(f"Wikidata misslyckades, behåller gammal fil: {exc}", file=sys.stderr)
        return 0
    players = current_clubs(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"players": players}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(players)} svenska spelare sparade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
