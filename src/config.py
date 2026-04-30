from datetime import date

# GDELT GKG themes relevant to ASGM
THEMES = {
    "primary": "WB_555_ARTISANAL_AND_SMALL_SCALE_MINING",
    "broader": [
        "ENV_MINING",
        "WB_1699_METAL_ORE_MINING",
        "WB_2936_GOLD",
        "WB_2898_EXTRACTIVE_INDUSTRIES",
    ],
}

# Keyword queries for articles the theme tagger may miss.
# Quoted phrases use GDELT full-text search.
KEYWORD_QUERIES = [
    '"artisanal mining"',
    '"small-scale mining"',
    '"small-scale gold"',
    "ASGM",
    "galamsey",       # Ghana
    "garimpeiro",     # Brazil
    "orpaillage",     # Francophone Africa
]

# Full DOC API timeline window: 2017-01-01 to present
DATE_RANGE = {
    "start": "2017-01-01",
    "end": date.today().strftime("%Y-%m-%d"),
}

# FIPS 2-letter country codes for ASGM-significant countries
ASGM_COUNTRIES = [
    "GH",  # Ghana
    "CO",  # Colombia
    "PE",  # Peru
    "PH",  # Philippines
    "ID",  # Indonesia
    "TZ",  # Tanzania
    "KE",  # Kenya
    "BF",  # Burkina Faso
    "ML",  # Mali
    "GY",  # Guyana
    "SR",  # Suriname
    "MN",  # Mongolia
    "BO",  # Bolivia
    "EC",  # Ecuador
    "BR",  # Brazil
]

# Local directory for cached query results
CACHE_DIR = "data"

# Seconds to sleep between API requests to respect rate limits
REQUEST_DELAY = 6

# Themes to compare against WB_555 for annual context.
# Each entry: theme_id -> display label.
COMPARISON_THEMES = {
    "WB_1699_METAL_ORE_MINING":     "Large-scale metal ore mining",
    "WB_2936_GOLD":                  "Gold sector broadly",
    "WB_2898_EXTRACTIVE_INDUSTRIES": "All extractive industries",
    "ENV_DEFORESTATION":             "Deforestation",
}

# Key events to annotate the timeline (date -> label)
KEY_EVENTS = {
    "2017-08-16": "Minamata Convention enters into force",
    "2019-09-01": "planetGOLD programme launches",
    "2021-03-01": "Ghana galamsey crackdown intensifies",
    "2023-10-01": "Minamata COP-5",
}
