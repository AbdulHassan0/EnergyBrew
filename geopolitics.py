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
# Exception for major cross-border military escalations with established
# energy-security exposure, even when a short wire headline omits oil or gas.
# The exposure is an inference for editorial review, not a factual price claim.
HIGH_IMPACT_PAIRINGS = (
    (("iran", "iranian"), ("israel", "israeli")),
    (("iran", "iranian"), ("united states", "us", "u.s.", "american")),
    (("russia", "russian"), ("ukraine", "ukrainian")),
    (("china", "chinese"), ("taiwan", "taiwanese")),
    (("iran", "iranian"), ("saudi arabia",)),
)
MAJOR_ESCALATIONS = (
    "missile", "missiles", "airstrike", "airstrikes", "strike", "strikes",
    "attack", "attacks", "attacked", "war", "invasion", "invades",
    "drone", "drones", "military", "blockade", "bombing", "bombed",
)


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
    if not risks or not (actors or chokepoints):
        return []
    if not market:
        # An explicit energy commodity is not in every internationally important
        # military headline. Surface only known cross-border escalation pairs,
        # clearly labeled as POTENTIAL risk rather than verified market impact.
        paired = next((
            (left[0], right[0])
            for left, right in HIGH_IMPACT_PAIRINGS
            if any(present(title, a) for a in left)
            and any(present(title, b) for b in right)
        ), None)
        if not paired or not any(present(title, risk) for risk in MAJOR_ESCALATIONS):
            return []
        return ["geopolitical_event:" + risks[0],
                "energy_market_exposure:inferred_high_risk_region",
                "world_context:" + "/".join(paired)]
    return ["geopolitical_event:" + risks[0],
            "energy_market_hook:" + market[0],
            "world_context:" + (actors[0] if actors else chokepoints[0])]
