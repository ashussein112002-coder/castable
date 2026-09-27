(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => (n == null ? "-" : Number(n).toLocaleString("en-US"));
  const pct = (n) => (n == null ? "-" : (Number(n) * 100).toFixed(1) + "%");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ts = (t) => (t == null ? "" : `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`);
  const compact = (n) => {
    if (n == null || isNaN(n)) return "-";
    const a = Math.abs(n);
    for (const [d, s] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) if (a >= d) { const x = n / d; return (x < 100 ? x.toFixed(1).replace(/\.0$/, "") : Math.round(x)) + s; }
    return String(Math.round(n));
  };
  const PLAT = { tiktok: "TikTok", instagram: "Instagram", youtube: "YouTube" };
  const FLAG = { competitor_mention: "Competitor", avoid_topic: "Avoid-list", drugs_vape: "Drugs / vape", gambling_scams: "Gambling / scams", weapons_violence: "Weapons", political_religious: "Political / religious", adult: "Adult", alcohol: "Alcohol", profanity: "Profanity" };
  const COMPS = ["relevance", "performance", "audience", "safety"];

  const EXAMPLES = [
    ["Luxury skincare · Dubai", "Luxury skincare launch in Dubai for a premium serum. Audience: women 22-35, Arabic and English speakers. Calm, premium tone, no discount-code creators. Competitors: La Mer, Estee Lauder, The Ordinary. Avoid: giveaways, casino, alcohol."],
    ["Modest fashion · Riyadh", "Modest fashion capsule collection launch in Riyadh for Ramadan. Audience: women 18-30, Arabic-first. Elegant, aspirational tone. Competitors: Shein, Zara. Avoid: political content."],
    ["Fitness app · UAE", "Fitness app launch in the UAE targeting men and women 20-35 who train in gyms. Energetic, authentic tone; micro creators with strong comments. Competitors: Nike Training Club, Fitness First. Avoid: supplements, steroids, vape."],
    ["Beauty · GCC (TikTok)", "Beauty brand entering the GCC with a foundation shade range for Middle Eastern skin tones. TikTok-first, GRWM formats, Arabic and English. Competitors: Huda Beauty, Fenty, Charlotte Tilbury."],
  ];
  // One-click demo: a complete brief that exercises every stage of the pipeline.
  const DEMO = {
    text: "Modest fashion brand in Dubai launching a Ramadan capsule; want micro creators who do try-on hauls and speak Arabic or English. Elegant, aspirational tone. Avoid: giveaways, alcohol.",
    brand: "Aurea", category: "fashion", region: "uae", band: "micro", competitors: "", days: 90,
  };

  let MODE = "mock";
  async function health() {
    try {
      const r = await fetch("/api/health").then((r) => r.json());
      MODE = r.mode || "mock";
      const cd = $("c_demo");
      if (cd) cd.textContent = MODE === "live" ? "Sample report" : "Try a demo";
      const led = r.ledger || {};
      let host = "";
      try { host = new URL(r.oriane_base_url).host; } catch (e) { host = r.oriane_base_url || ""; }
      const live = r.mode === "live";
      $("status").innerHTML = `<span class="pill mode ${esc(r.mode)}" title="${live ? "Reading real Instagram and TikTok videos through Oriane Connect" : "Sample data: bundled mock of the Oriane API"}">${live ? "LIVE · via Oriane" : "SAMPLE DATA"}</span>`;
      const sys = [`Oriane key ${r.oriane_key_present ? "✓" : "✗"}`];
      if (host && !/oriane\.xyz$/.test(host)) sys.push(`endpoint ${esc(host)}`);
      sys.push(`pitch writer ${esc(r.llm)}`, `credits used ${fmt(led.live_results_total)} results · ${fmt(led.live_calls)} calls`);
      window.__sys = sys.join(" · ");
      const b = r.budget || {};
      $("foot").textContent = `${window.__sys} · budget guard ≤${b.max_results_per_run} results/run · discovery ${b.discovery_limit} · vet top ${b.vet_top_k} × ${b.videos_per_creator} videos`;
    } catch (e) {
      $("status").innerHTML = `<span class="pill mode offline">server unreachable</span>`;
    }
  }

  async function regions() {
    const r = await fetch("/api/regions").then((r) => r.json());
    for (const sid of ["region", "c_region"]) {
      const sel = $(sid); if (!sel) continue;
      for (const reg of r.regions) {
        const o = document.createElement("option");
        o.value = reg.key; o.textContent = reg.label; if (reg.key === "uae") o.selected = true; sel.appendChild(o);
      }
    }
  }

  function examples() {
    const box = $("examples");
    for (const [label, text] of EXAMPLES) {
      const b = document.createElement("button"); b.type = "button"; b.textContent = label;
      b.onclick = () => { $("text").value = text; };
      box.appendChild(b);
    }
    $("demo").onclick = () => {
      $("text").value = DEMO.text; $("brand").value = DEMO.brand; $("category").value = DEMO.category;
      $("region").value = DEMO.region; $("band").value = DEMO.band; $("competitors").value = DEMO.competitors; $("days").value = DEMO.days;
      $("text").focus();
    };
  }

  async function recent() {
    try {
      const r = await fetch("/api/runs").then((r) => r.json());
      const all = (r.runs || []).filter((x) => x.status === "done");
      const when = (x) => (x.started ? new Date(x.started).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
      const runs = all.filter((x) => (x.kind || "brand") !== "creator");
      const sel = $("recent");
      sel.length = 1;
      for (const x of runs.slice(0, 20)) {
        const o = document.createElement("option");
        o.value = x.id; o.textContent = `${x.brand || x.category || "brief"} · ${x.region || ""} · ${x.shortlist ?? 0} creators · ${when(x)}`;
        sel.appendChild(o);
      }
      sel.hidden = runs.length === 0;
      const cruns = all.filter((x) => x.kind === "creator");
      const csel = $("c_recent");
      if (csel) {
        csel.length = 1;
        for (const x of cruns.slice(0, 20)) {
          const o = document.createElement("option");
          o.value = x.id; o.textContent = `@${x.handle || "?"} · ${x.region || ""} · ${when(x)}`;
          csel.appendChild(o);
        }
        csel.hidden = cruns.length === 0;
      }
    } catch (e) { /* optional */ }
  }

  function form() {
    const platforms = [];
    if ($("p_ig").checked) platforms.push("instagram");
    if ($("p_tt").checked) platforms.push("tiktok");
    return {
      text: $("text").value.trim(), brand: $("brand").value.trim(), category: $("category").value, region: $("region").value,
      platforms, follower_band: $("band").value, competitors: $("competitors").value, days_back: Number($("days").value || 90),
      image_url: $("image_url").value.trim(), use_llm: $("use_llm").checked,
    };
  }

  // ---- pipeline progress: light up the "How it works" steps from the run log
  function stage(run) {
    const log = (run.log || []).join("\n");
    if (run.status === "done") return 6;
    if (/LLM judgment/.test(log)) return 5;
    if (/vetting/.test(log)) return 4;
    if (/profiles:/.test(log)) return 3;
    if (/discovery/.test(log)) return 2;
    return run.status === "queued" ? 0 : 1;
  }
  function progress(n, done) {
    [...$("how").children].forEach((li, i) => {
      li.classList.toggle("done", i < n || (done && i === n - 1));
      li.classList.toggle("active", !done && i === n);
    });
  }

  function renderLog(lines) {
    if (!lines || !lines.length) return;
    $("log").innerHTML = lines.map((l) => {
      const m = /^(\[\s*[\d.]+s\])\s?(.*)$/.exec(l);
      const body = m ? m[2] : l;
      const cls = /error|failed|stopped|exhausted/i.test(body) ? "err" : /flags=\{/.test(body) ? "hit" : /flags=none|enriched|creators from/.test(body) ? "ok" : "";
      return `${m ? `<span class="t">${esc(m[1].replace(/\[\s+/, "["))}</span> ` : ""}<span class="${cls}">${esc(body)}</span>`;
    }).join("\n");
    $("log").scrollTop = $("log").scrollHeight;
  }

  let timer = null;
  async function start(e) {
    e.preventDefault();
    const f = form();
    if (f.text.length < 3) { $("text").focus(); return; }
    $("go").disabled = true; $("cards").innerHTML = ""; $("summary").textContent = ""; $("warn").innerHTML = ""; $("actions").hidden = true; $("resulthead").hidden = true;
    $("log").textContent = "Starting run…";
    progress(0, false);
    const r = await fetch("/api/scout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f) }).then((r) => r.json());
    poll(r.id);
  }

  function poll(id) {
    clearInterval(timer);
    const tick = async () => {
      const run = await fetch(`/api/runs/${id}`).then((r) => r.json());
      renderLog(run.log);
      progress(stage(run), run.status === "done");
      if (run.status === "done" || run.status === "error") {
        clearInterval(timer); $("go").disabled = false; render(run); health(); recent();
        try { history.replaceState(null, "", `?run=${encodeURIComponent(run.id)}`); } catch (e) { /* file:// etc. */ }
      }
    };
    timer = setInterval(tick, 900);
    tick();
  }

  // Restore the brief that produced a loaded run, so the page reads as one story.
  function fillForm(f) {
    if (!f) return;
    const set = (id, v) => { if (v != null && $(id)) $(id).value = v; };
    set("text", f.text); set("brand", f.brand); set("category", f.category); set("band", f.follower_band);
    set("competitors", f.competitors); set("days", f.days_back); set("image_url", f.image_url);
    if (f.region && [...$("region").options].some((o) => o.value === f.region)) $("region").value = f.region;
    if (Array.isArray(f.platforms)) { $("p_ig").checked = f.platforms.includes("instagram"); $("p_tt").checked = f.platforms.includes("tiktok"); }
    if (typeof f.use_llm === "boolean") $("use_llm").checked = f.use_llm;
  }

  async function load(id) {
    const res = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    if (!res.ok) { $("log").textContent = `Run ${id} not found.`; return; }
    const run = await res.json();
    fillForm(run.form);
    if (run.status === "done" || run.status === "error") {
      renderLog(run.log); progress(6, true); render(run);
      try { history.replaceState(null, "", `?run=${encodeURIComponent(run.id)}`); } catch (e) { /* ignore */ }
    } else {
      poll(id);
    }
  }

  function render(run) {
    $("warn").innerHTML = "";
    if (run.error) $("warn").innerHTML = `<div class="warn">${esc(run.error)}</div>`;
    for (const w of run.warnings || []) $("warn").innerHTML += `<div class="warn">${esc(w)}</div>`;
    $("summary").textContent = run.summary || "";
    $("resulthead").hidden = !run.summary;
    const list = run.shortlist || [];
    if (!list.length) {
      $("cards").innerHTML = `<div class="empty"><b>${run.status === "error" ? "Run failed" : "No creators matched"}</b><span>${run.status === "error" ? "See the run log above." : "Widen the region or simplify the brief."}</span></div>`;
      return;
    }
    $("dossier").href = `/dossier/${run.id}`; $("csv").href = `/dossier/${run.id}.csv`; $("json").href = `/api/runs/${run.id}`;
    $("actions").hidden = false; $("resulthead").hidden = false;
    $("cards").innerHTML = list.map((row, i) => card(row, i + 1, run.id)).join("");
  }

  function initials(name) {
    const w = String(name || "?").replace(/[._-]+/g, " ").trim().split(/\s+/);
    return ((w[0] || "?")[0] + (w[1] ? w[1][0] : "")).toUpperCase();
  }

  function card(row, rank, runId) {
    const c = row.candidate || {}, p = row.profile || {}, v = row.vetting, s = row.score || {}, j = row.judgment;
    const handle = c.handle || p.handle || "?";
    const platform = c.platform || p.platform || "";
    const url = platform === "tiktok" ? `https://www.tiktok.com/@${handle}` : `https://www.instagram.com/${handle}/`;
    const name = p.displayName || c.displayName || handle;
    const followers = p.followersCount ?? c.followers;
    const flags = (v && v.flags) || [];
    const comps = s.components || {}, w = s.weights || {};

    const avatar = `<span class="av" aria-hidden="true">${esc(initials(name))}${p.profilePictureUrl ? `<img src="${esc(p.profilePictureUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</span>`;

    const metrics = [
      `<span><b>${compact(followers)}</b> followers</span>`,
      c.matching_videos != null ? `<span><b>${c.matching_videos}</b> matching videos</span>` : "",
      c.er_views_mean != null ? `<span>ER / view <b>${pct(c.er_views_mean)}</b></span>` : "",
      v && v.sponsored_posts != null ? `<span><b>${v.sponsored_posts}</b> sponsored</span>` : "",
      v && v.cadence_per_week != null ? `<span><b>${v.cadence_per_week}</b> posts / wk</span>` : "",
      c.visual_best_rank ? `<span>visual match <b>#${c.visual_best_rank}</b></span>` : "",
    ].join("");

    let flagsHtml;
    if (!v) flagsHtml = `<span class="unvetted">Not vetted this run (outside top K): safety unknown</span>`;
    else if (!flags.length) flagsHtml = `<span class="clean">✓ No flags in ${v.videos_checked ?? "recent"} videos${v.window_days ? ` / ${v.window_days} days` : ""}</span>`;
    else flagsHtml = flags.slice(0, 3).map((f) => `<span class="fl ${esc(f.severity)}" title="${esc(f.quote || "")}"><b>${esc(FLAG[f.type] || f.type)}</b>${f.term ? ` · ${esc(f.term)}` : ""}${f.quote ? ` <q dir="auto">${esc(f.quote)}</q>` : ""}${f.t != null ? ` <span class="ts">@${ts(f.t)}</span>` : ""}</span>`).join("") + (flags.length > 3 ? `<span class="fl">+${flags.length - 3} more</span>` : "");

    const ev = (v && v.evidence_videos) || [];
    const quoteSrc = ev.find((e) => e.transcript_excerpt);
    const quote = quoteSrc ? `<p class="rc-quote" dir="auto">“${esc(quoteSrc.transcript_excerpt.length > 170 ? quoteSrc.transcript_excerpt.slice(0, 168) + "…" : quoteSrc.transcript_excerpt)}”${quoteSrc.views != null ? `<span class="ts" dir="ltr">${compact(quoteSrc.views)} views</span>` : ""}</p>` : "";
    const judgment = j && (j.fit_summary || j.recommended_angle) ? `<div class="rc-judg" dir="auto"><b>AI judgment</b> · ${esc(j.fit_summary || "")}${j.recommended_angle ? ` <em>Angle: ${esc(j.recommended_angle)}</em>` : ""}</div>` : "";
    const strip = ev.length ? `<div class="rc-strip">${ev.slice(0, 6).map((e) => `<a href="${esc(e.link || url)}" target="_blank" rel="noopener" title="${esc(e.caption || "")}"><span class="thumb">${e.thumbnail ? `<img src="${esc(e.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}<span>${compact(e.views)}</span></span></a>`).join("")}</div>` : "";

    const segs = COMPS.map((k) => (comps[k] != null && w[k] != null ? `<i class="seg-${k}" style="width:${(comps[k] * w[k]).toFixed(2)}%" title="${k} ${comps[k]} × ${w[k]}"></i>` : "")).join("");
    const vals = COMPS.map((k) => `<span><span><i class="seg-${k}"></i>${k[0].toUpperCase() + k.slice(1)}</span><b>${comps[k] != null ? Math.round(comps[k]) : "-"}${w[k] != null ? `<small> ×${w[k]}</small>` : ""}</b></span>`).join("");

    return `<article class="rc">
      <div class="rc-rank">${String(rank).padStart(2, "0")}</div>
      ${avatar}
      <div class="rc-main">
        <div class="rc-title"><a class="rc-name" href="${esc(url)}" target="_blank" rel="noopener" dir="auto">${esc(name)}</a>${p.isVerified ? `<span class="verified" title="Verified">✓</span>` : ""}${platform ? `<span class="plat ${esc(platform)}">${esc(PLAT[platform] || platform)}</span>` : ""}</div>
        <div class="rc-sub"><a href="${esc(url)}" target="_blank" rel="noopener">@${esc(handle)}</a>${p.locationCompleteAddress ? ` · ${esc(p.locationCompleteAddress)}` : ""}</div>
        <div class="rc-metrics">${metrics}</div>
        <div class="rc-flags">${flagsHtml}</div>
        ${quote}${judgment}${strip}
      </div>
      <div class="rc-score">
        <div class="sc-top"><div class="num">${s.total ?? "-"}<small>&thinsp;/100</small></div><span class="grade g-${esc(s.grade || "NA")}">${esc(s.grade || "–")}</span></div>
        <div class="bd">${segs}</div>
        <div class="bdvals">${vals}</div>
        ${s.caps && s.caps.length ? `<div class="caps">Capped: ${esc(s.caps.join("; "))}</div>` : ""}
        <a class="btn" href="/dossier/${esc(runId)}#c-${rank}" target="_blank" rel="noopener">View evidence ↗</a>
      </div>
    </article>`;
  }

  // ===================== creator mode =====================
  const C_STEPS = [
    ["profile:", "Found you on the index"],
    ["vetting:", "Reading your last videos"],
    ["topics:", "Learning what you talk about"],
    ["discovery", "Finding creators the algorithm puts next to you"],
    ["market:", "Scanning who sponsors them"],
    ["plan:", "Writing your pitches"],
  ];
  function setMode(mode) {
    for (const b of document.querySelectorAll(".modes [role=tab]")) {
      const on = b.dataset.mode === mode;
      b.setAttribute("aria-selected", on ? "true" : "false"); b.tabIndex = on ? 0 : -1;
    }
    for (const el of document.querySelectorAll("[data-for]")) el.hidden = el.dataset.for !== mode;
    $("mode-creator").hidden = mode !== "creator"; $("mode-brand").hidden = mode !== "brand";
    try { localStorage.setItem("castable.mode", mode); } catch (e) { /* private mode */ }
  }
  function cform() {
    const platforms = [];
    if ($("c_ig").checked) platforms.push("instagram");
    if ($("c_tt").checked) platforms.push("tiktok");
    return { handle: $("c_handle").value.trim().replace(/^@/, ""), platforms, region: $("c_region").value || "uae", niche: $("c_niche").value.trim(), use_llm: $("c_llm").checked };
  }
  function cSteps(run) {
    const log = (run.log || []).join("\n");
    const done = run.status === "done";
    let reached = -1;
    C_STEPS.forEach(([k], i) => { if (log.includes(k)) reached = i; });
    $("c_steps").innerHTML = C_STEPS.map(([, label], i) => {
      const st = done || i < reached ? "done" : i === reached ? "active" : "";
      return `<li class="${st}"><i></i><span>${esc(label)}${st === "active" ? "…" : ""}</span></li>`;
    }).join("");
    $("c_rawlog").hidden = !(run.log || []).length;
    $("c_log").innerHTML = (run.log || []).map((l) => esc(l)).join("\n");
  }
  let ctimer = null, cstart = 0;
  async function cStart(e) {
    e.preventDefault();
    const f = cform();
    if (!/^[A-Za-z0-9._]{2,64}$/.test(f.handle)) { $("c_handle").focus(); $("c_warn").innerHTML = `<div class="warn">Type your handle: letters, digits, dots or underscores (2–64 characters).</div>`; return; }
    if (!f.platforms.length) { $("c_warn").innerHTML = `<div class="warn">Pick at least one platform.</div>`; return; }
    $("c_go").disabled = true; $("c_warn").innerHTML = ""; $("c_result").innerHTML = `<div class="empty"><b>Working on @${esc(f.handle)}</b><span>This takes about a minute. Every number you get links to a video.</span></div>`;
    cSteps({ log: [], status: "queued" });
    let r;
    try {
      const res = await fetch("/api/creator", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f) });
      r = await res.json();
      if (!res.ok) throw new Error(res.status === 429 ? (r.detail || "Too many checks, try again in a minute.") : (Array.isArray(r.detail) ? r.detail.map((d) => d.msg).join("; ") : (r.detail || `HTTP ${res.status}`)));
    } catch (err) { $("c_go").disabled = false; $("c_warn").innerHTML = `<div class="warn">${esc(err.message)}</div>`; return; }
    cPoll(r.id);
  }
  function cPoll(id) {
    clearInterval(ctimer); cstart = Date.now();
    let every = 2000;
    const tick = async () => {
      let run;
      try { run = await fetch(`/api/runs/${id}`).then((r) => r.json()); } catch (e) { return; }
      cSteps(run);
      if (run.status === "done" || run.status === "error") {
        clearInterval(ctimer); $("c_go").disabled = false; cRender(run); health(); recent();
        try { history.replaceState(null, "", `?run=${encodeURIComponent(run.id)}`); } catch (e) { /* ignore */ }
      } else if (Date.now() - cstart > 8 * 60 * 1000) {
        clearInterval(ctimer); $("c_go").disabled = false;
        $("c_result").innerHTML = `<div class="empty"><b>Still working</b><span>Oriane is taking longer than usual. <a href="/?run=${esc(id)}">Reopen this check</a> in a minute.</span></div>`;
      }
    };
    ctimer = setInterval(tick, every);
    tick();
  }
  function cRender(run) {
    const rep = run.report || {};
    if (run.status === "error" || rep.error || !rep.score) {
      const msg = run.error || rep.error || "The report could not be completed.";
      const notIndexed = /not indexed|no recent videos/i.test(msg);
      $("c_result").innerHTML = `<div class="empty err"><b>${notIndexed ? "We couldn't find that handle" : "That didn't work"}</b><span>${esc(msg)}${notIndexed ? " Oriane indexes public Instagram and TikTok creators; check the spelling and the platform toggles, then try again." : ""}</span><button type="button" class="btn amber" id="c_retry">Try again</button></div>`;
      $("c_retry").onclick = () => $("c_go").click();
      return;
    }
    const p = rep.profile || {}, sc = rep.score || {}, plan = rep.plan || {}, bench = rep.benchmark || {}, me = rep.self_audit || {};
    const fixes = (plan.fix_before_pitching || []).length;
    const brands = (rep.market || []).length;
    const erp = bench.er_percentile;
    const comps = sc.components || {}, w = sc.weights || {};
    const segs = ["consistency", "engagement", "safety", "market_fit"].map((k) => (comps[k] != null && w[k] != null ? `<i class="seg-${k}" style="width:${(comps[k] * w[k]).toFixed(2)}%" title="${k} ${comps[k]} × ${w[k]}"></i>` : "")).join("");
    $("c_result").innerHTML = `<article class="cres">
      <div class="cres-top">
        <span class="av big">${esc(initials(p.displayName || p.handle))}${p.profilePictureUrl ? `<img src="${esc(p.profilePictureUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</span>
        <div class="cres-id"><div class="cres-handle">@${esc(p.handle || rep.handle)}</div><div class="rc-sub">${esc(PLAT[p.platform] || p.platform || "")} · ${compact(p.followersCount)} followers${p.isVerified ? " · verified" : ""}</div></div>
        <div class="cres-score"><div class="num">${sc.total ?? "-"}<small>&thinsp;/100</small></div><span class="grade g-${esc(sc.grade || "NA")}">${esc(sc.grade || "–")}</span></div>
      </div>
      <div class="bd">${segs}</div>
      <p class="summary" dir="auto">${esc(run.summary || "")}</p>
      <div class="facts">
        <div><b>${brands}</b><span>brands buying from creators like you</span></div>
        <div><b>${fixes}</b><span>things to fix before you pitch</span></div>
        <div><b>${erp != null ? "top " + Math.max(1, 100 - Math.round(erp)) + "%" : "–"}</b><span>engagement vs ${bench.peers ?? 0} peers</span></div>
      </div>
      ${plan.media_kit_line ? `<blockquote class="mk" dir="auto">“${esc(plan.media_kit_line)}”</blockquote>` : ""}
      <div class="actions">
        <a class="btn amber" href="/report/${esc(run.id)}" target="_blank" rel="noopener">Open my report ↗</a>
        <a class="btn" href="/api/runs/${esc(run.id)}" target="_blank" rel="noopener">Raw JSON</a>
        <span class="pill mode ${esc(run.mode || "")}">${esc((run.mode || "").toUpperCase())}</span>
      </div>
    </article>`;
  }
  async function cLoad(id, run) {
    if (!run) {
      const res = await fetch(`/api/runs/${encodeURIComponent(id)}`);
      if (!res.ok) return;
      run = await res.json();
    }
    setMode("creator");
    const f = run.form || {};
    if (f.handle) $("c_handle").value = f.handle;
    if (Array.isArray(f.platforms)) { $("c_ig").checked = f.platforms.includes("instagram"); $("c_tt").checked = f.platforms.includes("tiktok"); }
    if (f.region && [...$("c_region").options].some((o) => o.value === f.region)) $("c_region").value = f.region;
    if (f.niche) $("c_niche").value = f.niche;
    if (run.status === "done" || run.status === "error") { cSteps(run); cRender(run); } else { cPoll(id); }
  }
  async function loadAny(id) {
    const res = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    if (!res.ok) { $("log").textContent = `Run ${id} not found.`; return; }
    const run = await res.json();
    if (run.kind === "creator" || (run.form || {}).kind === "creator") return cLoad(id, run);
    setMode("brand"); fillForm(run.form);
    if (run.status === "done" || run.status === "error") { renderLog(run.log); progress(6, true); render(run); } else { poll(id); }
  }

  for (const b of document.querySelectorAll(".modes [role=tab]")) b.addEventListener("click", () => setMode(b.dataset.mode));
  $("cform").addEventListener("submit", cStart);
  $("c_demo").onclick = () => {
    if (MODE === "live") { window.open("/demo", "_blank", "noopener"); $("c_handle").focus(); return; }
    $("c_handle").value = "rania.skincare38.demo"; $("c_ig").checked = true; $("c_tt").checked = false; $("c_region").value = "dubai"; $("c_niche").value = "skincare routines and reviews"; $("c_handle").focus();
  };
  $("c_recent").addEventListener("change", (e) => { if (e.target.value) cLoad(e.target.value); });
  $("form").addEventListener("submit", start);
  $("recent").addEventListener("change", (e) => { if (e.target.value) load(e.target.value); });
  let savedMode = "creator";
  try { savedMode = localStorage.getItem("castable.mode") || "creator"; } catch (e) { /* ignore */ }
  setMode(savedMode);
  health(); examples(); recent();
  const qid = new URLSearchParams(location.search).get("run");
  regions().catch(() => {}).then(() => { if (qid) loadAny(qid); });
})();
