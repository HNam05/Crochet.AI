# Independent prototype final-relation audit V1

This verifier package establishes the exact, narrow construction relation between
one retained native analytic proposal and its final prototype CrochetIR. It does
not call the solver, compiler, prototype generator or producer link validator.
The existing search audit independently establishes proposal membership. Neither
audit authenticates execution or proves physical suitability.

## Inputs and bounds

The standalone API operation `inspect_prototype_final_relation` accepts exactly
`api_version`, `operation`, `design_spec`, `material_profile`, `original_proposal`
and `crochet_ir` (the final artifact). No client reports, budgets or producer links.
Use existing API transport ceilings. Before validation/hashing, the pair inspector
bounds JSON depth to 64, nodes to 100,000, string values to 4,096 characters,
ASCII object keys to 128 characters and each IR
to 30,000 events/table entries, 512 courses and 256 parameters. These are software
resource ceilings, not numerical tolerances. Any tighter optional internal budget
must be a positive exact integer and exhaustion cannot PASS.

Validate both complete raw IRs with the supplied DesignSpec and MaterialProfile
registry; independently inspect their analytic claims. Bind the report to all four
canonical input hashes. Restrict this profile to the existing single component,
single branch, single yarn, closed clockwise continuous-spiral SC construction,
with one initial multi-site magic ring and one terminal close. Broader construction
and policy versions remain INDETERMINATE. Invalid artifacts fail admission.

## Exact relation

The native proposal has no `prototype.*` parameters. The final has exactly these
additional parameters, all independently checked against its actual construction:
`prototype.phase_policy = FIXED_ZERO_CONTINUOUS_V1`, `prototype.count_schedule`
and `prototype.final_phases`. Preserve every original parameter (including source
snapshot) and all other provenance fields except the parameter digest, which must
independently validate for each artifact. Compare JCS values, so booleans cannot
stand in for integers. Unknown policy/parameter semantics do not establish PASS.
Schedule strings are exact comma-joined ordinary decimal counts/zero phases
without signs, padding or whitespace; permissive integer parsing is insufficient.

Both actual schedules must have identical ordered round counts and balanced
SC/INC/DEC event positions. Every actual final round phase is zero. For each raw
artifact, additionally establish the exact ordered execution chain: ring creation,
each contiguous course and its event/frontier chain, then closure. The initial
frontier is exactly the ring's ordered sites, anchored at its first site. Each
stitch consumes its ordered consecutive span; its output preserves the incoming
anchor if that anchor survives, otherwise anchors at the first newly created top.
The output cycle must be exactly the input cycle with that span replaced by the
ordered new tops, normalized at that required anchor. Course output feeds the
next course input without a hidden rotation or reordered event. Closure retires
the complete final ordered cycle and yields an empty closed terminal.

After these raw predicates and the independent analytic cyclic-coverage checks,
compare execution-normalized semantic projections using the existing canonical
equivalence adapter. Remove only stitch `base_attachment_location_ids`, frontier
`attachment_location_ids` and `anchor_attachment_location_id`, and the retired
location arrays on ADVANCE/CLOSE transitions. These phase-dependent fields are
fully checked by the raw predicates; removing them alone would be unsound. Retain
every other semantic field, including event/course order, top producers/order,
transition references, ring sites, material hashes, colors, yarn paths, capability
versions, lifecycle states and work directions. Alpha-renamed IDs, entity-table
permutations, labels and derivations use the existing equivalence contract.
This is a phase-policy relation, not semantic equivalence of the two whole IRs.

Shared schema validation and canonical projection remain common dependencies.
The additive coordinate claims/replay scope independently checks coordinate
provenance before the unchanged relation checker can establish PASS. This does
not waive any raw frontier, schedule, source or semantic comparison predicate.
Adversarial tests must independently alter valid anchored frontiers/connections,
same-count construction, color and lineage, with refreshed producer digests.
At least one positive and negative pair must be hand-authored without compiling
the expected final IR. No golden changes or generation changes in this package.

## Report and V5 integration

The immutable deterministic report uses profile
`PROTOTYPE_FINAL_RELATION_AUDIT_V1`; its digest is SHA256 of ASCII(`Crochet.AI`)
+ NUL + ASCII(profile) + NUL + JCS(report). Include input hashes, assertions,
diagnostics, resource budgets, scope, and explicit unauthenticated execution and
UNTESTED physical status. Exact supported relation yields PASS; a contradicted
supported relation yields FAIL; unsupported scope/policy or exhausted proof yields
INDETERMINATE. PASS applies only to this relation.
The API data envelope contains `final_relation`, `final_relation_sha256`,
`verification_state` (REJECTED on FAIL, otherwise NOT_VERIFIED) and
`physical_status = UNTESTED`. V5 retains the same report under
`linked_evidence.final_relation` and includes its digest among produced hashes.

V5 considers the relation only after the retained-proposal search audit PASS.
Select a unique original by exact native provenance identity: final provenance
with the three prototype parameters and its parameter digest removed versus
native provenance with its parameter digest removed, sorting parameter names.
Zero or multiple matches cannot satisfy the relation. No first-match selection,
producer hash assertion, implicit backfill or recompilation of missing originals.
This lookup is lineage binding; it does not prove physical candidate selection.

Link the independent pair report/hash into V5 evidence. Only relation PASS removes
`final_candidate_to_original_proposal_relation`. A contradicted relation fails
V5. Legacy missing originals remain incomplete. Preserve
`deterministic_candidate_selection_and_tie_break` and `physical_verification`;
V5 remains INDETERMINATE, overall NOT_VERIFIED and physical UNTESTED. Keep the
existing exact three-field `search_evidence` envelope and all other gates.
