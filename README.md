# EnergyBrew — Energy TLDR

This private repository hosts the independent **Energy TLDR news-collection pilot**. It is separate from the public newsletter and never automatically publishes, approves editorial content, or sends subscriber emails.

The GitHub Actions collector will poll eligible official RSS sources, store source-linked article metadata and daily coverage statistics, and make the results inspectable in a dedicated `collector-state` branch. Publisher feeds without commercial collection clearance remain disabled.

**Launch status:** hosted collector provisioning is in progress. Verify actual runs under the [Actions tab](https://github.com/AbdulHassan0/EnergyBrew/actions) and consult the `collector-state` branch when available. A configured workflow is not proof that live ingestion has succeeded.

For the complete local newsletter MVP, the latest packaged build is Energy TLDR v2.0. This repository initially focuses on proving real internet-based collection before moving the entire web application here.
