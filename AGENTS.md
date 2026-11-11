# Asset Extractor Guide for AI Agents

This guide documents how to navigate and extract data from Anno 117's asset structure using the asset-extractor library.

## Project Overview

Asset Extractor is a modular Python library for reading Anno game `assets.xml` files, resolving dependencies, and converting them into legible formats. It supports localization and icon conversion for Anno 117.

## Architecture

Four modules under `assetextractor/`:

1. **Extraction** (`assetextractor/extraction/`) — opens RDA files via `RDAConsole.exe`, extracts XML/DDS/CFG to a cache directory.
   - `utils.py` — `Config` class for path management
   - `extract.py` — dynamic RDA extraction
2. **Parsing** (`assetextractor/parsing/core/`) — reads XML files and reconstructs the hierarchical structure with full inheritance resolution.
   - `templates.py` (asset structure / OOP-class analogue), `assets.py` (concrete instances), `properties.py` (nested building blocks), `attributes.py` (typed values), `common.py` (base classes), `texts.py` (localization), `uitext.py` (UI text mapping).
   - `assetextractor/parsing/typed/` — optional **game-domain `Asset` subclasses** (Patron, LandUnit, OrnamentalBuilding, ProductionChain, …) that expose typed, computed views over the raw asset data. Registered by template name and auto-applied during `AssetCache.load()`, so `template.assets` returns the correct subclass. See `assetextractor/parsing/typed/README.md`.
3. **Conversion** (`assetextractor/conversion/`) — generates excerpts (HTML, JSON) from parsed asset data.
   - `assetbrowser/` — Jinja2 HTML converter; outputs to `config.assetbrowser_dir`; requires a `Config` passed to `Converter`.
   - `statistics/` — item extraction and Google Sheets export, plus domain extractors that emit simplified JSON + icons: `patron_extractor.py` (`PatronExtractor`), `ornaments_extractor.py` (`OrnamentsExtractor`), `production_chain_extractor.py` (`ProductionChainExtractor`), `specialist_extractor.py` (`SpecialistExtractor`), `fertility_set_extractor.py` (`FertilitySetExtractor`), and `icon_processor.py` (`IconProcessor`, shared icon export). Each has a companion notebook (`patrons.ipynb`, `ornaments.ipynb`, `production_chains.ipynb`, `specialists.ipynb`).
4. **Versioning** (`assetextractor/versioning/`) — tracks asset changes across game versions in SQLite (`versioning/anno117/assets.db`); supports snapshot, diff, export to CSV/JSON, and history queries.

## Topic Documentation

In-depth guides live under `docs/`. Read the relevant file before working on a topic:

- Development commands, release workflow, configuration, dependencies — `docs/development.md`
- Implementation notes (key concepts, RDA quirks, parsing pitfalls, iteration) — `docs/implementation_notes.md`
- Buffs and `Asset.buff_ui` — `docs/buffs.md`
- Asset pools (RewardPool / AssetPool, flattening, reverse index) — `docs/asset_pools.md`
- UI text mapping (rarity, niche, BuffUpgradeType, etc.) — `docs/ui_text_mapping.md`
- Boost conditions (`ItemWithBoost`) — `docs/conditions.md`
- Item sources (traders, tech, quests, expeditions) — `docs/item_sources.md`
- Assembly factions (island takeover by faction support, seats, regions, modding) — `docs/assembly_factions.md`
- API patterns (`find` / `find_value`, iteration, formatting) — `docs/api_patterns.md`
- Typed asset subclasses (registry, writing a subclass, notebook re-wrapping) — `assetextractor/parsing/typed/README.md`
- Test conventions — `tests/AGENTS.md`

## Running Scripts and Modules

Always run scripts as modules from the project root (`C:\dev\asset-extractor`) using `-m`. Running by file path will fail with `ModuleNotFoundError`.

```bash
uv run python -m assetextractor.extraction.extract
uv run python -m assetextractor.versioning
uv run pytest                                    # tests handle imports automatically
uv run pytest -k "building_size"                 # tests matching keyword
```

Path → module: drop the `.py`, replace `/` with `.`. Example: `assetextractor/extraction/extract.py` → `assetextractor.extraction.extract`.

## Class Reference

### Parsing (`assetextractor/parsing/core/`)

**common.py**
- `NamedElement[CacheT]` — base class; `name`, `find()`, `find_value()`, `get()`, `full_path`, `property_path`
- `Group[CacheT]` — container, `print_tree()`
- `ElementCache[ElementT, GroupT]` — `add()`, `get()`, `find()`, `print_tree()`
- `Dataset` / `DatasetCache` — datasets.xml; `literals` property
- `AttributeMissingError` — raised for missing XML attributes

**attributes.py**
- `parse_bool(text)` — Anno boolean parser
- `Property` — nested property; `resolve_inheritance()`, `print_tree()`
- `Attribute[CacheT, ValueT]` — base; `__call__()`, `is_compound`, `is_default`
- `PrimitiveAttribute` — Boolean/Choice/Float/FloatOrPercental/Int64/Integer/String; `ui_text_id`, `ui_icon_guid`, `ui_text_variants`, `buff_ui`
- `ColorAttribute`, `TextAttribute`, `TimeAttribute`
- `UpgradeAttribute` — numeric + percental; `buff_ui`
- `FlagsAttribute` — semicolon-separated dataset literals; `buff_ui`
- `FileNameAttribute` — file path with .dds resolution; `is_image`, `get_image()`, `get_data_url()`
- `ReferenceAttribute` / `QuestAttribute` — GUID references
- `ListItem` / `ListAttribute` — ordered lists; `buff_ui`
- `GenericDictAttribute` / `DictAttribute` — dict-like; `buff_ui`
- `TemplateAttribute` — AutoCreateAsset; `set_template()`, `process_properties()`
- `AttributeFactory` — `create()`, `create_default_node()`

**properties.py**
- `ValueDefinition`, `MetaProperty`, `PropertyGroup`, `MetaPropertyCache` — properties-toolone.xml metadata; `resolve_template_attributes()`

**templates.py**
- `WeightedReference`, `Template` (`add_instance()`, `assets`), `TemplateGroup`, `TemplateCache`

**assets.py**
- `Asset` — concrete instance; `guid`, `text`, `template`, `resolve_inheritance()`, `set_referenced_by()`, `print_tree()`, `short_description`, `long_description`, `buff_ui` (returns `list[BuffUI]`); `find_ref(path)` returns a resolved `Asset | None`. Subclass registry: `Asset._registry`, `__init_subclass__(template_names=...)`, classmethod `Asset.create(node, cache)`.
- `AssetGroup`, `AssetCache` — `resolve_inheritance()`, `resolve_references()`, `resolve_dlc_unlocks()`, static `load(config)`

**attributes.py (additions)**
- `AnnoColor` (dataclass: Anno signed-int ↔ RGBA/hex); `ColorAttribute.get_hex(color_mode="None")` → `#RRGGBBAA`, `ColorAttribute.get_rgba(...)` → `(r,g,b,a)`. `color_mode` ∈ `None|Deuteranopia|Protanopia|Tritanopia`.

**texts.py**
- `Text` — `id`, `values`, `has_html_escapes()`, `count_format_args()`, `format(list)`, `__call__()`
- `TextCache` — loads texts_*.xml; `converter` property
- `StandardTextConverter` — `__call__(text)` for language-specific output

**uitext.py**
- `UITextMapping` — dataclass: `text_id`, `text`, `icon`, `variants`
- `BuffUI` — dataclass: `icon`, `text`, `value`, `literal`
- `UITextCache` — `get_ui_text()`, `get_text_id()`, `get_buff_type_name()`, `format_buff_text()`, `create_buff_ui()`, `create_buff_ui_list()`, `create_buff_ui_dict()`, `create_buff_ui_flags()`

### Typed subclasses (`assetextractor/parsing/typed/`)

Game-domain `Asset` subclasses, each declaring `template_names=` so `Asset._registry` maps a template name to its class; `AssetCache.load()` imports the package and every asset is built via `Asset.create()`. `template.assets` already returns the right subclass. Concrete classes cover patrons, buildings (ornamental, aqueduct, residence, trade, public-service, villa), buffs (area/building/ship/defense), units and upgrades (building/factory/health/maintenance/movement/residence/trade-ship/unit/vehicle), economy/fertility, map generator (fertility set/pool), ownership (UplayProduct), factories and production chains. Abstract bases (`AssetPoolBase`, `AssetWithCosts`, `AssetWithMaintenance`) have no `template_names=`. Full usage — writing a subclass, notebook re-wrapping without reloading the cache — is in `assetextractor/parsing/typed/README.md`.

### Conversion (`assetextractor/conversion/`)

- `assetbrowser/convert.py::Converter` — HTML asset browser; `render_elements()`, `render_overview()`, `run()`
- `statistics/{patron,ornaments,production_chain,specialist,fertility_set}_extractor.py` — domain extractors emitting simplified JSON (`PatronExtractor`, `OrnamentsExtractor`, `ProductionChainExtractor`, `SpecialistExtractor`, `FertilitySetExtractor`); `statistics/icon_processor.py::IconProcessor` — shared icon export (`save_image`, mirrored/flattened path options)

## Basic Setup

```python
from assetextractor.extraction.utils import Config
from assetextractor.parsing.core.assets import AssetCache

config = Config.from_json("config.json")
assets = AssetCache.load(config)
items = assets.templates["Item"].assets
```

## Item Structure

```python
item.guid
item.text.values["english"]
item.Item.Rarity()         # "Common" | "Rare" | "Epic" | "Legendary" | ...
item.Item.TradePrice()
item.Item.Allocation()     # "Villa" | "Ship" | "None"
item.Item.Niche()          # "Finance" | "Nautics" | ...
item.Item.ItemType()       # "Specialist" | "Captains" | ...
item.Effect.Targets        # affected buildings/ships
item.Effect.Buffs          # buff references
item.Effect.EffectScope()  # "Local" | "Radius" | "Session" | ...
```

For UI-localized rarity/niche/etc., use the `ui_text_id` / `ui_icon_guid` properties on attributes — see `docs/ui_text_mapping.md`.

## Complete Example

`assetextractor/conversion/statistics/extract_items.ipynb` demonstrates end-to-end item extraction: buff chains, functional effects, ItemWithBoost conditions, all source types, BuildingBuff/ShipBuff handling, CSV export.
