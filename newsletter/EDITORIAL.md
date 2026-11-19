# EnergyBrew — five-minute newsletter editorial workflow

## Current stage

The collector discovers real source links. The newsletter engine generates unapproved review queues and email-ready layouts. **No collector lead is independently fact-checked, approved for publication, or licensed merely because it appeared in a feed.**

A weekday GitHub Action attempts to prepare an unapproved editorial queue around **6:15 AM America/Chicago** (subject to scheduling delay). No email is sent. Once a human approves a 4–8-story edition and commits its JSON file, the website can publish an archive and generate email-ready HTML/text. Actual subscriber delivery is NOT enabled.

## 1. Get the draft

Open https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/morning-editorial.yml and click Run workflow. Download the unapproved artifact named energybrew-editorial-draft-unapproved.

The artifact contains only source-linked lead metadata. Because this repository is currently PUBLIC, GitHub Actions artifacts may also be publicly accessible; do not put private editorial notes, credentials, subscriber information, licensed article text, or confidential material in this output.

The artifact contains:
- review_queue.json — real headlines/links, attribution, date basis, and empty editorial summary fields.
- DRAFT_email_preview.html — an email layout visibly marked DRAFT/UNVERIFIED.
- DRAFT_email_preview.txt — the same unapproved layout in plain text.

The automatic research queue does not invent article summaries or publication dates.

## 2. Verify and write the actual issue

For each candidate story, open the original source URL and:
1. Verify the original publishing date, source identity and facts, including any numbers and claims. A GDELT indexed-first-seen date is NOT a publisher date.
2. Check original material or corroborating primary sources for what is said.
3. Write an original concise summary (18–110 words) and a clear market-focused why-it-matters explanation (8–65 words).
4. Record source_date (YYYY-MM-DD), fact_check_evidence_urls (HTTPS original/evidence links), and useful verification_notes.
5. Only after individual verification, set original_source_checked, publisher_date_checked, and facts_checked to true.
6. Review publisher reuse and distribution permissions. Summarize in original wording; never copy article text. Only set summary_rights_checked after rights review.

Target about 500–700 total words for a five-minute issue; the validator enforces an 875-word maximum including headings and intro. Keep 4–8 distinct sources. Prioritize commercial relevance and avoid duplicating the same event across different publishers.

## 3. Human editorial approval

Keep the file name and issue date aligned: newsletter/editions/YYYY-MM-DD.json. IMPORTANT: this repository is PUBLIC; do not commit sensitive notes or private source material to it. The queue can be edited into an edition (schema_version=1).

Only after final review:
- Set status to approved.
- Set approval.editor to the responsible human editor.
- Set approval.approved_at_utc to the real timezone-aware approval timestamp.
- Set approval.edition_fact_checked and approval.distribution_rights_checked to true.

Run locally:

    python -m unittest discover -s tests -v
    python newsletter.py validate --edition newsletter/editions/YYYY-MM-DD.json
    python newsletter.py archive --editions newsletter/editions --site dist/editions --email-out output/newsletter

Validation enforces structured declarations, content bounds, HTTPS links and no duplicate URLs. **Code cannot independently verify that facts or permissions were actually checked.** An accountable editor is required.

Once committed to main, an approved valid edition is exported by the Pages workflow as a public page in /EnergyBrew/editions/. Invalid approved files stop the deployment rather than silently publishing.

## 4. Preview and optionally send ONE test email

For an approved edition, the archive command generates:

- output/newsletter/newsletter_email.html
- output/newsletter/newsletter_email.txt

The manually triggered Action is https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/newsletter-test-send.yml

Set protected GitHub Actions secrets: NEWSLETTER_TEST_TO (single consenting test address), NEWSLETTER_FROM (verified sender), SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and optionally SMTP_PORT (defaults to 587). The SMTP connection requires TLS on port 587 or SSL on 465.

Separately, set the repository Actions variable NEWSLETTER_ALLOW_TEST_SEND to YES before explicitly running the manual test workflow with the approved edition date. Never put email addresses or credentials in code. This test can send **one email to one test mailbox**. A manually rerun workflow can send a duplicate.

## 5. Requirements before a true daily subscriber mailing

Production delivery still requires a verified sending provider, opt-in subscriber system, unsubscribe preferences/links, suppression and bounce management, an actual send ledger/idempotency, legal review, monitoring, and any required sender authentication. **Do not turn the test workflow into a mass-email broadcaster.**

Publication rights must also be confirmed for any source-linked commercial use, regardless of whether an RSS feed or news website is publicly readable.

## 6. Operational troubleshooting

If the private queue has too few high-quality current articles, do not invent them: improve discovery or wait for verified material. If there is no approved issue, the public archive should say so rather than show a fake edition. If email credentials are not configured, the manual test fails safely without attempting delivery.

## MVP eight-story draft invariant

Research queues default to **no more than eight headlines** even when the
underlying six-category desk carries 32 links; this matches the publication
gate's 4–8-story limit. Unverified story summaries and publisher times remain
blank until a human editor checks originals and approves. Reducing to eight
does **not** make a draft sendable, and no delivery is implied.

## Temporary pilot mode (November 2026)

For testing a **complete readable email** without collecting human fact-check
attestations yet, use:

```bash
python newsletter.py pilot-preview --edition newsletter/pilots/2026-11-19.json --html output/newsletter/PILOT_email_preview.html --text output/newsletter/PILOT_email_preview.txt
```

A pilot file has `status: pilot`, source-linked, original briefs, and
market-impact notes. Pilot rendering intentionally skips source-date and
fact-check *attestation* gates. It still requires 4–8 real HTTPS source links,
nonempty substantive copy, correct beats, distinct URLs, and a five-minute
length cap. **Pilot mode does not publish, email, or permit subscriber sends.**
The existing `validate_approved()` publication and delivery gates are
unchanged and can be restored as the only mode by discontinuing
`pilot-preview`. Real content is preferable to invented title-only summaries;
this November 19 issue's prose was drafted from publisher articles.
