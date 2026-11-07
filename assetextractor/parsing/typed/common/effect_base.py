from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Dict, List, Sequence, Union, cast

from assetextractor.parsing.core.assets import Asset
from assetextractor.parsing.typed.buffs import BUFF_CLASSES, BuffKey
from assetextractor.parsing.typed.buildings import AssetBuildingBase
from assetextractor.parsing.typed.common.asset_pool_base import AssetPoolBase
from assetextractor.parsing.typed.common.building import AssetWithBuilding
from assetextractor.parsing.typed.common.cost import AssetWithCosts
from assetextractor.parsing.typed.common.enums import BuffCategory, ScopeVisualization
from assetextractor.parsing.typed.common.maintenance import AssetWithMaintenance
from assetextractor.parsing.typed.factories import AssetFactoryBase
from assetextractor.parsing.typed.production_chain import ProductionChain, ProductionChainBase

if TYPE_CHECKING:
    from assetextractor.parsing.core.attributes import ListAttribute


# Shared type definition for the production chain mapping keys to avoid repetition and errors
ChainKey = Union["ProductionChain", "AssetPoolBase", "AssetFactoryBase"]
ChainMapping = Dict[ChainKey, Dict[int, "AssetFactoryBase"]]

# Shared type definition for targets.
TargetKey = Union[AssetPoolBase, AssetFactoryBase, AssetBuildingBase]


@dataclass(frozen=True)
class EffectInfo:
    """The processed 'Effect' properties as one single object."""

    effect_scope: ScopeVisualization
    """Specific effect scope type from dataset 'Scope'. Comes from 'Effect.EffectScope'."""

    source_category: BuffCategory
    """Specific effect source category type from dataset 'BuffCategory'. Comes from 'Effect.SourceCategory'."""

    buffs: List[BuffKey]
    """List of buffs applied to the targets."""

    targets: List[TargetKey]
    """List of targets to apply the buffs."""


class AssetWithEffect(Asset):
    """
    Base class for assets that contain a 'Effect' property (this is NOT the
    same as the Template 'Effect').
    """

    @cached_property
    def effect_info(self) -> EffectInfo:
        """The structured 'Effect' (property) data."""
        # Get the literal of this effect scope and category.
        scope_text = cast("ScopeVisualization | None", self.find_value("Effect.EffectScope"))
        cat_text = cast("BuffCategory | None", self.find_value("Effect.SourceCategory"))

        return EffectInfo(
            effect_scope=scope_text or ScopeVisualization.RADIUS,
            source_category=cat_text or BuffCategory.ITEM,
            buffs=self.buffs,
            targets=self.targets,
        )

    @cached_property
    def buffs(self) -> List[BuffKey]:
        """
        Return a list of Assets that can be either 'BuildingBuff', 'ShipBuff'
        and so on.
        """
        # Populate the output list of asset buffs.
        out: List[BuffKey] = []
        for entry in cast("ListAttribute", self.find("Effect.Buffs")):
            buff = entry.find_ref("GUID")
            if isinstance(buff, BUFF_CLASSES):
                out.append(buff)
        return out

    @cached_property
    def targets(self) -> List[TargetKey]:
        """
        Return the list of 'AssetPoolNamed' asset targets whose members are
        impacted by this effect.
        """
        out: List[TargetKey] = []
        for entry in cast("ListAttribute", self.find("Effect.Targets")):
            target = entry.find_ref("GUID")
            if isinstance(target, (AssetPoolBase, AssetFactoryBase, AssetBuildingBase)):
                out.append(target)
        return out

    @cached_property
    def production_chains_by_target(
        self,
    ) -> Dict[ProductionChain | AssetPoolBase | AssetFactoryBase, Dict[int, AssetFactoryBase]]:
        """
        Dynamically clusters this effect's targets structurally.
        - Identifies structurally active complete production chains in the target pools first.
        - Binds loose regional variations and incomplete structures back into their
          parent chain contexts via factory product output/input profiles.
        - Standalone components (such as side fuel buildings) fall through safely.
        """
        mapping: Dict[ProductionChain | AssetPoolBase | AssetFactoryBase, Dict[int, AssetFactoryBase]] = {}

        def _get_chain_buildings(chain: ProductionChain) -> List[AssetFactoryBase]:
            buildings: List[AssetFactoryBase] = []

            def _traverse(node: ProductionChainBase):
                if node.building:
                    buildings.append(node.building)
                for sub in node.tier:
                    _traverse(sub)

            if hasattr(chain, "production_chain") and chain.production_chain:
                _traverse(chain.production_chain)
            return buildings

        def _find_production_chains(building: Asset) -> List[ProductionChain]:
            chains: List[ProductionChain] = []
            referenced_by = getattr(building, "referenced_by", None)
            if referenced_by:
                for ref in referenced_by.values():
                    source = getattr(ref, "source", None)
                    if source and isinstance(source, ProductionChain):
                        chains.append(source)
            return chains

        def _process_flat_buildings(pool_buildings: List[AssetFactoryBase]) -> None:
            """
            Clusters a flat sequence of building factory groups by looking for
            structural production chains, regional variants, and individual singletons.
            """
            pool_guids = {b.guid for b in pool_buildings}

            # Step 1: Discover and map completely intact structural production chains
            active_chains_in_pool: List[ProductionChain] = []
            for building in pool_buildings:
                chains = _find_production_chains(building)
                for chain in chains:
                    chain_buildings = _get_chain_buildings(chain)
                    chain_guids = {b.guid for b in chain_buildings}

                    if len(chain_guids) > 0 and chain_guids.issubset(pool_guids):
                        if chain not in mapping:
                            mapping[chain] = {}
                        mapping[chain][building.guid] = building
                        if chain not in active_chains_in_pool:
                            active_chains_in_pool.append(chain)

            # Step 2: Tie regional variants and incomplete chains to discovered chains
            for building in pool_buildings:
                # Allow common foundational ingredients (like standard Pig Farms) to map across multiple chains
                already_mapped = any(
                    chain in mapping and building.guid in mapping[chain] for chain in active_chains_in_pool
                )

                fb_info = building.factory_base_info
                building_outputs = [out.product.guid for out in fb_info.outputs if out.product]

                assigned_to_chain = False

                for chain in active_chains_in_pool:
                    chain_buildings = _get_chain_buildings(chain)
                    chain_output_guids: set[int] = set()

                    for cb in chain_buildings:
                        cb_fb = cb.factory_base_info
                        for out in cb_fb.outputs:
                            if out.product:
                                chain_output_guids.add(out.product.guid)

                    # Match Condition A: Incomplete regional chain structure outputs the same underlying product GUID
                    has_shared_product = any(p_guid in chain_output_guids for p_guid in building_outputs)

                    # Match Condition B: Variant ingredient shares a matching localized text description structure
                    has_structural_counterpart = False
                    if not has_shared_product and building.text:
                        building_text_val = building.text()
                        for cb in chain_buildings:
                            if cb.text:
                                cb_text_val = cb.text()
                                if cb_text_val == building_text_val:
                                    has_structural_counterpart = True
                                    break

                    if has_shared_product or has_structural_counterpart:
                        if chain not in mapping:
                            mapping[chain] = {}
                        mapping[chain][building.guid] = building
                        assigned_to_chain = True

                # Step 3: Absolute fallback layout frame for standalone individual singletons (e.g. Charcoal Burners)
                if not assigned_to_chain and not already_mapped:
                    if building not in mapping:
                        mapping[building] = {}
                    mapping[building][building.guid] = building

        # Temporary collection for direct AssetFactoryBase targets
        flat_targeted_buildings: List[AssetFactoryBase] = []

        for target_pool in self.targets:
            if isinstance(target_pool, AssetPoolBase):
                pool_named_asset = target_pool
                nested_pools = [sub for sub in pool_named_asset.asset_pool_list if isinstance(sub, AssetPoolBase)]

                if nested_pools:
                    # Vulcan Case: Nested sub-pools context (Mines & Quarries)
                    for active_pool in nested_pools:
                        pool_buildings = [b for b in active_pool.asset_pool_list if isinstance(b, AssetFactoryBase)]
                        pool_guids = {b.guid for b in pool_buildings}

                        for building in pool_buildings:
                            chains = _find_production_chains(building)
                            has_complete_chain = False

                            for chain in chains:
                                chain_buildings = _get_chain_buildings(chain)
                                chain_guids = {b.guid for b in chain_buildings}
                                all_present = len(chain_guids) > 0 and chain_guids.issubset(pool_guids)

                                if all_present:
                                    if chain not in mapping:
                                        mapping[chain] = {}
                                    mapping[chain][building.guid] = building
                                    has_complete_chain = True

                            if not has_complete_chain:
                                if active_pool not in mapping:
                                    mapping[active_pool] = {}
                                mapping[active_pool][building.guid] = building
                else:
                    # Neptune/Ceres/Minerva/Mars Case: Direct building pool listings
                    pool_buildings = [b for b in pool_named_asset.asset_pool_list if isinstance(b, AssetFactoryBase)]
                    _process_flat_buildings(pool_buildings)

            elif isinstance(target_pool, AssetFactoryBase):
                # Save flat AssetFactoryBase targets to process collectively
                flat_targeted_buildings.append(target_pool)

        # Process all flat-targeted AssetFactoryBase elements together
        if flat_targeted_buildings:
            _process_flat_buildings(flat_targeted_buildings)

        return mapping

    def print_affected_chains(self, scenario_b_only: bool = True) -> None:
        """
        Debug utility to quickly print the structural layout mappings for this effect.
        Skips execution if the effect contains no active targets.
        """
        affected_chains = self.production_chains_by_target

        # Verify if there is actually anything to print across all clusters
        if not affected_chains or all(not targets for targets in affected_chains.values()):
            return

        def _is_in_effect_targets(tgt: AssetFactoryBase, targets_to_match: Sequence[Asset]) -> bool:
            """Helper to recursively check if building is part of the effect target pools."""

            def _has_asset_recursive(current: Asset, target: AssetFactoryBase) -> bool:
                if current == target:
                    return True
                if isinstance(current, AssetPoolBase):
                    return any(_has_asset_recursive(sub, target) for sub in current.asset_pool_list)
                return False

            return any(_has_asset_recursive(et, tgt) for et in targets_to_match)

        def _get_chain_building_guids(chain: Asset) -> List[int]:
            """Helper to retrieve expected GUIDs for layout structure verification."""
            if isinstance(chain, AssetPoolBase):
                return [b.guid for b in chain.asset_pool_list]
            if not isinstance(chain, ProductionChain):
                return [chain.guid] if hasattr(chain, "guid") else []
            guids: List[int] = []

            def _traverse(node: ProductionChainBase) -> None:
                if node.building:
                    guids.append(node.building.guid)
                for sub in node.tier:
                    _traverse(sub)

            if hasattr(chain, "production_chain") and chain.production_chain:
                _traverse(chain.production_chain)
            return guids

        # Build Scenario B collections beforehand to check if Scenario B printing is empty
        scenario_b_output: List[
            tuple[ProductionChain | AssetPoolBase | AssetFactoryBase, List[AssetFactoryBase], List[int]]
        ] = []
        for chain, targets in affected_chains.items():
            active_production_assets = [
                tgt_asset for tgt_asset in targets.values() if _is_in_effect_targets(tgt_asset, self.targets)
            ]
            active_guids = {asset.guid for asset in active_production_assets}
            required_guids = _get_chain_building_guids(chain)

            if required_guids and all(b_guid in active_guids for b_guid in required_guids):
                scenario_b_output.append((chain, active_production_assets, required_guids))

        # If we only care about complete layouts (Scenario B) and none were found, skip printing entirely
        if scenario_b_only and not scenario_b_output:
            return

        # Print standard Header since we confirmed there is active output data to show
        print(f"{'=' * 100}")
        print(f" EFFECT: (Asset GUID: {self.guid})".center(100))
        print(f"{'=' * 100}")

        # --- Scenario A Printing ---
        if not scenario_b_only:
            print(" SCENARIO A: All Associated Chain/Pool Clusters ".center(100, "-"))
            for chain, targets in affected_chains.items():
                if not targets:
                    continue

                chain_text = chain.text() if chain.text else "N/A"
                print(f"Cluster: {chain.name} (GUID: {chain.guid}) -> Text: {chain_text}")
                print(f"  Affects {len(targets)} total target assets:")
                for target_guid, target_asset in targets.items():
                    print(f"    |- Target Asset: {target_asset.name} (GUID: {target_guid})")
                print("-" * 100)

        # --- Scenario B Printing ---
        print(" SCENARIO B: Structurally Complete Layouts Only ".center(100, "-"))
        for chain, active_production_assets, required_guids in scenario_b_output:
            chain_text = chain.text() if chain.text else "N/A"
            print(f"Chain GUID: {chain.guid} -> Text: {chain_text}")
            print(f"   Affects {len(active_production_assets)} active target assets inside layout:")
            for target_asset in active_production_assets:
                print(f"     |- Target Asset: {target_asset.name} (GUID: {target_asset.guid})")
            print("-" * 100)

    def _get_text(self, asset: Asset, def_text: str = "N/A") -> str:
        """Safely extracts localized text from an asset."""
        return asset.text() if asset.text else def_text

    def print_buffs(self, buffs: Sequence[Asset], prefix: str = "") -> None:
        """Processes and prints buff assets with clean box-drawing tree lines."""
        if not buffs:
            return

        if prefix == "":
            print(f"{'─' * 100}")
            print(f"Buffs ({len(buffs)}):")

        for idx, buff_asset in enumerate(buffs, 1):
            is_last = idx == len(buffs)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            print(f"{prefix}{connector}Buff #{idx}: {buff_asset.name} (GUID: {buff_asset.guid})")

            # Automatically find and run any printing methods that the buff
            # asset supports. I love duck-typing!.
            for method_name in (
                "print_building_upgrade_info",
                "print_residence_upgrade_info",
                "print_factory_upgrade_info",
                "print_health_upgrade_info",
                "print_movement_upgrade_info",
                "print_vehicle_upgrade_info",
                "print_trade_ship_upgrade_info",
                "print_area_need_attribute_buff_info",
                "print_maintenance_upgrade_info",
                "print_unit_upgrade_info",
            ):
                if hasattr(buff_asset, method_name):
                    method = getattr(buff_asset, method_name)
                    method(indent=child_prefix)

    def print_targets(self, targets: Sequence[Asset], chains_mapping: ChainMapping, prefix: str = "") -> None:
        """Processes and prints target assets and structural asset pools recursively.

        Args:
            targets: The sequence of target assets to loop over.
            chains_mapping: The patron's production_chains_by_target property dictionary.
            prefix: Continuous box-drawing indentation string tracking the current tree level.
        """
        if not targets:
            return

        if prefix == "":
            print(f"{'─' * 100}")
            print(f"Targets ({len(targets)}):")

        for idx, target_asset in enumerate(targets, 1):
            is_last = idx == len(targets)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            print(f"{prefix}{connector}Target #{idx}: {target_asset.name} (GUID: {target_asset.guid})")

            # Collect available properties to maintain clean node endpoints (└── vs ├──)
            sub_rows: List[str] = []

            # 1. Construction Costs
            if isinstance(target_asset, AssetWithCosts):
                costs = target_asset.formatted_costs
                if costs:
                    sub_rows.append(f"[Costs]: {', '.join([f'{c.amount} {c.ingredient}' for c in costs])}")

            # 2. Maintenance Costs
            if isinstance(target_asset, AssetWithMaintenance):
                m_costs = target_asset.formatted_maintenance_costs
                if m_costs:
                    sub_rows.append(f"[Maintenance]: {', '.join([f'{m.amount} {m.product}' for m in m_costs])}")

            # 3. Building/Category Metadata
            if isinstance(target_asset, AssetWithBuilding):
                sub_rows.append(f"[Category Name]: {target_asset.building_info.category_name}")

            # 4. Associated Production Chain Mappings
            for chain, targets_dict in chains_mapping.items():
                if target_asset.guid in targets_dict:
                    chain_text = self._get_text(chain)
                    sub_rows.append(f"[Production Chain]: {chain.name} (GUID: {chain.guid}) - {chain_text}")

            # Print collected sub-rows with proper dangling branch resolution
            for s_idx, row_text in enumerate(sub_rows, 1):
                # An attribute row is only the true end node if there is no recursive AssetPool under it
                is_last_row = (s_idx == len(sub_rows)) and not isinstance(target_asset, AssetPoolBase)
                row_connector = "└── " if is_last_row else "├── "
                print(f"{child_prefix}{row_connector}{row_text}")

            # 5. Handle AssetPool Recursion Last (Threads perfectly below the target parent)
            if isinstance(target_asset, AssetPoolBase):
                self.print_targets(target_asset.asset_pool_list, chains_mapping, prefix=child_prefix)
