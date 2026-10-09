# Sport på TV

En reklamfri sida som visar var du kan se svenska idrottare på TV. Första fliken
är **Svenskar på TV**: fotbollsmatcher där en svensk spelare finns i truppen,
med vilken tjänst som sänder matchen.

## Så fungerar det

| Del | Källa | Fil |
|---|---|---|
| Svenska spelare och deras klubbar | Wikidata (CC0, fri att använda) | `scripts/fetch_swedes.py` |
| Matcher kommande 7 dagar | football-data.org, gratisnivån | `scripts/fetch_matches.py` |
| Aktuella fotbollstrupper | football-data.org, gratisnivån | `scripts/fetch_squads.py` |
| NHL-matcher och trupper | NHL:s publika API | `scripts/fetch_nhl.py` |
| TV-rättigheter per turnering | Egen tabell | `data/broadcasters.json` |
| Bekräftade sändningar per match | Egen lista | `data/confirmations.json` |
| Övrig sport (NHL, landslaget, skidor m.m.) | Egen lista | `data/manual_events.json` |
| Rättelser av spelare och klubbnamn | Egen lista | `data/players_manual.json` |

`scripts/build.py` slår ihop allt till `docs/data/swedes-on-tv.json`.
`scripts/render.py` skriver sedan de statiska sidorna som Google läser:
startsidan (`docs/index.html`, från mallen `templates/index.html` – ändra i
mallen, inte i docs), en sida per spelare (`docs/spelare/`) och lag
(`docs/lag/`), samt `sitemap.xml` och `robots.txt`. Sidans adress och
Buy Me a Coffee-länken står i `data/site.json`. En GitHub Action
(`.github/workflows/update-data.yml`) kör allt varje natt och sparar resultatet.

### TV-märkningar – vi gissar aldrig

- **Bekräftad** (grön): matchen är hittad i kanalens egen tablå, länk sparad.
- **Bör sändas** (gul): turneringen sänds i sin helhet hos en enda tjänst.
- **Ej bekräftat** (grå): allt annat, t.ex. Premier League som delas mellan
  Viaplay och Prime Video.

## Kom igång

1. Skaffa en gratis nyckel på <https://www.football-data.org/client/register>.
2. Lägg in den i GitHub: *Settings → Secrets and variables → Actions → New
   repository secret*, namn `FOOTBALL_DATA_TOKEN`.
3. Kör *Actions → Uppdatera data → Run workflow* (schemat kör bara på `main`).
4. Publicera mappen `docs/`:
   - **Cloudflare Pages** (gratis, fungerar med privat repo, tillåter reklam):
     koppla repot, build command tomt, output directory `docs`.
   - **GitHub Pages** (gratis bara för publika repon): *Settings → Pages →
     Deploy from branch → main → /docs*.

## Lokalt

```sh
python3 -m unittest discover -s tests
python3 scripts/fetch_swedes.py
FOOTBALL_DATA_TOKEN=... python3 scripts/fetch_matches.py
python3 scripts/build.py
python3 scripts/render.py
python3 -m http.server -d docs 8000
```

## Viktigt

- TV-tabellen måste kontrolleras inför varje säsong; sätt `verified` till datumet.
- Kopiera aldrig tablåer från andra TV-guider. Bekräfta matcher hos kanalen själv.
- Wikidata kan ha gamla klubbyten; rätta i `data/players_manual.json`.
