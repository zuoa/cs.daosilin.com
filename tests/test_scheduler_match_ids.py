import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import ANY, patch

from database import MatchPlayer as DatabaseMatchPlayer
from scheduler import (_official_cup_matches, _store_match, canonical_match_id,
                       create_scheduler, reconcile_nightly_player_summaries,
                       refresh_perfect_ranks)


class MatchIdNormalizationTest(unittest.TestCase):
    def test_demo_reconciliation_runs_daily_at_0330(self):
        task_scheduler = create_scheduler()
        job = task_scheduler.get_job('demo_analysis_reconcile')

        self.assertEqual(str(job.trigger), "cron[hour='3', minute='30']")

    def test_live_status_cache_refresh_runs_every_five_minutes(self):
        task_scheduler = create_scheduler()
        job = task_scheduler.get_job('refresh_live_statuses')

        self.assertEqual(str(job.trigger), "cron[minute='*/5']")

    def test_player_summaries_wait_nightly_for_demo_completion(self):
        task_scheduler = create_scheduler()
        job = task_scheduler.get_job('player_summary_reconcile')

        self.assertEqual(str(job.trigger), "cron[hour='4-7', minute='*/10']")

    @patch('demo_tasks.demo_analysis_readiness')
    @patch('scheduler.Config')
    def test_nightly_player_summaries_do_not_run_before_demos_finish(
            self, config, readiness):
        config.get_value.return_value = None
        readiness.return_value = {
            'ready': False, 'disabled': False, 'eligible': 3, 'pending': 1,
        }

        with patch('player_summary_tasks.reconcile_player_summaries') as reconcile:
            result = reconcile_nightly_player_summaries()

        self.assertTrue(result['waiting_for_demo'])
        reconcile.assert_not_called()
        config.set_value.assert_not_called()

    @patch('demo_tasks.demo_analysis_readiness')
    @patch('scheduler.Config')
    def test_nightly_player_summaries_run_once_after_demos_finish(
            self, config, readiness):
        config.get_value.return_value = None
        readiness.return_value = {
            'ready': True, 'disabled': False, 'eligible': 3, 'pending': 0,
        }
        summary_result = {'eligible': 4, 'scheduled': 2, 'skipped': 2}

        with patch(
            'player_summary_tasks.reconcile_player_summaries',
            return_value=summary_result,
        ) as reconcile:
            result = reconcile_nightly_player_summaries(
                now=datetime(2026, 9, 10, 4, 20),
            )

        self.assertEqual(result['scheduled'], 2)
        reconcile.assert_called_once_with()
        config.set_value.assert_called_once_with(
            'player_summary_nightly_date', '2026-09-10',
        )

    def test_numeric_and_prefixed_ids_share_one_identity(self):
        self.assertEqual(canonical_match_id(9223339745715475470), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('9223339745715475470'), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('PVP@9223339745715475470'), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('pvp@9223339745715475470'), 'PVP@9223339745715475470')

    def test_non_pvp_match_ids_are_preserved(self):
        self.assertEqual(canonical_match_id('official-match-1'), 'official-match-1')
        self.assertEqual(canonical_match_id(None), '')

    def test_official_cup_matches_display_name_instead_of_url_slug(self):
        season = {
            'cup_name': 's2',
            'cup_alias': '鲨鱼 MAJOR S2',
            'name': '鲨鱼 MAJOR S2',
        }

        self.assertTrue(_official_cup_matches(season, '鲨鱼MAJOR S2'))
        self.assertFalse(_official_cup_matches(season, 's2'))

    def test_official_cup_display_name_falls_back_to_legacy_name(self):
        season = {
            'cup_name': 'legacy-s2',
            'cup_alias': None,
            'name': '鲨鱼 Major S2',
        }

        self.assertTrue(_official_cup_matches(season, '鲨鱼MAJOR S2'))

    @patch('scheduler.MatchPlayer')
    @patch('scheduler.Match')
    def test_store_uses_list_identity_when_detail_omits_prefix(self, match_model, match_player_model):
        match_model.get_by_match_id.return_value = None
        match_data = {
            'base': {
                'matchId': '9223339745715475470',
                'map': 'de_ancient',
                'mapEn': 'de_ancient',
                'score1': 5,
                'score2': 13,
            },
            'players': [],
        }

        with patch('demo_service.demo_analysis_enabled', return_value=True), \
                patch('demo_tasks.schedule_demo_analysis') as schedule_demo:
            stored_id = _store_match(
                match_data,
                assigned_cup_name='cs-practice-20260827',
                match_id='PVP@9223339745715475470',
            )

        self.assertEqual(stored_id, 'PVP@9223339745715475470')
        schedule_demo.assert_not_called()
        self.assertEqual(
            match_model.create.call_args.kwargs['match_id'],
            'PVP@9223339745715475470',
        )
        match_player_model.is_exist.assert_not_called()

    @patch('scheduler.Player')
    @patch('scheduler.MatchPlayer')
    @patch('scheduler.Match')
    def test_store_maps_non_demo_advanced_stats(
        self, match_model, match_player_model, player_model,
    ):
        match_model.get_by_match_id.return_value = None
        match_player_model.is_exist.return_value = False
        player_model.is_exist.return_value = True
        match_data = {
            'base': {
                'matchId': '123', 'map': 'de_mirage', 'mapEn': 'de_mirage',
                'score1': 13, 'score2': 8, 'winTeam': 1,
            },
            'players': [{
                'playerId': 'p1', 'nickName': 'One', 'team': 1,
                'tradeFragCount': 4, 'grenadeDamage': 37, 'infernoDamage': 52,
                'killMap': {'p2': 3},
            }],
        }

        _store_match(match_data, assigned_cup_name='season-one')

        saved = match_player_model.create.call_args.kwargs
        self.assertEqual(saved['trade_frag_count'], 4)
        self.assertEqual(saved['grenade_damage'], 37)
        self.assertEqual(saved['inferno_damage'], 52)
        self.assertEqual(saved['kill_map'], '{"p2": 3}')
        self.assertLessEqual(set(saved), set(DatabaseMatchPlayer._meta.fields))

    @patch('scheduler.load_demo_credential')
    @patch('scheduler.time.sleep')
    @patch('scheduler.clear_perfect_rank_cache')
    @patch('scheduler.Config')
    @patch('scheduler.get_perfect_rank')
    @patch('scheduler.resolve_steam_id64')
    @patch('scheduler.PlayerPerfectRankHistory')
    @patch('scheduler.Player')
    def test_refresh_perfect_ranks_persists_successful_lookup(
        self, player_model, rank_history_model, resolve_steam_id, get_rank,
        config_model, clear_cache, sleep, load_credential,
    ):
        player = SimpleNamespace(
            player_id='76561199039451434',
            steam_id=None,
            in_library=True,
        )
        player_model.select.return_value.order_by.return_value = [player]
        resolve_steam_id.return_value = player.player_id
        credential = {'steam_id': '76561198000000001', 'access_token': 'token'}
        load_credential.return_value = credential
        get_rank.return_value = {'score': 2401, 'level': 'S', 'stars': 18}

        stats = refresh_perfect_ranks()

        self.assertEqual(stats, {'total': 1, 'updated': 1, 'failed': 0, 'invalid': 0})
        player_model.update.assert_called_once()
        saved = player_model.update.call_args.kwargs
        self.assertEqual(saved['perfect_score'], 2401)
        self.assertEqual(saved['perfect_level'], 'S')
        self.assertEqual(saved['perfect_stars'], 18)
        self.assertIn('perfect_rank_updated_at', saved)
        rank_history_model.create.assert_called_once_with(
            player_id=player.player_id,
            score=2401,
            level='S',
            stars=18,
            sampled_at=saved['perfect_rank_updated_at'],
        )
        get_rank.assert_called_once_with(player.player_id, credential=credential)
        config_model.set_value.assert_any_call('perfect_rank_refresh_stats', ANY)
        clear_cache.assert_called_once_with()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
