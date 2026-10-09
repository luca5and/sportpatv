import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build  # noqa: E402
from fetch_swedes import current_clubs  # noqa: E402


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


class TvStatusTest(unittest.TestCase):
    rights = {
        "SA": {"services": ["TV4 Play"], "coverage": "all", "source": "s"},
        "PL": {"services": ["Viaplay", "Prime Video"], "coverage": "split"},
        "CL": {"services": ["Viaplay"], "coverage": "unknown"},
    }

    def test_split_league_likely_once_round_exception_confirmed(self):
        rights = {"PL": {"services": ["Viaplay", "Prime Video"], "coverage": "split",
                         "default": "Viaplay", "per_round_exception": "Prime Video"}}
        conf = {"1": {"service": "Prime Video"}}
        matches = [
            {"id": "1", "competition": {"code": "PL"}, "matchday": 6},
            {"id": "2", "competition": {"code": "PL"}, "matchday": 6},
            {"id": "3", "competition": {"code": "PL"}, "matchday": 7},
        ]
        rounds = build.rounds_with_exception(matches, rights, conf)
        self.assertEqual(rounds, {("PL", 6)})
        same_round = build.tv_status("2", "PL", rights, conf, ("PL", 6) in rounds)
        self.assertEqual((same_round["status"], same_round["service"]), ("likely", "Viaplay"))
        self.assertEqual(build.tv_status("3", "PL", rights, conf, ("PL", 7) in rounds)["status"], "unknown")

    def test_confirmation_wins(self):
        tv = build.tv_status("1", "PL", self.rights, {"1": {"service": "Prime Video", "source": "u"}})
        self.assertEqual((tv["status"], tv["service"]), ("confirmed", "Prime Video"))

    def test_whole_league_on_one_service_is_likely(self):
        self.assertEqual(build.tv_status("2", "SA", self.rights, {})["status"], "likely")

    def test_split_or_unchecked_is_never_guessed(self):
        pl = build.tv_status("3", "PL", self.rights, {})
        self.assertEqual((pl["status"], pl["service"]), ("unknown", None))
        self.assertEqual(pl["note"], "Troligen Viaplay eller Prime Video")
        self.assertEqual(build.tv_status("4", "CL", self.rights, {})["status"], "unknown")
        self.assertEqual(build.tv_status("5", "XX", self.rights, {})["note"], None)


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
