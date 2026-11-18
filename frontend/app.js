/* EnergyBrew research preview. This interface never claims editorial approval. */
(function () {
  "use strict";
  const categories = ["Natural Gas & LNG", "Power & Electricity", "Oil & Energy", "Infrastructure & Investment"];
  const labels = {"Natural Gas & LNG":"NATURAL GAS & LNG","Power & Electricity":"POWER & ELECTRICITY","Oil & Energy":"OIL & ENERGY","Infrastructure & Investment":"INFRASTRUCTURE & INVESTMENT"};
  const originLabels = {official_rss:"Official publisher feed",regulatory_notice:"Regulatory notice",global_discovery:"Global discovery lead",company_announcement:"Company announcement"};
  const dateLabels = {official_rss:"Publisher feed date",regulatory_notice:"Regulatory publication date",global_discovery:"First indexed",company_announcement:"Release feed date"};
  const key = "energybrew.saved.v1";
  const view = {stories:[],category:"All",query:"",savedOnly:false,limit:9,saved:new Set()};
  const byId = id => document.getElementById(id);
  function element(tag,className,text) { const e=document.createElement(tag);if(className)e.className=className;if(text!==undefined&&text!==null)e.textContent=String(text);return e; }
  function secureUrl(raw) {try {const url=new URL(raw);return url.protocol==="https:"||url.protocol==="http:" ? url.href : null;} catch (_) {return null;}}
  function dateText(value,withTime) {
    if(!value) return "Date unavailable";
    const date=new Date(value);if(!Number.isFinite(date.getTime()))return "Date unavailable";
    return new Intl.DateTimeFormat("en-US",{timeZone:"UTC",year:"numeric",month:"short",day:"numeric",...(withTime?{hour:"2-digit",minute:"2-digit",hour12:false}:{})}).format(date)+(withTime?" UTC":"");
  }
  function timeBasis(story) {return (dateLabels[story.origin]||"Observed")+" · "+dateText(story.observed_time_utc);}
  function sourceLink(story,text,className) {const a=element("a",className||"source-link",text);a.href=secureUrl(story.url)||"#";a.target="_blank";a.rel="noopener noreferrer";a.setAttribute("aria-label",text+" (external source)");return a;}
  function savedButton(story) {const isSaved=view.saved.has(story.id);const b=element("button","save-btn",isSaved?"★ Saved":"☆ Save");b.type="button";b.dataset.save=story.id;b.setAttribute("aria-pressed",String(isSaved));b.setAttribute("aria-label",isSaved?"Remove saved story":"Save story");return b;}
  function featured(story) {
    const article=element("article","lead");
    article.append(element("div","lead-eyebrow","FEATURED RESEARCH LEAD · "+(labels[story.category]||"ENERGY")));
    const title=element("h3");title.append(sourceLink(story,story.title,""));article.append(title);
    const source=element("div","lead-source");source.append(element("span","origin-tag",originLabels[story.origin]||"Research lead"),element("span","",story.source||story.domain||"Original source"));article.append(source);
    const bottom=element("div","lead-bottom");bottom.append(element("span","",timeBasis(story)));
    const controls=element("div");controls.append(sourceLink(story,"Original source ↗"),savedButton(story));bottom.append(controls);article.append(bottom);
    return article;
  }
  function storyCard(story,index) {
    const article=element("article","article");article.append(element("div","number",String(index).padStart(2,"0")));
    const content=element("div");
    content.append(element("div","article-category",labels[story.category]||"ENERGY"));
    const h3=element("h3");h3.append(sourceLink(story,story.title,""));content.append(h3);
    const meta=element("div","article-meta");meta.append(element("span","",story.source||story.domain||"Source"),element("span","","·"),element("span","",timeBasis(story)));content.append(meta);
    const controls=element("div","article-controls");
    controls.append(element("span","origin-tag",originLabels[story.origin]||"Research lead"),sourceLink(story,"Read at source ↗"),savedButton(story));
    if(Array.isArray(story.needs_editor_review)&&story.needs_editor_review.length)controls.append(element("span","review-flag","Needs additional review"));
    content.append(controls);article.append(content);return article;
  }
  function matches() {const q=view.query.trim().toLowerCase();return view.stories.filter(s=>{
    const themes=Array.isArray(s.coverage_themes)?s.coverage_themes:[s.category];
    if(view.category!=="All"&&!themes.includes(view.category))return false;
    if(view.savedOnly&&!view.saved.has(s.id))return false;
    if(q&&![s.title,s.source,s.domain,s.category].join(" ").toLowerCase().includes(q))return false;
    return true;
  });}
  function render() {
    const saveToggle=byId("saved-filter");saveToggle.textContent=(view.savedOnly?"★":"☆")+" Saved ("+view.saved.size+")";saveToggle.setAttribute("aria-pressed",String(view.savedOnly));
    document.querySelectorAll("[data-category]").forEach(b=>{const selected=b.dataset.category===view.category;b.classList.toggle("active",selected);b.setAttribute("aria-pressed",String(selected));});
    const filtered=matches();byId("result-count").textContent=filtered.length+" RESEARCH "+(filtered.length===1?"LEAD":"LEADS");
    const lead=byId("featured"),list=byId("stories-list");lead.replaceChildren();list.replaceChildren();
    if(!filtered.length){const empty=element("div","feed-state");empty.append(element("strong","",view.stories.length?"No stories match this view":"No qualifying research stories yet"),element("p","",view.stories.length?"Try another category, search, or saved filter.":"Check the next collector scan."));list.append(empty);}
    else{const visible=filtered.slice(0,view.limit);const showFeature=view.category==="All"&&!view.query&&!view.savedOnly;
      if(showFeature){lead.append(featured(visible[0]));visible.slice(1).forEach((s,i)=>list.append(storyCard(s,i+2)));}
      else visible.forEach((s,i)=>list.append(storyCard(s,i+1)));
    }
    byId("more").hidden=filtered.length<=view.limit;
  }
  function renderCoverage(data){
    const counts=data.selected_topic_coverage_counts||{};
    const maximum=Math.max(1,...categories.map(c=>Number(counts[c])||0));const container=byId("coverage-bars");container.replaceChildren();
    categories.forEach((category)=>{
      const count=Math.max(0,Number(counts[category])||0),box=element("div","coverage-item"),label=element("div","coverage-label");
      label.append(element("span","",category),element("strong","",count));
      const track=element("div","bar-track"),fill=element("div","bar-fill");fill.style.width=count/maximum*100+"%";track.append(fill);box.append(label,track);container.append(box);
    });
  }
  function renderMetrics(data) {
    byId("total-links").textContent=String(Number(data.unique_relevant_urls_7d)||0);
    byId("selected").textContent=String(data.stories.length);
    byId("domains").textContent=String(Number(data.unique_domains_in_selection)||new Set(data.stories.map(s=>s.domain)).size);
    renderCoverage(data);
    const stamp=dateText(data.generated_utc||data.build_utc,true);byId("edition-date").textContent="Desk refreshed "+stamp;byId("top-date").textContent="RESEARCH EDITION · "+stamp;
    const metrics=data.metrics||{},timestamps=[metrics.latest_official_scan_utc,metrics.latest_gal_sample_utc].filter(Boolean).map(d=>new Date(d).getTime()).filter(Number.isFinite);
    const age=timestamps.length?(Date.now()-Math.max(...timestamps))/60000:Infinity;
    const latestOfficial=metrics.latest_official_scan_utc?new Date(metrics.latest_official_scan_utc).getTime():NaN;
    const lastOfficialHours=(Date.now()-latestOfficial)/3600000;
    const stale=!Number.isFinite(age)||age>60||!Number.isFinite(lastOfficialHours)||lastOfficialHours>12||(metrics.warnings||[]).some(s=>/missing|older than|sampling gap/i.test(s));
    byId("scan-pill").classList.toggle("warning",stale);
    byId("scan-status").textContent=stale?"Collector status needs review":"Recent collector activity";
  }
  function toast(message){const n=byId("toast");n.textContent=message;n.classList.add("visible");clearTimeout(toast.timer);toast.timer=setTimeout(()=>n.classList.remove("visible"),2000);}
  function loadSaved(){try{const a=JSON.parse(localStorage.getItem(key)||"[]");if(Array.isArray(a))view.saved=new Set(a.filter(x=>typeof x==="string").slice(0,300));}catch(_){view.saved=new Set();}}
  function persist(){try{localStorage.setItem(key,JSON.stringify([...view.saved]));}catch(_){}}
  async function load(){
    byId("loading").hidden=false;byId("error").hidden=true;
    try{const response=await fetch("./data/feed.json",{cache:"no-store"});if(!response.ok)throw new Error("HTTP "+response.status);
      const data=await response.json();if(!data||!Array.isArray(data.stories))throw new Error("Bad feed");
      view.stories=data.stories.filter(s=>s&&s.id&&s.title&&secureUrl(s.url));
      byId("loading").hidden=true;renderMetrics(data);render();
    }catch(_){byId("loading").hidden=true;byId("error").hidden=false;byId("result-count").textContent="RESEARCH FEED UNAVAILABLE";byId("scan-pill").classList.add("warning");byId("scan-status").textContent="Feed unavailable";}
  }
  document.addEventListener("click",event=>{
    const save=event.target.closest("[data-save]");if(save){if(view.saved.has(save.dataset.save)){view.saved.delete(save.dataset.save);toast("Removed from saved stories");}else{view.saved.add(save.dataset.save);toast("Saved for later");}persist();render();return;}
    const tab=event.target.closest("[data-category]");if(tab){view.category=tab.dataset.category;view.limit=9;render();}
  });
  byId("saved-filter").addEventListener("click",()=>{view.savedOnly=!view.savedOnly;view.limit=9;render();});
  byId("search").addEventListener("input",event=>{view.query=event.target.value||"";view.limit=9;render();});
  byId("more").addEventListener("click",()=>{view.limit+=9;render();});
  byId("retry").addEventListener("click",load);
  loadSaved();load();
})();
