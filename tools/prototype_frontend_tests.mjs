import test from "node:test";
import assert from "node:assert/strict";
import { applySessionAcknowledgement, canStartProjectOperation, clampCursor, courseInstructionCount, decodeEnvelope, downloadName, feedbackPayload, readableRounds, sessionPayload, shapeExampleRequest, stitchCountAtCursor, stepForCursor, validateProject, validateShapeCatalog } from "../src/crochet_ai/prototype_static/state.mjs";

test("shape test examples preserve the crocheter's measured material values", () => {
  const catalog = [{id:"pear",label_de:"Birne",description_de:"Organische Testform",example_diameter_mm:40,example_height_mm:55}];
  const request = {shape:"sphere",diameter_mm:36,height_mm:36,stitches_per_100mm:22,courses_per_100mm:31,yarn_label:"Eigene Wolle",hook_diameter_mm:2.5};
  assert.deepEqual(shapeExampleRequest(request,catalog,"pear"),{...request,shape:"pear",diameter_mm:40,height_mm:55});
  assert.equal(request.shape,"sphere");
  assert.throws(()=>shapeExampleRequest(request,catalog,"torus"),/nicht unterstützt/);
  assert.throws(()=>validateShapeCatalog([...catalog,...catalog]),/ungültige/);
  assert.throws(()=>validateShapeCatalog([{...catalog[0],example_diameter_mm:NaN}]),/ungültige/);
});

function project() {
  return {
    project_id:"a".repeat(64), source_crochet_ir_sha256:"b".repeat(64), material_profile:{profile_id:"mp_local"},
    request:{shape:"sphere",diameter_mm:40}, verification_state:"NOT_VERIFIED", physical_status:"UNTESTED",
    session:{project_id:"a".repeat(64),revision:3,cursor:1}, pattern_text:"CROCHET PATTERN V1\n",
    courses:[{course_id:"c1",number:1,total_stitches:3,summary_de:"Runde 1",step_ids:["s1","s2"]}],
    steps:[
      {step_id:"s0",event_index:0,course_id:null,course_number:null,instruction_de:"Fadenring beginnen.",produced_stitches:0,course_stitches_after:0,top_location_ids:[]},
      {step_id:"s1",event_index:1,course_id:"c1",course_number:1,instruction_de:"1 feste Masche häkeln.",produced_stitches:1,course_stitches_after:1,top_location_ids:["l1"]},
      {step_id:"s2",event_index:2,course_id:"c1",course_number:1,instruction_de:"Eine Zunahme häkeln.",produced_stitches:2,course_stitches_after:3,top_location_ids:["l2","l3"]},
      {step_id:"s3",event_index:3,course_id:null,course_number:null,instruction_de:"Arbeit schließen.",produced_stitches:0,course_stitches_after:null,top_location_ids:[]}
    ],
    preview:{profile:"SCHEMATIC_COURSE_LAYOUT_V1",unit:"mm",role:"ILLUSTRATIVE_NOT_PHYSICAL",points:[{location_id:"l1",step_id:"s1",course_id:"c1",xyz_mm:[1,2,3],color_hex:"#B88757"},{location_id:"l2",step_id:"s2",course_id:"c1",xyz_mm:[2,2,3],color_hex:"#B88757"}]}
  };
}

test("cursor counts instruction events, including compound shaping as one step",()=>{
  const p=project();
  assert.equal(clampCursor(p,-2),0); assert.equal(clampCursor(p,99),4);
  assert.equal(stepForCursor(p,2).produced_stitches,2);
  assert.equal(stepForCursor(p,4),null);
  assert.equal(courseInstructionCount(p,"c1"),2);
});

test("session updates carry the exact optimistic revision and a bounded next-instruction cursor",()=>{
  const p=project();
  assert.deepEqual(sessionPayload(p,3,99),{prototype_version:"1.0.0",project_id:p.project_id,expected_revision:3,cursor:4});
  assert.throws(()=>sessionPayload(p,-1,0),/revision/);
});

test("live stitch count follows completed construction events rather than instruction count",()=>{
  const p=project();
  assert.equal(stitchCountAtCursor(p,0),0);
  assert.equal(stitchCountAtCursor(p,2),1);
  assert.equal(stitchCountAtCursor(p,3),3);
  assert.equal(stitchCountAtCursor(p,4),3);
});

test("project switching stays locked during session writes and acknowledged state is exported",()=>{
  assert.equal(canStartProjectOperation({}),true);
  assert.equal(canStartProjectOperation({sessionBusy:true}),false);
  assert.equal(canStartProjectOperation({sessionQueued:true}),false);
  assert.equal(canStartProjectOperation({projectOperation:true}),false);
  const p=project(); const session=applySessionAcknowledgement(p,2,{project_id:p.project_id,revision:4,cursor:2});
  assert.deepEqual(session,{project_id:p.project_id,revision:4,cursor:2});
  assert.throws(()=>applySessionAcknowledgement(p,3,{project_id:"other",revision:5,cursor:3}),/does not match/);
});

test("API envelope rejects conflict and malformed JSON without inventing success",async()=>{
  await assert.rejects(decodeEnvelope(new Response(JSON.stringify({ok:false,error:{code:"E_CONFLICT",reason:"Stale revision"}}),{status:409})),error=>error.status===409&&error.code==="E_CONFLICT"&&error.message==="Stale revision");
  await assert.rejects(decodeEnvelope(new Response("not-json",{status:200})),/Ungültige Serverantwort/);
  assert.deepEqual(await decodeEnvelope(new Response(JSON.stringify({ok:true,data:{revision:4,cursor:2}}),{status:200})),{revision:4,cursor:2});
});

test("project validation rejects broken course and schematic source links",()=>{
  const p=project(); assert.equal(validateProject(p),p);
  const broken=project();broken.preview.points[0].step_id="missing";
  assert.throws(()=>validateProject(broken),/resolve/);
  const unresolved=project();unresolved.steps[1].course_id="absent";
  assert.throws(()=>validateProject(unresolved),/unresolved/);
});

test("readable rounds preserve one instruction line for a compound increase and exact course count",()=>{
  const text=readableRounds(project());
  assert.match(text,/Vorbereitung[\s\S]*Fadenring/);assert.match(text,/Runde 1/);assert.match(text,/Eine Zunahme häkeln/);assert.match(text,/Maschen oben: 3/);assert.match(text,/Abschluss[\s\S]*Arbeit schließen/);
  assert.equal(text.split("Eine Zunahme häkeln").length-1,1);
});

test("feedback uses the selected source-bound project identity with only contract fields",()=>{
  const p=project();const payload=feedbackPayload(p,{outcome:"WORKED",notes:"Gut.",actual_diameter_mm:"39",actual_height_mm:""});
  assert.deepEqual(payload,{prototype_version:"1.0.0",project_id:p.project_id,outcome:"WORKED",notes:"Gut.",actual_diameter_mm:39,actual_height_mm:null});
  assert.equal(downloadName(p,"feedback.json"),`crochet-ai-${p.project_id.slice(0,16)}.feedback.json`);
  const missing={...p,source_crochet_ir_sha256:undefined};assert.throws(()=>feedbackPayload(missing,{}),/source-bound/);
});

test("a new course starts at zero, and closure cannot erase the last stitch count",()=>{
  const p=project();
  p.courses.push({course_id:"c2",number:2,total_stitches:2,summary_de:"Runde 2",step_ids:["d1","d2"]});
  p.steps.splice(3,0,{step_id:"d1",course_id:"c2",course_stitches_after:1,produced_stitches:1},{step_id:"d2",course_id:"c2",course_stitches_after:2,produced_stitches:1});
  p.steps.at(-1).course_stitches_after=0;
  assert.equal(stitchCountAtCursor(p,3),0);
  assert.equal(stitchCountAtCursor(p,4),1);
  assert.equal(stitchCountAtCursor(p,5),2);
  assert.equal(stitchCountAtCursor(p,6),2);
});
