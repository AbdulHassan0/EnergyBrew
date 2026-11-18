/* EnergyBrew morning edition — source-linked research, never invented reporting. */
(function () {
  "use strict";
  const LABELS = {
    "Natural Gas & LNG": "NATURAL GAS & LNG",
    "Power & Electricity": "POWER & ELECTRICITY",
    "Oil & Energy": "OIL & ENERGY",
    "Infrastructure & Investment": "INFRASTRUCTURE"
  };
  const CATEGORIES = Object.keys(LABELS);
  const ORIGIN = {
    official_rss: { name: "Official publisher feed", date: "Publisher feed date" },
    regulatory_notice: { name: "Regulatory notice", date: "Regulatory publication date" },
    global_discovery: { name: "Global discovery lead", date: "First indexed" },
    company_announcement: { name: "Company announcement", date: "Release feed date" }
  };
  const model = { stories: [], morning: [], view: "morning", category: "All", search: "", savedOnly: false, shown: 9, saved: new Set(), read: new Set() };
  const $ = (id) => document.getElementById(id);
  const make = (tag, klass, text) => {
    const n = document.createElement(tag);
    if (klass) n.className = klass;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
  const savedKey = "energybrew.saved.v1";
  const readKey = "energybrew.read.v1";
  function safeURL(raw) {
    try {
      const url = new URL(raw);
      if (!["https:", "http:"].includes(url.protocol)) return null;
      return url.href;
    } catch (_) { return null; }
  }
  function timeText(raw, detailed) {
    const date = new Date(raw);
    if (!raw || !Number.isFinite(date.getTime())) return "Date not confirmed";
    const options = { timeZone: "UTC", month: "short", day: "numeric", year: "numeric" };
    if (detailed) Object.assign(options, { hour: "2-digit", minute: "2-digit", hour12: false });
    return new Intl.DateTimeFormat("en-US", options).format(date) + (detailed ? " UTC" : "");
  }
  function originDate(story) {
    const definition = ORIGIN[story.origin];
    return (definition ? definition.date : "Observed") + " · " + timeText(story.observed_time_utc, false);
  }
  function link(story, label, klass) {
    const a = make("a", klass || "article-link", label);
    a.href = safeURL(story.url) || "#";
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.setAttribute("aria-label", label + " — opens original source in a new tab");
    return a;
  }
  function button(story, action) {
    const isRead = model.read.has(story.id);
    const isSaved = model.saved.has(story.id);
    const isActive = action === "read" ? isRead : isSaved;
    const label = action === "read" ? (isRead ? "✓ Read" : "Mark read") : (isSaved ? "★ Saved" : "☆ Save");
    const b = make("button", action === "read" ? "read-btn" : "save-btn", label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(isActive));
    b.setAttribute("aria-label", action === "read" ? (isRead ? "Mark story unread" : "Mark story read") : (isSaved ? "Remove saved story" : "Save story"));
    b.dataset[action] = story.id;
    return b;
  }
  function storyActions(story) {
    const controls = make("div", "story-controls");
    controls.append(link(story, "Read original ↗", "source-link"), button(story, "read"), button(story, "save"));
    if (Array.isArray(story.needs_editor_review) && story.needs_editor_review.length) {
      controls.append(make("span", "story-flag", "Review needed"));
    }
    return controls;
  }
  function meta(story) {
    const n = make("div", "article-meta");
    n.append(make("span", "", story.source || story.domain || "Original source"));
    n.append(make("span", "", originDate(story)));
    return n;
  }
  function featuredArticle(story) {
    const article = make("article", "featured-article" + (model.read.has(story.id) ? " is-read" : ""));
    article.append(make("div", "story-tag", (LABELS[story.category] || "ENERGY") + " · FIRST SIP"));
    const h = make("h3");
    h.append(link(story, story.title, "article-link"));
    article.append(h, meta(story), storyActions(story));
    return article;
  }
  function storyArticle(story, index) {
    const article = make("article", "story-item" + (model.read.has(story.id) ? " is-read" : ""));
    article.append(make("span", "story-index", String(index).padStart(2, "0")));
    const body = make("div", "story-body");
    body.append(make("div", "story-tag", LABELS[story.category] || "ENERGY"));
    const h = make("h3");
    h.append(link(story, story.title, "article-link"));
    body.append(h, meta(story), storyActions(story));
    article.append(body);
    return article;
  }
  function morningCut(stories) {
    // Preserve original ranked order *within* category; intentionally diversify
    // the opening six source-linked leads without claiming editorial verification.
    const chosen = [];
    const seen = new Set();
    for (const category of CATEGORIES) {
      const candidate = stories.find((s) => (s.category === category) && !seen.has(s.id));
      if (candidate) { chosen.push(candidate); seen.add(candidate.id); }
    }
    for (const story of stories) {
      if (chosen.length >= 6) break;
      if (!seen.has(story.id)) { chosen.push(story); seen.add(story.id); }
    }
    return chosen.slice(0, 6);
  }
  function filtered() {
    const q = model.search.trim().toLowerCase();
    return model.stories.filter((s) => {
      const tags = Array.isArray(s.coverage_themes) ? s.coverage_themes : [s.category];
      if (model.category !== "All" && !tags.includes(model.category)) return false;
      if (model.savedOnly && !model.saved.has(s.id)) return false;
      if (q && ![s.title, s.source, s.domain, s.category].join(" ").toLowerCase().includes(q)) return false;
      return true;
    });
  }
  function updateProgress() {
    const total = model.morning.length;
    const count = model.morning.filter((s) => model.read.has(s.id)).length;
    $("progress-count").textContent = count + " of " + total + " marked read";
    $("progress-track").setAttribute("aria-valuemax", String(total));
    $("progress-track").setAttribute("aria-valuenow", String(count));
    $("progress-fill").style.width = (total ? count / total * 100 : 0) + "%";
  }
  function render() {
    const morning = model.view === "morning";
    document.querySelectorAll("[data-view]").forEach((tab) => {
      const active = tab.dataset.view === model.view;
      tab.classList.toggle("is-selected", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-category]").forEach((tab) => {
      const active = tab.dataset.category === model.category;
      tab.classList.toggle("is-selected", active);
      tab.setAttribute("aria-pressed", String(active));
    });
    $("desk-tools").hidden = morning;
    $("reading-progress").hidden = !morning;
    $("open-all-stories").hidden = !morning;
    $("mode-caption").textContent = morning ? "Six source-linked headlines for a quick scan" : "Dig deeper into the collector's research links";
    $("saved-filter").textContent = (model.savedOnly ? "★ " : "☆ ") + "Saved (" + model.saved.size + ")";
    $("saved-filter").setAttribute("aria-pressed", String(model.savedOnly));
    const stories = morning ? model.morning : filtered();
    $("results-label").textContent = morning ? "YOUR MORNING RESEARCH CUT · " + stories.length + " LEADS" : stories.length + " RESEARCH " + (stories.length === 1 ? "LEAD" : "LEADS");
    $("featured").replaceChildren();
    $("stories-list").replaceChildren();
    if (!stories.length) {
      const empty = make("div", "feed-state");
      empty.append(make("h3", "", model.stories.length ? "Nothing in this view yet." : "No research leads available."));
      empty.append(make("p", "", model.stories.length ? "Clear the search or try another sector or saved filter." : "Check the next hosted collector scan."));
      $("stories-list").append(empty);
    } else if (morning) {
      $("featured").append(featuredArticle(stories[0]));
      stories.slice(1).forEach((story, i) => $("stories-list").append(storyArticle(story, i + 2)));
    } else {
      stories.slice(0, model.shown).forEach((story, i) => $("stories-list").append(storyArticle(story, i + 1)));
    }
    $("more").hidden = morning || stories.length <= model.shown;
    updateProgress();
  }
  function setView(next) {
    model.view = next === "desk" ? "desk" : "morning";
    model.shown = 9;
    render();
  }
  function showToast(text) {
    const toast = $("toast");
    toast.textContent = text;
    toast.classList.add("is-visible");
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 2000);
  }
  function loadSet(key) {
    try {
      const list = JSON.parse(localStorage.getItem(key) || "[]");
      return Array.isArray(list) ? new Set(list.filter((v) => typeof v === "string").slice(0, 500)) : new Set();
    } catch (_) { return new Set(); }
  }
  function storeSet(key, list) {
    try { localStorage.setItem(key, JSON.stringify(Array.from(list).slice(-500))); } catch (_) {}
  }
  function collectorStatus(data) {
    const metrics = data.metrics || {};
    const official = Date.parse(metrics.latest_official_scan_utc || "");
    const discovery = Date.parse(metrics.latest_gal_sample_utc || "");
    const officialOld = !Number.isFinite(official) || Date.now() - official > 12 * 3600000;
    const discoveryOld = !Number.isFinite(discovery) || Date.now() - discovery > 35 * 60000;
    return officialOld || discoveryOld ? "Status needs review" : "Recent scan observed";
  }
  function updateIssue(data) {
    const stamp = data.generated_utc || data.build_utc;
    $("edition-date").textContent = "RESEARCH SNAPSHOT · " + timeText(stamp, true);
    $("stat-selected").textContent = String(model.stories.length);
    $("stat-domains").textContent = String(Number(data.unique_domains_in_selection) || new Set(model.stories.map((s) => s.domain)).size);
    $("scan-status").textContent = collectorStatus(data);
    const age = Date.now() - Date.parse(stamp || "");
    if (Number.isFinite(age) && age > 24 * 3600000) {
      const notice = $("research-notice").querySelector("p");
      if (notice && !notice.dataset.ageWarning) {
        notice.append(document.createTextNode(" This snapshot is over 24 hours old; verify dates at the original sources."));
        notice.dataset.ageWarning = "true";
      }
    }
  }
  async function fetchFeed() {
    $("loading").hidden = false;
    $("error").hidden = true;
    try {
      const response = await fetch("./data/feed.json", { cache: "no-store" });
      if (!response.ok) throw new Error("Feed HTTP " + response.status);
      const data = await response.json();
      if (!data || !Array.isArray(data.stories)) throw new Error("No usable research feed");
      model.stories = data.stories.filter((s) => s && typeof s.id === "string" && typeof s.title === "string" && safeURL(s.url));
      model.morning = morningCut(model.stories);
      updateIssue(data);
      $("loading").hidden = true;
      render();
    } catch (_) {
      $("loading").hidden = true;
      $("error").hidden = false;
      $("results-label").textContent = "RESEARCH FEED UNAVAILABLE";
      $("featured").replaceChildren();
      $("stories-list").replaceChildren();
    }
  }
  document.addEventListener("click", (event) => {
    const save = event.target.closest("[data-save]");
    if (save) {
      const id = save.dataset.save;
      if (model.saved.has(id)) { model.saved.delete(id); showToast("Removed from saved stories"); }
      else { model.saved.add(id); showToast("Saved for later"); }
      storeSet(savedKey, model.saved);
      render();
      return;
    }
    const read = event.target.closest("[data-read]");
    if (read) {
      const id = read.dataset.read;
      if (model.read.has(id)) { model.read.delete(id); showToast("Marked unread"); }
      else { model.read.add(id); showToast("Marked read"); }
      storeSet(readKey, model.read);
      render();
      return;
    }
    const sector = event.target.closest("[data-category]");
    if (sector) {
      model.category = sector.dataset.category;
      model.shown = 9;
      render();
      return;
    }
    const tab = event.target.closest("[data-view]");
    if (tab) { setView(tab.dataset.view); return; }
    const full = event.target.closest("[data-switch-desk]");
    if (full) {
      event.preventDefault();
      setView("desk");
      $("edition").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  });
  $("open-all-stories").addEventListener("click", () => {
    setView("desk");
    $("edition").scrollIntoView({ behavior: "smooth" });
  });
  $("saved-filter").addEventListener("click", () => { model.savedOnly = !model.savedOnly; model.shown = 9; render(); });
  $("search").addEventListener("input", (event) => { model.search = event.target.value || ""; model.shown = 9; render(); });
  $("more").addEventListener("click", () => { model.shown += 9; render(); });
  $("retry").addEventListener("click", fetchFeed);
  model.saved = loadSet(savedKey);
  model.read = loadSet(readKey);
  if (window.location.hash === "#desk") model.view = "desk";
  fetchFeed();
})();
