"""Anonymous, once-per-day community ratings for player seasons."""

import hashlib
import hmac
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from itsdangerous import BadSignature, URLSafeSerializer
from peewee import fn

from database import PlayerCommunityRating


COOKIE_NAME = 'cs_community_voter'
COOKIE_MAX_AGE = 365 * 24 * 60 * 60
COOKIE_SALT = 'player-community-rating-v1'
SHANGHAI = ZoneInfo('Asia/Shanghai')

RATING_OPTIONS = (
    (5, '夯', '统治级，没得说'),
    (4, '顶级', '大腿表现，很硬'),
    (3, '人上人', '高于平均，有说法'),
    (2, 'NPC', '中规中矩，正常发挥'),
    (1, '拉完了', '这季状态不在线'),
)


def rating_today():
    return datetime.now(SHANGHAI).date()


def read_voter_id(secret_key, token):
    if not token:
        return None
    try:
        voter_id = URLSafeSerializer(secret_key, salt=COOKIE_SALT).loads(token)
    except BadSignature:
        return None
    if not isinstance(voter_id, str) or not 16 <= len(voter_id) <= 128:
        return None
    return voter_id


def new_voter(secret_key):
    voter_id = secrets.token_urlsafe(32)
    token = URLSafeSerializer(secret_key, salt=COOKIE_SALT).dumps(voter_id)
    return voter_id, token


def hash_voter(secret_key, voter_id):
    return hmac.new(
        str(secret_key).encode('utf-8'),
        voter_id.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def save_daily_rating(player_id, cup_name, voter_hash, score):
    today = rating_today()
    with PlayerCommunityRating._meta.database.atomic():
        (PlayerCommunityRating
         .insert(
            player_id=player_id,
            cup_name=cup_name,
            voter_hash=voter_hash,
            vote_date=today,
            score=score,
         )
         .on_conflict(
             conflict_target=(
                 PlayerCommunityRating.player_id,
                 PlayerCommunityRating.cup_name,
                 PlayerCommunityRating.voter_hash,
                 PlayerCommunityRating.vote_date,
             ),
             update={
                 PlayerCommunityRating.score: score,
                 PlayerCommunityRating.updated_at: datetime.now(),
             },
         )
         .execute())
    return rating_payload(player_id, cup_name, voter_hash, reveal=True)


def rating_payload(player_id, cup_name, voter_hash=None, reveal=False):
    today_score = None
    if voter_hash:
        vote = PlayerCommunityRating.get_or_none(
            PlayerCommunityRating.player_id == player_id,
            PlayerCommunityRating.cup_name == cup_name,
            PlayerCommunityRating.voter_hash == voter_hash,
            PlayerCommunityRating.vote_date == rating_today(),
        )
        today_score = vote.score if vote else None

    results_visible = bool(reveal or today_score is not None)
    counts = {score: 0 for score, _, _ in RATING_OPTIONS}
    if results_visible:
        rows = (PlayerCommunityRating
                .select(PlayerCommunityRating.score,
                        fn.COUNT(PlayerCommunityRating.id).alias('count'))
                .where(PlayerCommunityRating.player_id == player_id,
                       PlayerCommunityRating.cup_name == cup_name)
                .group_by(PlayerCommunityRating.score))
        for row in rows:
            if row.score in counts:
                counts[row.score] = int(row.count or 0)

    total_votes = sum(counts.values()) if results_visible else None
    options = []
    for score, label, hint in RATING_OPTIONS:
        option = {'score': score, 'label': label, 'hint': hint}
        if results_visible:
            count = counts[score]
            option.update({
                'count': count,
                'percentage': round(count / total_votes * 100, 1) if total_votes else 0.0,
            })
        options.append(option)

    consensus = None
    if results_visible:
        if total_votes < 5:
            consensus = {'status': 'collecting', 'score': None, 'label': None}
        else:
            highest = max(counts.values())
            leaders = [score for score, count in counts.items() if count == highest]
            if len(leaders) != 1:
                consensus = {'status': 'tied', 'score': None, 'label': None}
            else:
                score = leaders[0]
                label = next(label for value, label, _ in RATING_OPTIONS if value == score)
                consensus = {'status': 'formed', 'score': score, 'label': label}

    return {
        'viewer_score': today_score,
        'voted_today': today_score is not None,
        'results_visible': results_visible,
        'total_votes': total_votes,
        'options': options,
        'consensus': consensus,
        'timezone': 'Asia/Shanghai',
    }
