// Figure editor: edits a FigureSpec, solves it live on the local server and
// shows a schematic stitch-point preview. All results are NOT_VERIFIED/UNTESTED.

const $ = id => document.getElementById(id);
const STORE_KEY = "crochet.figure.spec.v1";
let csrf = "";
let meta = { shapes: [], templates: [] };
let spec = null;
let result = null;
let selectedPart = null;
let solveTimer = 0;
let solveSeq = 0;
let activeTemplate = null;

const END_LABEL = { closed: "geschlossen", open: "offen zum Annähen", flat: "flach geschlossen" };
const STUFF_LABEL = { "": "automatisch", full: "fest", light: "leicht", none: "keine" };

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children) if (child !== null && child !== undefined) node.append(child);
  return node;
}

async function api(path, body, binary = false) {
  const options = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(body),
  };
  const response = await fetch(path, { ...options, credentials: "same-origin", cache: "no-store" });
  if (binary && response.ok) return response.blob();
  const data = await response.json();
  if (!data.ok) throw Object.assign(new Error(data.error.message_de || data.error.reason), data.error);
  return data.data;
}

function saveLocal() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(spec)); } catch { /* optional */ }
}

function loadLocal() {
  try { const raw = localStorage.getItem(STORE_KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
}

// ------------------------------------------------------------- form editing

function field(label, input, unit) { return el("label", {}, label, unit ? el("span", { text: unit }) : null, input); }

function numberInput(value, onChange, { min, max, step = 1 } = {}) {
  return el("input", { type: "number", value, min, max, step, oninput: e => {
    const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(v);
  } });
}

function textInput(value, onChange, max = 40) {
  return el("input", { value, maxlength: max, oninput: e => onChange(e.target.value) });
}

function select(options, value, onChange) {
  const node = el("select", { onchange: e => onChange(e.target.value) });
  for (const [key, label] of options) node.append(el("option", { value: key, text: label }));
  node.value = value;
  return node;
}

function colorOptions() { return spec.colors.map(c => [c.id, c.label]); }

function uniqueId(base, taken) {
  let id = base; let i = 2;
  while (taken.has(id)) id = `${base}${i++}`;
  return id;
}

function renderForm() {
  $("name").value = spec.name;
  $("technique").value = spec.technique ?? "crochet";
  $("g-stitches").value = spec.gauge.stitches_per_100mm;
  $("g-rows").value = spec.gauge.rows_per_100mm;
  $("g-hook").value = spec.gauge.hook_mm ?? 3;
  $("g-yarn").value = spec.gauge.yarn ?? "";
  renderColors(); renderParts(); renderFeatures(); renderJson(); renderSummaries(); renderQuick();
}

function renderSummaries() {
  const g = spec.gauge;
  $("sum-basics").textContent = `${spec.technique === "knit" ? "Stricken" : "Häkeln"} · ${g.stitches_per_100mm} M × ${g.rows_per_100mm} R · ${g.hook_mm ?? 3} mm`;
  $("sum-colors").replaceChildren(...spec.colors.map(c => el("span", { class: "yarn-dot", style: `background:${c.hex}`, title: c.label })));
  $("sum-parts").textContent = spec.parts.length === 1 ? "1 Teil" : `${spec.parts.length} Teile`;
  const details = (spec.features ?? []).length;
  $("sum-features").textContent = details ? `${details} ${details === 1 ? "Detail" : "Details"}` : "keine";
}

// Template gallery: each card shows the real solved preview of its template.
const thumbs = new Map();

function renderTemplates() {
  const gallery = $("templates");
  if (!gallery.childElementCount) {
    for (const t of meta.templates) {
      const canvas = el("canvas", { "aria-hidden": "true" });
      gallery.append(el("button", { type: "button", class: "template-card", "data-id": t.id, onclick: () => loadTemplate(t.id) },
        canvas, el("span", { text: t.name.replace(/\s*\(.*\)$/, "") })));
      thumbs.set(t.id, new FigureViewer(canvas, { interactive: false }));
    }
    drawThumbnails();
  }
  for (const card of gallery.children) card.setAttribute("aria-pressed", String(card.dataset.id === activeTemplate));
}

async function drawThumbnails() {
  for (const t of meta.templates) {
    try { thumbs.get(t.id).setResult(await api("/api/figure/solve", { spec: t.spec })); }
    catch { /* a card without preview still works */ }
  }
}

function renderColors() {
  const box = $("colors"); box.replaceChildren();
  spec.colors.forEach((color, index) => {
    box.append(el("div", { class: "color-line" },
      el("input", { type: "color", value: color.hex, "aria-label": `Farbe ${color.label}`,
        oninput: e => { color.hex = e.target.value.toUpperCase(); renderQuick(); changed(false); } }),
      textInput(color.label, v => { color.label = v; renderQuick(); changed(false); }),
      el("button", { type: "button", class: "quiet", text: "×", "aria-label": `Farbe ${color.label} entfernen`,
        disabled: spec.colors.length < 2 ? "" : null,
        onclick: () => { spec.colors.splice(index, 1); changed(true); } })));
  });
}

function renderParts() {
  const box = $("parts"); box.replaceChildren();
  spec.parts.forEach((part, index) => {
    const shape = meta.shapes.find(s => s.id === part.shape) || meta.shapes[0];
    const ends = shape.ends.map(e => [e, END_LABEL[e]]);
    if (!shape.ends.includes(part.end ?? shape.ends[0])) part.end = shape.ends[0];
    const card = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("strong", { text: `${index + 1}. ${part.label}` }),
        index === 0 ? el("span", { class: "small-note", text: "Grundkörper" }) :
          el("button", { type: "button", class: "quiet", text: "Entfernen", onclick: () => removePart(index) })),
      el("div", { class: "field-row" },
        field("Name", textInput(part.label, v => { part.label = v; changed(false); })),
        field("Form", select(meta.shapes.map(s => [s.id, s.label_de]), part.shape, v => {
          part.shape = v; const s = meta.shapes.find(x => x.id === v); part.end = s.ends[0]; changed(true);
        }))),
      el("div", { class: "field-row" },
        field(part.circumference_mm !== undefined ? "Umfang" : "Breite Ø",
          numberInput(part.circumference_mm ?? part.width_mm, v => {
            if (part.circumference_mm !== undefined) part.circumference_mm = v; else part.width_mm = v; changed(false);
          }, { min: 4, max: 950 }), "mm"),
        field("Höhe", numberInput(part.height_mm, v => { part.height_mm = v; changed(false); }, { min: 3, max: 400 }), "mm")),
      el("div", { class: "field-row" },
        field("Ende", select(ends, part.end, v => { part.end = v; changed(false); })),
        field("Farbe", select(colorOptions(), part.color, v => { part.color = v; changed(false); })),
        field("Füllung", select(Object.entries(STUFF_LABEL), part.stuffing ?? "", v => {
          if (v) part.stuffing = v; else delete part.stuffing; changed(false);
        }))),
    );
    if (index > 0) {
      const attach = part.attach;
      const hosts = spec.parts.slice(0, index).filter(p => !p.attach || p.attach.angles.length === 1).map(p => [p.id, p.label]);
      card.append(el("div", { class: "field-row" },
        field("Annähen an", select(hosts, attach.to, v => { attach.to = v; changed(false); })),
        field("Höhe auf Teil", el("input", { type: "range", min: 0, max: 100, step: 1,
          value: Math.round(attach.at * 100), oninput: e => {
            attach.at = Number(e.target.value) / 100;
            e.target.previousElementSibling.textContent = `${e.target.value} %`;
            changed(false);
          } }), `${Math.round(attach.at * 100)} %`)),
        el("div", { class: "field-row" },
          field("Winkel", textInput(attach.angles.join(", "), v => {
            const values = v.split(/[,;\s]+/).filter(Boolean).map(Number);
            if (values.length && values.every(Number.isFinite)) { attach.angles = values; changed(false); }
          }, 60), "° je Exemplar"),
          field("Neigung nach unten", numberInput(attach.tilt ?? 0, v => { attach.tilt = v; changed(false); }, { min: -85, max: 85 }), "°")));
    }
    box.append(card);
  });
}

function renderFeatures() {
  const box = $("features"); box.replaceChildren();
  (spec.features ?? []).forEach((feature, index) => {
    const hosts = spec.parts.filter(p => !p.attach || p.attach.angles.length === 1).map(p => [p.id, p.label]);
    box.append(el("div", { class: "card" },
      el("div", { class: "card-head" }, el("strong", { text: feature.type === "eye" ? "Sicherheitsaugen" : "Nase (gestickt)" }),
        el("button", { type: "button", class: "quiet", text: "Entfernen", onclick: () => { spec.features.splice(index, 1); changed(true); } })),
      el("div", { class: "field-row" },
        field("Typ", select([["eye", "Augen"], ["nose", "Nase"]], feature.type, v => { feature.type = v; changed(true); })),
        field("auf Teil", select(hosts, feature.on, v => { feature.on = v; changed(false); })),
        field("Farbe", select(colorOptions(), feature.color, v => { feature.color = v; changed(false); }))),
      el("div", { class: "field-row" },
        field("Höhe", numberInput(Math.round(feature.at * 100), v => { feature.at = Math.min(1, Math.max(0, v / 100)); changed(false); }, { min: 0, max: 100 }), "%"),
        field("Winkel", textInput(feature.angles.join(", "), v => {
          const values = v.split(/[,;\s]+/).filter(Boolean).map(Number);
          if (values.length && values.every(Number.isFinite)) { feature.angles = values; changed(false); }
        }, 40), "°"),
        field("Größe", numberInput(feature.size_mm, v => { feature.size_mm = v; changed(false); }, { min: 2, max: 40 }), "mm"))));
  });
}

function renderJson() { $("json").value = JSON.stringify(spec, null, 2); }

function removePart(index) {
  const removed = spec.parts[index].id;
  const doomed = new Set([removed]);
  // Remove dependants transitively so the spec stays consistent.
  for (const part of spec.parts) if (part.attach && doomed.has(part.attach.to)) doomed.add(part.id);
  spec.parts = spec.parts.filter(p => !doomed.has(p.id));
  spec.features = (spec.features ?? []).filter(f => !doomed.has(f.on));
  changed(true);
}

function changed(rerenderForm) {
  if (rerenderForm) { renderParts(); renderFeatures(); renderColors(); renderQuick(); }
  if (activeTemplate) { activeTemplate = null; renderTemplates(); }
  renderJson(); renderSummaries(); saveLocal(); scheduleSolve();
}

// ------------------------------------------------------------- solving

function scheduleSolve() {
  clearTimeout(solveTimer);
  solveTimer = setTimeout(solve, 350);
}

async function solve() {
  const seq = ++solveSeq;
  try {
    const data = await api("/api/figure/solve", { spec });
    if (seq !== solveSeq) return;
    result = data;
    $("error").hidden = true;
    renderResult();
  } catch (error) {
    if (seq !== solveSeq) return;
    $("error").hidden = false;
    $("error").textContent = error.message || String(error);
  }
}

function renderResult() {
  $("figure-title").textContent = result.name;
  const height = (result.bounds_mm.max[1] - result.bounds_mm.min[1]) / 10;
  const parts = result.parts.length === 1 ? "1 Teil" : `${result.parts.length} Teile`;
  $("summary").textContent = `${parts} · ${result.total_stitches.toLocaleString("de-DE")} Maschen · ca. ${height.toLocaleString("de-DE", { maximumFractionDigits: 1 })} cm hoch`;
  const tabs = $("part-tabs"); tabs.replaceChildren();
  if (!result.parts.some(p => p.id === selectedPart)) selectedPart = result.parts[0].id;
  result.parts.forEach(part => {
    const color = result.colors.find(c => c.id === part.color);
    tabs.append(el("button", { type: "button", "aria-pressed": String(part.id === selectedPart),
      onclick: () => { selectedPart = part.id; renderResult(); },
      onmouseenter: () => viewer.highlight(result.parts.indexOf(part)),
      onmouseleave: () => viewer.highlight(-1) },
      el("span", { class: "yarn-dot", style: `background:${color.hex}` }),
      `${part.label}${part.instances > 1 ? ` ×${part.instances}` : ""}`));
  });
  const part = result.parts.find(p => p.id === selectedPart);
  const colors = Object.fromEntries(result.colors.map(c => [c.id, c]));
  const list = el("ol", { class: "rounds" });
  for (const row of part.rows) {
    // A yarn strip in the row's colour runs down the left edge of the pattern.
    const yarn = () => el("span", { class: "yarn", style: `background:${colors[row.color].hex}`, "aria-hidden": "true" });
    for (const note of row.notes) list.append(el("li", { class: "note" }, yarn(), el("span"), el("span", { class: "text", text: note })));
    const label = row.from === row.to ? `R${row.from}` : `R${row.from}–${row.to}`;
    const body = row.text_de.slice(row.text_de.indexOf(": ") + 2).replace(/ \(\d+\)$/, "");
    list.append(el("li", {}, yarn(), el("span", { class: "label", text: label }), el("span", { class: "text", text: body }),
      el("span", { class: "count", text: String(row.count), title: "Maschen am Ende der Runde", "aria-label": `${row.count} Maschen` })));
  }
  list.append(el("li", { class: "finish" }, el("span", { class: "text", text: part.finish_de })));
  const unit = part.construction === "rows" ? "Reihen" : "Runden";
  const flat = part.shape === "disc" || part.shape === "rectangle";
  $("part-detail").replaceChildren(...[
    el("p", { class: "part-meta num", text: `${part.round_count} ${unit} · bis ${part.max_stitches} Maschen · ca. ${Math.round(part.predicted_width_mm)} mm breit${flat ? "" : ` · Ende ${END_LABEL[part.end]}`}` }),
    part.note ? el("p", { class: "small-note", text: part.note }) : null,
    list].filter(Boolean));
  const steps = $("assembly"); steps.replaceChildren();
  for (const step of [...result.features, ...result.assembly]) steps.append(el("li", { text: step.text_de }));
  const calPart = $("cal-part"); const previous = calPart.value;
  calPart.replaceChildren(...result.parts.map(p => el("option", { value: p.id, text: `${p.label} · geplant ${Math.round(p.predicted_width_mm)} × ${Math.round(p.predicted_height_mm)} mm` })));
  if (result.parts.some(p => p.id === previous)) calPart.value = previous;
  viewer.setResult(result);
  renderSize();
  if (making) renderMaking();
}

// ------------------------------------------------------------- compose & calibrate

async function composeFromText() {
  const text = $("compose-text").value.trim();
  const notes = $("compose-notes"); const button = $("compose");
  if (!text) { notes.hidden = false; notes.textContent = "Bitte zuerst beschreiben, was du machen möchtest."; return; }
  button.disabled = true; notes.hidden = false; notes.textContent = "Entwurf wird erstellt …";
  try {
    const data = await api("/api/figure/compose", { text, use_claude: $("use-claude").checked });
    spec = data.spec; if (!spec.features) spec.features = [];
    activeTemplate = null; renderTemplates();
    renderForm(); saveLocal(); solve();
    notes.textContent = `${data.source === "claude" ? "Entwurf von Claude" : "Erkannt"}: ${data.notes_de.join(" ")} Unter „Feinarbeit“ lässt sich alles anpassen.`;
  } catch (error) {
    notes.textContent = error.message || String(error);
  } finally { button.disabled = false; }
}

let pendingGauge = null;

async function calibrate() {
  const box = $("cal-result"); box.hidden = false; $("cal-apply").hidden = true;
  const width = parseFloat($("cal-width").value); const height = parseFloat($("cal-height").value);
  if (!Number.isFinite(width)) { box.textContent = "Bitte die gemessene Breite eintragen."; return; }
  try {
    const data = await api("/api/figure/calibrate", {
      spec, part: $("cal-part").value, measured_mm: width, measure_mode: $("cal-mode").value,
      measured_height_mm: Number.isFinite(height) ? height : null,
    });
    pendingGauge = data;
    box.textContent = `${data.explanation_de} Bisher: ${spec.gauge.stitches_per_100mm} M × ${spec.gauge.rows_per_100mm} R.`;
    $("cal-apply").hidden = false;
  } catch (error) { box.textContent = error.message || String(error); }
}

function applyCalibration() {
  if (!pendingGauge) return;
  spec.gauge.stitches_per_100mm = pendingGauge.stitches_per_100mm;
  spec.gauge.rows_per_100mm = pendingGauge.rows_per_100mm;
  pendingGauge = null; $("cal-apply").hidden = true;
  $("cal-result").textContent += " Übernommen, alle Teile sind neu berechnet.";
  renderForm(); changed(false);
}

// ------------------------------------------------------------- quick adjust

// The one size that matters for this kind of project, in cm.
function sizeControl() {
  const only = spec.parts.length === 1 ? spec.parts[0] : null;
  if (only?.circumference_mm !== undefined) {
    return { label: "Kopfumfang", value: only.circumference_mm / 10, min: 30, max: 65, step: 0.5, apply: v => { only.circumference_mm = v * 10; } };
  }
  if (only?.shape === "rectangle") return { label: "Länge", value: only.height_mm / 10, min: 10, max: 250, step: 1, apply: v => { only.height_mm = v * 10; } };
  if (only?.shape === "disc") return { label: "Durchmesser", value: only.width_mm / 10, min: 5, max: 60, step: 0.5, apply: v => { only.width_mm = v * 10; } };
  const height = result ? (result.bounds_mm.max[1] - result.bounds_mm.min[1]) / 10 : 15;
  return { label: "Höhe", value: Math.round(height * 2) / 2, min: 4, max: 40, step: 0.5, apply: v => scaleFigure(v / height) };
}

// Same rule as the server-side text interpreter (figure_compose._scale_spec).
function scaleFigure(factor) {
  for (const part of spec.parts) {
    for (const key of ["width_mm", "height_mm", "circumference_mm"]) {
      if (part[key] !== undefined) part[key] = Math.round(part[key] * factor * 10) / 10;
    }
  }
  for (const feature of spec.features ?? []) feature.size_mm = Math.round(Math.min(40, Math.max(2, feature.size_mm * factor)) * 10) / 10;
}

const cm = v => `${v.toLocaleString("de-DE", { maximumFractionDigits: 1 })} cm`;

function renderSize() {
  const size = sizeControl(); const input = $("size");
  $("size-label").textContent = size.label;
  Object.assign(input, { min: size.min, max: size.max, step: size.step });
  input.value = size.value; $("size-value").textContent = cm(size.value);
}

function renderQuick() {
  $("quick-colors").replaceChildren(...spec.colors.map(color => el("label", { class: "yarn", title: color.label },
    el("input", { type: "color", value: color.hex, "aria-label": `Garnfarbe ${color.label}`,
      oninput: e => { color.hex = e.target.value.toUpperCase(); renderColors(); changed(false); } }),
    el("span", { text: color.label }))));
  const knit = spec.technique === "knit";
  $("tech-crochet").setAttribute("aria-pressed", String(!knit));
  $("tech-knit").setAttribute("aria-pressed", String(knit));
}

function setTechnique(value) {
  if (value === "crochet") delete spec.technique; else spec.technique = value;
  $("technique").value = value; renderQuick(); changed(false);
}

// ------------------------------------------------------------- making mode

// Walks the pattern one round at a time, like a row counter. Progress is kept
// per figure in this browser only.
const PROGRESS_KEY = "crochet.figure.progress.v1";
let making = null;
let makingViewer = null;

function rowBody(row) { return row.text_de.slice(row.text_de.indexOf(": ") + 2).replace(/ \(\d+\)$/, ""); }

function makingSteps(part) {
  const steps = [];
  for (const row of part.rows) {
    for (let r = row.from; r <= row.to; r++) {
      steps.push({ round: r, text: rowBody(row), count: row.count, color: row.color,
        notes: r === row.from ? row.notes : [], group: row.from === row.to ? "" : `R${row.from}–R${row.to}` });
    }
  }
  steps.push({ finish: true, text: part.finish_de, notes: [] });
  return steps;
}

function progressStore() {
  try { return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {}; } catch { return {}; }
}

function figureKey() {
  return `${result.name}|${result.parts.map(p => `${p.id}:${p.round_count}:${p.max_stitches}`).join(",")}`;
}

function saveProgress() {
  const store = progressStore(); store[figureKey()] = { part: making.part, at: making.at };
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(store)); } catch { /* optional */ }
}

function openMaking() {
  if (!result) return;
  const saved = progressStore()[figureKey()] ?? {};
  making = { part: result.parts.some(p => p.id === saved.part) ? saved.part : result.parts[0].id, at: saved.at ?? {} };
  if (!makingViewer) makingViewer = new FigureViewer($("making-canvas"));
  $("making").hidden = false; document.body.classList.add("making-open");
  renderMaking(); $("making-next").focus();
}

function closeMaking() {
  $("making").hidden = true; document.body.classList.remove("making-open"); making = null;
  $("start-making").focus();
}

function moveMaking(delta) {
  const part = result.parts.find(p => p.id === making.part);
  const steps = makingSteps(part); const index = making.at[part.id] ?? 0;
  if (delta > 0 && index >= steps.length - 1) {
    const next = result.parts[result.parts.indexOf(part) + 1];
    making.at[part.id] = steps.length;
    if (next) making.part = next.id;
  } else {
    making.at[part.id] = Math.max(0, Math.min(steps.length - 1, index + delta));
  }
  saveProgress(); renderMaking();
}

function renderMaking() {
  const colors = Object.fromEntries(result.colors.map(c => [c.id, c]));
  $("making-title").textContent = result.name;
  $("making-parts").replaceChildren(...result.parts.map(p => {
    const total = makingSteps(p).length; const done = Math.min(making.at[p.id] ?? 0, total);
    return el("button", { type: "button", "aria-pressed": String(p.id === making.part), onclick: () => { making.part = p.id; saveProgress(); renderMaking(); } },
      el("span", { class: "yarn-dot", style: `background:${colors[p.color].hex}` }), p.label,
      el("span", { class: "chip-meta num", text: done >= total ? "fertig" : `${done}/${total - 1}` }));
  }));
  const part = result.parts.find(p => p.id === making.part);
  const steps = makingSteps(part); const doneAll = (making.at[part.id] ?? 0) >= steps.length;
  const index = Math.min(making.at[part.id] ?? 0, steps.length - 1); const step = steps[index];
  const previous = steps[index - 1];
  const unit = part.construction === "rows" ? "Reihe" : "Runde";
  $("making-progress").max = steps.length; $("making-progress").value = doneAll ? steps.length : index;
  $("making-step").textContent = doneAll ? `${part.label} ist fertig` : step.finish ? "Abschluss" : `${unit} ${step.round} von ${part.round_count}`;
  $("making-notes").replaceChildren(...(doneAll ? [] : step.notes).map(note => el("p", { text: note })));
  $("making-notes").hidden = doneAll || !step.notes.length;
  $("making-color").hidden = doneAll || step.finish || !previous || previous.color === step.color;
  if (!$("making-color").hidden) $("making-color").replaceChildren(el("span", { class: "yarn-dot", style: `background:${colors[step.color].hex}` }), `Ab hier mit ${colors[step.color].label}`);
  const lastPart = result.parts.indexOf(part) === result.parts.length - 1;
  $("making-text").textContent = !doneAll ? step.text : lastPart && result.parts.length > 1
    ? "Alle Teile sind fertig. Jetzt zusammennähen, die Schritte stehen in der Anleitung unter „Zusammennähen“."
    : "Alle Runden dieses Teils sind abgehakt.";
  $("making-count").textContent = doneAll || step.finish ? "" : `${step.count} Maschen`;
  $("making-group").textContent = doneAll || step.finish || !step.group ? "" : `Gleiche Runde wie ${step.group}`;
  $("making-prev").disabled = index === 0 && !doneAll;
  $("making-next").disabled = doneAll && lastPart;
  $("making-next").textContent = doneAll ? (lastPart ? "Fertig" : "Nächstes Teil") : step.finish ? (lastPart ? "Figur fertig" : "Teil fertig") : `${unit} fertig`;
  makingViewer.setResult(result); makingViewer.highlight(result.parts.indexOf(part));
}

// ------------------------------------------------------------- viewer

class FigureViewer {
  constructor(canvas, { interactive = true } = {}) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d");
    this.yaw = -0.5; this.pitch = 0.18; this.zoom = 1; this.focus = -1; this.result = null;
    new ResizeObserver(() => this.draw()).observe(canvas);
    if (interactive) this.listen(canvas);
  }
  listen(canvas) {
    canvas.addEventListener("pointerdown", e => { this.drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", e => {
      if (!this.drag) return;
      this.yaw += (e.clientX - this.drag.x) * 0.01;
      this.pitch = Math.max(-1.3, Math.min(1.3, this.pitch + (e.clientY - this.drag.y) * 0.01));
      this.drag = { x: e.clientX, y: e.clientY }; this.draw();
    });
    canvas.addEventListener("pointerup", () => { this.drag = null; });
    canvas.addEventListener("dblclick", () => { this.yaw = -0.5; this.pitch = 0.18; this.zoom = 1; this.draw(); });
    canvas.addEventListener("wheel", e => { e.preventDefault(); this.zoom = Math.max(0.4, Math.min(4, this.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1))); this.draw(); }, { passive: false });
    canvas.addEventListener("keydown", e => {
      const step = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, 0.1], ArrowDown: [0, -0.1] }[e.key];
      if (step) { this.yaw += step[0]; this.pitch += step[1]; this.draw(); e.preventDefault(); }
    });
  }
  setResult(result) { this.result = result; this.draw(); }
  highlight(index) { this.focus = index; this.draw(); }
  draw() {
    const { canvas, ctx } = this;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth; const height = canvas.clientHeight;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0); ctx.clearRect(0, 0, width, height);
    if (!this.result) return;
    const { min, max } = this.result.bounds_mm;
    const center = [(min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2];
    const extent = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 1);
    const scale = Math.min(width, height) / extent * 0.82 * this.zoom;
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    // Soft contact shadow on the floor plane under the figure.
    const floor = min[1] - center[1];
    const shadowX = width / 2, shadowY = height / 2 - floor * cp * scale;
    const rx = Math.max(max[0] - min[0], max[2] - min[2]) * 0.5 * scale;
    const ry = Math.max(4, rx * Math.abs(sp) + 6);
    const shadow = ctx.createRadialGradient(shadowX, shadowY, 0, shadowX, shadowY, rx);
    shadow.addColorStop(0, "rgba(38,48,42,.22)"); shadow.addColorStop(1, "rgba(38,48,42,0)");
    ctx.save(); ctx.translate(shadowX, shadowY); ctx.scale(1, ry / rx); ctx.translate(-shadowX, -shadowY);
    ctx.fillStyle = shadow; ctx.beginPath(); ctx.arc(shadowX, shadowY, rx, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    const palette = this.result.colors.map(c => [parseInt(c.hex.slice(1, 3), 16), parseInt(c.hex.slice(3, 5), 16), parseInt(c.hex.slice(5, 7), 16)]);
    const projected = this.result.preview.points.map(p => {
      const x = p[0] - center[0], y = p[1] - center[1], z = p[2] - center[2];
      const x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
      const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
      return [width / 2 + x1 * scale, height / 2 - y2 * scale, z2, p];
    }).sort((a, b) => a[2] - b[2]);
    for (const [sx, sy2, depth, p] of projected) {
      const shade = 0.62 + 0.38 * Math.max(0, Math.min(1, (depth / extent) + 0.5));
      const [r, g, b] = palette[p[3]];
      const dim = this.focus >= 0 && p[4] !== this.focus && p[4] !== -1;
      ctx.fillStyle = `rgba(${Math.round(r * shade)},${Math.round(g * shade)},${Math.round(b * shade)},${dim ? 0.18 : 1})`;
      ctx.beginPath(); ctx.arc(sx, sy2, Math.max(1.2, p[6] * scale * 1.15), 0, Math.PI * 2); ctx.fill();
    }
  }
}

const viewer = new FigureViewer($("figure-canvas"));

// ------------------------------------------------------------- downloads

async function download(path, filename, type) {
  try {
    const blob = await api(path, { spec }, true);
    if (!(blob instanceof Blob)) throw new Error("Download fehlgeschlagen.");
    const url = URL.createObjectURL(type ? new Blob([blob], { type }) : blob);
    const link = el("a", { href: url, download: filename }); document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (error) {
    $("error").hidden = false; $("error").textContent = error.message || String(error);
  }
}

async function verify() {
  const box = $("verify-result"); const button = $("verify");
  box.hidden = false; button.disabled = true;
  box.textContent = "Jede Masche wird unabhängig nachgerechnet. Das dauert ein paar Sekunden …";
  try {
    const data = await api("/api/figure/verify", { spec });
    const passed = data.parts.filter(p => p.status === "PASS").length;
    const skipped = data.parts.filter(p => p.status === "NOT_APPLICABLE");
    const checked = data.parts.length - skipped.length;
    box.replaceChildren(...[
      el("strong", { text: checked ? `${passed} von ${checked} Teilen stimmen.` : "Keine gehäkelten Runden zum Nachrechnen." }),
      checked ? el("span", { text: "Maschenzahlen, Einstichstellen, Farbwechsel und Öffnungen passen zusammen. Ob Form und Größe stimmen, zeigt erst dein Testteil." }) : null,
      skipped.length ? el("span", { text: `${skipped.length === 1 ? "1 Teil ist" : `${skipped.length} Teile sind`} gestrickt oder in Reihen gearbeitet. Dort werden bisher nur die Maschenzahlen geprüft.` }) : null,
      ...data.parts.filter(p => p.status === "FAIL").map(p => el("span", { text: `Stimmt nicht: ${p.label} (${p.reason})` })),
    ].filter(Boolean));
  } catch (error) {
    box.textContent = `Prüfung fehlgeschlagen: ${error.message}`;
  } finally { button.disabled = false; }
}

function slug() { return (spec.name || "figur").toLowerCase().replace(/[^a-z0-9äöüß]+/g, "-").replace(/^-|-$/g, "") || "figur"; }

// ------------------------------------------------------------- bootstrap

function loadTemplate(id) {
  const template = meta.templates.find(t => t.id === id);
  spec = structuredClone(template.spec);
  if (!spec.features) spec.features = [];
  activeTemplate = id; renderTemplates();
  renderForm(); saveLocal(); solve();
}

async function start() {
  const boot = await api("/api/bootstrap");
  csrf = boot.csrf_token;
  meta = await api("/api/figure/templates");
  renderTemplates();
  $("name").addEventListener("input", e => { spec.name = e.target.value; changed(false); });
  $("technique").addEventListener("change", e => setTechnique(e.target.value));
  $("tech-crochet").addEventListener("click", () => setTechnique("crochet"));
  $("tech-knit").addEventListener("click", () => setTechnique("knit"));
  $("size").addEventListener("input", e => { $("size-value").textContent = cm(Number(e.target.value)); });
  $("size").addEventListener("change", e => { sizeControl().apply(Number(e.target.value)); renderParts(); renderFeatures(); changed(false); });
  $("start-making").addEventListener("click", openMaking);
  $("making-close").addEventListener("click", closeMaking);
  $("making-prev").addEventListener("click", () => moveMaking(-1));
  $("making-next").addEventListener("click", () => moveMaking(1));
  $("making").addEventListener("keydown", e => {
    if (e.key === "Escape") closeMaking();
    else if (e.target.tagName !== "BUTTON" && (e.key === " " || e.key === "ArrowRight")) { moveMaking(1); e.preventDefault(); }
    else if (e.target.tagName !== "BUTTON" && e.key === "ArrowLeft") { moveMaking(-1); e.preventDefault(); }
  });
  if (meta.claude_available) $("claude-row").hidden = false;
  $("compose").addEventListener("click", composeFromText);
  $("compose-text").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) composeFromText(); });
  $("calibrate").addEventListener("click", calibrate);
  $("cal-apply").addEventListener("click", applyCalibration);
  const gauge = (id, key) => $(id).addEventListener("input", e => {
    const v = parseFloat(e.target.value); if (Number.isFinite(v)) { spec.gauge[key] = v; changed(false); }
  });
  gauge("g-stitches", "stitches_per_100mm"); gauge("g-rows", "rows_per_100mm"); gauge("g-hook", "hook_mm");
  $("g-yarn").addEventListener("input", e => { spec.gauge.yarn = e.target.value; changed(false); });
  $("add-color").addEventListener("click", () => {
    const id = uniqueId("farbe", new Set(spec.colors.map(c => c.id)));
    spec.colors.push({ id, label: "Neue Farbe", hex: "#7A8FA6" }); changed(true);
  });
  $("add-part").addEventListener("click", () => {
    const id = uniqueId("teil", new Set(spec.parts.map(p => p.id)));
    spec.parts.push({ id, label: "Neues Teil", shape: "sphere", width_mm: 20, height_mm: 20, color: spec.colors[0].id,
      attach: { to: spec.parts[0].id, at: 0.5, angles: [0] } });
    changed(true);
  });
  $("add-feature").addEventListener("click", () => {
    spec.features = spec.features ?? [];
    spec.features.push({ type: "eye", on: spec.parts[spec.parts.length > 1 ? 1 : 0].id, at: 0.5, angles: [25, 335], size_mm: 8,
      color: spec.colors[spec.colors.length - 1].id });
    changed(true);
  });
  $("apply-json").addEventListener("click", () => {
    try { spec = JSON.parse($("json").value); if (!spec.features) spec.features = []; renderForm(); saveLocal(); solve(); }
    catch (error) { $("error").hidden = false; $("error").textContent = `JSON ungültig: ${error.message}`; }
  });
  $("verify").addEventListener("click", verify);
  $("download-pdf").addEventListener("click", async () => {
    const button = $("download-pdf"); button.disabled = true; button.textContent = "PDF wird erstellt …";
    try { await download("/api/figure/pdf", `${slug()}.pdf`); }
    finally { button.disabled = false; button.textContent = "Anleitung als PDF"; }
  });
  $("download-text").addEventListener("click", () => download("/api/figure/text", `${slug()}.txt`, "text/plain;charset=utf-8"));
  const saved = loadLocal();
  if (saved && saved.parts) { spec = saved; if (!spec.features) spec.features = []; renderForm(); solve(); }
  else loadTemplate(meta.templates[0].id);
}

start().catch(error => { $("error").hidden = false; $("error").textContent = `Start fehlgeschlagen: ${error.message}`; });
