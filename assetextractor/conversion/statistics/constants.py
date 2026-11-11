"""Constants used across the statistics extraction module."""

# Maximum contract score for probability calculation
# Source: Participant 3rdParty.ContractProvider.DestroyContractBalancing[16].MaxAmount
MAX_CONTRACT_SCORE = 3600

# Text IDs for source type labels (localized text)
SOURCE_TEXT_IDS = {
    "quest": -6905698394117185352,  # "Quest"
    "selling": -6902222124635972240,  # "Selling"
    "contracts": -6914021190765224130,  # "Contracts"
    "research": -6902138578600598283,  # "Research"
    "drops": -6917297453044695070,  # "Flotsam" (repurposed for Drops)
    "festival": -6908773579491322283,  # "Festival"
    "hall_of_fame": -6906945524005841361,  # "Hall of Fame"
    "subjugated": -6908107531205007038,  # "Subjugated Into Specialist"
    "trade_routes": -6915569607474692589,  # "Trade Routes"
    "no_patron": -6910831837642126966,  # "No patron god selected on this island"
    "colosseum": -6904343816604170694,  # "Colosseum" (monument event)
    "in_storage": -6915287623296488680,  # "In Storage"
}

# Comparison operators for boost conditions
COMPARISON_OPERATORS = {0: ">=", "AtLeast": ">=", "AtMost": "<=", "LessThan": "<", "MoreThan": ">", "Equals": "="}
