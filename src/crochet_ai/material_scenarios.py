"""Finite, hypothesis-only gauge endpoint scenarios for material robustness."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from math import isfinite
from typing import Any, TypeAlias

from .canonical import CanonicalizationError, CanonicalProfile, canonical_hash, jcs_bytes
from .forward_graph import ForwardGraph, StitchMaterialResponse
from .json_types import JSONValue
from .validation import SemanticValidator

PROFILE = "CARTESIAN_GAUGE_ENDPOINTS_V1"
_SCENARIO_DOMAIN = b"CARTESIAN_GAUGE_ENDPOINTS_V1\0"


class MaterialScenarioError(ValueError):
    """Invalid material scenario input or incomplete bounded evaluation."""


@dataclass(frozen=True, slots=True)
class GaugeEndpoint:
    response_id: str
    stitch_pitch_mm: float
    course_pitch_mm: float


@dataclass(frozen=True, slots=True)
class GaugeScenario:
    scenario_id: str
    material_profile_sha256: str
    policy_sha256: str
    response_ids: tuple[str, ...]
    corner: tuple[int, int] | None
    endpoints: tuple[GaugeEndpoint, ...]
    coverage_multiplier: float
    scenario_sha256: str


@dataclass(frozen=True, slots=True)
class ScenarioForwardGraph:
    """Derived graph input retaining base-material and scenario identities."""

    graph: ForwardGraph
    base_material_sha256: str
    scenario_sha256: str


ScenarioRunner: TypeAlias = Callable[[ScenarioForwardGraph], Mapping[str, object]]


def build_gauge_scenarios(
    material_profile: dict[str, Any], graph: ForwardGraph, policy: object
) -> tuple[GaugeScenario, ...]:
    """Validate the source profile and create nominal plus four endpoint corners.

    The same stitch/course corner signs are applied across all resolved
    SINGLE_CROCHET/CYCLIC responses. This is a deterministic finite scenario
    set, not a probability or covariance model.
    """
    if not isinstance(material_profile, dict) or not isinstance(graph, ForwardGraph):
        raise MaterialScenarioError("scenario.input_type_invalid")
    validator = SemanticValidator()
    report = validator.validate_material_profile(material_profile)
    if not report.ok:
        raise MaterialScenarioError("scenario.material_profile_not_admitted")
    try:
        material_hash = canonical_hash(material_profile, CanonicalProfile.MATERIAL_PROFILE)
    except (CanonicalizationError, KeyError, TypeError, ValueError) as error:
        raise MaterialScenarioError("scenario.material_profile_hash_invalid") from error
    if graph.material_sha256 != material_hash:
        raise MaterialScenarioError("scenario.graph_material_binding_mismatch")
    coverage, max_scenarios, max_runs, policy_hash = _policy(policy)

    allowed_responses = {
        response["response_id"]: response
        for response in material_profile["calibration_responses"]
        if response["measurement_conditions"]["canonical_stitch_type"] == "SINGLE_CROCHET"
        and response["measurement_conditions"]["course_mode"] == "CYCLIC"
    }
    profile_response_ids = {
        response["response_id"] for response in material_profile["calibration_responses"]
    }
    if not {response.response_id for response in graph.material_responses}.issubset(
        profile_response_ids
    ):
        raise MaterialScenarioError("scenario.graph_response_unmatched")
    selected_ids = tuple(
        sorted(
            {
                response.response_id
                for response in graph.material_responses
                if response.response_id in allowed_responses
            }
        )
    )
    if not selected_ids:
        raise MaterialScenarioError("scenario.no_resolved_sc_cyclic_response")
    if len(selected_ids) != 1:
        raise MaterialScenarioError("scenario.multiple_responses_unsupported")
    graph_ids = {response.response_id for response in graph.material_responses}
    if any(response_id not in graph_ids for response_id in selected_ids):
        raise MaterialScenarioError("scenario.graph_response_unmatched")
    endpoints_by_response: dict[str, tuple[float, float, float, float]] = {}
    for response_id in selected_ids:
        response = allowed_responses[response_id]
        gauge = response["effective_gauge"]
        uncertainty = response["uncertainty"]
        stitch = _endpoint_pair(
            gauge["effective_stitch_pitch_mm"],
            uncertainty["stitch_pitch_standard_uncertainty_mm"],
            coverage,
        )
        course = _endpoint_pair(
            gauge["effective_course_pitch_mm"],
            uncertainty["course_pitch_standard_uncertainty_mm"],
            coverage,
        )
        endpoints_by_response[response_id] = (stitch[0], stitch[1], course[0], course[1])

    corners: tuple[tuple[int, int] | None, ...] = (
        None,
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    )
    if len(corners) > max_scenarios or len(corners) > max_runs:
        raise MaterialScenarioError("scenario.budget_exhausted_before_work")
    scenarios: list[GaugeScenario] = []
    for ordinal, corner in enumerate(corners):
        gauge_endpoints: list[GaugeEndpoint] = []
        for response_id in selected_ids:
            response = allowed_responses[response_id]
            stitch_low, stitch_high, course_low, course_high = endpoints_by_response[response_id]
            if corner is None:
                stitch_pitch = float(response["effective_gauge"]["effective_stitch_pitch_mm"])
                course_pitch = float(response["effective_gauge"]["effective_course_pitch_mm"])
            else:
                stitch_pitch = stitch_low if corner[0] < 0 else stitch_high
                course_pitch = course_low if corner[1] < 0 else course_high
            gauge_endpoints.append(GaugeEndpoint(response_id, stitch_pitch, course_pitch))
        scenario_id = f"gauge_endpoint_{ordinal}"
        endpoint_tuple = tuple(gauge_endpoints)
        scenarios.append(
            GaugeScenario(
                scenario_id=scenario_id,
                material_profile_sha256=material_hash,
                policy_sha256=policy_hash,
                response_ids=selected_ids,
                corner=corner,
                endpoints=endpoint_tuple,
                coverage_multiplier=coverage,
                scenario_sha256=_scenario_hash_values(
                    scenario_id,
                    material_hash,
                    policy_hash,
                    selected_ids,
                    corner,
                    endpoint_tuple,
                    coverage,
                ),
            )
        )
    return tuple(scenarios)


def validate_gauge_scenario(
    graph: ForwardGraph,
    scenario: GaugeScenario,
    *,
    material_profile: dict[str, Any],
    policy: object,
) -> None:
    """Require exact membership in a freshly derived admitted five-case set."""
    expected = build_gauge_scenarios(material_profile, graph, policy)
    if scenario not in expected:
        raise MaterialScenarioError("scenario.inputs_do_not_match_admitted_profile")
    _validate_single_scenario(graph, scenario)


def apply_gauge_scenario(
    graph: ForwardGraph,
    scenario: GaugeScenario,
    *,
    material_profile: dict[str, Any],
    policy: object,
) -> ScenarioForwardGraph:
    """Return an immutable derived graph with only resolved pitches replaced."""
    validate_gauge_scenario(
        graph, scenario, material_profile=material_profile, policy=policy
    )
    endpoint_map = {endpoint.response_id: endpoint for endpoint in scenario.endpoints}
    changed: list[StitchMaterialResponse] = []
    for response in graph.material_responses:
        endpoint = endpoint_map.get(response.response_id)
        changed.append(
            response
            if endpoint is None
            else replace(
                response,
                effective_stitch_pitch_mm=endpoint.stitch_pitch_mm,
                effective_course_pitch_mm=endpoint.course_pitch_mm,
            )
        )
    derived = replace(graph, material_responses=tuple(changed))
    return ScenarioForwardGraph(derived, graph.material_sha256, scenario.scenario_sha256)


def _validate_single_scenario(graph: ForwardGraph, scenario: GaugeScenario) -> None:
    if graph.material_sha256 != scenario.material_profile_sha256:
        raise MaterialScenarioError("scenario.graph_material_binding_mismatch")
    if not isfinite(scenario.coverage_multiplier) or scenario.coverage_multiplier <= 0:
        raise MaterialScenarioError("scenario.coverage_multiplier_invalid")
    endpoint_map = {endpoint.response_id: endpoint for endpoint in scenario.endpoints}
    if set(endpoint_map) != set(scenario.response_ids):
        raise MaterialScenarioError("scenario.endpoint_response_set_mismatch")
    response_ids = {response.response_id for response in graph.material_responses}
    if not set(endpoint_map).issubset(response_ids):
        raise MaterialScenarioError("scenario.graph_response_unmatched")
    if any(
        not isfinite(value) or value <= 0
        for endpoint in scenario.endpoints
        for value in (endpoint.stitch_pitch_mm, endpoint.course_pitch_mm)
    ):
        raise MaterialScenarioError("scenario.endpoint_nonpositive_or_nonfinite")
    if _scenario_hash(scenario) != scenario.scenario_sha256:
        raise MaterialScenarioError("scenario.hash_mismatch")


def evaluate_gauge_scenarios(
    graph: ForwardGraph,
    scenarios: tuple[GaugeScenario, ...],
    runner: ScenarioRunner,
    *,
    max_runs: int,
    material_profile: dict[str, Any],
    policy: object,
) -> dict[str, JSONValue]:
    """Run every scenario under one cumulative budget and aggregate fail-closed."""
    if not isinstance(graph, ForwardGraph) or not scenarios or not callable(runner):
        raise MaterialScenarioError("scenario.evaluation_input_invalid")
    if not isinstance(max_runs, int) or isinstance(max_runs, bool) or not 1 <= max_runs <= 9:
        raise MaterialScenarioError("scenario.run_budget_invalid")
    if len(scenarios) > max_runs:
        raise MaterialScenarioError("scenario.run_budget_exhausted_before_work")
    _validate_scenario_set(graph, scenarios)
    expected_scenarios = build_gauge_scenarios(material_profile, graph, policy)
    if scenarios != expected_scenarios:
        raise MaterialScenarioError("scenario.inputs_do_not_match_admitted_profile")
    results: list[JSONValue] = []
    statuses: list[str] = []
    failures: list[JSONValue] = []
    for scenario in scenarios:
        raw = runner(
            apply_gauge_scenario(
                graph, scenario, material_profile=material_profile, policy=policy
            )
        )
        status = raw.get("status")
        if status not in {"PASS", "FAIL", "INDETERMINATE", "NOT_RUN"}:
            raise MaterialScenarioError("scenario.runner_status_invalid")
        if not isinstance(raw.get("metrics"), Mapping):
            raise MaterialScenarioError("scenario.runner_metrics_missing")
        if not isinstance(raw.get("failures"), list):
            raise MaterialScenarioError("scenario.runner_failures_invalid")
        metric_values = raw["metrics"]
        if status == "PASS" and not metric_values:
            raise MaterialScenarioError("scenario.runner_pass_metrics_empty")
        failure_values = raw["failures"]
        if status == "PASS" and failure_values:
            raise MaterialScenarioError("scenario.runner_pass_has_failures")
        json_result = _json_mapping(raw)
        json_result["scenario_id"] = scenario.scenario_id
        json_result["scenario_sha256"] = scenario.scenario_sha256
        results.append(json_result)
        statuses.append(str(status))
        if status != "PASS":
            failure_records = raw.get("failures")
            if not isinstance(failure_records, list):
                raise MaterialScenarioError("scenario.runner_failures_invalid")
            if failure_records:
                failures.extend(
                    {"scenario_id": scenario.scenario_id, "failure": _json_value(item)}
                    for item in failure_records
                )
            else:
                failures.append({"scenario_id": scenario.scenario_id, "status": status})
    complete = len(results) == len(scenarios)
    failed = "FAIL" in statuses
    status = "FAIL" if failed else "INDETERMINATE" if not complete or failures else "PASS"
    ranked_results = [result for result in results if isinstance(result, dict)]
    rank = {"PASS": 0, "INDETERMINATE": 1, "NOT_RUN": 1, "FAIL": 2}
    worst_case = max(ranked_results, key=lambda result: rank[str(result["status"])])
    return {
        "profile_id": PROFILE,
        "status": status,
        "outcome_scope": "CALLER_CALLBACK_DIAGNOSTIC_ONLY",
        "authenticity": "NOT_ESTABLISHED",
        "verification_claim": "NOT_VERIFIED",
        "scenario_count_required": len(scenarios),
        "scenario_count_completed": len(results),
        "runs_used": len(results),
        "max_runs": max_runs,
        "results": results,
        "failures": failures,
        "worst_case_status": "FAIL" if failed else "INDETERMINATE" if failures else "PASS",
        "worst_case_result": worst_case,
        "policy_sha256": scenarios[0].policy_sha256,
    }


def _policy(value: object) -> tuple[float, int, int, str]:
    if not isinstance(value, Mapping):
        raise MaterialScenarioError("scenario.policy_invalid")
    required = {
        "policy_version",
        "profile_id",
        "coverage_multiplier",
        "coverage_multiplier_unit",
        "coverage_multiplier_owner",
        "coverage_multiplier_rationale",
        "validation_path",
        "max_scenarios",
        "max_runs",
    }
    if set(value) != required:
        raise MaterialScenarioError("scenario.policy_fields_invalid")
    if value["policy_version"] != "MATERIAL_SCENARIO_POLICY_V1" or value["profile_id"] != PROFILE:
        raise MaterialScenarioError("scenario.policy_version_unsupported")
    for key in (
        "coverage_multiplier_owner",
        "coverage_multiplier_rationale",
        "validation_path",
    ):
        if not isinstance(value[key], str) or not value[key].strip():
            raise MaterialScenarioError("scenario.policy_ownership_missing")
    if value["coverage_multiplier_unit"] != "1":
        raise MaterialScenarioError("scenario.coverage_unit_invalid")
    coverage = value["coverage_multiplier"]
    if not isinstance(coverage, (int, float)) or isinstance(coverage, bool):
        raise MaterialScenarioError("scenario.coverage_multiplier_invalid")
    if not isfinite(float(coverage)) or float(coverage) <= 0:
        raise MaterialScenarioError("scenario.coverage_multiplier_invalid")
    for key in ("max_scenarios", "max_runs"):
        limit = value[key]
        if not isinstance(limit, int) or isinstance(limit, bool) or not 5 <= limit <= 9:
            raise MaterialScenarioError("scenario.budget_out_of_range")
    canonical_policy = _json_mapping(value)
    policy_hash = sha256(b"MATERIAL_SCENARIO_POLICY_V1\0" + jcs_bytes(canonical_policy)).hexdigest()
    return float(coverage), int(value["max_scenarios"]), int(value["max_runs"]), policy_hash


def _validate_scenario_set(
    graph: ForwardGraph, scenarios: tuple[GaugeScenario, ...]
) -> None:
    expected_corners: tuple[tuple[int, int] | None, ...] = (
        None,
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    )
    if len(scenarios) != len(expected_corners):
        raise MaterialScenarioError("scenario.required_set_incomplete")
    first = scenarios[0]
    if (
        first.material_profile_sha256 != graph.material_sha256
        or len(first.response_ids) != 1
        or not first.policy_sha256
    ):
        raise MaterialScenarioError("scenario.binding_invalid")
    if tuple(scenario.scenario_id for scenario in scenarios) != tuple(
        f"gauge_endpoint_{index}" for index in range(len(expected_corners))
    ):
        raise MaterialScenarioError("scenario.order_or_identity_invalid")
    if tuple(scenario.corner for scenario in scenarios) != expected_corners:
        raise MaterialScenarioError("scenario.required_set_incomplete")
    for scenario in scenarios:
        if (
            scenario.material_profile_sha256 != first.material_profile_sha256
            or scenario.policy_sha256 != first.policy_sha256
            or scenario.response_ids != first.response_ids
            or scenario.coverage_multiplier != first.coverage_multiplier
            or len(scenario.endpoints) != 1
            or scenario.endpoints[0].response_id not in scenario.response_ids
            or _scenario_hash(scenario) != scenario.scenario_sha256
        ):
            raise MaterialScenarioError("scenario.binding_or_hash_invalid")


def _endpoint_pair(nominal: object, uncertainty: object, coverage: float) -> tuple[float, float]:
    if not isinstance(nominal, (float, int)) or isinstance(nominal, bool):
        raise MaterialScenarioError("scenario.pitch_invalid")
    if not isinstance(uncertainty, (float, int)) or isinstance(uncertainty, bool):
        raise MaterialScenarioError("scenario.uncertainty_invalid")
    centre, spread = float(nominal), float(uncertainty) * coverage
    low, high = centre - spread, centre + spread
    if not all(isfinite(value) and value > 0 for value in (centre, spread, low, high)):
        raise MaterialScenarioError("scenario.endpoint_nonpositive_or_nonfinite")
    return low, high


def _scenario_hash(scenario: GaugeScenario) -> str:
    return _scenario_hash_values(
        scenario.scenario_id,
        scenario.material_profile_sha256,
        scenario.policy_sha256,
        scenario.response_ids,
        scenario.corner,
        scenario.endpoints,
        scenario.coverage_multiplier,
    )


def _scenario_hash_values(
    scenario_id: str,
    material_hash: str,
    policy_hash: str,
    response_ids: tuple[str, ...],
    corner: tuple[int, int] | None,
    endpoints: tuple[GaugeEndpoint, ...],
    coverage: float,
) -> str:
    data: dict[str, JSONValue] = {
        "scenario_profile": PROFILE,
        "scenario_id": scenario_id,
        "material_profile_sha256": material_hash,
        "policy_sha256": policy_hash,
        "response_ids": list(response_ids),
        "corner": None if corner is None else list(corner),
        "coverage_multiplier": coverage,
        "endpoints": [
            {
                "response_id": endpoint.response_id,
                "stitch_pitch_mm": endpoint.stitch_pitch_mm,
                "course_pitch_mm": endpoint.course_pitch_mm,
            }
            for endpoint in endpoints
        ],
    }
    return sha256(_SCENARIO_DOMAIN + jcs_bytes(data)).hexdigest()


def _json_mapping(value: Mapping[str, object]) -> dict[str, JSONValue]:
    converted = _json_value(value)
    if not isinstance(converted, dict):
        raise MaterialScenarioError("scenario.runner_result_invalid")
    return converted


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not isfinite(value):
            raise MaterialScenarioError("scenario.runner_result_nonfinite")
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise MaterialScenarioError("scenario.runner_result_invalid")
        return {str(key): _json_value(item) for key, item in value.items()}
    raise MaterialScenarioError("scenario.runner_result_invalid")
