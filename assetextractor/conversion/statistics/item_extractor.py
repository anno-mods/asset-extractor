"""Main orchestrator for item extraction."""

import csv
from pathlib import Path

import pandas as pd  # type: ignore

from assetextractor.conversion.statistics.boost_conditions import BoostConditionParser
from assetextractor.conversion.statistics.constants import SOURCE_TEXT_IDS
from assetextractor.conversion.statistics.item_sources import ItemSourceTracker
from assetextractor.conversion.statistics.quest_tracking import QuestTracker
from assetextractor.conversion.statistics.utils import (
    extract_boost_buffs,
    flatten_pool,
    format_all_sources_csv,
    format_buff_attributes,
    get_localized_name,
)
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import Attribute, ListAttribute, Property
from assetextractor.parsing.core.texts import StandardTextConverter


class ItemExtractor:
    """Main orchestrator for extracting items from Anno 117 assets."""

    def __init__(self, assets: AssetCache, language: str = "english"):
        """Initialize the item extractor.

        Args:
            assets: Asset cache with loaded assets
            language: Language for text localization (default: "english")
        """
        self.assets = assets
        self.texts = assets.texts
        self.texts.converter = StandardTextConverter(language)

        # Initialize all dependencies
        self.quest_tracker = QuestTracker(assets, self.texts)
        self.source_tracker = ItemSourceTracker(assets, self.texts, self.quest_tracker)
        self.boost_parser = BoostConditionParser(assets, self.texts)
        self.dlc_label_map = self._build_dlc_label_map()

    def _build_dlc_label_map(self) -> dict[int, str]:
        """Map each DLC asset GUID to a short label like 'DLC01'.

        Derives the label from the prefix of `Standard.ID` (e.g. 'DLC01_Prophecies_of_Ash'
        -> 'DLC01'); falls back to the asset name when no ID is set.
        """
        labels: dict[int, str] = {}
        uplay_template = self.assets.templates.get("UplayProduct")
        if uplay_template is None:
            return labels
        for dlc in uplay_template.assets:
            sid = dlc.find_value("Standard.ID")
            if isinstance(sid, str) and sid:
                labels[dlc.guid] = sid.split("_")[0]
            else:
                labels[dlc.guid] = dlc.name
        return labels

    def _get_version(self, asset: Asset) -> str:
        """Return space-separated DLC labels that unlock this asset, or 'base'."""
        unlocked_by = getattr(asset, "unlocked_by_dlcs", None)
        if not unlocked_by:
            return "base"
        labels = sorted({self.dlc_label_map.get(guid, str(guid)) for guid in unlocked_by})
        return " ".join(labels) if labels else "base"

    def extract_all_items(self) -> list[dict[str, str | int]]:
        """Extract all items from the asset cache.

        Returns:
            List of item dicts with all extracted data
        """
        items_data: list[dict[str, str | int]] = []
        skipped_count = 0

        for template_name in ["Item", "ItemWithBoost"]:
            if template_name not in self.assets.templates:
                print(f"Warning: Template '{template_name}' not found")
                continue

            template = self.assets.templates[template_name]
            if template is None:
                continue

            for asset in template.assets:
                try:
                    # Skip items with no references (unless they're Hall of Fame items)
                    has_pool_refs = hasattr(asset, "in_reward_pool") and asset.in_reward_pool
                    has_direct_refs = hasattr(asset, "referenced_by") and asset.referenced_by
                    is_hall_of_fame = self.source_tracker.is_hall_of_fame_item(asset)

                    # Placeholder items only used as notification icons
                    if "Fake Item" in asset.name:
                        skipped_count += 1
                        continue

                    if not (has_pool_refs or has_direct_refs or is_hall_of_fame):
                        skipped_count += 1
                        continue

                    item = {
                        "guid": asset.guid,
                        "name": get_localized_name(asset),
                        "version": self._get_version(asset),
                        "niche": "",
                        "rarity": "",
                        "trade_price": "",
                        "targets": "",
                        "buffs": "",
                        "boost_condition": "",
                        "boost_buffs": "",
                        "source": "",
                    }

                    # Get niche
                    try:
                        item_prop = asset["Item"]
                        if isinstance(item_prop, Property):
                            niche_attr = item_prop["Niche"]
                            if isinstance(niche_attr, Attribute):
                                niche = niche_attr()
                                if isinstance(niche, str):
                                    ui_cache = self.assets.properties.ui_text_cache
                                    if ui_cache is not None:
                                        niche_mapping = ui_cache.get_ui_text("ItemNiche", niche)
                                        if niche_mapping is not None and niche_mapping.text is not None:
                                            item["niche"] = niche_mapping.text()
                    except Exception:
                        pass

                    # Get rarity
                    try:
                        item_prop = asset["Item"]
                        if isinstance(item_prop, Property):
                            rarity_attr = item_prop["Rarity"]
                            if isinstance(rarity_attr, Attribute):
                                rarity = rarity_attr()
                                if isinstance(rarity, str):
                                    ui_cache = self.assets.properties.ui_text_cache
                                    if ui_cache is not None:
                                        rarity_mapping = ui_cache.get_ui_text("Rarity", rarity)
                                        if rarity_mapping is not None and rarity_mapping.text is not None:
                                            item["rarity"] = rarity_mapping.text()
                    except Exception:
                        pass

                    # Get trade price
                    try:
                        item_prop = asset["Item"]
                        if isinstance(item_prop, Property):
                            trade_price_attr = item_prop["TradePrice"]
                            if isinstance(trade_price_attr, Attribute):
                                trade_price = trade_price_attr()
                                if isinstance(trade_price, int | float):
                                    item["trade_price"] = str(int(trade_price))
                    except Exception:
                        pass

                    # Get targets (with pool name prepending)
                    try:
                        targets = asset.find("Effect.Targets")

                        if isinstance(targets, ListAttribute):
                            target_guids: list[int] = []
                            pool_name = None
                            for target in targets:
                                pool = target.find_ref("GUID")
                                target_guids.extend(flatten_pool(pool))
                                if pool_name is None and pool is not None and pool.text is not None:
                                    pool_name = pool.text()

                            if target_guids:
                                item["targets"] = self._get_target_names(target_guids)
                            if pool_name is not None:
                                item["targets"] = pool_name + (f": {item['targets']}" if target_guids else "")
                    except Exception:
                        pass

                    # Get buffs using buff_ui
                    try:
                        buffs = asset.find("Effect.Buffs")
                        if isinstance(buffs, ListAttribute):
                            buff_descriptions: list[str] = []
                            for buff in buffs:
                                buff_asset = buff.find_ref("GUID")
                                if buff_asset is not None:
                                    buff_desc = format_buff_attributes(buff_asset)
                                    if buff_desc != "No attributes":
                                        buff_descriptions.append(buff_desc)
                            if buff_descriptions:
                                item["buffs"] = " | ".join(buff_descriptions)
                    except Exception:
                        pass

                    # Get boost condition and boost buffs
                    if "ItemWithBoost" in asset.template.name:
                        try:
                            boost_condition = self.boost_parser.parse(asset)
                            if boost_condition:
                                item["boost_condition"] = boost_condition
                        except Exception:
                            pass

                        try:
                            boost_buffs = extract_boost_buffs(asset, self.assets)
                            if boost_buffs:
                                item["boost_buffs"] = boost_buffs
                        except Exception:
                            pass

                    # Get sources
                    if is_hall_of_fame:
                        hall_of_fame_text_id = SOURCE_TEXT_IDS["hall_of_fame"]
                        hall_of_fame_text = self.texts.get(hall_of_fame_text_id)
                        if hall_of_fame_text is not None:
                            item["source"] = hall_of_fame_text()
                        else:
                            item["source"] = "Hall of Fame"
                    else:
                        try:
                            sources = self.source_tracker.find_all_sources(asset)
                            sources_csv = format_all_sources_csv(sources, self.texts)
                            if sources_csv:
                                item["source"] = sources_csv
                        except Exception as e:
                            print(f"Error finding sources for {asset.guid}: {e}")

                    items_data.append(item)

                except Exception as e:
                    print(f"Error processing asset {asset.guid}: {e}")
                    continue

        print(f"Extracted {len(items_data)} items (skipped {skipped_count} items with no references)")
        return items_data

    def _get_target_names(self, target_guids: list[int]) -> str:
        """Convert list of target GUIDs to comma-separated names.

        Args:
            target_guids: List of asset GUIDs

        Returns:
            Comma-separated string of target names
        """
        names: list[str] = []
        for guid in target_guids:
            try:
                asset = self.assets[guid]
                if isinstance(asset, Asset):
                    names.append(get_localized_name(asset))
            except Exception:
                names.append(f"Unknown_{guid}")
        return ", ".join(names) if names else ""

    def save_to_csv(self, items: list[dict[str, str | int]], output_path: Path) -> None:
        """Save items data to a CSV file.

        Args:
            items: List of item dicts
            output_path: Path to output CSV file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "guid",
                "name",
                "version",
                "niche",
                "rarity",
                "trade_price",
                "targets",
                "buffs",
                "boost_condition",
                "boost_buffs",
                "source",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(items)

        print(f"Saved {len(items)} items to {output_path.absolute()}")

    def display_statistics(self, items: list[dict[str, str | int]]) -> None:
        """Display comprehensive statistics about the extracted items.

        Args:
            items: List of item dicts
        """
        df = pd.DataFrame(items)

        print("\n=== Item Statistics ===")
        print(f"Total items: {len(items)}")

        # Count by rarity
        rarity_counts = df["rarity"].value_counts()  # type: ignore
        print("\nItems by rarity:")
        for rarity, count in rarity_counts.items():  # type: ignore
            print(f"  {rarity}: {count}")

        # Items with effects
        items_with_buffs = df[df["buffs"] != ""].shape[0]  # type: ignore
        items_with_targets = df[df["targets"] != ""].shape[0]  # type: ignore
        items_with_sources = df[df["source"] != ""].shape[0]  # type: ignore
        print(f"\nItems with buffs: {items_with_buffs}")
        print(f"\nItems with targets: {items_with_targets}")
        print(f"Items with known sources: {items_with_sources}")

        # Price statistics
        df_with_price = df[df["trade_price"] != ""]  # type: ignore
        if len(df_with_price) > 0:  # type: ignore
            df_with_price["trade_price_num"] = pd.to_numeric(df_with_price["trade_price"])  # type: ignore
            print(f"\nPrice statistics (for {len(df_with_price)} items with prices):")  # type: ignore
            print(f"  Min: {df_with_price['trade_price_num'].min()}")  # type: ignore
            print(f"  Max: {df_with_price['trade_price_num'].max()}")  # type: ignore
            print(f"  Average: {df_with_price['trade_price_num'].mean():.2f}")  # type: ignore
