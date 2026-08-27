"""Season title engine.

Titles are intentionally scarce and evidence-led. A player can receive at most
one honour, one play-style label and one season story. Every saved description
contains the values that caused the title to be awarded.
"""

from dataclasses import dataclass, replace
from enum import Enum
import math
import statistics
from typing import Callable, Dict, List, Optional, Tuple

from config import MAX_TITLES_PER_PLAYER


PlayerData = Dict[str, object]
Metric = Callable[[PlayerData], float]
Condition = Callable[[PlayerData, List[PlayerData]], bool]
Evidence = Callable[[PlayerData, List[PlayerData]], str]


class TitleType(Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"  # Kept for compatibility with historical rows.


class TitleCategory(Enum):
    HONOUR = "honour"
    FIREPOWER = "firepower"
    ENTRY = "entry"
    CLUTCH = "clutch"
    TEAMWORK = "teamwork"
    CONSISTENCY = "consistency"
    STYLE = "style"


class TitleSlot(Enum):
    HONOUR = "honour"
    STYLE = "style"
    STORY = "story"


@dataclass(frozen=True)
class Title:
    name: str
    description: str
    category: TitleCategory
    title_type: TitleType
    condition_func: Condition
    priority: int = 1
    slot: TitleSlot = TitleSlot.STYLE
    evidence_func: Optional[Evidence] = None
    score_func: Optional[Callable[[PlayerData, List[PlayerData]], float]] = None


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _per_match(field: str) -> Metric:
    return lambda data: _number(data.get(field)) / max(_number(data.get("match_count")), 1)


def _field(field: str) -> Metric:
    return lambda data: _number(data.get(field))


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ratio(value: float) -> str:
    return f"{value:.2f}"


class RefactoredTitleSystem:
    """Calculate a compact, explainable season profile for every player."""

    def __init__(self):
        self.titles = self._initialize_titles()

    @staticmethod
    def _minimum_matches(all_players_data: List[PlayerData]) -> int:
        maximum = max((_number(p.get("match_count")) for p in all_players_data), default=0)
        if maximum <= 3:
            return 1
        return max(3, math.ceil(maximum * 0.30))

    def _eligible_players(self, all_players_data: List[PlayerData]) -> List[PlayerData]:
        minimum = self._minimum_matches(all_players_data)
        return [p for p in all_players_data if _number(p.get("match_count")) >= minimum]

    @staticmethod
    def _same_player(left: PlayerData, right: PlayerData) -> bool:
        left_id = left.get("player_id")
        right_id = right.get("player_id")
        if left_id is not None and right_id is not None:
            return left_id == right_id
        return left is right or left == right

    def _is_eligible(self, player_data: PlayerData, all_players_data: List[PlayerData]) -> bool:
        return any(self._same_player(player_data, candidate) for candidate in self._eligible_players(all_players_data))

    def _rank(
        self,
        player_data: PlayerData,
        all_players_data: List[PlayerData],
        metric: Metric,
        *,
        reverse: bool = True,
        valid: Optional[Callable[[PlayerData], bool]] = None,
    ) -> Tuple[Optional[int], int]:
        candidates = self._eligible_players(all_players_data)
        if valid:
            candidates = [p for p in candidates if valid(p)]
        if not candidates or not any(self._same_player(player_data, candidate) for candidate in candidates):
            return None, len(candidates)

        value = metric(player_data)
        if reverse:
            rank = 1 + sum(metric(candidate) > value for candidate in candidates)
        else:
            rank = 1 + sum(metric(candidate) < value for candidate in candidates)
        return rank, len(candidates)

    def _is_top(
        self,
        player_data: PlayerData,
        all_players_data: List[PlayerData],
        metric: Metric,
        fraction: float,
        *,
        valid: Optional[Callable[[PlayerData], bool]] = None,
    ) -> bool:
        rank, total = self._rank(player_data, all_players_data, metric, valid=valid)
        return rank is not None and rank <= max(1, math.ceil(total * fraction))

    def _is_bottom(
        self,
        player_data: PlayerData,
        all_players_data: List[PlayerData],
        metric: Metric,
        fraction: float,
    ) -> bool:
        rank, total = self._rank(player_data, all_players_data, metric, reverse=False)
        return rank is not None and rank <= max(1, math.ceil(total * fraction))

    def _is_first(
        self,
        player_data: PlayerData,
        all_players_data: List[PlayerData],
        metric: Metric,
        *,
        valid: Optional[Callable[[PlayerData], bool]] = None,
    ) -> bool:
        rank, _ = self._rank(player_data, all_players_data, metric, valid=valid)
        return rank == 1

    def _median(self, all_players_data: List[PlayerData], metric: Metric) -> float:
        values = [metric(player) for player in self._eligible_players(all_players_data)]
        return statistics.median(values) if values else 0.0

    def _rank_evidence(
        self,
        player_data: PlayerData,
        all_players_data: List[PlayerData],
        metric: Metric,
        label: str,
        formatter: Callable[[float], str] = _ratio,
        *,
        valid: Optional[Callable[[PlayerData], bool]] = None,
    ) -> str:
        rank, total = self._rank(player_data, all_players_data, metric, valid=valid)
        suffix = f"，赛季 #{rank}/{total}" if rank is not None else ""
        return f"{label} {formatter(metric(player_data))}{suffix}"

    def _rank_score(self, player_data: PlayerData, all_players_data: List[PlayerData], metric: Metric) -> float:
        rank, total = self._rank(player_data, all_players_data, metric)
        if rank is None or total == 0:
            return 0.0
        return 1 - (rank - 1) / total

    @staticmethod
    def _weighted_clutches(data: PlayerData) -> float:
        return (
            _number(data.get("total_1v2"))
            + 2 * _number(data.get("total_1v3"))
            + 3 * _number(data.get("total_1v4"))
            + 4 * _number(data.get("total_1v5"))
        ) / max(_number(data.get("match_count")), 1)

    @staticmethod
    def _weighted_multi_kills(data: PlayerData) -> float:
        return (
            _number(data.get("total_2k"))
            + 2 * _number(data.get("total_3k"))
            + 3 * _number(data.get("total_4k"))
            + 4 * _number(data.get("total_5k"))
        ) / max(_number(data.get("match_count")), 1)

    @staticmethod
    def _day_ratings(data: PlayerData) -> List[float]:
        history = data.get("day_history") or []
        return [_number(item.get("avg_pw_rating")) for item in history if _number(item.get("avg_pw_rating")) > 0]

    def _rating_cv(self, data: PlayerData) -> float:
        values = self._day_ratings(data)
        if len(values) < 2 or statistics.mean(values) == 0:
            return math.inf
        return statistics.pstdev(values) / statistics.mean(values)

    def _late_gain(self, data: PlayerData) -> float:
        values = self._day_ratings(data)
        if len(values) < 4:
            return 0.0
        middle = len(values) // 2
        early = statistics.mean(values[:middle])
        late = statistics.mean(values[middle:])
        return (late / early - 1) if early else 0.0

    def _initialize_titles(self) -> List[Title]:
        pwr = _field("avg_pw_rating")
        adpr = _field("avg_adpr")
        win_rate = _field("win_rate")
        kd = _field("kd_ratio")
        headshot = _field("avg_headshot_ratio")
        entry_pm = _per_match("total_first_kills")
        first_death_pm = _per_match("total_first_deaths")
        assist_pm = _per_match("total_assists")
        snipe_pm = _per_match("total_snipe_num")
        throws_pm = _per_match("total_throws_count")
        mvp_rate = _per_match("match_mvp_count")
        deaths_pm = _per_match("total_deaths")

        enough_kills = lambda d: _number(d.get("total_kills")) >= 10
        has_sniper_sample = lambda d: _number(d.get("total_snipe_num")) >= 3
        has_utility_sample = lambda d: _number(d.get("total_throws_count")) > 0
        has_mvp = lambda d: _number(d.get("match_mvp_count")) > 0

        return [
            Title(
                "赛季标杆", "综合评分领跑赛季", TitleCategory.HONOUR, TitleType.POSITIVE,
                lambda d, all_d: self._is_first(d, all_d, pwr), 100, TitleSlot.HONOUR,
                lambda d, all_d: self._rank_evidence(d, all_d, pwr, "PWR Rating"),
                lambda d, all_d: self._rank_score(d, all_d, pwr),
            ),
            Title(
                "火力天花板", "回合伤害领跑赛季", TitleCategory.FIREPOWER, TitleType.POSITIVE,
                lambda d, all_d: self._is_first(d, all_d, adpr), 96, TitleSlot.HONOUR,
                lambda d, all_d: self._rank_evidence(d, all_d, adpr, "ADPR", lambda v: f"{v:.1f}"),
                lambda d, all_d: self._rank_score(d, all_d, adpr),
            ),
            Title(
                "关键先生", "高频拿下比赛 MVP", TitleCategory.HONOUR, TitleType.POSITIVE,
                lambda d, all_d: has_mvp(d) and self._is_top(d, all_d, mvp_rate, .10, valid=has_mvp),
                92, TitleSlot.HONOUR,
                lambda d, all_d: self._rank_evidence(d, all_d, mvp_rate, "MVP 率", _percent, valid=has_mvp),
                lambda d, all_d: self._rank_score(d, all_d, mvp_rate),
            ),
            Title(
                "胜利引擎", "胜率与个人表现同时在线", TitleCategory.HONOUR, TitleType.POSITIVE,
                lambda d, all_d: self._is_top(d, all_d, win_rate, .10) and pwr(d) >= self._median(all_d, pwr),
                90, TitleSlot.HONOUR,
                lambda d, all_d: f"胜率 {_percent(win_rate(d))}，PWR {pwr(d):.2f}",
                lambda d, all_d: self._rank_score(d, all_d, win_rate),
            ),
            Title(
                "破局先锋", "以首杀打开回合局面", TitleCategory.ENTRY, TitleType.POSITIVE,
                lambda d, all_d: _number(d.get("fk_fd_ratio")) >= 1.2 and self._is_top(d, all_d, entry_pm, .15),
                80, TitleSlot.STYLE,
                lambda d, all_d: f"场均首杀 {entry_pm(d):.2f}，FK/FD {_number(d.get('fk_fd_ratio')):.2f}",
                lambda d, all_d: self._rank_score(d, all_d, entry_pm),
            ),
            Title(
                "爆头美学", "稳定以头部命中终结对手", TitleCategory.FIREPOWER, TitleType.POSITIVE,
                lambda d, all_d: self._is_top(d, all_d, headshot, .15, valid=enough_kills),
                78, TitleSlot.STYLE,
                lambda d, all_d: self._rank_evidence(d, all_d, headshot, "爆头率", _percent, valid=enough_kills),
                lambda d, all_d: self._rank_score(d, all_d, headshot),
            ),
            Title(
                "长枪管辖区", "狙击是主要火力来源", TitleCategory.FIREPOWER, TitleType.POSITIVE,
                lambda d, all_d: (
                    _number(d.get("total_snipe_num")) / max(_number(d.get("total_kills")), 1) >= .30
                    and self._is_top(d, all_d, snipe_pm, .20, valid=has_sniper_sample)
                ),
                77, TitleSlot.STYLE,
                lambda d, all_d: f"场均狙杀 {snipe_pm(d):.2f}，占击杀 {_percent(_number(d.get('total_snipe_num')) / max(_number(d.get('total_kills')), 1))}",
                lambda d, all_d: self._rank_score(d, all_d, snipe_pm),
            ),
            Title(
                "生存专家", "高效完成击杀交换", TitleCategory.FIREPOWER, TitleType.POSITIVE,
                lambda d, all_d: self._is_top(d, all_d, kd, .10), 75, TitleSlot.STYLE,
                lambda d, all_d: self._rank_evidence(d, all_d, kd, "K/D"),
                lambda d, all_d: self._rank_score(d, all_d, kd),
            ),
            Title(
                "战术支点", "助攻产出稳定支撑团队", TitleCategory.TEAMWORK, TitleType.POSITIVE,
                lambda d, all_d: self._is_top(d, all_d, assist_pm, .15) and pwr(d) >= self._median(all_d, pwr),
                73, TitleSlot.STYLE,
                lambda d, all_d: self._rank_evidence(d, all_d, assist_pm, "场均助攻"),
                lambda d, all_d: self._rank_score(d, all_d, assist_pm),
            ),
            Title(
                "道具调度员", "高频使用道具建立回合条件", TitleCategory.TEAMWORK, TitleType.POSITIVE,
                lambda d, all_d: self._is_top(d, all_d, throws_pm, .10, valid=has_utility_sample),
                70, TitleSlot.STYLE,
                lambda d, all_d: self._rank_evidence(d, all_d, throws_pm, "场均投掷物", lambda v: f"{v:.1f}", valid=has_utility_sample),
                lambda d, all_d: self._rank_score(d, all_d, throws_pm),
            ),
            Title(
                "不可能任务", "完成过高难度残局", TitleCategory.CLUTCH, TitleType.POSITIVE,
                lambda d, all_d: _number(d.get("total_1v4")) + _number(d.get("total_1v5")) > 0,
                88, TitleSlot.STORY,
                lambda d, all_d: f"1v4 {_number(d.get('total_1v4')):.0f} 次，1v5 {_number(d.get('total_1v5')):.0f} 次",
                lambda d, all_d: self._weighted_clutches(d),
            ),
            Title(
                "ACE 收藏家", "在赛季中完成过五杀", TitleCategory.CLUTCH, TitleType.POSITIVE,
                lambda d, all_d: _number(d.get("total_5k")) > 0, 86, TitleSlot.STORY,
                lambda d, all_d: f"赛季五杀 {_number(d.get('total_5k')):.0f} 次",
                lambda d, all_d: _number(d.get("total_5k")),
            ),
            Title(
                "残局接管", "残局产出位列赛季前列", TitleCategory.CLUTCH, TitleType.POSITIVE,
                lambda d, all_d: self._weighted_clutches(d) > 0 and self._is_top(d, all_d, self._weighted_clutches, .10),
                84, TitleSlot.STORY,
                lambda d, all_d: self._rank_evidence(d, all_d, self._weighted_clutches, "加权残局/场"),
                lambda d, all_d: self._rank_score(d, all_d, self._weighted_clutches),
            ),
            Title(
                "连杀制造机", "多杀回合产出位列赛季前列", TitleCategory.FIREPOWER, TitleType.POSITIVE,
                lambda d, all_d: (
                    _number(d.get("total_3k")) + _number(d.get("total_4k")) + _number(d.get("total_5k")) > 0
                    and self._is_top(d, all_d, self._weighted_multi_kills, .10)
                ),
                80, TitleSlot.STORY,
                lambda d, all_d: self._rank_evidence(d, all_d, self._weighted_multi_kills, "加权多杀/场"),
                lambda d, all_d: self._rank_score(d, all_d, self._weighted_multi_kills),
            ),
            Title(
                "后程加速", "后半程表现显著提升", TitleCategory.CONSISTENCY, TitleType.POSITIVE,
                lambda d, all_d: self._late_gain(d) >= .15 and pwr(d) >= self._median(all_d, pwr),
                76, TitleSlot.STORY,
                lambda d, all_d: f"后半程 PWR 较前半程提升 {_percent(self._late_gain(d))}",
                lambda d, all_d: self._late_gain(d),
            ),
            Title(
                "稳如准星", "多比赛日保持稳定输出", TitleCategory.CONSISTENCY, TitleType.POSITIVE,
                lambda d, all_d: len(self._day_ratings(d)) >= 4 and self._rating_cv(d) <= .12 and pwr(d) >= self._median(all_d, pwr),
                74, TitleSlot.STORY,
                lambda d, all_d: f"{len(self._day_ratings(d))} 个比赛日，PWR 波动系数 {_percent(self._rating_cv(d))}",
                lambda d, all_d: 1 - self._rating_cv(d),
            ),
            Title(
                "玻璃大炮", "输出凶猛，同时承担较高阵亡风险", TitleCategory.STYLE, TitleType.NEUTRAL,
                lambda d, all_d: self._is_top(d, all_d, adpr, .20) and self._is_top(d, all_d, deaths_pm, .20),
                68, TitleSlot.STORY,
                lambda d, all_d: f"ADPR {adpr(d):.1f}，场均阵亡 {deaths_pm(d):.2f}",
                lambda d, all_d: self._rank_score(d, all_d, adpr),
            ),
            Title(
                "高风险突破", "频繁参与回合的第一波交火", TitleCategory.ENTRY, TitleType.NEUTRAL,
                lambda d, all_d: (
                    _number(d.get("fk_fd_ratio")) >= .9
                    and self._is_top(d, all_d, entry_pm, .20)
                    and self._is_top(d, all_d, first_death_pm, .20)
                ),
                66, TitleSlot.STORY,
                lambda d, all_d: f"场均首杀 {entry_pm(d):.2f}，场均首死 {first_death_pm(d):.2f}",
                lambda d, all_d: self._rank_score(d, all_d, entry_pm),
            ),
            Title(
                "逆风核心", "个人表现突出，但赛果未完全兑现", TitleCategory.STYLE, TitleType.NEUTRAL,
                lambda d, all_d: self._is_top(d, all_d, pwr, .20) and self._is_bottom(d, all_d, win_rate, .40),
                64, TitleSlot.STORY,
                lambda d, all_d: f"PWR {pwr(d):.2f}，胜率 {_percent(win_rate(d))}",
                lambda d, all_d: self._rank_score(d, all_d, pwr),
            ),
        ]

    def calculate_titles(
        self,
        player_data: PlayerData,
        all_players_data: Optional[List[PlayerData]] = None,
    ) -> List[Tuple[Title, float]]:
        all_data = all_players_data or [player_data]
        if not self._is_eligible(player_data, all_data):
            return []

        qualified: List[Tuple[Title, float]] = []
        for title in self.titles:
            try:
                if not title.condition_func(player_data, all_data):
                    continue
                score = self._calculate_title_score(title, player_data, all_data)
                description = title.evidence_func(player_data, all_data) if title.evidence_func else title.description
                qualified.append((replace(title, description=description), score))
            except (ArithmeticError, KeyError, TypeError, ValueError):
                continue
        return sorted(qualified, key=lambda item: (item[0].priority, item[1]), reverse=True)

    def _calculate_title_score(
        self,
        title: Title,
        player_data: PlayerData,
        all_players_data: Optional[List[PlayerData]] = None,
    ) -> float:
        all_data = all_players_data or [player_data]
        match_score = title.score_func(player_data, all_data) if title.score_func else 0.0
        return round(title.priority + match_score, 4)

    def get_best_titles(
        self,
        player_data: PlayerData,
        max_titles: Optional[int] = None,
        all_players_data: Optional[List[PlayerData]] = None,
    ) -> List[Title]:
        limit = min(max_titles or MAX_TITLES_PER_PLAYER, 3)
        selected: List[Title] = []
        used_slots = set()
        for title, _ in self.calculate_titles(player_data, all_players_data):
            if title.slot in used_slots:
                continue
            selected.append(title)
            used_slots.add(title.slot)
            if len(selected) >= limit:
                break
        return sorted(selected, key=lambda title: list(TitleSlot).index(title.slot))

    def get_title_statistics(self, all_players_data: List[PlayerData]) -> Dict[str, object]:
        distribution: Dict[str, int] = {}
        categories: Dict[str, int] = {}
        for player_data in all_players_data:
            for title in self.get_best_titles(player_data, all_players_data=all_players_data):
                distribution[title.name] = distribution.get(title.name, 0) + 1
                key = title.category.value
                categories[key] = categories.get(key, 0) + 1
        return {
            "total_players": len(all_players_data),
            "title_distribution": distribution,
            "category_distribution": categories,
        }


title_system = RefactoredTitleSystem()
