# EnergyBrew — direct news feed rights review

Status: November 18, 2026. This inventory is **news collection engineering only**.

A public RSS endpoint responding with HTTP 200 establishes **technical reachability, not commercial-use permission**. EnergyBrew must not ingest publisher article bodies, store long snippets, republish or automatically distribute content without appropriate rights. GDELT discovery links are different from directly polling an outlet's RSS and do not imply rights to extract or publish its work.

## Explicit restrictions and safe defaults

| Source | Tested endpoint | Hosted probe | Direct production use | Reason |
|---|---|---|---|---|
| LNG Prime | https://lngprime.com/feed/ | Working | BLOCK pending permission | https://lngprime.com/terms-and-conditions/ prohibits republishing, redistributing and reediting site material without consent |
| Energy-Storage.news | https://www.energy-storage.news/feed/ | Working | BLOCK pending permission | https://www.energy-storage.news/terms-of-use/ restricts reproduction or storage in another electronic retrieval system without written permission |
| POWER Magazine | https://www.powermag.com/feed/ | Working | Review pending | Feed reachable; publisher-specific commercial rights to automate and reuse metadata not confirmed |
| Power Engineering | https://www.power-eng.com/feed/ | Working | Review pending | Feed reachable; publisher-specific commercial rights to automate and reuse metadata not confirmed |
| LNG Industry | https://www.lngindustry.com/feed/ | XML parse error | Disabled | Parser failed on the hosted-run endpoint; no supported feed confirmed |
| Rigzone / Oil & Gas Journal | RSS endpoints not connected | Not commissioned | BLOCK | Known commercial-use restrictions from prior source-vetting work; verify specific terms and seek permission |

Following this review, recurring automated diagnostics SKIP every new publisher feed whose permission remains blocked or under review. The one-off hosted connectivity results above remain historical research only.

Production source changes require: publisher identity, official endpoint evidence, source classification, latest hosted connectivity, separate 24h article volume, posted usage terms or documented permission, and a public-metadata-only collection policy. Keep full-content scraping, credential bypass and unauthorized syndicated redistribution out of scope.

The currently connected 15 public-source metadata feeds are an **existing pilot**, not a blanket grant of commercial redistribution rights. Future reviews may require changes to that pilot. A metadata link is never an independently fact-checked news story.
