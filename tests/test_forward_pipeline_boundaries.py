from __future__ import annotations

from dataclasses import replace

import pytest
from test_forward_pipeline import _provenance, _request, _run

from crochet_ai.analytic_compile import compile_closed_schedule
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.forward_pipeline import (
    ForwardPipelineError,
    admit_forward_pipeline_recipe,
    run_forward_pipeline,
)
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def test_target_size_and_origin_do_not_enter_physical_execution() -> None:
    first = _request()
    changed = _request()
    design = changed["design_spec"]
    design["dimensions"]["measurements"][0]["value_mm"] = 55
    design["target_geometry"]["origin_mm"] = [25, -10, 2]
    changed["crochet_ir"]["design_spec_ref"]["sha256"] = canonical_hash(
        design, CanonicalProfile.DESIGN_SPEC
    )
    api = BackendAPI(_provenance())
    original_response, changed_response = api.handle(first), api.handle(changed)
    assert original_response["ok"] and changed_response["ok"]
    assert original_response["data"]["source_crochet_ir_sha256"] != (
        changed_response["data"]["source_crochet_ir_sha256"]
    )
    assert original_response["data"]["experimental_forward_bundle"] == (
        changed_response["data"]["experimental_forward_bundle"]
    )


@pytest.mark.parametrize("mutation", ["budget", "binding", "shear", "bending"])
def test_forged_recipe_is_rejected_before_graph_execution(monkeypatch, mutation: str) -> None:
    request = _request()
    design, material, ir = (
        request["design_spec"], request["material_profile"], request["crochet_ir"]
    )
    source_validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    projection = PhysicalSemanticProjection(ir, material, validator=source_validator)
    recipe = admit_forward_pipeline_recipe(request["forward_run"])
    if mutation == "budget":
        forged = replace(recipe, inputs=replace(recipe.inputs, max_energy_evaluations=4097))
    elif mutation == "binding":
        forged = replace(recipe, inputs=replace(recipe.inputs, max_energy_evaluations=1))
    elif mutation == "shear":
        forged = replace(recipe, shear=replace(recipe.shear, rest_cosine=0.5))
    else:
        forged = replace(recipe, bending=replace(recipe.bending, rest_dihedral_rad=0.5))

    def unexpected_execution(*args, **kwargs):
        pytest.fail("Rejected recipe entered graph/numerical execution")

    monkeypatch.setattr("crochet_ai.forward_pipeline.lower_forward_graph", unexpected_execution)
    with pytest.raises(ForwardPipelineError) as rejected:
        run_forward_pipeline(
            projection, material, forged,
            validator=SemanticValidator(material_profiles={material["profile_id"]: material}),
        )
    assert rejected.value.code == "E_INPUT"


@pytest.mark.parametrize("value", [True, float("inf"), float("nan"), 10**1000])
def test_direct_recipe_rejects_invalid_coefficients(value: object) -> None:
    recipe = _request()["forward_run"]
    recipe["shear_parameters"]["stiffness_n_mm"] = value
    with pytest.raises(ForwardPipelineError) as rejected:
        admit_forward_pipeline_recipe(recipe)
    assert rejected.value.code == "E_INPUT"


@pytest.mark.parametrize("status", ["NUMERICAL_FAILURE", "LINE_SEARCH_FAILED"])
def test_real_optimizer_failures_suppress_geometry_and_contact(monkeypatch, status: str) -> None:
    request = _request()
    request["forward_run"]["shear_parameters"].update(
        stiffness_n_mm=1e308 if status == "NUMERICAL_FAILURE" else 100.0, rest_cosine=-1.0
    )
    request["forward_run"]["config"]["tolerances"]["force_residual_n"]["value"] = 0.001
    request["forward_run"]["config"]["work_budgets"]["max_line_search_trials"] = 1

    def unexpected_contact(*args, **kwargs):
        pytest.fail("Failed optimization entered contact diagnosis")

    monkeypatch.setattr(
        "crochet_ai.forward_pipeline.diagnose_final_exact_self_contact", unexpected_contact
    )
    result = _run(request)
    assert result["status"] == status
    assert result["coordinates_mm"] is None
    assert result["optimizer"]["coordinates_mm"] is None
    assert result["canonical_bytes_object"]["coordinates_mm"] is None
    assert result["triangles"] is None
    assert result["final_contact"] is None


def test_valid_shaping_is_explicitly_unsupported() -> None:
    request = _request()
    request["design_spec"]["difficulty_constraints"]["allowed_shaping"] = [
        "INCREASE", "DECREASE"
    ]
    request["crochet_ir"] = compile_closed_schedule(
        request["design_spec"], request["material_profile"], (6, 12, 6), (0, 0),
        _provenance(), max_stitches=100,
    )
    response = BackendAPI(_provenance()).handle(request)
    assert not response["ok"]
    assert response["error"]["code"] == "E_UNSUPPORTED_FEATURE"


@pytest.mark.parametrize("mutation", ["missing", "unknown"])
def test_optimizer_coordinate_domain_is_not_repaired(monkeypatch, mutation: str) -> None:
    import crochet_ai.forward_pipeline as pipeline

    original_optimizer = pipeline.optimize_stretch_shear_bending_prototype

    def malformed_optimizer(*args, **kwargs):
        original = original_optimizer(*args, **kwargs)
        rows = dict(original.coordinates_mm)
        if mutation == "missing":
            # Remove a surface location, not an excluded magic-ring anchor.
            key = next(key for key in rows if any(
                key in term.attachment_location_ids for term in args[1].terms
            ))
            del rows[key]
        else:
            rows["unknown-location"] = (0.0, 0.0, 0.0)
        return replace(original, coordinates_mm=tuple(sorted(rows.items())))

    monkeypatch.setattr(pipeline, "optimize_stretch_shear_bending_prototype", malformed_optimizer)
    response = BackendAPI(_provenance()).handle(_request())
    assert not response["ok"]
    assert response["error"]["code"] == "E_INPUT"
    assert "data" not in response


@pytest.mark.parametrize("mutation", ["missing", "profile", "nested-field"])
def test_closed_recipe_and_profile_fail_at_api_boundary(mutation: str) -> None:
    request = _request()
    recipe = request["forward_run"]
    if mutation == "missing":
        del recipe["bending_parameters"]
    elif mutation == "profile":
        recipe["profile"] = "FORWARD_STRETCH_SHEAR_BENDING_PIPELINE_V999"
    else:
        recipe["shear_parameters"]["target_radius_mm"] = 20
    response = BackendAPI(_provenance()).handle(request)
    assert not response["ok"]
    assert response["error"]["code"] == (
        "E_UNSUPPORTED_FEATURE" if mutation == "profile" else "E_INPUT"
    )
