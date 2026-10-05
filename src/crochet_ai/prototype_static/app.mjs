import { applySessionAcknowledgement, canStartProjectOperation, clampCursor, courseInstructionCount, decodeEnvelope, downloadName, feedbackPayload, readableRounds, sessionPayload, shapeExampleRequest, stitchCountAtCursor, validateProject, validateShapeCatalog } from "/state.mjs";
import { SchematicViewer } from "/viewer.mjs";

const $ = id => document.getElementById(id);
const form = $("generation-form"), feedbackForm = $("feedback-form");
form.elements.height_mm.disabled = true;
const viewer = new SchematicViewer($("object-view"), stepId => {
  if (!state.project) return;
  const index = state.project.steps.findIndex(step => step.step_id === stepId);
  if (index >= 0) setCursor(index);
});
const state = { csrf: null, defaults: null, shapeCatalog: [], project: null, cursor: 0, revision: 0, inputVersion: 0, request: null, sessionBusy: false, sessionQueued: false, projectOperation: false, conflict: false, feedbackLoaded: false, feedback: [], viewMode: "full" };

function shapeLabel(id) { return state.shapeCatalog.find(shape => shape.id === id)?.label_de || id; }
function updateShapeHelp() { $("shape-help").textContent = state.shapeCatalog.find(shape => shape.id === form.elements.shape.value)?.description_de || "Geschlossene Form in fortlaufenden Runden."; }

function announce(message) { $("live-message").textContent = message; }
function serialize(formElement) { return Object.fromEntries(new FormData(formElement).entries()); }
function numeric(value) { return Number(value); }
function requestBody() {
  const raw = serialize(form); const shape = raw.shape;
  return { prototype_version: "1.0.0", shape, diameter_mm: numeric(raw.diameter_mm), height_mm: shape === "sphere" ? numeric(raw.diameter_mm) : numeric(raw.height_mm), stitches_per_100mm: numeric(raw.stitches_per_100mm), courses_per_100mm: numeric(raw.courses_per_100mm), hook_diameter_mm: numeric(raw.hook_diameter_mm), yarn_label: raw.yarn_label, color_hex: raw.color_hex.toUpperCase(), uncertainty_percent: numeric(raw.uncertainty_percent) };
}
function projectMatchesForm(project) {
  if (!project?.request) return false;
  const current=requestBody(), saved=project.request;
  return ["shape","diameter_mm","height_mm","stitches_per_100mm","courses_per_100mm","hook_diameter_mm","yarn_label","color_hex","uncertainty_percent"].every(key => String(current[key]) === String(saved[key]));
}
function restoreRequest(project) {
  const request=project.request;
  for(const key of ["shape","diameter_mm","height_mm","stitches_per_100mm","courses_per_100mm","hook_diameter_mm","yarn_label","color_hex","uncertainty_percent"]) if(request[key] !== undefined) form.elements[key].value=request[key];
  form.elements.height_mm.disabled=form.elements.shape.value==="sphere";
  $("color-value").textContent=form.elements.color_hex.value.toUpperCase();
  updateShapeHelp();
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {}); headers.set("Accept", "application/json");
  if (options.body !== undefined) { headers.set("Content-Type", "application/json"); headers.set("X-CSRF-Token", state.csrf || ""); }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  return decodeEnvelope(response);
}
function showError(error, prefix = "") {
  const conflict = error.status === 409 || error.code === "E_CONFLICT";
  if (conflict) { state.conflict = true; state.sessionQueued=false; $("save-state").textContent = "Fortschritt kollidiert mit einer anderen Änderung. Projekt neu laden, bevor du weiterarbeitest."; }
  let message = error.message;
  if (message === "request.capsule_height") message = "Eine Kapsel benötigt mindestens so viel Höhe wie Durchmesser.";
  else if (message === "request.course_count_unsupported") message = "Diese Maße und Maschenprobe benötigen eine Rundenzahl außerhalb des Prototyp-Bereichs von 3 bis 32. Prüfe die Maschenprobe oder ändere die Maße.";
  else if (message.startsWith("generation.NO_FEASIBLE_CONSTRUCTION")) message = "Für diese Maße und Maschenprobe wurde innerhalb der unterstützten Grenzen keine ausführbare Anleitung gefunden. Probiere kleinere Maße oder prüfe die Maschenprobe.";
  else if (message.startsWith("generation.SEARCH_BUDGET_EXHAUSTED")) message = "Die begrenzte Suche konnte diese Form nicht vollständig berechnen. Es wurde kein unvollständiges Muster ausgewählt. Probiere kleinere Maße.";
  const text = `${prefix}${message}${conflict ? " Lade das Projekt aus der Liste neu." : ""}`;
  announce(text); $("project-description").textContent = text;
}
function saveFile(name, content, type) {
  const blob = new Blob([content], { type }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function refreshInteractionLocks() {
  const busy = state.projectOperation || state.sessionBusy || state.sessionQueued;
  $("generate-button").disabled = busy;
  $("load-shape-example").disabled = busy || !state.shapeCatalog.length;
  $("download-pdf").disabled = busy || !state.project;
  $("previous-step").disabled = !state.project || state.cursor <= 0 || state.conflict || state.projectOperation;
  $("next-step").disabled = !state.project || state.cursor >= state.project.steps.length || state.conflict || state.projectOperation;
  for (const button of document.querySelectorAll(".project-actions button")) button.disabled = busy;
  for (const field of feedbackForm.elements) field.disabled = busy || !state.project;
  $("feedback-button").disabled = busy || !state.project;
}
function renderProject() {
  const project = state.project;
  const hasProject = Boolean(project);
  $("making-view").disabled = !hasProject;
  for (const id of ["download-readable", "download-pattern", "download-project"]) $(id).disabled = !hasProject;
  $("download-feedback").disabled = !hasProject || !state.feedbackLoaded;
  $("previous-step").disabled = !hasProject || state.cursor <= 0 || state.conflict || state.projectOperation;
  $("next-step").disabled = !hasProject || state.cursor >= (project?.steps.length || 0) || state.conflict || state.projectOperation;
  if (!project) { viewer.setProject(null, 0); return; }
  $("project-title").textContent = `${shapeLabel(project.request.shape)} · ${project.request.diameter_mm} × ${project.request.height_mm} mm`;
  const inputsMatch=projectMatchesForm(project);
  $("verification-state").textContent = inputsMatch ? `${project.verification_state} · ${project.physical_status}` : `${project.verification_state} · Eingaben geändert`;
  $("project-description").textContent = inputsMatch ? `${project.steps.length} Arbeitsschritte. Versuchsmuster, nicht kalibriert oder physisch geprüft.` : "Eingaben wurden geändert. Die Arbeitsfläche zeigt weiterhin das zuvor erzeugte Muster; berechne neu, um passende Ergebnisse zu erhalten.";
  const current = project.steps[state.cursor];
  $("instruction-progress").textContent = `${state.cursor} von ${project.steps.length} Schritten erledigt`;
  const currentCourse = current?.course_id ? project.courses.find(course => course.course_id === current.course_id) : null;
  const liveCount=stitchCountAtCursor(project,state.cursor);
  const expectedAfter=current && Number.isSafeInteger(current.course_stitches_after) ? current.course_stitches_after : null;
  $("stitch-counter").textContent=currentCourse && expectedAfter !== null ? `${liveCount} aktuell · nach Schritt ${expectedAfter} von ${currentCourse.total_stitches} Maschen` : `${liveCount} Maschen aktuell`;
  $("instruction-heading").textContent = current ? `${current.course_number ? `Runde ${current.course_number}` : "Vorbereitung / Abschluss"} · Schritt ${state.cursor + 1}` : "Versuch abgeschlossen";
  $("instruction-text").textContent = current ? current.instruction_de : "Alle Schritte der Anleitung wurden durchgearbeitet.";
  viewer.setProject(project, state.cursor);
  viewer.setMode(state.viewMode);
  renderRounds();
  refreshInteractionLocks();
}
function renderRounds() {
  const project = state.project, list = $("round-list"); list.replaceChildren();
  if (!project) { list.innerHTML = '<li class="empty">Nach der Berechnung erscheinen hier die Runden.</li>'; return; }
  const currentCourse = project.steps[state.cursor]?.course_id;
  const populate = (details, entries) => {
    if (details.dataset.populated === "true") return;
    const stepList=document.createElement("ol");stepList.className="round-steps";
    for(const item of entries){const line=document.createElement("li"),select=document.createElement("button");select.type="button";select.textContent=item.step.instruction_de;select.setAttribute("aria-current",String(item.index===state.cursor));select.addEventListener("click",()=>setCursor(item.index));line.append(select);stepList.append(line);}
    details.append(stepList);details.dataset.populated="true";
  };
  for (const course of project.courses) {
    const li = document.createElement("li"),details=document.createElement("details");details.open=course.course_id===currentCourse;
    const button = document.createElement("summary"); button.setAttribute("aria-current", String(course.course_id === currentCourse));
    const title = document.createElement("span"); title.className = "round-title"; title.textContent = course.summary_de;
    const meta = document.createElement("span"); meta.className = "round-meta"; meta.textContent = `${courseInstructionCount(project, course.course_id)} Schritte · ${course.total_stitches} Maschen`;
    button.append(title, meta);details.append(button);
    const steps = project.steps.map((step,index)=>({step,index})).filter(item=>item.step.course_id===course.course_id);
    details.addEventListener("toggle",()=>{if(!details.open)return;populate(details,steps);if(project.steps[state.cursor]?.course_id!==course.course_id){const first=steps[0]?.index;if(first!==undefined)setCursor(first);}});
    if(details.open)populate(details,steps);li.append(details); list.append(li);
  }
  const ungrouped = project.steps.map((step,index)=>({step,index})).filter(item=>!item.step.course_id);
  if (ungrouped.length) { const li=document.createElement("li"), details=document.createElement("details"),summary=document.createElement("summary");summary.textContent="Vorbereitung und Abschluss";details.open=currentCourse===null;details.append(summary);details.addEventListener("toggle",()=>{if(!details.open)return;populate(details,ungrouped);if(project.steps[state.cursor]?.course_id!==null){const first=ungrouped[0]?.index;if(first!==undefined)setCursor(first);}});if(details.open)populate(details,ungrouped);li.append(details);list.prepend(li); }
  $("round-count").textContent = `${project.courses.length} Runden`;
}
function setCursor(value) {
  if (!state.project || state.projectOperation || state.conflict) return;
  state.cursor = clampCursor(state.project, value); viewer.setCursor(state.cursor); renderProject(); queueSessionSave();
}
function queueSessionSave() {
  if (!state.project || state.conflict) return;
  state.sessionQueued = true; if (!state.sessionBusy) void flushSession();
}
async function flushSession() {
  if (!state.sessionQueued || state.sessionBusy || !state.project || state.conflict) return;
  state.sessionQueued = false; state.sessionBusy = true; const projectId=state.project.project_id, cursor=state.cursor, revision=state.revision;
  $("save-state").textContent="Speichere Fortschritt …";refreshInteractionLocks();
  try {
    const data = await api("/api/session", { method:"POST", body:JSON.stringify(sessionPayload(state.project,revision,cursor)) });
    if (state.project?.project_id === projectId) { applySessionAcknowledgement(state.project,cursor,data);state.revision=data.revision; $("save-state").textContent="Fortschritt lokal gespeichert."; }
  } catch(error) { showError(error,"Fortschritt nicht gespeichert: "); }
  finally { state.sessionBusy=false;refreshInteractionLocks();if(state.sessionQueued && !state.conflict) void flushSession(); }
}
async function loadProject(projectId) {
  if(!canStartProjectOperation(state))return;
  state.projectOperation=true;refreshInteractionLocks();
  try {
    const project=validateProject(await api(`/api/projects/${encodeURIComponent(projectId)}`));
    state.project=project;$("pdf-status").textContent="PDF enthält das ausgewählte Muster, Materialwerte und ein Rückmeldeblatt.";restoreRequest(project);state.revision=project.session.revision;state.cursor=clampCursor(project,project.session.cursor);state.conflict=false;state.feedback=[];state.feedbackLoaded=false;feedbackForm.reset();
    $("save-state").textContent="Gespeicherter Fortschritt geladen.";renderProject();await refreshFeedback();announce("Projekt und gespeicherter Fortschritt geladen.");
  } catch(error){showError(error,"Projekt konnte nicht geladen werden: ");}
  finally{state.projectOperation=false;refreshInteractionLocks();renderProject();}
}
async function loadProjects() {
  const list=$("project-list");
  try {
    const data=await api("/api/projects"); if(!Array.isArray(data.projects))throw new Error("Ungültige Projektliste vom Server");list.replaceChildren();
    if(!data.projects.length){const li=document.createElement("li");li.className="empty";li.textContent="Noch keine gespeicherten Muster.";list.append(li);return;}
    for(const summary of data.projects){const li=document.createElement("li"),info=document.createElement("div"),name=document.createElement("strong"),meta=document.createElement("span"),actions=document.createElement("div"),button=document.createElement("button");const display=summary.display_name||summary.name||(summary.shape?`${shapeLabel(summary.shape)} · ${summary.diameter_mm??"?"}${summary.shape!=="sphere"?` × ${summary.height_mm??"?"}`:""} mm · ${summary.yarn_label||"Garn"}`:"Versuchsmuster");info.className="project-info";name.textContent=display;meta.textContent=`Kennung ${summary.project_id.slice(0,16)} · ungeprüft`;meta.title=summary.project_id;info.append(name,meta);actions.className="project-actions";button.type="button";button.textContent="Laden und fortsetzen";button.disabled=state.projectOperation||state.sessionBusy||state.sessionQueued;button.addEventListener("click",()=>void loadProject(summary.project_id));actions.append(button);li.append(info,actions);list.append(li);}
  } catch(error){list.replaceChildren();const li=document.createElement("li");li.className="empty";li.textContent=`Projekte konnten nicht geladen werden: ${error.message}`;list.append(li);}
}
async function refreshFeedback() {
  if(!state.project)return;
  const projectId=state.project.project_id;
  try{const data=await api(`/api/projects/${encodeURIComponent(projectId)}/feedback`);if(!Array.isArray(data.feedback))throw new Error("Ungültige Rückmeldungsantwort");if(state.project?.project_id!==projectId)return;state.feedback=data.feedback;state.feedbackLoaded=true;$("download-feedback").disabled=false;}
  catch(error){if(state.project?.project_id!==projectId)return;state.feedback=[];state.feedbackLoaded=false;$("download-feedback").disabled=true;announce(`Rückmeldungen konnten nicht geladen werden: ${error.message}`);}
}

$("shape").addEventListener("change",()=>{updateShapeHelp();form.elements.height_mm.disabled=form.elements.shape.value==="sphere";if(form.elements.shape.value==="sphere")form.elements.height_mm.value=form.elements.diameter_mm.value;});
form.elements.diameter_mm.addEventListener("input",()=>{state.inputVersion++;if(form.elements.shape.value==="sphere")form.elements.height_mm.value=form.elements.diameter_mm.value;});
form.addEventListener("input",event=>{if(event.target.name!=="diameter_mm")state.inputVersion++;if(event.target.name==="color_hex")$("color-value").textContent=event.target.value.toUpperCase();if(state.request)state.request.abort();if(state.project){const matches=projectMatchesForm(state.project);$("verification-state").textContent=matches?`${state.project.verification_state} · ${state.project.physical_status}`:`${state.project.verification_state} · Eingaben geändert`;$("project-description").textContent=matches?`${state.project.steps.length} Arbeitsschritte. Versuchsmuster, nicht kalibriert oder physisch geprüft.`:"Eingaben wurden geändert. Die Arbeitsfläche zeigt weiterhin das zuvor erzeugte Muster; berechne neu, um passende Ergebnisse zu erhalten.";}});
form.addEventListener("submit",async event=>{
  event.preventDefault();if(!canStartProjectOperation(state))return;state.projectOperation=true;refreshInteractionLocks();const version=state.inputVersion, controller=new AbortController(); if(state.request)state.request.abort();state.request=controller;
  $("generate-button").textContent="Berechne Muster …";$("project-description").textContent="Der lokale Generator erstellt und prüft ein Versuchsmuster …";
  try{const project=validateProject(await api("/api/generate",{method:"POST",body:JSON.stringify(requestBody()),signal:controller.signal}));if(version!==state.inputVersion||controller.signal.aborted){announce("Eingaben wurden geändert; dieses Ergebnis wurde nicht ausgewählt.");$("project-description").textContent="Eingaben geändert. Starte die Berechnung erneut, um ein passendes Ergebnis auszuwählen.";}else{state.project=project;$("pdf-status").textContent="PDF enthält das ausgewählte Muster, Materialwerte und ein Rückmeldeblatt.";restoreRequest(project);state.revision=project.session.revision;state.cursor=clampCursor(project,project.session.cursor);state.conflict=false;state.feedback=[];state.feedbackLoaded=false;feedbackForm.reset();renderProject();await loadProjects();await refreshFeedback();announce("Versuchsmuster berechnet und lokal gespeichert.");}}
  catch(error){if(error.name==="AbortError"){if(state.project)renderProject();else $("project-description").textContent="Berechnung abgebrochen, weil sich Eingaben geändert haben. Starte sie mit den neuen Werten erneut.";announce("Berechnung abgebrochen, weil sich Eingaben geändert haben.");}else showError(error,"Muster konnte nicht berechnet werden: ");}
  finally{if(state.request===controller)state.request=null;state.projectOperation=false;$("generate-button").textContent="Muster berechnen";refreshInteractionLocks();}
});
$("previous-step").addEventListener("click",()=>setCursor(state.cursor-1));$("next-step").addEventListener("click",()=>setCursor(state.cursor+1));
window.addEventListener("keydown",event=>{if(event.altKey||event.ctrlKey||event.metaKey||event.repeat)return;const target=event.target;if(target instanceof HTMLElement&&(target.isContentEditable||target.matches("input,textarea,select,button,a,canvas,[role=button]")))return;if(event.key==="ArrowLeft"){if(state.project&&state.cursor>0){setCursor(state.cursor-1);event.preventDefault();}}else if(event.key==="ArrowRight"||event.key===" "){if(state.project&&state.cursor<state.project.steps.length){setCursor(state.cursor+1);event.preventDefault();}}});
$("making-view").addEventListener("click",()=>{const active=document.body.classList.toggle("making-view");$("making-view").setAttribute("aria-pressed",String(active));$("making-view").textContent=active?"Entwurf bearbeiten":"Häkelansicht öffnen";requestAnimationFrame(()=>window.scrollTo({top:0}));});
$("reset-view").addEventListener("click",()=>viewer.reset());$("zoom-in").addEventListener("click",()=>viewer.zoomBy(1.2));$("zoom-out").addEventListener("click",()=>viewer.zoomBy(1/1.2));$("refresh-projects").addEventListener("click",()=>void loadProjects());
$("view-full").addEventListener("click",()=>{state.viewMode="full";viewer.setMode("full");$("view-full").setAttribute("aria-pressed","true");$("view-progress").setAttribute("aria-pressed","false");});
$("view-progress").addEventListener("click",()=>{state.viewMode="progress";viewer.setMode("progress");$("view-full").setAttribute("aria-pressed","false");$("view-progress").setAttribute("aria-pressed","true");});
$("download-readable").addEventListener("click",()=>{if(state.project)saveFile(downloadName(state.project,"txt"),`Crochet.AI · Versuchsmuster\nStatus: ${state.project.verification_state} / ${state.project.physical_status}\n\n${readableRounds(state.project)}\n`,"text/plain;charset=utf-8");});
$("download-pattern").addEventListener("click",()=>{if(state.project)saveFile(downloadName(state.project,"pattern-v1.txt"),state.project.pattern_text,"text/plain;charset=utf-8");});
$("download-project").addEventListener("click",()=>{if(state.project)saveFile(downloadName(state.project,"json"),JSON.stringify(state.project,null,2),"application/json;charset=utf-8");});
$("download-pdf").addEventListener("click", async () => {
  if (!state.project || !canStartProjectOperation(state)) return;
  const project = state.project;
  state.projectOperation = true; refreshInteractionLocks();
  $("pdf-status").textContent = "Erstelle PDF für das ausgewählte, gespeicherte Muster …";
  try {
    const response = await fetch(`/api/projects/${encodeURIComponent(project.project_id)}/pattern.pdf`, {credentials:"same-origin",cache:"no-store"});
    if (!response.ok) await decodeEnvelope(response);
    if (!response.headers.get("Content-Type")?.startsWith("application/pdf")) throw new Error("Der Dienst lieferte keine PDF-Datei");
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length < 5 || new TextDecoder().decode(bytes.slice(0,5)) !== "%PDF-") throw new Error("Die PDF-Datei ist unvollständig");
    saveFile(downloadName(project,"pdf"), bytes, "application/pdf");
    $("pdf-status").textContent = `PDF für ${shapeLabel(project.request.shape)} erstellt; Download gestartet. Materialwerte und Testbericht sind enthalten; das Muster bleibt physisch ungeprüft.`;
  } catch (error) {
    const message = error.message.includes("unsupported_unicode") ? "Ein Zeichen in der Garnbezeichnung wird im PDF nicht unterstützt. Verwende für den Export Buchstaben ohne Sonderzeichen außerhalb des deutschen Zeichensatzes." : error.message;
    $("pdf-status").textContent = `PDF konnte nicht erstellt werden: ${message}`;
    announce($("pdf-status").textContent);
  } finally { state.projectOperation = false; refreshInteractionLocks(); }
});
$("load-shape-example").addEventListener("click", () => {
  if (!canStartProjectOperation(state)) return;
  const example = shapeExampleRequest(requestBody(), state.shapeCatalog, form.elements.shape.value);
  restoreRequest({request:example}); state.inputVersion++;
  if (state.request) state.request.abort();
  if (state.project) renderProject();
  announce("Beispielmaße geladen. Deine Maschenprobe und Garnwerte bleiben erhalten. Muster neu berechnen.");
});
feedbackForm.addEventListener("submit",async event=>{event.preventDefault();if(!state.project||!canStartProjectOperation(state))return;const values=serialize(feedbackForm);const project=state.project;state.projectOperation=true;refreshInteractionLocks();try{const payload=feedbackPayload(project,values);const result=await api("/api/feedback",{method:"POST",body:JSON.stringify(payload)});if(state.project?.project_id!==project.project_id){announce("Rückmeldung gespeichert, aber das ausgewählte Projekt wurde inzwischen gewechselt.");return;}state.feedback.push(result);saveFile(downloadName(project,"feedback.json"),JSON.stringify({project_id:project.project_id,source_crochet_ir_sha256:project.source_crochet_ir_sha256,material_profile:project.material_profile,feedback:state.feedback},null,2),"application/json;charset=utf-8");feedbackForm.reset();announce("Rückmeldung quellgebunden lokal gespeichert.");}catch(error){showError(error,"Rückmeldung konnte nicht gespeichert werden: ");}finally{state.projectOperation=false;refreshInteractionLocks();}});
$("download-feedback").addEventListener("click",()=>{if(state.project)saveFile(downloadName(state.project,"feedback.json"),JSON.stringify({project_id:state.project.project_id,source_crochet_ir_sha256:state.project.source_crochet_ir_sha256,material_profile:state.project.material_profile,feedback:state.feedback},null,2),"application/json;charset=utf-8");});
async function bootstrap(){try{const data=await api("/api/bootstrap");if(data.prototype_version!=="1.0.0"||typeof data.csrf_token!=="string"||!data.default_request)throw new Error("Prototyp-Version oder Startdaten werden nicht unterstützt");state.csrf=data.csrf_token;state.defaults=data.default_request;state.shapeCatalog=validateShapeCatalog(data.shape_catalog);form.elements.shape.replaceChildren(...state.shapeCatalog.map(shape=>{const option=document.createElement("option");option.value=shape.id;option.textContent=shape.label_de;return option;}));restoreRequest({request:state.defaults});refreshInteractionLocks();await loadProjects();$("save-state").textContent="Lokal verbunden. Fortschritt wird beim Schrittwechsel gespeichert.";}catch(error){$("project-description").textContent=`Lokaler Dienst nicht bereit: ${error.message}`;announce(`Lokaler Dienst nicht bereit: ${error.message}`);}}
void bootstrap();
