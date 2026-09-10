"""Dedicated single-concurrency RQ worker for DeepSeek editorial tasks."""
from redis import Redis
from rq import Queue, Worker
from rq.serializers import JSONSerializer

from config import REDIS_URL


if __name__ == '__main__':
    if not REDIS_URL:
        raise SystemExit('REDIS_URL is required for player-summary-worker')
    connection = Redis.from_url(REDIS_URL)
    queues = [
        Queue('season-lineup', connection=connection, serializer=JSONSerializer),
        Queue('player-summary', connection=connection, serializer=JSONSerializer),
    ]
    Worker(queues, connection=connection, serializer=JSONSerializer).work()
