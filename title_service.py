"""Application service for calculating and persisting season titles."""

from typing import Dict, List, Optional

from ajlog import logger
from cache_service import invalidate_season
from database import MatchPlayer, Player, PlayerTitle
from title_system import Title, title_system


class RefactoredTitleService:
    def __init__(self):
        self.title_system = title_system

    def load_players_data(
        self,
        cup_name: str,
        play_day: str = None,
        *,
        include_history: bool = True,
    ) -> List[Dict]:
        """Load comparable player aggregates for one season or match day."""
        query = MatchPlayer.select(MatchPlayer.player_id).where(MatchPlayer.cup_name == cup_name).distinct()
        if play_day:
            query = query.where(MatchPlayer.play_day == play_day)

        player_ids = Player.canonical_ids(record.player_id for record in query)
        aggregate_map = MatchPlayer.get_match_exploits(cup_name, player_ids, play_day)
        players_data = []
        for player_id in player_ids:
            data = aggregate_map.get(str(player_id))
            if not data:
                continue
            data["player_id"] = player_id
            players_data.append(data)

        if include_history and not play_day:
            days = sorted(MatchPlayer.get_cup_day_set(cup_name) or [])
            history_by_player = {str(player_id): [] for player_id in player_ids}
            day_map = MatchPlayer.get_match_exploits_by_day(cup_name, player_ids)
            for day in days:
                for player_id in player_ids:
                    day_data = day_map.get((str(player_id), day))
                    if day_data:
                        history_by_player[str(player_id)].append(day_data)
            for data in players_data:
                data["day_history"] = history_by_player.get(str(data['player_id']), [])

        return players_data

    def build_title_rows(self, player_data: Dict, all_players_data: List[Dict]) -> List[Dict]:
        """Return API-shaped title rows with dynamic evidence descriptions."""
        rows = []
        for title in self.title_system.get_best_titles(player_data, all_players_data=all_players_data):
            definition = self.get_title_by_name(title.name)
            rows.append({
                "title_name": title.name,
                "title_description": title.description,
                "title_summary": definition.description if definition else "赛季数据画像",
                "title_category": title.category.value,
                "title_type": title.title_type.value,
                "title_priority": title.priority,
                "title_score": self.title_system._calculate_title_score(title, player_data, all_players_data),
                "title_slot": title.slot.value,
            })
        return rows

    @staticmethod
    def _storage_rows(title_rows: List[Dict]) -> List[Dict]:
        return [{
            "name": row["title_name"],
            "description": row["title_description"],
            "category": row["title_category"],
            "type": row["title_type"],
            "priority": row["title_priority"],
            "score": row["title_score"],
        } for row in title_rows]

    def calculate_and_save_titles(self, cup_name: str, play_day: str = None) -> bool:
        try:
            all_players_data = self.load_players_data(cup_name, play_day)
            if not all_players_data:
                logger.info(f"赛季 {cup_name} 暂无可计算称号的数据")
                return False

            success_count = 0
            for player_data in all_players_data:
                rows = self.build_title_rows(player_data, all_players_data)
                if PlayerTitle.update_player_titles(
                    player_data["player_id"], cup_name, play_day, self._storage_rows(rows)
                ):
                    success_count += 1
                    logger.info(
                        f"成功为玩家 {player_data['player_id']} 计算并保存称号: "
                        f"{[row['title_name'] for row in rows]}"
                    )

            logger.info(f"称号计算完成: {success_count}/{len(all_players_data)} 个玩家成功")
            invalidate_season(cup_name, external=False)
            return success_count == len(all_players_data)
        except Exception as exc:
            logger.error(f"计算并保存称号失败: {exc}")
            return False

    def get_player_titles(self, player_id: str, cup_name: str = None, play_day: str = None) -> List[Dict]:
        return PlayerTitle.get_player_titles(player_id, cup_name, play_day)

    def get_all_players_titles(self, cup_name: str, play_day: str = None) -> Dict[str, List[Dict]]:
        result = {}
        for data in self.load_players_data(cup_name, play_day, include_history=False):
            titles = self.get_player_titles(data["player_id"], cup_name, play_day)
            if titles:
                result[data["player_id"]] = titles
        return result

    def recalculate_titles_for_player(self, player_id: str, cup_name: str, play_day: str = None) -> bool:
        try:
            all_players_data = self.load_players_data(cup_name, play_day)
            player_data = next((data for data in all_players_data if data["player_id"] == player_id), None)
            if not player_data:
                logger.warning(f"未找到玩家 {player_id} 的数据")
                return False
            rows = self.build_title_rows(player_data, all_players_data)
            return PlayerTitle.update_player_titles(
                player_id, cup_name, play_day, self._storage_rows(rows)
            )
        except Exception as exc:
            logger.error(f"重新计算玩家 {player_id} 称号失败: {exc}")
            return False

    def get_title_by_name(self, title_name: str) -> Optional[Title]:
        return next((title for title in self.title_system.titles if title.name == title_name), None)

    def get_titles_by_category(self, category: str) -> List[Title]:
        return [title for title in self.title_system.titles if title.category.value == category]

    def get_titles_by_type(self, title_type: str) -> List[Title]:
        return [title for title in self.title_system.titles if title.title_type.value == title_type]

    def get_title_statistics(self, cup_name: str, play_day: str = None) -> Dict:
        return self.title_system.get_title_statistics(self.load_players_data(cup_name, play_day))

    def get_title_distribution_stats(self, cup_name: str, play_day: str = None) -> Dict:
        all_titles = self.get_all_players_titles(cup_name, play_day)
        counts = [len(titles) for titles in all_titles.values()]
        return {
            "total_players": len(self.load_players_data(cup_name, play_day, include_history=False)),
            "players_with_titles": len(all_titles),
            "total_titles": sum(counts),
            "avg_titles_per_player": round(sum(counts) / len(counts), 2) if counts else 0,
            "players_with_multiple_titles": sum(count > 1 for count in counts),
            "max_titles_per_player": max(counts, default=0),
        }


title_service = RefactoredTitleService()
