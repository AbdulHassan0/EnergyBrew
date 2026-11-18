"""EnergyBrew editorial pipeline: draft research, validate approvals, render newsletter.

Collection and ranking NEVER constitute verification or permission to publish.
This module contains no AI-generated copy and never auto-approves stories.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

LOCAL_ZONE = ZoneInfo("America/Chicago")
TOPICS = ("Natural Gas & LNG", "Power & Electricity", "Oil & Energy",
          "Infrastructure & Investment")
MAX_ARTICLES = 8
MIN_ARTICLES = 4
MAX_WORDS = 875


class EditorialError(ValueError):
    """Newsletter issue has not met the editorial publication gate."""


def valid_url(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        parsed = urlparse(raw.strip())
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not any(ch in raw for ch in ("\r", "\n", "\x00")))
    except ValueError:
        return False


def parse_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None or d.utcoffset() is None:
        return None
    return d.astimezone(timezone.utc)


def date_only(raw: object) -> bool:
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return False
    try:
        return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d") == raw
    except ValueError:
        return False


def word_count(raw: object) -> int:
    return len(str(raw or "").split())


def safe_text(raw: object, max_chars: int = 300) -> str:
    return " ".join(str(raw or "").split())[:max_chars]


def research_queue(desk: dict, *, edition_date: str | None = None, limit: int = 10) -> dict:
    """Make private editor work items with *empty* summary fields."""
    if not isinstance(desk, dict) or not isinstance(desk.get("stories"), list):
        raise EditorialError("Collector desk does not contain a stories array")
    issue_date = edition_date or datetime.now(LOCAL_ZONE).date().isoformat()
    if not date_only(issue_date):
        raise EditorialError("Expected valid YYYY-MM-DD local issue date")
    cleaned = []
    seen = set()
    for entry in desk["stories"]:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not valid_url(url) or url in seen:
            continue
        title = safe_text(entry.get("title"))
        if not title:
            continue
        seen.add(url)
        topic = entry.get("category") if entry.get("category") in TOPICS else "Oil & Energy"
        cleaned.append({
            "title": title,
            "source_url": url,
            "publisher": safe_text(entry.get("source") or entry.get("domain"), 100),
            "section": topic,
            "lead_origin": safe_text(entry.get("origin"), 40),
            "lead_observed_utc": safe_text(entry.get("observed_time_utc"), 40),
            "lead_date_basis": safe_text(entry.get("time_basis"), 60),
            "source_date": "",
            "summary": "",
            "why_it_matters": "",
            "fact_check_evidence_urls": [],
            "original_source_checked": False,
            "publisher_date_checked": False,
            "facts_checked": False,
            "summary_rights_checked": False,
            "verification_notes": "",
        })
    chosen = []
    selected = set()
    # Ensure a beat-balanced shortlist while preserving desk ranking in each beat.
    for topic in TOPICS:
        item = next((x for x in cleaned if x["section"] == topic and x["source_url"] not in selected), None)
        if item:
            chosen.append(item)
            selected.add(item["source_url"])
    for item in cleaned:
        if len(chosen) >= limit:
            break
        if item["source_url"] not in selected:
            chosen.append(item)
            selected.add(item["source_url"])
    return {
        "schema_version": 1,
        "edition_date": issue_date,
        "status": "draft",
        "headline": "Your daily shot of energy.",
        "intro": "",
        "approval": {"editor": "", "approved_at_utc": "", "edition_fact_checked": False,
                     "distribution_rights_checked": False},
        "stories": chosen[:limit],
        "research_snapshot_utc": desk.get("generated_utc"),
        "notice": "RESEARCH ONLY: original article/date/facts/rights not verified. Do not send.",
    }


def validate_approved(edition: dict, *, now: datetime | None = None) -> dict:
    """Fail closed unless human editorial metadata and content are all provided.

    Boolean attestations are human declarations; software cannot independently
    verify whether an original publisher page supports the written claims.
    """
    now = now or datetime.now(timezone.utc)
    errors = []
    if not isinstance(edition, dict):
        raise EditorialError("Edition must be a JSON object")
    if edition.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if not date_only(edition.get("edition_date")):
        errors.append("edition_date must be a valid YYYY-MM-DD")
    if edition.get("status") != "approved":
        errors.append("edition status must be 'approved'")
    approval = edition.get("approval")
    if not isinstance(approval, dict):
        approval = {}
    if len(safe_text(approval.get("editor"), 100)) < 2:
        errors.append("approval.editor must identify the human approver")
    approved_at = parse_utc(approval.get("approved_at_utc"))
    if approved_at is None or approved_at > now:
        errors.append("approval.approved_at_utc must be a nonfuture UTC timestamp")
    if approval.get("edition_fact_checked") is not True:
        errors.append("approval.edition_fact_checked must be true")
    if approval.get("distribution_rights_checked") is not True:
        errors.append("approval.distribution_rights_checked must be true")
    stories = edition.get("stories")
    if not isinstance(stories, list) or not MIN_ARTICLES <= len(stories) <= MAX_ARTICLES:
        errors.append(f"stories must have {MIN_ARTICLES}–{MAX_ARTICLES} items")
        stories = stories if isinstance(stories, list) else []
    seen = set()
    total_words = word_count(edition.get("intro"))
    for i, story in enumerate(stories, 1):
        if not isinstance(story, dict):
            errors.append(f"story {i} must be an object")
            continue
        name = f"story {i}"
        url = story.get("source_url")
        if not valid_url(url):
            errors.append(f"{name}: source_url must be https with no credentials")
        elif url in seen:
            errors.append(f"{name}: duplicate original source URL")
        else:
            seen.add(url)
        if word_count(story.get("title")) < 3:
            errors.append(f"{name}: meaningful title missing")
        if not (isinstance(story.get("publisher"), str) and story["publisher"].strip()):
            errors.append(f"{name}: publisher missing")
        if story.get("section") not in TOPICS:
            errors.append(f"{name}: unrecognized energy section")
        if not date_only(story.get("source_date")):
            errors.append(f"{name}: verified original publisher date missing")
        summary_words = word_count(story.get("summary"))
        why_words = word_count(story.get("why_it_matters"))
        if not 18 <= summary_words <= 110:
            errors.append(f"{name}: summary must be 18–110 words")
        if not 8 <= why_words <= 65:
            errors.append(f"{name}: why_it_matters must be 8–65 words")
        total_words += summary_words + why_words + word_count(story.get("title"))
        for flag in ("original_source_checked", "publisher_date_checked",
                     "facts_checked", "summary_rights_checked"):
            if story.get(flag) is not True:
                errors.append(f"{name}: {flag} must be true")
        proof = story.get("fact_check_evidence_urls")
        if not isinstance(proof, list) or not proof or any(not valid_url(x) for x in proof):
            errors.append(f"{name}: at least one valid evidence URL is required")
        if not safe_text(story.get("verification_notes"), 800):
            errors.append(f"{name}: verification_notes required")
    if total_words > MAX_WORDS:
        errors.append(f"total reading copy exceeds {MAX_WORDS} words")
    if errors:
        raise EditorialError("Edition is NOT publishable:\n- " + "\n- ".join(errors))
    return edition


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _date_label(raw: str) -> str:
    return datetime.strptime(raw, "%Y-%m-%d").strftime("%B %-d, %Y")


def render_html(edition: dict, *, preview: bool = False) -> str:
    """Email-client-friendly table-based HTML; all editorial text escaped."""
    if not preview:
        validate_approved(edition)
    title = f"EnergyBrew — {_date_label(edition['edition_date'])}"
    story_html = []
    for i, item in enumerate(edition.get("stories", []), 1):
        if not isinstance(item, dict):
            continue
        raw_url = item.get("source_url")
        if not valid_url(raw_url):
            continue
        url = _esc(raw_url)
        summary = _esc(item.get("summary") or "[Summary pending fact-check]")
        why = _esc(item.get("why_it_matters") or "[Why it matters pending review]")
        sector = _esc(item.get("section"))
        story_html.append(
            '<tr><td style="padding:24px 30px 18px;border-bottom:1px solid #e2d6ca">'
            f'<p style="font:700 11px Arial,sans-serif;letter-spacing:1px;color:#a45232;margin:0 0 10px">{sector}</p>'
            f'<h2 style="font:normal 26px/1.22 Georgia,serif;color:#28211c;margin:0 0 14px">{_esc(item.get("title"))}</h2>'
            f'<p style="font:15px/1.7 Arial,sans-serif;color:#4c443d;margin:0 0 14px">{summary}</p>'
            f'<p style="font:14px/1.6 Arial,sans-serif;color:#392b25;margin:0 0 16px"><strong>Why it matters:</strong> {why}</p>'
            f'<a href="{url}" style="font:700 13px Arial,sans-serif;color:#a45232;text-decoration:underline">Read original at {_esc(item.get("publisher"))} →</a>'
            f'<p style="font:11px Arial,sans-serif;color:#7b7168;margin:12px 0 0">Original source date: {_esc(item.get("source_date") or "not verified")}</p>'
            '</td></tr>')
    draft_label = (
        '<tr><td style="padding:16px 30px;background:#f9e6d1;color:#633820;font:700 12px/1.6 Arial,sans-serif">'
        'DRAFT — NOT FACT-CHECKED, APPROVED, OR AUTHORIZED FOR DISTRIBUTION'
        '</td></tr>' if preview else ""
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_esc(title)}</title></head>'
        '<body style="margin:0;padding:22px 10px;background:#f7f2e9;color:#28211c">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"><tr><td align="center">'
        '<table role="presentation" width="600" style="width:100%;max-width:600px;border-collapse:collapse;background:#fffdfa" cellspacing="0" cellpadding="0" border="0">'
        f'{draft_label}'
        '<tr><td style="background:#392b25;padding:28px 30px;color:#fff6e9">'
        '<p style="font:700 12px Arial,sans-serif;letter-spacing:1.5px;margin:0 0 16px">ENERGYBREW / THE MORNING BRIEF</p>'
        '<h1 style="font:normal 40px/1.12 Georgia,serif;letter-spacing:-1px;margin:0 0 14px">Your daily shot of energy.</h1>'
        f'<p style="font:14px Arial,sans-serif;margin:0;color:#e9d6c4">{_esc(_date_label(edition["edition_date"]))} · About five minutes with your coffee</p>'
        '</td></tr>'
        f'<tr><td style="padding:23px 30px 8px;font:15px/1.7 Arial,sans-serif;color:#54493f">{_esc(edition.get("intro") or "The energy headlines worth knowing.")}</td></tr>'
        + "".join(story_html) +
        '<tr><td style="padding:24px 30px;font:12px/1.6 Arial,sans-serif;color:#675b50">'
        'EnergyBrew · Independent concise energy reporting. Original links provided for context.'
        '<p style="margin:12px 0 0">To unsubscribe, use the preference link provided by the eventual email service. '
        'This HTML is a render preview only until an email provider and consent workflow are configured.</p>'
        '</td></tr></table></td></tr></table></body></html>'
    )


def render_text(edition: dict, *, preview: bool = False) -> str:
    if not preview:
        validate_approved(edition)
    lines = ["ENERGYBREW — YOUR DAILY SHOT OF ENERGY", _date_label(edition["edition_date"]), ""]
    if preview:
        lines += ["DRAFT / UNVERIFIED / NOT APPROVED FOR DISTRIBUTION", ""]
    lines += [edition.get("intro") or "The energy headlines worth knowing.", ""]
    for item in edition.get("stories", []):
        lines += [item.get("section", ""), item.get("title", ""),
                  item.get("summary") or "[Summary pending fact-check]",
                  "Why it matters: " + (item.get("why_it_matters") or "[Pending review]"),
                  item.get("source_url", ""), ""]
    return "\n".join(lines).strip() + "\n"


def archive(edition_dir: Path, output_dir: Path, email_out: Path) -> int:
    """Publish only approved, valid issues. Invalid 'approved' files abort the build."""
    output_dir.mkdir(parents=True, exist_ok=True)
    email_out.mkdir(parents=True, exist_ok=True)
    editions = []
    for path in sorted(edition_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") == "draft":
            continue
        validate_approved(data)
        if path.stem != data["edition_date"]:
            raise EditorialError(f"{path}: filename must match edition_date")
        editions.append(data)
    entries = []
    for item in sorted(editions, key=lambda x: x["edition_date"], reverse=True):
        filename = item["edition_date"] + ".html"
        (output_dir / filename).write_text(render_html(item), encoding="utf-8")
        entries.append(f'<li><a href="./{_esc(filename)}">{_esc(_date_label(item["edition_date"]))}</a> — five-minute energy brief</li>')
    latest = editions[-1] if editions else None
    if latest:
        (email_out / "newsletter_email.html").write_text(render_html(latest), encoding="utf-8")
        (email_out / "newsletter_email.txt").write_text(render_text(latest), encoding="utf-8")
    body = "<ul>" + "".join(entries) + "</ul>" if entries else "<p>No approved issues yet. Newsletter editions will appear here after editorial verification and sign-off.</p>"
    index = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width, initial-scale=1">'
             '<title>EnergyBrew — Edition archive</title></head>'
             '<body style="margin:0;background:#f7f2e9;color:#392b25;font:16px/1.7 Arial,sans-serif">'
             '<main style="max-width:640px;margin:70px auto;padding:0 24px">'
             '<p><a href="../" style="color:#9b4a30">← Back to EnergyBrew</a></p>'
             '<h1 style="font:normal 48px Georgia,serif">Past morning brews</h1>'
             + body + '</main></body></html>')
    (output_dir / "index.html").write_text(index, encoding="utf-8")
    return len(editions)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare", help="Private draft from live collector leads; NO summary invented")
    p.add_argument("--desk", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--date")
    p = sub.add_parser("preview", help="Render private, clearly unapproved review artifact")
    p.add_argument("--draft", type=Path, required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--text", type=Path)
    p = sub.add_parser("archive", help="Render approved editions only")
    p.add_argument("--editions", type=Path, default=Path("newsletter/editions"))
    p.add_argument("--site", type=Path, default=Path("dist/editions"))
    p.add_argument("--email-out", type=Path, default=Path("output/newsletter"))
    p = sub.add_parser("validate", help="Check an approved edition's editorial gate")
    p.add_argument("--edition", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "prepare":
        desk = json.loads(args.desk.read_text(encoding="utf-8"))
        draft = research_queue(desk, edition_date=args.date)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Prepared {len(draft['stories'])} UNAPPROVED research leads in {args.out}")
    elif args.action == "preview":
        draft = json.loads(args.draft.read_text(encoding="utf-8"))
        if draft.get("status") != "draft":
            raise EditorialError("Preview action is only for unapproved draft queue files")
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(draft, preview=True), encoding="utf-8")
        if args.text:
            args.text.parent.mkdir(parents=True, exist_ok=True)
            args.text.write_text(render_text(draft, preview=True), encoding="utf-8")
        print(f"Wrote clearly labeled unapproved draft preview: {args.html}")
    elif args.action == "archive":
        print(f"Published {archive(args.editions, args.site, args.email_out)} approved issues.")
    else:
        validate_approved(json.loads(args.edition.read_text(encoding="utf-8")))
        print("Editorial approval gates passed; this is a metadata check, not independent fact checking.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
