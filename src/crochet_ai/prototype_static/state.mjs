export function validateShapeCatalog(catalog) {
  if (!Array.isArray(catalog) || catalog.length === 0 || catalog.length > 16) throw new TypeError("Formkatalog fehlt oder ist ungültig");
  const ids = new Set();
  for (const shape of catalog) {
    if (!shape || typeof shape.id !== "string" || !/^[a-z_]+$/.test(shape.id) || ids.has(shape.id) || typeof shape.label_de !== "string" || typeof shape.description_de !== "string" || ![shape.example_diameter_mm, shape.example_height_mm].every(value => Number.isFinite(value) && value >= 20 && value <= 100)) throw new TypeError("Formkatalog enthält ungültige Beispiele");
    ids.add(shape.id);
  }
  return catalog;
}

export function shapeExampleRequest(request, catalog, shapeId) {
  const shape = validateShapeCatalog(catalog).find(item => item.id === shapeId);
  if (!shape) throw new TypeError("Diese Form wird nicht unterstützt");
  return { ...request, shape: shape.id, diameter_mm: shape.example_diameter_mm, height_mm: shape.example_height_mm };
}

export function stepForCursor(project, cursor) {
  if (!project || !Array.isArray(project.steps) || !Number.isInteger(cursor)) return null;
  if (cursor < 0 || cursor >= project.steps.length) return null;
  return project.steps[cursor];
}

export function clampCursor(project, cursor) {
  if (!project || !Array.isArray(project.steps) || !Number.isInteger(cursor)) throw new TypeError("Project steps and integer cursor are required");
  return Math.min(project.steps.length, Math.max(0, cursor));
}

export function courseInstructionCount(project, courseId) {
  if (!Array.isArray(project?.steps)) throw new TypeError("Project steps are required");
  return project.steps.filter(step => step.course_id === courseId).length;
}

export function stitchCountAtCursor(project, cursor) {
  const bounded = clampCursor(project, cursor);
  const currentCourse = project.steps[bounded]?.course_id;
  for (let index = Math.min(bounded - 1, project.steps.length - 1); index >= 0; index -= 1) {
    const step = project.steps[index];
    if (step.course_id === null) continue;
    if (currentCourse && step.course_id !== currentCourse) return 0;
    const count = step.course_stitches_after;
    if (Number.isSafeInteger(count) && count >= 0) return count;
  }
  return 0;
}

export function canStartProjectOperation(state) {
  return !state.sessionBusy && !state.sessionQueued && !state.projectOperation;
}

export function applySessionAcknowledgement(project, sentCursor, acknowledgement) {
  if (!project?.project_id || acknowledgement?.project_id !== project.project_id || !Number.isSafeInteger(acknowledgement.revision) || acknowledgement.revision < 0 || acknowledgement.cursor !== sentCursor) {
    throw new TypeError("Session acknowledgement does not match the saved project and cursor");
  }
  project.session = { project_id: project.project_id, revision: acknowledgement.revision, cursor: sentCursor };
  return project.session;
}

export function readableRounds(project) {
  if (!project || !Array.isArray(project.courses) || !Array.isArray(project.steps)) throw new TypeError("Complete project is required");
  const courses = new Map(project.courses.map(course => [course.course_id, course]));
  const courseStepCounts = new Map(project.courses.map(course => [course.course_id, courseInstructionCount(project, course.course_id)]));
  let current = undefined, inCourse = 0, output = [];
  for (const step of project.steps) {
    if (step.course_id !== current) {
      current = step.course_id; inCourse = 0;
      if (current === null) output.push(project.steps.findIndex(item => item.step_id === step.step_id) === 0 ? "Vorbereitung" : "Abschluss");
      else {
        const course = courses.get(current);
        if (!course) throw new TypeError("Project step refers to a missing course");
        output.push(course.summary_de);
      }
    }
    inCourse += 1; output.push(`  ${inCourse}. ${step.instruction_de}`);
    if (step.course_id && inCourse === courseStepCounts.get(step.course_id)) output.push(`Maschen oben: ${courses.get(step.course_id).total_stitches}`);
  }
  return output.join("\n");
}

export function validateProject(project) {
  if (!project || !Array.isArray(project.steps) || !Array.isArray(project.courses) || !Array.isArray(project.preview?.points)) throw new TypeError("Server returned an incomplete project");
  const courseIds = new Set(project.courses.map(c => c.course_id));
  if (project.steps.some(s => (s.course_id !== null && !courseIds.has(s.course_id)) || typeof s.step_id !== "string" || typeof s.instruction_de !== "string")) throw new TypeError("Project contains unresolved step references");
  const stepIds = new Set(project.steps.map(s => s.step_id));
  if (stepIds.size !== project.steps.length) throw new TypeError("Project contains duplicate steps");
  if (project.preview.points.some(p => !stepIds.has(p.step_id) || !Array.isArray(p.xyz_mm) || p.xyz_mm.length !== 3 || !p.xyz_mm.every(Number.isFinite))) throw new TypeError("Schematic points must resolve to finite project steps");
  return project;
}

export function feedbackPayload(project, values) {
  if (!project?.project_id || typeof project.source_crochet_ir_sha256 !== "string") throw new TypeError("A source-bound project is required");
  const measurement = value => value === "" ? null : Number(value);
  return {
    prototype_version: "1.0.0",
    project_id: project.project_id,
    outcome: values.outcome,
    notes: values.notes,
    actual_diameter_mm: measurement(values.actual_diameter_mm),
    actual_height_mm: measurement(values.actual_height_mm)
  };
}

export function sessionPayload(project, revision, cursor) {
  if (!project?.project_id || !Number.isSafeInteger(revision) || revision < 0) throw new TypeError("Project and current revision are required");
  return { prototype_version: "1.0.0", project_id: project.project_id, expected_revision: revision, cursor: clampCursor(project, cursor) };
}

export async function decodeEnvelope(response) {
  let envelope;
  try { envelope = await response.json(); } catch { throw new Error(`Ungültige Serverantwort (${response.status})`); }
  if (!response.ok || envelope?.ok !== true) {
    const failure = new Error(envelope?.error?.reason || `Anfrage fehlgeschlagen (${response.status})`);
    failure.code = envelope?.error?.code || `HTTP_${response.status}`;
    failure.status = response.status;
    throw failure;
  }
  return envelope.data;
}

export function downloadName(project, suffix) {
  const id = String(project?.project_id || "versuch").slice(0, 16).replace(/[^a-zA-Z0-9_-]/g, "_");
  return `crochet-ai-${id}.${suffix}`;
}
