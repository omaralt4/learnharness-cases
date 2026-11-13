// Rounds tools frontend: tool renderers for practice sessions, then the Cases page (further down).
//
// Draws the image returned by show_case_image. Click the image to switch between
// fit-to-width and full size (scroll sideways at full size to follow a rhythm strip).

const text = (doc, tag, value, style) => {
  const el = doc.createElement(tag);
  el.textContent = value;
  if (style) el.setAttribute("style", style);
  return el;
};

export function activate(ctx) {
  ctx.registerToolRenderer({
    toolName: "show_case_image",
    mount(container, tool) {
      const doc = container.ownerDocument;
      const muted = "font-size:12px;opacity:0.7;margin:4px 0;";

      if (tool.state === "output-error") {
        container.append(text(doc, "p", `Couldn't show the image: ${tool.errorText || "unknown error"}`, muted));
        return () => container.replaceChildren();
      }
      const out = tool.output;
      if (tool.state !== "output-available" || !out || typeof out.dataUrl !== "string" || !out.dataUrl.startsWith("data:image/")) {
        container.append(text(doc, "p", "Loading image…", muted));
        return () => container.replaceChildren();
      }

      const frame = doc.createElement("div");
      frame.setAttribute("style", "max-width:100%;overflow-x:auto;border:1px solid rgba(127,127,127,0.3);border-radius:8px;background:#fff;");
      const img = doc.createElement("img");
      img.src = out.dataUrl;
      img.alt = out.caption || "Case image";
      let full = false;
      const fit = () => img.setAttribute("style", `display:block;cursor:${full ? "zoom-out" : "zoom-in"};${full ? "max-width:none;" : "width:100%;height:auto;"}`);
      fit();
      img.addEventListener("click", () => { full = !full; fit(); });
      frame.append(img);

      container.append(frame, text(doc, "p", `${out.caption ? out.caption + " · " : ""}click to zoom`, muted));
      return () => container.replaceChildren();
    },
  });

  ctx.registerToolRenderer({
    toolName: "log_case_result",
    mount(container, tool) {
      const doc = container.ownerDocument;
      const muted = "font-size:12px;opacity:0.7;margin:4px 0;";
      if (tool.state === "output-error") {
        container.append(text(doc, "p", `Couldn't log this case: ${tool.errorText || "unknown error"}`, muted));
        return () => container.replaceChildren();
      }
      const out = tool.output;
      if (tool.state !== "output-available" || !out || !Array.isArray(out.decisions)) {
        container.append(text(doc, "p", "Logging case…", muted));
        return () => container.replaceChildren();
      }
      const box = doc.createElement("div");
      box.setAttribute("style", "border:1px solid var(--border, rgba(127,127,127,0.3));border-radius:8px;padding:10px 12px;font-size:13px;");
      const right = out.decisions.filter(d => d.verdict === "correct").length;
      const part = out.decisions.filter(d => d.verdict === "partial").length;
      let head = `Case logged · ${out.diagnosis || ""} · ${right}/${out.decisions.length} right`;
      if (part) head += `, ${part} partial`;
      if (out.exam_questions) head += ` · questions ${out.exam_questions.correct}/${out.exam_questions.total}`;
      box.append(text(doc, "div", head, "font-weight:600;margin-bottom:6px;"));
      const mark = { correct: "✓", partial: "~", wrong: "✗" };
      const list = doc.createElement("div");
      for (const d of out.decisions) list.append(text(doc, "div", `${mark[d.verdict] || "·"} ${d.point}`, "margin:2px 0;"));
      box.append(list);
      if (Array.isArray(out.weak_spots) && out.weak_spots.length) {
        box.append(text(doc, "div", "Review:", "margin-top:8px;font-weight:600;"));
        for (const w of out.weak_spots) box.append(text(doc, "div", `• ${w}`, "margin:2px 0;"));
      }
      container.append(box);
      return () => container.replaceChildren();
    },
  });

  registerCasesUi(ctx);
}

// ---------------------------------------------------------------------------------------------
// Cases page: make cases, see progress and review, edit the mix. All data comes from the backend
// (which runs pick_case.py). Spoiler rules: no case contents anywhere; topic names only for
// finished cases (Review), or in Progress behind a switch that is off every time the page opens.
// All text is inserted with textContent.
// ---------------------------------------------------------------------------------------------

const CASES_ICON =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="2" width="8" height="4" rx="1"/>' +
  '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>' +
  '<path d="M7.5 14H10l1.5-3 2 6 1.5-3h1.5"/></svg>';

const CASES_CSS = `
.rt-cases{max-width:860px;margin:0 auto;padding:20px 24px 56px;color:var(--foreground);font-size:14px;line-height:1.5}
.rt-cases *{box-sizing:border-box}
.rt-cases h2{font-size:15px;font-weight:600;margin:22px 0 8px}
.rt-cases p{margin:6px 0}
.rt-muted{color:var(--muted-foreground,inherit);opacity:.9;font-size:13px}
.rt-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;margin:10px 0}
.rt-systems{padding:10px 12px;border:1px solid var(--border);border-radius:8px}
.rt-check{display:inline-flex;align-items:center;gap:6px;cursor:pointer}
.rt-tabs{display:flex;flex-wrap:wrap;gap:4px;margin:16px 0 4px;border-bottom:1px solid var(--border)}
.rt-tab{font:inherit;color:inherit;background:none;border:0;border-bottom:2px solid transparent;padding:8px 12px;cursor:pointer;opacity:.7}
.rt-tab[aria-selected="true"]{opacity:1;border-bottom-color:var(--foreground);font-weight:600}
.rt-btn{font:inherit;color:var(--primary-foreground,var(--background));background:var(--primary,var(--foreground));border:1px solid transparent;border-radius:6px;padding:7px 14px;cursor:pointer}
.rt-btn.rt-quiet{color:inherit;background:transparent;border-color:var(--border)}
.rt-btn:disabled{opacity:.5;cursor:default}
.rt-cases :is(button,input,select,textarea):focus-visible{outline:2px solid var(--ring,var(--foreground));outline-offset:2px}
.rt-input{font:inherit;color:inherit;background:var(--background);border:1px solid var(--border);border-radius:6px;padding:6px 8px}
.rt-input.rt-num{width:84px}
.rt-input.rt-wide{flex:1 1 260px;min-width:0}
.rt-field{display:flex;flex-direction:column;gap:4px;margin:10px 0}
.rt-field>span{font-size:13px}
.rt-box{border:1px solid var(--border);border-radius:8px;padding:12px 14px;margin:12px 0}
.rt-ok{border-color:var(--lh-success,var(--border))}
.rt-error{border-color:var(--lh-error,var(--destructive,var(--border)));white-space:pre-wrap;overflow-wrap:anywhere}
.rt-warn{border-color:var(--lh-warning,var(--border))}
.rt-message{width:100%;min-height:64px;resize:vertical;font-family:var(--font-mono,monospace);font-size:12px}
.rt-table{width:100%;border-collapse:collapse;margin:8px 0}
.rt-table th,.rt-table td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:top}
.rt-table th{font-weight:600;font-size:13px}
.rt-table .rt-n{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.rt-bar{height:8px;border-radius:4px;background:var(--muted,rgba(127,127,127,.2));overflow:hidden;min-width:80px}
.rt-bar>i{display:block;height:100%;background:var(--foreground);opacity:.75}
.rt-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.rt-stat{border:1px solid var(--border);border-radius:8px;padding:10px 12px}
.rt-stat b{display:block;font-size:20px;font-weight:600;font-variant-numeric:tabular-nums}
.rt-mix{display:grid;grid-template-columns:minmax(150px,1.3fr) minmax(110px,2fr) 84px 56px;gap:8px 12px;align-items:center;margin:8px 0}
.rt-mix input[type=range]{width:100%}
.rt-mix .rt-n{text-align:right;font-variant-numeric:tabular-nums}
.rt-spot{margin:12px 0}
.rt-spot ul{margin:4px 0 0;padding-left:20px}
@media (max-width:560px){.rt-mix{grid-template-columns:1fr 84px 56px}.rt-mix input[type=range]{grid-column:1 / -1}}
`;

const percent = value => `${Math.round((Number(value) || 0) * 100)}%`;

function registerCasesUi(ctx) {
  ctx.registerView({ id: "cases", name: "Cases", mount: (container, signal) => mountCases(ctx, container, signal) });
  ctx.registerAction({ id: "open-cases", name: "Cases", icon: CASES_ICON, run: () => ctx.app.openView("cases") });
  ctx.placeAction({ id: "cases-sidebar", actionId: "open-cases", location: "sidebar" });
  ctx.registerSettings((container, signal) => mountCaseSettings(ctx, container, signal));
}

function domHelper(doc) {
  // h("div", {class, text, ...attributes, onclick}, ...children). Text always goes in as text.
  return (tag, props, ...kids) => {
    const el = doc.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = String(value);
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else if (key === "value") el.value = value;
      else if (key === "checked" || key === "disabled") el[key] = !!value;
      else el.setAttribute(key, value === true ? "" : String(value));
    }
    for (const kid of kids.flat()) if (kid !== undefined && kid !== null && kid !== false) el.append(kid);
    return el;
  };
}

function mountCases(ctx, container, signal) {
  const doc = container.ownerDocument;
  const win = doc.defaultView;
  const h = domHelper(doc);
  const STORE = "case-images:cases-page";
  const saved = (() => { try { return JSON.parse(win.localStorage.getItem(STORE)) || {}; } catch { return {}; } })();
  const remember = patch => { Object.assign(saved, patch); try { win.localStorage.setItem(STORE, JSON.stringify(saved)); } catch { /* private mode */ } };
  const errorText = e => (e instanceof Error ? e.message : String(e));
  const alive = () => !signal.aborted;

  const style = h("style");
  style.textContent = CASES_CSS;
  const banner = h("div");
  const systemsBox = h("div", { class: "rt-systems rt-row", role: "group", "aria-label": "Systems" });
  const tabBar = h("div", { class: "rt-tabs", role: "tablist" });
  const panel = h("div", { role: "tabpanel" });
  const root = h("div", { class: "rt-cases" }, banner, systemsBox, tabBar, panel);
  container.append(style, root);

  let config = null;
  let selected = new Set();
  let preparing = false;
  let tab = typeof saved.tab === "string" ? saved.tab : "new";
  let showTopics = false; // never remembered: off every time the page opens
  let lastMade = null;    // result of the last Make case / Fetch report, kept while the page is open

  const picked = () => [...selected];
  const errorBox = e => h("div", { class: "rt-box rt-error", role: "alert", text: errorText(e) });
  const button = (label, onclick, quiet) => h("button", { class: quiet ? "rt-btn rt-quiet" : "rt-btn", type: "button", text: label, onclick });

  async function copyText(textToCopy) {
    try { await win.navigator.clipboard.writeText(textToCopy); return true; } catch { /* fall through */ }
    try { await ctx.call("copy", { text: textToCopy }); return true; } catch { return false; }
  }

  // ----- header -----

  function renderBanner() {
    banner.replaceChildren();
    if (!config) return;
    const problems = [];
    if (!config.folderOk) problems.push(`pick_case.py is not in "${config.casesFolder}".`);
    if (!config.python) problems.push("Python wasn't found.");
    for (const w of config.warnings || []) problems.push(w);
    if (config.folderOk && !config.systems.length) problems.push("No topic lists were found in the topics folder.");
    if (!problems.length) return;
    const blocking = !config.folderOk || !config.python;
    banner.append(h("div", { class: `rt-box ${blocking ? "rt-error" : "rt-warn"}`, role: blocking ? "alert" : "status" },
      ...problems.map(p => h("p", { text: p })),
      h("div", { class: "rt-row" }, button("Open plugin settings", () => ctx.app.openSettings(), true))));
  }

  function renderSystems() {
    systemsBox.replaceChildren(h("strong", { text: "Systems" }));
    if (!config || !config.systems.length) { systemsBox.append(h("span", { class: "rt-muted", text: "none found" })); return; }
    for (const name of config.systems) {
      const box = h("input", { type: "checkbox", checked: selected.has(name), onchange: () => {
        if (box.checked) selected.add(name); else selected.delete(name);
        remember({ systems: picked() });
        if (tab === "progress" || tab === "review") renderTab();
      } });
      systemsBox.append(h("label", { class: "rt-check" }, box, h("span", { text: name })));
    }
    if (config.systems.length > 1) systemsBox.append(h("span", { class: "rt-muted", text: "Ticking several mixes their topics. The case won't say which system it came from." }));
  }

  const TABS = [["new", "New case"], ["report", "Case report"], ["progress", "Progress"], ["review", "Review"], ["mix", "Mix"], ["guidelines", "Guidelines"]];
  function renderTabs() {
    tabBar.replaceChildren(...TABS.map(([id, label]) => h("button", {
      class: "rt-tab", type: "button", role: "tab", "aria-selected": String(tab === id), text: label,
      onclick: () => { tab = id; remember({ tab }); renderTabs(); renderTab(); },
    })));
  }

  let renderToken = 0;
  function renderTab() {
    const token = ++renderToken;
    const current = () => alive() && token === renderToken;
    panel.replaceChildren();
    ({ new: tabNew, report: tabReport, progress: tabProgress, review: tabReview, mix: tabMix, guidelines: tabGuidelines }[tab] || tabNew)(current);
  }

  // ----- New case / Case report -----

  function madeBox(result) {
    const count = result.cases.length;
    const area = h("textarea", { class: "rt-input rt-message", readonly: true, "aria-label": "Opening message", value: result.message });
    const status = h("strong", { text: result.copied ? "Copied. Start a Practice session and paste." : "Couldn't reach the clipboard. Copy the message below and paste it into a Practice session." });
    const again = button("Copy again", async () => {
      status.textContent = (await copyText(result.message)) ? "Copied. Start a Practice session and paste." : "Couldn't reach the clipboard. Select the message below and copy it.";
    }, true);
    return h("div", { class: `rt-box ${result.copied ? "rt-ok" : "rt-warn"}`, role: "status" },
      h("p", {}, status),
      h("p", { class: "rt-muted", text: `${count} case${count === 1 ? "" : "s"} made${result.asked > count ? ` (asked for ${result.asked})` : ""}.` }),
      area,
      h("div", { class: "rt-row" }, again),
      ...(result.notes || []).map(n => h("p", { class: "rt-muted", text: n })));
  }

  function makerTab(current, { kind, intro, extraFields, collect, operation, actionLabel, busyLabel }) {
    const batch = h("input", { class: "rt-input rt-num", type: "number", min: 1, max: 10, step: 1, value: saved.batch || 1, "aria-label": "How many cases" });
    const go = button(actionLabel, run);
    const out = h("div", { "aria-live": "polite" });
    if (lastMade && lastMade.kind === kind) out.append(madeBox(lastMade));
    panel.append(h("p", { class: "rt-muted", text: intro }), ...(extraFields || []),
      h("div", { class: "rt-row" }, h("label", { class: "rt-check" }, h("span", { text: "How many" }), batch), go), out);
    if (preparing) { go.disabled = true; out.prepend(h("p", { class: "rt-muted", text: "Guidelines are being prepared. Cases can be made when that finishes." })); }

    async function run() {
      const asked = Math.min(10, Math.max(1, Math.round(Number(batch.value)) || 1));
      batch.value = asked;
      remember({ batch: asked });
      go.disabled = true;
      go.textContent = busyLabel;
      out.replaceChildren(h("p", { class: "rt-muted", text: "This can take up to a minute when an ECG or article has to be downloaded." }));
      try {
        const result = await ctx.call(operation, { systems: picked(), batch: asked, ...collect() });
        result.copied = await copyText(result.message);
        result.kind = kind;
        result.asked = asked;
        lastMade = result;
        if (current()) out.replaceChildren(madeBox(result));
      } catch (e) {
        if (current()) out.replaceChildren(errorBox(e));
      } finally {
        go.disabled = false;
        go.textContent = actionLabel;
      }
    }
  }

  function tabNew(current) {
    makerTab(current, {
      kind: "new", operation: "newCase", actionLabel: "Make case", busyLabel: "Making…",
      intro: "Picks a topic you haven't seen, or a weak one that is due, from the ticked systems. Nothing about the case is shown here.",
      collect: () => ({}),
    });
  }

  function tabReport(current) {
    const complaint = h("input", { class: "rt-input rt-wide", type: "text", maxlength: 200, value: saved.complaint || "", placeholder: "e.g. chest pain, syncope" });
    const journal = h("input", { class: "rt-input rt-wide", type: "text", maxlength: 80, value: saved.journal || "", placeholder: "e.g. Cureus" });
    const ed = h("input", { type: "checkbox", checked: !!saved.ed });
    makerTab(current, {
      kind: "report", operation: "caseReport", actionLabel: "Fetch case report", busyLabel: "Searching…",
      intro: "Fetches a real open-access case report from Europe PMC. Reports lean toward unusual cases.",
      extraFields: [
        h("label", { class: "rt-field" }, h("span", { text: "Complaint (optional; separate several with commas; empty = a random complaint from the ticked systems)" }), complaint),
        h("label", { class: "rt-field" }, h("span", { text: "Journal (optional)" }), journal),
        h("div", { class: "rt-row" }, h("label", { class: "rt-check" }, ed, h("span", { text: "Emergency department only" }))),
      ],
      collect: () => {
        remember({ complaint: complaint.value, journal: journal.value, ed: ed.checked });
        return { complaint: complaint.value, journal: journal.value, ed: ed.checked };
      },
    });
  }

  // ----- Progress -----

  function tabProgress(current) {
    const body = h("div", { "aria-live": "polite" }, h("p", { class: "rt-muted", text: "Loading…" }));
    const toggle = h("input", { type: "checkbox", checked: showTopics, onchange: () => { showTopics = toggle.checked; load(); } });
    panel.append(
      h("div", { class: "rt-row" }, button("Refresh", () => load(), true),
        h("label", { class: "rt-check" }, toggle, h("span", { text: "Show per-system counts and topic names (may spoil cases you haven't run)" }))),
      body);
    load();

    async function load() {
      if (!picked().length) { body.replaceChildren(h("p", { class: "rt-muted", text: "Tick at least one system." })); return; }
      try {
        const s = await ctx.call("status", { systems: picked(), showTopics });
        if (current()) body.replaceChildren(...draw(s));
      } catch (e) {
        if (current()) body.replaceChildren(errorBox(e));
      }
    }

    function draw(s) {
      const stat = (value, label) => h("div", { class: "rt-stat" }, h("b", { text: value }), h("span", { class: "rt-muted", text: label }));
      const share = s.topicsTotal ? s.topicsCovered / s.topicsTotal : 0;
      const out = [
        h("h2", { text: "Coverage" }),
        h("p", { text: `${s.topicsCovered} of ${s.topicsTotal} topics picked at least once (${percent(share)}).` }),
        h("div", { class: "rt-bar", role: "img", "aria-label": `${percent(share)} of topics covered` }, h("i", { style: `width:${Math.round(share * 100)}%` })),
        h("div", { class: "rt-stats" },
          stat(s.built, "built cases"), stat(s.reportsUsed, "case reports used"), stat(s.ecgsUsed, "ECGs used"),
          stat(s.casesFinished, "cases finished"), stat(s.casesWaiting, "made, not finished yet")),
        h("p", { class: "rt-muted", text: "A topic counts as covered when its case is made, not when you finish it." }),
      ];
      if (showTopics) {
        out.push(h("h2", { text: "By system" }));
        for (const sys of s.systems) {
          out.push(h("p", {}, h("strong", { text: sys.system }), doc.createTextNode(`: ${sys.topicsCovered} of ${sys.topicsTotal} topics, ${sys.built} built cases`)));
          if (sys.topics && sys.topics.length) {
            out.push(h("table", { class: "rt-table" }, h("tbody", {}, ...sys.topics.map(t => h("tr", {}, h("td", { class: "rt-n", text: `${t.count}×` }), h("td", { text: t.topic }))))));
          }
        }
      }
      out.push(h("h2", { text: "Encounter mix so far" }));
      const total = s.encounters.reduce((sum, e) => sum + e.count, 0);
      out.push(total
        ? h("table", { class: "rt-table" }, h("tbody", {}, ...s.encounters.map(e => h("tr", {},
            h("td", { text: e.label }),
            h("td", {}, h("div", { class: "rt-bar" }, h("i", { style: `width:${Math.round(100 * e.count / total)}%` }))),
            h("td", { class: "rt-n", text: `${e.count} (${Math.round(100 * e.count / total)}%)` })))))
        : h("p", { class: "rt-muted", text: "No cases made yet." }));
      out.push(h("h2", { text: "Guideline files" }));
      for (const sys of s.systems) {
        const clean = !sys.missing.length && !sys.unconverted.length && !sys.strays.length;
        out.push(h("p", {}, h("strong", { text: sys.system }), doc.createTextNode(clean ? ": all guideline PDFs are in place and converted." : ":")));
        if (sys.missing.length) {
          out.push(h("p", { text: `Missing from guidelines/${sys.system}/:` }),
            h("table", { class: "rt-table" }, h("tbody", {}, ...sys.missing.map(m => h("tr", {}, h("td", { text: m.file }), h("td", { text: m.guideline }))))));
        }
        if (sys.unconverted.length) out.push(h("p", { text: `Not converted to text yet (use the Guidelines tab): ${sys.unconverted.join(", ")}` }));
        if (sys.strays.length) out.push(h("p", { text: `PDFs with names the topic list doesn't use (rename them?): ${sys.strays.join(", ")}` }));
      }
      return out;
    }
  }

  // ----- Review -----

  function tabReview(current) {
    const body = h("div", { "aria-live": "polite" }, h("p", { class: "rt-muted", text: "Loading…" }));
    panel.append(h("div", { class: "rt-row" }, button("Refresh", () => load(), true),
      h("span", { class: "rt-muted", text: "Only finished cases appear here." })), body);
    load();

    async function load() {
      try {
        const r = await ctx.call("review", { systems: picked() });
        if (current()) body.replaceChildren(...draw(r));
      } catch (e) {
        if (current()) body.replaceChildren(errorBox(e));
      }
    }

    function draw(r) {
      if (!r.finished) return [h("p", { class: "rt-muted", text: "No finished cases logged yet. A case is logged at the end of its Practice session." })];
      const out = [
        h("p", { text: `${r.finished} finished case${r.finished === 1 ? "" : "s"} logged.` }),
        h("h2", { text: "Topics, weakest first" }),
        h("table", { class: "rt-table" },
          h("thead", {}, h("tr", {}, h("th", { text: "Topic" }), h("th", { class: "rt-n", text: "Cases" }), h("th", { class: "rt-n", text: "Last" }), h("th", { class: "rt-n", text: "Average" }))),
          h("tbody", {}, ...r.topics.map(t => h("tr", {},
            h("td", { text: t.topic }), h("td", { class: "rt-n", text: t.cases }), h("td", { class: "rt-n", text: percent(t.last) }), h("td", { class: "rt-n", text: percent(t.average) }))))),
        h("h2", { text: "Weak spots, most recent first" }),
      ];
      if (!r.weakSpots.length) out.push(h("p", { class: "rt-muted", text: "None logged in the recent cases." }));
      for (const w of r.weakSpots) {
        out.push(h("div", { class: "rt-spot" },
          h("strong", { text: [w.date, w.topic, w.diagnosis, percent(w.score)].filter(Boolean).join(" · ") }),
          h("ul", {}, ...w.spots.map(s => h("li", { text: s })))));
      }
      return out;
    }
  }

  // ----- Mix (scenarios.json) -----

  function tabMix(current) {
    const body = h("div", {}, h("p", { class: "rt-muted", text: "Loading…" }));
    panel.append(body);
    load();

    async function load() {
      try {
        const s = await ctx.call("getScenarios");
        if (current()) draw(s);
      } catch (e) {
        if (current()) body.replaceChildren(errorBox(e), h("div", { class: "rt-row" }, button("Reload", () => load(), true)));
      }
    }

    function draw(s) {
      const state = {
        encounters: Object.fromEntries(s.encounters.map(r => [r.key, Number(r.value) || 0])),
        extras: Object.fromEntries(s.extras.map(r => [r.key, Number(r.value) || 0])),
        review: { weak_below: Number(s.review.weak_below) || 0, after_days: Number(s.review.after_days) || 0, order: s.review.order },
      };
      const shares = {};
      const status = h("div", { "aria-live": "polite" });
      const save = button("Save", onSave);
      const refreshShares = () => {
        const total = Object.values(state.encounters).reduce((a, b) => a + b, 0);
        for (const [key, el] of Object.entries(shares)) el.textContent = total > 0 ? `${Math.round(100 * state.encounters[key] / total)}%` : "–";
        save.disabled = !(total > 0);
        if (!(total > 0)) status.replaceChildren(h("p", { class: "rt-muted", text: "At least one encounter needs a weight above 0." }));
        else if (status.dataset.kind !== "saved") status.replaceChildren();
      };
      // A slider and a number box that stay in step. Returns the two controls.
      const pair = (label, get, set, { min, max, step }) => {
        const clampTo = v => Math.min(max, Math.max(min, v));
        const range = h("input", { type: "range", min, max: Math.max(max, get()), step, value: get(), "aria-label": label });
        const number = h("input", { class: "rt-input rt-num", type: "number", min, max, step, value: get(), "aria-label": `${label}, exact value` });
        range.addEventListener("input", () => { set(Number(range.value)); number.value = range.value; changed(); });
        number.addEventListener("input", () => {
          const v = Number(number.value);
          if (number.value.trim() === "" || !Number.isFinite(v)) return;
          set(clampTo(v)); range.value = clampTo(v); changed();
        });
        number.addEventListener("blur", () => { number.value = get(); });
        return [range, number];
      };
      const changed = () => { delete status.dataset.kind; refreshShares(); };

      const encounterGrid = h("div", { class: "rt-mix" });
      for (const row of s.encounters) {
        shares[row.key] = h("span", { class: "rt-n", title: "Share of cases with the current weights" });
        encounterGrid.append(h("span", { text: row.label }),
          ...pair(row.label, () => state.encounters[row.key], v => { state.encounters[row.key] = v; }, { min: 0, max: Math.max(100, state.encounters[row.key]), step: 1 }),
          shares[row.key]);
      }
      const extrasGrid = h("div", { class: "rt-mix" });
      for (const row of s.extras) {
        const shown = h("span", { class: "rt-n", text: percent(state.extras[row.key]) });
        extrasGrid.append(h("span", { text: row.label }),
          ...pair(row.label, () => state.extras[row.key], v => { state.extras[row.key] = Math.round(v * 100) / 100; shown.textContent = percent(v); }, { min: 0, max: 1, step: 0.05 }),
          shown);
      }
      const weakShown = h("span", { class: "rt-n", text: percent(state.review.weak_below) });
      const days = h("input", { class: "rt-input rt-num", type: "number", min: 0, step: 0.5, value: state.review.after_days, "aria-label": "Review after days" });
      days.addEventListener("input", () => { const v = Number(days.value); if (days.value.trim() !== "" && Number.isFinite(v) && v >= 0) { state.review.after_days = v; changed(); } });
      const order = h("select", { class: "rt-input", "aria-label": "Order" },
        h("option", { value: "unseen_first", text: "Unseen topics first, then due reviews" }),
        h("option", { value: "review_first", text: "Due reviews first, then unseen topics" }));
      order.value = state.review.order === "review_first" ? "review_first" : "unseen_first";
      order.addEventListener("change", () => { state.review.order = order.value; changed(); });
      const reviewGrid = h("div", { class: "rt-mix" },
        h("span", { text: "A topic is weak below this score" }),
        ...pair("Weak below", () => state.review.weak_below, v => { state.review.weak_below = Math.round(v * 100) / 100; weakShown.textContent = percent(v); }, { min: 0, max: 1, step: 0.05 }),
        weakShown);

      body.replaceChildren(
        s.exists ? "" : h("p", { class: "rt-muted", text: "scenarios.json doesn't exist yet. These are the defaults; Save creates the file." }),
        h("h2", { text: "Encounters" }),
        h("p", { class: "rt-muted", text: "Weights are relative: a bigger number means more often, 0 switches one off. The last column is the share of cases each one gets." }),
        encounterGrid,
        h("h2", { text: "Extras" }),
        h("p", { class: "rt-muted", text: "Each is an independent chance per case, from 0 to 1 (0.25 = one case in four)." }),
        extrasGrid,
        h("h2", { text: "Review" }),
        reviewGrid,
        h("div", { class: "rt-row" }, h("label", { class: "rt-check" }, h("span", { text: "A weak topic comes back after this many days" }), days)),
        h("div", { class: "rt-row" }, h("label", { class: "rt-check" }, h("span", { text: "Order" }), order)),
        h("div", { class: "rt-row" }, save, button("Revert", () => load(), true)),
        status);
      refreshShares();

      async function onSave() {
        save.disabled = true;
        try {
          await ctx.call("saveScenarios", state);
          status.dataset.kind = "saved";
          if (current()) status.replaceChildren(h("div", { class: "rt-box rt-ok", role: "status", text: "Saved to scenarios.json. The next case uses these values." }));
        } catch (e) {
          delete status.dataset.kind;
          if (current()) status.replaceChildren(errorBox(e));
        } finally {
          save.disabled = false;
        }
      }
    }
  }

  // ----- Guidelines (prepare) -----

  function tabGuidelines(current) {
    const force = h("input", { type: "checkbox" });
    const go = button("Prepare guidelines", start);
    const body = h("div", { "aria-live": "polite" });
    panel.append(
      h("p", { class: "rt-muted", text: "Converts the guideline PDFs of the ticked systems to searchable text, so a case reads only the sections it needs. Run it once, and again after adding PDFs. Large guidelines take a few minutes each." }),
      h("div", { class: "rt-row" }, go, h("label", { class: "rt-check" }, force, h("span", { text: "Convert again even if already done" }))),
      body);
    ctx.call("prepareState").then(s => { if (current()) draw(s); }, e => { if (current()) body.replaceChildren(errorBox(e)); });
    drawPrepare = s => { if (current()) draw(s); };

    async function start() {
      try { draw(await ctx.call("prepareStart", { systems: picked(), force: force.checked })); } catch (e) { body.replaceChildren(errorBox(e)); }
    }

    function draw(s) {
      preparing = !!s.running;
      go.disabled = preparing;
      go.textContent = preparing ? "Preparing…" : "Prepare guidelines";
      if (s.running) { body.replaceChildren(h("p", { text: `Converting guidelines for ${(s.systems || []).join(", ")}. You can leave this page; it keeps going.` })); return; }
      if (s.error) { body.replaceChildren(errorBox(s.error)); return; }
      if (!s.files) { body.replaceChildren(); return; }
      const describe = f => {
        if (f.state === "converted") {
          let line = `Converted: ${f.pages} pages, ${Number(f.words).toLocaleString()} words, ${f.sections} sections indexed`;
          if (f.sections < 5) line += ". Few headings found, so the contents list will be thin";
          if (f.thin_pages && f.thin_pages.length) line += `. Little or no text on ${f.thin_pages.length} page${f.thin_pages.length === 1 ? "" : "s"} (usually figures)`;
          return line + ".";
        }
        if (f.state === "failed") return `Failed (${f.error}). Cases will use the guideline from the model's own knowledge.`;
        return "Already converted.";
      };
      body.replaceChildren(
        h("p", { text: `Converted ${s.converted} file${s.converted === 1 ? "" : "s"}.` }),
        h("table", { class: "rt-table" },
          h("thead", {}, h("tr", {}, h("th", { text: "System" }), h("th", { text: "File" }), h("th", { text: "Result" }))),
          h("tbody", {}, ...s.files.map(f => h("tr", {}, h("td", { text: f.system }), h("td", { text: f.file }), h("td", { text: describe(f) }))))),
        ...(s.notes || []).map(n => h("p", { class: "rt-muted", text: n })));
    }
  }

  let drawPrepare = null;
  const offNotification = ctx.onNotification(event => {
    if (event.topic !== "prepare" || !alive()) return;
    preparing = !!(event.data && event.data.running);
    if (tab === "guidelines" && drawPrepare) drawPrepare(event.data || {});
    else if (tab === "new" || tab === "report") renderTab();
  });

  // ----- start -----

  panel.append(h("p", { class: "rt-muted", text: "Loading…" }));
  Promise.all([ctx.call("getConfig"), ctx.call("prepareState").catch(() => ({}))]).then(([cfg, prep]) => {
    if (!alive()) return;
    config = cfg;
    preparing = !!prep.running;
    const remembered = Array.isArray(saved.systems) ? saved.systems.filter(s => cfg.systems.includes(s)) : [];
    selected = new Set(remembered.length ? remembered : cfg.systems);
    renderBanner();
    renderSystems();
    renderTabs();
    renderTab();
  }, e => { if (alive()) panel.replaceChildren(errorBox(e)); });

  return () => { offNotification(); container.replaceChildren(); };
}

// ----- plugin settings page: Cases folder and Python path -----

async function mountCaseSettings(ctx, container, signal) {
  const doc = container.ownerDocument;
  const h = domHelper(doc);
  const rowsHost = h("div");
  const status = h("div", { style: "font-size:13px;margin-top:12px;" });
  container.append(
    h("p", { style: "font-size:13px;opacity:0.8;margin:0 0 12px;", text:
      "Rounds tools shows case images (ECGs, films) inline in practice sessions, logs each finished case to case_log.jsonl, " +
      "and adds the Cases page in the sidebar. The Cases page runs pick_case.py from the cases folder with the Python below. No model calls." }),
    rowsHost, status);

  let config;
  try { config = await ctx.call("getConfig"); } catch (e) {
    status.textContent = e instanceof Error ? e.message : String(e);
    return () => container.replaceChildren();
  }
  if (signal.aborted) return;

  const describe = () => {
    const lines = [
      config.folderOk ? `Using cases folder: ${config.casesFolder}` : `pick_case.py is not in ${config.casesFolder}`,
      config.python ? `Using Python: ${config.python.path} (${config.python.version || "version unknown"}, found via ${config.python.source})` : "Python wasn't found. Give the full path to python.exe above.",
      ...config.warnings,
    ];
    status.replaceChildren(...lines.map(line => h("p", { style: "margin:4px 0;overflow-wrap:anywhere;", text: line })));
  };
  const rows = () => [
    {
      type: "text", key: "casesFolder", label: "Cases folder", value: config.casesFolderSetting,
      description: `The folder with pick_case.py, topics and cases. Leave empty for ${config.defaultFolder}`,
      onChange: async value => { config = await ctx.call("setConfig", { casesFolder: value }); handle.update({ rows: rows() }); describe(); },
    },
    {
      type: "text", key: "pythonPath", label: "Python path", value: config.pythonSetting,
      description: "Full path to python.exe. Leave empty to find it the way the .bat launchers do.",
      onChange: async value => { config = await ctx.call("setConfig", { pythonPath: value }); handle.update({ rows: rows() }); describe(); },
    },
  ];
  const handle = ctx.ui.mountSettingsRows(rowsHost, { rows: rows() }, { signal });
  describe();
  return () => { handle.dispose(); container.replaceChildren(); };
}
