#!/usr/bin/env node
/* Narrow, independent Node.js RFC 8785/JCS and project-profile vector checker. */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const profiles = new Set([
  "DESIGN_SPEC_CANONICAL_JSON_V1",
  "CROCHET_IR_CANONICAL_JSON_V1",
  "MATERIAL_PROFILE_CANONICAL_JSON_V1",
  "CROCHET_SEMANTIC_EQUIVALENCE_V1",
]);

function reject(message) {
  throw new Error(message);
}

function assertIJson(value, path = "") {
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || !Number.isSafeInteger(value) && Number.isInteger(value)) {
      reject(`invalid I-JSON number at ${path || "/"}`);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((child, index) => assertIJson(child, `${path}/${index}`));
    return;
  }
  if (typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      assertIJson(key, `${path}/<key>`);
      assertIJson(child, `${path}/${key}`);
    }
    return;
  }
  reject(`unsupported JSON value at ${path || "/"}`);
}

function jcs(value) {
  assertIJson(value);
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(jcs).join(",")}]`;
  const keys = Object.keys(value).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${jcs(value[key])}`).join(",")}}`;
}

function sortByJcs(items) {
  return [...items].sort((left, right) => Buffer.compare(Buffer.from(jcs(left)), Buffer.from(jcs(right))));
}

function compareCodePoints(left, right) {
  const a = [...left];
  const b = [...right];
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    const difference = a[index].codePointAt(0) - b[index].codePointAt(0);
    if (difference !== 0) return difference;
  }
  return a.length - b.length;
}

function materialProjection(value) {
  const result = structuredClone(value);
  const responseIds = new Set();
  const semanticKeys = new Set();
  for (const response of result.calibration_responses) {
    const conditions = response.measurement_conditions;
    const semanticKey = [
      conditions.canonical_stitch_type,
      conditions.course_mode,
      conditions.tension_profile_id,
      conditions.fabric_state,
    ].join("\u0000");
    if (responseIds.has(response.response_id) || semanticKeys.has(semanticKey)) {
      reject("duplicate material response identity");
    }
    responseIds.add(response.response_id);
    semanticKeys.add(semanticKey);
    const observations = sortByJcs(response.observations);
    if (new Set(observations.map(jcs)).size !== observations.length) reject("duplicate observation");
    response.observations = observations;
  }
  result.calibration_responses.sort((left, right) => {
    const a = left.measurement_conditions;
    const b = right.measurement_conditions;
    return compareCodePoints(
      [a.canonical_stitch_type, a.course_mode, a.tension_profile_id, a.fabric_state, left.response_id].join("\u0000"),
      [b.canonical_stitch_type, b.course_mode, b.tension_profile_id, b.fabric_state, b.response_id].join("\u0000"),
    );
  });
  if (new Set(result.provenance.source_record_ids).size !== result.provenance.source_record_ids.length) {
    reject("duplicate source record");
  }
  result.provenance.source_record_ids.sort(compareCodePoints);
  return result;
}

function sortByField(items, field) {
  return [...items].sort((left, right) => {
    if (typeof left[field] === "number") return left[field] - right[field];
    return compareCodePoints(left[field], right[field]);
  });
}

function designProjection(value) {
  const result = structuredClone(value);
  if (result.material_profile.binding_type === "INLINE") result.material_profile.profile = materialProjection(result.material_profile.profile);
  result.dimensions.measurements = sortByField(result.dimensions.measurements, "measurement_id");
  for (const [field, id] of [["symmetries", "symmetry_id"], ["landmarks", "landmark_id"], ["colors", "color_id"]]) {
    result[field] = sortByField(result[field], id);
  }
  if ("parameters" in result.target_geometry) result.target_geometry.parameters = sortByField(result.target_geometry.parameters, "parameter");
  const orders = {
    allowed_join_methods: ["CROCHETED", "SEWN"],
    allowed_stitch_types: ["CHAIN", "SLIP_STITCH", "SINGLE_CROCHET", "HALF_DOUBLE_CROCHET", "DOUBLE_CROCHET", "TREBLE_CROCHET"],
    allowed_shaping: ["INCREASE", "DECREASE"],
    allowed_construction_operations: ["MAGIC_RING", "JOIN", "SPLIT", "RESERVE", "ATTACH", "COLOR_CHANGE", "CUT_YARN", "CLOSE", "DECLARE_OPENING"],
    allowed_solver_families: ["ANALYTIC", "GEODESIC", "FRONTIER", "GARMENT", "FLAT", "LACE"],
    required_geometry_metrics: ["SYMMETRIC_CHAMFER", "PERCENTILE_HAUSDORFF", "SILHOUETTE_IOU", "CROSS_SECTION_ERROR", "VOLUME_ERROR", "LANDMARK_DEVIATION", "NORMAL_DEVIATION", "CURVATURE_DIAGNOSTIC", "TOPOLOGY"],
  };
  for (const [field, order] of Object.entries(orders)) {
    const holder = field in result.construction_constraints ? result.construction_constraints : field in result.difficulty_constraints ? result.difficulty_constraints : field in result.solver_options ? result.solver_options : result.verification_requirements;
    holder[field].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  }
  result.construction_constraints.intentional_openings = sortByField(result.construction_constraints.intentional_openings, "opening_requirement_id");
  result.construction_constraints.intentional_openings.forEach((item) => item.boundary_landmark_ids.sort());
  result.colors.forEach((color) => color.roles.sort(compareCodePoints));
  result.verification_requirements.required_gates.sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
  result.interpretation_provenance.source_artifacts = sortByField(result.interpretation_provenance.source_artifacts, "artifact_id");
  result.interpretation_provenance.assumptions = sortByField(result.interpretation_provenance.assumptions, "assumption_id");
  return result;
}

function irProjection(value) {
  const result = structuredClone(value);
  const tables = {
    colors: "color_id", yarns: "yarn_id", attachment_locations: "attachment_location_id", stitches: "stitch_id",
    construction_operations: "operation_id", courses: "course_id", frontiers: "frontier_id", branches: "branch_id",
    components: "component_id", openings: "opening_id", yarn_paths: "yarn_path_id", derivations: "derivation_id",
  };
  for (const [table, id] of Object.entries(tables)) result[table] = sortByField(result[table], id);
  result.construction_sequence = sortByField(result.construction_sequence, "sequence_index");
  result.frontier_transitions = sortByField(result.frontier_transitions, "transition_index");
  result.required_capabilities.sort();
  result.branches.forEach((branch) => { branch.parent_branch_ids.sort(); branch.course_ids.sort(); });
  result.components.forEach((component) => component.branch_ids.sort());
  result.derivations.forEach((derivation) => derivation.subject_refs.sort((a, b) => {
    const aId = a[Object.keys(a).find((key) => key.endsWith("_id"))];
    const bId = b[Object.keys(b).find((key) => key.endsWith("_id"))];
    return compareCodePoints(`${a.entity_type}\u0000${aId}`, `${b.entity_type}\u0000${bId}`);
  }));
  result.provenance.input_artifacts = sortByField(result.provenance.input_artifacts, "artifact_id");
  result.provenance.solver_parameters = sortByField(result.provenance.solver_parameters, "name");
  return result;
}

function project(input, profile) {
  if (!profiles.has(profile)) reject(`unsupported profile ${profile}`);
  if (profile === "MATERIAL_PROFILE_CANONICAL_JSON_V1" && "profile_id" in input) return materialProjection(input);
  if (profile === "DESIGN_SPEC_CANONICAL_JSON_V1" && "design_spec_id" in input) return designProjection(input);
  if (profile === "CROCHET_IR_CANONICAL_JSON_V1" && "crochet_ir_id" in input) return irProjection(input);
  return input;
}

function digest(profile, canonicalJson) {
  const prefix = `Crochet.AI\0${profile}\0`;
  const preimage = Buffer.from(prefix + canonicalJson, "utf8");
  return {
    prefix,
    preimage,
    sha256: createHash("sha256").update(preimage).digest("hex"),
  };
}

const vectors = JSON.parse(readFileSync(process.argv[2], "utf8"));
let failed = false;
for (const vector of vectors) {
  try {
    const input = vector.input_file
      ? JSON.parse(readFileSync(vector.input_file, "utf8"))
      : vector.input;
    if (vector.inline_material_file) {
      input.material_profile = {
        binding_type: "INLINE",
        profile: JSON.parse(readFileSync(vector.inline_material_file, "utf8")),
      };
    }
    const canonicalJson = jcs(project(input, vector.profile));
    const expectedCanonicalJson = vector.expected_canonical_file
      ? readFileSync(vector.expected_canonical_file, "utf8").replace(/\r?\n$/, "")
      : vector.expected_canonical_json;
    const result = digest(vector.profile, canonicalJson);
    if (
      (expectedCanonicalJson && canonicalJson !== expectedCanonicalJson)
      || (vector.expected_preimage_prefix_ascii && result.prefix !== vector.expected_preimage_prefix_ascii)
      || (
        expectedCanonicalJson
        && !result.preimage.equals(Buffer.from(result.prefix + expectedCanonicalJson, "utf8"))
      )
      || result.sha256 !== vector.expected_sha256
    ) {
      throw new Error("canonical JSON or hash mismatch");
    }
    console.log(`PASS ${vector.id}: canonical JSON, UTF-8 preimage, SHA-256`);
  } catch (error) {
    failed = true;
    console.error(`FAIL ${vector.id}: ${error.message}`);
  }
}
process.exitCode = failed ? 1 : 0;
