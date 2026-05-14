# Typed Asset Subclasses

This package contains game-domain `Asset` subclasses. Each subclass declares which XML template name(s) it handles via the `template_names=` keyword, and the `Asset` base class auto-registers them.

## How it works

`Asset.__init_subclass__` fires when Python defines a subclass. The `template_names=` keyword populates `Asset._registry`. When `AssetCache` is constructed, every `<Asset>` node is instantiated via `Asset.create()`, which looks up the right subclass in the registry.

`BaseAssetGUID` assets (no `<Template>` tag) are initially created as plain `Asset` instances and upgraded to the correct subclass in `AssetCache.resolve_inheritance()`, once the base asset's template name is known.

## Adding a new typed subclass

1. Create `assetextractor/parsing/typed/my_thing.py`.
2. Declare the class with `template_names=`:

```python
from assetextractor.parsing.core.assets import Asset

class MyThing(Asset, template_names="MyTemplateName"):
    ...
```

The `pkgutil` auto-discovery in `typed/__init__.py` imports every module in this package on `AssetCache.load()`, so **no other file needs to change**.

## Mapping multiple templates to one class

Pass a list to `template_names`:

```python
class ProductionVariant(AssetWithCosts, template_names=["Production", "SlotFactoryBuilding7"]):
    ...
```

Each name in the list registers independently. Later registrations override earlier ones for the same name, so order matters when the same template name would be claimed by two classes.

## Caveats

**Abstract bases have no `template_names=`.**  
`AssetPoolBase`, `AssetWithCosts`, and `AssetWithMaintenance` are intermediate base classes, not tied to a specific template. Only concrete leaf classes should declare `template_names=`.

**The registry is populated at import time.**  
`AssetCache.load()` imports this package before constructing the cache, ensuring the registry is full. Any code that constructs `AssetCache` directly (bypassing `load()`) must import `assetextractor.parsing.typed` first or the registry will be empty.

**`cached_property` and `__init__` assignments conflict.**  
Do not set an instance attribute in `__init__` with the same name as a `@cached_property` — the instance attribute silently shadows the descriptor and the property is never invoked.

**`BaseAssetGUID` upgrade creates a new instance.**  
For assets resolved through `BaseAssetGUID`, `AssetCache.resolve_inheritance()` instantiates the typed subclass fresh from the original XML node. If you store a reference to the plain `Asset` before `AssetCache` finishes loading (e.g. during `__init__`), that reference will become stale. Always resolve typed assets after `AssetCache.load()` returns.

**Template name must match the XML `<Template>` tag exactly.**  
Check the asset browser or `templates.xml` to confirm spelling and casing. Names are case-sensitive (e.g. `"Production Field"` vs `"ProductionField"`).

## Iterating without reloading the cache

`AssetCache.load()` is the slow part (XML parsing, inheritance and reference resolution). Typed subclasses are just thin views over the already-loaded `(node, cache)` data, so you never need to reload the cache when changing a subclass.

**Re-wrap a specific asset on demand**

```python
from assetextractor.parsing.typed.land_unit import LandUnit
unit = LandUnit(assets[37553].node, assets)
unit.maintenance_costs   # computed fresh from already-loaded data
```

`Asset.__init__` is O(1) — it only reads a few XML text nodes. All properties are lazy, so nothing is computed until accessed.

**In-place reclassification after `importlib.reload`**

```python
import importlib
import assetextractor.parsing.typed.land_unit as m

importlib.reload(m)
asset = assets[37553]
asset.__class__ = m.LandUnit   # swap the class in-place
del asset.__dict__             # clear stale cached_property values
asset.maintenance_costs        # now uses the reloaded class
```

`@cached_property` stores results in the instance `__dict__`, so swapping `__class__` alone does not clear them. Delete specific keys (e.g. `del asset.__dict__["maintenance_costs"]`) or wipe the whole dict if the property logic changed.

**Typical notebook workflow**

- **Cell 1** (run once): `assets = AssetCache.load(config)`
- **Cell 2** (re-run freely): test with `LandUnit(assets[guid].node, assets)`, or patch `__class__` on a handful of instances

To make `Asset.create()` pick up a reloaded class for any newly constructed cache, reload `assetextractor.parsing.typed` (which re-runs auto-discovery and repopulates `Asset._registry`).

## API quick reference

### Reading attribute values

| Goal | API |
|---|---|
| Raw value (int, str, bool) | `asset.find_value("Group.Field")` |
| Referenced asset | `asset.find_ref("Group.Field")` -> `Asset \| None` |
| Referenced asset from a list item | `entry.find_ref("FieldName")` -> `Asset \| None` |
| Localized text string | `asset.text()` -- `Text.__call__()` uses the active converter |
| Name with text fallback | `asset.short_description` -- `text()` -> `name` -> `{guid}` |

### Schema guarantees — no defensive guards needed

- Every attribute in the template **always exists** on the asset; `find()` / `find_value()` never return `None` for a known path.
- Attributes **always have a value**; no `if value is not None` needed before using it.
- `find_value` calls `()` on the element and returns the **raw Python value** directly; no `isinstance(attr, PrimitiveAttribute)` etc.
- `find_ref` returns the **already-resolved `Asset`**; no `cache.get(ref.guid)` needed.

### Iterating a list attribute

```python
# cast once for static typing; the schema guarantees a ListAttribute
for entry in cast("ListAttribute", self.find("Group.Items")):
    asset  = entry.find_ref("Asset")                       # reference field
    amount = cast(int, entry.find_value("Amount") or 0)    # primitive field
    text   = cast(Text | None, entry.find_value("Title"))  # text field
    result = text() if text else "fallback"
```

### Text localization

```python
asset.text()   # localized string via the active texts.converter

# Attribute that holds a Text object:
text_obj = cast(Text | None, self.find_value("Some.TextField"))
result = text_obj() if text_obj else "fallback"

# Set the converter language once before extraction:
assets.texts.converter = StandardTextConverter("english")
```

### Accessing typed assets from a template

```python
template = assets.templates.get("Patron")
patrons = [a for a in template.assets if isinstance(a, Patron)] if template else []
```

All assets in `template.assets` are already the correct subclass (registry guarantee), so the `isinstance` filter is only needed for static type narrowing.
