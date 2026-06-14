"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let _currentPdf    = null;
let _currentIframe = null;
let _noteData      = [];
let _currentNote   = null;
let _currentCard   = null;
let _corpus        = [];
let _crMd          = "";
let _activeRuleset = null;   // {id, label} of the active ruleset

// ── Init — stream PDF list with per-file progress ─────────────────────────────
async function init() {
  // Load available rulesets and populate the selector
  fetch("/api/rulesets").then(r => r.json()).then(data => {
    _activeRuleset = {id: data.active, label: ""};
    const sel = document.getElementById("ruleset-select");
    if (sel) {
      sel.innerHTML = "";
      (data.rulesets || []).forEach(rs => {
        const opt = document.createElement("option");
        opt.value = rs.id;
        opt.textContent = rs.label;
        if (rs.id === data.active) { opt.selected = true; _activeRuleset.label = rs.label; }
        sel.appendChild(opt);
      });
    }
    // Update sub-label
    const sub = document.getElementById("source-label");
    if (sub && _activeRuleset.label) sub.textContent = _activeRuleset.label;
  });

  // Load corpus in parallel while streaming PDFs
  fetch("/api/regression/corpus").then(r => r.json()).then(c => {
    _corpus = c;
    updateCorpusCount();
  });

  const list = document.getElementById("pdf-list");

  // Show shimmer placeholders while the first events arrive
  function addShimmer() {
    const s = document.createElement("div");
    s.className = "pdf-shimmer";
    s.innerHTML = `<div class="shimmer-line"></div><div class="shimmer-line short"></div>`;
    list.appendChild(s);
    return s;
  }
  const shimmers = [addShimmer(), addShimmer(), addShimmer()];

  const es = new EventSource("/api/pdfs/stream");

  es.addEventListener("start", e => {
    const d = JSON.parse(e.data);
    document.getElementById("source-label").textContent = "Source: " + d.source_dir;
    // Remove extra shimmers if we have fewer PDFs than placeholders
    while (shimmers.length > d.total && shimmers.length > 0) {
      const s = shimmers.pop();
      s.remove();
    }
  });

  es.addEventListener("pdf", e => {
    const d = JSON.parse(e.data);

    // Replace next shimmer with real item (or append if none left)
    const shimmer = shimmers.shift();
    const el = document.createElement("div");
    el.className = "pdf-item";
    el.dataset.name = d.name;
    el.innerHTML = `
      <div class="pdf-name">${escHtml(d.name)}</div>
      <div class="pdf-meta">${d.note_count} note${d.note_count !== 1 ? "s" : ""}</div>
      <div class="pdf-scan-bar"><div class="pdf-scan-fill" style="width:100%"></div></div>`;
    el.addEventListener("click", () => selectPdf(d.name, el));

    if (shimmer) {
      list.replaceChild(el, shimmer);
    } else {
      list.appendChild(el);
    }

    // Fade out the scan bar after a moment
    setTimeout(() => {
      const bar = el.querySelector(".pdf-scan-bar");
      if (bar) bar.style.opacity = "0";
    }, 600);
  });

  es.addEventListener("done", () => {
    // Remove any leftover shimmers (edge case: source_dir is empty)
    shimmers.forEach(s => s.remove());
    shimmers.length = 0;
    es.close();
  });

  es.onerror = () => {
    shimmers.forEach(s => s.remove());
    es.close();
  };
}

// ── PDF selection — stream evaluation with live progress ──────────────────────
let _evalEs = null;  // active EventSource for evaluation

function selectPdf(name, el) {
  if (_currentPdf === name) return;

  // Cancel any in-flight evaluation
  if (_evalEs) { _evalEs.close(); _evalEs = null; }

  _currentPdf = name;
  _noteData   = [];
  document.querySelectorAll(".pdf-item").forEach(e => e.classList.remove("active"));
  el.classList.add("active");
  loadPdfViewer(name, 1);

  const pane       = document.getElementById("results-pane");
  const evalProg   = document.getElementById("eval-progress");
  const evalBar    = document.getElementById("eval-bar");
  const statusText = document.getElementById("eval-status-text");
  const llmInd     = document.getElementById("llm-indicator");

  pane.innerHTML   = "";
  pane.scrollTop   = 0;
  document.getElementById("right-header").textContent = "Evaluating…";
  document.getElementById("spinner").style.display = "none";
  evalProg.style.display  = "block";
  evalBar.style.width     = "0%";
  statusText.textContent  = "Opening PDF…";
  llmInd.classList.remove("active");

  // Per-note state: noteAccordions[ni] = {el, inner, cardCount, totalChecks}
  const noteAccordions = {};
  // Accumulated full note objects keyed by note_index
  const noteObjects    = {};
  let totalChecks      = 49;  // will be updated from 'init' event
  let totalNotes       = 1;
  let checksCompleted  = 0;
  let llmActive        = 0;

  function updateBar() {
    const pct = totalChecks > 0 ? Math.min(100, (checksCompleted / (totalNotes * totalChecks)) * 100) : 0;
    evalBar.style.width = pct + "%";
  }

  _evalEs = new EventSource(`/api/evaluate/stream?pdf=${encodeURIComponent(name)}`);

  _evalEs.addEventListener("init", e => {
    const d = JSON.parse(e.data);
    totalNotes  = d.total_notes;
    totalChecks = d.total_checks;
    statusText.textContent = `Found ${totalNotes} note${totalNotes !== 1 ? "s" : ""}…`;
  });

  _evalEs.addEventListener("note_start", e => {
    const d   = JSON.parse(e.data);
    const ni  = d.note_index;
    const accId = `acc-${ni}`;

    // Create accordion shell immediately so cards can populate into it
    const acc = document.createElement("div");
    acc.className = "accordion";
    acc.id        = accId;

    const hdr = document.createElement("div");
    hdr.className = "acc-header streaming";
    const typeLabel = (d.note_type || "note").replace(/_/g, " ");
    hdr.innerHTML = `
      <span class="chevron">▶</span>
      <span class="acc-note-label">Note ${ni+1}: ${escHtml(typeLabel)} · ${escHtml(d.member||"…")} · ${escHtml(d.service_date||"…")}</span>
      <span class="acc-summary"></span>
      <span class="acc-progress"><span class="acc-progress-fill" id="np-${ni}"></span></span>`;
    hdr.addEventListener("click", () => toggleAccordion(accId, d.first_page));
    acc.appendChild(hdr);

    const body  = document.createElement("div");
    body.className = "acc-body";
    const inner = document.createElement("div");
    inner.className = "acc-body-inner";
    body.appendChild(inner);
    acc.appendChild(body);
    pane.appendChild(acc);

    // First note auto-opens
    if (ni === 0) {
      acc.classList.add("open");
      jumpToPage(d.first_page);
    }

    noteAccordions[ni] = { el: acc, inner, hdr, cardCount: 0, totalChecks: d.total_checks };
    noteObjects[ni]    = { note_index: ni, note_type: d.note_type, member: d.member,
                           service_date: d.service_date, first_page: d.first_page,
                           section_keys: [], header: {}, cards: [] };

    statusText.textContent = `Note ${ni+1}/${totalNotes}: ${escHtml(typeLabel)}`;
  });

  _evalEs.addEventListener("judge_start", e => {
    llmActive++;
    if (llmActive > 0) llmInd.classList.add("active");
  });

  _evalEs.addEventListener("judge_done", e => {
    llmActive = Math.max(0, llmActive - 1);
    if (llmActive === 0) llmInd.classList.remove("active");
  });

  _evalEs.addEventListener("check_done", e => {
    const d   = JSON.parse(e.data);
    const ni  = d.note_index;
    const card = d.card;
    const acc  = noteAccordions[ni];
    if (!acc) return;

    // Append the card to the note's inner div
    const isNA      = card.applicability === null;
    const isSkipped = card.verdict === "skipped";
    const div  = document.createElement("div");
    div.className = "card" + (isNA ? " na" : isSkipped ? " skipped" : "");
    if (card.payer_text) div.title = card.payer_text;
    div.innerHTML = `
      <div class="card-top">
        <span class="card-id">${card.standard_id}</span>
        ${verdictBadge(card.verdict)}
        <span class="card-title">${escHtml(card.title)}</span>
      </div>
      <div class="card-rationale">${escHtml(card.rationale)}</div>`;

    if (!isNA && card.verdict !== "skipped") {
      // card click needs the full note object — stash card in noteObjects for later
      div.addEventListener("click", () => {
        const n = noteObjects[ni];
        if (n) openModal(n, card);
      });
    }
    acc.inner.appendChild(div);

    // Store card in note object
    if (noteObjects[ni]) noteObjects[ni].cards.push(card);

    // Update per-note mini progress bar
    acc.cardCount++;
    const npBar = document.getElementById(`np-${ni}`);
    if (npBar) npBar.style.width = Math.min(100, (acc.cardCount / totalChecks) * 100) + "%";

    // Update global progress
    checksCompleted++;
    updateBar();
  });

  _evalEs.addEventListener("note_done", e => {
    const d  = JSON.parse(e.data);
    const ni = d.note_index;
    const acc = noteAccordions[ni];

    // Merge full note metadata into noteObjects
    if (noteObjects[ni]) {
      Object.assign(noteObjects[ni], {
        section_keys: d.section_keys,
        header:       d.header,
        clinician:    d.clinician,
        page_indices: d.page_indices,
      });
      _noteData[ni] = noteObjects[ni];
    }

    // Finish the accordion header: add fail/review badges, remove streaming class
    if (acc) {
      const cards    = noteObjects[ni]?.cards || [];
      const failCnt  = cards.filter(c => c.verdict === "fail").length;
      const mrCnt    = cards.filter(c => c.verdict === "manual_review").length;
      const badges   = [
        failCnt > 0 ? `<span class="badge badge-fail">${failCnt} fail</span>`            : "",
        mrCnt   > 0 ? `<span class="badge badge-manual_review">${mrCnt} review</span>` : "",
      ].filter(Boolean).join(" ");
      acc.hdr.querySelector(".acc-summary").innerHTML = badges;
      acc.hdr.classList.remove("streaming");
    }

    statusText.textContent = `Note ${ni+1}/${totalNotes} done`;
  });

  _evalEs.addEventListener("done", () => {
    _evalEs.close(); _evalEs = null;
    evalBar.style.width = "100%";
    llmInd.classList.remove("active");

    // Update global header count
    const allCards  = Object.values(noteObjects).flatMap(n => n.cards || []);
    const failCount = allCards.filter(c => c.verdict === "fail").length;
    const mrCount   = allCards.filter(c => c.verdict === "manual_review").length;
    document.getElementById("right-header").textContent = `Standards — ${failCount} fail · ${mrCount} review`;

    setTimeout(() => { evalProg.style.display = "none"; }, 1200);
    statusText.textContent = "Complete";
  });

  _evalEs.addEventListener("error", e => {
    if (_evalEs) { _evalEs.close(); _evalEs = null; }
    evalProg.style.display = "none";
    llmInd.classList.remove("active");
    if (!pane.querySelector(".accordion")) {
      pane.innerHTML = `<div style="padding:12px;color:#c00">Evaluation failed. Check the terminal for errors.</div>`;
    }
  });
}

function loadPdfViewer(name, page) {
  const center = document.getElementById("center");
  const ph = document.getElementById("pdf-placeholder");
  if (ph) ph.remove();
  const src = `/pdf/${encodeURIComponent(name)}#page=${page}`;
  if (_currentIframe) {
    _currentIframe.src = src;
  } else {
    const iframe = document.createElement("iframe");
    iframe.id = "pdf-frame";
    iframe.style.cssText = "flex:1;border:none;background:#555;";
    iframe.src = src;
    center.appendChild(iframe);
    _currentIframe = iframe;
  }
  document.getElementById("center-header").textContent = `${name}  —  page ${page}`;
}

function jumpToPage(page) {
  if (_currentPdf) loadPdfViewer(_currentPdf, page);
}

// ── Accordion ─────────────────────────────────────────────────────────────────
function toggleAccordion(id, jumpPage) {
  const acc   = document.getElementById(id);
  const isOpen = acc.classList.contains("open");
  document.querySelectorAll(".accordion").forEach(a => a.classList.remove("open"));
  if (!isOpen) {
    acc.classList.add("open");
    acc.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (jumpPage) jumpToPage(jumpPage);
  }
}

// ── Results ───────────────────────────────────────────────────────────────────
function verdictBadge(verdict) {
  const labels = { pass:"PASS", fail:"FAIL", manual_review:"REVIEW", not_applicable:"N/A", skipped:"SKIPPED" };
  return `<span class="badge badge-${verdict}">${labels[verdict] || verdict.toUpperCase()}</span>`;
}

function renderResults(notes) {
  const pane = document.getElementById("results-pane");
  pane.innerHTML = "";
  const failCount = notes.reduce((s,n) => s + n.cards.filter(c=>c.verdict==="fail").length, 0);
  const mrCount   = notes.reduce((s,n) => s + n.cards.filter(c=>c.verdict==="manual_review").length, 0);
  document.getElementById("right-header").textContent = `Standards — ${failCount} fail · ${mrCount} review`;

  notes.forEach((note, ni) => {
    const accId = `acc-${ni}`;
    const noteFail = note.cards.filter(c=>c.verdict==="fail").length;
    const noteMr   = note.cards.filter(c=>c.verdict==="manual_review").length;
    const summaryBadges = [
      noteFail > 0 ? `<span class="badge badge-fail">${noteFail} fail</span>` : "",
      noteMr   > 0 ? `<span class="badge badge-manual_review">${noteMr} review</span>` : "",
    ].filter(Boolean).join(" ");

    const acc = document.createElement("div");
    acc.className = "accordion";
    acc.id = accId;

    const header = document.createElement("div");
    header.className = "acc-header";
    header.innerHTML = `
      <span class="chevron">▶</span>
      <span class="acc-note-label">Note ${ni+1}: ${escHtml(note.note_type.replace(/_/g," "))} · ${escHtml(note.member)} · ${escHtml(note.service_date||"—")}</span>
      <span class="acc-summary">${summaryBadges}</span>`;
    header.addEventListener("click", () => toggleAccordion(accId, note.first_page));
    acc.appendChild(header);

    const body = document.createElement("div");
    body.className = "acc-body";
    const inner = document.createElement("div");
    inner.className = "acc-body-inner";

    note.cards.forEach(card => {
      const isNA      = card.applicability === null;
      const isSkipped = card.verdict === "skipped";
      const div  = document.createElement("div");
      div.className = "card" + (isNA ? " na" : isSkipped ? " skipped" : "");
      if (card.payer_text) div.title = card.payer_text;
      div.innerHTML = `
        <div class="card-top">
          <span class="card-id">${card.standard_id}</span>
          ${verdictBadge(card.verdict)}
          <span class="card-title">${escHtml(card.title)}</span>
        </div>
        <div class="card-rationale">${escHtml(card.rationale)}</div>`;
      if (!isNA && card.verdict !== "skipped") div.addEventListener("click", () => openModal(note, card));
      inner.appendChild(div);
    });

    body.appendChild(inner);
    acc.appendChild(body);
    pane.appendChild(acc);
  });

  const first = pane.querySelector(".accordion");
  if (first) {
    first.classList.add("open");
    if (_noteData[0]) jumpToPage(_noteData[0].first_page);
  }
}

// ── Main dialog ───────────────────────────────────────────────────────────────
function openModal(note, card) {
  _currentNote = note;
  _currentCard = card;
  const overlay = document.getElementById("modal-overlay");
  const applLabel = card.applicability==="R" ? "Required" : card.applicability==="C" ? "Conditional" : "Not applicable";
  const applClass = card.applicability || "none";

  document.getElementById("modal-title").textContent = `${card.standard_id} — ${card.title}`;
  document.getElementById("modal-subtitle").textContent =
    `${note.note_type.replace(/_/g," ")} · ${note.member} · ${note.service_date||"—"}`;

  let html = "";

  // 1. Applicability + verdict
  html += `<div class="section-label">Applicability &amp; Verdict</div>
    <div class="verdict-row">
      <span class="appl-badge appl-${applClass}">${applLabel}</span>
      ${verdictBadge(card.verdict)}
    </div>
    <div class="rationale-text">${escHtml(card.rationale)}</div>`;

  // 1b. Payer standard text
  if (card.payer_text) {
    html += `<div class="section-label">Payer standard (verbatim)</div>
      <div class="payer-text">${escHtml(card.payer_text)}</div>`;
  }

  // 2. Evidence
  if (card.excerpts?.length > 0) {
    html += `<div class="section-label">Evidence</div>`;
    card.excerpts.forEach(ex => { html += `<div class="excerpt-box">${escHtml(ex)}</div>`; });
  }

  // 3. Page buttons
  if (card.page_numbers?.length > 0) {
    html += `<div class="section-label">Source pages</div>`;
    card.page_numbers.forEach(pg => {
      html += `<button class="page-btn" onclick="jumpToPage(${pg});closeModal()">Jump to page ${pg}</button>`;
    });
  }

  // 4. Judge path + prompt editor
  if (card.judge_calls?.length > 0) {
    html += `<div class="section-label">Judge path (${escHtml(card.judge_used||"null")})</div>`;
    card.judge_calls.forEach((call, i) => {
      const overrideNote = call.prompt_overridden
        ? `<span class="override-note">⚠ prompt overridden by rules/prompts/${card.standard_id}.md</span>` : "";
      html += `<div class="judge-call">
        <div class="judge-q">Original question ${i+1}: ${escHtml(call.question)}</div>
        ${call.prompt_overridden ? `<div class="judge-q-eff">Effective (override): ${escHtml(call.effective_question)}</div>` : ""}
        <div class="judge-ctx">${escHtml(call.context)}</div>
        <div class="judge-answer">${verdictBadge(call.verdict)} <span style="font-size:11px;margin-left:6px">${escHtml(call.rationale)}</span>${overrideNote}</div>
      </div>`;
    });

    // Prompt editor
    const currentQ = card.judge_calls[0].effective_question || card.judge_calls[0].question;
    html += `<div class="edit-panel" id="prompt-panel">
      <h4>✏ Edit judge prompt${card.judge_calls[0].prompt_overridden ? " (override active)" : ""}</h4>
      <div class="prompt-editor">
        <textarea id="prompt-text">${escHtml(currentQ)}</textarea>
        <div class="btn-row">
          <button class="btn btn-primary" onclick="testPrompt()">Test against this note</button>
          <button class="btn btn-success" onclick="savePrompt()">Save prompt</button>
          ${card.judge_calls[0].prompt_overridden
            ? `<button class="btn btn-warn" onclick="deletePrompt()">Remove override</button>` : ""}
          <span class="save-feedback" id="prompt-saved">✓ Saved</span>
        </div>
        <div id="prompt-test-result" style="display:none" class="test-result"></div>
      </div>
    </div>`;
  } else {
    html += `<div class="section-label">Judge path</div>
      <div style="font-size:11px;color:#888">Rule-only check — no judge invoked.</div>`;
  }

  // 5. Rule inputs — header fields
  html += `<div class="section-label">Rule inputs — header fields</div>
    <table class="input-table">`;
  Object.entries(note.header).forEach(([k, v]) => {
    const val = Array.isArray(v) ? v.join(", ") : String(v ?? "—");
    html += `<tr><td>${escHtml(k)}</td><td>${escHtml(val)}</td></tr>`;
  });
  html += `</table>`;

  // 6. Sections extracted
  html += `<div class="section-label">Rule inputs — sections extracted from note</div>`;
  if (note.section_keys.length > 0) {
    html += `<div class="sections-list">${note.section_keys.map(escHtml).join("  ·  ")}</div>`;
  } else {
    html += `<div style="font-size:11px;color:#aaa">No named sections extracted.</div>`;
  }

  // 7. Synonym editor — sections searched but not found
  if (card.sections_missing?.length > 0) {
    html += `<div class="section-label">Tier 1: Sections not found — add synonyms to fix</div>`;
    card.sections_missing.forEach(canon => {
      html += `<div class="missing-section">
        <strong>${escHtml(canon)}</strong> not found as a named section.
        <button class="btn btn-primary" style="padding:2px 8px;font-size:10px"
          onclick="openSynonymEditor('${escHtml(canon)}')">Edit synonyms</button>
      </div>`;
    });
    html += `<div id="synonym-panel"></div>`;
  }

  // 8. Applicability editor
  html += `<div class="section-label">Tier 1: Applicability</div>
    <div style="font-size:11px;color:#555;margin-bottom:6px">
      Current applicability for <strong>${note.note_type}</strong>:
      <span class="appl-badge appl-${applClass}">${applLabel}</span>
    </div>
    <div class="btn-row">
      <button class="btn btn-ghost" onclick="openApplEditor()">Edit applicability matrix</button>
    </div>
    <div id="appl-panel"></div>`;

  // 9. Actions
  html += `<div class="section-label">Actions</div>`;
  const isPinned = _corpus.some(e =>
    e.pdf === _currentPdf && e.note_index === note.note_index && e.standard_id === card.standard_id);

  const REWRITABLE = new Set(["A1","A2","A3","B1","B2","F6","F7","K1"]);
  const isRewritable = REWRITABLE.has(card.standard_id);
  const isFailCard = card.verdict === "fail";

  let rewriteBtn = "";
  if (isFailCard && isRewritable) {
    rewriteBtn = `<button class="btn btn-rewrite" onclick="openRewritePanel()">Author a rewrite…</button>`;
  } else if (isFailCard && !isRewritable) {
    rewriteBtn = `<span style="font-size:10px;color:#888;margin-left:4px" title="This standard requires new clinical documentation — it cannot be remedied by editing the PDF.">⚠ Remedy requires clinical documentation</span>`;
  }

  html += `<div class="btn-row">
    <button class="btn ${isPinned ? "btn-danger" : "btn-ghost"}"
      onclick="${isPinned ? "unpinVerdict()" : "pinVerdict()"}">
      📌 ${isPinned ? "Unpin from corpus" : "Pin verdict to corpus"}
    </button>
    <button class="btn btn-ghost" onclick="openCR()">Tier 3a: Generate change request</button>
    ${rewriteBtn}
  </div>
  <div id="rewrite-panel"></div>`;

  document.getElementById("modal-body").innerHTML = html;
  overlay.classList.add("open");
}

function closeModal() { document.getElementById("modal-overlay").classList.remove("open"); }
document.getElementById("modal-overlay").addEventListener("click", e => { if (e.target.id==="modal-overlay") closeModal(); });
document.addEventListener("keydown", e => { if (e.key==="Escape") { closeModal(); closeCR(); } });

// ── Synonym editor ────────────────────────────────────────────────────────────
let _synEditorCanon = null;
let _synEditorData  = {};

async function openSynonymEditor(canon) {
  _synEditorCanon = canon;
  const allSyns = await fetch("/api/config/synonyms").then(r => r.json());
  _synEditorData  = JSON.parse(JSON.stringify(allSyns)); // deep copy
  const current   = allSyns[canon] || [];
  const panel     = document.getElementById("synonym-panel");

  panel.innerHTML = `
    <div class="edit-panel" style="margin-top:4px">
      <h4>Synonyms for <code>${escHtml(canon)}</code></h4>
      <div class="synonym-list" id="syn-chips">
        ${current.map(s => synChip(s, canon)).join("")}
      </div>
      <div class="syn-add-row">
        <input id="syn-input" type="text" placeholder="New synonym phrase…"
          onkeydown="if(event.key==='Enter'){event.preventDefault();addSyn();}">
        <button class="btn btn-primary" onclick="addSyn()">Add</button>
      </div>
      <div class="btn-row" style="margin-top:8px">
        <button class="btn btn-success" onclick="saveSynonyms()">Save &amp; re-evaluate</button>
        <button class="btn btn-ghost" onclick="document.getElementById('synonym-panel').innerHTML=''">Cancel</button>
        <span class="save-feedback" id="syn-saved">✓ Saved — re-evaluating…</span>
      </div>
    </div>`;
}

function synChip(s, canon) {
  return `<span class="synonym-chip">${escHtml(s)}<span class="rm-syn" onclick="removeSyn('${escHtml(s)}')" title="Remove">×</span></span>`;
}

function removeSyn(s) {
  if (!_synEditorCanon) return;
  const list = _synEditorData[_synEditorCanon] || [];
  _synEditorData[_synEditorCanon] = list.filter(x => x !== s);
  refreshSynChips();
}

function addSyn() {
  if (!_synEditorCanon) return;
  const inp = document.getElementById("syn-input");
  const val = inp.value.trim().toLowerCase();
  if (!val) return;
  const list = _synEditorData[_synEditorCanon] || [];
  if (!list.includes(val)) {
    _synEditorData[_synEditorCanon] = [...list, val];
  }
  inp.value = "";
  refreshSynChips();
}

function refreshSynChips() {
  const canon = _synEditorCanon;
  const list  = _synEditorData[canon] || [];
  document.getElementById("syn-chips").innerHTML = list.map(s => synChip(s, canon)).join("");
}

async function saveSynonyms() {
  const fb = document.getElementById("syn-saved");
  await fetch("/api/config/synonyms", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(_synEditorData),
  });
  fb.style.display = "inline";
  // Re-evaluate current PDF and refresh
  reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

// ── Applicability editor ──────────────────────────────────────────────────────
async function openApplEditor() {
  const panel = document.getElementById("appl-panel");
  if (panel.innerHTML) { panel.innerHTML = ""; return; }
  const matrix = await fetch("/api/config/applicability").then(r => r.json());
  const sid    = _currentCard.standard_id;
  const row    = matrix[sid] || {};
  const types  = ["intake","progress","consultation","treatment_plan","discharge","group","family"];
  let html = `<div class="edit-panel" style="margin-top:4px"><h4>Applicability — ${sid}</h4>
    <table class="input-table"><thead><tr><th>Doc type</th><th>Applicability</th></tr></thead><tbody>`;
  types.forEach(t => {
    const val = row[t] ?? "";
    html += `<tr><td>${t}</td><td>
      <select id="appl-${t}" style="font-size:11px;padding:2px 4px;border:1px solid #ccd;border-radius:3px">
        <option value=""${!val?" selected":""}>— (not applicable)</option>
        <option value="R"${val==="R"?" selected":""}>R (required)</option>
        <option value="C"${val==="C"?" selected":""}>C (conditional)</option>
      </select></td></tr>`;
  });
  html += `</tbody></table>
    <div class="btn-row" style="margin-top:8px">
      <button class="btn btn-success" onclick="saveApplicability('${sid}')">Save applicability</button>
      <span class="save-feedback" id="appl-saved">✓ Saved</span>
    </div></div>`;
  panel.innerHTML = html;
}

async function saveApplicability(sid) {
  const types = ["intake","progress","consultation","treatment_plan","discharge","group","family"];
  const row   = {};
  types.forEach(t => {
    const v = document.getElementById(`appl-${t}`)?.value;
    row[t]  = v || null;
  });
  const overrides = await fetch("/api/config/applicability").then(r => r.json());
  overrides[sid]  = row;
  await fetch("/api/config/applicability", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(overrides),
  });
  const fb = document.getElementById("appl-saved");
  fb.style.display = "inline";
  reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

// ── Prompt editor ─────────────────────────────────────────────────────────────
async function testPrompt() {
  const q    = document.getElementById("prompt-text").value.trim();
  const ctx  = _currentCard.judge_calls?.[0]?.context || "";
  const res  = await fetch(`/api/prompts/${_currentCard.standard_id}/test`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ question: q, context: ctx }),
  }).then(r => r.json());
  const el = document.getElementById("prompt-test-result");
  el.style.display = "block";
  el.className     = `test-result ${res.verdict || ""}`;
  el.innerHTML = res.error
    ? `Error: ${escHtml(res.error)}`
    : `${verdictBadge(res.verdict)} ${escHtml(res.rationale)}`;
}

async function savePrompt() {
  const q = document.getElementById("prompt-text").value.trim();
  await fetch(`/api/prompts/${_currentCard.standard_id}/save`, {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ prompt: q }),
  });
  const fb = document.getElementById("prompt-saved");
  fb.style.display = "inline";
  reEvalCurrent();
  setTimeout(() => { fb.style.display = "none"; }, 3000);
}

async function deletePrompt() {
  await fetch(`/api/prompts/${_currentCard.standard_id}/delete`, { method: "POST" });
  reEvalCurrent();
  closeModal();
}

// ── Regression corpus ─────────────────────────────────────────────────────────
function updateCorpusCount() {
  document.getElementById("corpus-count").textContent = `(${_corpus.length})`;
}

function toggleRegression() {
  const panel = document.getElementById("reg-panel");
  const runBtn = document.getElementById("run-reg-btn");
  const open   = panel.classList.toggle("open");
  runBtn.style.display = open ? "inline-block" : "none";
}

async function pinVerdict() {
  const entry = {
    pdf:              _currentPdf,
    note_index:       _currentNote.note_index,
    standard_id:      _currentCard.standard_id,
    expected_verdict: _currentCard.verdict,
    rationale:        _currentCard.rationale.slice(0, 120),
  };
  const res = await fetch("/api/regression/pin", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(entry),
  }).then(r => r.json());
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());
  updateCorpusCount();
  closeModal();
}

async function unpinVerdict() {
  await fetch("/api/regression/unpin", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({
      pdf: _currentPdf,
      note_index: _currentNote.note_index,
      standard_id: _currentCard.standard_id,
    }),
  });
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());
  updateCorpusCount();
  closeModal();
}

async function runRegression() {
  const body = document.getElementById("reg-body");
  body.innerHTML = `<p style="padding:8px;font-size:11px;color:#888">Running…</p>`;
  const data = await fetch("/api/regression/run").then(r => r.json());
  _corpus = await fetch("/api/regression/corpus").then(r => r.json());

  let html = `<div style="padding:6px 8px;font-size:11px;font-weight:600;color:${data.failed>0?"#c00":"#2d7a2d"}">
    ${data.passed}/${data.total} passed (${data.failed} regressions)
  </div>`;
  (data.results || []).forEach(r => {
    const ok = r.match;
    html += `<div class="delta-row ${ok?"ok":"bad"}">
      <span class="delta-label">
        <strong>${escHtml(r.standard_id)}</strong> · ${escHtml(r.pdf)} note ${r.note_index}
      </span>
      ${verdictBadge(r.expected_verdict)} → ${verdictBadge(r.actual)}
      ${!ok ? `<span style="color:#c00;font-weight:700">✗</span>` : `<span style="color:#2d7a2d">✓</span>`}
    </div>`;
  });
  body.innerHTML = html || `<p style="padding:8px;font-size:11px;color:#888">No pinned items.</p>`;
}

// ── Tier 3a — Change request ──────────────────────────────────────────────────
function openCR() {
  closeModal();
  document.getElementById("cr-result").style.display = "none";
  document.getElementById("cr-desc").value = "";
  document.getElementById("cr-desired").value = _currentCard?.verdict || "pass";
  document.getElementById("cr-overlay").classList.add("open");
}
function closeCR() { document.getElementById("cr-overlay").classList.remove("open"); }

async function generateCR() {
  const desired = document.getElementById("cr-desired").value;
  const desc    = document.getElementById("cr-desc").value.trim();
  const body    = {
    standard_id:      _currentCard.standard_id,
    note_type:        _currentNote.note_type,
    member:           _currentNote.member,
    service_date:     _currentNote.service_date,
    section_keys:     _currentNote.section_keys,
    sections_searched: _currentCard.sections_searched,
    sections_missing:  _currentCard.sections_missing,
    header:           _currentNote.header,
    current_verdict:  _currentCard.verdict,
    current_rationale: _currentCard.rationale,
    judge_calls:      _currentCard.judge_calls,
    desired_verdict:  desired,
    description:      desc,
  };
  const res = await fetch("/api/generate-request", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  }).then(r => r.json());
  _crMd = res.markdown || "";
  document.getElementById("cr-file").textContent = res.file || "";
  document.getElementById("cr-md").textContent   = _crMd;
  document.getElementById("cr-result").style.display = "block";
}

async function copyCR() {
  await navigator.clipboard.writeText(_crMd).catch(() => {});
}

// ── Reload rules ──────────────────────────────────────────────────────────────
async function reloadRules() {
  await fetch("/api/reload", { method: "POST" });
  if (_currentPdf) reEvalCurrent();
}

function reEvalCurrent() {
  if (!_currentPdf) return;
  // Re-select the active PDF item to trigger a fresh streamed evaluation
  const el = document.querySelector(`.pdf-item[data-name="${CSS.escape(_currentPdf)}"]`);
  const savedPdf = _currentPdf;
  _currentPdf = null;  // force selectPdf to re-run
  if (el) selectPdf(savedPdf, el);
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── Rewrite authoring panel ───────────────────────────────────────────────────
let _rwActions = [];
let _rwSpans   = [];
let _rwDiff    = [];
let _rwOverflowAcked = false;

async function openRewritePanel() {
  const panel = document.getElementById("rewrite-panel");
  panel.innerHTML = `<div class="rw-panel"><h4>Author a PDF rewrite</h4>
    <div style="font-size:11px;color:#888;margin-bottom:8px">Loading spans and actions…</div></div>`;

  const note = _currentNote;
  const card = _currentCard;

  // Fetch actions and spans in parallel
  const [actRes, spanRes] = await Promise.all([
    fetch("/api/rewrite/actions").then(r => r.json()),
    fetch(`/api/rewrite/spans?pdf=${encodeURIComponent(_currentPdf)}&note=${note.note_index}`).then(r => r.json()),
  ]);

  _rwActions = actRes;
  _rwSpans   = (spanRes.pages || []).flatMap(p => p.spans || []);
  _rwDiff    = [];
  _rwOverflowAcked = false;

  // Filter actions applicable to this doc type and this verdict
  const applicableActions = _rwActions.filter(a =>
    a.applies_to.length === 0 || a.applies_to.includes(note.note_type)
  );

  // Group spans: header-priority first, then rest
  const headerSpans = _rwSpans.filter(s => s.is_header);
  const otherSpans  = _rwSpans.filter(s => !s.is_header);

  function spanItem(s, idx) {
    return `<label class="rw-span-item ${s.is_header ? "rw-header-span" : ""}">
      <input type="checkbox" data-idx="${idx}" onchange="rwToggleSpan(this)">
      <span class="rw-span-text">${escHtml(s.text)}</span>
      <span class="rw-span-meta">p.${s.page_index}</span>
    </label>`;
  }

  const allSpansHtml = [...headerSpans, ...otherSpans]
    .map((s, i) => spanItem(s, _rwSpans.indexOf(s)))
    .join("");

  const actionOptions = applicableActions.map(a =>
    `<option value="${escHtml(a.id)}">${escHtml(a.label)} (${escHtml(a.tier)})</option>`
  ).join("");

  panel.innerHTML = `<div class="rw-panel" id="rw-panel-inner">
    <h4>Author a PDF rewrite for ${escHtml(card.standard_id)}</h4>

    <div class="rw-section">
      <div class="rw-section-label">1. Select span(s) to rewrite</div>
      <div style="font-size:9px;color:#888;margin-bottom:4px">Header spans highlighted. Tick the span(s) that contain the text to fix.</div>
      <div class="rw-span-list">${allSpansHtml || "<div style='padding:8px;font-size:11px;color:#aaa'>No spans found.</div>"}</div>
    </div>

    <div class="rw-section">
      <div class="rw-section-label">2. Choose action</div>
      <div class="rw-action-select">
        <select id="rw-action-select">${actionOptions || "<option value=''>No applicable actions</option>"}</select>
      </div>
      <div style="margin-top:6px">
        <button class="btn btn-primary" style="font-size:10px;padding:3px 10px" onclick="rwPreview()">Preview changes</button>
        <button class="btn btn-ghost" style="font-size:10px;padding:3px 10px" onclick="rwOpenTier3()">Tier 3: Generate codegen request</button>
      </div>
    </div>

    <div class="rw-section" id="rw-diff-section" style="display:none">
      <div class="rw-section-label">3. Review changes</div>
      <div id="rw-diff-content"></div>
    </div>

    <div class="rw-section" id="rw-apply-section" style="display:none">
      <button class="btn btn-rewrite" onclick="rwApply()">Apply rewrite to PDF</button>
      <span style="font-size:9px;color:#888;margin-left:8px">Writes to output/ directory. Originals unchanged.</span>
      <div id="rw-apply-result"></div>
    </div>
  </div>`;
}

let _rwSelectedSpans = [];

function rwToggleSpan(checkbox) {
  const idx = parseInt(checkbox.dataset.idx);
  const span = _rwSpans[idx];
  if (checkbox.checked) {
    _rwSelectedSpans.push(span);
  } else {
    _rwSelectedSpans = _rwSelectedSpans.filter(s => s !== span);
  }
}

async function rwPreview() {
  if (_rwSelectedSpans.length === 0) {
    alert("Select at least one span to rewrite.");
    return;
  }
  const actionId = document.getElementById("rw-action-select").value;
  if (!actionId) { alert("Select an action."); return; }

  const diffSection = document.getElementById("rw-diff-section");
  const diffContent = document.getElementById("rw-diff-content");
  diffSection.style.display = "";
  diffContent.innerHTML = `<span style="font-size:11px;color:#888">Previewing…</span>`;

  const res = await fetch("/api/rewrite/preview", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      pdf: _currentPdf,
      note: _currentNote.note_index,
      action_id: actionId,
      spans: _rwSelectedSpans,
    }),
  }).then(r => r.json());

  if (res.error) {
    diffContent.innerHTML = `<div class="rw-result-err">${escHtml(res.error)}</div>`;
    return;
  }

  _rwDiff = res.diff || [];
  _rwOverflowAcked = false;

  if (_rwDiff.length === 0) {
    diffContent.innerHTML = `<div style="font-size:11px;color:#888">No changes identified. Try selecting different spans or a different action.</div>`;
    document.getElementById("rw-apply-section").style.display = "none";
    return;
  }

  let html = `<table class="rw-diff-table">
    <tr><th>Page</th><th>Original</th><th>Replacement</th><th>Overflow?</th></tr>`;
  _rwDiff.forEach(d => {
    html += `<tr>
      <td>${d.page_index}</td>
      <td class="rw-diff-old">${escHtml(d.old_text)}</td>
      <td class="rw-diff-new">${escHtml(d.new_text)}</td>
      <td>${d.overflow ? "⚠ yes" : "—"}</td>
    </tr>`;
  });
  html += `</table>`;

  if (res.has_overflow) {
    html += `<div class="rw-overflow-warn">
      ⚠ One or more replacements may be wider than the original span and could overlap adjacent text.
      <label style="display:block;margin-top:4px">
        <input type="checkbox" id="rw-overflow-ack" onchange="_rwOverflowAcked=this.checked">
        I understand and want to proceed anyway
      </label>
    </div>`;
  }

  diffContent.innerHTML = html;
  document.getElementById("rw-apply-section").style.display = "";
}

async function rwApply() {
  if (_rwDiff.length === 0) { alert("Preview first."); return; }

  const hasOverflow = _rwDiff.some(d => d.overflow);
  if (hasOverflow && !_rwOverflowAcked) {
    alert("Acknowledge the overflow warning before applying.");
    return;
  }

  const applyResult = document.getElementById("rw-apply-result");
  applyResult.innerHTML = `<span style="font-size:11px;color:#888">Applying…</span>`;

  const actionId = document.getElementById("rw-action-select").value;

  const res = await fetch("/api/rewrite/apply", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      pdf: _currentPdf,
      note: _currentNote.note_index,
      action_id: actionId,
      diff: _rwDiff,
      overflow_acknowledged: _rwOverflowAcked,
      standard_id: _currentCard.standard_id,
    }),
  }).then(r => r.json());

  if (res.error) {
    applyResult.innerHTML = `<div class="rw-result-err">${escHtml(res.error)}</div>`;
    return;
  }

  applyResult.innerHTML = `<div class="rw-result-ok">
    ✓ Rewrite applied — ${res.spans_changed} span(s) corrected.
    <a href="${res.rewritten_pdf_url}" target="_blank" style="color:#1a5a1a;margin-left:8px">View rewritten PDF</a>
    <br><button class="btn btn-primary" style="font-size:10px;padding:3px 10px;margin-top:6px"
      onclick="rwReEvaluate('${escHtml(res.rewritten_pdf_url)}')">
      Re-evaluate rewritten note
    </button>
  </div>`;
}

async function rwReEvaluate(outputPdfUrl) {
  // Re-evaluate the rewritten PDF (served from /pdf/output/<name>)
  // by stripping the path prefix and using a virtual source path.
  // We show a simple notice since the output PDF is in a different dir.
  alert("Re-evaluation compares the output PDF against your regression corpus. " +
    "To evaluate: copy the rewritten PDF from output/ to sourcedocs/, reload the left pane, " +
    "then select it and run evaluation. Full in-place re-evaluate is planned for a future release.");
}

async function rwOpenTier3() {
  const panel = document.getElementById("rw-diff-section");
  // Build Tier-3 request artifact for data-driven action authoring
  const desc = prompt("Describe the desired rewrite transform (what data source, what logic):");
  if (!desc) return;

  const res = await fetch("/api/rewrite/generate-request", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      pdf: _currentPdf,
      note: _currentNote.note_index,
      standard_id: _currentCard.standard_id,
      description: desc,
      spans: _rwSelectedSpans,
      desired_replacement: "",
      data_source: "",
    }),
  }).then(r => r.json());

  if (res.error) { alert("Error: " + res.error); return; }
  alert(`Rewrite change-request artifact saved to:\n${res.file}\n\nOpen it in VS Code and paste it to Claude Code to implement the action.`);
}

init();
