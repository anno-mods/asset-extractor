"""Boost condition parser for ItemWithBoost assets."""

import typing as t
from typing import Any, TypeVar

from assetextractor.conversion.statistics.constants import COMPARISON_OPERATORS, SOURCE_TEXT_IDS
from assetextractor.conversion.statistics.utils import get_localized_name
from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import Attribute, DictAttribute, Property, TemplateAttribute
from assetextractor.parsing.core.texts import Text, TextCache

T = TypeVar("T")


class BoostConditionParser:
    """Parse boost conditions from ItemWithBoost assets."""

    def __init__(self, assets: AssetCache, texts: TextCache):
        """Initialize the boost condition parser.

        Args:
            assets: Asset cache for looking up assets
            texts: Text cache for localized text
        """
        self.assets = assets
        self.texts = texts
        self.reputation_zones, self.special_states = self._load_reputation_zones()

    def _load_reputation_zones(self) -> tuple[dict[str, str], dict[str, str]]:
        """Load reputation zone names and special state names from config asset.

        Returns:
            Tuple of (zone_names_dict, special_state_names_dict)
        """
        reputation_config_guid = 38180
        zone_names: dict[str, str] = {}
        special_state_names: dict[str, str] = {}

        try:
            reputation_config = self.assets[reputation_config_guid]
            if reputation_config is None:
                return zone_names, special_state_names

            # Load reputation zones
            reputation_zones_attr = reputation_config.find("ReputationFeature.ReputationZones")
            if isinstance(reputation_zones_attr, DictAttribute) and reputation_zones_attr.value is not None:
                for zone_name, zone_data in reputation_zones_attr.value.items():
                    if isinstance(zone_data, DictAttribute):
                        zone_name_attr = zone_data["ZoneName"]
                        if isinstance(zone_name_attr, Attribute):
                            zone_text = zone_name_attr()
                            if isinstance(zone_text, Text):
                                zone_names[zone_name] = zone_text()

            # Load reputation special states
            special_states_attr = reputation_config.find("ReputationFeature.ReputationSpecialStates")
            if isinstance(special_states_attr, DictAttribute) and special_states_attr.value is not None:
                for state_name, state_data in special_states_attr.value.items():
                    if isinstance(state_data, DictAttribute):
                        state_name_attr = state_data["Name"]
                        if isinstance(state_name_attr, Attribute):
                            state_text = state_name_attr()
                            if isinstance(state_text, str):
                                special_state_names[state_name] = state_text

        except Exception as e:
            print(f"Warning: Error loading reputation data: {e}")

        return zone_names, special_state_names

    @staticmethod
    def find_val[T](
        obj: Asset | TemplateAttribute | DictAttribute | Property,
        path: str,
        value_type: type[T] | tuple[type[t.Any], ...],
    ) -> T | None:
        """Find and return a value at the given path with strict typing.

        Args:
            obj: Asset or TemplateAttribute to search in
            path: Dot-separated path to the attribute (e.g., "ConditionObjectCount.Amount")
            value_type: Expected return type for type checking

        Returns:
            The value cast to value_type, or None if not found or wrong type
        """
        try:
            attr = obj.find(path)
            if isinstance(attr, Attribute):
                value = attr()
                if isinstance(value, value_type):
                    return t.cast("T", value)
            return None
        except Exception:
            return None

    def parse(self, item_asset: Asset) -> str:
        """Parse boost condition from an ItemWithBoost asset.

        Args:
            item_asset: The ItemWithBoost asset

        Returns:
            Formatted boost condition string, or empty string if none
        """
        try:
            condition_attr = item_asset.find("ItemWithBoost.BoostCondition.PreConditionList.Condition")
            if condition_attr is None:
                return ""

            condition = condition_attr
            if not isinstance(condition, TemplateAttribute):
                return ""

            # Try each parser in order
            parsers: list[Any] = [
                self._parse_object_count,  # Must be early for Matcher support
                self._parse_need_attribute,
                self._parse_religion,
                self._parse_dominant_patron,
                self._parse_player_counter,
                self._parse_active_emperor,
                self._parse_emperor_relation,
                self._parse_diplomacy_state,
                self._parse_trade_route_count,
                self._parse_item_used,
                self._parse_monument_events,
                self._parse_war_state,
                self._parse_in_storage,
                self._parse_festival_active,
                self._parse_race_outcome,
                self._parse_compare_variable,
                self._parse_romanization,
                self._parse_always_true,  # Check last as it's often present with others
            ]

            for parser in parsers:
                result = parser(condition)
                if result is not None:
                    return result

            # Fallback for unhandled conditions
            return "Boost condition active"

        except Exception:
            return ""

    def _parse_always_true(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionAlwaysTrue."""
        try:
            if hasattr(condition, "ConditionAlwaysTrue"):
                # Check if there are other conditions besides AlwaysTrue
                has_other = any(
                    hasattr(condition, ct)
                    for ct in [
                        "ConditionObjectCount",
                        "ConditionDominantPatron",
                        "ConditionNeedAttributeCounter",
                        "ConditionPlayerCounter",
                        "ConditionActiveEmperor",
                        "ConditionReligion",
                        "ConditionMonumentEventsActive",
                        "ConditionEmperorRelation",
                        "ConditionDiplomacyState",
                        "ConditionItemUsed",
                        "ConditionWarState",
                        "ConditionInStorage",
                        "ConditionTradeRouteCount",
                        "ConditionFestivalActive",
                        "ConditionRaceOutcome",
                        "ConditionCompareVariable",
                        "ConditionRomanization",
                    ]
                )
                if not has_other:
                    return "Always active"
        except Exception:
            pass
        return None

    def _parse_object_count(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionObjectCount with Matcher support for ship configuration."""
        try:
            if hasattr(condition, "ConditionObjectCount"):
                amount = self.find_val(condition, "ConditionObjectCount.Amount", (int, float))
                comparison_op = self.find_val(condition, "ConditionObjectCount.ComparisonOp", (int, str))
                obj: Asset | None = condition.find_ref("ObjectFilter.ObjectGUID")

                if amount is None or comparison_op is None:
                    return None

                # Check for Matcher reference (ship configuration requirements)
                matcher_condition: str | None = None
                try:
                    matcher: Asset | None = condition.find_ref("ObjectFilter.Matcher")
                    if matcher is not None:
                        ship_config = matcher.find("Matcher.Criterion.MatcherCriterionShipConfiguration")

                        if isinstance(ship_config, (TemplateAttribute, DictAttribute, Property)):
                            req_modules = self.find_val(ship_config, "RequiredModuleCount", int)
                            req_military = self.find_val(ship_config, "RequiredMilitaryModuleCount", int)
                            negate = self.find_val(ship_config, "Negate", bool)

                            if req_military is not None and req_military > 0:
                                matcher_condition = f"At least {req_military} military modules"
                            elif req_modules is not None and req_modules > 0:
                                matcher_condition = f"At least {req_modules} modules on the ship"

                            if negate and matcher_condition is not None:
                                matcher_condition = "NOT (" + matcher_condition + ")"

                            ship_config_val = self.find_val(ship_config, "ShipConfiguration", Asset)
                            if ship_config_val is not None and obj is not None:
                                matcher_condition = f"Must be socketed into {get_localized_name(obj)}"
                except Exception:
                    pass

                # If we have a matcher condition, return it directly
                if matcher_condition is not None:
                    return matcher_condition

                # Otherwise, return the standard object count condition
                if obj is not None:
                    obj_name = get_localized_name(obj)
                    return self.format_comparison(obj_name, amount, comparison_op)
        except Exception:
            pass
        return None

    def _parse_need_attribute(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionNeedAttributeCounter with scope support."""
        try:
            if hasattr(condition, "ConditionNeedAttributeCounter"):
                need_type_raw = self.find_val(condition, "ConditionNeedAttributeCounter.NeedAttributeType", str)
                amount = self.find_val(condition, "ConditionNeedAttributeCounter.NeedAttributeAmount", (int, float))
                comparison_op = self.find_val(condition, "ConditionNeedAttributeCounter.ComparisonOpType", (int, str))
                is_global = self.find_val(condition, "ConditionNeedAttributeCounter.UseGlobalSum", bool)

                if need_type_raw is None or amount is None or comparison_op is None:
                    return None

                need_type: str | Text
                ui_cache = self.assets.properties.ui_text_cache
                if ui_cache is not None:
                    mapping = ui_cache.get_ui_text("NeedAttributeType", str(need_type_raw))
                    if mapping is not None and mapping.text is not None:
                        need_type = mapping.text()
                    else:
                        need_type = str(need_type_raw)
                else:
                    need_type = str(need_type_raw)

                suffix = "(Global)" if is_global else ""
                return self.format_comparison(str(need_type), amount, comparison_op, suffix)
        except Exception:
            pass
        return None

    def _parse_religion(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionReligion (None means no patron required)."""
        try:
            if hasattr(condition, "ConditionReligion"):
                religion_asset: Asset | None = condition.find_ref("ConditionReligion.ReligionAsset")
                if religion_asset is not None:
                    return f"Patron: {get_localized_name(religion_asset)}"
                else:
                    # None means no patron required
                    text_obj = self.texts.get(SOURCE_TEXT_IDS["no_patron"])
                    return text_obj() if text_obj is not None else "No patron required"
        except Exception:
            pass
        return None

    def _parse_dominant_patron(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionDominantPatron."""
        try:
            if hasattr(condition, "ConditionDominantPatron"):
                patron: Asset | None = condition.find_ref("ConditionDominantPatron.PatronGUID")
                if patron is not None:
                    return f"Dominant Patron: {get_localized_name(patron)}"
        except Exception:
            pass
        return None

    def _parse_player_counter(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionPlayerCounter with context building and scope."""
        try:
            if hasattr(condition, "ConditionPlayerCounter"):
                player_counter = self.find_val(condition, "ConditionPlayerCounter.PlayerCounter", (int, str))
                comparison_op = self.find_val(condition, "ConditionPlayerCounter.ComparisonOp", (int, str))
                counter_amount = self.find_val(condition, "ConditionPlayerCounter.CounterAmount", (int, float))
                scope = self.find_val(condition, "ConditionPlayerCounter.CounterScope", (int, str))

                if comparison_op is None or counter_amount is None:
                    return None

                if scope is None:
                    scope = "Global"

                context_building: Asset | None = condition.find_ref("ConditionPlayerCounter.Context")
                if context_building is not None:
                    building_name = get_localized_name(context_building)
                    return self.format_comparison(building_name, counter_amount, comparison_op, f"({scope})")

                if player_counter is not None and player_counter != 0:
                    counter_name = str(player_counter)
                    return self.format_comparison(counter_name, counter_amount, comparison_op, f"({scope})")
        except Exception:
            pass
        return None

    def _parse_active_emperor(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionActiveEmperor."""
        try:
            if hasattr(condition, "ConditionActiveEmperor"):
                emperor: Asset | None = condition.find_ref("ConditionActiveEmperor.EmperorParticipant")
                if emperor is not None:
                    return f"Emperor: {get_localized_name(emperor)}"
        except Exception:
            pass
        return None

    def _parse_emperor_relation(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionEmperorRelation with reputation zones and special states."""
        try:
            if hasattr(condition, "ConditionEmperorRelation"):
                allowed_zones = t.cast(
                    "t.Union[list[t.Any], str, None]",
                    self.find_val(condition, "ConditionEmperorRelation.AllowedZones", (list, str)),
                )
                allowed_special_states = t.cast(
                    "t.Union[list[t.Any], str, None]",
                    self.find_val(condition, "ConditionEmperorRelation.AllowedSpecialStates", (list, str)),
                )

                parts: list[str] = []

                # Handle AllowedZones
                if allowed_zones is not None:
                    zone_list: list[str] = []
                    if isinstance(allowed_zones, str):
                        zone_list = [z.strip() for z in allowed_zones.split(";") if z.strip()]
                    else:
                        zone_list = [str(z) for z in allowed_zones if z]

                    zone_names: list[str] = []
                    for zone in zone_list:
                        if zone in self.reputation_zones:
                            zone_names.append(self.reputation_zones[zone])
                        else:
                            zone_names.append(zone)

                    if len(zone_names) > 0:
                        parts.append(f"Reputation: {' or '.join(zone_names)}")

                # Handle AllowedSpecialStates
                if allowed_special_states is not None:
                    state_list: list[str] = []
                    if isinstance(allowed_special_states, str):
                        state_list = [s.strip() for s in allowed_special_states.split(";") if s.strip()]
                    else:
                        state_list = [str(s) for s in allowed_special_states if s]

                    state_names: list[str] = []
                    for state in state_list:
                        if state in self.special_states:
                            state_names.append(self.special_states[state])
                        else:
                            state_names.append(state)

                    if len(state_names) > 0:
                        parts.append(f"Emperor State: {' or '.join(state_names)}")

                if len(parts) > 0:
                    return "; ".join(parts)

                return "Emperor relation required"
        except Exception:
            pass
        return None

    def _parse_diplomacy_state(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionDiplomacyState."""
        try:
            if hasattr(condition, "ConditionDiplomacyState"):
                profile2: Asset | None = condition.find_ref("ConditionDiplomacyState.Profile2")
                desired_state = self.find_val(condition, "ConditionDiplomacyState.DesiredState", str)
                if profile2 is not None and desired_state is not None:
                    profile_name = get_localized_name(profile2)
                    return f"Diplomacy with {profile_name}: {desired_state}"
        except Exception:
            pass
        return None

    def _parse_trade_route_count(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionTradeRouteCount."""
        try:
            if hasattr(condition, "ConditionTradeRouteCount"):
                count = self.find_val(condition, "ConditionTradeRouteCount.TradeRouteCount", int)
                count_op = self.find_val(condition, "ConditionTradeRouteCount.CountComparisonOp", (int, str))
                if count is not None and count_op is not None:
                    text_obj = self.texts.get(SOURCE_TEXT_IDS["trade_routes"])
                    subject = text_obj() if text_obj is not None else "Trade routes"
                    return self.format_comparison(subject, count, count_op)
        except Exception:
            pass
        return None

    def _parse_item_used(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionItemUsed."""
        try:
            if hasattr(condition, "ConditionItemUsed"):
                item_amount = self.find_val(condition, "ConditionItemUsed.ItemAmount", int)
                if item_amount is not None:
                    return f"{item_amount} items equipped"
        except Exception:
            pass
        return None

    def _parse_monument_events(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionMonumentEventsActive."""
        try:
            if hasattr(condition, "ConditionMonumentEventsActive"):
                return "Monument events active"
        except Exception:
            pass
        return None

    def _parse_war_state(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionWarState."""
        try:
            if hasattr(condition, "ConditionWarState"):
                return "At war"
        except Exception:
            pass
        return None

    def _parse_in_storage(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionInStorage."""
        try:
            if hasattr(condition, "ConditionInStorage"):
                in_storage_goods_attr = condition.ConditionInStorage.InStorageGoods  # type: ignore
                if isinstance(in_storage_goods_attr, Attribute):
                    in_storage_goods = in_storage_goods_attr()
                    if in_storage_goods is not None and hasattr(in_storage_goods, "__iter__"):
                        text_obj = self.texts.elements.get(SOURCE_TEXT_IDS["in_storage"])
                        in_storage_label = text_obj() if text_obj is not None else "In storage"

                        goods_list: list[str] = []
                        for item in in_storage_goods:
                            product: Asset | None = item.find_ref("Product")
                            amount_attr = item.find("Amount")
                            if product is not None and isinstance(amount_attr, Attribute):
                                amount = amount_attr()
                                if amount is not None:
                                    product_name = get_localized_name(product)
                                    goods_list.append(f"{int(amount)}t {product_name}")

                        if len(goods_list) > 0:
                            return f"{in_storage_label}: {', '.join(goods_list)}"

                return "Items in storage"
        except Exception:
            pass
        return None

    def _parse_festival_active(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionFestivalActive (missing Festival means any festival satisfies it)."""
        try:
            if hasattr(condition, "ConditionFestivalActive"):
                festival: Asset | None = condition.find_ref("ConditionFestivalActive.Festival")
                if festival is not None:
                    text_obj = self.texts.get(SOURCE_TEXT_IDS["festival"])
                    label = text_obj() if text_obj is not None else "Festival"
                    return f"{label}: {get_localized_name(festival)}"
                return "Any festival active"
        except Exception:
            pass
        return None

    def _parse_race_outcome(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionRaceOutcome (event, finish position, and/or specific racer)."""
        try:
            race = condition.find("ConditionRaceOutcome")
            if isinstance(race, (TemplateAttribute, DictAttribute, Property)):
                parts: list[str] = []

                if self.find_val(race, "CheckEventGuid", bool):
                    event: Asset | None = race.find_ref("CompareEventGuid")
                    if event is not None:
                        parts.append(get_localized_name(event))

                if self.find_val(race, "CheckRaceFinishPosition", bool):
                    position = self.find_val(race, "CompareRaceFinishPosition", (int, float))
                    position_op = self.find_val(race, "CompareRaceFinishPositionOperator", (int, str))
                    if position is not None:
                        parts.append(self.format_comparison("Finish position", position, position_op or "AtLeast"))

                if self.find_val(race, "CheckRacerGuid", bool):
                    racer: Asset | None = race.find_ref("CompareRacerGuid")
                    if racer is not None:
                        parts.append(f"Racer: {get_localized_name(racer)}")

                if len(parts) > 0:
                    return "; ".join(parts)
                return "Race outcome required"
        except Exception:
            pass
        return None

    def _parse_romanization(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionRomanization (Romanization percentage threshold)."""
        try:
            romanization = condition.find("ConditionRomanization")
            if isinstance(romanization, (TemplateAttribute, DictAttribute, Property)):
                target_value = self.find_val(romanization, "TargetValue", (int, float))
                comparison_op = self.find_val(romanization, "ComparisonOperator", (int, str))
                is_global = self.find_val(romanization, "CheckGlobalValue", bool)

                if target_value is None:
                    return None

                op_symbol = COMPARISON_OPERATORS.get(comparison_op or "AtLeast", ">=")
                amount_str = str(int(target_value)) if target_value == int(target_value) else str(target_value)
                result = f"Romanization {op_symbol} {amount_str}%"
                if is_global:
                    result += " (Global)"
                return result
        except Exception:
            pass
        return None

    def _parse_compare_variable(self, condition: TemplateAttribute) -> str | None:
        """Parse ConditionCompareVariable (session/global variable compared against a literal)."""
        try:
            cv = condition.find("ConditionCompareVariable")
            if isinstance(cv, (TemplateAttribute, DictAttribute, Property)):
                variable_name = self.find_val(cv, "VariableToCheck", str)
                comparison_op = self.find_val(cv, "ComparisonOperation", (int, str))
                if not variable_name:
                    return None

                second_variable = cv.find("SecondVariable")
                value: Any = None
                if isinstance(second_variable, (TemplateAttribute, DictAttribute, Property)):
                    if second_variable.find("BoolVariableOrValue") is not None:
                        value = self.find_val(second_variable, "BoolVariableOrValue.BoolValue", bool)
                    elif second_variable.find("IntVariableOrValue") is not None:
                        value = self.find_val(second_variable, "IntVariableOrValue.IntValue", (int, float))
                    elif second_variable.find("FloatVariableOrValue") is not None:
                        value = self.find_val(second_variable, "FloatVariableOrValue.FloatValue", (int, float))
                    elif second_variable.find("AssetVariableOrValue") is not None:
                        asset_ref = second_variable.find_ref("AssetVariableOrValue.AssetValue")
                        value = get_localized_name(asset_ref) if asset_ref is not None else None
                    elif second_variable.find("StringVariableOrValue") is not None:
                        value = self.find_val(second_variable, "StringVariableOrValue.StringValue", str)

                if value is None:
                    return f"{variable_name} comparison required"

                if isinstance(value, bool):
                    op_symbol = COMPARISON_OPERATORS.get(comparison_op or "AtLeast", ">=")
                    return f"{variable_name} {op_symbol} {'Yes' if value else 'No'}"

                if isinstance(value, (int, float)):
                    return self.format_comparison(variable_name, value, comparison_op or "AtLeast")

                return f"{variable_name}: {value}"
        except Exception:
            pass
        return None

    @staticmethod
    def format_comparison(subject: str, amount: float, comparison_op: int | str, suffix: str = "") -> str:
        """Format a comparison condition.

        Args:
            subject: The thing being compared (e.g., "Population", "Trade routes")
            amount: The numeric threshold
            comparison_op: The comparison operator (0, "AtLeast", "AtMost", etc.)
            suffix: Optional suffix to append (e.g., "(Global)")

        Returns:
            Formatted comparison string (e.g., "Population <= 5000")
        """
        op_symbol = COMPARISON_OPERATORS.get(comparison_op, ">=")
        amount_str = str(int(amount)) if amount == int(amount) else str(amount)

        result = f"{subject} {op_symbol} {amount_str}"
        if suffix:
            result += f" {suffix}"
        return result
