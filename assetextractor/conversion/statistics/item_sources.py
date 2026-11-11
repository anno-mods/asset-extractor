"""Item source tracking and discovery."""

from assetextractor.conversion.statistics.constants import MAX_CONTRACT_SCORE
from assetextractor.conversion.statistics.quest_tracking import QuestTracker
from assetextractor.conversion.statistics.utils import SourceDict, SourceInfo, SourceType, get_source_display_name
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import Attribute, ListAttribute
from assetextractor.parsing.core.texts import TextCache

# Sequence actions that hand an item to the player as a quest reward
QUEST_REWARD_ACTIONS = ("ActionAddGoodsToItemContainer", "ActionAddItemToMetaStorage")

# Source types shown in the CSV; achievement, function and trigger references are not real sources
DISPLAYED_SOURCE_TYPES = ("selling", "contracts", "research", "quest", "drops", "festival", "subjugated", "colosseum")

# "Asset Pool All HoF Specialists", referenced by StatisticsMenu.HallOfFame.BackupOfflinePool
HALL_OF_FAME_POOL_GUID = 182615


class ItemSourceTracker:
    """Discover all sources for an item across 11 source types."""

    def __init__(self, assets: AssetCache, texts: TextCache, quest_tracker: QuestTracker):
        """Initialize the item source tracker.

        Args:
            assets: Asset cache for looking up assets
            texts: Text cache for localized text
            quest_tracker: Quest tracker for finding parent quests
        """
        self.assets = assets
        self.texts = texts
        self.quest_tracker = quest_tracker
        self._processed_pools: set[Asset] = set()

    def find_all_sources(self, item: Asset) -> dict[str, list[SourceType]]:
        """Discover all sources for an item.

        Args:
            item: The item asset to find sources for

        Returns:
            Dict mapping source types to lists of source dicts/SourceInfo
        """
        # Clear pool cache for each item
        self._processed_pools.clear()

        sources: dict[str, list[SourceType]] = {
            "selling": [],
            "contracts": [],
            "research": [],
            "quest": [],
            "drops": [],
            "achievement": [],
            "festival": [],
            "function": [],
            "trigger": [],
            "subjugated": [],
            "colosseum": [],
        }

        # Find pool-based sources (pass sources dict to preserve quest deduplication within pool sources)
        self._find_pool_sources(item, sources)

        # Find reference-based sources (NO deduplication with pool sources - matches original behavior)
        ref_sources = self._find_reference_sources(item)
        for source_type, source_list in ref_sources.items():
            sources[source_type].extend(source_list)

        # Story items created by the game engine have no explicit reward action; they are only
        # bound to or swapped in by their quest, so consult those links only as a last resort.
        if not any(sources[source_type] for source_type in DISPLAYED_SOURCE_TYPES):
            sources["quest"].extend(self._find_quest_binding_sources(item))

        return sources

    def _find_story_line(self, start: Asset, max_depth: int = 12) -> Asset | None:
        """Breadth-first search up the reference chain for the enclosing StoryLine.

        Args:
            start: The asset to start searching from
            max_depth: Maximum number of reference hops

        Returns:
            StoryLine asset if found, None otherwise
        """
        visited = {start.guid}
        frontier = [start]
        for _ in range(max_depth):
            next_frontier: list[Asset] = []
            for current in frontier:
                for parent in (ref.source for ref in getattr(current, "referenced_by", {}).values()):
                    if parent.guid in visited:
                        continue
                    if parent.template.name == "StoryLine":
                        return parent
                    visited.add(parent.guid)
                    next_frontier.append(parent)
            frontier = next_frontier
            if not frontier:
                break
        return None

    def _find_quest_binding_sources(self, item: Asset) -> list[SourceType]:
        """Find quests that bind this item or swap it in as a replacement item.

        Args:
            item: The item asset

        Returns:
            Quest sources, deduplicated by quest
        """
        found: dict[int, SourceType] = {}
        for weighted_ref in getattr(item, "referenced_by", {}).values():
            path = weighted_ref.path or ""
            is_binding = "ActionBindItemToQuest" in path or ("ActionReplaceItem" in path and "NewItem" in path)
            if not is_binding:
                continue
            quest = self.quest_tracker.find_quest(weighted_ref.source) or self._find_story_line(weighted_ref.source)
            if quest is not None and quest.guid not in found:
                found[quest.guid] = SourceDict(
                    name=get_source_display_name(quest, self.texts), guid=quest.guid, sequence=weighted_ref.source.guid
                )
        return list(found.values())

    def _find_pool_sources(self, item: Asset, sources: dict[str, list[SourceType]]) -> None:
        """Find sources from pool references.

        Args:
            item: The item asset
            sources: Dict to populate with sources (modified in place)
        """
        if not hasattr(item, "in_reward_pool"):
            return

        for pool_guid, ref in item.in_reward_pool.items():
            pool = self.assets[pool_guid]

            if pool is None or pool in self._processed_pools:
                continue

            if not hasattr(pool, "referenced_by"):
                continue

            # Check all assets referencing this pool
            for pool_ref in pool.referenced_by.values():
                source = pool_ref.source
                template = source.template.name

                # Categorize by template and path
                if "Participant" in template and "3rdParty" in template:
                    if "ShipDropRewardPool" in pool_ref.path:
                        sources["drops"].append(
                            SourceInfo(
                                guid=source.guid,
                                name=get_source_display_name(source, self.texts),
                                probability=ref.weight,
                            )
                        )
                    elif "OfferedItems" in pool_ref.path:
                        sources["selling"].append(
                            SourceInfo(
                                guid=source.guid,
                                name=get_source_display_name(source, self.texts),
                                probability=ref.weight,
                            )
                        )
                    elif "ContractProvider" in pool_ref.path:
                        prob = self._process_contract_rewards(source, item)
                        if prob is not None:
                            sources["contracts"].append(
                                SourceInfo(
                                    guid=source.guid, name=get_source_display_name(source, self.texts), probability=prob
                                )
                            )

                elif template == "Tech":
                    sources["research"].append(
                        SourceInfo(
                            guid=source.guid, name=get_source_display_name(source, self.texts), probability=ref.weight
                        )
                    )

                elif template == "Achievement":
                    sources["achievement"].append(
                        SourceInfo(
                            guid=source.guid, name=get_source_display_name(source, self.texts), probability=ref.weight
                        )
                    )

                elif template == "Festival":
                    sources["festival"].append(
                        SourceInfo(
                            guid=source.guid, name=get_source_display_name(source, self.texts), probability=ref.weight
                        )
                    )

                elif template == "Function":
                    sources["function"].append(
                        SourceInfo(
                            guid=source.guid, name=get_source_display_name(source, self.texts), probability=ref.weight
                        )
                    )

                elif template in ("Trigger", "Gate"):
                    sources["trigger"].append(
                        SourceInfo(
                            guid=source.guid, name=get_source_display_name(source, self.texts), probability=ref.weight
                        )
                    )

                elif "Objective" in template:
                    quest = self.quest_tracker.find_quest(source)
                    if quest is not None:
                        sources["quest"].append(
                            SourceInfo(
                                guid=quest.guid, name=get_source_display_name(quest, self.texts), probability=ref.weight
                            )
                        )

    def _find_reference_sources(self, item: Asset) -> dict[str, list[SourceType]]:
        """Find sources from direct references.

        Args:
            item: The item asset

        Returns:
            Dict mapping source types to lists of source dicts
        """
        sources: dict[str, list[SourceType]] = {"quest": [], "subjugated": [], "colosseum": []}

        if not hasattr(item, "referenced_by"):
            return sources

        for weighted_ref in item.referenced_by.values():
            source = weighted_ref.source

            # Quest sequences
            if (
                "Sequence" in source.template.name
                and weighted_ref.path
                and any(action in weighted_ref.path for action in QUEST_REWARD_ACTIONS)
            ):
                quest = self.quest_tracker.find_quest(source)
                if quest is not None:
                    sources["quest"].append(
                        SourceDict(
                            name=get_source_display_name(quest, self.texts), guid=quest.guid, sequence=source.guid
                        )
                    )

            # Quest objectives with rewards
            if "Objective" in source.template.name and weighted_ref.path and "Reward" in weighted_ref.path:
                quest = self.quest_tracker.find_quest(source)
                if quest is not None:
                    sources["quest"].append(
                        SourceDict(
                            name=get_source_display_name(quest, self.texts),
                            guid=quest.guid,
                            objective=source.guid,
                            probability=weighted_ref.weight,
                        )
                    )

            # Rival defeat items
            if (
                weighted_ref.path
                and "ItemGainedWhenDefeated" in weighted_ref.path
                and "Participant 2ndParty (Rival)" in source.template.name
            ):
                sources["subjugated"].append(
                    SourceDict(name=get_source_display_name(source, self.texts), guid=source.guid)
                )

            # Colosseum event items
            if (
                source.template.name == "Decision"
                and weighted_ref.path
                and "ActionAddGoodsToItemContainer" in weighted_ref.path
            ):
                is_colosseum, parent_decision = self._is_colosseum_decision(source)

                if is_colosseum:
                    decision_guid = parent_decision.guid if parent_decision else source.guid
                    decision = self.assets.get(decision_guid)
                    name = get_source_display_name(decision, self.texts) if decision is not None else None

                    already_added = any(
                        s.get("decision_guid") == decision_guid for s in sources["colosseum"] if isinstance(s, dict)
                    )
                    if not already_added:
                        sources["colosseum"].append(
                            SourceDict(
                                name=name,  # Decision name (e.g., "The Mysterious Murmillo Part II, Act I")
                                guid=98164,  # Colosseum Story Questpool GUID
                                decision_guid=decision_guid,
                            )
                        )
                else:
                    # It's a quest decision. The decision asset itself is the source.
                    # Do not try to find a parent quest, as it can be incorrect for standalone decisions.
                    already_added = any(
                        s.get("objective") == source.guid for s in sources["quest"] if isinstance(s, dict)
                    )
                    if not already_added:
                        sources["quest"].append(
                            SourceDict(
                                name=get_source_display_name(source, self.texts),
                                guid=source.guid,
                                objective=source.guid,
                                probability=weighted_ref.weight,
                            )
                        )

        return sources

    def _process_contract_rewards(self, trader: Asset, item: Asset) -> float | None:
        """Calculate contract reward probability for an item.

        Args:
            trader: The trader asset
            item: The item asset

        Returns:
            Probability (0.0-1.0) or None if not found
        """
        reward_list = trader.find("ContractProvider.ItemRewards")
        if not isinstance(reward_list, ListAttribute):
            return None

        probability = 0.0
        for element in reward_list:
            min_range_attr = element.find("MinRange")
            max_range_attr = element.find("MaxRange")

            if not isinstance(min_range_attr, Attribute) or not isinstance(max_range_attr, Attribute):
                continue

            min_range = min_range_attr()
            max_range = max_range_attr()

            if not isinstance(min_range, int | float) or not isinstance(max_range, int | float):
                continue

            lower = min(float(min_range), float(MAX_CONTRACT_SCORE))
            upper = min(float(max_range), float(MAX_CONTRACT_SCORE))

            pool = element.find_ref("ItemRewardPool")

            if pool is None:
                continue

            probability += (upper - lower) / MAX_CONTRACT_SCORE * pool.pool_assets().get(item, 0)

            self._processed_pools.add(pool)

        return probability if probability > 0 else None

    def _is_colosseum_decision(self, decision: Asset) -> tuple[bool, Asset | None]:
        """Check if a decision is related to the Colosseum.

        Args:
            decision: The decision asset

        Returns:
            Tuple of (is_colosseum, parent_decision)
        """
        # Check if this decision has "Colosseum" in the name
        if "Colosseum" in decision.name:
            return True, decision

        # Check if this decision is referenced by a Colosseum decision
        if hasattr(decision, "referenced_by"):
            for parent_ref in decision.referenced_by.values():
                parent = parent_ref.source
                if parent.template.name == "Decision" and "Colosseum" in parent.name:
                    return True, parent

        return False, None

    def is_hall_of_fame_item(self, asset: Asset) -> bool:
        """Check if item is a Hall of Fame item by name pattern or Hall of Fame pool membership.

        Args:
            asset: The item asset

        Returns:
            True if this is a Hall of Fame item
        """
        if "HallOfFame" in asset.name:
            return True
        referenced_by = getattr(asset, "referenced_by", None)
        return bool(referenced_by) and HALL_OF_FAME_POOL_GUID in referenced_by
