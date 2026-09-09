import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from peewee import SqliteDatabase

from database import FeedbackSubmission
from feedback_service import (FeedbackError, feedback_inbox,
                              get_public_feedback, normalize_feedback,
                              public_feedback_payload, submit_feedback,
                              update_feedback)


def suggestion(subject='烟雾弹建筑师', content='表彰最会用烟雾切割战场的人。'):
    return {
        'type': 'award_suggestion',
        'subject': subject,
        'content': content,
        'submitter_name': '水友A',
        'context': {'type': 'season', 'id': 'test-cup', 'label': '测试赛季'},
        'details': {'method': '统计有效烟覆盖回合'},
        'source_path': '/test-cup/honours?ignored=1',
    }


class FeedbackServiceTest(unittest.TestCase):
    def setUp(self):
        self.database = SqliteDatabase(':memory:')
        self.binding = self.database.bind_ctx([FeedbackSubmission])
        self.binding.__enter__()
        self.database.create_tables([FeedbackSubmission])

    def tearDown(self):
        self.database.drop_tables([FeedbackSubmission])
        self.binding.__exit__(None, None, None)
        self.database.close()

    def test_normalize_feedback_uses_generic_contract(self):
        result = normalize_feedback(suggestion())

        self.assertEqual(result['feedback_type'], 'award_suggestion')
        self.assertEqual(result['context_type'], 'season')
        self.assertEqual(result['context_id'], 'test-cup')
        self.assertEqual(result['source_path'], '/test-cup/honours')

    def test_unknown_type_and_mismatched_context_are_rejected(self):
        data = suggestion()
        data['type'] = 'anything'
        with self.assertRaisesRegex(FeedbackError, '暂不支持'):
            normalize_feedback(data)

        data = suggestion()
        data['context']['type'] = 'player'
        with self.assertRaisesRegex(FeedbackError, '上下文'):
            normalize_feedback(data)

    def test_duplicate_is_returned_without_creating_another_row(self):
        now = datetime(2026, 9, 9, 12, 0)
        first, duplicate = submit_feedback(suggestion(), 'visitor-a', now=now)
        repeated, repeated_duplicate = submit_feedback(
            suggestion(), 'visitor-a', now=now + timedelta(minutes=2),
        )

        self.assertFalse(duplicate)
        self.assertTrue(repeated_duplicate)
        self.assertEqual(first.public_id, repeated.public_id)
        self.assertEqual(FeedbackSubmission.select().count(), 1)

    def test_hourly_limit_allows_five_distinct_submissions(self):
        now = datetime(2026, 9, 9, 12, 0)
        for index in range(5):
            submit_feedback(suggestion(subject=f'奖项 {index}'), 'visitor-a', now=now)

        with self.assertRaises(FeedbackError) as raised:
            submit_feedback(suggestion(subject='第六项'), 'visitor-a', now=now)
        self.assertEqual(raised.exception.status_code, 429)

    def test_admin_reply_is_visible_only_to_owning_fingerprint(self):
        row, _ = submit_feedback(suggestion(), 'visitor-a')
        updated = update_feedback(
            row.public_id, {'reply': '这个想法已进入下一版候选。'}, 'admin',
        )

        self.assertEqual(updated.status, 'replied')
        self.assertEqual(updated.replied_by, 'admin')
        self.assertIsNone(get_public_feedback(row.public_id, 'visitor-b'))
        public = public_feedback_payload(get_public_feedback(row.public_id, 'visitor-a'))
        self.assertEqual(public['reply'], '这个想法已进入下一版候选。')

    def test_admin_inbox_filters_and_returns_counts(self):
        first, _ = submit_feedback(suggestion(subject='奖项 A'), 'visitor-a')
        submit_feedback(suggestion(subject='奖项 B'), 'visitor-b')
        update_feedback(first.public_id, {'status': 'reviewing'}, 'admin')

        result = feedback_inbox(status='reviewing')

        self.assertEqual(result['total'], 1)
        self.assertEqual(result['items'][0]['subject'], '奖项 A')
        self.assertEqual(result['counts']['reviewing'], 1)
        self.assertEqual(result['counts']['new'], 1)

    @patch('app.current_admin', return_value='tester')
    def test_public_submit_admin_reply_and_owner_read_api(self, _current_admin):
        from app import app

        app.config['TESTING'] = True
        client = app.test_client()
        response = client.post('/api/v1/feedback', json=suggestion())
        self.assertEqual(response.status_code, 201)
        reference = response.get_json()['data']['reference']
        self.assertIn('cs_feedback_visitor=', response.headers['Set-Cookie'])

        inbox_response = client.get('/api/admin/feedback')
        self.assertEqual(inbox_response.status_code, 200)
        self.assertEqual(inbox_response.get_json()['data']['items'][0]['reference'], reference)

        reply_response = client.patch(
            f'/api/admin/feedback/{reference}',
            json={'reply': '会认真研究这个奖。', 'status': 'replied'},
        )
        self.assertEqual(reply_response.status_code, 200)

        public_response = client.get(f'/api/v1/feedback/{reference}')
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.get_json()['data']['reply'], '会认真研究这个奖。')

        stranger = app.test_client()
        self.assertEqual(stranger.get(f'/api/v1/feedback/{reference}').status_code, 404)


if __name__ == '__main__':
    unittest.main()
