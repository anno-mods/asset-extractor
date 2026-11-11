# Assembly Factions (Faction System)

The faction system is called **Assembly** in the game files. Each foreign island has an assembly in which six factions hold seats. A governor gains a faction's support by donating money; holding a supermajority of the seats enables a peaceful takeover of the island. The military takeover is a separate system (`MilitaryTakeoverScene`).

The data below was read from the playtest cache (`.cache-117-playtest`) and compared with the release cache (`.cache-117`). Differences between the two builds are listed in [Release vs. playtest](#release-vs-playtest). The assets hold parameters only; how seats, presence and bonus values are combined is engine logic and is not recorded in the assets.

## Assets

| Asset | Template | GUID | Role |
|---|---|---|---|
| Faction Craftsmen / Merchants / Devotees / Polymaths / Families / Traditionalists | `AssemblyFaction` | 41797 / 41798 / 41799 / 41800 / 41801 / 41802 | One asset per faction |
| TakeoverBalancing | `AssemblyTakeoverBalancing` | 41817 | Global rules and faction-to-region mapping; the only asset that references the factions |
| AssemblyTakeoverScene | `AssemblyTakeoverScene` | 42186 | UI scene (texts, icons, info tips) |
| MilitaryTakeoverGovRequest | `GovernorRequestAsset` | 49700 | Governor request referenced by `TakeoverBalancing.GovernorRequest` |
| FactionEffect * | `Effect` | 42238, 42367-42371 | Bonus of a faction (`ProvidedBonus`) |
| FactionEffect * Buff | `AreaBuff` / `MetaBuff` | 42239, 42372-42375, 42377 | Buff contained in the effect |
| City Status Roman/Celtic/Egyptian NN | `CityStatus` | 1929, 3559, ... | Seat price (`AssemblySeatPrice`) per city status level |
| ImpactTreatyPositive_Assembly | `DiplomacyImpactTendency` | 44071 | Diplomacy impact of the Assembly Protection Treaty |
| Accept / Renew Assembly Protection | `GovernorRequestDynamicDecision` | 41424, 41425 | Governor requests for the protection treaty |

Template definitions are in `templates.xml` (group `AssemblyTakeover`) and `properties-meta.xml` (properties `AssemblyFaction` and `Takeover`).

The `AssemblyTakeoverScene` (42186), `ImpactTreatyPositive_Assembly` (44071) and the protection governor requests (41424, 41425) are referenced by no other asset. The engine finds them by template or name.

## Faction parameters

Shared by all six factions: `MinimumSeats` 5, `MaximumSeat` 100, `MinimumPresence` 5 %, `MaximumPresence` 50 %, `NeededSeatsForAdditionalBonus` 10, `AdditionalBonus` 1.0.

| Faction | `BaseBonus` | Effect | Buff |
|---|---|---|---|
| Craftsmen (41797) | 1.0 | 42367, `AreasInSession` | `AreaMaintenanceUpgrade`: +1 Libertus workforce, +1 Wader workforce |
| Merchants (41798) | 0.5 | 42238, `Meta` | `MetaEconomyBuff`: `AdditionalMoneyIncome` +10 |
| Devotees (41799) | 4.0 | 42368, `AreasInSession` | `AreaNeedAttributeBuff`: `BonusAttributes` +2 |
| Polymaths (41800) | 4.0 | 42369, `AreasInSession` | `AreaNeedAttributeBuff`: `BonusAttributes` +2 |
| Families (41801) | 4.0 | 42370, `AreasInSession` | `AreaNeedAttributeBuff`: `BonusAttributes` +2 |
| Traditionalists (41802) | 5.0 | 42371, `AreasInSession` | `AreaNeedAttributeBuff`: `BonusAttributes` +1, +1, +1 (three entries) |

All effects have `SourceCategory: Assembly` and `HideInGovernorsBar: 1`. The need attributes targeted by `BonusAttributes` are not resolved here.

The template default `ProvidedBonus` is GUID 32511. No asset with this GUID exists; every faction overrides it.

## Seats from buildings

`FactionProviderBuildings` lists the buildings that give a faction seats (`ProvidedSeats`, 1 each). Every faction has 12 entries. All 59 listed buildings are Roman or Celtic; none is Egyptian.

Buildings that count for several factions:

| Building | Factions |
|---|---|
| Roman Baths (3620) | Craftsmen, Families, Traditionalists |
| Roman Celtic Baths (8062) | Craftsmen, Families, Traditionalists |
| Celtic Chariots (5616) | Craftsmen, Devotees, Merchants |
| Roman Celtic Mirrors (5615) | Craftsmen, Families, Traditionalists |
| Roman Forum (3617) | Devotees, Polymaths, Merchants |
| Roman Celtic Temple (6729) | Polymaths, Merchants |
| Celtic Clan Shield (31773) | Polymaths, Families, Merchants |
| Roman Lyres (4832) | Polymaths, Traditionalists |
| Roman Celtic Fanum (6728) | Devotees, Traditionalists |

### Data inconsistencies

- **Clan Shield without seats:** The entries for 31773 in Polymaths and Families have no `ProvidedSeats` value, so they give 0 seats. Merchants gives 1 seat for the same building.
- **Empty entry in Devotees:** One `FactionProviderBuildings` item has `ProvidedSeats` 1 but no `ProviderBuilding`. It sits between Celtic Torcs (5606) and Celtic Chariots (5616). The Devotees have 11 resolvable buildings.

## Regions

The `Region` dataset has four values: `Meta` (0), `Roman` (7), `Celtic` (8), `Egyptian` (12).

`TakeoverBalancing.AssemblyFactionsPerRegion` maps a region to its factions:

| Region | Factions |
|---|---|
| Roman | All six (inherited from the template default of `AssemblyTakeoverBalancing`) |
| Celtic | All six (set in the asset) |
| Meta | None |
| Egyptian | None |

The three Egyptian-looking factions in the Naukratis quest (`QO Factions in Naukratis - Peregrine Leaguers`, `Kumatic Partisans`, `Hellenic Purists`) are quest objects and have no connection to `AssemblyFaction`.

## Global rules (`TakeoverBalancing`, GUID 41817)

| Property | Value |
|---|---|
| `AssemblyFactionUpdateTime` | 120000 ms (template default 300000 ms) |
| `AssemblySupermajorityPercent` | 66.66 |
| `AssemblyDonationCooldown` | 300000 ms |
| `AssemblyTransferRationPercent` | 50 |
| `GovernorRequest` | 49700 |
| `TakeoverInfolayerConquering` / `TakeoverInfolayerVassalized` | 44193 / 44194 |
| `MilitaryTakeoverNotificationForNewOwner` / `...ForPreviousOwner` | 52661 / 52662 |
| `VassalizedIslandTakenOverByOtherParticipant` | 93790 |
| `ReputationCostFactor` | 15 |
| `MilitaryTakeoverRadius` | 10 |
| `MoneyCostFactor` | 80 % |

### Seat price

`CityStatus.AssemblySeatPrice` is 1000 at level 1 and rises by 50 per level to 1700 at level 15. Levels above 15 stay at 1700. Roman and Celtic have 45 levels each, Egyptian has 35 levels.

## Related engine hooks

- Dataset `PlayerCounter`: `BoughtAssemblyFaction`, `LostAssemblyFaction`.
- Dataset (game event): `BuyAssemblyFaction` ("Buy a Share", id 82) and `AssemblyTakeover` (id 153).
- Texts: `AssemblyTakeoverScene ...` (seats, supporting text, supermajority title, donation, cooldown, island filter, popup), `AssemblyTakeoverTakeoverButtonInfoTip_*` (headline, no supermajority, assembly protection treaty), `AssemblyTakeover_OwnFactionError`, `AssemblyTakeover_OwnIslandWarning`.
- Info tips: `AssemblyTakeoverTakeoverButtonInfoTip` (43737), `AssemblyTakeoverDonationButton` (43863), `AssemblyTakeoverCancelButton` (43991).
- Gamepad bindings in `console/balancing/balancing.xml`: `AssemblyTakeoverFocusMacroMap`, `AssemblyTakeoverFocusIslandList`.
- Audio: `PaMSy_Athr_Expansion_NPCAssemblyTakeover_*` and `..._PlayerAssemblyTakeover_*`.
- Prop `faction_flag` (3 variants) for faction flags on islands; `MoodImage` on `AssemblyFaction`.

## Release vs. playtest

All assembly assets are identical in both builds: factions, effects, buffs, `TakeoverBalancing`, `AssemblyTakeoverScene`, info tips, treaty assets and templates. Differences exist only in content added by the playtest build:

- `CityStatus` assets for the Egyptian region (GUIDs 149795, 149796, 154821-154853) carry `AssemblySeatPrice`; the release cache has no Egyptian city statuses.
- The three Naukratis quest objects (154606, 158501, 158502) and the sequence 173989 (`MurderMystery_SpokeToFactions`) exist only in the playtest build. They are unrelated to the assembly system.

The release cache holds no `texts_*.xml` and no `balancing.xml`, so texts and gamepad bindings could not be compared.

## Modding

Mods patch `assets.xml` through the Anno mod loader (documentation: <https://jakobharder.github.io/anno-mod-loader/>; mods go into `<installation dir>/mods/` or `<user documents>/Anno 117 - Pax Romana/mods/`; GUID ranges must be reserved at <https://github.com/anno-mods/GuidRanges>).

**Data that a mod can change** (all of it is plain asset data):

- Faction values (`BaseBonus`, seat limits, presence limits, provider buildings and seats).
- Faction effects and buffs.
- Faction lists per region in `TakeoverBalancing` (for example an `Egyptian` entry), supermajority, cooldown, transfer ratio and cost factors.
- Seat prices in `CityStatus`.
- New factions (a new `AssemblyFaction` asset, its `Effect` and buff, and an entry in `AssemblyFactionsPerRegion`).

**Not decidable from the assets:** whether the engine exposes the assembly takeover flow (button, donation, scene) for a given island. No asset gates the scene, the treaty or the governor requests, so any gate is in the engine. The `AssemblyTakeoverScene` with its texts and info tips, the `BuyAssemblyFaction` and `AssemblyTakeover` game events and the player counters show that engine support exists. Whether it is reachable in the live game has to be tested in-game with a minimal mod (for example adding an `Egyptian` faction list, or changing `AssemblySupermajorityPercent`) and by reading `mod-loader.log`.

**Likely obstacles:**

- Egyptian islands have no factions in `AssemblyFactionsPerRegion` and no Egyptian provider buildings, so a mod needs both a faction list and building entries for that region.
- The inconsistencies listed above (Clan Shield without seats, empty Devotees entry) suggest that the seat data was not finished.
