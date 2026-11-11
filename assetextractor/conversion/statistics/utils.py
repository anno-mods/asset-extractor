"""Utility functions for item extraction and formatting."""

import typing as t
from dataclasses import dataclass

from assetextractor.conversion.statistics.constants import SOURCE_TEXT_IDS
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import Attribute
from assetextractor.parsing.core.texts import Text, TextCache
from assetextractor.parsing.core.uitext import BuffUI


@dataclass
class SourceInfo:
    """Information about where an item can be obtained."""

    guid: int
    name: Text | str
    probability: float | None = None


class SourceDict(t.TypedDict, total=False):
    guid: int
    name: Text | str | None
    probability: float | None
    sequence: int | None
    objective: int | None
    decision_guid: int | None


SourceType = t.Union[SourceInfo, SourceDict]


def flatten_pool(pool: Asset | None) -> list[int]:
    """Recursively flatten an AssetPool into individual asset GUIDs.

    Args:
        pool: An AssetPool asset or None

    Returns:
        List of asset GUIDs contained in the pool
    """
    if pool is None:
        return []

    if "AssetPool" not in pool.template.name:
        return [pool.guid]

    res: list[int] = []
    for entry in pool.AssetPool.AssetList:  # type: ignore
        if entry.Asset() is not None:  # type: ignore  # Last item can sometimes be None
            res += flatten_pool(entry.Asset())  # type: ignore
    # The same asset can be listed in several nested pools
    return list(dict.fromkeys(res))


def get_localized_name(asset: Asset) -> str:
    """Get the localized name of an asset.

    Args:
        asset: The asset to get the name for

    Returns:
        Localized name or fallback to internal name or GUID
    """
    if asset.text is not None:
        return asset.text()
    # Fallback to internal name
    return asset.name or f"Asset_{asset.guid}"


def get_source_display_name(source: Asset, texts: TextCache) -> Text | str:
    """Get localized display name for a source asset.

    Args:
        source: The source asset (trader, quest, tech, etc.)
        texts: TextCache for looking up localized text

    Returns:
        Text object or string (always returns a non-None value)
    """
    from assetextractor.parsing.core.attributes import TextAttribute

    # Check for DecisionScreenConfig.Headline (for decisions)
    text_attr = source.find("Decision.DecisionScreenConfig.Headline")
    if isinstance(text_attr, TextAttribute) and text_attr() is not None:
        return text_attr()

    # Prefer localized text
    if source.text is not None:
        return source.text

    # Check for TechName (for Tech template)
    if source.template.name == "Tech":
        tech_name_attr = source.find("Tech.TechName")
        if isinstance(tech_name_attr, Attribute):
            text_ref = tech_name_attr()
            if text_ref is not None and isinstance(text_ref, int):
                text_obj = texts.elements.get(text_ref)
                if text_obj is not None:
                    return text_obj

    # Fallback to internal name or GUID (as string)
    return source.name or f"Asset_{source.guid}"


def format_buff_ui(buff_ui: BuffUI) -> str:
    """Format a single BuffUI object to text.

    Args:
        buff_ui: A BuffUI object with text and value attributes

    Returns:
        Formatted string combining text and value
    """
    parts: list[str] = []

    # Get text
    if buff_ui.text is not None:
        text = buff_ui.text() if isinstance(buff_ui.text, Text) else str(buff_ui.text)
        if text:
            parts.append(text)

    # Get value
    if buff_ui.value is not None:
        parts.append(buff_ui.value)

    return ": ".join(parts) if len(parts) > 0 else ""


def format_buff_attributes(buff_asset: Asset, visited_effects: t.Set[int] | None = None) -> str:
    """Extract and format buff attributes using buff_ui property.

    Args:
        buff_asset: The buff asset (BuildingBuff or ShipBuff)
        visited_effects: Set of visited effect GUIDs to prevent infinite loops

    Returns:
        Formatted string with all buff attributes
    """
    if visited_effects is None:
        visited_effects = set()

    functional_effects: list[str] = []

    # Get buff UI from the asset
    buff_ui_list = buff_asset.buff_ui

    # Format all BuffUI objects
    buff_texts: list[str] = []
    for buff_ui in buff_ui_list:
        formatted = format_buff_ui(buff_ui)
        if formatted:
            buff_texts.append(formatted)

    # Combine functional effects and direct buffs
    all_texts = functional_effects + buff_texts

    return "; ".join(all_texts) if len(all_texts) > 0 else "No attributes"


def extract_boost_buffs(item_asset: Asset, assets: AssetCache, visited_effects: t.Set[int] | None = None) -> str:
    """Extract and format boost buff attributes from an ItemWithBoost asset.

    Args:
        item_asset: The ItemWithBoost asset
        assets: AssetCache for looking up buff assets
        visited_effects: Set of visited effect GUIDs to prevent infinite loops

    Returns:
        Formatted string with all boost buff attributes
    """
    if visited_effects is None:
        visited_effects = set()

    try:
        boost_buffs_attr = item_asset.find("ItemWithBoost.BoostBuffs")
        if boost_buffs_attr is None:
            return ""

        buff_descriptions: list[str] = []
        for buff_entry in boost_buffs_attr:  # type: ignore
            try:
                buff_guid = buff_entry.GUID.guid  # type: ignore
                if buff_guid is not None:
                    buff_asset = assets[buff_guid]
                    if buff_asset is not None:
                        buff_desc = format_buff_attributes(buff_asset, visited_effects)
                        if buff_desc and buff_desc != "No attributes":
                            buff_descriptions.append(buff_desc)
            except Exception:
                pass

        return " | ".join(buff_descriptions) if len(buff_descriptions) > 0 else ""
    except Exception:
        return ""


def format_source_for_csv(
    source_type: str, source_name: Text | str | None, probability: float | None, texts: TextCache
) -> str:
    """Format a single source for CSV export.

    Args:
        source_type: Type of source (selling, contracts, research, quest, etc.)
        source_name: Name of the source (Text object or string)
        probability: Probability of getting item from this source (0.0-1.0)
        texts: TextCache for looking up localized text

    Returns:
        Formatted source string for CSV
    """
    # Get source type label
    type_labels = {
        "selling": "Selling",
        "contracts": "Contracts",
        "research": "Research",
        "quest": "Quest",
        "drops": "Drops",
        "achievement": "Achievement",
        "festival": "Festival",
        "function": "Event",
        "trigger": "Unlock",
        "hall_of_fame": "Hall of Fame",
        "subjugated": "Subjugated Into Specialist",
        "colosseum": "Colosseum",
    }

    text_id = SOURCE_TEXT_IDS.get(source_type, None)
    if text_id is not None:
        text_obj = texts.get(text_id)
        label = text_obj() if text_obj is not None else type_labels.get(source_type, source_type.title())
    else:
        label = type_labels.get(source_type, source_type.title())

    # Convert Text object to localized string
    name_str: str | None
    if isinstance(source_name, Text):
        name_str = source_name()
    elif source_name is not None:
        name_str = str(source_name)
    else:
        name_str = None

    # For subjugated and colosseum items, don't include additional details (just the source type)
    if source_type == "subjugated" or name_str is None:
        return label

    # Add probability if significant
    if probability is not None and probability < 1.0:
        return f"{label}: {name_str} ({probability:.3%})"
    else:
        return f"{label}: {name_str}"


def format_all_sources_csv(sources: t.Dict[str, t.List[SourceType]], texts: TextCache) -> str:
    """Format all sources as semicolon-separated string for CSV.

    Args:
        sources: Dictionary of source types to list of source dicts/SourceInfo
        texts: TextCache for looking up localized text

    Returns:
        Semicolon-separated string of all sources
    """
    all_sources: list[str] = []

    # Order by importance
    # exclude achievement, function, and trigger as these are not sources
    order = [
        "hall_of_fame",
        "subjugated",
        "colosseum",
        "selling",
        "contracts",
        "research",
        "festival",
        "quest",
        "drops",
    ]

    # Deduplicate by GUID
    for source_type in order:
        seen_guids: set[int] = set()
        for source in sources.get(source_type, []):
            # Handle both SourceInfo objects and dicts
            if isinstance(source, SourceInfo):
                guid = source.guid
                name = source.name
                probability = source.probability
            else:
                guid = source.get("guid")
                name = source.get("name")
                probability = source.get("probability")

            if guid is not None and guid not in seen_guids:
                seen_guids.add(guid)
                formatted = format_source_for_csv(source_type, name, probability, texts)
                all_sources.append(formatted)

    return "; ".join(all_sources) if len(all_sources) > 0 else ""
