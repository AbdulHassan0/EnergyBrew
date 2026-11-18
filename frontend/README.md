# EnergyBrew — five-minute morning newsletter preview

EnergyBrew is built around a simple idea: **five minutes of energy news with your morning coffee**. The frontend now behaves like a short editorial edition rather than a dense research dashboard.

## Website

**[Open EnergyBrew](https://abdulhassan0.github.io/EnergyBrew/)**

The current website is a **research preview**, not a fact-checked published newsletter. It includes a six-headline morning selection and a full searchable research desk sourced from the live GitHub-hosted collectors. Source dates are labeled by what they actually represent.

## What you can do

- Browse a concise morning selection drawn from real research leads, without made-up summaries.
- Mark those headlines read and track your morning progress; your choices stay in your browser.
- Save links for later.
- Open the original publisher or regulator source.
- Switch to Full research desk to search and filter natural gas/LNG, power, oil and infrastructure news.
- View source-health information and publication-date caveats.

The site deliberately has **no fake email signup**. Subscriber registration, verified editorial context, and five-minute daily email delivery remain development work.

## How to preview locally

Download the "energybrew-frontend-preview" artifact from the latest [frontend Actions run](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/site-preview.yml), extract the ZIP, and run:

    python -m http.server 8000

Open http://localhost:8000/ to use the site.

## How to deploy

GitHub repository **Settings → Pages → Source: GitHub Actions**. The [site-preview workflow](https://github.com/AbdulHassan0/EnergyBrew/actions/workflows/site-preview.yml) rebuilds on frontend changes and attempts to refresh the site every two hours using the latest private \`collector-state\` branch snapshot. GitHub Actions can be delayed; the site labels its own snapshot date.

## Technical and editorial commitments

- Pure HTML, CSS and JavaScript; Python builds a static JSON export. No npm dependencies.
- Only whitelisted metadata is exported from the private collection state.
- Links are validated and rendered with DOM textContent rather than unsafe HTML insertion.
- User choices are stored locally; no account or email address is collected.
- Discovery "first indexed" dates are not presented as verified original publisher publication times.
- All leads remain unapproved until editorial review, original-source verification and rights checks.

The product truth and visual direction are recorded in [PRODUCT.md](../PRODUCT.md) and [DESIGN.md](../DESIGN.md).
