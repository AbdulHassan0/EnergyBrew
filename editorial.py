"""Conservative, explainable relevance signals for EnergyBrew editorial research.
This ranks candidates; it does not verify facts, approve stories, or grant content rights.
"""
from __future__ import annotations
import re
from collections import defaultdict

# Strong sector-specific phrases; generic words such as "project", "commission",
# "energy", "oil" inside another word, or "capacity" alone do not qualify a story.
BEATS = {
    "Natural Gas & LNG": {
        "natural gas": 12, "lng": 13, "liquefied": 10, "gas pipeline": 10,
        "gas storage": 9, "gas-fired": 9, "gas exports": 9,
        "feedgas": 12, "henry hub": 12, "haynesville": 10,
        "bossier shale": 9, "waha": 9, "perryville": 8,
        "gillis": 8, "methane": 6, "gas production": 10,
        "gas supply": 9, "gas demand": 9, "pipeline capacity": 7,
        "gas prices": 9, "gas-fired power": 10,
        "gas transmission": 10, "algonquin gas transmission": 12,
        "northwest pipeline": 10, "interstate pipeline": 10,
        "texas eastern": 9, "trunkline": 9, "transco": 9,
        "columbia gulf": 9, "gulf run": 10,
        "cheniere": 13, "venture global": 13, "nextdecade": 12,
        "golden pass": 12, "plaquemines lng": 12, "sabine pass": 11,
        "freeport lng": 11, "cameron lng": 11, "woodside energy": 10,
        "commonwealth lng": 11, "sempra infrastructure": 10,
        "lng tanker": 10, "lng feedgas": 13, "gas basis": 10,
    },
    "Power & Electricity": {
        "electricity": 11, "power grid": 11, "grid reliability": 11,
        "power demand": 11, "power plant": 10, "transmission line": 9,
        "electric transmission": 10, "interconnection": 9,
        "data center": 10, "load growth": 9, "power generation": 9,
        "generation capacity": 8, "capacity market": 10,
        "ercot": 12, "pjm": 10, "miso": 10, "caiso": 10, "nyiso": 10,
        "iso-ne": 10, "offshore wind": 9, "electrification": 5,
        "nuclear plant": 9, "utility rates": 7, "power prices": 10,
        "vistra": 10, "calpine": 10, "nrg energy": 10,
        "southwest power pool": 10, "iso new england": 10,
    },
    "Oil & Energy": {
        "crude oil": 12, "brent": 11, "wti": 11, "oil prices": 11,
        "oil production": 10, "oil exports": 10, "oil pipeline": 10,
        "refinery": 10, "petroleum": 9, "opec": 10, "drilling": 7,
        "gasoline": 8, "diesel": 7, "oilfield": 7, "oil and gas": 10,
        "upstream": 7, "offshore production": 10,
        "chevron": 11, "exxonmobil": 11, "exxon mobil": 11,
        "conocophillips": 11, "diamondback energy": 9,
    },
    "Infrastructure & Investment": {
        "pipeline project": 10, "pipeline expansion": 12,
        "lng terminal": 12, "export terminal": 11, "export facility": 9,
        "final investment decision": 12, "energy acquisition": 10,
        "pipeline permit": 10, "in-service date": 10,
        "gas infrastructure": 10, "grid expansion": 10,
        "transmission project": 10, "ferc": 7,
        "pipeline approval": 12, "lng project": 10,
        "kinder morgan": 10, "energy transfer": 9,
        "williams companies": 9, "pipeline takeaway": 10,
    },
}

def occurrences(text, phrase):
    # Underscores count as word characters: electricity_demand is a tag name,
    # not an article mentioning electricity. Word boundaries also prevent
    # e.g. "oil" from matching "boiler" or "spoiled".
    return bool(re.search(r"(?<![a-z0-9_])" + re.escape(phrase) + r"(?![a-z0-9_])", text, re.I))


def non_article_reason(title, url=""):
    """Reject obvious landing/tag pages, not foreign-language energy articles."""
    from urllib.parse import urlsplit
    title = (title or "").strip().lower()
    if not title:
        return "empty_title"
    if re.match(r"^(?:tag|tags|category|categories|archive|archives|topics?)\\s*:", title):
        return "archive_title"
    if not url:
        return None
    path = urlsplit(url).path.lower()
    # Only reject explicit top-level taxonomy paths. Do not throw away
    # legitimate articles simply because a URL has a category directory.
    if re.fullmatch(r"/(?:tag|tags|category|categories|archive|archives|topic|topics)/[^/]+/?", path):
        return "taxonomy_page"
    return None


def evaluate(title, excerpt=""):
    title = (title or "").lower()
    excerpt = (excerpt or "").lower()[:900]
    contributions = defaultdict(int)
    evidence = defaultdict(list)
    for category, terms in BEATS.items():
        for phrase, weight in terms.items():
            title_hit = occurrences(title, phrase)
            excerpt_hit = occurrences(excerpt, phrase)
            if phrase == "brent":
                # Brent Cross and other proper names are not crude benchmarks.
                # Require explicit price/oil context even for a lone "Brent".
                context = title + " " + excerpt
                oil_context = ("crude", "oil", "barrel", "bbl", "petroleum",
                               "futures", "wti", "opec", "benchmark", "baril", "barril")
                if occurrences(context, "brent cross") or not any(
                    occurrences(context, clue) for clue in oil_context
                ):
                    continue
            if title_hit or excerpt_hit:
                contributions[category] += weight * (3 if title_hit else 1)
                evidence[category].append(phrase)
    if not contributions:
        return {"category":"Cross-sector", "relevance_score":0, "editorial_candidate":False, "evidence":[]}
    best = max(BEATS, key=lambda category: contributions[category])
    score = min(100, contributions[best])
    # Only use high-confidence sector signals as a shortlist threshold;
    # single weak observations are still saved as research data.
    return {"category":best, "relevance_score":score,
            "editorial_candidate":score >= 22, "evidence":sorted(evidence[best])}

def normalized_event_title(title):
    """Conservative exact-title event key. Does not claim independent fact-checking."""
    words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return " ".join(words)
