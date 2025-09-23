"""
重构后的称号系统 - 基于统一逻辑的精简称号分配系统
采用统一的排名规则和分类体系，去除重复和相似称号
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import math
from config import MAX_TITLES_PER_PLAYER, MAX_POSITIVE_TITLES, MAX_NEGATIVE_TITLES, TITLE_PRIORITY_THRESHOLD


class TitleType(Enum):
    """称号类型"""
    POSITIVE = "positive"  # 正面称号
    NEGATIVE = "negative"  # 反面称号
    NEUTRAL = "neutral"    # 中性称号


class TitleCategory(Enum):
    """称号分类"""
    KILLING = "killing"           # 击杀相关
    SURVIVAL = "survival"         # 生存相关
    SKILL = "skill"              # 技能相关
    TEAMWORK = "teamwork"         # 团队合作
    ACHIEVEMENT = "achievement"   # 成就相关
    CONSISTENCY = "consistency"   # 稳定性相关


@dataclass
class Title:
    """称号定义"""
    name: str
    description: str
    category: TitleCategory
    title_type: TitleType
    condition_func: callable
    priority: int = 1  # 优先级，数字越大优先级越高


class RefactoredTitleSystem:
    """重构后的称号系统核心类"""
    
    def __init__(self):
        self.titles = self._initialize_titles()
    
    def _calculate_relative_rank(self, player_value: float, all_values: List[float], reverse: bool = True) -> float:
        """
        计算玩家在所有人中的相对排名
        
        Args:
            player_value: 玩家数值
            all_values: 所有玩家的数值列表
            reverse: True表示数值越大越好，False表示数值越小越好
            
        Returns:
            相对排名比例 (0-1)，1表示最高排名
        """
        if not all_values or len(all_values) <= 1:
            return 0.5
        
        sorted_values = sorted(all_values, reverse=reverse)
        try:
            rank = sorted_values.index(player_value) + 1
            return rank / len(sorted_values)
        except ValueError:
            return 0.5
    
    def _is_extreme_value(self, player_value: float, all_values: List[float], 
                         is_max: bool = True) -> bool:
        """
        判断是否为极值（第1名）
        
        Args:
            player_value: 玩家数值
            all_values: 所有玩家的数值列表
            is_max: True表示判断是否为最大值，False表示最小值
            
        Returns:
            是否为极值
        """
        if not all_values or len(all_values) <= 1:
            return False
        
        if is_max:
            max_val = max(all_values)
            ret =  player_value == max_val and player_value > 0
            return ret
        else:
            min_val = min(all_values)
            return player_value == min_val
    
    def _get_percentile_rank(self, player_value: float, all_values: List[float], 
                            reverse: bool = True) -> float:
        """
        获取百分位排名
        
        Args:
            player_value: 玩家数值
            all_values: 所有玩家的数值列表
            reverse: True表示数值越大越好
            
        Returns:
            百分位排名 (0-100)
        """
        if not all_values or len(all_values) <= 1:
            return 50.0
        
        sorted_values = sorted(all_values, reverse=reverse)
        try:
            rank = sorted_values.index(player_value) + 1
            return (rank - 1) / (len(sorted_values) - 1) * 100
        except ValueError:
            return 50.0
    
    def _is_top_players_by_field(self, player_data: Dict, all_players_data: List[Dict], 
                                 field_name: str, top_n: int = 3, reverse: bool = True) -> bool:
        """
        判断玩家是否在指定字段的前N名
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            field_name: 字段名
            top_n: 前N名，默认为3
            reverse: True表示数值越大越好，False表示数值越小越好
            
        Returns:
            是否在前N名中
        """
        if not all_players_data or len(all_players_data) < top_n:
            return False
        
        # 计算所有玩家在该字段的数值
        player_values = []
        for player in all_players_data:
            value = player.get(field_name, 0)
            player_values.append((player.get('player_id'), value))
        
        # 按数值排序
        player_values.sort(key=lambda x: x[1], reverse=reverse)
        
        # 获取前N名的玩家ID
        top_players = [pid for pid, _ in player_values[:top_n]]
        
        # 检查当前玩家是否在前N名中
        current_player_id = player_data.get('player_id')
        return current_player_id in top_players
    
    def _is_bottom_players_by_field(self, player_data: Dict, all_players_data: List[Dict], 
                                   field_name: str, bottom_n: int = 3) -> bool:
        """
        判断玩家是否在指定字段的最后N名
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            field_name: 字段名
            bottom_n: 最后N名，默认为3
            
        Returns:
            是否在最后N名中
        """
        return self._is_top_players_by_field(player_data, all_players_data, field_name, bottom_n, reverse=False)
    
    def _is_top_percentile(self, player_data: Dict, all_players_data: List[Dict], 
                          field_name: str, percentile: float = 10.0, reverse: bool = True) -> bool:
        """
        判断玩家是否在指定百分位以上
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            field_name: 字段名
            percentile: 百分位阈值（如10.0表示前10%）
            reverse: True表示数值越大越好
            
        Returns:
            是否在指定百分位以上
        """
        if not all_players_data:
            return False
        
        player_value = player_data.get(field_name, 0)
        all_values = [p.get(field_name, 0) for p in all_players_data]
        
        rank = self._get_percentile_rank(player_value, all_values, reverse)
        return rank >= (100 - percentile)
    
    def _is_bottom_percentile(self, player_data: Dict, all_players_data: List[Dict], 
                             field_name: str, percentile: float = 10.0) -> bool:
        """
        判断玩家是否在指定百分位以下
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            field_name: 字段名
            percentile: 百分位阈值（如10.0表示后10%）
            
        Returns:
            是否在指定百分位以下
        """
        if not all_players_data:
            return False
        
        player_value = player_data.get(field_name, 0)
        all_values = [p.get(field_name, 0) for p in all_players_data]
        
        rank = self._get_percentile_rank(player_value, all_values, reverse=True)
        return rank <= percentile
    
    def _is_top_players_by_accuracy(self, player_data: Dict, all_players_data: List[Dict], top_n: int = 3) -> bool:
        """
        判断玩家是否是命中率最高的前N名
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            top_n: 前N名，默认为3
            
        Returns:
            是否是命中率最高的前N名
        """
        if not all_players_data or len(all_players_data) < top_n:
            return False
        
        # 计算所有玩家的命中率
        player_accuracies = []
        for player in all_players_data:
            hit_count = player.get('total_hit_count', 0)
            fire_count = player.get('total_fire_count', 1)
            accuracy = hit_count / max(fire_count, 1)
            player_accuracies.append((player.get('player_id'), accuracy))
        
        # 按命中率降序排序
        player_accuracies.sort(key=lambda x: x[1], reverse=True)
        
        # 获取前N名的玩家ID
        top_players = [pid for pid, _ in player_accuracies[:top_n]]
        
        # 检查当前玩家是否在前N名中
        current_player_id = player_data.get('player_id')
        return current_player_id in top_players
    
    def _initialize_titles(self) -> List[Title]:
        """初始化所有称号定义 - 精简版"""
        titles = []
        
        # ========== 极值称号（第1名） ==========

        # 击杀相关极值称号
        titles.extend([
            Title(
                name="击杀之王",
                description="总击杀数最多的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('total_kills', 0),
                    [p.get('total_kills', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
            Title(
                name="爆头之王",
                description="爆头率最高的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('avg_headshot_ratio', 0),
                    [p.get('avg_headshot_ratio', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
            Title(
                name="多杀之王",
                description="多杀次数最多的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('total_multi_kills', 0),
                    [p.get('total_multi_kills', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
        ])

        # 生存相关极值称号
        titles.extend([
            Title(
                name="生存之王",
                description="K/D比最高的玩家",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('kd_ratio', 0),
                    [p.get('kd_ratio', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
        ])

        # 技能相关极值称号
        titles.extend([
            Title(
                name="伤害之王",
                description="平均每回合伤害最高的玩家",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('avg_adpr', 0),
                    [p.get('avg_adpr', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
        ])

        # 团队合作极值称号
        titles.extend([
            Title(
                name="助攻之王",
                description="总助攻数最多的玩家",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('total_assists', 0),
                    [p.get('total_assists', 0) for p in all_data],
                    is_max=True
                ),
                priority=4
            ),
        ])

        # 成就相关极值称号
        titles.extend([
            Title(
                name="MVP之王",
                description="MVP次数最多的玩家",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('match_mvp_count', 0),
                    [p.get('match_mvp_count', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
            Title(
                name="胜率之王",
                description="胜率最高的玩家",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_extreme_value(
                    data.get('win_rate', 0),
                    [p.get('win_rate', 0) for p in all_data],
                    is_max=True
                ),
                priority=5
            ),
        ])
        
        # ========== 前三称号 ==========
        
        # 击杀相关前三称号
        titles.extend([
            Title(
                name="爆头大师",
                description="爆头率前三的精准射手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'avg_headshot_ratio', top_n=3),
                priority=4
            ),
            Title(
                name="连杀大师",
                description="多杀次数前三的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'total_multi_kills', top_n=3),
                priority=3
            ),
            Title(
                name="AWP大师",
                description="AWP击杀数前三的狙击手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'total_snipe_num', top_n=3),
                priority=4
            ),
        ])
        
        # 生存相关前三称号
        titles.extend([
            Title(
                name="生存大师",
                description="K/D比前三的生存专家",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'kd_ratio', top_n=3),
                priority=4
            ),
        ])
        
        # 技能相关前三称号
        titles.extend([
            Title(
                name="神枪手",
                description="命中率前三的精准射手",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_accuracy(data, all_data, top_n=3),
                priority=4
            ),
            Title(
                name="输出大师",
                description="平均伤害前三的输出手",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'avg_adpr', top_n=3),
                priority=4
            ),
        ])
        
        # 团队合作前三称号
        titles.extend([
            Title(
                name="闪光专家",
                description="闪光成功率前三的辅助",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'flash_success_ratio', top_n=3),
                priority=3
            ),
            Title(
                name="投掷物专家",
                description="投掷物使用前三的战术家",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_players_by_field(data, all_data, 'total_throws_count', top_n=3),
                priority=2
            ),
        ])
        
        # ========== 前10%称号 ==========
        
        titles.extend([
            Title(
                name="精英射手",
                description="击杀数排名前10%的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_percentile(data, all_data, 'total_kills', 10.0),
                priority=3
            ),
            Title(
                name="精英选手",
                description="PWR评分排名前10%的玩家",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_percentile(data, all_data, 'avg_pw_rating', 10.0),
                priority=3
            ),
            Title(
                name="精英生存者",
                description="K/D比排名前10%的玩家",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data, all_data: self._is_top_percentile(data, all_data, 'kd_ratio', 10.0),
                priority=3
            ),
        ])

        
        # ========== 后10%称号 ==========
        
        titles.extend([
            Title(
                name="菜鸟射手",
                description="击杀数排名后10%的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data, all_data: self._is_bottom_percentile(data, all_data, 'total_kills', 10.0),
                priority=2
            ),
            Title(
                name="菜鸟选手",
                description="PWR评分排名后10%的玩家",
                category=TitleCategory.SKILL,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data, all_data: self._is_bottom_percentile(data, all_data, 'avg_pw_rating', 10.0),
                priority=2
            ),
            Title(
                name="送分童子",
                description="死亡数排名后10%的玩家",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data, all_data: self._is_bottom_percentile(data, all_data, 'total_deaths', 10.0),
                priority=2
            ),
        ])
        
        # ========== 特殊成就称号 ==========
        
        titles.extend([
            Title(
                name="冠军收割者",
                description="获得过冠军的传奇选手",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('is_champion', False),
                priority=5
            ),
            Title(
                name="常胜将军",
                description="胜率超过80%的胜利者",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('win_rate', 0) > 0.8,
                priority=4
            ),
            Title(
                name="铁人",
                description="比赛场次超过30场的选手",
                category=TitleCategory.CONSISTENCY,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('match_count', 0) > 30,
                priority=2
            ),
            Title(
                name="万年老二",
                description="总是获得亚军的选手",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('is_runner_up', False) and not data.get('is_champion', False),
                priority=1
            ),
        ])
        
        # ========== 反差萌称号 ==========
        
        titles.extend([
            Title(
                name="反差萌",
                description="击杀数很高但死亡数也很高的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.NEUTRAL,
                condition_func=lambda data, all_data: self._is_high_in_both(
                    data, all_data, 'total_kills', 'total_deaths', 0.7
                ),
                priority=2
            ),
            Title(
                name="莽夫",
                description="射击次数很多但命中率很低的玩家",
                category=TitleCategory.SKILL,
                title_type=TitleType.NEUTRAL,
                condition_func=lambda data, all_data: self._is_high_in_both(
                    data, all_data, 'total_fire_count', 'total_hit_count', 0.3, reverse_second=True
                ),
                priority=2
            ),
            Title(
                name="躺赢专家",
                description="胜率很高但个人评分很低的玩家",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.NEUTRAL,
                condition_func=lambda data, all_data: self._is_high_in_both(
                    data, all_data, 'win_rate', 'avg_pw_rating', 0.3, reverse_second=True
                ),
                priority=2
            ),
        ])
        
        return titles
    
    def _is_high_in_both(self, player_data: Dict, all_players_data: List[Dict], 
                        field1: str, field2: str, threshold: float, 
                        reverse_second: bool = False) -> bool:
        """
        判断玩家在两个字段上是否都排名靠前
        
        Args:
            player_data: 玩家数据
            all_players_data: 所有玩家数据
            field1: 第一个字段名
            field2: 第二个字段名
            threshold: 排名阈值 (0-1)
            reverse_second: 第二个字段是否反向排序
            
        Returns:
            是否在两个字段上都排名靠前
        """
        if not all_players_data:
            return False
        
        val1 = player_data.get(field1, 0)
        val2 = player_data.get(field2, 0)
        
        all_vals1 = [p.get(field1, 0) for p in all_players_data]
        all_vals2 = [p.get(field2, 0) for p in all_players_data]
        
        rank1 = self._get_percentile_rank(val1, all_vals1, reverse=True)
        rank2 = self._get_percentile_rank(val2, all_vals2, reverse=not reverse_second)
        
        return rank1 >= threshold * 100 and rank2 >= threshold * 100
    
    def calculate_titles(self, player_data: Dict, all_players_data: List[Dict] = None) -> List[Tuple[Title, float]]:
        """
        为玩家计算称号
        
        Args:
            player_data: 玩家数据字典
            all_players_data: 所有玩家数据列表，用于相对比较
            
        Returns:
            符合条件的称号列表，按优先级排序
        """
        qualified_titles = []
        
        for title in self.titles:
            try:
                # 为条件函数提供所有玩家数据用于相对比较
                if all_players_data:
                    if title.condition_func(player_data, all_players_data):
                        # 计算称号匹配度分数
                        score = self._calculate_title_score(title, player_data, all_players_data)
                        qualified_titles.append((title, score))
                else:
                    # 兼容原有的单玩家计算方式
                    if title.condition_func(player_data):
                        score = self._calculate_title_score(title, player_data)
                        qualified_titles.append((title, score))
            except Exception as e:
                # 如果计算过程中出现错误，跳过这个称号
                continue
        
        # 按优先级和分数排序
        qualified_titles.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        
        return qualified_titles
    
    def _calculate_title_score(self, title: Title, player_data: Dict, all_players_data: List[Dict] = None) -> float:
        """计算称号匹配度分数"""
        score = 1.0  # 基础分数
        
        # 根据称号类型调整分数
        if title.title_type == TitleType.POSITIVE:
            # 正面称号根据相关数据值调整分数
            if title.category == TitleCategory.KILLING:
                score += min(player_data.get('total_kills', 0) / 100, 2.0)
            elif title.category == TitleCategory.SURVIVAL:
                score += min(player_data.get('kd_ratio', 0) / 2.0, 2.0)
            elif title.category == TitleCategory.SKILL:
                score += min(player_data.get('avg_pw_rating', 0) / 2.0, 2.0)
            elif title.category in [TitleCategory.TEAMWORK, TitleCategory.ACHIEVEMENT]:
                # 相对比较称号根据排名调整分数
                if all_players_data:
                    score += self._calculate_relative_score(title, player_data, all_players_data)
        else:
            # 反面称号根据相关数据值调整分数
            if title.category == TitleCategory.SURVIVAL:
                score += min(player_data.get('total_deaths', 0) / 100, 2.0)
            elif title.category in [TitleCategory.KILLING, TitleCategory.SKILL]:
                # 相对比较称号根据排名调整分数
                if all_players_data:
                    score += self._calculate_relative_score(title, player_data, all_players_data)
        
        return score
    
    def _calculate_relative_score(self, title: Title, player_data: Dict, all_players_data: List[Dict]) -> float:
        """计算相对比较称号的分数"""
        # 根据称号名称确定比较的字段
        field_mapping = {
            '击杀之王': 'total_kills',
            '死亡之王': 'total_deaths', 
            '评分之王': 'avg_pw_rating',
            '伤害之王': 'avg_adpr',
            '爆头之王': 'avg_headshot_ratio',
            '助攻之王': 'total_assists',
            'MVP之王': 'match_mvp_count',
            '胜率之王': 'win_rate',
            '多杀之王': 'total_multi_kills',
        }
        
        field_name = field_mapping.get(title.name)
        if not field_name:
            return 0.0
        
        player_value = player_data.get(field_name, 0)
        all_values = [p.get(field_name, 0) for p in all_players_data]
        
        # 计算相对排名分数
        relative_rank = self._calculate_relative_rank(player_value, all_values, 
                                                    reverse=title.title_type == TitleType.POSITIVE)
        
        # 极值称号额外加分
        if "之王" in title.name:
            is_extreme = self._is_extreme_value(player_value, all_values, 
                                              is_max=title.title_type == TitleType.POSITIVE)
            if is_extreme:
                return 3.0 + relative_rank * 2.0
        
        return relative_rank * 2.0
    
    def get_best_titles(self, player_data: Dict, max_titles: int = None, all_players_data: List[Dict] = None) -> List[Title]:
        """
        获取玩家最佳称号
        
        Args:
            player_data: 玩家数据字典
            max_titles: 最大返回称号数量，None表示使用配置中的默认值
            all_players_data: 所有玩家数据列表，用于相对比较
            
        Returns:
            最佳称号列表
        """
        if max_titles is None:
            max_titles = MAX_TITLES_PER_PLAYER
            
        qualified_titles = self.calculate_titles(player_data, all_players_data)
        
        # 按类型分组
        positive_titles = []
        negative_titles = []
        neutral_titles = []
        
        for title, score in qualified_titles:
            if title.title_type == TitleType.POSITIVE:
                positive_titles.append((title, score))
            elif title.title_type == TitleType.NEGATIVE:
                negative_titles.append((title, score))
            else:
                neutral_titles.append((title, score))
        
        # 选择最佳称号
        result = []
        seen_titles = set()
        
        # 优先选择高优先级的正面称号
        for title, score in positive_titles:
            if (len(result) < max_titles and 
                title.name not in seen_titles and 
                len([t for t in result if t.title_type == TitleType.POSITIVE]) < MAX_POSITIVE_TITLES and
                title.priority >= TITLE_PRIORITY_THRESHOLD):
                seen_titles.add(title.name)
                result.append(title)
        
        # 如果还有空间，选择高优先级的反面称号
        for title, score in negative_titles:
            if (len(result) < max_titles and 
                title.name not in seen_titles and 
                len([t for t in result if t.title_type == TitleType.NEGATIVE]) < MAX_NEGATIVE_TITLES and
                title.priority >= TITLE_PRIORITY_THRESHOLD):
                seen_titles.add(title.name)
                result.append(title)
        
        # 如果还有空间，选择中性称号
        for title, score in neutral_titles:
            if (len(result) < max_titles and 
                title.name not in seen_titles and
                title.priority >= TITLE_PRIORITY_THRESHOLD):
                seen_titles.add(title.name)
                result.append(title)
        
        # 如果仍然没有足够的称号，降低优先级要求
        if len(result) < max_titles:
            all_remaining = []
            for title, score in qualified_titles:
                if title.name not in seen_titles:
                    all_remaining.append((title, score))
            
            # 按优先级和分数排序
            all_remaining.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
            
            for title, score in all_remaining:
                if len(result) < max_titles:
                    seen_titles.add(title.name)
                    result.append(title)
        
        return result
    
    def get_title_statistics(self, all_players_data: List[Dict]) -> Dict:
        """
        获取称号统计信息
        
        Args:
            all_players_data: 所有玩家数据列表
            
        Returns:
            称号统计信息
        """
        stats = {
            'total_players': len(all_players_data),
            'title_distribution': {},
            'category_distribution': {}
        }
        
        for player_data in all_players_data:
            titles = self.get_best_titles(player_data, max_titles=1, all_players_data=all_players_data)
            if titles:
                title = titles[0]
                stats['title_distribution'][title.name] = stats['title_distribution'].get(title.name, 0) + 1
                stats['category_distribution'][title.category.value] = stats['category_distribution'].get(title.category.value, 0) + 1
        
        return stats


# 全局称号系统实例
title_system = RefactoredTitleSystem()
