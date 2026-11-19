# EnergyBrew six-beat pilot content handoff

This is the critical handoff between finding real source articles and
assembling complete five-minute pilot emails. News discovery alone cannot
write truthful 40-word summaries.

## Input

Create `newsletter/briefs/YYYY-MM-DD.json` with an ISO date, optional
intro and a nonempty array of *authored* briefs.

```json
{
  "edition_date": "YYYY-MM-DD",
  "intro": "A short, original morning introduction.",
  "briefs": [
    {
      "section": "Natural Gas",
      "source_url": "https://example.com/actual-original-article",
      "publisher": "Original publisher",
      "source_date": "YYYY-MM-DD",
      "title": "Original article summary headline",
      "summary": "An original, source-supported 18–110 word news brief authored after reading the original source.",
      "why_it_matters": "An original, energy-market-specific 8–65 word implication.",
      "priority": 80
    }
  ]
}
```

The JSON above is **schema illustration only**; sample URL and copy must
never be used in a live pilot. Each real issue requires complete material
for **all six categories**: Natural Gas, LNG, Power & Electricity,
Oil & Energy, Infrastructure & Investment, and Geopolitics. Two extras
are allowed when supported. The source URL must exist in the retained
RSS/GDELT/issuer metadata. The compiler does not scrape publisher text,
invent missing numbers or infer source publication dates from GDELT.

## Run without paid infrastructure

```bash
python brief_compiler.py --desk state/desk_latest.json --briefs newsletter/briefs/YYYY-MM-DD.json --rss state/articles.json --discovery state/discovery.json --releases state/press_releases.json --out output/newsletter/COMPILED_PILOT.json
python pilot_audit.py --pilot output/newsletter/COMPILED_PILOT.json --desk state/desk_latest.json --rss state/articles.json --discovery state/discovery.json --releases state/press_releases.json --output output/newsletter/PILOT_QUALITY_REPORT.json
python newsletter.py pilot-preview --edition output/newsletter/COMPILED_PILOT.json --html output/newsletter/PILOT_email_preview.html --text output/newsletter/PILOT_email_preview.txt
```

The GitHub editorial workflow performs these steps automatically
**only if a real daily briefs file exists**. Otherwise it preserves the
unsummarized research queue rather than generating a misleading email.
Cutoff-completeness and licensed redistribution are not claimed.
Production sending and approval still remain separately disabled.
