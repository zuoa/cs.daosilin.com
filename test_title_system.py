import unittest

from title_system import RefactoredTitleSystem


def player(player_id, **overrides):
    data = {
        "player_id": player_id,
        "match_count": 10,
        "avg_pw_rating": 1.0,
        "avg_adpr": 70,
        "win_rate": .5,
        "kd_ratio": 1.0,
        "avg_headshot_ratio": .4,
        "total_kills": 100,
        "total_deaths": 100,
        "total_first_kills": 10,
        "total_first_deaths": 10,
        "fk_fd_ratio": 1.0,
        "total_assists": 30,
        "total_snipe_num": 0,
        "total_throws_count": 0,
        "match_mvp_count": 0,
        "total_1v2": 0,
        "total_1v3": 0,
        "total_1v4": 0,
        "total_1v5": 0,
        "total_2k": 0,
        "total_3k": 0,
        "total_4k": 0,
        "total_5k": 0,
    }
    data.update(overrides)
    return data


class TitleSystemTest(unittest.TestCase):
    def setUp(self):
        self.system = RefactoredTitleSystem()

    def test_small_sample_is_not_ranked_with_full_season_players(self):
        players = [player(str(index), avg_pw_rating=1 + index / 100) for index in range(9)]
        cameo = player("cameo", match_count=2, avg_pw_rating=3.0)
        players.append(cameo)

        self.assertEqual([], self.system.get_best_titles(cameo, all_players_data=players))

    def test_zero_utility_data_never_awards_utility_title(self):
        players = [player(str(index), avg_pw_rating=1 + index / 100) for index in range(10)]

        for data in players:
            names = [title.name for title in self.system.get_best_titles(data, all_players_data=players)]
            self.assertNotIn("道具调度员", names)

    def test_rate_metrics_are_not_biased_by_total_matches(self):
        efficient = player(
            "efficient",
            match_count=5,
            total_first_kills=20,
            total_first_deaths=10,
            fk_fd_ratio=2.0,
        )
        volume = player(
            "volume",
            match_count=10,
            total_first_kills=15,
            total_first_deaths=20,
            fk_fd_ratio=1.5,
        )
        challenger = player("challenger", total_first_kills=25)
        players = [efficient, volume, challenger]
        players.extend(player(str(index), total_first_kills=5) for index in range(7))

        efficient_names = [title.name for title in self.system.get_best_titles(efficient, all_players_data=players)]
        volume_names = [title.name for title in self.system.get_best_titles(volume, all_players_data=players)]

        self.assertIn("破局先锋", efficient_names)
        self.assertNotIn("破局先锋", volume_names)

    def test_titles_are_scarce_unique_and_explainable(self):
        star = player(
            "star",
            avg_pw_rating=2.0,
            avg_adpr=140,
            kd_ratio=2.0,
            total_first_kills=50,
            total_first_deaths=20,
            fk_fd_ratio=2.5,
            match_mvp_count=6,
            total_1v4=2,
            total_5k=1,
        )
        players = [star]
        players.extend(player(str(index), avg_pw_rating=.8 + index / 100) for index in range(9))

        titles = self.system.get_best_titles(star, all_players_data=players)

        self.assertLessEqual(len(titles), 3)
        self.assertEqual(len(titles), len({title.slot for title in titles}))
        self.assertEqual("赛季标杆", titles[0].name)
        self.assertIn("#1/10", titles[0].description)


if __name__ == "__main__":
    unittest.main()
