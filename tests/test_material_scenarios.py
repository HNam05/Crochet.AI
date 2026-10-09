from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.forward_graph import ForwardGraph, StitchMaterialResponse
from crochet_ai.material_scenarios import (
    GaugeEndpoint,
    MaterialScenarioError,
    _scenario_hash,
    apply_gauge_scenario,
    build_gauge_scenarios,
    evaluate_gauge_scenarios,
    validate_gauge_scenario,
)


def material_profile():
    path = Path(__file__).parent / "fixtures/schema-valid/material-profile.minimal.valid.json"
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_policy():
    return {
        "policy_version": "MATERIAL_SCENARIO_POLICY_V1",
        "profile_id": "CARTESIAN_GAUGE_ENDPOINTS_V1",
        "coverage_multiplier": 1.0,
        "coverage_multiplier_unit": "1",
        "coverage_multiplier_owner": "test owner",
        "coverage_multiplier_rationale": "fixture interval assumption",
        "validation_path": "fixture only",
        "max_scenarios": 5,
        "max_runs": 5,
    }


def forward_graph(material=None):
    source = material or material_profile()
    material_hash = canonical_hash(source, CanonicalProfile.MATERIAL_PROFILE)
    return ForwardGraph(
        projection_sha256="a" * 64,
        material_sha256=material_hash,
        nodes=(),
        shaping_groups=(),
        edges=(),
        yarn_path_links=(),
        construction_operations=(),
        frontier_boundaries=(),
        material_responses=(
            StitchMaterialResponse("st_1", "mr_fixture_relaxed_sc", 4, 3.5, 0.5, 0.5),
            StitchMaterialResponse("st_2", "mr_fixture_relaxed_sc", 4, 3.5, 0.5, 0.5),
        ),
    )


def test_endpoint_scenarios_are_deterministic_and_reference_bound():
    material = material_profile()
    graph = forward_graph()
    scenarios = build_gauge_scenarios(material, graph, scenario_policy())
    assert len(scenarios) == 5
    assert scenarios == build_gauge_scenarios(material, graph, scenario_policy())
    assert scenarios[0].corner is None
    assert scenarios[0].endpoints == (GaugeEndpoint("mr_fixture_relaxed_sc", 4, 3.5),)
    assert {scenario.corner for scenario in scenarios[1:]} == {
        (-1, -1), (-1, 1), (1, -1), (1, 1)
    }
    assert all(scenario.material_profile_sha256 == graph.material_sha256 for scenario in scenarios)
    changed = apply_gauge_scenario(
        graph,
        scenarios[1],
        material_profile=material,
        policy=scenario_policy(),
    )
    assert changed.base_material_sha256 == graph.material_sha256
    assert changed.scenario_sha256 == scenarios[1].scenario_sha256
    assert changed.graph.material_sha256 == graph.material_sha256
    assert changed.graph.material_responses[0].effective_stitch_pitch_mm == 3.5
    assert graph.material_responses[0].effective_stitch_pitch_mm == 4


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"coverage_multiplier": 0}, "coverage_multiplier_invalid"),
        ({"coverage_multiplier": float("inf")}, "coverage_multiplier_invalid"),
        ({"max_scenarios": 4}, "budget_out_of_range"),
        ({"max_runs": 10}, "budget_out_of_range"),
        ({"coverage_multiplier_owner": ""}, "policy_ownership_missing"),
    ],
)
def test_invalid_bounds_and_budget_fail_closed(update, message):
    selected = scenario_policy()
    selected.update(update)
    with pytest.raises(MaterialScenarioError, match=message):
        build_gauge_scenarios(material_profile(), forward_graph(), selected)


def test_endpoint_that_crosses_zero_is_rejected():
    material = material_profile()
    response = material["calibration_responses"][0]
    response["uncertainty"]["stitch_pitch_standard_uncertainty_mm"] = 5
    response["uncertainty"]["course_pitch_standard_uncertainty_mm"] = 0.25
    graph = forward_graph(material)
    with pytest.raises(MaterialScenarioError, match="endpoint_nonpositive_or_nonfinite"):
        build_gauge_scenarios(material, graph, scenario_policy())


def test_material_observation_tampering_is_rejected_by_semantic_admission():
    material = material_profile()
    material["calibration_responses"][0]["observations"][0]["stitch_span_length_mm"] = 20
    graph = forward_graph()
    with pytest.raises(MaterialScenarioError, match="material_profile_not_admitted"):
        build_gauge_scenarios(material, graph, scenario_policy())


def test_unmatched_graph_response_is_rejected():
    graph = forward_graph()
    invalid = ForwardGraph(
        **{
            field: getattr(graph, field)
            for field in graph.__dataclass_fields__
            if field != "material_responses"
        },
        material_responses=(StitchMaterialResponse("st_1", "mr_unknown", 4, 3.5, 0.5, 0.5),),
    )
    with pytest.raises(MaterialScenarioError, match="graph_response_unmatched"):
        build_gauge_scenarios(material_profile(), invalid, scenario_policy())


def test_endpoint_failure_overrides_nominal_pass_and_preserves_failures():
    graph = forward_graph()
    scenarios = build_gauge_scenarios(material_profile(), graph, scenario_policy())

    def runner(scenario_graph):
        response = scenario_graph.graph.material_responses[0]
        if response.effective_stitch_pitch_mm < 4:
            return {
                "status": "FAIL",
                "failures": ["shape threshold"],
                "metrics": {"chamfer": 0.2},
            }
        return {"status": "PASS", "failures": [], "metrics": {"chamfer": 0.0}}

    result = evaluate_gauge_scenarios(
        graph,
        scenarios,
        runner,
        max_runs=5,
        material_profile=material_profile(),
        policy=scenario_policy(),
    )
    assert result["status"] == "FAIL"
    assert result["worst_case_status"] == "FAIL"
    assert result["outcome_scope"] == "CALLER_CALLBACK_DIAGNOSTIC_ONLY"
    assert result["authenticity"] == "NOT_ESTABLISHED"
    assert result["verification_claim"] == "NOT_VERIFIED"
    assert len(result["results"]) == 5
    assert result["failures"] == [
        {"scenario_id": scenarios[1].scenario_id, "failure": "shape threshold"},
        {"scenario_id": scenarios[2].scenario_id, "failure": "shape threshold"},
    ]


def test_missing_run_budget_prevents_callback_work():
    graph = forward_graph()
    scenarios = build_gauge_scenarios(material_profile(), graph, scenario_policy())
    called = False

    def runner(_scenario_graph):
        nonlocal called
        called = True
        return {"status": "PASS", "metrics": {}, "failures": []}

    with pytest.raises(MaterialScenarioError, match="run_budget_exhausted_before_work"):
        evaluate_gauge_scenarios(
            graph,
            scenarios,
            runner,
            max_runs=4,
            material_profile=material_profile(),
            policy=scenario_policy(),
        )
    assert not called


def test_forged_scenario_hash_is_rejected():
    graph = forward_graph()
    material = material_profile()
    policy = scenario_policy()
    scenario = build_gauge_scenarios(material, graph, policy)[0]
    forged = replace(scenario, endpoints=(replace(scenario.endpoints[0], stitch_pitch_mm=99),))
    forged = replace(forged, scenario_sha256=_scenario_hash(forged))
    with pytest.raises(MaterialScenarioError, match="inputs_do_not_match_admitted_profile"):
        validate_gauge_scenario(graph, forged, material_profile=material, policy=policy)
    with pytest.raises(MaterialScenarioError, match="inputs_do_not_match_admitted_profile"):
        apply_gauge_scenario(graph, forged, material_profile=material, policy=policy)


def test_incomplete_scenario_tuple_never_runs_callback():
    graph = forward_graph()
    scenarios = build_gauge_scenarios(material_profile(), graph, scenario_policy())
    called = False

    def runner(_scenario_graph):
        nonlocal called
        called = True
        return {"status": "PASS", "metrics": {}, "failures": []}

    with pytest.raises(MaterialScenarioError, match="required_set_incomplete"):
        evaluate_gauge_scenarios(
            graph,
            scenarios[:4],
            runner,
            max_runs=5,
            material_profile=material_profile(),
            policy=scenario_policy(),
        )
    assert not called


def test_unexpected_runner_exception_is_not_suppressed():
    graph = forward_graph()
    scenarios = build_gauge_scenarios(material_profile(), graph, scenario_policy())

    def runner(_scenario_graph):
        raise RuntimeError("programming defect")

    with pytest.raises(RuntimeError, match="programming defect"):
        evaluate_gauge_scenarios(
            graph,
            scenarios,
            runner,
            max_runs=5,
            material_profile=material_profile(),
            policy=scenario_policy(),
        )
