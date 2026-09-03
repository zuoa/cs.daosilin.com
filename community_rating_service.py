"""Anonymous, once-per-day community ratings for player seasons."""

import hashlib
import hmac
import math
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from itsdangerous import BadSignature, URLSafeSerializer
from database import Player, PlayerCommunityRating


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
MINIMUM_RATINGS = 5
PRIOR_WEIGHT = 5
NEUTRAL_PRIOR = 3.0


def _label_for_average(value):
    """Map a continuous 1–5 result to the nearest community tier."""
    score = max(1, min(5, math.floor(float(value) + 0.5)))
    return next(label for option_score, label, _ in RATING_OPTIONS if option_score == score)


def _summary_from_counts(counts, prior_mean):
    total_votes = sum(counts.values())
    if total_votes < MINIMUM_RATINGS:
        return {
            'status': 'collecting',
            'score': None,
            'label': None,
            'total_votes': total_votes,
            'minimum_votes': MINIMUM_RATINGS,
            'method': 'bayesian_average',
        }

    score_sum = sum(score * count for score, count in counts.items())
    raw_average = score_sum / total_votes
    adjusted_average = (
        score_sum + PRIOR_WEIGHT * prior_mean
    ) / (total_votes + PRIOR_WEIGHT)
    return {
        'status': 'formed',
        'score': round(adjusted_average, 2),
        'raw_average': round(raw_average, 2),
        # The weighted score is useful for stable leaderboard sorting, but the
        # visible verdict should still describe what people actually voted.
        'label': _label_for_average(raw_average),
        'label_method': 'raw_average',
        'total_votes': total_votes,
        'minimum_votes': MINIMUM_RATINGS,
        'method': 'bayesian_average',
    }


def community_rating_summaries(cup_name, player_ids):
    """Return stable, season-relative rating summaries for leaderboard rows."""
    account_map = Player.account_map()
    player_ids = tuple(dict.fromkeys(
        account_map.get(str(player_id), str(player_id)) for player_id in player_ids
    ))
    if not player_ids:
        return {}

    counts_by_player = {
        player_id: {score: 0 for score, _, _ in RATING_OPTIONS}
        for player_id in player_ids
    }
    rows = (PlayerCommunityRating.select()
            .where(PlayerCommunityRating.cup_name == cup_name)
            .order_by(PlayerCommunityRating.updated_at))
    latest_votes = {}
    for row in rows:
        canonical_id = account_map.get(str(row.player_id), str(row.player_id))
        latest_votes[(canonical_id, row.voter_hash, row.vote_date)] = row

    cup_score_sum = 0
    cup_vote_count = 0
    for (canonical_id, _voter_hash, _vote_date), row in latest_votes.items():
        cup_score_sum += int(row.score)
        cup_vote_count += 1
        player_counts = counts_by_player.get(canonical_id)
        if player_counts is not None and row.score in player_counts:
            player_counts[row.score] += 1

    prior_mean = cup_score_sum / cup_vote_count if cup_vote_count else NEUTRAL_PRIOR
    return {
        player_id: _summary_from_counts(counts, prior_mean)
        for player_id, counts in counts_by_player.items()
    }


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
    player_id = Player.canonical_player_id(player_id)
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
    player_id = Player.canonical_player_id(player_id)
    account_ids = Player.account_ids(player_id)
    today_score = None
    if voter_hash:
        vote = (PlayerCommunityRating.select()
                .where(PlayerCommunityRating.player_id.in_(account_ids),
                       PlayerCommunityRating.cup_name == cup_name,
                       PlayerCommunityRating.voter_hash == voter_hash,
                       PlayerCommunityRating.vote_date == rating_today())
                .order_by(PlayerCommunityRating.updated_at.desc())
                .first())
        today_score = vote.score if vote else None

    results_visible = bool(reveal or today_score is not None)
    counts = {score: 0 for score, _, _ in RATING_OPTIONS}
    if results_visible:
        rows = (PlayerCommunityRating.select()
                .where(PlayerCommunityRating.player_id.in_(account_ids),
                       PlayerCommunityRating.cup_name == cup_name)
                .order_by(PlayerCommunityRating.updated_at))
        latest_votes = {}
        for row in rows:
            latest_votes[(row.voter_hash, row.vote_date)] = row
        for row in latest_votes.values():
            if row.score in counts:
                counts[row.score] += 1

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
        summary = community_rating_summaries(cup_name, [player_id])[str(player_id)]
        consensus = {
            key: value for key, value in summary.items()
            if key not in ('total_votes', 'minimum_votes')
        }

    return {
        'viewer_score': today_score,
        'voted_today': today_score is not None,
        'results_visible': results_visible,
        'total_votes': total_votes,
        'options': options,
        'consensus': consensus,
        'minimum_votes': MINIMUM_RATINGS,
        'timezone': 'Asia/Shanghai',
    }
