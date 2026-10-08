"""Independent numeric oracles and refreshed untrusted coordinate-trace mutations."""

import ast
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE, config
from test_coordinate_target_adversarial import explicit_design

from crochet_ai.analytic_coordinate_target import admit_analytic_coordinate_target
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.analytic_trace_audit import inspect_analytic_search_trace
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.coordinate_meridian_replay import CoordinateMeridianReplay, CoordinateReplayError
from crochet_ai.trace_verification_types import TraceReplayBudgetExceeded, TraceReplayWork
from crochet_ai.validation import SemanticValidator


def numeric_replay(points, *, allowance=1e-8, budget=6_000_000):
    design, material = explicit_design(points)
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    target = admit_analytic_coordinate_target(design, validator)
    work = TraceReplayWork(budget)
    return CoordinateMeridianReplay.build(target, 0.05, allowance, 10000, work), work


@given(radius=st.integers(1, 12), height=st.integers(1, 12),
       numerator=st.integers(0, 100), offset=st.integers(-100, 100))
@settings(max_examples=40, deadline=None, derandomize=True)
def test_replay_matches_exact_orthogonal_cap_oracle(radius, height, numerator, offset):
    """Exact capped-cylinder formula; Hypothesis shrinks any false length/sample claim."""
    model, work = numeric_replay(
        [(0, offset), (radius, offset), (radius, offset + height), (0, offset + height)]
    )
    distance = Fraction(numerator, 100) * (2 * radius + height)
    if distance <= radius:
        r, z = distance, Fraction(offset)
    elif distance <= radius + height:
        r, z = Fraction(radius), offset + distance - radius
    else:
        r, z = 2 * radius + height - distance, Fraction(offset + height)
    result = model.sample(Fraction(numerator, 100), work)
    assert model.total == 2 * radius + height
    assert model.error_bound == 0
    assert abs(Fraction(result.radius_mm) - r) <= Fraction(1e-8)
    assert abs(Fraction(result.axial_mm) - z) <= Fraction(1e-8)
    assert abs(Fraction(result.s_mm) - distance) <= Fraction(1e-8)


@pytest.mark.parametrize("u", [Fraction(1, 17), Fraction(1, 3), Fraction(1, 2), Fraction(4, 5)])
def test_replay_nonmonotone_samples_against_decimal_square_root_oracle(u):
    """100-digit arithmetic, no producer/replay length or sampling helper as oracle."""
    points = [(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)]
    model, work = numeric_replay(points)
    result = model.sample(u, work)
    with localcontext() as context:
        context.prec = 100
        lengths = [Decimal((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2).sqrt()
                   for a, b in pairwise(points)]
        total = sum(lengths)
        distance = Decimal(u.numerator) / Decimal(u.denominator) * total
        consumed = Decimal(0)
        for index, length in enumerate(lengths):
            if distance <= consumed + length:
                weight = (distance - consumed) / length
                r0, z0 = points[index]
                r1, z1 = points[index + 1]
                r, z = Decimal(r0) + weight * (r1 - r0), Decimal(z0) + weight * (z1 - z0)
                break
            consumed += length
        else:
            raise AssertionError("Decimal oracle failed to locate sample")
        bound = 2 * Decimal.from_float(model.error_bound) + Decimal.from_float(1e-8)
        assert abs(Decimal.from_float(model.total_float) - total) <= bound
        assert abs(Decimal.from_float(result.radius_mm) - r) <= bound
        assert abs(Decimal.from_float(result.axial_mm) - z) <= bound


def test_numeric_replay_resource_and_roundoff_failures_never_produce_a_sample():
    with pytest.raises(TraceReplayBudgetExceeded):
        numeric_replay([(0, 0), (4, 0), (4, 6), (0, 6)], budget=1)
    model, work = numeric_replay([(0, 0), (3, 0), (0, 4)], allowance=1e-30)
    with pytest.raises(CoordinateReplayError):
        model.sample(Fraction(1, 3), work)
    with pytest.raises(CoordinateReplayError):
        numeric_replay([(0, 0), (4, 0), (4, 1e308), (0, 1e308)])


@pytest.mark.parametrize("u", [Fraction(0), Fraction(1, 7), Fraction(1, 2), Fraction(1)])
def test_replay_preserves_declared_signed_order_and_binary_scale_covariance(u):
    """Independent transformed input identities; exact coordinates within policy allowances."""
    points = [(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)]
    baseline, work = numeric_replay(points)
    expected = baseline.sample(u, work)
    for transformed, fraction, r_scale, z_scale in (
        (list(reversed(points)), 1 - u, 1, 1),
        ([(r, -z) for r, z in points], u, 1, -1),
        ([(2 * r, 2 * z) for r, z in points], u, 2, 2),
    ):
        model, changed_work = numeric_replay(transformed)
        actual = model.sample(fraction, changed_work)
        assert abs(actual.radius_mm - r_scale * expected.radius_mm) <= 1e-8
        assert abs(actual.axial_mm - z_scale * expected.axial_mm) <= 1e-8
        assert abs(model.total_float - abs(r_scale) * baseline.total_float) <= 1e-8


def coordinate_evidence():
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    batch = generate_analytic(design, material, config(), PROVENANCE)
    assert batch.candidates and batch.search_trace is not None
    wire = asdict(config())
    wire["minimum_shaping_separation_turns"] = "1/12"
    return {"design_spec": design, "material_profile": material, "run_config": wire,
            "search_trace": batch.search_trace.to_dict(),
            "candidate_proposals": [item.crochet_ir.to_dict() for item in batch.candidates]}


@pytest.fixture(scope="module")
def coordinate_trace():
    return coordinate_evidence()


def audit(values, **kwargs):
    design, material = values["design_spec"], values["material_profile"]
    validator = SemanticValidator(design_specs={design["design_spec_id"]: design},
                                  material_profiles={material["profile_id"]: material})
    return inspect_analytic_search_trace(design, material, values["run_config"],
                                         values["search_trace"], values["candidate_proposals"],
                                         validator=validator, **kwargs)


@pytest.mark.parametrize("field", ["s_mm", "radius_mm", "axial_mm"])
def test_refreshed_trace_digest_cannot_hide_a_false_coordinate_sample(coordinate_trace, field):
    values = deepcopy(coordinate_trace)
    sample = values["search_trace"]["hypotheses"][0]["samples"][0]
    changed = Fraction(sample[field]) + 1
    sample[field] = f"{changed.numerator}/{changed.denominator}"
    refreshed = sha256(b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0" +
                       jcs_bytes(values["search_trace"])).hexdigest()
    assert len(refreshed) == 64
    assert audit(values).status == "FAIL"


@pytest.mark.parametrize("mutation", ["drop_axial", "source", "budget", "work", "prefix"])
def test_binding_and_completeness_mutations_cannot_pass_coordinate_replay(
    coordinate_trace, mutation
):
    values = deepcopy(coordinate_trace)
    trace = values["search_trace"]
    if mutation == "drop_axial":
        del trace["hypotheses"][0]["samples"][0]["axial_mm"]
    elif mutation == "source":
        trace["source"]["source_snapshot_sha256"] = "c" * 64
    elif mutation == "budget":
        trace["budgets"]["numerics.max_arc_panels"] += 1
    elif mutation == "work":
        trace["terminal"]["work"]["count_transition_evaluations"] += 1
    else:
        trace["hypotheses"].pop()
    assert audit(values).status == "FAIL"


def test_coordinate_proof_exhaustion_and_missing_originals_stay_incomplete(coordinate_trace):
    assert audit(coordinate_trace).status == "PASS"
    exhausted = audit(coordinate_trace, max_replay_work=1)
    assert exhausted.status == "INDETERMINATE"
    assert "independent_replay_budget_exhausted" in exhausted.missing_checks
    values = deepcopy(coordinate_trace)
    values["candidate_proposals"] = []
    absent = audit(values)
    assert absent.status == "INDETERMINATE"
    assert "original_proposal_artifacts" in absent.missing_checks


def test_unknown_proposal_parameter_remains_incomplete_after_refreshing_every_digest(
    coordinate_trace,
):
    values = deepcopy(coordinate_trace)
    ir = values["candidate_proposals"][0]
    provenance = ir["provenance"]
    provenance["solver_parameters"].append({"name": "solver.future_policy", "value": 123})
    provenance["solver_parameters_sha256"] = sha256(
        b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0" +
        jcs_bytes(sorted(provenance["solver_parameters"], key=lambda row: row["name"]))
    ).hexdigest()
    design, material = values["design_spec"], values["material_profile"]
    validator = SemanticValidator(design_specs={design["design_spec_id"]: design},
                                  material_profiles={material["profile_id"]: material})
    digest = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
    trace = values["search_trace"]
    old = trace["terminal"]["proposal_ir_sha256"][0]
    trace["terminal"]["proposal_ir_sha256"][0] = digest
    for row in trace["hypotheses"]:
        if row.get("proposal_ir_sha256") == old:
            row["proposal_ir_sha256"] = digest
    report = audit(values)
    assert report.status == "INDETERMINATE", report.to_dict()
    assert any("unsupported_parameter:solver.future_policy" in v for v in report.missing_checks)


def test_verifier_import_boundary_includes_new_coordinate_numerical_kernel():
    forbidden = {"analytic_coordinate_meridian", "analytic_geometry", "analytic_solver",
                 "analytic_counts", "analytic_placement", "analytic_compile", "balanced_course"}
    root = Path(__file__).resolve().parents[1] / "src" / "crochet_ai"
    for name in ("coordinate_meridian_replay.py", "analytic_claims.py", "analytic_trace_audit.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert not any(module.split(".")[-1] in forbidden for module in imported)
