"""Central constants: API paths, enums, and lookup maps for etmoney.com."""

BASE_URL = "https://www.etmoney.com"

LISTING_API = "/api/mffeed/mutual-funds/get-all-regular-funds-listing"
SEARCH_API = "/api/mffeed/mutual-funds/mf-search/"
FUND_URL = "/mutual-funds/{slug}/{scheme_id}"
COMPARE_URL = "/mutual-funds/compare"
FEATURED_URL = "/mutual-funds/featured/{slug}/{id}"
STOCK_SCREEN_URL = "/stocks/market-data/{slug}/{id}"
INDEX_URL = "/stocks/index/{slug}/{id}"
SECTOR_URL = "/stocks/sector/{slug}/{id}"
STOCK_DETAIL_URL = "/stocks/{slug}/{stock_id}"
AMC_FUNDS_URL = "/mutual-funds/fund-houses/{slug}"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Investment modes accepted by the listing API
INVESTMENT_MODES = {"sip": 2, "lumpsum": 1}

# Return duration windows (days) accepted by the listing API
DURATIONS = {
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "3y": 1095,
    "5y": 1825,
    "10y": 3650,
}

# Sort keys accepted by the listing API
SORT_TYPES = {"etm_rank": 1, "returns": 3, "fund_size": 6}
SORT_ORDERS = {"asc", "desc"}

# Fund-size buckets (bitmask): <100Cr=1, 100-500Cr=2, 500-1000Cr=4, >1000Cr=8
FUND_SIZE_BUCKETS = {"<100cr": 1, "100-500cr": 2, "500-1000cr": 4, ">1000cr": 8}

# Primary category groups as returned by the listing API
CATEGORY_GROUPS = ("EQUITY", "DEBT", "HYBRID", "COMMODITIES", "OTHERS")

# Stock market-data screens: slug -> page id
SCREENS = {
    "top_gainers": "top-gainers/2",
    "top_losers": "top-losers/3",
    "52w_high": "at-52-week-high/12",
    "52w_low": "at-52-week-low/14",
    "all_time_high": "all-time-high/8",
    "all_time_low": "all-time-low/10",
    "high_dividend_yield": "high-dividend-yield-stocks/36",
    "bluechip": "bluechip-stocks/38",
    "multibagger": "multibagger-stocks/37",
    "most_active": "most-active-stocks/43",
}

# Popular indices: slug -> page id
INDICES = {
    "nifty_50": "nifty-50/31",
    "nifty_next_50": "nifty-next-50/23",
    "nifty_100": "nifty-100/27",
    "nifty_200": "nifty-200/65",
    "nifty_500": "nifty-500/19",
    "nifty_midcap_50": "nifty-midcap-50/88",
    "nifty_midcap_150": "nifty-midcap-150/47",
    "nifty_smallcap_250": "nifty-smallcap-250/6",
    "nifty_bank": "nifty-bank/29",
    "nifty_fmcg": "nifty-fmcg/103",
}

# Sector pages: slug -> page id
SECTORS = {
    "automobiles": "automobiles/415",
    "banking": "banking/418",
    "defence": "defence/383",
    "fmcg": "fmcg/178",
    "healthcare": "hospital-and-healthcare-services/341",
    "it_software": "it-software/237",
    "refineries": "refineries/212",
    "pharmaceuticals": "pharmaceuticals/218",
    "power": "power-generation-distribution/286",
    "telecom": "telecom-services/293",
}

# Featured fund themes: slug -> page id
THEMES = {
    "best_index_funds": "best-index-funds/12",
    "best_mutual_funds": "best-mutual-funds/29",
    "best_sip_funds": "best-sip-funds/18",
    "best_fof": "best-fund-of-funds-fof/27",
    "best_gold_funds": "best-gold-mutual-funds/25",
    "low_risk": "best-low-risk-mutual-funds/21",
    "moderate_risk": "moderate-risk-mutual-funds/10",
    "high_return": "high-risk-and-high-returns/20",
    "retirement": "retirement-funds/13",
    "beginners": "mutual-fund-for-beginners/14",
    "better_than_fd": "mutual-funds-better-than-fd/22",
    "better_than_savings": "earn-more-than-savings-account/2",
    "balanced": "best-balanced-funds/3",
    "nifty50_index": "best-nifty-50-index-funds/30",
}
