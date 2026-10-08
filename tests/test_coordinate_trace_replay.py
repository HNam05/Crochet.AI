"""Independent replay tests against exact and Decimal coordinate oracles."""

from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from sys import float_info
from types import SimpleNamespace

import pytest
import rfc8785
from test_analytic_solver import PROVENANCE, config
from test_coordinate_target_adversarial import explicit_design

from crochet_ai.analytic_claims import inspect_analytic_candidate_claims
from crochet_ai.analytic_coordinate_target import admit_analytic_coordinate_target
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.analytic_trace_audit import inspect_analytic_search_trace
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.coordinate_meridian_replay import CoordinateMeridianReplay, CoordinateReplayError
from crochet_ai.solver_types import GenerationStatus
from crochet_ai.trace_verification_types import TraceReplayWork
from crochet_ai.validation import SemanticValidator


def _replay(points, *, arc_tolerance=0.05, roundoff=1e-8, limit=10_000):
    design, material = explicit_design(points)
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    target = admit_analytic_coordinate_target(design, validator)
    result = CoordinateMeridianReplay.build(
        target, arc_tolerance, roundoff, limit, TraceReplayWork()
    )
    return result


def test_three_four_five_total_and_exact_knot_sampling():
    replay = _replay([(0, 0), (3, 0), (0, 4)])
    assert replay.total == 8
    at_knot = replay.sample(Fraction(3, 8), TraceReplayWork())
    assert (at_knot.radius_mm, at_knot.axial_mm) == (3.0, 0.0)
    capped = _replay([(0, -2), (3, -2), (3, 2), (0, 2)])
    assert capped.total == 10
    assert capped.sample(Fraction(1, 2), TraceReplayWork()).axial_mm == 0.0


def test_nonmonotone_signed_axial_samples_against_decimal_linear_scan():
    points = [(0, -1), (4, 0), (4, 6), (2, 4), (0, 5)]
    replay = _replay(points)
    fraction = Fraction(1, 3)
    with localcontext() as context:
        context.prec = 100
        dec_points = [(Decimal(r), Decimal(z)) for r, z in points]
        lengths = [
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2).sqrt() for a, b in pairwise(dec_points)
        ]
        desired = Decimal(fraction.numerator) / Decimal(fraction.denominator) * sum(lengths)
        for index, length in enumerate(lengths):
            if desired <= length:
                weight = desired / length
                expected = tuple(
                    dec_points[index][axis]
                    + weight * (dec_points[index + 1][axis] - dec_points[index][axis])
                    for axis in (0, 1)
                )
                break
            desired -= length
    sample = replay.sample(fraction, TraceReplayWork())
    assert sample.radius_mm == pytest.approx(float(expected[0]), abs=1e-7)
    assert sample.axial_mm == pytest.approx(float(expected[1]), abs=1e-7)
    reflected = _replay([(r, -z) for r, z in points]).sample(fraction, TraceReplayWork())
    assert reflected.radius_mm == sample.radius_mm
    assert reflected.axial_mm == -sample.axial_mm


def test_coordinate_replay_fails_closed_on_segment_and_conditioning_budgets():
    with pytest.raises(CoordinateReplayError, match="segment_budget"):
        _replay([(0, 0), (3, 0), (3, 4), (0, 4)], limit=2)
    with pytest.raises(CoordinateReplayError, match="numerics"):
        _replay([(0, 0), (3, 0), (0, 4)], limit=200_001)
    with pytest.raises(CoordinateReplayError, match=r"length_conversion|arc_tolerance"):
        _replay([(0, 0), (3, 1), (0, 4)], arc_tolerance=1e-20, roundoff=1e-21)
    replay = _replay([(0, 0), (3, 0), (0, 4)])
    work = TraceReplayWork(1)
    with pytest.raises(ValueError, match="replay_budget_exhausted"):
        replay.sample(Fraction(1, 2), work)


def test_sqrt_bracket_uses_at_most_two_neighbors_and_rejects_infinity(monkeypatch):
    import crochet_ai.coordinate_meridian_replay as kernel

    design, material = explicit_design([(0, 0), (3, 1), (0, 4)])
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    target = admit_analytic_coordinate_target(design, validator)
    original_neighbor = kernel._neighbor
    neighbors = []

    def counted_neighbor(value, upward):
        neighbors.append((value, upward))
        return original_neighbor(value, upward)

    monkeypatch.setattr(kernel.math, "hypot", lambda *_args: 1e9)
    monkeypatch.setattr(kernel, "_neighbor", counted_neighbor)
    with pytest.raises(CoordinateReplayError, match="sqrt_bracket"):
        CoordinateMeridianReplay.build(target, 0.05, 1e-8, 10_000, TraceReplayWork())
    assert sum(upward for _, upward in neighbors) <= 2
    assert sum(not upward for _, upward in neighbors) <= 2

    huge = SimpleNamespace(
        coordinates_mm=((0.0, 0.0), (1.7e308, 1.7e308)),
        sha256="a" * 64,
    )
    monkeypatch.setattr(kernel.math, "hypot", lambda *_args: float_info.max)
    with pytest.raises(CoordinateReplayError, match="sqrt_bracket"):
        CoordinateMeridianReplay.build(huge, float_info.max, 1e-8, 10_000, TraceReplayWork())


@pytest.mark.parametrize(
    "parameter",
    [
        "solver.coordinate_sampler_version",
        "solver.coordinate_target_sha256",
        "solver.coordinate_sqrt_bracket_max_steps",
    ],
)
def test_partial_coordinate_parameter_deletion_fails_claims_and_trace(parameter):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    batch = generate_analytic(design, material, config(), PROVENANCE)
    proposals = [candidate.crochet_ir.to_dict() for candidate in batch.candidates]
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material},
        design_specs={design["design_spec_id"]: design},
    )
    proposal = proposals[0]
    old_hash = canonical_hash(proposal, CanonicalProfile.CROCHET_IR, validator=validator)
    proposal["provenance"]["solver_parameters"] = [
        row for row in proposal["provenance"]["solver_parameters"] if row["name"] != parameter
    ]
    ordered = sorted(proposal["provenance"]["solver_parameters"], key=lambda row: row["name"])
    proposal["provenance"]["solver_parameters_sha256"] = sha256(
        b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0" + rfc8785.dumps(ordered)
    ).hexdigest()
    new_hash = canonical_hash(proposal, CanonicalProfile.CROCHET_IR, validator=validator)
    claims = inspect_analytic_candidate_claims(design, material, proposal, validator=validator)
    assert claims.status == "FAIL"
    assert any(name == "coordinate_sampler_parameters" and not ok for name, ok in claims.assertions)

    trace = batch.search_trace.to_dict()
    for hypothesis in trace["hypotheses"]:
        if hypothesis.get("proposal_ir_sha256") == old_hash:
            hypothesis["proposal_ir_sha256"] = new_hash
    trace["terminal"]["proposal_ir_sha256"] = [
        new_hash if value == old_hash else value
        for value in trace["terminal"]["proposal_ir_sha256"]
    ]
    audit = inspect_analytic_search_trace(
        design,
        material,
        {**asdict(config()), "minimum_shaping_separation_turns": "1/12"},
        trace,
        proposals,
        validator=validator,
    )
    assert audit.status == "FAIL"


def test_truthful_coordinate_sample_failure_is_incomplete_and_false_success_fails():
    design, material = explicit_design([(0, 0), (3, 0), (3, 4), (0, 4)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    run = replace(
        config(),
        numerics=replace(config().numerics, roundoff_allowance_mm=1e-30),
    )
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.status is GenerationStatus.NUMERICAL_FAILURE
    assert batch.search_trace is not None
    trace = batch.search_trace.to_dict()
    assert trace["hypotheses"][0]["stage"] == "sample"
    assert trace["hypotheses"][0]["samples"] == []
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    run_config = asdict(run)
    run_config["minimum_shaping_separation_turns"] = "1/12"
    audit = inspect_analytic_search_trace(
        design, material, run_config, trace, [], validator=validator
    )
    assert audit.status == "INDETERMINATE"
    assert "coordinate_sampling_numerical_failure" in audit.missing_checks

    false_success = batch.search_trace.to_dict()
    false_success["hypotheses"][0]["outcome"] = "COMPILED"
    rejected = inspect_analytic_search_trace(
        design, material, run_config, false_success, [], validator=validator
    )
    assert rejected.status == "FAIL"


def test_declared_thin_neck_scope_limit_is_indeterminate():
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    batch = generate_analytic(design, material, config(), PROVENANCE)
    assert batch.search_trace is not None
    run_config = {**asdict(config()), "minimum_shaping_separation_turns": "1/12"}
    run_config["numerics"]["radius_zero_tolerance_mm"] = 5.0
    trace = batch.search_trace.to_dict()
    trace["budgets"]["numerics.radius_zero_tolerance_mm"] = 5.0
    flat = {
        key: value
        for key, value in run_config.items()
        if key not in {"numerics", "count_budget", "placement_budget"}
    }
    for group in ("numerics", "count_budget", "placement_budget"):
        flat.update((group + "." + key, value) for key, value in run_config[group].items())
    trace["bindings"]["run_config_sha256"] = sha256(
        b"Crochet.AI\0ANALYTIC_SEARCH_RUN_CONFIG_V1\0"
        + jcs_bytes([[key, value] for key, value in sorted(flat.items())])
    ).hexdigest()
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    audit = inspect_analytic_search_trace(
        design,
        material,
        run_config,
        trace,
        [candidate.crochet_ir.to_dict() for candidate in batch.candidates],
        validator=validator,
    )
    assert audit.status == "INDETERMINATE"
    assert "unsupported_coordinate_thin_neck" in audit.missing_checks
