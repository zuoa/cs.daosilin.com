"""
称号系统 - 基于多维度数据分析的玩家称号分配系统
支持正面和反面称号，根据玩家表现数据动态计算
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
    # 正面分类
    KILLING = "killing"           # 击杀相关
    SURVIVAL = "survival"         # 生存相关
    TEAMWORK = "teamwork"         # 团队合作
    SKILL = "skill"              # 技能相关
    ACHIEVEMENT = "achievement"   # 成就相关
    CONSISTENCY = "consistency"   # 稳定性相关
    
    # 反面分类
    DEATH = "death"              # 死亡相关
    MISTAKE = "mistake"          # 失误相关
    INCONSISTENCY = "inconsistency"  # 不稳定相关
    LUCK = "luck"                # 运气相关


@dataclass
class Title:
    """称号定义"""
    name: str
    description: str
    category: TitleCategory
    title_type: TitleType
    condition_func: callable
    priority: int = 1  # 优先级，数字越大优先级越高
    rarity: str = "common"  # 稀有度：common, rare, epic, legendary


class TitleSystem:
    """称号系统核心类"""
    
    def __init__(self):
        self.titles = self._initialize_titles()
    
    def _initialize_titles(self) -> List[Title]:
        """初始化所有称号定义"""
        titles = []
        
        # ========== 正面称号 ==========
        
        # 击杀相关正面称号
        titles.extend([
            Title(
                name="爆头大师",
                description="爆头率超过60%的精准射手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('avg_headshot_ratio', 0) > 0.6,
                priority=3,
                rarity="rare"
            ),
            Title(
                name="连杀机器",
                description="多杀次数最多的玩家",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_multi_kills', 0) > 50,
                priority=2,
                rarity="common"
            ),
            Title(
                name="AWP之神",
                description="AWP击杀数最多的狙击手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_snipe_num', 0) > 30,
                priority=3,
                rarity="rare"
            ),
            Title(
                name="首杀王",
                description="首杀次数最多的突破手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_first_kills', 0) > 20,
                priority=2,
                rarity="common"
            ),
            Title(
                name="五杀狂魔",
                description="完成过5杀的传奇选手",
                category=TitleCategory.KILLING,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_5k', 0) > 2,
                priority=5,
                rarity="legendary"
            ),
        ])
        
        # 生存相关正面称号
        titles.extend([
            Title(
                name="不死鸟",
                description="K/D比超过2.0的生存专家",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('kd_ratio', 0) > 2.0,
                priority=4,
                rarity="epic"
            ),
            Title(
                name="残局之王",
                description="1V5胜利次数最多的选手",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_1v5', 0) > 0,
                priority=5,
                rarity="legendary"
            ),
            Title(
                name="护甲破坏者",
                description="护甲伤害最高的选手",
                category=TitleCategory.SURVIVAL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('avg_damage_armar', 0) > 400,
                priority=2,
                rarity="common"
            ),
        ])
        
        # 团队合作正面称号
        titles.extend([
            Title(
                name="团队大脑",
                description="助攻数最多的团队指挥",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_assists', 0) > 50,
                priority=2,
                rarity="common"
            ),
            Title(
                name="闪光专家",
                description="闪光成功率最高的辅助",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('flash_success_ratio', 0) > 0.7,
                priority=2,
                rarity="common"
            ),
            Title(
                name="投掷物大师",
                description="投掷物使用最多的战术家",
                category=TitleCategory.TEAMWORK,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_throws_count', 0) > 200,
                priority=1,
                rarity="common"
            ),
        ])
        
        # 技能相关正面称号
        titles.extend([
            Title(
                name="神枪手",
                description="命中率最高的精准射手",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('total_hit_count', 0) > 500 and data.get('total_hit_count', 0) / max(data.get('fire_count', 1), 1) > 0.3,
                priority=3,
                rarity="rare"
            ),
            Title(
                name="评分之王",
                description="PWR Rating最高的选手",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('avg_pw_rating', 0) > 1.8,
                priority=4,
                rarity="epic"
            ),
            Title(
                name="伤害机器",
                description="ADPR最高的输出手",
                category=TitleCategory.SKILL,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('avg_adpr', 0) > 120,
                priority=3,
                rarity="rare"
            ),
        ])
        
        # 成就相关正面称号
        titles.extend([
            Title(
                name="MVP收割机",
                description="MVP次数最多的明星选手",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('match_mvp_count', 0) > 5,
                priority=4,
                rarity="epic"
            ),
            Title(
                name="常胜将军",
                description="胜率超过80%的胜利者",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('win_rate', 0) > 0.8,
                priority=4,
                rarity="epic"
            ),
            Title(
                name="冠军收割者",
                description="获得过冠军的传奇选手",
                category=TitleCategory.ACHIEVEMENT,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('is_champion', False),
                priority=5,
                rarity="legendary"
            ),
        ])
        
        # 稳定性相关正面称号
        titles.extend([
            Title(
                name="稳定输出",
                description="RWS评分最稳定的选手",
                category=TitleCategory.CONSISTENCY,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('avg_rws', 0) > 15,
                priority=2,
                rarity="common"
            ),
            Title(
                name="铁人",
                description="比赛场次最多的选手",
                category=TitleCategory.CONSISTENCY,
                title_type=TitleType.POSITIVE,
                condition_func=lambda data: data.get('match_count', 0) > 30,
                priority=1,
                rarity="common"
            ),
        ])
        
        # ========== 反面称号 ==========
        
        # 死亡相关反面称号
        titles.extend([
            Title(
                name="送人头王",
                description="死亡数最多的选手",
                category=TitleCategory.DEATH,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('total_deaths', 0) > 150,
                priority=1,
                rarity="common"
            ),
            Title(
                name="首死专业户",
                description="首死次数最多的选手",
                category=TitleCategory.DEATH,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('total_first_deaths', 0) > 30,
                priority=2,
                rarity="common"
            ),
            Title(
                name="脆皮鸡",
                description="K/D比低于0.5的选手",
                category=TitleCategory.DEATH,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('kd_ratio', 0) < 0.5,
                priority=3,
                rarity="rare"
            ),
        ])
        
        # 失误相关反面称号
        titles.extend([
            Title(
                name="队友杀手",
                description="队友闪光次数最多的选手",
                category=TitleCategory.MISTAKE,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('total_flash_teammate', 0) > 30,
                priority=2,
                rarity="common"
            ),
            Title(
                name="空枪王",
                description="命中率最低的选手",
                category=TitleCategory.MISTAKE,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('total_hit_count', 0) < 100 and data.get('total_hit_count', 0) / max(data.get('fire_count', 1), 1) < 0.15,
                priority=2,
                rarity="common"
            ),
        ])
        
        # 不稳定相关反面称号
        titles.extend([
            Title(
                name="神经刀",
                description="表现极不稳定的选手",
                category=TitleCategory.INCONSISTENCY,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('avg_pw_rating', 0) < 0.8,
                priority=2,
                rarity="common"
            ),
            Title(
                name="躺赢王",
                description="胜率高但个人数据差的选手",
                category=TitleCategory.INCONSISTENCY,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('win_rate', 0) > 0.6 and data.get('avg_pw_rating', 0) < 0.9,
                priority=3,
                rarity="rare"
            ),
        ])
        
        # 运气相关反面称号
        titles.extend([
            Title(
                name="倒霉蛋",
                description="胜率最低的选手",
                category=TitleCategory.LUCK,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('win_rate', 0) < 0.3,
                priority=2,
                rarity="common"
            ),
            Title(
                name="万年老二",
                description="总是获得亚军的选手",
                category=TitleCategory.LUCK,
                title_type=TitleType.NEGATIVE,
                condition_func=lambda data: data.get('is_runner_up', False) and not data.get('is_champion', False),
                priority=1,
                rarity="common"
            ),
        ])
        
        return titles
    
    def calculate_titles(self, player_data: Dict) -> List[Tuple[Title, float]]:
        """
        为玩家计算称号
        
        Args:
            player_data: 玩家数据字典
            
        Returns:
            符合条件的称号列表，按优先级排序
        """
        qualified_titles = []
        
        for title in self.titles:
            try:
                if title.condition_func(player_data):
                    # 计算称号匹配度分数
                    score = self._calculate_title_score(title, player_data)
                    qualified_titles.append((title, score))
            except Exception as e:
                # 如果计算过程中出现错误，跳过这个称号
                continue
        
        # 按优先级和分数排序
        qualified_titles.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        
        return qualified_titles
    
    def _calculate_title_score(self, title: Title, player_data: Dict) -> float:
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
        else:
            # 反面称号根据相关数据值调整分数
            if title.category == TitleCategory.DEATH:
                score += min(player_data.get('total_deaths', 0) / 100, 2.0)
            elif title.category == TitleCategory.MISTAKE:
                score += min(player_data.get('total_flash_teammate', 0) / 10, 2.0)
        
        return score
    
    def get_best_titles(self, player_data: Dict, max_titles: int = None) -> List[Title]:
        """
        获取玩家最佳称号
        
        Args:
            player_data: 玩家数据字典
            max_titles: 最大返回称号数量，None表示使用配置中的默认值
            
        Returns:
            最佳称号列表
        """
        if max_titles is None:
            max_titles = MAX_TITLES_PER_PLAYER
            
        qualified_titles = self.calculate_titles(player_data)
        
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
    
    def get_strict_titles(self, player_data: Dict) -> List[Title]:
        """
        获取玩家最严格的称号选择（每个玩家最多2个称号）
        
        Args:
            player_data: 玩家数据字典
            
        Returns:
            最严格的称号列表
        """
        qualified_titles = self.calculate_titles(player_data)
        
        if not qualified_titles:
            return []
        
        # 按优先级和分数排序
        qualified_titles.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        
        # 按类型分组
        positive_titles = [t for t in qualified_titles if t[0].title_type == TitleType.POSITIVE]
        negative_titles = [t for t in qualified_titles if t[0].title_type == TitleType.NEGATIVE]
        
        result = []
        seen_titles = set()
        
        # 优先选择最高优先级的正面称号
        if positive_titles and len(result) < MAX_TITLES_PER_PLAYER:
            best_positive = positive_titles[0]
            if best_positive[0].priority >= TITLE_PRIORITY_THRESHOLD:
                result.append(best_positive[0])
                seen_titles.add(best_positive[0].name)
        
        # 如果还有空间，选择最高优先级的反面称号
        if negative_titles and len(result) < MAX_TITLES_PER_PLAYER:
            best_negative = negative_titles[0]
            if best_negative[0].priority >= TITLE_PRIORITY_THRESHOLD:
                result.append(best_negative[0])
                seen_titles.add(best_negative[0].name)
        
        # 如果仍然没有称号，选择优先级最高的称号
        if not result:
            best_title = qualified_titles[0][0]
            result.append(best_title)
        
        return result
    
    def get_smart_titles(self, player_data: Dict) -> List[Title]:
        """
        智能选择玩家最有代表性的称号
        
        Args:
            player_data: 玩家数据字典
            
        Returns:
            智能选择的称号列表
        """
        qualified_titles = self.calculate_titles(player_data)
        
        if not qualified_titles:
            return []
        
        # 按优先级和分数排序
        qualified_titles.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        
        # 按类型分组
        positive_titles = [t for t in qualified_titles if t[0].title_type == TitleType.POSITIVE]
        negative_titles = [t for t in qualified_titles if t[0].title_type == TitleType.NEGATIVE]
        
        result = []
        seen_categories = set()
        
        # 优先选择最高优先级的正面称号
        if positive_titles:
            best_positive = positive_titles[0]
            if (best_positive[0].priority >= TITLE_PRIORITY_THRESHOLD and 
                best_positive[0].category not in seen_categories):
                result.append(best_positive[0])
                seen_categories.add(best_positive[0].category)
        
        # 如果还有空间，选择最高优先级的反面称号
        if negative_titles and len(result) < MAX_TITLES_PER_PLAYER:
            best_negative = negative_titles[0]
            if (best_negative[0].priority >= TITLE_PRIORITY_THRESHOLD and 
                best_negative[0].category not in seen_categories):
                result.append(best_negative[0])
                seen_categories.add(best_negative[0].category)
        
        # 如果仍然没有足够的称号，选择不同分类的高优先级称号
        if len(result) < MAX_TITLES_PER_PLAYER:
            for title, score in qualified_titles:
                if (len(result) < MAX_TITLES_PER_PLAYER and 
                    title.category not in seen_categories and
                    title.priority >= TITLE_PRIORITY_THRESHOLD):
                    result.append(title)
                    seen_categories.add(title.category)
        
        # 如果仍然没有称号，选择优先级最高的称号
        if not result:
            best_title = qualified_titles[0][0]
            result.append(best_title)
        
        return result
    
    def get_title_by_category(self, player_data: Dict, category: TitleCategory) -> Optional[Title]:
        """
        获取指定分类的最佳称号
        
        Args:
            player_data: 玩家数据字典
            category: 称号分类
            
        Returns:
            该分类的最佳称号，如果没有则返回None
        """
        qualified_titles = self.calculate_titles(player_data)
        
        for title, score in qualified_titles:
            if title.category == category:
                return title
        
        return None
    
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
            'rarity_distribution': {},
            'category_distribution': {}
        }
        
        for player_data in all_players_data:
            titles = self.get_best_titles(player_data, max_titles=1)
            if titles:
                title = titles[0]
                stats['title_distribution'][title.name] = stats['title_distribution'].get(title.name, 0) + 1
                stats['rarity_distribution'][title.rarity] = stats['rarity_distribution'].get(title.rarity, 0) + 1
                stats['category_distribution'][title.category.value] = stats['category_distribution'].get(title.category.value, 0) + 1
        
        return stats


# 全局称号系统实例
title_system = TitleSystem()
