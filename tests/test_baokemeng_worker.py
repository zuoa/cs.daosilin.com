import unittest
from unittest.mock import patch

from baokemeng_worker import _ReconnectBackoff


class ReconnectBackoffTest(unittest.TestCase):
    @patch('baokemeng_worker.random.uniform', return_value=0)
    def test_healthy_connection_resets_consecutive_failures(self, _uniform):
        backoff = _ReconnectBackoff()

        self.assertEqual(backoff.failed_delay(), 2)
        self.assertEqual(backoff.failed_delay(), 4)
        backoff.connected()
        self.assertEqual(backoff.failed_delay(), 2)


if __name__ == '__main__':
    unittest.main()
