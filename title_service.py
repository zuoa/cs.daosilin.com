"""
重构后的称号服务 - 使用新的精简称号系统
"""

from typing import Dict, List, Optional

from ajlog import logger
from database import PlayerTitle, MatchPlayer
from title_system import title_system, Title


class RefactoredTitleService:
    """重构后的称号服务类"""

    def __init__(self):
        self.title_system = title_system

    def calculate_and_save_titles(self, cup_name: str, play_day: str = None) -> bool:
        """
        计算并保存所有玩家的称号
        
        Args:
            cup_name: 杯赛名称
            play_day: 比赛日期，None表示整个杯赛
            
        Returns:
            是否成功
        """
        try:
            # 获取所有玩家数据
            filter_params = {'cup_name': cup_name}
            if play_day:
                filter_params['play_day'] = play_day

            players = MatchPlayer.filter_records(**filter_params)
            player_ids = list(set([player['player_id'] for player in players]))

            # 获取所有玩家的完整数据用于相对比较
            all_players_data = []
            for player_id in player_ids:
                player_data = MatchPlayer.get_match_exploit(cup_name, player_id, play_day)
                if player_data:
                    player_data['player_id'] = player_id
                    player_data['is_champion'] = False  # 这里需要从其他地方获取
                    player_data['is_runner_up'] = False  # 这里需要从其他地方获取
                    all_players_data.append(player_data)

            success_count = 0
            total_count = len(player_ids)

            for player_data in all_players_data:
                try:
                    player_id = player_data['player_id']

                    # 使用新的称号系统，传递所有玩家数据用于相对比较
                    best_titles = self.title_system.get_best_titles(player_data, all_players_data=all_players_data)

                    if best_titles:
                        # 转换为数据库格式
                        titles_data = []
                        for title in best_titles:
                            # 重新计算分数
                            score = self.title_system._calculate_title_score(title, player_data, all_players_data)
                            titles_data.append({
                                'name': title.name,
                                'description': title.description,
                                'category': title.category.value,
                                'type': title.title_type.value,
                                'priority': title.priority,
                                'score': score
                            })

                        # 保存到数据库
                        if PlayerTitle.update_player_titles(player_id, cup_name, play_day, titles_data):
                            success_count += 1
                            logger.info(f"成功为玩家 {player_id} 计算并保存称号: {[t.name for t in best_titles]}")
                        else:
                            logger.error(f"保存玩家 {player_id} 称号失败")
                    else:
                        logger.info(f"玩家 {player_id} 没有符合条件的称号")

                except Exception as e:
                    logger.error(f"处理玩家 {player_id} 称号时出错: {str(e)}")
                    continue

            logger.info(f"称号计算完成: {success_count}/{total_count} 个玩家成功")
            return success_count > 0

        except Exception as e:
            logger.error(f"计算并保存称号失败: {str(e)}")
            return False


    def get_all_players_titles(self, cup_name: str, play_day: str = None) -> Dict[str, List[Dict]]:
        """
        获取所有玩家的称号
        
        Args:
            cup_name: 杯赛名称
            play_day: 比赛日期
            
        Returns:
            玩家ID到称号列表的映射
        """
        try:
            # 获取所有玩家
            filter_params = {'cup_name': cup_name}
            if play_day:
                filter_params['play_day'] = play_day

            players = MatchPlayer.filter_records(**filter_params)
            player_ids = list(set([player['player_id'] for player in players]))

            result = {}
            for player_id in player_ids:
                titles = self.get_player_titles(player_id, cup_name, play_day)
                if titles:
                    result[player_id] = titles

            return result

        except Exception as e:
            logger.error(f"获取所有玩家称号失败: {str(e)}")
            return {}

    def get_title_statistics(self, cup_name: str, play_day: str = None) -> Dict:
        """
        获取称号统计信息
        
        Args:
            cup_name: 杯赛名称
            play_day: 比赛日期
            
        Returns:
            称号统计信息
        """
        try:
            # 获取所有玩家数据
            filter_params = {'cup_name': cup_name}
            if play_day:
                filter_params['play_day'] = play_day

            players = MatchPlayer.filter_records(**filter_params)
            player_ids = list(set([player['player_id'] for player in players]))

            all_players_data = []
            for player_id in player_ids:
                player_data = MatchPlayer.get_match_exploit(cup_name, player_id, play_day)
                if player_data:
                    player_data['player_id'] = player_id
                    all_players_data.append(player_data)

            return self.title_system.get_title_statistics(all_players_data)

        except Exception as e:
            logger.error(f"获取称号统计信息失败: {str(e)}")
            return {}

    def recalculate_titles_for_player(self, player_id: str, cup_name: str, play_day: str = None) -> bool:
        """
        重新计算指定玩家的称号
        
        Args:
            player_id: 玩家ID
            cup_name: 杯赛名称
            play_day: 比赛日期
            
        Returns:
            是否成功
        """
        try:
            # 获取玩家数据
            player_data = MatchPlayer.get_match_exploit(cup_name, player_id, play_day)
            if not player_data:
                logger.warning(f"未找到玩家 {player_id} 的数据")
                return False

            # 添加额外信息
            player_data['player_id'] = player_id
            player_data['is_champion'] = False  # 这里需要从其他地方获取
            player_data['is_runner_up'] = False  # 这里需要从其他地方获取

            # 使用新的称号系统
            best_titles = self.title_system.get_best_titles(player_data)

            if best_titles:
                # 转换为数据库格式
                titles_data = []
                for title in best_titles:
                    # 重新计算分数
                    score = self.title_system._calculate_title_score(title, player_data)
                    titles_data.append({
                        'name': title.name,
                        'description': title.description,
                        'category': title.category.value,
                        'type': title.title_type.value,
                        'priority': title.priority,
                        'score': score
                    })

                # 保存到数据库
                if PlayerTitle.update_player_titles(player_id, cup_name, play_day, titles_data):
                    logger.info(f"成功重新计算玩家 {player_id} 的称号: {[t.name for t in best_titles]}")
                    return True
                else:
                    logger.error(f"保存玩家 {player_id} 称号失败")
                    return False
            else:
                # 删除该玩家的所有称号
                PlayerTitle.delete().where(
                    PlayerTitle.player_id == player_id,
                    PlayerTitle.cup_name == cup_name,
                    PlayerTitle.play_day == play_day
                ).execute()
                logger.info(f"玩家 {player_id} 没有符合条件的称号，已清除旧称号")
                return True

        except Exception as e:
            logger.error(f"重新计算玩家 {player_id} 称号失败: {str(e)}")
            return False

    def get_title_by_name(self, title_name: str) -> Optional[Title]:
        """
        根据称号名称获取称号定义
        
        Args:
            title_name: 称号名称
            
        Returns:
            称号定义，如果不存在则返回None
        """
        for title in self.title_system.titles:
            if title.name == title_name:
                return title
        return None

    def get_titles_by_category(self, category: str) -> List[Title]:
        """
        根据分类获取称号列表
        
        Args:
            category: 称号分类
            
        Returns:
            该分类的称号列表
        """
        return [title for title in self.title_system.titles if title.category.value == category]

    def get_titles_by_type(self, title_type: str) -> List[Title]:
        """
        根据类型获取称号列表
        
        Args:
            title_type: 称号类型 (positive/negative/neutral)
            
        Returns:
            该类型的称号列表
        """
        return [title for title in self.title_system.titles if title.title_type.value == title_type]

    def get_title_distribution_stats(self, cup_name: str, play_day: str = None) -> Dict:
        """
        获取称号分布统计信息
        
        Args:
            cup_name: 杯赛名称
            play_day: 比赛日期
            
        Returns:
            称号分布统计信息
        """
        try:
            # 获取所有玩家称号
            all_titles = self.get_all_players_titles(cup_name, play_day)

            stats = {
                'total_players': len(all_titles),
                'players_with_titles': 0,
                'total_titles': 0,
                'avg_titles_per_player': 0,
                'title_type_distribution': {'positive': 0, 'negative': 0, 'neutral': 0},
                'title_category_distribution': {},
                'players_with_multiple_titles': 0,
                'max_titles_per_player': 0
            }

            for player_id, titles in all_titles.items():
                if titles:
                    stats['players_with_titles'] += 1
                    stats['total_titles'] += len(titles)
                    stats['max_titles_per_player'] = max(stats['max_titles_per_player'], len(titles))

                    if len(titles) > 1:
                        stats['players_with_multiple_titles'] += 1

                    for title in titles:
                        # 统计称号类型
                        title_type = title.get('type', 'neutral')
                        if title_type in stats['title_type_distribution']:
                            stats['title_type_distribution'][title_type] += 1

                        # 统计称号分类
                        category = title.get('category', 'unknown')
                        stats['title_category_distribution'][category] = stats['title_category_distribution'].get(category, 0) + 1

            if stats['players_with_titles'] > 0:
                stats['avg_titles_per_player'] = round(stats['total_titles'] / stats['players_with_titles'], 2)

            return stats

        except Exception as e:
            logger.error(f"获取称号分布统计失败: {str(e)}")
            return {}

    def compare_with_old_system(self, cup_name: str, play_day: str = None) -> Dict:
        """
        对比新旧称号系统的效果
        
        Args:
            cup_name: 杯赛名称
            play_day: 比赛日期
            
        Returns:
            对比结果
        """
        try:
            # 获取所有玩家数据
            filter_params = {'cup_name': cup_name}
            if play_day:
                filter_params['play_day'] = play_day

            players = MatchPlayer.filter_records(**filter_params)
            player_ids = list(set([player['player_id'] for player in players]))

            all_players_data = []
            for player_id in player_ids:
                player_data = MatchPlayer.get_match_exploit(cup_name, player_id, play_day)
                if player_data:
                    player_data['player_id'] = player_id
                    player_data['is_champion'] = False
                    player_data['is_runner_up'] = False
                    all_players_data.append(player_data)

            # 使用新系统计算称号
            new_stats = self.get_title_distribution_stats(cup_name, play_day)

            # 统计新系统的称号分布
            new_title_counts = {}
            for player_data in all_players_data:
                titles = self.title_system.get_best_titles(player_data, all_players_data=all_players_data)
                for title in titles:
                    new_title_counts[title.name] = new_title_counts.get(title.name, 0) + 1

            comparison = {
                'new_system_stats': new_stats,
                'new_title_distribution': new_title_counts,
                'total_titles_in_new_system': len(self.title_system.titles),
                'players_analyzed': len(all_players_data)
            }

            return comparison

        except Exception as e:
            logger.error(f"对比新旧称号系统失败: {str(e)}")
            return {}


# 全局称号服务实例
title_service = RefactoredTitleService()
