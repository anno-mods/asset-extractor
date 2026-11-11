"""These are merely used for intellisense or easier conversion to JSON schemas."""

from enum import StrEnum


class BuildingType(StrEnum):
    """Define the dataset 'BuildingType' that must contain 8 values."""

    FACTORY = "Factory"
    RESIDENCE = "Residence"
    OTHER = "Other"
    MINE = "Mine"
    LOGISTIC = "Logistic"
    PUBLIC = "Public"
    BUILDING_MODULE = "BuildingModule"
    WAREHOUSE = "Warehouse"


class Region(StrEnum):
    """Define the dataset 'Region' that must contain 4 values."""

    META = "Meta"
    ROMAN = "Roman"
    CELTIC = "Celtic"
    EGYPTIAN = "Egyptian"


class IslandType(StrEnum):
    """Define the dataset 'IslandType' that must contain 8 values."""

    NORMAL = "Normal"
    STARTER = "Starter"
    DECORATION = "Decoration"
    THIRD_PARTY = "ThirdParty"
    PIRATE_ISLAND = "PirateIsland"
    CLIFF_ISLAND = "CliffIsland"
    RESERVED_FOR_PLAYER = "ReservedForPlayer"
    VOLCANIC_ISLAND = "VolcanicIsland"


class IslandSize(StrEnum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    XL = "XL"
    CONTINENTAL = "Continental"


class IslandGameType(StrEnum):
    SANDBOX_SINGLEPLAYER = "SandboxSingleplayer"
    SANDBOX_MULTIPLAYER = "SandboxMultilayer"
    CAMPAIGN_MODE = "CampaignMode"


class IslandDifficulty(StrEnum):
    NORMAL = "Normal"
    HARD = "Hard"


class ResourceAmount(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class ScopeVisualization(StrEnum):
    """Define the dataset 'ScopeVisualization' that must contain 12 values."""

    LOCAL = "Local"
    MODULE_OWNER = "ModuleOwner"
    STREET_DISTANCE = "StreetDistance"
    RADIUS = "Radius"
    OBJECTS_IN_AREA = "ObjectsInArea"
    AREA = "Area"
    OBJECTS_IN_SESSION = "ObjectsInSession"
    SESSION = "Session"
    OBJECTS_IN_META = "ObjectsInMeta"
    META = "Meta"
    AREAS_IN_META = "AreasInMeta"
    AREAS_IN_SESSION = "AreasInSession"


class BuffCategory(StrEnum):
    """
    Define the dataset 'BuffCategory' that must contain 15 values. This comes
    from 'BuffConfig' asset.
    """

    ADJACENCY = "Adjacency"
    AQUEDUCT = "Aqueduct"
    ASSEMBLY = "Assembly"
    DIPLOMACY = "Diplomacy"
    INCIDENT = "Incident"
    MAJOR_INCIDENT = "MajorIncident"
    INSTITUTION = "Institution"
    ITEM = "Item"
    RELIGION = "Religion"
    TECH = "Tech"

    # TODO: Complete this. I am lazy atm and just needed the "Item".


class ItemAllocation(StrEnum):
    """
    Define the dataset 'ItemAllocation' that must contain 3 values. This comes
    from 'ItemBalancing' asset.
    """

    NONE = "None"
    SHIP = "Ship"
    VILLA = "Villa"


class RarityVisualization(StrEnum):
    """
    Define the dataset 'RarityVisualization' that must contain 8 values. This comes
    from 'ItemBalancing' asset.
    """

    NARRATIVE = "Narrative"
    COMMON = "Common"
    UNCOMMON = "Uncommon"
    RARE = "Rare"
    EPIC = "Epic"
    LEGENDARY = "Legendary"
    QUEST = "Quest"
    UNIQUE = "Unique"


class NicheVisualization(StrEnum):
    """
    Define the dataset 'NicheVisualization' that must contain 10 values. This comes
    from 'ItemBalancing' asset.
    """

    NONE = "None"
    FINANCE = "Finance"
    RELIGION = "Religion"
    RESEARCH = "Research"
    CULTURE = "Culture"
    ECONOMY = "Economy"
    AGRICULTURE = "Agriculture"
    DIPLOMACY = "Diplomacy"
    MILITARY = "Military"
    NAUTICS = "Nautics"


class ItemOrigin(StrEnum):
    """
    Define the dataset 'ItemOrigin' that must contain 5 values. This comes
    from '?' asset.
    """

    TESTING = "Testing"
    BASE_RELEASE = "BaseRelease"  # Vanilla
    PREORDER = "PreOrder"  # Mostly for ornaments and logos.
    TWITCH_DROP = "TwitchDrop"  # Mostly ornaments and logos.
    DLC_POA = "DLC01"  # Prophecies of Ashes
    DLC_HIPO = "DLC02"  # Assuming this is gonna be for Hippodrome.
    DLC_EGYPT = "DLC03"  # Assuming this is gonna be for Dawn of the Delta.


class SlotType(StrEnum):
    """
    Define the dataset 'SlotType' that must contain 7 values. This comes
    from '?' asset.
    """

    NONE = "None"
    COAST = "Coast"
    RIVER = "River"
    CLAIMING = "ClaimingBuilding"
    MOUNTAIN = "Mountain"
    WORKAREA = "WorkArea"
    MARSH = "Marsh"


class UplayProductType(StrEnum):
    """
    Define the dataset 'UplayProductType' that must contain 6 values. This comes
    from '?' asset.
    """

    SEASON_PASS = "SeasonPass"
    DLC = "DLC"
    COSMETIC_DLC = "CosmeticDLC"
    PREORDER_BONUS = "PreOrderBonus"
    TWITCH_DROP = "TwitchDrop"
    LANGUAGE_PACK = "LanguagePack"


class AchievementDifficultyType(StrEnum):
    """
    Dataset 'AchievementDifficulty' (Id 252), backed by the 'Choice' property
    'Achievement.AchievementDifficulty' (schema default: Bronze). Verified against
    real 'Achievement' assets in assets.xml (e.g. GUID 80528 = Silver, 80536 = Gold).
    """

    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"
