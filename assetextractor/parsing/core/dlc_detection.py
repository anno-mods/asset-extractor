import typing as t

from assetextractor.parsing.core.assets import Asset, AssetCache
from assetextractor.parsing.core.attributes import ListAttribute, ListItem, ReferenceAttribute
from assetextractor.parsing.core.common import WeightedReference


class DLCDetector:
    def __init__(self, cache: AssetCache) -> None:
        self._cache: AssetCache = cache
        self._dlc_map: dict[int, set[int]] = {}  # asset_guid -> {dlc_guid}
        self._all_dlc_guids: set[int] = set()
        self._all_dlc_prefix_map: dict[str, int] = {}  # "dlc01" -> guid
        self._dlc_guid_to_asset: dict[int, Asset] = {}  # DLC guid -> UplayProduct asset (ProductType=DLC only)
        self._exclusive_region_to_dlc: dict[str, int] = {}
        self._fu_dlcs: dict[int, set[int]] = {}  # feature_unlock_guid -> {dlc_guid}
        self._fe_to_buildings: dict[int, set[int]] = {}  # effect_guid -> {building_guid}
        self._buff_to_effects: dict[int, set[int]] = {}  # buff_guid -> {effect_guid}
        self._base_region_names: set[str] = {"Roman", "Celtic"}

    def detect(self) -> dict[int, set[int]]:
        self._build_dlc_index()
        self._seed_unlock_references()
        self._build_region_index()
        self._strategy_1_icon_path()
        self._strategy_1b_associated_regions()
        self._strategy_1c_production_regions()
        self._strategy_1c_fertility_by_name()
        self._strategy_1d_item_name_prefix()
        self._strategy_1e_internal_name_region()
        self._strategy_1f_template_name_region()
        self._strategy_2_uplay_unlocks()
        self._strategy_3_5_feature_unlock_bfs()
        self._strategy_7_patron_propagation()
        self._build_guard_indices()
        self._strategy_8_asset_reference_propagation()
        self._strategy_9_need_product()
        self._populate_reference_dicts()
        return self._dlc_map

    def _add_dlc(self, asset_guid: int, dlc_guid: int) -> None:
        self._dlc_map.setdefault(asset_guid, set()).add(dlc_guid)

    def _add_dlc_multiple(self, asset_guid: int, dlc_guids: set[int]) -> None:
        for dlc_guid in dlc_guids:
            self._add_dlc(asset_guid, dlc_guid)

    def _get_cond_dlcs_from_path(self, asset: Asset, path: str) -> set[int]:
        """Extract DLC GUIDs from a TriggerCondition.ConditionIsDLCActive at the given path."""
        full_path = f"{path}.ConditionIsDLCActive.DLCAssetList"
        dlc_guids = self._get_list_guids(asset, full_path, "DLCAsset")
        return {guid for guid in dlc_guids if guid in self._all_dlc_guids}

    def _build_dlc_index(self) -> None:
        uplay_template = self._cache.templates.get("UplayProduct")
        if uplay_template:
            for dlc in list(uplay_template.assets):
                if dlc.find_value("UplayProduct.ProductType") != "DLC":
                    continue

                dlc_id = dlc.find_value("Standard.ID")
                if dlc_id:
                    full_id = str(dlc_id)
                    prefix = full_id.split("_")[0].lower() if "_" in full_id else full_id.lower()
                    self._all_dlc_prefix_map[prefix] = dlc.guid
                    self._all_dlc_guids.add(dlc.guid)
                    self._dlc_guid_to_asset[dlc.guid] = dlc

    def _seed_unlock_references(self) -> None:
        """Seed unlocked_by_dlcs / dlc_unlocks dicts (and _dlc_map) directly from
        UplayProduct.UplayProductUnlocks, recursing through RewardPool.ItemsPool.
        """
        uplay_template = self._cache.templates.get("UplayProduct")
        if not uplay_template:
            return

        for dlc_asset in list(uplay_template.assets):
            attr_list = dlc_asset.find("UplayProduct.UplayProductUnlocks")
            if not isinstance(attr_list, ListAttribute):
                continue

            visited: set[int] = set()
            for item in attr_list:
                try:
                    ref = item.find("UplayProductUnlock")
                    if ref is None:
                        ref = item.find("GUID")
                    if isinstance(ref, ReferenceAttribute) and ref.value:
                        self._flatten_and_tag_unlock(ref.value, dlc_asset, visited)
                except Exception:
                    pass

    def _flatten_and_tag_unlock(self, asset: Asset, dlc_asset: Asset, visited: set[int]) -> None:
        if asset.guid in visited:
            return
        visited.add(asset.guid)

        asset.unlocked_by_dlcs[dlc_asset.guid] = WeightedReference(source=dlc_asset, target=asset)
        dlc_asset.dlc_unlocks[asset.guid] = WeightedReference(source=asset, target=dlc_asset)
        if dlc_asset.guid in self._all_dlc_guids:
            self._add_dlc(asset.guid, dlc_asset.guid)

        if asset.template and "RewardPool" in asset.template.name:
            items_pool = asset.find("RewardPool.ItemsPool")
            if isinstance(items_pool, ListAttribute):
                for item in items_pool:
                    try:
                        ref = item.find("ItemLink")
                        if isinstance(ref, ReferenceAttribute) and ref.value:
                            self._flatten_and_tag_unlock(ref.value, dlc_asset, visited)
                    except Exception:
                        pass

    def _build_region_index(self) -> None:
        # Map region keywords to DLCs dynamically from Region template
        region_template = self._cache.templates.get("Region")
        region_dataset = self._cache.datasets.get("Region")

        if region_template:
            for region_asset in list(region_template.assets):
                unlocks = list(region_asset.unlocked_by_dlcs.keys())

                # Get the region literal from dataset using the Standard.ID
                # e.g. RegionEgyptian -> Egyptian
                id_val = str(region_asset.find_value("Standard.ID") or "")

                if not unlocks:
                    # Fallback for Egyptian if we know it's DLC03 (67904)
                    # This happens if it's implicitly unlocked by a session start trigger
                    if "Egyptian" in id_val and "dlc03" in self._all_dlc_prefix_map:
                        unlocks = [self._all_dlc_prefix_map["dlc03"]]
                    else:
                        continue

                dlc_guid = unlocks[0]

                kw_to_add: set[str] = set()
                if id_val and region_dataset:
                    # Dataset Region literals are like "Egyptian", "Roman"
                    # Region asset IDs are like "RegionEgyptian", "RegionRoman"
                    for literal in region_dataset.literals:
                        if literal in id_val:
                            kw_to_add.add(literal)

                # Fallback to name-based keyword extraction
                name = str(region_asset.name or "")
                if name:
                    kw_to_add.add(name.replace("Region", "").strip())

                if not kw_to_add and id_val:
                    kw_to_add.add(id_val.replace("Region", "").strip())

                for kw in kw_to_add:
                    if kw:
                        self._exclusive_region_to_dlc[kw] = dlc_guid
                        self._exclusive_region_to_dlc[kw.lower()] = dlc_guid

        # print(f"DEBUG _exclusive_region_to_dlc: {self._exclusive_region_to_dlc}")

    def _strategy_1_icon_path(self) -> None:
        for asset in list(self._cache.elements.values()):
            icon_path = asset.find_value("Standard.IconFilename")
            if icon_path:
                icon_path_str = str(icon_path).lower().replace("\\", "/")
                if "hall_of_fame" in icon_path_str:
                    continue
                for prefix, dlc_guid in self._all_dlc_prefix_map.items():
                    if f"/{prefix}/" in icon_path_str:
                        self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1b_associated_regions(self) -> None:
        if not self._exclusive_region_to_dlc:
            return
        for asset in list(self._cache.elements.values()):
            # Check Building.AssociatedRegions (list)
            regions_val = asset.find_value("Building.AssociatedRegions")
            if isinstance(regions_val, list):
                # Add type hint for regions_val to satisfy pyright
                region_list: list[t.Any] = t.cast("list[t.Any]", regions_val)
                if len(region_list) == 1:
                    region_name = str(region_list[0])
                    dlc_guid = self._exclusive_region_to_dlc.get(region_name)
                    if dlc_guid:
                        self._add_dlc(asset.guid, dlc_guid)

            # Check Standard.AssociatedRegion (single choice)
            region_val = asset.find_value("Standard.AssociatedRegion")
            if region_val:
                dlc_guid = self._exclusive_region_to_dlc.get(str(region_val))
                if dlc_guid:
                    self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1c_production_regions(self) -> None:
        for asset in list(self._cache.elements.values()):
            if asset.template and asset.template.name == "Product":
                pr_attr = asset.find("Product.ProductionRegions")
                if isinstance(pr_attr, ListAttribute):
                    region_types: set[str] = set()
                    for item in pr_attr:
                        try:
                            # Use find_value on the ListItem
                            rt = item.find_value("RegionType")
                            if rt:
                                region_types.add(str(rt))
                        except Exception:
                            pass

                    if not region_types or region_types & self._base_region_names:
                        continue
                    for region, dlc_guid in self._exclusive_region_to_dlc.items():
                        if region in region_types:
                            self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1c_fertility_by_name(self) -> None:
        fertility_template = self._cache.templates.get("Fertility")
        if fertility_template:
            for asset in list(fertility_template.assets):
                name = asset.name or ""
                if any(r in name for r in self._base_region_names):
                    continue
                for region, dlc_guid in self._exclusive_region_to_dlc.items():
                    if region in name:
                        self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1d_item_name_prefix(self) -> None:
        for tmpl_name in ("Item", "ItemWithBoost"):
            tmpl = self._cache.templates.get(tmpl_name)
            if tmpl:
                for asset in list(tmpl.assets):
                    name = (asset.name or "").lower()
                    for prefix, dlc_guid in self._all_dlc_prefix_map.items():
                        if name.startswith(prefix.lower()):
                            self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1e_internal_name_region(self) -> None:
        if not self._exclusive_region_to_dlc:
            return

        # Aegyptus is a synonym for Egyptian in internal names
        synonyms = {"Aegyptus": "Egyptian"}

        for asset in list(self._cache.elements.values()):
            name = (asset.name or "").lower()
            for region, dlc_guid in self._exclusive_region_to_dlc.items():
                if region.lower() in name:
                    self._add_dlc(asset.guid, dlc_guid)

            for syn, target_region in synonyms.items():
                if syn.lower() in name:
                    dlc_guid = self._exclusive_region_to_dlc.get(target_region)
                    if dlc_guid:
                        self._add_dlc(asset.guid, dlc_guid)

    def _strategy_1f_template_name_region(self) -> None:
        if not self._exclusive_region_to_dlc:
            return
        for asset in list(self._cache.elements.values()):
            if not asset.template:
                continue
            tmpl_name = asset.template.name.lower()
            for region, dlc_guid in self._exclusive_region_to_dlc.items():
                if region.lower() in tmpl_name:
                    self._add_dlc(asset.guid, dlc_guid)

    def _strategy_2_uplay_unlocks(self) -> None:
        uplay_template = self._cache.templates.get("UplayProduct")
        if uplay_template:
            for dlc in list(uplay_template.assets):
                if dlc.guid in self._all_dlc_guids:
                    guids = self._get_list_guids(dlc, "UplayProduct.UplayProductUnlocks", "UplayProductUnlock")
                    self._propagate_to_guids(guids, {dlc.guid})

    def _get_cond_dlcs(self, fu_asset: Asset) -> set[int]:
        dlc_guids = self._get_list_guids(
            fu_asset, "Trigger.TriggerCondition.ConditionIsDLCActive.DLCAssetList", "DLCAsset"
        )
        return {guid for guid in dlc_guids if guid in self._all_dlc_guids}

    def _get_cond_unlocked_ref(self, fu_asset: Asset) -> int | None:
        ref_asset = fu_asset.find_value("Trigger.TriggerCondition.ConditionUnlocked.AssetToCheck")
        if isinstance(ref_asset, Asset):
            return ref_asset.guid
        return None

    def _is_base_session(self, guid: int) -> bool:
        """True if the asset is a Session whose Region is a base-game region.

        Egypt (DLC03) ships triggers like "Unlock Trigger Roman Province from Egypt"
        whose ConditionIsDLCActive=DLC03 and ActionUnlockAsset point at the base
        sessions Latium (Roman) / Albion (Celtic). These merely grant an additional
        travel route to sessions that already exist in the base game, so an "unlock"
        from a DLC trigger must not tag them as DLC content.
        """
        asset = self._cache.elements.get(guid)
        if asset is None or not asset.template or not asset.template.name.startswith("Session"):
            return False
        region = asset.find("Session.Region")
        region_asset = getattr(region, "value", None)
        if region_asset is None:
            return False
        region_id = str(region_asset.find_value("Standard.ID") or "")
        region_name = str(region_asset.name or "")
        return any(base in region_id or base in region_name for base in self._base_region_names)

    def _reject_base_sessions(self, guids: t.Iterable[int]) -> list[int]:
        return [guid for guid in guids if not self._is_base_session(guid)]

    def _get_action_unlock_guids(self, fu_asset: Asset) -> list[int]:
        result: list[int] = []
        ta_attr = fu_asset.find("Trigger.TriggerActions")
        if not isinstance(ta_attr, ListAttribute):
            return result

        for action_item in ta_attr:
            try:
                trigger_action = getattr(action_item, "TriggerAction", None)
                if trigger_action and hasattr(trigger_action, "ActionUnlockAsset"):
                    aua = trigger_action.ActionUnlockAsset
                    if hasattr(aua, "UnlockAssets"):
                        for ua_item in aua.UnlockAssets:
                            ref = getattr(ua_item, "Asset", None)
                            if isinstance(ref, ReferenceAttribute) and ref.value:
                                result.append(ref.value.guid)
            except Exception:
                pass
        return result

    def _flatten_asset_pool(self, pool_asset: Asset, dlc_guids: set[int]) -> None:
        pool_guids = self._get_list_guids(pool_asset, "AssetPool.AssetList", "Asset")
        self._propagate_to_guids([guid for guid in pool_guids if not self._is_base_product(guid)], dlc_guids)

    def _is_base_product(self, guid: int) -> bool:
        """True if the asset is a Product that is producible in a base-game region.

        DLC03 research techs reward pools like "Asset Pool Research Greco Roman Wine" that
        mix Egyptian content with base-game goods (Grapes, Wine, Soap, ...) which Egypt is
        merely allowed to produce. Pool membership must not tag those goods as DLC content.
        Genuine DLC goods are tagged independently via their DLC icon path (strategy 1).
        """
        asset = self._cache.elements.get(guid)
        if asset is None or not asset.template or asset.template.name != "Product":
            return False
        regions = asset.find("Product.ProductionRegions")
        if not isinstance(regions, ListAttribute):
            return False
        for item in regions:
            try:
                if str(item.find_value("RegionType")) in self._base_region_names:
                    return True
            except Exception:
                pass
        return False

    def _get_list_guids(self, asset: Asset | ListItem, list_path: str, ref_attr_name: str) -> list[int]:
        """Extract a list of GUIDs from a ListAttribute by following a ReferenceAttribute field."""
        result: list[int] = []
        try:
            attr_list = asset.find(list_path)
            if not isinstance(attr_list, ListAttribute):
                return result
            for item in attr_list:
                try:
                    ref = getattr(item, ref_attr_name)
                    if isinstance(ref, ReferenceAttribute) and ref.value:
                        result.append(ref.value.guid)
                except Exception:
                    pass
        except Exception:
            pass
        return result

    def _propagate_to_guids(self, guids: t.Iterable[int], dlc_guids: set[int]) -> bool:
        """Add DLC tags to multiple GUIDs and return True if any new tags were added."""
        changed = False
        for guid in guids:
            for dlc_guid in dlc_guids:
                if dlc_guid not in self._dlc_map.get(guid, set()):
                    self._add_dlc(guid, dlc_guid)
                    changed = True
        return changed

    def _strategy_3_5_feature_unlock_bfs(self) -> None:
        all_fu_assets: list[Asset] = []
        for name in ("FeatureUnlock", "TechFeatureUnlock"):
            tmpl = self._cache.templates.get(name)
            if tmpl:
                all_fu_assets.extend(list(tmpl.assets))

        # Seed FeatureUnlocks from their own TriggerCondition
        for fu in all_fu_assets:
            dlcs = self._get_cond_dlcs_from_path(fu, "Trigger.TriggerCondition")
            if dlcs:
                self._fu_dlcs[fu.guid] = dlcs
                self._propagate_to_guids([fu.guid], dlcs)

        # Seed from Trigger ConditionIsDLCActive
        trigger_template = self._cache.templates.get("Trigger")
        if trigger_template:
            for trigger in list(trigger_template.assets):
                dlcs_for_trigger = self._get_cond_dlcs_from_path(trigger, "Trigger.TriggerCondition")
                if not dlcs_for_trigger:
                    continue

                # Tag the trigger itself
                self._add_dlc_multiple(trigger.guid, dlcs_for_trigger)

                # Direct unlocks in trigger actions
                self._propagate_to_guids(
                    self._reject_base_sessions(self._get_action_unlock_guids(trigger)), dlcs_for_trigger
                )

                # RegisterTrigger chaining: tag sub-trigger and propagate its unlock actions
                ta_attr = trigger.find("Trigger.TriggerActions")
                if isinstance(ta_attr, ListAttribute):
                    for action_item in ta_attr:
                        sub_trigger = action_item.find_value("TriggerAction.ActionRegisterTrigger.TriggerAsset")
                        if not isinstance(sub_trigger, Asset):
                            continue
                        self._add_dlc_multiple(sub_trigger.guid, dlcs_for_trigger)
                        sub_ta = sub_trigger.find("Trigger.TriggerActions")
                        if isinstance(sub_ta, ListAttribute):
                            for sub_item in sub_ta:
                                for field in ("UnhideAssets", "UnlockAssets"):
                                    guids = self._get_list_guids(
                                        sub_item, f"TriggerAction.ActionUnlockAsset.{field}", "Asset"
                                    )
                                    self._propagate_to_guids(self._reject_base_sessions(guids), dlcs_for_trigger)

        changed = True
        while changed:
            changed = False

            for fu in all_fu_assets:
                if fu.guid in self._fu_dlcs:
                    continue
                parent_guid = self._get_cond_unlocked_ref(fu)
                if parent_guid is not None and parent_guid in self._fu_dlcs:
                    self._fu_dlcs[fu.guid] = set(self._fu_dlcs[parent_guid])
                    changed = True

            for fu_guid, dlc_guids in list(self._fu_dlcs.items()):
                fu_asset = self._cache.elements.get(fu_guid)
                if not fu_asset:
                    continue

                # ActionUnlockAsset
                self._propagate_to_guids(
                    self._reject_base_sessions(self._get_action_unlock_guids(fu_asset)), dlc_guids
                )

                # TechCategory -> Techs -> Tech -> Rewards.Unlocks
                for unlocked_guid in self._get_action_unlock_guids(fu_asset):
                    unlocked_asset = self._cache.elements.get(unlocked_guid)
                    if unlocked_asset is None:
                        continue

                    tech_guids = self._get_list_guids(unlocked_asset, "TechCategory.Techs", "Tech")
                    self._propagate_to_guids(tech_guids, dlc_guids)

                    for tech_guid in tech_guids:
                        tech_asset = self._cache.elements.get(tech_guid)
                        if not tech_asset:
                            continue

                        reward_guids = self._get_list_guids(tech_asset, "Tech.Rewards.Unlocks", "UnlockReward")
                        if self._propagate_to_guids(reward_guids, dlc_guids):
                            # Check if any reward is a FeatureUnlock to continue BFS
                            for r_guid in reward_guids:
                                r_asset = self._cache.elements.get(r_guid)
                                if isinstance(r_asset, Asset):
                                    self._flatten_asset_pool(r_asset, dlc_guids)
                                    if (
                                        r_asset.template
                                        and "FeatureUnlock" in r_asset.template.name
                                        and r_guid not in self._fu_dlcs
                                    ):
                                        self._fu_dlcs[r_guid] = set(dlc_guids)
                                        changed = True

    def _strategy_7_patron_propagation(self) -> None:
        patron_template = self._cache.templates.get("Patron")
        if patron_template:
            for patron in list(patron_template.assets):
                if patron.guid not in self._dlc_map:
                    continue
                dlc_guids = self._dlc_map[patron.guid]
                for field in ("Patron.Wonder", "Patron.Shrine"):
                    try:
                        ref = patron.find(field)
                        if isinstance(ref, ReferenceAttribute) and ref.value:
                            if self._propagate_to_guids([ref.value.guid], dlc_guids):
                                pass
                            self._flatten_asset_pool(ref.value, dlc_guids)
                    except Exception:
                        pass
                for field in ("Patron.LocalEffects", "Patron.DominantEffects"):
                    guids = self._get_list_guids(patron, field, "GUID")
                    self._propagate_to_guids(guids, dlc_guids)

    def _build_guard_indices(self) -> None:
        for bld in list(self._cache.elements.values()):
            for eff_guid in self._get_list_guids(bld, "Building.FunctionalEffects", "FunctionalEffect"):
                self._fe_to_buildings.setdefault(eff_guid, set()).add(bld.guid)

        for effect in list(self._cache.elements.values()):
            if effect.template and effect.template.name == "Effect":
                for buff_guid in self._get_list_guids(effect, "Effect.Buffs", "GUID"):
                    self._buff_to_effects.setdefault(buff_guid, set()).add(effect.guid)

    def _strategy_8_asset_reference_propagation(self) -> None:
        changed = True
        while changed:
            changed = False
            for guid, dlc_guids in list(self._dlc_map.items()):
                asset = self._cache.elements.get(guid)
                if not asset or not asset.template:
                    continue

                tmpl_name = asset.template.name

                # Tech -> Rewards.Effects
                if tmpl_name == "Tech":
                    guids = self._get_list_guids(asset, "Tech.Rewards.Effects", "EffectAsset")
                    if self._propagate_to_guids(guids, dlc_guids):
                        changed = True

                # Effect -> Buffs (guarded)
                if tmpl_name == "Effect":
                    try:
                        for buff_item in asset.Effect.Buffs:
                            ref = buff_item.GUID
                            if ref and ref.value:
                                buff_guid = ref.value.guid
                                all_effs = self._buff_to_effects.get(buff_guid, set())
                                if (
                                    all_effs
                                    and all(eff in self._dlc_map for eff in all_effs)
                                    and self._propagate_to_guids([buff_guid], dlc_guids)
                                ):
                                    changed = True
                    except Exception:
                        pass

                # Item/ItemWithBoost -> inline Effect.Buffs (guarded)
                if tmpl_name in ("Item", "ItemWithBoost"):
                    try:
                        for buff_item in asset.Effect.Buffs:
                            ref = buff_item.GUID
                            if ref and ref.value:
                                buff_guid = ref.value.guid
                                all_effs = self._buff_to_effects.get(buff_guid, set())
                                if (
                                    not all_effs or all(eff in self._dlc_map for eff in all_effs)
                                ) and self._propagate_to_guids([buff_guid], dlc_guids):
                                    changed = True
                    except Exception:
                        pass

                # BuildingBuff -> AdditionalFunctionalEffect + ProvidedNeedUpgrade
                if tmpl_name == "BuildingBuff":
                    try:
                        afe = asset.find("BuildingUpgrade.AdditionalFunctionalEffect")
                        if afe and getattr(afe, "value", None):
                            afe_guid = int(getattr(afe.value, "guid"))
                            if self._propagate_to_guids([afe_guid], dlc_guids):
                                changed = True
                    except Exception:
                        pass

                    try:
                        for pnu_item in asset.ResidenceUpgrade.ProvidedNeedUpgrade:
                            ref = getattr(pnu_item, "ProvidedNeed", None)
                            if isinstance(ref, ReferenceAttribute) and ref.value:
                                need_asset = ref.value
                                np_ref = need_asset.find("Need.NeedProduct")
                                if (
                                    isinstance(np_ref, ReferenceAttribute)
                                    and np_ref.value
                                    and np_ref.value.guid in self._dlc_map
                                    and self._propagate_to_guids([need_asset.guid], dlc_guids)
                                ):
                                    changed = True
                    except Exception:
                        pass

                # Monument/HippodromeBuilding -> BuildingRank -> RankEffect + AdditionalEffect
                if tmpl_name in ("Monument", "HippodromeBuilding"):
                    try:
                        ranks = asset.find("BuildingRank.Ranks")
                        if isinstance(ranks, ListAttribute):
                            for rank_item in ranks:
                                for field in ("RankEffect", "AdditionalEffect"):
                                    ref = getattr(rank_item, field, None)
                                    if (
                                        isinstance(ref, ReferenceAttribute)
                                        and ref.value
                                        and self._propagate_to_guids([ref.value.guid], dlc_guids)
                                    ):
                                        changed = True
                    except Exception:
                        pass

                # Building -> FunctionalEffects (guarded)
                try:
                    fe_list = asset.find("Building.FunctionalEffects")
                    if isinstance(fe_list, ListAttribute):
                        for effect_item in fe_list:
                            try:
                                func_ref = getattr(effect_item, "FunctionalEffect", None)
                                if isinstance(func_ref, ReferenceAttribute) and func_ref.value:
                                    eff_guid = func_ref.value.guid
                                    all_blds = self._fe_to_buildings.get(eff_guid, set())
                                    if (
                                        all_blds
                                        and all(b in self._dlc_map for b in all_blds)
                                        and self._propagate_to_guids([eff_guid], dlc_guids)
                                    ):
                                        changed = True
                            except Exception:
                                pass
                except Exception:
                    pass

    def _strategy_9_need_product(self) -> None:
        need_template = self._cache.templates.get("Need")
        if need_template:
            for need in list(need_template.assets):
                product_asset = need.find_value("Need.NeedProduct")
                if isinstance(product_asset, Asset):
                    for dlc_guid in self._dlc_map.get(product_asset.guid, set()):
                        self._add_dlc(need.guid, dlc_guid)

    def _populate_reference_dicts(self) -> None:
        """Populate asset.unlocked_by_dlcs / dlc_asset.dlc_unlocks from final _dlc_map.
        Seeded entries (from _seed_unlock_references) are preserved.
        """
        for asset_guid, dlc_guids in self._dlc_map.items():
            asset = self._cache.elements.get(asset_guid)
            if asset is None:
                continue
            for dlc_guid in dlc_guids:
                dlc_asset = self._dlc_guid_to_asset.get(dlc_guid)
                if dlc_asset is None:
                    continue
                if dlc_guid not in asset.unlocked_by_dlcs:
                    asset.unlocked_by_dlcs[dlc_guid] = WeightedReference(source=dlc_asset, target=asset)
                if asset_guid not in dlc_asset.dlc_unlocks:
                    dlc_asset.dlc_unlocks[asset_guid] = WeightedReference(source=asset, target=dlc_asset)
