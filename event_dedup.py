"""Conservative likely-same-event detection for energy news source links.

A cluster is never presented as verified independent corroboration. The desk
preserves alternative publisher URLs for human review, but shows one top lead.
"""
from __future__ import annotations
import re
from datetime import datetime

ENTITY_NAMES = (
    "venture global", "china gas", "woodside", "trafigura", "cheniere",
    "qatarenergy", "qatar energy", "exxonmobil", "exxon mobil", "chevron",
    "orlen", "equinor", "bp", "shell", "totalenergies", "nextdecade",
    "kinder morgan", "energy transfer", "williams", "vistra", "constellation",
    "microsoft", "amazon", "google", "meta", "sabine pass", "golden pass",
    "freeport lng", "corpus christi lng", "cameron lng", "plaquemines lng",
    "lake charles lng", "algonquin gas transmission",
)
COMMON = frozenset((
    "the of as on to with for a an and in at after from by new more than"
    " energy gas lng oil power electricity pipeline project natural major"
    " big deal update says announces announced report latest its their"
).split())


def words(title):
    return {x for x in re.findall(r"[a-z0-9]+", (title or "").lower())
            if len(x) >= 3 and x not in COMMON}


def entities(title):
    raw = " " + re.sub(r"[^a-z0-9 ]", " ", (title or "").lower()) + " "
    found = {name for name in ENTITY_NAMES
             if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", raw)}
    for variant, canonical in (("exxon mobil","exxonmobil"),("qatar energy","qatarenergy")):
        if variant in found:
            found.remove(variant)
            found.add(canonical)
    return found


def family(title):
    t = (title or "").lower()
    if re.search(r"\b(lng|liquefied natural gas)\b",t) and re.search(
        r"\b(agreement|contract|deal|offtake|supply|long.term|upsizes|increase[ds]?|expands?)\b",t
    ):
        return "lng_contract"
    if re.search(r"\b(acquisition|acquires?|takeover|merger|purchases?|buys?|stake)\b",t):
        return "merger"
    return None


def event_direction(title):
    """Identify explicit opposite developments; unknown titles remain unclassified.

    This is deliberately narrow: ambiguous headlines should not be assigned an
    invented status just to increase deduplication.
    """
    t = (title or "").lower()
    adverse = re.search(
        r"\b(cancelled|canceled|cancels|terminates?|terminated|scrapped|"
        r"suspended|suspends|halted|halts|withdrawn|withdraws|revoked|"
        r"rejected|blocked)\b", t)
    positive = re.search(
        r"\b(signed|signs|approved|approves|resumed|resumes|restarted|"
        r"restarts|secured|awarded|greenlit|completed)\b", t)
    if adverse and not positive:
        return "adverse"
    if positive and not adverse:
        return "positive"
    return None


def same_event(a, b):
    if a.get("url") == b.get("url"):
        return True
    try:
        dt_a=datetime.fromisoformat(a["observed_time_utc"].replace("Z","+00:00"))
        dt_b=datetime.fromisoformat(b["observed_time_utc"].replace("Z","+00:00"))
        if dt_a.tzinfo is None or dt_b.tzinfo is None:
            return False
        if abs((dt_a-dt_b).total_seconds())>48*3600:
            return False
    except (KeyError,ValueError,TypeError):
        return False
    # A deal being cancelled, a permit being revoked, or production halting
    # is not the same news development as its signing, approval or restart.
    direction_a = event_direction(a.get("title", ""))
    direction_b = event_direction(b.get("title", ""))
    if direction_a and direction_b and direction_a != direction_b:
        return False
    name_a=entities(a.get("title",""))
    name_b=entities(b.get("title",""))
    fam_a=family(a.get("title",""))
    fam_b=family(b.get("title",""))
    # A merger and a supply contract can feature the same counterparties
    # and overlapping headline terms; they are separate developments.
    if fam_a and fam_b and fam_a != fam_b:
        return False
    # Conflicting explicitly named counterparties trump generic headline
    # similarity. A shared company alone does not make two deals one event.
    if name_a - name_b and name_b - name_a:
        return False
    # Two contracts between the same counterparties are not necessarily the
    # same event. Different explicit transaction figures or years protect
    # distinct developments from a false merge, even on the entity shortcut.
    numbers_a=set(re.findall(r"\d+(?:\.\d+)?",a.get("title","")))
    numbers_b=set(re.findall(r"\d+(?:\.\d+)?",b.get("title","")))
    if numbers_a and numbers_b and numbers_a!=numbers_b:
        return False
    if fam_a and fam_a==fam_b and len(name_a & name_b)>=2:
        return True
    x,y=words(a.get("title","")),words(b.get("title",""))
    common=x & y
    if len(common)<6:
        return False
    # Different numbers often distinguish projects or individual transactions.
    return len(common)/len(x|y)>=.78


def attach_related(primary, related):
    primary.setdefault("related_reports",[]).append({
        "title":related["title"],"url":related["url"],"source":related.get("source"),
        "origin":related.get("origin"),
        "note":"Potential same-event source link; not independently corroborated",
    })
