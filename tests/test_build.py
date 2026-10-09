import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build  # noqa: E402
from fetch_swedes import current_clubs, people_index  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_strips_club_suffixes_and_accents(self):
        self.assertEqual(build.normalize("Arsenal F.C."), "arsenal")
        self.assertEqual(build.normalize("Arsenal FC"), "arsenal")
        self.assertEqual(build.normalize("1. FC Köln"), "koln")
        self.assertEqual(build.normalize("Brighton & Hove Albion FC"), "brighton")
        self.assertEqual(build.normalize("Brighton & Hove Albion F.C."), "brighton")

    def test_keeps_distinguishing_words(self):
        self.assertNotEqual(build.normalize("Manchester United FC"), build.normalize("Manchester City FC"))


class MatchingTest(unittest.TestCase):
    players = [
        {"name": "Viktor Gyökeres", "club": "Arsenal FC", "club_names": ["Arsenal F.C.", "Arsenal", "The Gunners"]},
        {"name": "Alexander Isak", "club": "Liverpool FC", "club_names": ["Liverpool F.C.", "Liverpool"]},
        {"name": "Gammal Spelare", "club": "Arsenal FC", "club_names": ["Arsenal F.C."]},
    ]

    def test_finds_swedes_by_full_name_or_short_name(self):
        manual = {"remove": ["Gammal Spelare"]}
        index = build.build_club_index(self.players, manual)
        found = build.swedes_in({"name": "Arsenal FC", "shortName": "Arsenal"}, index, manual, {})
        self.assertEqual([s["name"] for s in found], ["Viktor Gyökeres"])

    def test_no_swedes_for_other_club(self):
        index = build.build_club_index(self.players, {})
        self.assertEqual(build.swedes_in({"name": "Chelsea FC", "shortName": "Chelsea"}, index, {}, {}), [])

    def test_alias_file_and_manual_add(self):
        manual = {"add": [{"name": "Ny Svensk", "team": "Wolverhampton Wanderers FC"}]}
        aliases = {"Liverpool FC": ["The Reds"]}
        players = [{"name": "X", "club": "", "club_names": ["The Reds"]}]
        index = build.build_club_index(players, manual)
        self.assertEqual(build.swedes_in({"name": "Liverpool FC", "shortName": "Liverpool"}, index, manual, aliases)[0]["name"], "X")
        self.assertEqual(build.swedes_in({"name": "Wolverhampton Wanderers FC", "shortName": "Wolves"}, index, manual, {})[0]["name"], "Ny Svensk")


class SquadTest(unittest.TestCase):
    squads = {"57": {"players": [
        {"name": "Viktor Gyökeres", "nationality": "Sweden"},
        {"name": "Dubbel Medborgare", "nationality": "Turkey"},
        {"name": "Bukayo Saka", "nationality": "England"},
    ]}}
    team = {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal"}

    def test_squad_replaces_stale_wikidata(self):
        players = [
            {"name": "Gammal Spelare", "club_names": ["Arsenal F.C."]},  # inte i truppen
            {"name": "Dubbel Medborgare", "club_names": ["Arsenal F.C."]},
        ]
        index = build.build_club_index(players, {})
        found = build.swedes_in(self.team, index, {}, {}, self.squads)
        self.assertEqual([s["name"] for s in found], ["Dubbel Medborgare", "Viktor Gyökeres"])

    def test_falls_back_to_wikidata_without_squad(self):
        index = build.build_club_index([{"name": "X", "club_names": ["Arsenal"]}], {})
        found = build.swedes_in({"id": 99, "name": "Arsenal FC"}, index, {}, {}, self.squads)
        self.assertEqual([s["name"] for s in found], ["X"])

    def test_manual_remove_applies_to_squad(self):
        found = build.swedes_in(self.team, {}, {"remove": ["Viktor Gyökeres"]}, {}, self.squads)
        self.assertEqual(found, [])


class ProfileUrlTest(unittest.TestCase):
    people = {
        "viktor gyokeres": [{"id": "Q1", "url": "https://sv.wikipedia.org/wiki/Viktor_Gy%C3%B6keres"}],
        "viktor johansson": [{"id": "Q2", "url": "https://sv.wikipedia.org/wiki/A"},
                             {"id": "Q3", "url": "https://sv.wikipedia.org/wiki/B"}],
    }
    players_by_id = {"Q3": {"club_names": ["Stoke City F.C."]}}
    stoke = {"name": "Stoke City FC", "shortName": "Stoke"}

    def test_unique_name_gets_link(self):
        url = build.profile_url("Viktor Gyökeres", {"name": "Arsenal FC"}, self.people, {}, {})
        self.assertIn("Gy%C3%B6keres", url)

    def test_hyphen_and_space_are_the_same_name(self):
        people = {"victor nilsson lindelof": [{"id": "Q9", "url": "u"}]}
        self.assertEqual(build.profile_url("Victor Nilsson-Lindelöf", {"name": "Aston Villa FC"}, people, {}, {}), "u")

    def test_shared_name_resolved_by_club(self):
        self.assertTrue(build.profile_url("Viktor Johansson", self.stoke, self.people, self.players_by_id, {}).endswith("/B"))

    def test_shared_name_without_club_match_gets_no_link(self):
        self.assertIsNone(build.profile_url("Viktor Johansson", {"name": "Hull City AFC"}, self.people, self.players_by_id, {}))
        self.assertIsNone(build.profile_url("Okänd Spelare", self.stoke, self.people, {}, {}))


class PeopleIndexTest(unittest.TestCase):
    def row(self, pid, name, article):
        return {"player": {"value": "http://www.wikidata.org/entity/" + pid},
                "name": {"value": name}, "article": {"value": article}}

    def test_swedish_article_preferred_and_names_normalized(self):
        index = people_index({
            "en": [self.row("Q1", "Alieu Njie", "https://en.wikipedia.org/wiki/Alieu_Njie")],
            "sv": [self.row("Q1", "Alieu Njie", "https://sv.wikipedia.org/wiki/Alieu_Njie")],
        })
        self.assertEqual(index["alieu njie"], [{"id": "Q1", "url": "https://sv.wikipedia.org/wiki/Alieu_Njie"}])

    def test_english_only_player_still_linked(self):
        index = people_index({"en": [self.row("Q2", "Armin Ćulum", "https://en.wikipedia.org/wiki/Armin_%C4%86ulum")]})
        self.assertIn("armin culum", index)


class NhlTest(unittest.TestCase):
    def test_parse_and_build(self):
        import fetch_nhl
        schedule = {"gameWeek": [{"games": [
            {"id": 2026020050, "startTimeUTC": "2099-10-10T23:00:00Z", "gameState": "FUT", "gameType": 2,
             "homeTeam": {"abbrev": "TOR", "placeName": {"default": "Toronto"}, "commonName": {"default": "Maple Leafs"}},
             "awayTeam": {"abbrev": "DET", "placeName": {"default": "Detroit"}, "commonName": {"default": "Red Wings"}}},
            {"id": 2026020051, "startTimeUTC": "2099-10-10T23:00:00Z", "gameState": "FUT", "gameType": 2,
             "homeTeam": {"abbrev": "BOS"}, "awayTeam": {"abbrev": "NYR"}},
        ]}]}
        games = fetch_nhl.parse_schedule(schedule)
        self.assertEqual(games[0]["home"]["name"], "Toronto Maple Leafs")
        roster = {"forwards": [{"firstName": {"default": "William"}, "lastName": {"default": "Nylander"}, "birthCountry": "SWE"},
                               {"firstName": {"default": "Auston"}, "lastName": {"default": "Matthews"}, "birthCountry": "USA"}]}
        self.assertEqual(fetch_nhl.parse_roster(roster), ["William Nylander"])
        twins = {"forwards": [{"firstName": {"default": "Elias"}, "lastName": {"default": "Pettersson"}, "birthCountry": "SWE", "sweaterNumber": 40}],
                 "defensemen": [{"firstName": {"default": "Elias"}, "lastName": {"default": "Pettersson"}, "birthCountry": "SWE", "sweaterNumber": 25}]}
        self.assertEqual(fetch_nhl.parse_roster(twins), ["Elias Pettersson #25", "Elias Pettersson #40"])
        people = {"william nylander": [{"id": "Q1", "url": "https://sv.wikipedia.org/wiki/William_Nylander"}]}
        rights = {"NHL": {"services": ["Viaplay", "Disney+"], "coverage": "split"}}
        events = build.nhl_events({"games": games, "swedes": {"TOR": ["William Nylander"]}}, rights, {}, people)
        self.assertEqual(len(events), 1)  # BOS–NYR saknar svenskar
        e = events[0]
        self.assertEqual((e["id"], e["sport"], e["title"]), ("nhl-2026020050", "Ishockey", "Toronto Maple Leafs – Detroit Red Wings"))
        self.assertEqual(e["swedes"][0]["url"], "https://sv.wikipedia.org/wiki/William_Nylander")
        self.assertEqual(e["swedes"][0]["team"], "Maple Leafs")
        removed = build.nhl_events({"games": games, "swedes": {"TOR": ["William Nylander"]}}, rights, {}, people, {"William Nylander"})
        self.assertEqual(removed, [])
        self.assertEqual((e["tv"]["status"], e["tv"]["note"]), ("unknown", "Troligen Viaplay eller Disney+"))


class TvStatusTest(unittest.TestCase):
    rights = {
        "SA": {"services": ["TV4 Play"], "coverage": "all", "source": "s"},
        "PL": {"services": ["Viaplay", "Prime Video"], "coverage": "split",
               "default": "Viaplay", "per_round_exception": "Prime Video"},
        "PPL": {"services": ["TV4 Play"], "coverage": "selected", "per_round": 3},
        "CL": {"services": ["Viaplay"], "coverage": "unknown"},
    }

    def test_confirmation_wins(self):
        tv = build.tv_status("1", "PL", self.rights, {"1": {"service": "Prime Video", "source": "u"}})
        self.assertEqual((tv["status"], tv["service"]), ("confirmed", "Prime Video"))

    def test_single_source_confirmation_is_likely(self):
        tv = build.tv_status("1", "NHL", self.rights, {"1": {"service": "Disney+", "single_source": True}})
        self.assertEqual((tv["status"], tv["service"]), ("likely", "Disney+"))

    def test_split_default_until_exceptions_known(self):
        rights = {"NHL": {"services": ["Viaplay", "Disney+"], "coverage": "split",
                          "default": "Viaplay", "exceptions_known_until": "2026-10-31"}}
        inside = build.tv_status("2", "NHL", rights, {}, start="2026-10-20T23:00:00Z")
        self.assertEqual((inside["status"], inside["service"]), ("likely", "Viaplay"))
        self.assertEqual(build.tv_status("3", "NHL", rights, {}, start="2026-11-02T23:00:00Z")["status"], "unknown")

    def test_confirmed_not_broadcast(self):
        self.assertEqual(build.tv_status("1", "PPL", self.rights, {"1": {"service": None}})["status"], "none")

    def test_whole_league_on_one_service_is_confirmed(self):
        tv = build.tv_status("2", "SA", self.rights, {})
        self.assertEqual((tv["status"], tv["service"]), ("confirmed", "TV4 Play"))

    def test_unchecked_is_never_guessed(self):
        pl = build.tv_status("3", "PL", self.rights, {})
        self.assertEqual((pl["status"], pl["service"], pl["note"]), ("unknown", None, "Troligen Viaplay eller Prime Video"))
        self.assertEqual(build.tv_status("4", "CL", self.rights, {})["status"], "unknown")
        self.assertIsNone(build.tv_status("5", "XX", self.rights, {})["note"])

    def test_split_league_likely_once_round_exception_confirmed(self):
        conf = {"1": {"service": "Prime Video"}}
        matches = [
            {"id": "1", "competition": {"code": "PL"}, "matchday": 6},
            {"id": "2", "competition": {"code": "PL"}, "matchday": 6},
            {"id": "3", "competition": {"code": "PL"}, "matchday": 7},
        ]
        counts = build.round_counts(matches, self.rights, conf)
        self.assertEqual(counts, {("PL", 6): 1})
        same = build.tv_status("2", "PL", self.rights, conf, counts.get(("PL", 6), 0))
        self.assertEqual((same["status"], same["service"]), ("likely", "Viaplay"))
        self.assertEqual(build.tv_status("3", "PL", self.rights, conf, counts.get(("PL", 7), 0))["status"], "unknown")

    def test_selected_league_rest_not_shown_once_round_is_known(self):
        conf = {str(i): {"service": "TV4 Play"} for i in (1, 2)}
        matches = [{"id": str(i), "competition": {"code": "PPL"}, "matchday": 8} for i in range(1, 6)]
        two = build.round_counts(matches, self.rights, conf)[("PPL", 8)]
        tv = build.tv_status("5", "PPL", self.rights, conf, two)
        self.assertEqual((tv["status"], tv["note"]), ("unknown", "TV4 Play visar 3 utvalda matcher per omgång"))
        conf["3"] = {"service": "TV4 Play"}
        three = build.round_counts(matches, self.rights, conf)[("PPL", 8)]
        self.assertEqual(build.tv_status("5", "PPL", self.rights, conf, three)["status"], "none")


class CurrentClubTest(unittest.TestCase):
    def row(self, club, start=None, end=None):
        r = {"player": {"value": "http://www.wikidata.org/entity/Q1"}, "playerSv": {"value": "P"},
             "club": {"value": "http://www.wikidata.org/entity/" + club}}
        if start:
            r["start"] = {"value": start}
        if end:
            r["end"] = {"value": end}
        return r

    def test_latest_club_wins_over_old_unclosed_club(self):
        rows = [self.row("Q1", "2010-01-01T00:00:00Z"), self.row("Q2", "2025-07-01T00:00:00Z")]
        self.assertEqual(current_clubs(rows), [("Q1", "P", "Q2")])

    def test_player_whose_latest_club_ended_has_no_club(self):
        rows = [self.row("Q1", "2011-01-01T00:00:00Z"), self.row("Q2", "2022-01-01T00:00:00Z", "2023-12-31T00:00:00Z")]
        self.assertEqual(current_clubs(rows), [])

    def test_undated_open_club_only_if_single(self):
        self.assertEqual(current_clubs([self.row("Q5"), self.row("Q6", end="2020-01-01T00:00:00Z")]), [("Q1", "P", "Q5")])
        self.assertEqual(current_clubs([self.row("Q5"), self.row("Q6")]), [])


if __name__ == "__main__":
    unittest.main()
