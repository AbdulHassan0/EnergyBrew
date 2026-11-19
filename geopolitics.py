"""EnergyBrew geopolitical energy-market impact signals (research only).

Flag global political/security developments with an explicit energy-market
exposure, not general election/conflict news. No automatic impact verification.
"""
import re

ACTORS = (
    "iran", "iranian", "israel", "israeli", "russia", "russian", "ukraine",
    "ukrainian", "china", "chinese", "taiwan", "venezuela", "venezuelan",
    "saudi arabia", "kuwait", "bahrain", "qatar", "uae", "emirates",
    "yemen", "houthi", "houthis", "iraq", "libya", "nigeria", "egypt",
    "turkey", "pakistan", "india", "european union", "eu", "europe",
    "united states", "us", "u.s.", "american", "united kingdom",
    "britain", "nato", "north korea", "south korea", "mozambique",
)
EVENTS = (
    "sanctions", "sanctioned", "embargo", "trade war", "tariff", "tariffs",
    "export ban", "import ban", "export restrictions", "trade restrictions",
    "attacked", "attack", "attacks", "airstrike", "airstrikes",
    "strikes", "strike", "missile", "missiles", "drone", "drones",
    "blockade", "blockaded", "war", "invasion", "invades", "military",
    "conflict", "ceasefire", "sabotage", "seized", "seizes", "seizure",
    "retaliation", "retaliates", "threatens", "threatened", "bombed",
    "bombing", "shipping disruption", "nationalization",
)
MARKET_HOOKS = (
    "oil", "crude", "brent", "wti", "petroleum", "refinery", "refineries",
    "oilfield", "oilfields", "natural gas", "gas pipeline", "gas supply",
    "gas transit", "gas field", "lng", "liquefied", "fuel", "diesel",
    "gasoline", "tanker", "tankers", "shipping", "shipments",
    "pipeline", "pipelines", "energy", "power grid", "electric grid",
    "power plant", "electricity", "solar panels", "energy exports",
    "strait of hormuz", "hormuz", "bab el mandeb", "red sea", "suez canal",
)
CHOKEPOINTS = ("strait of hormuz", "hormuz", "bab el mandeb", "red sea", "suez canal")


def present(title, phrase):
    return bool(re.search(r"(?<![a-z0-9_])" + re.escape(phrase) +
                          r"(?![a-z0-9_])", title, re.I))


def geopolitical_evidence(title):
    """Signals are potential market exposure, never proof of actual price moves."""
    title = (title or "").lower()
    actors = [x for x in ACTORS if present(title, x)]
    risks = [x for x in EVENTS if present(title, x)]
    market = [x for x in MARKET_HOOKS if present(title, x)]
    chokepoints = [x for x in CHOKEPOINTS if present(title, x)]
    if not (actors or chokepoints) or not risks or not market:
        return []
    return ["geopolitical_event:" + risks[0],
            "energy_market_hook:" + market[0],
            "world_context:" + (actors[0] if actors else chokepoints[0])]
