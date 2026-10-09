"""Independent objective oracles and transport checks for closed mechanics."""

import json
from copy import deepcopy
from hashlib import sha256
from math import dist, fsum
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_forward_shaped_delivery import PROVENANCE, _energy, shaped_request

from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.forward_closed_mechanics import PROFILE, _evaluate, _perimeter_term
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated
from crochet_ai.prototype_server import make_server
from crochet_ai.validation import SemanticValidator


def closed_request():
    request = shaped_request()
    request["operation"] = "run_closed_forward_prototype"
    request["forward_run"] = {
        "profile": PROFILE,
        "elastic_recipe": request["forward_run"],
        "closure_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "synthetic-delivery",
            "ring_rest_perimeter_mm": 1.0,
            "ring_stiffness_n_per_mm": 0.2,
            "close_rest_perimeter_mm": 1.0,
            "close_stiffness_n_per_mm": 0.2,
        },
        "pressure_loading": {
            "schema_version": "1.0.0",
            "status": "USER_DECLARED",
            "provenance_id": "synthetic-pressure-record",
            "loading_profile_id": "synthetic-load",
            "pressure_n_per_mm2": 0.001,
            "volume_limit_mm3": 1e6,
        },
    }
    return request


def _bundle(request):
    response = BackendAPI(PROVENANCE).handle(request)
    assert response["ok"], response
    return response["data"]["experimental_forward_bundle"]


def _independent_objective(points, faces, terms, cycles, parameters, pressure):
    volume = (
        fsum(
            points[a][0] * (points[b][1] * points[c][2] - points[b][2] * points[c][1])
            + points[a][1] * (points[b][2] * points[c][0] - points[b][0] * points[c][2])
            + points[a][2] * (points[b][0] * points[c][1] - points[b][1] * points[c][0])
            for a, b, c in faces
        )
        / 6
    )
    closure = 0
    for name, cycle in zip(("ring", "close"), cycles, strict=True):
        perimeter = fsum(
            dist(points[a], points[b]) for a, b in zip(cycle, cycle[1:] + cycle[:1], strict=True)
        )
        closure += (
            parameters[f"{name}_stiffness_n_per_mm"]
            * max(perimeter - parameters[f"{name}_rest_perimeter_mm"], 0) ** 2
            / 2
        )
    return _energy(terms, points) + closure - pressure * volume, volume


def test_published_positions_and_mechanics_match_independent_objective():
    request = closed_request()
    bundle = _bundle(request)
    initial_request = deepcopy(request)
    initial_request["operation"] = "inspect_shaped_forward_model"
    initial_request["forward_run"] = request["forward_run"]["elastic_recipe"]
    initial = _bundle(initial_request)
    # Explicit very loose fixture tolerance deliberately accepts the initial points.
    assert bundle["status"] == "EXPERIMENTAL_FORCE_BALANCED"
    assert bundle["coordinates_mm"] == initial["coordinates_mm"]
    assert bundle["energy_evaluations"] == 1 and bundle["line_search_trials"] == 0
    assert bundle["initial_mechanics"] == bundle["final_mechanics"]
    unsigned = {key: value for key, value in bundle.items() if key != "sha256"}
    assert (
        sha256(b"Crochet.AI\0" + PROFILE.encode() + b"\0" + jcs_bytes(unsigned)).hexdigest()
        == bundle["sha256"]
    )


def test_total_force_is_independent_energy_gradient_at_every_vertex():
    # Asymmetric tetrahedron, no cancellation-only directional derivative.
    points = {
        "a": [0.2, 0.1, 0.3],
        "b": [1.4, 0.1, 0.3],
        "c": [0.2, 1.6, 0.3],
        "d": [0.2, 0.1, 2.1],
    }
    faces = [["a", "c", "b"], ["a", "b", "d"], ["a", "d", "c"], ["b", "c", "d"]]
    cycles = (["a", "b", "c"], ["b", "c", "d"])
    parameters = {
        "ring_rest_perimeter_mm": 1.0,
        "ring_stiffness_n_per_mm": 0.2,
        "close_rest_perimeter_mm": 1.5,
        "close_stiffness_n_per_mm": 0.3,
    }
    ring = _perimeter_term("RING_CLOSURE", tuple(cycles[0]), 1.0, 0.2)
    close = _perimeter_term("CLOSE_CLOSURE", tuple(cycles[1]), 1.5, 0.3)
    state = _evaluate((), ring, close, 0.4, faces, points, 0.001, 100)
    expected, volume = _independent_objective(points, faces, (), cycles, parameters, 0.4)
    assert state[0] == pytest.approx(expected, abs=1e-12)
    assert state[3]["volume_mm3"] == pytest.approx(volume, abs=1e-12)
    # Test-only central step 1e-5 mm and derivative error 1e-8 N, owned by this oracle.
    for key, force in state[1].items():
        for axis in range(3):
            plus, minus = deepcopy(points), deepcopy(points)
            plus[key][axis] += 1e-5
            minus[key][axis] -= 1e-5
            derivative = (
                _independent_objective(plus, faces, (), cycles, parameters, 0.4)[0]
                - _independent_objective(minus, faces, (), cycles, parameters, 0.4)[0]
            ) / 2e-5
            assert force[axis] == pytest.approx(-derivative, abs=1e-8)


def test_accepted_deformed_geometry_matches_published_energy():
    request = closed_request()
    recipe = request["forward_run"]
    config = recipe["elastic_recipe"]["config"]
    config["tolerances"]["force_residual_n"]["value"] = 0.05
    config["work_budgets"]["max_energy_evaluations"] = 512
    initial_request = deepcopy(request)
    initial_request["operation"] = "inspect_shaped_forward_model"
    initial_request["forward_run"] = recipe["elastic_recipe"]
    initial = _bundle(initial_request)
    bundle = _bundle(request)
    assert bundle["status"] == "EXPERIMENTAL_FORCE_BALANCED", bundle["status"]
    assert bundle["coordinates_mm"] != initial["coordinates_mm"]
    points = {row["attachment_location_id"]: row["position_mm"] for row in bundle["coordinates_mm"]}
    ir = request["crochet_ir"]
    operations = {row["operation_type"]: row for row in ir["construction_operations"]}
    frontiers = {row["frontier_id"]: row for row in ir["frontiers"]}
    cycles = (
        operations["MAGIC_RING"]["attachment_location_ids"],
        frontiers[operations["CLOSE"]["input_frontier_ids"][0]]["attachment_location_ids"],
    )
    expected, volume = _independent_objective(
        points,
        bundle["faces"],
        initial["spring_terms"],
        cycles,
        recipe["closure_parameters"],
        0.001,
    )
    assert bundle["final_mechanics"]["energy_n_mm"] == pytest.approx(expected, abs=1e-10)
    assert bundle["final_mechanics"]["volume_mm3"] == pytest.approx(volume, abs=1e-10)
    assert expected < bundle["initial_mechanics"]["energy_n_mm"]
    assert bundle["maximum_force_n"] <= 0.05
    assert bundle["comparison_eligible"] is False and bundle["v6_status"] == "NOT_RUN"


@pytest.mark.parametrize("change", ["generator", "seed", "target", "color"])
def test_excluded_source_metadata_cannot_change_loaded_model(change):
    request = closed_request()
    expected = _bundle(request)
    ir = request["crochet_ir"]
    if change == "generator":
        ir["provenance"]["generator"]["name"] = "different-source"
    elif change == "seed":
        ir["provenance"]["random_seed"] = 123
    elif change == "target":
        ir["provenance"]["input_artifacts"] = [
            {
                "artifact_id": "asset_different_target",
                "artifact_role": "TARGET_GEOMETRY",
                "sha256": "f" * 64,
            }
        ]
    else:
        ir["colors"][0]["srgb_hex"] = "#FF0000"
    assert _bundle(request) == expected


def test_wire_and_isolated_job_preserve_exact_response(tmp_path):
    request = closed_request()
    api = BackendAPI(PROVENANCE)
    expected = api.handle(request)
    assert api.handle_json(jcs_bytes(request)) == expected
    store = JobStore(tmp_path / "closed.sqlite3")
    job = store.submit(jcs_bytes(request), "closed-forward")
    assert execute_one_isolated(store, api, max_wall_seconds=30)
    restored = JobStore(tmp_path / "closed.sqlite3").get(job)
    assert restored["status"] == "SUCCEEDED" and restored["result"] == expected


@pytest.mark.parametrize("field", ["ring_stiffness_n_per_mm", "close_stiffness_n_per_mm"])
def test_extreme_finite_closure_stiffness_returns_counted_numerical_failure(field):
    request = closed_request()
    request["forward_run"]["closure_parameters"][field] = 1e308
    bundle = _bundle(request)
    assert bundle["status"] == "NUMERICAL_FAILURE"
    assert bundle["energy_evaluations"] == 1
    assert bundle["coordinates_mm"] is None and bundle["faces"] is None
    assert bundle["initial_mechanics"] is None and bundle["final_mechanics"] is None


def test_http_saved_project_compute_is_read_only_and_csrf_protected(tmp_path):
    request = closed_request()
    server = make_server(0, tmp_path, "a" * 40)
    project_id = "b" * 64
    # A legacy snapshot has no trace to fabricate; only stored source artifacts execute.
    project = {key: request[key] for key in ("design_spec", "material_profile", "crochet_ir")}
    validator = SemanticValidator(
        design_specs={project["design_spec"]["design_spec_id"]: project["design_spec"]},
        material_profiles={project["material_profile"]["profile_id"]: project["material_profile"]},
    )
    source_hash = canonical_hash(
        project["crochet_ir"], CanonicalProfile.CROCHET_IR, validator=validator
    )
    project.update(project_id=project_id, source_crochet_ir_sha256=source_hash, generation={})
    server.prototype_store.save_project(project, "2026-10-08T00:00:00Z")
    before = server.prototype_store.get_project(project_id)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    body = jcs_bytes({"project_id": project_id, "forward_run": request["forward_run"]})
    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(Request(base + "/api/forward/closed", data=body), timeout=10)
        assert denied.value.code == 403
        with urlopen(base + "/api/bootstrap", timeout=10) as response:
            token = json.load(response)["data"]["csrf_token"]
        headers = {"Origin": base, "X-CSRF-Token": token, "Content-Type": "application/json"}
        with urlopen(
            Request(base + "/api/forward/closed", data=body, headers=headers), timeout=30
        ) as response:
            actual = json.load(response)
        assert actual == BackendAPI(PROVENANCE).handle(request)
        assert server.prototype_store.get_project(project_id) == before
        for bad_id, status in (("missing", 400), ("c" * 64, 404)):
            with pytest.raises(HTTPError) as missing:
                urlopen(
                    Request(
                        base + "/api/forward/closed",
                        headers=headers,
                        data=jcs_bytes(
                            {"project_id": bad_id, "forward_run": request["forward_run"]}
                        ),
                    ),
                    timeout=10,
                )
            assert missing.value.code == status
        invalid = deepcopy(request["forward_run"])
        invalid["target_geometry"] = {}
        with pytest.raises(HTTPError) as rejected:
            urlopen(
                Request(
                    base + "/api/forward/closed",
                    headers=headers,
                    data=jcs_bytes({"project_id": project_id, "forward_run": invalid}),
                ),
                timeout=10,
            )
        assert rejected.value.code == 422
        assert json.loads(rejected.value.read())["error"]["code"] == "E_INPUT"
        forged_project = deepcopy(project)
        forged_project_id = "d" * 64
        forged_project.update(project_id=forged_project_id, source_crochet_ir_sha256="e" * 64)
        server.prototype_store.save_project(forged_project, "2026-10-09T00:00:00Z")
        forged_before = server.prototype_store.get_project(forged_project_id)
        with pytest.raises(HTTPError) as wrong_source:
            urlopen(
                Request(
                    base + "/api/forward/closed",
                    headers=headers,
                    data=jcs_bytes(
                        {"project_id": forged_project_id, "forward_run": request["forward_run"]}
                    ),
                ),
                timeout=30,
            )
        assert wrong_source.value.code == 422
        assert json.loads(wrong_source.value.read())["error"]["code"] == "E_PROVENANCE"
        assert server.prototype_store.get_project(forged_project_id) == forged_before
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        server.prototype_store.close()
