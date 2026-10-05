from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest
from test_forward_aabb_broadphase import _coordinates, _initialization, _inputs, _source

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_bending import admit_bending_parameters, prepare_bending_terms
from crochet_ai.forward_final_exact_contact import (
    ForwardFinalExactContactError,
    diagnose_final_exact_self_contact,
)
from crochet_ai.forward_optimize import _result, optimize_stretch_prototype
from crochet_ai.forward_shear import (
    admit_shear_parameters,
    optimize_stretch_shear_bending_prototype,
    optimize_stretch_shear_prototype,
    prepare_shear_terms,
)
from crochet_ai.forward_stretch import ForwardStretchTerms, StretchTerm
from crochet_ai.forward_triangulation import triangulate_forward_surface_cells


def _optimized(inputs, coordinates):
    source = _source()
    terms = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", source.projection_sha256,
        source.material_sha256, inputs.sha256, (),
    )
    return _result(
        "EXPERIMENTAL_FORCE_BALANCED", terms, dict(coordinates), 0.0, [], 0, 0, 0,
        _initialization(inputs).sha256,
    )


def test_final_coordinates_report_separated_surface_deterministically() -> None:
    inputs = _inputs()
    source = _source()
    result = _optimized(inputs, _coordinates())
    triangulation = triangulate_forward_surface_cells(source)
    report = diagnose_final_exact_self_contact(source, triangulation, result, inputs)
    assert report.status == "FINAL_COORDINATE_SELF_CONTACT_DIAGNOSTIC_ONLY"
    assert report.all_pair_count == 28
    assert report.forbidden_pair_count == 0
    assert report.minimum_squared_distance_numerator == "1"
    assert report.minimum_squared_distance_denominator == "3"
    assert report.minimizing_face_pairs == ((0, 7), (1, 2), (3, 4), (5, 6))
    assert report == diagnose_final_exact_self_contact(source, triangulation, result, inputs)


def test_actual_optimizer_output_is_accepted_without_promoting_v6() -> None:
    inputs = _inputs()
    source = _source()
    terms = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", source.projection_sha256,
        source.material_sha256, inputs.sha256,
        (StretchTerm("COURSE", "lower_0", "lower_1", 1.0, 1.0, "fixture"),),
    )
    optimized = optimize_stretch_prototype(terms, _initialization(inputs), inputs)
    assert optimized.status == "EXPERIMENTAL_FORCE_BALANCED"
    report = diagnose_final_exact_self_contact(
        source, triangulate_forward_surface_cells(source), optimized, inputs
    )
    assert report.forbidden_pair_count == 0
    assert report.status == "FINAL_COORDINATE_SELF_CONTACT_DIAGNOSTIC_ONLY"


def test_combined_shear_optimizer_connects_to_final_contact_with_provenance() -> None:
    inputs = _inputs()
    source = _source()
    stretch = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", source.projection_sha256,
        source.material_sha256, inputs.sha256,
        (StretchTerm("COURSE", "lower_0", "lower_1", 1.0, 1.0, "fixture"),),
    )
    shear = prepare_shear_terms(
        source, admit_shear_parameters("synthetic-right-angle", 1.0, 0.0), inputs
    )
    optimized = optimize_stretch_shear_prototype(
        stretch, shear, _initialization(inputs), inputs
    )
    assert optimized.status == "EXPERIMENTAL_FORCE_BALANCED"
    triangulation = triangulate_forward_surface_cells(source)
    report = diagnose_final_exact_self_contact(source, triangulation, optimized, inputs)
    assert report.forbidden_pair_count == 0
    assert report.minimum_squared_distance_numerator == "1"
    assert report.minimum_squared_distance_denominator == "3"
    with pytest.raises(ForwardFinalExactContactError, match="optimization_integrity"):
        diagnose_final_exact_self_contact(
            source, triangulation,
            replace(optimized, stretch_terms_sha256="f" * 64), inputs,
        )


def test_combined_bending_optimizer_connects_to_final_contact_with_provenance() -> None:
    inputs = _inputs()
    source = _source()
    old_initialization = _initialization(inputs)
    payload = {
        "profile": "FORWARD_STRETCH_INITIALIZATION_V1",
        "status": old_initialization.status,
        "projection_sha256": old_initialization.projection_sha256,
        "material_sha256": old_initialization.material_sha256,
        "forward_inputs_sha256": old_initialization.forward_inputs_sha256,
        "anchor_location_groups": [],
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)}
            for key, point in old_initialization.coordinates_mm
        ],
    }
    encoded = jcs_bytes(payload)
    initialization = replace(
        old_initialization,
        anchor_location_groups=(),
        canonical_bytes=encoded,
        sha256=sha256(
            b"Crochet.AI\0FORWARD_STRETCH_INITIALIZATION_V1\0" + encoded
        ).hexdigest(),
    )
    stretch = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", source.projection_sha256,
        source.material_sha256, inputs.sha256,
        (StretchTerm("COURSE", "lower_0", "lower_1", 1.0, 1.0, "fixture"),),
    )
    shear = prepare_shear_terms(
        source, admit_shear_parameters("synthetic-right-angle", 1.0, 0.0), inputs
    )
    bending = prepare_bending_terms(
        source, initialization,
        admit_bending_parameters("synthetic-flat-rest", 0.0, 1.0), inputs,
    )
    optimized = optimize_stretch_shear_bending_prototype(
        stretch, shear, bending, initialization, inputs
    )
    assert optimized.status == "EXPERIMENTAL_FORCE_BALANCED"
    triangulation = triangulate_forward_surface_cells(source)
    report = diagnose_final_exact_self_contact(source, triangulation, optimized, inputs)
    assert report.forbidden_pair_count == 0
    assert report.minimum_squared_distance_numerator == "1"
    assert report.minimum_squared_distance_denominator == "3"
    with pytest.raises(ForwardFinalExactContactError, match="optimization_integrity"):
        diagnose_final_exact_self_contact(
            source, triangulation,
            replace(optimized, bending_terms_sha256="f" * 64), inputs,
        )


def test_final_coordinates_report_nonadjacent_intersections() -> None:
    inputs = _inputs()
    source = _source()
    coordinates = dict(_coordinates())
    # Reverse the top ring's order to make nonadjacent side faces cross.
    for index, upper in enumerate(((0., 0.), (0., 1.), (1., 1.), (1., 0.))):
        coordinates[f"upper_{index}"] = (upper[0], upper[1], 0.25)
    result = _optimized(inputs, tuple(sorted(coordinates.items())))
    report = diagnose_final_exact_self_contact(
        source, triangulate_forward_surface_cells(source), result, inputs
    )
    assert report.forbidden_pair_count > 0
    assert report.minimum_squared_distance_numerator == "0"
    assert report.minimum_squared_distance_denominator == "1"


def test_failed_or_tampered_optimizer_artifacts_and_pair_budget_fail_closed() -> None:
    inputs = _inputs(27)
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    result = _optimized(inputs, _coordinates())
    with pytest.raises(ForwardFinalExactContactError, match="pair_budget_exhausted"):
        diagnose_final_exact_self_contact(source, triangulation, result, inputs)
    with pytest.raises(ForwardFinalExactContactError, match="optimization_integrity"):
        diagnose_final_exact_self_contact(
            source, triangulation, replace(result, sha256="0" * 64), inputs
        )
    failed = _result(
        "BUDGET_EXHAUSTED",
        ForwardStretchTerms("EXPERIMENTAL_STRETCH_TERMS", source.projection_sha256,
                            source.material_sha256, inputs.sha256, ()),
        None, None, [], 0, 0, 0, _initialization(inputs).sha256,
    )
    with pytest.raises(ForwardFinalExactContactError, match="coordinates_unavailable"):
        diagnose_final_exact_self_contact(source, triangulation, failed, inputs)
