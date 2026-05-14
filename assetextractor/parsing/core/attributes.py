from __future__ import annotations

import base64
import datetime
import logging
import typing as t
from contextlib import suppress
from io import BytesIO
from pathlib import Path

import lxml.etree as et

from assetextractor.parsing.core.common import ElementCache, NamedElement, WeightedReference
from assetextractor.parsing.core.texts import Text, parse_text_id

logger = logging.getLogger("parsing")


class WandImageProto(t.Protocol):
    width: int
    height: int
    format: str
    compression_quality: int

    def __init__(self, image: "WandImageProto | None" = None, filename: str | None = None) -> None: ...
    def __enter__(self) -> "WandImageProto": ...
    def __exit__(self, *args: object) -> None: ...
    def resize(self, width: int, height: int) -> None: ...
    def save(self, file: t.IO[bytes]) -> None: ...


def _load_wand_image() -> type[WandImageProto]:
    """Import wand.image.Image lazily.

    Raises ImportError with installation guidance if Wand/ImageMagick is missing.
    """
    try:
        from wand.image import Image as WandImage  # type: ignore[import-untyped]
    except ImportError as e:
        raise ImportError(
            "Image processing requires the optional 'Wand' package and a working ImageMagick installation. "
            "Install with: uv sync --extra images. "
            "See README.md ('Optional: ImageMagick / Wand for image processing') for ImageMagick setup."
        ) from e
    return t.cast("type[WandImageProto]", WandImage)


AttributeParentT: t.TypeAlias = t.Union[
    "Attribute[MetaPropertyCache, t.Any]", "Property", "ListItem", "NamedElement[MetaPropertyCache]", None
]

if t.TYPE_CHECKING:
    from assetextractor.parsing.core.assets import Asset
    from assetextractor.parsing.core.properties import MetaProperty, MetaPropertyCache, PropertyGroup, ValueDefinition
    from assetextractor.parsing.core.templates import Template, TemplateCache
    from assetextractor.parsing.core.uitext import BuffUI


def parse_bool(text: str | None) -> bool:
    if text is None:
        return False
    return str(text).strip().lower() not in ("0", "false", "")


# Property must be here due to cyclic constructor calls between Property and TemplateAttribute
class Property(NamedElement[t.Any]):
    """Building block for templates, can be nested. Can be used like a dictionary with the only exception that a for-each iterates over values instead of keys. One can easily get the key by `value.name`."""

    def __init__(self, node: et._Element, parent: NamedElement[t.Any], meta: MetaProperty, cache: MetaPropertyCache):
        super().__init__(node, parent, cache, str(node.tag))

        self.meta = meta
        self.cache = cache
        self.inherited = False
        self.attributes: dict[str, Attribute[t.Any, t.Any]] = dict()
        self.properties: dict[str, Property] = dict()
        self._full_path = None
        self._property_path = None

        all_properties = set(child for child in self.node.iterchildren() if isinstance(child.tag, str))
        for meta_property in self.meta.properties.values():
            # if meta_property.export_serialize_code:
            #    continue

            name = meta_property.name
            child = node.find(name)
            if child is None:
                setattr(self, name, None)
                continue
            all_properties.remove(child)

            self.properties[name] = Property(child, self, meta_property, self.cache)
            setattr(self, name, self.properties[name])

        for value_definition in self.meta.value_definitions.values():
            name = value_definition.name
            child = node.find(name)

            if child is not None:
                all_properties.remove(child)

            attribute = AttributeFactory.create(child, self, value_definition, cache)

            self.attributes[name] = attribute
            setattr(self, name, attribute)

        for child in all_properties:
            logger.info(
                f"Ignoring property {child.tag} without meta definition in property {self.full_path} [{self.source}]"
            )

    @property
    def is_compound(self) -> bool:
        return True

    @staticmethod
    def process(parent: PropertyGroup, node: et._Element, container: dict[str, Property], cache: MetaPropertyCache):
        """Creates Property objects given an xml node and stores them in container."""
        for child in node.iterchildren():
            meta_property = parent.elements.get(str(child.tag))

            if meta_property is None:
                logger.info(f"Ignoring property {parent.full_path}.{child.tag} [{parent.source}]")
                continue

            # this check would lead to cyclic imports
            # if not isinstance(meta_property, MetaProperty):
            #    raise ValueError(f"Got group but expected property for {child.tag} in {parent.full_path}")

            prop = Property(child, parent, meta_property, cache)  # type: ignore
            container[str(prop.name)] = prop

    def resolve_inheritance(self, default: Property):
        """Recursively override not initialized attributes with the values form default."""
        for meta_property in self.meta.properties.values():
            # if meta_property.export_serialize_code:
            #    continue

            if (prop := self.properties.get(meta_property.name)) is None:
                logger.debug(f"Copy {meta_property.name} from {default.full_path} [{default.source}]")
                prop = getattr(default, meta_property.name)
                setattr(self, meta_property.name, prop)
                if prop is not None:
                    self.properties[meta_property.name] = prop
            else:
                logger.debug(f"{prop.name} from {default.full_path} [{default.source}]")
                prop.resolve_inheritance(getattr(default, meta_property.name))

        for value_definition in self.meta.value_definitions.values():
            name = value_definition.name
            default_attr = default.attributes.get(name)
            if default_attr is None:
                raise ValueError(
                    f"Missing attribute {name} of type {value_definition.data_type} in {default.full_path} [{default.source}] (found when updating inheritance in {self.full_path})"
                )

            if (attr := self.attributes.get(name)) is None:
                logger.debug(f"Copy {name} from {default_attr.full_path} [{default_attr.source}]")
                setattr(self, name, default_attr)
                self.attributes[name] = default_attr
            else:
                if attr.is_default:
                    logger.debug(f"Copy {attr.name} from default {default_attr.full_path} [{default_attr.source}]")
                    self.attributes[name] = default_attr
                    setattr(self, name, default_attr)
                else:
                    logger.debug(f"{attr.name} from {default.full_path} [{default.source}]")
                    attr.resolve_inheritance(default_attr)

    def find_ref(self, path: str) -> Asset | None:
        """Follow path and return the referenced Asset, or None if missing or unresolved."""
        return t.cast("Asset | None", self.find_value(path))

    def get_tree_note(self, inherited: bool) -> str:
        if inherited:
            return "*"

        return ""

    def print_tree(self, indent: str = "", inherited: bool = False):
        print(f"{indent}{self.name}{self.get_tree_note(inherited)}:")
        for attribute in self.attributes.values():
            attribute.print_tree(indent + "\t", attribute.parent != self)
        for property in self.properties.values():
            property.print_tree(indent + "\t", property.parent != self)

        if indent == "":
            print("*) inherited")

    def print_meta_tree(self, indent: str = ""):
        self.meta.print_tree(indent)

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        return key in self.attributes or key in self.properties

    def __iter__(self) -> t.Iterator[Attribute[ElementCache[t.Any, t.Any], t.Any] | Property]:
        for attribute in self.attributes.values():
            yield attribute

        for attribute in self.properties.values():
            yield attribute

    def __getitem__(self, key: str) -> Attribute[t.Any, t.Any] | Property | None:
        """Allows bracket notation access to elements."""
        if key in self.attributes:
            return self.attributes[key]
        if key in self.properties:
            return self.properties[key]
        return None


class Variable:
    """Mixin for attributes that can be variables (placeholders with names instead of concrete values).

    When is_variable is True, the attribute contains a variable name rather than a concrete value.
    This is used for dynamic references and placeholders in the asset system.

    Attributes:
        is_variable: Whether this attribute is a variable (placeholder)
        variable_name: The variable name if is_variable is True, None otherwise
    """


class Attribute[CacheT: ElementCache[t.Any, t.Any], ValueT](NamedElement[CacheT]):
    """Virtual base class for all attributes."""

    def __init__(self, node: et._Element, parent: t.Any, meta: ValueDefinition, cache: CacheT):
        super().__init__(node, parent, cache, name=str(node.tag))

        self.meta = meta
        self.cache = cache
        self.value: ValueT | None = None
        self.is_variable = False

        self._value_text = node.text

    def resolve_inheritance(self, default: t.Self | None):
        if self.meta.default == self and default is not None:
            raise ValueError(f"Trying to override default attribute {self.meta.full_path} with {default.full_path}")

        if default is not None and self.value is None:
            self.value = default.value  # For non-primitive attributes: copy values from default to self

    @property
    def is_compound(self) -> bool:
        """Checks if the attribute is compound."""
        return self.meta.is_compound

    @property
    def is_default(self) -> bool:
        """Checks if the attribute is default."""
        return self.meta.default == self or self.node.sourceline is None

    def find_ref(self, path: str) -> Asset | None:
        """Follow path and return the referenced Asset, or None if missing or unresolved."""
        return t.cast("Asset | None", self.find_value(path))

    def get_tree_note(self, inherited: bool = False) -> str:
        """Returns a note for the tree representation."""
        if self.is_default:
            return "**"
        if inherited:
            return "*"

        return ""

    def print_tree(self, indent: str = "", inherited: bool = False):
        print(f"{indent}{self!s} {self.get_tree_note(inherited)}")
        if indent == "":
            print("*) inherited **) default")

    def print_meta_tree(self, indent: str = ""):
        self.meta.print_tree(indent)

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self):
        return f"{self.name}: {self.value!s}{'%' if self.meta.is_percent or getattr(self, 'percental', False) else ''}"

    def __call__(self) -> t.Any:
        return self.value

    def __getitem__(self, key: int | str) -> str | ListItem | Attribute[t.Any, t.Any] | Property | None:
        """Allows bracket notation access to elements."""
        if self._value_text is None:
            return None

        if isinstance(key, str):
            raise ValueError(
                f"Trying key access with {key} on attribute {self.meta.full_path if self.is_default else self.full_path}"
            )
        else:
            return self._value_text[key]


class PrimitiveAttribute(Attribute["MetaPropertyCache", bool | str | float | int], Variable):
    TYPE_MAP: t.ClassVar[t.Mapping[str | None, type[t.Any]]] = {
        "Bool": bool,
        "Boolean": bool,
        "Choice": str,
        "Float": float,
        "FloatOrPercental": float,
        "Int": int,
        "Int64": int,
        "Integer": int,
        "String": str,
        "UnsignedInt64": int,
    }

    def __init__(
        self,
        node: et._Element,
        parent: AttributeParentT,
        meta: ValueDefinition,
        data_type: str,
        is_variable: bool,
        cache: MetaPropertyCache,
    ):
        super().__init__(node, parent, meta, cache)

        self.is_variable = is_variable

        self.percental = False
        self.variable_name = None

        # UI text fields - populated on-demand via get_ui_text_mapping()
        self._ui_text_mapping = None
        self._ui_text_mapping_loaded = False

        if self._value_text is None:
            self.value = None
            return

        if self.is_variable:
            self.variable_name = self._value_text
            return

        if data_type == "FloatOrPercental":
            percental_node = node.find("Percental")
            if percental_node is not None and percental_node.text is not None:
                self.percental = parse_bool(percental_node.text)

            value_node = node.find("Value")
            try:
                if value_node is None:
                    self.value = None
                elif value_node.text is not None:
                    self.value = float(value_node.text)
                else:
                    self.value = float(self._value_text)
            except ValueError:
                raise ValueError(
                    f"Could not convert {self._value_text} to float in {self.meta.full_path if self.is_default else self.full_path}: {et.tostring(self.node, pretty_print=True).decode('utf-8')}"
                )

            return

        if data_type.startswith("Bool"):
            self.value = parse_bool(self._value_text)
            return

        if data_type in self.TYPE_MAP:
            try:
                self.value = self.TYPE_MAP[data_type](self._value_text)
            except ValueError:
                raise ValueError(
                    f"Could not convert {self._value_text} to {data_type} in {self.meta.full_path if self.is_default else self.full_path}."
                )
        else:
            raise ValueError(
                f"Unknown data type: {data_type} in {self.meta.full_path if self.is_default else self.full_path}."
            )

    def resolve_inheritance(self, default: t.Self | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        """Resolve inheritance, handling variable attributes specially."""
        # Check for invalid default override
        if self.meta.default == self and default is not None:
            raise ValueError(f"Trying to override default attribute {self.meta.full_path} with {default.full_path}")

        # If this is a variable, we have a variable name and shouldn't inherit concrete values
        if self.is_variable:
            return

        # If default is a variable and we don't have a value, inherit the variable
        if default is not None and self.value is None:
            self.is_variable = default.is_variable
            self.variable_name = default.variable_name
            self.value = default.value

    def get_ui_text_mapping(self):
        """Get UI text mapping for this attribute (lazy loading).

        Returns:
            UITextMapping if available, None otherwise
        """
        if self._ui_text_mapping_loaded:
            return self._ui_text_mapping

        self._ui_text_mapping_loaded = True

        # Only Choice attributes with datasets can have UI text
        if self.meta.data_type != "Choice" or self.meta.dataset is None or self.value is None:
            return None

        # Check if UI text cache is available
        if self.cache.ui_text_cache is None:
            return None

        with suppress(Exception):
            # Silently ignore UI text lookup failures
            self._ui_text_mapping = self.cache.ui_text_cache.get_ui_text(self.meta.dataset.name, str(self.value))

        return self._ui_text_mapping

    @property
    def ui_text_id(self) -> int | None:
        """Get the UI text ID for this attribute."""
        mapping = self.get_ui_text_mapping()
        return mapping.text_id if mapping else None

    @property
    def ui_text(self):
        """Get the UI Text object for this attribute.

        Returns:
            Text object with localized strings, or None if not available
        """
        mapping = self.get_ui_text_mapping()
        return mapping.text if mapping else None

    @property
    def ui_icon_guid(self):
        """Get the UI icon FileNameAttribute for this attribute.

        Returns:
            FileNameAttribute with icon path, or None if not available
        """
        mapping = self.get_ui_text_mapping()
        return mapping.icon if mapping else None

    @property
    def ui_text_variants(self) -> dict[str, int]:
        """Get UI text variants (context-specific text) for this attribute."""
        mapping = self.get_ui_text_mapping()
        return mapping.variants if mapping else {}

    @property
    def buff_ui(self):
        """Get BuffUI representation of this attribute.

        Returns:
            BuffUI object with icon, text, and formatted value, or None if not available
        """
        if self.name == "RadiusEffectRangeUpgrade":
            return None  # handeled in RadiusEffectRangeTarget

        if self.cache.ui_text_cache is None or self.value is None or self.value == 0:
            return None

        # Get property path for buff type mapping
        if not hasattr(self, "parent") or self.parent is None or not hasattr(self.parent, "name"):
            return None

        property_name = self.parent.name
        attr_name = self.name

        try:
            return self.cache.ui_text_cache.create_buff_ui(
                property_name=property_name, attr_name=attr_name, value=self.value
            )
        except Exception:
            return None


class ColorAttribute(Attribute["MetaPropertyCache", dict[str, int] | int]):
    """Represents a color attribute that can handle both single value and dictionary-like XML structures."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)

        if len(node) == 0:  # Single value case
            try:
                self.value = int(self._value_text) if self._value_text else None
            except ValueError:
                raise ValueError(
                    f"Could not convert {self._value_text} to int in {self.meta.full_path if self.is_default else self.full_path}."
                )
        else:  # Dictionary-like structure case
            self.value = {}
            for child in node.iterchildren():
                try:
                    if child.text is None or str(child.tag) == "ColorMode":
                        continue

                    self.value[str(child.tag)] = int(child.text)
                except ValueError:
                    print(f"XML for {node.tag}:\n{et.tostring(node, pretty_print=True).decode('utf-8')}")
                    raise ValueError(
                        f"Could not convert {child.text} to int in {self.meta.full_path if self.is_default else self.full_path}."
                    )

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        if isinstance(self.value, dict):
            return key in self.value
        return False

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        if isinstance(self.value, dict):
            return f"{self.name}: {self.value}"
        return f"{self.name}: {self.value}"


class TextAttribute(Attribute["MetaPropertyCache", Text]):
    """A localized text stored in texts_*.xml. Internal strings are stored as PrimitiveAttribute of data type string."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)
        if self._value_text:
            try:
                self.value = self.cache.texts.get(parse_text_id(self._value_text))
            except ValueError:
                logger.warning("Cannot parse text ID %r at %s", self._value_text, self.full_path)
                self.value = None
        else:
            self.value = None

    def __iter__(self) -> t.Iterator[str]:
        if self.value is None:
            return

        for text in self.value.values.values():
            yield text

    def __getitem__(self, key: int | str) -> str | None:
        """Allows bracket notation access to elements."""
        if self.value is None:
            return None

        if isinstance(key, str):
            if self.cache.texts.languages.get(key) is None:
                raise ValueError(
                    f"Unknown language {key} when accessing text attribute {self.meta.full_path if self.is_default else self.full_path}"
                )
            return self.value.values.get(key)
        else:
            raise ValueError(
                f"Trying index access with {key} on the time attribute {self.meta.full_path if self.is_default else self.full_path}"
            )

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        return key in self.cache.texts.languages

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        if self._value_text == "0":
            return f'{self.name}:""'
        if self.value is None:
            return f"{self.name}: Missing text with id {self._value_text}"
        return f"{self.name}: {self.value!s}"


class TimeAttribute(Attribute["MetaPropertyCache", datetime.timedelta]):
    """Represents a duration."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)
        self.value = datetime.timedelta(milliseconds=int(self._value_text)) if self._value_text else None


class UpgradeAttribute(Attribute["MetaPropertyCache", float]):
    """Consists of an amount (stored in value) and bool percental."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)
        value = node.find("Value")

        if value is None:
            self.value = 0
            self._value_text = None
        else:
            self._value_text = value.text
            try:
                self.value = float(value.text) if value.text else None
            except ValueError:
                raise ValueError(
                    f"Could not convert {value} to int in {self.meta.full_path if self.is_default else self.full_path}"
                )

        percental = node.find("Percental")
        if percental is not None:
            self.percental = parse_bool(percental.text)
        elif self.name.endswith("IsPercent"):
            self.percental = True
        else:
            self.percental = None

    def resolve_inheritance(self, default: t.Self | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        if self.meta.default == self and default is not None:
            raise ValueError(f"Trying to override default attribute {self.meta.full_path} with {default.full_path}")

        if default is None:
            return

        if self._value_text is None:  # value is initialized with 0
            self.value = default.value
        if self.percental is None:
            self.percental = default.percental

    @property
    def buff_ui(self):
        """Get BuffUI representation of this upgrade attribute.

        Returns:
            BuffUI object with icon, text, and formatted value, or None if not available
        """
        if not self.cache.ui_text_cache or self.value is None or self.value == 0:
            return None

        # Get property path for buff type mapping
        if not hasattr(self, "parent") or self.parent is None or not hasattr(self.parent, "name"):
            return None

        property_name = self.parent.name
        attr_name = self.name

        try:
            return self.cache.ui_text_cache.create_buff_ui(
                property_name=property_name, attr_name=attr_name, value=self.value, percental=self.percental
            )
        except Exception:
            return None


class FlagsAttribute(Attribute["MetaPropertyCache", list[str]]):
    """A (potentially empty) list of literals. See self.meta.dataset.literals for all literals."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)
        self.value = self._value_text.split(";") if self._value_text else []

    def __contains__(self, key: str | int) -> bool:
        """Allows the use of the 'in' keyword."""
        assert self.value is not None
        return key in self.value

    def __iter__(self) -> t.Iterator[str]:
        if self.value is None:
            return

        for flag in self.value:
            yield flag

    def __getitem__(self, key: int | str) -> str | ListItem | None:
        """Allows bracket notation access to elements."""
        if self.value is None:
            return None

        if isinstance(key, str):
            raise ValueError(
                f"Trying key access with {key} on list attribute {self.meta.full_path if self.is_default else self.full_path}"
            )
        else:
            if key >= len(self.value):
                raise IndexError(
                    f"Index {key} out of range for {self.meta.full_path if self.is_default else self.full_path}"
                )
            return self.value[key]

    @property
    def buff_ui(self) -> list[BuffUI] | None:
        """Get list of BuffUI representations for all list items.

        Returns:
            List of BuffUI objects for non-zero value items
        """
        if self.cache.ui_text_cache is None or self.value is None:
            return None

        # Get property path for buff type mapping
        if not hasattr(self, "parent") or self.parent is None or not hasattr(self.parent, "name"):
            return None

        property_name = self.parent.name
        attr_name = self.name

        return self.cache.ui_text_cache.create_buff_ui_flags(property_name, attr_name, self)


class FileNameAttribute(Attribute["MetaPropertyCache", Path]):
    """Stores a link to another file. The link is resolved to your local cache directory."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)

        if self._value_text is None:
            return

        self.value = self.cache.unpacked_path / Path(self._value_text)
        if self.is_image:
            self.value = self.value
            if not self.value.exists():
                self.value = self.value.with_suffix(".dds")
            if not self.value.exists() and not self.value.stem.endswith("_0"):
                self.value = self.value.with_stem(self.value.stem + "_0")
            if not self.value.exists():
                # Try alternative subfolders for UI images
                ui_index = None
                parts = list(self.value.parts)
                for i, part in enumerate(parts):
                    if part == "ui":
                        ui_index = i
                        break

                if ui_index is not None and ui_index + 1 < len(parts):
                    for subfolder in ["4k", "4kimages", "2kimages"]:
                        alt_parts = parts[:]
                        alt_parts[ui_index + 1] = subfolder
                        alt_path = Path(*alt_parts)
                        if alt_path.exists():
                            self.value = alt_path
                            break

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        assert self.value is not None
        return key in str(self.value)

    def __getitem__(self, key: int | str) -> str | None:
        raise ValueError(
            f"Trying index access with {key} on the filename attribute {self.meta.full_path if self.is_default else self.full_path}"
        )

    @property
    def identifier(self) -> str:
        if self._value_text is None:
            return ""

        return str(Path(self._value_text).as_posix())

    @property
    def is_image(self) -> bool:
        """Checks if the file is an image."""
        if self.value is None:
            return False

        return str(self.value).endswith((".png", ".jpg", ".jpeg", ".tga", ".bmp", ".gif", ".dds"))

    @property
    def canonical_name(self) -> str:
        """Generate a canonical, URL-safe name for this icon file.

        Format: icon_{template}_{asset_canonical_name}
        - template: First word of asset's template name (lowercase)
        - asset_canonical_name: The asset's canonical name

        Examples:
            - "icon_production_resin_tapper_latium"
            - "icon_item_dorian"
        """
        from assetextractor.parsing.core.assets import Asset

        # Find the parent asset by traversing up the parent chain
        current = self.parent
        while current is not None:
            if isinstance(current, Asset):
                # Get asset's canonical name (without template prefix)
                asset_canonical = current.canonical_name

                return asset_canonical if asset_canonical.startswith("icon") else f"icon_{asset_canonical}"
            if hasattr(current, "parent"):
                current = current.parent
            else:
                break

        # Fallback if no asset found
        return "icon_unknown"

    def get_image(self) -> WandImageProto | None:
        """Returns the image if the file is an image.

        Raises ImportError if Wand/ImageMagick is not installed.
        """
        if self.value is None or not self.is_image:
            return None

        WandImage = _load_wand_image()  # noqa: N806

        try:
            filename = self.value
            logger.debug(f"Loading image {filename}")

            if not filename.exists():
                logger.error(f"Image {filename} does not exist.")
                return None

            return WandImage(filename=str(filename))
        except Exception as e:
            logger.error(f"Could not load image {self.value}: {e}")
            return None

    def get_data_url(self, compression_quality: int | None = None, scaling: float = 0.25) -> str | None:
        """Returns the data URL of the image if the file is an image.

        Raises ImportError if Wand/ImageMagick is not installed.
        """
        if compression_quality is not None and not (compression_quality > 0 and compression_quality <= 100):
            raise ValueError(f"Invalid compression quality {compression_quality} (0-100)")

        WandImage = _load_wand_image()  # noqa: N806

        data = self.get_image()
        if data is None:
            return None

        try:
            with WandImage(data) as webp_img:
                width = webp_img.width
                height = webp_img.height
                webp_img.resize(int(width * scaling), int(height * scaling))
                webp_img.format = "webp"
                if compression_quality is not None:
                    webp_img.compression_quality = compression_quality
                buffer = BytesIO()
                webp_img.save(file=buffer)
                base64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
                return f"data:image/webp;base64,{base64_str}"
        except Exception as e:
            logger.error(f"Could not encode image {self.value}: {e}")
            return None


class ReferenceAttribute(Attribute["MetaPropertyCache", "Asset"], Variable):
    """Stores a reference to another asset. If the reference is invalid (i.e. the destination does not exist) the value is None."""

    IGNORED_VALUES = ("Human0", "Resident_tier01_atWork")

    def __init__(
        self,
        node: et._Element,
        parent: AttributeParentT,
        meta: ValueDefinition,
        is_variable: bool,
        cache: MetaPropertyCache,
    ):
        super().__init__(node, parent, meta, cache)

        self.is_variable = is_variable or self._value_text in self.IGNORED_VALUES

        if self.is_variable:
            self.variable_name = self._value_text
            self.guid = 0
            self.value = None
        else:
            self.variable_name = None
            if self._value_text is None:
                self.guid = 0
            else:
                # Game data may include labels like "Province Egyptian Aegyptus - 149679"
                text = self._value_text
                if not text.lstrip("-").isdigit() and " - " in text:
                    text = text.rsplit(" - ", 1)[-1]
                self.guid = int(text)
            self.value = None  # is set in constructor of AssetCache

    def set_reference(self, source: Asset, target: Asset | None):
        # ReferenceAttribute might be included in several assets
        self.value = target

        if self.value is None:
            logger.info(
                f"Invalid reference {self.guid} in {self.meta.full_path if self.is_default else self.full_path}"
            )
        else:
            self.value.set_referenced_by(source, self)

    @property
    def is_compound(self) -> bool:
        return True

    def resolve_inheritance(self, default: t.Self | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        """Resolve inheritance, handling variable attributes specially."""
        # If this is a variable, we have a variable name and shouldn't inherit concrete values
        if self.is_variable:
            return

        # If default is a variable and we don't have a guid, inherit the variable
        if default is not None and default.is_variable and self.guid == 0:
            self.is_variable = True
            self.variable_name = default.variable_name
            return

        # Normal reference inheritance
        if default is not None and self.guid == 0:
            self.value = default.value
            self.guid = default.guid

    def __iter__(self) -> t.Iterator[Property]:
        if self.value is None:
            return

        for property in self.value:
            yield property

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        if self.value is None:
            return False

        return key in self.value

    def __getitem__(self, key: int | str) -> Property | None:
        if self.value is None:
            raise ValueError(
                f"Cannot access invalid reference {self.meta.full_path if self.is_default else self.full_path}: {self!s}"
            )

        if isinstance(key, str):
            return self.value[key]
        else:
            raise ValueError(
                f"Trying index access with {key} on the reference attribute {self.meta.full_path if self.is_default else self.full_path}"
            )

    @property
    def buff_ui(self):
        """Get BuffUI representation for this reference attribute with formatted text.

        Returns:
            BuffUI object with icon and formatted text, or None if not applicable
        """
        from assetextractor.parsing.core.uitext import BuffUI

        if self.value is None or not self.name.endswith(
            "Fertility"
        ):  # matches both AddedAreaFertility or AddedFertility
            return None

        parent = getattr(self, "parent", None)

        # Get property path for buff type mapping
        if parent is None:
            return None

        try:
            percentage = parent.find_value("FertilityPercent")
            if percentage is None:
                percentage = parent.find_value("AreaFertilityPercent")

            if percentage is None:
                return None

            fertility_asset = self.value

            # Get text and icon from the Fertility asset
            text_obj = fertility_asset.text
            icon_obj = fertility_asset.icon

            # Format value - check if it's percental
            value_str = f"{percentage}%"  # no sign

            return BuffUI(icon=icon_obj, text=text_obj, value=value_str)

        except Exception:
            return None


class QuestAttribute(ReferenceAttribute):
    """References a quest asset and stores a boolean win_quest."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, is_variable=False, cache=cache)
        guid = node.get("Quest")
        self.guid = 0 if guid is None else int(guid)

        if win_quest := node.get("WinQuest"):
            self.win_quest = parse_bool(win_quest)
        else:
            self.win_quest = None


class ListItem(NamedElement[t.Any]):
    def __init__(self, index: int, node: et._Element, parent: ListAttribute | DictAttribute, cache: MetaPropertyCache):
        super().__init__(node, parent, cache, name=str(index))
        self.index: int = index
        self.parent: ListAttribute | DictAttribute = parent  # pyright: ignore[reportIncompatibleVariableOverride]
        self.cache: MetaPropertyCache = cache
        self.super_index: int | None = self.get_super_index(self.node)
        self.inherited: bool = self.super_index is not None
        self.value: dict[str, Attribute[t.Any, t.Any] | Property | None] = {}
        self._full_path: str | None = None
        self._property_path: str | None = None

        meta = parent.meta
        if meta and hasattr(meta, "items"):
            for value_definition in meta.items:
                name: str = value_definition.name
                child = node.find(name)

                if child is None:
                    attr = value_definition.default
                else:
                    attr = AttributeFactory.create(child, self, value_definition, cache)
                    if attr.is_compound and not self.inherited:
                        attr.resolve_inheritance(value_definition.default)

                self.value[name] = attr
                if name:
                    setattr(self, name, attr)

    def __call__(self) -> dict[str, Attribute[t.Any, t.Any] | Property | None]:
        return self.value

    @staticmethod
    def get_super_index(node: et._Element) -> int | None:
        subnode = node.find("VectorElement")
        if subnode is not None:
            subnode = subnode.find("InheritedIndex")

            if subnode is not None and subnode.text is not None:
                return int(subnode.text)

        return None

    def resolve_inheritance(self, default: ListItem):
        meta = self.parent.meta
        if meta and hasattr(meta, "items"):
            for value_definition in meta.items:
                name = value_definition.name
                attribute = self.value.get(name)
                default_attr = default.value.get(name)

                if default_attr is None:
                    continue

                if attribute is None or (isinstance(attribute, Attribute) and attribute.is_default):
                    setattr(self, name, default_attr)
                    self.value[name] = default_attr
                elif isinstance(attribute, Attribute) and isinstance(default_attr, Attribute):  # noqa: SIM114
                    attribute.resolve_inheritance(default_attr)
                elif isinstance(attribute, Property) and isinstance(default_attr, Property):
                    attribute.resolve_inheritance(default_attr)

    @property
    def full_path(self) -> str:
        if self._full_path is None:
            self._full_path = f"{self.parent.full_path}[{self.index}]"
        return self._full_path

    @property
    def property_path(self) -> str:
        if self._property_path is None:
            self._property_path = f"{self.parent.property_path}[{self.index}]"
        return self._property_path

    def get(self, name: str) -> NamedElement[t.Any] | None:
        """Returns the element with the given name or None if it does not exist."""
        if hasattr(self, "__getitem__"):
            try:
                return self[name]
            except (KeyError, IndexError, TypeError):
                return None
        return None

    def find(self, path: str) -> NamedElement[t.Any] | ListItem | None:
        """Parses dot seperated list of names to find the element.

        Returns None if the path is not found.
        """
        parts = path.split(".")
        elem = self
        i = 0
        while i < len(parts) and (elem := elem.get(parts[i])):
            i += 1

        return elem if i == len(parts) else None

    def find_ref(self, path: str) -> Asset | None:
        """Follow path and return the referenced Asset, or None if missing or unresolved."""
        return t.cast("Asset | None", self.find_value(path))

    @property
    def ui_text(self) -> str | None:
        """Get formatted UI text for this list item with placeholders filled.

        Deprecated: Use buff_ui property instead.

        Returns:
            Formatted text string, or None if not applicable
        """
        buff_ui_obj = self.buff_ui
        if buff_ui_obj and buff_ui_obj.text:
            if isinstance(buff_ui_obj.text, str):
                return buff_ui_obj.text
            return str(buff_ui_obj.text)
        return None

    @property
    def buff_ui(self):
        """Get BuffUI representation for this list item with formatted text.

        Returns:
            BuffUI object with icon and formatted text, or None if not applicable
        """
        from assetextractor.parsing.core.uitext import BuffUI

        try:
            # Get the UI text cache from the asset cache
            ui_text_cache = self.cache.ui_text_cache

            if ui_text_cache is None:
                logger.debug(f"ui_text_cache not found on cache for {self.full_path}")
                return None

            # Determine buff type from parent path
            parent_path = self.parent.property_path if hasattr(self.parent, "property_path") else ""

            logger.debug(f"ListItem.buff_ui - parent_path: {parent_path}")

            # Extract the property name from path
            if "." not in parent_path:
                return None

            path_parts = parent_path.split(".")
            if len(path_parts) < 2:
                return None

            property_name = path_parts[-2]  # e.g., "FactoryUpgrade"
            attr_name = path_parts[-1]  # e.g., "AdditionalOutput"

            # Get buff type name
            buff_type = ui_text_cache.get_buff_type_name(property_name, attr_name)
            if not buff_type or buff_type not in ui_text_cache.buff_text_structs:
                return None

            buff_info = ui_text_cache.buff_text_structs[buff_type]
            buff_struct = buff_info["struct"]

            # Get icon from buff struct (if available)
            icon_obj = None
            try:
                # Special handling for BuffResidenceProvidedNeedText - get icon from ProvidedNeed asset
                if buff_type == "BuffResidenceProvidedNeedText":
                    need_asset = self.find_ref("ProvidedNeed")

                    if need_asset:
                        # Get icon from Need asset's Standard.IconFilename
                        icon_obj = need_asset.icon

                # Special handling for BuffOutputWorkforce - get icon from WorkforceGUID asset
                elif buff_type == "BuffOutputWorkforce":
                    workforce_asset = self.find_ref("WorkforceGUID")
                    if workforce_asset:
                        # Get icon from Workforce asset's Standard.IconFilename
                        icon_obj = workforce_asset.icon

                # Default: try to find Icon in buff struct
                elif hasattr(buff_struct, "find") and not isinstance(buff_struct, TextAttribute):
                    icon_attr = buff_struct.find("Icon")
                    icon_obj = ui_text_cache._get_icon(icon_attr)
            except Exception:
                # Icon lookup failed, continue without icon
                pass

            # Special handling for AdditionalOutput - use _format_additional_factory_output directly
            if attr_name == "AdditionalOutput" and buff_type == "BuffAdditionalFactoryOutput":
                formatted_text = ui_text_cache._format_additional_factory_output(self, buff_info)
            else:
                # Fall back to generic format_buff_text
                formatted_text = ui_text_cache.format_buff_text(buff_type, self)

            if formatted_text:
                return BuffUI(
                    icon=icon_obj,
                    text=formatted_text,
                    value="",  # Value is embedded in formatted text
                )

            return None
        except Exception as e:
            logger.debug(f"Error in ListItem.buff_ui: {e}")
            return None

    def get_tree_note(self, inherited: bool = False) -> str:
        """Returns a note for the tree representation."""
        if self.inherited:
            return "*"

        return ""

    def print_tree(self, indent: str = "", inherited: bool = False):
        print(f"{indent}{self!s} {self.get_tree_note(inherited)}:")
        for attribute in self.value.values():
            if attribute is not None:
                attribute.print_tree(indent + "\t")
        if indent == "":
            print("*) inherited **) default")

    def print_meta_tree(self):
        self.parent.print_meta_tree()

    @property
    def is_compound(self) -> bool:
        return True

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        return key in self.value

    def __iter__(self) -> t.Iterator[Attribute[t.Any, t.Any] | Property]:
        for attribute in self.value.values():
            if attribute is not None:
                yield attribute

    def __getitem__(self, key: int | str) -> Attribute[t.Any, t.Any] | Property | None:
        if isinstance(key, str):
            return self.value.get(key)
        else:
            raise ValueError(f"Trying index access with {key} on the reference attribute {self.full_path}")

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"Item ({self.index})"


class ListAttribute(Attribute["MetaPropertyCache", list[ListItem]]):
    """Represents a list. Supports for-each iteration, index access, and checking containment - like regular Python lists. Modifying methods like concatention are not supported."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)

        self.value = []
        self.inherits = False

        for item_node in node.iterchildren():
            if item_node.tag != "Item":
                raise ValueError(
                    f"Invalid list item tag: {item_node.tag} in {self.meta.full_path if self.is_default else self.full_path}"
                )

            item = ListItem(len(self.value), item_node, self, cache)
            if item.super_index is not None:
                self.inherits = True

            self.value.append(item)

        self._value_list = self.value

    def resolve_inheritance(self, default: t.Self | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        if not self.inherits or default is None:
            return

        assert self.value is not None

        for item in self.value:
            if item.super_index is not None:
                assert default is not None and default.value is not None

                super_item = None
                if len(default.value) == 0:
                    if isinstance(self.meta.default, ListAttribute):
                        default = self.meta.default  # type: ignore
                    if len(default.value) == 0 and item.super_index == 0:  # type: ignore
                        # Vectors in template that inherit items from DefaultContainerValues
                        super_item = ListItem(
                            0, AttributeFactory.create_default_node("Item", "Vector"), self, self.cache
                        )

                assert default is not None and default.value is not None

                if super_item is None:
                    try:
                        super_item = default.value[item.super_index]
                    except Exception:
                        raise ValueError(
                            f"Invalid inheritance index {item.super_index} for {self.meta.full_path if self.is_default else self.full_path}: {default.meta.full_path if default.is_default else default.full_path}",
                            default,
                        )

                logger.debug(f"[{item.index}] from {super_item.full_path}")
                item.resolve_inheritance(super_item)

    @property
    def is_compound(self) -> bool:
        return True

    def print_tree(self, indent: str = "", inherited: bool = False):
        assert self.value is not None
        print(f"{indent}{self!s} ({len(self.value)} items) {self.get_tree_note(inherited)}:")

        for item in self.value:
            item.print_tree(indent + "\t", item.parent != self)

        if indent == "":
            print("*) inherited **) default")

    def __iter__(self) -> t.Iterator[ListItem]:
        assert self.value is not None
        for attribute in self.value:
            yield attribute

    def __len__(self) -> int:
        """Returns the number of items in the list."""
        assert self.value is not None
        return len(self.value)

    def __getitem__(self, key: int | str) -> str | ListItem | None:
        """Allows bracket notation access to elements."""
        if self.value is None:
            return None

        if isinstance(key, str):
            raise ValueError(
                f"Trying key access with {key} on list attribute {self.meta.full_path if self.is_default else self.full_path}"
            )
        else:
            if key >= len(self.value):
                raise IndexError(
                    f"Index {key} out of range for {self.meta.full_path if self.is_default else self.full_path}"
                )
            return self.value[key]

    @property
    def buff_ui(self):
        """Get list of BuffUI representations for all list items.

        Returns:
            List of BuffUI objects for non-zero value items
        """
        result: list[BuffUI] = []

        if self.cache.ui_text_cache is None or self.value is None:
            return result

        # Get property path for buff type mapping
        if not hasattr(self, "parent") or self.parent is None or not hasattr(self.parent, "name"):
            return result

        property_name = self.parent.name
        attr_name = self.name

        # Use the centralized create_buff_ui_list method
        buff_ui_list = self.cache.ui_text_cache.create_buff_ui_list(
            property_name=property_name, attr_name=attr_name, list_attr=self
        )

        return buff_ui_list if buff_ui_list else result

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"{self.name}"


class GenericDictAttribute[ValueT: Property | Attribute[t.Any, t.Any]](
    Attribute["MetaPropertyCache", dict[str, ValueT]]
):
    """Parent class for DictAttribute and TemplateAttribute. Provides methods for for-each iteration, key access, and checking containment."""

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        """Ignore_dataset is used to create child dictionries for each literal of the dataset."""
        super().__init__(node, parent, meta, cache)

        self.value = {}
        self._value_list: list[ValueT] = []
        self.attributes: dict[str, ValueT] = {}
        self.inherits = False

        self.unprocessed_properties = set(child for child in node.iterchildren() if isinstance(child.tag, str))

    def _add_attribute(self, name: str, attribute: ValueT):
        self.unprocessed_properties.discard(attribute.node)  # node is not in all_properties if it is a default node

        if name in self.attributes:
            for idx, child in enumerate(self._value_list):
                if child.name == name:
                    self._value_list[idx] = attribute
                    break

        else:
            self._value_list.append(attribute)

        self.attributes[name] = attribute
        assert self.value is not None
        self.value[name] = attribute

        setattr(self, name, attribute)

    def print_tree(self, indent: str = "", inherited: bool = False):
        print(f"{indent}{self!s} {self.get_tree_note(inherited)}:")

        for item in self._value_list:
            item.print_tree(indent + "\t", item.parent != self)

        if indent == "":
            print("*) inherited **) default")

    @property
    def is_compound(self) -> bool:
        return True

    def __contains__(self, key: str) -> bool:
        """Allows the use of the 'in' keyword."""
        return key in self.attributes

    def __iter__(self) -> t.Iterator[ValueT]:
        for attribute in self._value_list:
            yield attribute

    def __len__(self) -> int:
        """Returns the number of attributes in the dictionary."""
        return len(self._value_list)

    def __getitem__(self, key: int | str) -> str | ValueT | None:
        """Allows bracket notation access to elements."""
        if self.value is None:
            return None

        if isinstance(key, str):
            return self.value.get(key)
        else:
            if key >= len(self.value):
                raise IndexError(
                    f"Index {key} out of range for {self.meta.full_path if self.is_default else self.full_path}"
                )
            return self._value_list[key]

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"{self.name}"


class DictAttribute(GenericDictAttribute[Attribute[t.Any, t.Any]]):
    """Union for the attributes Array, Struct, and Property."""

    def __init__(
        self,
        node: et._Element,
        parent: AttributeParentT,
        meta: ValueDefinition,
        cache: MetaPropertyCache,
        ignore_dataset: bool = False,
    ):
        """Ignore_dataset is used to create child dictionries for each literal of the dataset."""
        super().__init__(node, parent, meta, cache)

        if meta.dataset is not None and not ignore_dataset:
            # Create a dictionary for each literal in the dataset
            for key in meta.dataset.literals:
                child = node.find(key)
                if child is None:
                    child = AttributeFactory.create_default_node(key, meta.data_type)

                self._add_attribute(key, DictAttribute(child, self, self.meta, self.cache, ignore_dataset=True))

        else:
            for value_definition in meta.items:
                name = value_definition.name
                child = node.find(name)
                self._add_attribute(name, AttributeFactory.create(child, self, value_definition, cache))

        for child in self.unprocessed_properties:
            logger.info(
                f"Ignoring property {child.tag} without meta definition in dictionary {self.meta.full_path if self.is_default else self.full_path}"
            )

    def resolve_inheritance(self, default: t.Self | None, ignore_dataset: bool = False):  # pyright: ignore[reportIncompatibleMethodOverride]
        if default is None:
            return

        if self.inherits:
            for item in self._value_list:
                super_index = ListItem.get_super_index(item.node)
                if super_index is not None:
                    try:
                        assert default.value is not None
                        super_item = default._value_list[super_index]
                    except Exception:
                        raise ValueError(
                            f"Invalid inheritance index {super_index} for {self.meta.full_path if self.is_default else self.full_path}"
                        )

                    if super_item.name != item.name:
                        raise ValueError(
                            f"Inherited index resolved to incorrect item: {self.meta.full_path if self.is_default else self.full_path} with index {super_index} resolved to {super_item.full_path}"
                        )

                    logger.debug(f"{item.name} from {super_item.full_path}")
                    item.resolve_inheritance(super_item)

        elif self.meta.dataset is not None and not ignore_dataset:
            for child in self.attributes.values():
                default_attr = default.attributes.get(child.name)
                if not isinstance(default_attr, DictAttribute) or not isinstance(child, DictAttribute):
                    raise ValueError(
                        f"Missing attribute {child.name} of dataset {self.meta.dataset.name} in {default.full_path} (found when updating inheritance in {self.full_path})"
                    )
                child.resolve_inheritance(default_attr, ignore_dataset=True)
        else:
            for value_definition in self.meta.items:
                name = value_definition.name
                default_attr = default.attributes.get(name)
                if default_attr is None:
                    raise ValueError(
                        f"Missing attribute {name} of type {value_definition.data_type} in {default.full_path} (found when updating inheritance in {self.full_path})"
                    )

                if (attr := self.attributes.get(name)) is None:
                    logger.debug(f"Copy {name} from {default_attr.full_path}")
                    self._add_attribute(name, default_attr)
                else:
                    if attr.is_default:
                        logger.debug(f"Copy {attr.name} from default {default_attr.full_path}")
                        self._add_attribute(name, default_attr)
                    else:
                        logger.debug(f"{attr.name} from {default.full_path}")
                        attr.resolve_inheritance(default_attr)

    @property
    def buff_ui(self):
        """Get list of BuffUI representations for dict entries with non-zero values.

        Returns:
            List of BuffUI objects for non-zero value entries, using literals as keys
        """
        return self.get_buff_ui()

    def get_buff_ui(self, in_additional_effect: bool = False):
        result: list[BuffUI] = []

        if self.cache.ui_text_cache is None or self.value is None:
            return result

        # Get property path for buff type mapping
        if not hasattr(self, "parent") or self.parent is None or not hasattr(self.parent, "name"):
            return result

        property_name = self.parent.name
        attr_name = self.name

        # Use the centralized create_buff_ui_dict method
        return self.cache.ui_text_cache.create_buff_ui_dict(
            property_name=property_name, attr_name=attr_name, dict_attr=self, in_additional_effect=in_additional_effect
        )


class TemplateAttribute(GenericDictAttribute["Property"]):
    """Represents an AutoCreateAsset attribute. For those, their building blocks are not defined in meta properties but in templates where they indicate from which template their properties are taken. The instances of the same meta attribute might reference different templates."""

    TEMPLATE_CACHE: TemplateCache | None = None

    def __init__(self, node: et._Element, parent: AttributeParentT, meta: ValueDefinition, cache: MetaPropertyCache):
        super().__init__(node, parent, meta, cache)
        self.template_node = node.find("Template")
        self.value_node = node.find("Values")
        self.template_name: str | None = None
        self.template: Template | None = None
        self.inherits = False
        self._is_initialized = False

        # Both Template and IsBaseAutoCreateAsset can be set, see "DefaultDeliveryExecutionPlace" (ConiditionQuestObjective) in properties-meta.xml
        if self.template_node is not None:
            # Template and Values can be inherited
            self.template_name = str(self.template_node.text)
            return

        if self.get_value("IsBaseAutoCreateAsset", bool):
            self.inherits = True

            if not isinstance(self.meta.default, TemplateAttribute):
                raise ValueError(
                    f"AutoCreateAsset {self.full_path} [{self.source}] does not specify a default template."
                )

            return

        if isinstance(self.parent, ListItem):
            return  # Handle special case for Anno 1800 in assets.xml line 920279 where where SubCondition specifies neither IsBaseAutoCreateAsset nor Template

        if hasattr(self.meta, "default"):  # we are not creating the default attribute right now
            raise ValueError(
                f"AutoCreateAsset {self.full_path} [{self.source}] specifies neither IsBaseAutoCreateAsset nor Template."
            )

    def derive_template_name(self):
        if self.template_name is not None:
            return

        if self.TEMPLATE_CACHE is None:
            return

        template_names = [template.name for template in self.meta.allowed_templates]
        if len(template_names) == 1:
            self.template_name = template_names[0]
            return

        if self.value_node is None:
            return

        for child in self.value_node.iterchildren():
            name = str(child.tag)

            if name in template_names:
                self.template_name = name
                break

    def resolve_inheritance(self, default: t.Self | None):  # pyright: ignore[reportIncompatibleMethodOverride]
        if self._is_initialized:
            return

        if self.is_default and self.template_name is None:
            self._is_initialized = True
            return

        if default is not None and self.template_name is None:
            if default.is_default and isinstance(self.meta.default, TemplateAttribute):
                default = t.cast("t.Self", self.meta.default)
                # use updated default (from container values) instead of the default created one by upstream property

            self.template_node = default.template_node
            self.template_name = default.template_name

        # Cases to consider:
        # default is None
        # initializing MetaProperty -> default is None
        # initializing Template -> TemplateCache is None
        # initializing base Asset -> self.template (root is the base Asset) can reference different default.template (root is the Template of base Asset)
        # intializing inheriting Asset

        # Case 1: We are initializing properties and templates
        # Do nothing here, TemplateCach will call self.set_template after initialization
        if self.TEMPLATE_CACHE is None:
            return

        if self.template_name is None and default is not None and not default._is_initialized:
            print(f"self.full_path: {self.full_path}")
            print(f"self.is_default: {self.is_default}")
            print(f"self.template_name: {self.template_name}")
            print(f"default.full_path: {default.full_path}")
            print(f"default.is_default: {default.is_default}")
            print(f"default.template_name: {default.template_name}")
            print(f"default._is_initialized: {default._is_initialized}")
            raise ValueError(
                f"Passing non-initialized default to AutoCreatAsset: {self.full_path} [{self.source}]\t{default.full_path} [{default.source}]"
            )

        if self.template_name is None and default is not None and default.template_name is None:
            self.derive_template_name()

        if self.template_name is None:
            default_info = f"{default.full_path} [{default.source}]" if default is not None else "No default"
            raise ValueError(
                f"Could not derive template name for AutoCreatAsset: {self.full_path} [{self.source}]\t{default_info}"
            )

        template: Template | TemplateAttribute | None = None
        if default is not None and self.inherits and default.template and default.template.name == self.template_name:
            template = default
            self.template = default.template

        if template is None and self.template_name:
            template = self.TEMPLATE_CACHE.get(self.template_name)
            self.template = template

        if template is None:
            if self.name.startswith("Test"):
                return
            raise ValueError(
                f"Template {self.template_name} not found for AutoCreateAsset {self.full_path} [{self.source}]"
            )

        # value node is None if we initialize the default attribute from a template derived from allowed templates
        unprocessed_properties = (
            set[str](child.tag for child in self.value_node.iterchildren() if isinstance(child.tag, str))
            if self.value_node is not None
            else set[str]()
        )

        for template_property in template:
            name = template_property.name

            child = self.value_node.find(name) if self.value_node is not None else None

            if child is None or len(child) == 0:
                property = Property(template_property.node, self, template_property.meta, self.cache)
            else:
                property = Property(child, self, template_property.meta, self.cache)

            unprocessed_properties.discard(name)
            property.resolve_inheritance(template_property)
            self._add_attribute(name, property)

        self._is_initialized = True

        if len(unprocessed_properties) > 0:
            logger.warning(
                f"Template Attribute {self.full_path} [{self.source}] specifies {unprocessed_properties} which is not in Template {self.template_name}."
            )

    def set_reference(self, root: Asset | None = None):
        """Sets the template for the AutoCreateAsset."""
        if self.template is None or root is None:
            return

        self.template.instances[root.guid] = WeightedReference(root, self.template, self.property_path)


class AttributeFactory:
    IGNORED_TYPES = ("AssetGroup", "Matrix", "QuestGroup", "TextGroup", "ScriptIdGroup", "UiText")

    @staticmethod
    def create_default_node(name: str, data_type: str, default_value: str | None = None) -> et._Element:
        """Creates an XML tree with a single node containing the given name and a default value."""
        root = et.Element(name)

        if data_type == "Choice" and default_value is not None:
            root.text = str(default_value)
        if data_type == "String":
            root.text = ""
        elif data_type in PrimitiveAttribute.TYPE_MAP or data_type in "Time":
            root.text = "0"
            child = et.Element("Value")
            child.text = "0"
            root.append(child)
        elif data_type == "AutoCreateAsset":
            pass

        return root

    @staticmethod
    def create(
        node: et._Element | None, parent: AttributeParentT, value_definition: ValueDefinition, cache: MetaPropertyCache
    ) -> Attribute[t.Any, t.Any]:
        if node is None:
            return value_definition.default

        dt = value_definition.data_type
        is_variable = False
        if dt in AttributeFactory.IGNORED_TYPES:
            return Attribute(node, parent, value_definition, cache)

        if dt == "Variable":
            dt = value_definition.variable_type or "String"

            if dt in AttributeFactory.IGNORED_TYPES:
                return Attribute(node, parent, value_definition, cache)

            variable_attr = node.find("IsVariable")
            is_variable = variable_attr is not None and parse_bool(variable_attr.text)

            value = node.find("Value")
            if value is not None:
                node = value

        if (
            dt == "String" or value_definition.is_primitive
        ):  # contains internla strings, for localized strings see TextAttribute
            return PrimitiveAttribute(node, parent, value_definition, dt, is_variable, cache)

        if dt == "Asset" and value_definition.name == "Text":
            # Handle KeyBindings where text is marked as Asset
            return TextAttribute(node, parent, value_definition, cache)

        match dt:
            case "Color":
                return ColorAttribute(node, parent, value_definition, cache)
            case "Time":
                return TimeAttribute(node, parent, value_definition, cache)
            case "Upgrade":
                return UpgradeAttribute(node, parent, value_definition, cache)
            case "Flags":
                return FlagsAttribute(node, parent, value_definition, cache)
            case "Text" | "ScriptId":  # ScriptId references both: a voice recording and a subtitle text
                return TextAttribute(node, parent, value_definition, cache)
            case "Asset":
                return ReferenceAttribute(node, parent, value_definition, is_variable, cache)
            case "Quest":
                return QuestAttribute(node, parent, value_definition, cache)
            case "FileName":
                return FileNameAttribute(node, parent, value_definition, cache)
            case "Property" | "Struct" | "Array":
                return DictAttribute(node, parent, value_definition, cache)
            case "Vector":
                return ListAttribute(node, parent, value_definition, cache)
            case "AutoCreateAsset":
                return TemplateAttribute(node, parent, value_definition, cache)
            case _:
                raise ValueError(f"Unprocessed data type: {dt} in {value_definition.full_path}.")
