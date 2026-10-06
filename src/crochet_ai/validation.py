"""Independent fail-closed semantic validation for Milestone 0 artifacts."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import sqrt
from typing import Any

from .diagnostics import Diagnostic, FailureCode, ValidationReport
from .schema import artifact_fingerprint, validate_schema

SUPPORTED_CAPABILITIES = {
    "CORE_STITCHES_V1",
    "SHAPING_V1",
    "MAGIC_RING_V1",
    "MULTI_STITCH_RING_V1",
    "FRONTIER_BRANCHING_V1",
    "COLOR_CHANGES_V1",
    "SEWN_JOINS_V1",
}


def _id_from_ref(reference: Mapping[str, Any]) -> str:
    identifiers = [value for key, value in reference.items() if key.endswith("_id")]
    return str(identifiers[0]) if identifiers else ""


def _is_subsequence(candidate: Sequence[str], source: Sequence[str]) -> bool:
    cursor = iter(source)
    return all(any(value == wanted for value in cursor) for wanted in candidate)


def _rotate_to(values: list[str], anchor: str | None) -> list[str] | None:
    if not values:
        return [] if anchor is None else None
    if anchor not in values:
        return None
    index = values.index(anchor)
    return values[index:] + values[:index]


def _type_a_replicate_estimate(values: Sequence[float]) -> tuple[float, float]:
    """Return the V1 sequential-binary64 mean and Type-A uncertainty of replicates."""
    count = len(values)
    if count < 2:
        raise ValueError("Type-A replicate estimation requires at least two observations")
    total = 0.0
    for value in values:
        total += value
    mean = total / count
    squared_deviations = 0.0
    for value in values:
        deviation = value - mean
        squared_deviations += deviation * deviation
    return mean, sqrt(squared_deviations / (count * (count - 1)))


@dataclass(slots=True)
class _Collector:
    fingerprint: str
    diagnostics: list[Diagnostic]

    def add(
        self,
        code: FailureCode,
        gate: str,
        key: str,
        summary: str,
        *,
        refs: Iterable[str] = (),
        pointers: Iterable[str] = (),
        expected: Any = None,
        observed: Any = None,
        units: str | None = None,
    ) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                gate=gate,
                message_key=key,
                summary=summary,
                artifact_hash=self.fingerprint,
                entity_refs=tuple(refs),
                json_pointers=tuple(pointers),
                expected=expected,
                observed=observed,
                units=units,
            )
        )


class SemanticValidator:
    """Validator with no dependency on solver or artifact-builder logic."""

    def __init__(
        self,
        *,
        design_specs: Mapping[str, dict[str, Any]] | None = None,
        material_profiles: Mapping[str | tuple[str, int], dict[str, Any]] | None = None,
    ) -> None:
        self._design_specs = dict(design_specs or {})
        self._material_profiles = {
            (profile["profile_id"], profile["revision"]): profile
            for profile in (material_profiles or {}).values()
        }

    def validate_material_profile(self, value: dict[str, Any]) -> ValidationReport:
        schema_report = validate_schema("material_profile", value)
        if not schema_report.ok:
            return schema_report
        collector = _Collector(artifact_fingerprint(value), [])
        response_ids: set[str] = set()
        semantic_keys: set[tuple[str, str, str, str]] = set()
        for index, response in enumerate(value["calibration_responses"]):
            response_id = response["response_id"]
            conditions = response["measurement_conditions"]
            semantic_key = (
                conditions["canonical_stitch_type"],
                conditions["course_mode"],
                conditions["tension_profile_id"],
                conditions["fabric_state"],
            )
            if response_id in response_ids:
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "material.duplicate_response_id",
                    "MaterialProfile response IDs must be unique",
                    refs=(response_id,),
                    pointers=(f"/calibration_responses/{index}/response_id",),
                )
            if semantic_key in semantic_keys:
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "material.ambiguous_semantic_key",
                    "A material response semantic key must resolve uniquely",
                    refs=(response_id,),
                    pointers=(f"/calibration_responses/{index}/measurement_conditions",),
                    observed=semantic_key,
                )
            response_ids.add(response_id)
            semantic_keys.add(semantic_key)
            seen_observations: set[str] = set()
            for observation_index, observation in enumerate(response["observations"]):
                marker = repr(sorted(observation.items()))
                if marker in seen_observations:
                    collector.add(
                        FailureCode.COUNT,
                        "V1",
                        "material.duplicate_observation",
                        "Exact duplicate material observations are forbidden",
                        refs=(response_id,),
                        pointers=(
                            f"/calibration_responses/{index}/observations/{observation_index}",
                        ),
                    )
                seen_observations.add(marker)
            if response["uncertainty"]["basis"] == "REPLICATE_COMBINED_STANDARD_UNCERTAINTY":
                from .canonical import jcs_bytes

                ordered = sorted(response["observations"], key=jcs_bytes)
                dimensions = (
                    (
                        "stitch_span_length_mm",
                        "stitch_span_count",
                        "effective_stitch_pitch_mm",
                        "stitch_pitch_standard_uncertainty_mm",
                    ),
                    (
                        "course_span_length_mm",
                        "course_span_count",
                        "effective_course_pitch_mm",
                        "course_pitch_standard_uncertainty_mm",
                    ),
                )
                for length_key, count_key, gauge_key, uncertainty_key in dimensions:
                    values = [
                        observation[length_key] / observation[count_key]
                        for observation in ordered
                    ]
                    estimate, type_a_uncertainty = _type_a_replicate_estimate(values)
                    if response["effective_gauge"][gauge_key] != estimate:
                        collector.add(
                            FailureCode.COUNT,
                            "V1",
                            "material.replicate_gauge_mismatch",
                            "Replicate effective gauge must equal the V1 Type-A mean",
                            refs=(response_id,),
                            pointers=(f"/calibration_responses/{index}/effective_gauge/{gauge_key}",),
                            expected=estimate,
                            observed=response["effective_gauge"][gauge_key],
                            units="mm",
                        )
                    if response["uncertainty"][uncertainty_key] != type_a_uncertainty:
                        collector.add(
                            FailureCode.COUNT,
                            "V1",
                            "material.replicate_uncertainty_mismatch",
                            "Replicate standard uncertainty must equal the V1 Type-A result",
                            refs=(response_id,),
                            pointers=(f"/calibration_responses/{index}/uncertainty/{uncertainty_key}",),
                            expected=type_a_uncertainty,
                            observed=response["uncertainty"][uncertainty_key],
                            units="mm",
                        )
            if len(response["observations"]) == 1:
                observation = response["observations"][0]
                expected_gauge = (
                    observation["stitch_span_length_mm"] / observation["stitch_span_count"],
                    observation["course_span_length_mm"] / observation["course_span_count"],
                )
                observed_gauge = (
                    response["effective_gauge"]["effective_stitch_pitch_mm"],
                    response["effective_gauge"]["effective_course_pitch_mm"],
                )
                if observed_gauge != expected_gauge:
                    collector.add(
                        FailureCode.INPUT,
                        "V1",
                        "material.gauge_observation_mismatch",
                        "Single-observation effective pitches must equal recomputed spans",
                        refs=(response_id,),
                        expected=expected_gauge,
                        observed=observed_gauge,
                        pointers=(f"/calibration_responses/{index}/effective_gauge",),
                    )
        source_ids = value["provenance"]["source_record_ids"]
        if len(source_ids) != len(set(source_ids)):
            collector.add(
                FailureCode.REFERENCE,
                "V1",
                "material.duplicate_source_record",
                "Material source record IDs must be unique",
                pointers=("/provenance/source_record_ids",),
            )
        return ValidationReport.from_iterable(collector.diagnostics)

    def validate_design_spec(self, value: dict[str, Any]) -> ValidationReport:
        schema_report = validate_schema("design_spec", value)
        if not schema_report.ok:
            return schema_report
        collector = _Collector(artifact_fingerprint(value), [])
        self._validate_unique_table(
            collector,
            value["dimensions"]["measurements"],
            "measurement_id",
            "/dimensions/measurements",
        )
        for table, identifier in (
            ("symmetries", "symmetry_id"),
            ("landmarks", "landmark_id"),
            ("colors", "color_id"),
        ):
            self._validate_unique_table(collector, value[table], identifier, f"/{table}")
        measurements = {item["measurement_id"] for item in value["dimensions"]["measurements"]}
        landmarks = {item["landmark_id"] for item in value["landmarks"]}
        target = value["target_geometry"]
        frame_id = target.get("coordinate_frame", {}).get("coordinate_frame_id")
        for table_name in ("symmetries", "landmarks"):
            for index, item in enumerate(value[table_name]):
                if item["coordinate_frame_id"] != frame_id:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V1",
                        "design.unknown_coordinate_frame",
                        "Symmetry and landmark frames must resolve to the target frame",
                        refs=(item["coordinate_frame_id"],),
                        pointers=(f"/{table_name}/{index}/coordinate_frame_id",),
                        expected=frame_id,
                        observed=item["coordinate_frame_id"],
                    )
        for index, parameter in enumerate(target.get("parameters", [])):
            if parameter["measurement_id"] not in measurements:
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "design.unknown_measurement",
                    "Analytic shape parameter references an unknown measurement",
                    refs=(parameter["measurement_id"],),
                    pointers=(f"/target_geometry/parameters/{index}/measurement_id",),
                )
        if "coordinate_frame" in target:
            frame = target["coordinate_frame"]
            if frame["up_axis"].removeprefix("POSITIVE_").removeprefix("NEGATIVE_") == frame[
                "front_axis"
            ].removeprefix("POSITIVE_").removeprefix("NEGATIVE_"):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V1",
                    "design.degenerate_coordinate_frame",
                    "Up and front axes must be linearly independent",
                    pointers=("/target_geometry/coordinate_frame",),
                )
        openings = value["construction_constraints"]["intentional_openings"]
        self._validate_unique_table(
            collector,
            openings,
            "opening_requirement_id",
            "/construction_constraints/intentional_openings",
        )
        for opening_index, opening in enumerate(openings):
            for landmark_id in opening["boundary_landmark_ids"]:
                if landmark_id not in landmarks:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V1",
                        "design.unknown_opening_landmark",
                        "Intentional opening references an unknown landmark",
                        refs=(opening["opening_requirement_id"], landmark_id),
                        pointers=(
                            f"/construction_constraints/intentional_openings/{opening_index}/boundary_landmark_ids",
                        ),
                    )
        domain = value["domain_constraints"]
        referenced_measurements = list(target.get("body_measurement_ids", []))
        referenced_measurements.extend(domain.get("body_measurement_ids", []))
        referenced_measurements.extend(
            item["measurement_id"] for item in domain.get("ease_allowances", [])
        )
        for measurement_id in referenced_measurements:
            if measurement_id not in measurements:
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "design.unknown_domain_measurement",
                    "Domain and garment target measurements must resolve uniquely",
                    refs=(measurement_id,),
                )
        solver = value["solver_options"]
        if not set(solver["solver_family_preference"]).issubset(solver["allowed_solver_families"]):
            collector.add(
                FailureCode.REFERENCE,
                "V1",
                "design.solver_preference_not_allowed",
                "Every preferred solver family must also be allowed",
                pointers=("/solver_options/solver_family_preference",),
            )
        compatible_solvers = {
            "AMIGURUMI_3D": {"ANALYTIC", "GEODESIC", "FRONTIER"},
            "GARMENT": {"GARMENT"},
            "FLAT": {"FLAT"},
            "LACE_MOTIF": {"LACE"},
        }[value["project_type"]]
        incompatible = set(solver["allowed_solver_families"]) - compatible_solvers
        if incompatible:
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "V1",
                "design.solver_domain_mismatch",
                "Allowed solver families must be compatible with the project domain",
                refs=sorted(incompatible),
                expected=sorted(compatible_solvers),
                observed=solver["allowed_solver_families"],
            )
        self._validate_design_target(value, measurements, openings, collector)
        if value["interpretation_provenance"]["unresolved_ambiguities"]:
            collector.add(
                FailureCode.INPUT,
                "V1",
                "design.unresolved_ambiguity",
                "DesignSpec cannot be executable while ambiguity remains",
                pointers=("/interpretation_provenance/unresolved_ambiguities",),
            )
        binding = value["material_profile"]
        if binding["binding_type"] == "INLINE":
            collector.diagnostics.extend(
                self.validate_material_profile(binding["profile"]).diagnostics
            )
        else:
            profile = self._material_profiles.get((binding["profile_id"], binding["revision"]))
            if profile is None:
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "material_profile_ref.unresolved",
                    "Referenced MaterialProfile must be supplied to semantic validation",
                    refs=(binding["profile_id"],),
                    pointers=("/material_profile",),
                )
            else:
                self._validate_material_binding(binding, profile, collector, "/material_profile")
        return ValidationReport.from_iterable(collector.diagnostics)

    @staticmethod
    def _validate_design_target(
        value: dict[str, Any],
        measurement_ids: set[str],
        openings: list[dict[str, Any]],
        collector: _Collector,
    ) -> None:
        target = value["target_geometry"]
        if target["geometry_type"] == "MESH_3D":
            numerical_profile_id = target["preflight_numerical_profile_id"]
            if numerical_profile_id == "v0_num_mesh_binary64_adjacent_barycentric_v2":
                from .v0_adjacent_profile import (
                    AdjacentProfileError,
                    parse_adjacent_exclusion_zone,
                    resolve_v0_adjacent_numeric_profile,
                )

                try:
                    parse_adjacent_exclusion_zone(target["adjacent_exclusion_zone"])
                    resolve_v0_adjacent_numeric_profile(numerical_profile_id)
                except AdjacentProfileError as error:
                    collector.add(
                        FailureCode.INPUT,
                        "V1",
                        "design.adjacent_exclusion_zone_invalid",
                        str(error),
                        pointers=("/target_geometry/adjacent_exclusion_zone",),
                    )
            expected_profile = None
            if value["project_type"] == "AMIGURUMI_3D":
                expected_profile = {
                    "CLOSED": "V0_AMIGURUMI_CLOSED_SURFACE_V1",
                    "DECLARED_OPENINGS": "V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1",
                }[value["domain_constraints"]["surface_mode"]]
            elif value["project_type"] == "GARMENT":
                expected_profile = "V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1"
            if target["preflight_profile_id"] != expected_profile:
                collector.add(
                    FailureCode.INPUT,
                    "V1",
                    "design.mesh_preflight_domain_mismatch",
                    "Mesh preflight profile must match project type and surface mode",
                    expected=expected_profile,
                    observed=target["preflight_profile_id"],
                )
            remain_open_count = sum(
                opening["closure_expectation"] == "REMAIN_OPEN" for opening in openings
            )
            if target["topology_expectation"]["expected_boundary_components"] != (
                remain_open_count
            ):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V1",
                    "design.mesh_opening_count_mismatch",
                    "Mesh boundary count must equal declared REMAIN_OPEN requirements",
                    expected=remain_open_count,
                    observed=target["topology_expectation"]["expected_boundary_components"],
                )
        if target["geometry_type"] != "ANALYTIC_SHAPE":
            return
        required_parameters = {
            "SPHERE": {"RADIUS"},
            "CYLINDER": {"RADIUS", "AXIAL_LENGTH"},
            "CONE": {"BASE_RADIUS", "AXIAL_LENGTH"},
            "ELLIPSOID": {"EQUATORIAL_RADIUS", "POLAR_RADIUS"},
            "SURFACE_OF_REVOLUTION": (
                {"AXIAL_LENGTH"}
                if value.get("schema_version") == "1.2.0"
                and target.get("radial_profile", {}).get("canonicalization_profile")
                == "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
                else {"MERIDIONAL_LENGTH"}
            ),
        }[target["primitive"]]
        observed_parameters = [item["parameter"] for item in target["parameters"]]
        if set(observed_parameters) != required_parameters or len(observed_parameters) != len(
            required_parameters
        ):
            collector.add(
                FailureCode.INPUT,
                "V1",
                "design.analytic_parameter_set",
                "Analytic primitive parameters must match the exact required set",
                expected=sorted(required_parameters),
                observed=observed_parameters,
            )
        if target["primitive"] != "SURFACE_OF_REVOLUTION":
            return
        axis = target["axis_direction"]
        if sum(component * component for component in axis) != 1.0:
            collector.add(
                FailureCode.INPUT,
                "V1",
                "design.axis_not_normalized",
                "Surface-of-revolution axis_direction must be normalized",
                observed=axis,
            )
        profile = target["radial_profile"]
        samples = profile["samples"]
        coordinate_profile = (
            profile["canonicalization_profile"]
            == "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
        )
        if coordinate_profile:
            from .canonical import CanonicalProfile, canonical_hash

            indexes = [sample["sample_index"] for sample in samples]
            radii = [float(sample["radius_mm"]) for sample in samples]
            axial = [float(sample["axial_mm"]) for sample in samples]
            invalid = indexes != list(range(len(samples))) or any(
                not math.isfinite(radius) or radius < 0 for radius in radii
            ) or any(not math.isfinite(coordinate) for coordinate in axial)
            if invalid:
                collector.add(
                    FailureCode.INPUT, "V1", "design.coordinate_profile_values",
                    "Coordinate profile requires contiguous indexes and finite nonnegative radii",
                    pointers=("/target_geometry/radial_profile/samples",),
                )
            parameter = next(
                (item for item in target["parameters"] if item["parameter"] == "AXIAL_LENGTH"),
                None,
            )
            measurement = next(
                (
                    item
                    for item in value["dimensions"]["measurements"]
                    if parameter is not None
                    and item["measurement_id"] == parameter["measurement_id"]
                ),
                None,
            )
            extent = max(axial) - min(axial)
            if (
                not math.isfinite(extent)
                or extent <= 0
                or (measurement is not None and float(measurement["value_mm"]) != extent)
            ):
                collector.add(
                    FailureCode.INPUT, "V1", "design.coordinate_profile_extent",
                    "AXIAL_LENGTH must equal the finite binary64 axial extent",
                    expected=(extent if math.isfinite(extent) else "finite positive axial extent"),
                    observed=None if measurement is None else measurement["value_mm"], units="mm",
                )
            boundary_ids = {opening["opening_requirement_id"] for opening in openings}
            for endpoint in (profile["start_boundary"], profile["end_boundary"]):
                if endpoint["boundary_type"] == "INTENTIONAL_OPENING" and endpoint.get(
                    "opening_requirement_id"
                ) not in boundary_ids:
                    collector.add(
                        FailureCode.REFERENCE, "V1", "design.coordinate_profile_unknown_opening",
                        "Coordinate profile opening must resolve to DesignSpec",
                        refs=(endpoint.get("opening_requirement_id", ""),),
                    )
            payload = dict(profile)
            observed_hash = payload.pop("sha256")
            expected_hash = canonical_hash(
                payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES
            )
            if observed_hash != expected_hash:
                collector.add(
                    FailureCode.DETERMINISM, "V1", "design.coordinate_profile_hash_mismatch",
                    "Coordinate profile hash must match its ordered canonical payload",
                    expected=expected_hash, observed=observed_hash,
                )
            return
        indexes = [sample["sample_index"] for sample in samples]
        positions = [sample["s_mm"] for sample in samples]
        if (
            indexes != list(range(len(samples)))
            or positions[0] != 0
            or any(right <= left for left, right in pairwise(positions))
        ):
            collector.add(
                FailureCode.INPUT,
                "V1",
                "design.radial_profile_order",
                "Radial samples require contiguous indexes and strictly increasing s from zero",
                observed=(indexes, positions),
            )
        parameter = next(
            item for item in target["parameters"] if item["parameter"] == "MERIDIONAL_LENGTH"
        )
        measurement = next(
            (
                item
                for item in value["dimensions"]["measurements"]
                if item["measurement_id"] == parameter["measurement_id"]
            ),
            None,
        )
        if measurement is not None and positions[-1] != measurement["value_mm"]:
            collector.add(
                FailureCode.INPUT,
                "V1",
                "design.radial_profile_endpoint",
                "Final radial sample must equal the MERIDIONAL_LENGTH measurement",
                expected=measurement["value_mm"],
                observed=positions[-1],
                units="mm",
            )
        opening_ids = {opening["opening_requirement_id"] for opening in openings}
        for endpoint in (profile["start_boundary"], profile["end_boundary"]):
            if (
                endpoint["boundary_type"] == "INTENTIONAL_OPENING"
                and endpoint["opening_requirement_id"] not in opening_ids
            ):
                collector.add(
                    FailureCode.REFERENCE,
                    "V1",
                    "design.radial_profile_unknown_opening",
                    "Radial profile endpoint opening must resolve to DesignSpec",
                    refs=(endpoint["opening_requirement_id"],),
                )
        from .canonical import CanonicalProfile, canonical_hash

        payload = dict(profile)
        observed_hash = payload.pop("sha256")
        expected_hash = canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION)
        if observed_hash != expected_hash:
            collector.add(
                FailureCode.DETERMINISM,
                "V1",
                "design.radial_profile_hash_mismatch",
                "Radial profile hash must match its canonical payload",
                expected=expected_hash,
                observed=observed_hash,
            )

    def validate_crochet_ir(
        self,
        value: dict[str, Any],
        design_spec: dict[str, Any] | None = None,
    ) -> ValidationReport:
        schema_report = validate_schema("crochet_ir", value)
        if not schema_report.ok:
            diagnostics = list(schema_report.diagnostics)
            fingerprint = artifact_fingerprint(value)
            stitches = value.get("stitches", [])
            if isinstance(stitches, list):
                for index, stitch in enumerate(stitches):
                    if not isinstance(stitch, dict):
                        continue
                    shaping = stitch.get("shaping")
                    family = stitch.get("stitch_type")
                    arity = (stitch.get("base_arity"), stitch.get("top_arity"))
                    unsupported_shaping = shaping in {"INCREASE", "DECREASE"} and (
                        family != "SINGLE_CROCHET"
                        or (shaping == "INCREASE" and arity != (1, 2))
                        or (shaping == "DECREASE" and arity != (2, 1))
                    )
                    if unsupported_shaping:
                        diagnostics.append(
                            Diagnostic(
                                code=FailureCode.UNSUPPORTED_FEATURE,
                                gate="V3",
                                message_key="stitch.unsupported_form",
                                summary=(
                                    "Stitch shaping is representable by the graph model but "
                                    "unavailable in CROCHET_CORE_1.0.0"
                                ),
                                artifact_hash=fingerprint,
                                entity_refs=(str(stitch.get("stitch_id", f"stitch[{index}]")),),
                                json_pointers=(f"/stitches/{index}",),
                                observed=(family, shaping, *arity),
                            )
                        )
            return ValidationReport.from_iterable(diagnostics)
        collector = _Collector(artifact_fingerprint(value), [])
        tables = self._index_ir_tables(value, collector)
        resolved_design_spec = design_spec or self._design_specs.get(
            value["design_spec_ref"]["design_spec_id"]
        )
        self._validate_capabilities(value, collector)
        self._validate_design_binding(value, resolved_design_spec, collector)
        self._validate_ir_material_bindings(value, collector)
        self._validate_ir_references(value, tables, collector, resolved_design_spec)
        self._validate_sequence(value, tables, collector)
        self._validate_courses(value, tables, collector)
        self._validate_topology_tables(value, tables, collector)
        self._validate_frontier_replay(value, tables, collector, resolved_design_spec)
        self._validate_yarn_paths(value, tables, collector)
        self._validate_multi_stitch_rings(value, tables, collector)
        return ValidationReport.from_iterable(collector.diagnostics)

    @staticmethod
    def _validate_multi_stitch_rings(
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
    ) -> None:
        """Independently check the 1.1 multi-site ring contract (ADR-0016)."""
        if value["semantics_profile"] != "CROCHET_CORE_1.1.0":
            return
        for operation in value["construction_operations"]:
            sites = operation["attachment_location_ids"]
            if operation["operation_type"] != "MAGIC_RING" or len(sites) <= 1:
                continue
            consumers = [
                stitch for stitch in value["stitches"]
                if set(stitch["base_attachment_location_ids"]) & set(sites)
            ]
            by_subject = {stitch["stitch_id"]: stitch for stitch in consumers}
            ordered = [
                by_subject[event["subject_ref"]["stitch_id"]]
                for event in sorted(value["construction_sequence"],
                                    key=lambda item: item["sequence_index"])
                if event["subject_ref"]["entity_type"] == "STITCH"
                and event["subject_ref"]["stitch_id"] in by_subject
            ]
            course_ids = {stitch["course_id"] for stitch in consumers}
            course = tables["courses"].get(next(iter(course_ids))) if len(course_ids) == 1 else None
            valid = (
                len(ordered) == len(sites)
                and all(
                    stitch["stitch_type"] == "SINGLE_CROCHET"
                    and stitch["shaping"] == "PLAIN"
                    and stitch["base_attachment_location_ids"] == [site]
                    for stitch, site in zip(ordered, sites, strict=False)
                )
                and all(tables["attachment_locations"].get(site, {}).get("location_type")
                        == "MAGIC_RING_ANCHOR" for site in sites)
                and course is not None
                and course["ordinal"] == 0
                and course["course_form"] == "CYCLIC"
                and course["input_frontier_ids"] == operation["output_frontier_ids"]
                and len([stitch for stitch in value["stitches"]
                         if stitch["course_id"] in course_ids]) == len(sites)
            )
            if not valid:
                collector.add(
                    FailureCode.FRONTIER, "V4", "magic_ring.initial_course",
                    "Each ring site must feed exactly one ordered plain SC in the initial course",
                    refs=(operation["operation_id"],), expected=list(sites),
                    observed=[stitch["base_attachment_location_ids"] for stitch in ordered],
                )

    def _validate_design_binding(
        self,
        value: dict[str, Any],
        design_spec: dict[str, Any] | None,
        collector: _Collector,
    ) -> None:
        if design_spec is None:
            collector.add(
                FailureCode.REFERENCE,
                "V2",
                "design_spec_ref.unresolved",
                "Referenced DesignSpec must be supplied to semantic validation",
                refs=(value["design_spec_ref"]["design_spec_id"],),
                pointers=("/design_spec_ref",),
            )
            return
        design_report = self.validate_design_spec(design_spec)
        collector.diagnostics.extend(design_report.diagnostics)
        if not design_report.ok:
            return
        from .canonical import CanonicalProfile, canonical_hash

        reference = value["design_spec_ref"]
        expected_hash = canonical_hash(design_spec, CanonicalProfile.DESIGN_SPEC, validator=self)
        if (
            reference["design_spec_id"] != design_spec["design_spec_id"]
            or reference["sha256"] != expected_hash
        ):
            collector.add(
                FailureCode.REFERENCE,
                "V2",
                "design_spec_ref.content_mismatch",
                "CrochetIR DesignSpec ID and hash must match the validated DesignSpec",
                refs=(reference["design_spec_id"],),
                pointers=("/design_spec_ref",),
                expected=(design_spec["design_spec_id"], expected_hash),
                observed=(reference["design_spec_id"], reference["sha256"]),
            )

    def _validate_ir_material_bindings(self, value: dict[str, Any], collector: _Collector) -> None:
        for index, yarn in enumerate(value["yarns"]):
            binding = yarn["material_profile_ref"]
            profile = self._material_profiles.get((binding["profile_id"], binding["revision"]))
            pointer = f"/yarns/{index}/material_profile_ref"
            if profile is None:
                collector.add(
                    FailureCode.REFERENCE,
                    "V2",
                    "material_profile_ref.unresolved",
                    "Referenced MaterialProfile must be supplied to semantic validation",
                    refs=(binding["profile_id"],),
                    pointers=(pointer,),
                )
                continue
            self._validate_material_binding(binding, profile, collector, pointer)

    def _validate_material_binding(
        self,
        binding: Mapping[str, Any],
        profile: dict[str, Any],
        collector: _Collector,
        pointer: str,
    ) -> None:
        report = self.validate_material_profile(profile)
        collector.diagnostics.extend(report.diagnostics)
        if not report.ok:
            return
        from .canonical import CanonicalProfile, canonical_hash

        expected = (
            profile["profile_id"],
            profile["revision"],
            canonical_hash(profile, CanonicalProfile.MATERIAL_PROFILE),
        )
        observed = (binding["profile_id"], binding["revision"], binding["sha256"])
        if observed != expected:
            collector.add(
                FailureCode.REFERENCE,
                "V2",
                "material_profile_ref.content_mismatch",
                "MaterialProfile ID, revision, and hash must match resolved canonical content",
                refs=(binding["profile_id"],),
                pointers=(pointer,),
                expected=expected,
                observed=observed,
            )

    @staticmethod
    def _validate_unique_table(
        collector: _Collector,
        values: Sequence[Mapping[str, Any]],
        identifier: str,
        pointer: str,
    ) -> None:
        counts = Counter(item[identifier] for item in values)
        for duplicate, count in counts.items():
            if count > 1:
                collector.add(
                    FailureCode.REFERENCE,
                    "V2",
                    "identity.duplicate_id",
                    "Explicit IDs must be unique",
                    refs=(str(duplicate),),
                    pointers=(pointer,),
                    observed=count,
                )

    def _index_ir_tables(
        self, value: dict[str, Any], collector: _Collector
    ) -> dict[str, dict[str, dict[str, Any]]]:
        declarations = {
            "colors": "color_id",
            "yarns": "yarn_id",
            "attachment_locations": "attachment_location_id",
            "stitches": "stitch_id",
            "construction_operations": "operation_id",
            "construction_sequence": "event_id",
            "courses": "course_id",
            "frontiers": "frontier_id",
            "frontier_transitions": "frontier_transition_id",
            "branches": "branch_id",
            "components": "component_id",
            "openings": "opening_id",
            "yarn_paths": "yarn_path_id",
            "derivations": "derivation_id",
        }
        tables: dict[str, dict[str, dict[str, Any]]] = {}
        global_ids: dict[str, str] = {}
        for table, identifier in declarations.items():
            self._validate_unique_table(collector, value[table], identifier, f"/{table}")
            tables[table] = {item[identifier]: item for item in value[table]}
            for entity_id in tables[table]:
                prior = global_ids.get(entity_id)
                if prior is not None:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V2",
                        "identity.cross_namespace_collision",
                        "Typed entity IDs must not collide across tables",
                        refs=(entity_id,),
                        pointers=(f"/{prior}", f"/{table}"),
                    )
                global_ids[entity_id] = table
        return tables

    @staticmethod
    def _validate_capabilities(value: dict[str, Any], collector: _Collector) -> None:
        declared = set(value["required_capabilities"])
        unsupported = sorted(declared - SUPPORTED_CAPABILITIES)
        for capability in unsupported:
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "V2",
                "capability.unsupported",
                "CrochetIR requires a capability unavailable in Milestone 0",
                refs=(capability,),
                pointers=("/required_capabilities",),
            )
        implied = {"CORE_STITCHES_V1"}
        if any(stitch["shaping"] != "PLAIN" for stitch in value["stitches"]):
            implied.add("SHAPING_V1")
        operation_types = {
            operation["operation_type"] for operation in value["construction_operations"]
        }
        if "MAGIC_RING" in operation_types:
            implied.add("MAGIC_RING_V1")
        if any(operation["operation_type"] == "MAGIC_RING"
               and len(operation["attachment_location_ids"]) > 1
               for operation in value["construction_operations"]):
            implied.add("MULTI_STITCH_RING_V1")
        if operation_types & {"SPLIT", "RESERVE", "ATTACH", "JOIN"}:
            implied.add("FRONTIER_BRANCHING_V1")
        if "COLOR_CHANGE" in operation_types:
            implied.add("COLOR_CHANGES_V1")
        if any(
            operation["operation_type"] == "JOIN" and operation["join_method"] == "SEWN"
            for operation in value["construction_operations"]
        ):
            implied.add("SEWN_JOINS_V1")
        location_types = {location["location_type"] for location in value["attachment_locations"]}
        if "CHAIN_SPACE" in location_types:
            implied.add("CHAIN_SPACES_V1")
        if "MOTIF_ATTACHMENT_POINT" in location_types:
            implied.add("MOTIF_ATTACHMENTS_V1")
        for missing in sorted(implied - declared):
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "V2",
                "capability.missing_declaration",
                "CrochetIR must declare every capability required by its semantics",
                refs=(missing,),
                pointers=("/required_capabilities",),
            )

    def _validate_ir_references(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
        design_spec: dict[str, Any] | None,
    ) -> None:
        def require(table: str, entity_id: str | None, pointer: str) -> None:
            if entity_id is not None and entity_id not in tables[table]:
                collector.add(
                    FailureCode.REFERENCE,
                    "V2",
                    "reference.dangling",
                    f"Reference does not resolve to {table}",
                    refs=(entity_id,),
                    pointers=(pointer,),
                )

        for index, yarn in enumerate(value["yarns"]):
            require("colors", yarn["color_id"], f"/yarns/{index}/color_id")
        unused_colors = set(tables["colors"]) - {yarn["color_id"] for yarn in value["yarns"]}
        for color_id in sorted(unused_colors):
            collector.add(
                FailureCode.REFERENCE,
                "V2",
                "color.unused",
                "Every canonical color must be referenced by at least one yarn",
                refs=(color_id,),
                pointers=("/colors",),
            )
        for index, location in enumerate(value["attachment_locations"]):
            producer = location["producer_ref"]
            table = "stitches" if producer["entity_type"] == "STITCH" else "construction_operations"
            require(table, _id_from_ref(producer), f"/attachment_locations/{index}/producer_ref")
        for index, stitch in enumerate(value["stitches"]):
            for location_id in (
                stitch["base_attachment_location_ids"] + stitch["top_attachment_location_ids"]
            ):
                require("attachment_locations", location_id, f"/stitches/{index}")
            require(
                "frontiers",
                stitch["frontier_edit"]["frontier_id"],
                f"/stitches/{index}/frontier_edit/frontier_id",
            )
            edit = stitch["frontier_edit"]
            if edit["edit_type"] == "INSERT_AT_GAP":
                require(
                    "attachment_locations",
                    edit["left_location_id"],
                    f"/stitches/{index}/frontier_edit/left_location_id",
                )
                require(
                    "attachment_locations",
                    edit["right_location_id"],
                    f"/stitches/{index}/frontier_edit/right_location_id",
                )
            require("yarns", stitch["yarn_id"], f"/stitches/{index}/yarn_id")
            require("colors", stitch["color_id"], f"/stitches/{index}/color_id")
            require("courses", stitch["course_id"], f"/stitches/{index}/course_id")
            require("derivations", stitch["derivation_id"], f"/stitches/{index}/derivation_id")
        for index, operation in enumerate(value["construction_operations"]):
            for frontier_id in operation["input_frontier_ids"] + operation["output_frontier_ids"]:
                require("frontiers", frontier_id, f"/construction_operations/{index}")
            for location_id in operation["attachment_location_ids"]:
                require(
                    "attachment_locations",
                    location_id,
                    f"/construction_operations/{index}/attachment_location_ids",
                )
            for yarn_id in operation["input_yarn_ids"] + operation["output_yarn_ids"]:
                require("yarns", yarn_id, f"/construction_operations/{index}")
            require(
                "openings", operation["opening_id"], f"/construction_operations/{index}/opening_id"
            )
            require(
                "derivations",
                operation["derivation_id"],
                f"/construction_operations/{index}/derivation_id",
            )
            for mapping_index, mapping in enumerate(operation["join_input_mappings"]):
                require(
                    "frontiers",
                    mapping["input_frontier_id"],
                    f"/construction_operations/{index}/join_input_mappings/{mapping_index}",
                )
                for location_id in mapping["consumed_attachment_location_ids"]:
                    require(
                        "attachment_locations",
                        location_id,
                        f"/construction_operations/{index}/join_input_mappings/{mapping_index}",
                    )
        for index, event in enumerate(value["construction_sequence"]):
            subject = event["subject_ref"]
            table = "stitches" if subject["entity_type"] == "STITCH" else "construction_operations"
            require(table, _id_from_ref(subject), f"/construction_sequence/{index}/subject_ref")
            require(
                "yarns",
                event["active_yarn_id_before"],
                f"/construction_sequence/{index}/active_yarn_id_before",
            )
            require(
                "yarns",
                event["active_yarn_id_after"],
                f"/construction_sequence/{index}/active_yarn_id_after",
            )
            require(
                "colors",
                event["active_color_id_before"],
                f"/construction_sequence/{index}/active_color_id_before",
            )
            require(
                "colors",
                event["active_color_id_after"],
                f"/construction_sequence/{index}/active_color_id_after",
            )
            for transition_id in event["frontier_transition_ids"]:
                require(
                    "frontier_transitions",
                    transition_id,
                    f"/construction_sequence/{index}/frontier_transition_ids",
                )
        for index, course in enumerate(value["courses"]):
            require("components", course["component_id"], f"/courses/{index}/component_id")
            require("branches", course["branch_id"], f"/courses/{index}/branch_id")
            require("derivations", course["derivation_id"], f"/courses/{index}/derivation_id")
            for event_id in course["member_event_ids"]:
                require("construction_sequence", event_id, f"/courses/{index}/member_event_ids")
            for frontier_id in course["input_frontier_ids"] + course["output_frontier_ids"]:
                require("frontiers", frontier_id, f"/courses/{index}")
        for index, frontier in enumerate(value["frontiers"]):
            require("components", frontier["component_id"], f"/frontiers/{index}/component_id")
            require("branches", frontier["branch_id"], f"/frontiers/{index}/branch_id")
            require("yarns", frontier["active_yarn_id"], f"/frontiers/{index}/active_yarn_id")
            require(
                "frontier_transitions",
                frontier["created_by_transition_id"],
                f"/frontiers/{index}/created_by_transition_id",
            )
            for location_id in frontier["attachment_location_ids"]:
                require(
                    "attachment_locations",
                    location_id,
                    f"/frontiers/{index}/attachment_location_ids",
                )
            require(
                "attachment_locations",
                frontier["anchor_attachment_location_id"],
                f"/frontiers/{index}/anchor_attachment_location_id",
            )
        for index, transition in enumerate(value["frontier_transitions"]):
            for frontier_id in transition["input_frontier_ids"] + transition["output_frontier_ids"]:
                require("frontiers", frontier_id, f"/frontier_transitions/{index}")
            for field in (
                "retired_attachment_location_ids",
                "created_attachment_location_ids",
                "reserved_attachment_location_ids",
            ):
                for location_id in transition[field]:
                    require(
                        "attachment_locations",
                        location_id,
                        f"/frontier_transitions/{index}/{field}",
                    )
            require(
                "openings", transition["opening_id"], f"/frontier_transitions/{index}/opening_id"
            )
        for index, branch in enumerate(value["branches"]):
            require("components", branch["component_id"], f"/branches/{index}/component_id")
            require(
                "frontier_transitions",
                branch["created_by_transition_id"],
                f"/branches/{index}/created_by_transition_id",
            )
            for branch_id in branch["parent_branch_ids"]:
                require("branches", branch_id, f"/branches/{index}/parent_branch_ids")
            for course_id in branch["course_ids"]:
                require("courses", course_id, f"/branches/{index}/course_ids")
            for frontier_id in branch["entry_frontier_ids"] + branch["terminal_frontier_ids"]:
                require("frontiers", frontier_id, f"/branches/{index}")
        for index, component in enumerate(value["components"]):
            for branch_id in component["branch_ids"]:
                require("branches", branch_id, f"/components/{index}/branch_ids")
            for frontier_id in (
                component["initial_frontier_ids"] + component["terminal_frontier_ids"]
            ):
                require("frontiers", frontier_id, f"/components/{index}")
        for index, opening in enumerate(value["openings"]):
            require("components", opening["component_id"], f"/openings/{index}/component_id")
            require(
                "construction_operations",
                opening["declared_by_operation_id"],
                f"/openings/{index}/declared_by_operation_id",
            )
            require("derivations", opening["derivation_id"], f"/openings/{index}/derivation_id")
            for location_id in opening["boundary_attachment_location_ids"]:
                require(
                    "attachment_locations",
                    location_id,
                    f"/openings/{index}/boundary_attachment_location_ids",
                )
        for index, derivation in enumerate(value["derivations"]):
            for reference in derivation["subject_refs"]:
                entity_type = reference["entity_type"]
                table = {
                    "STITCH": "stitches",
                    "CONSTRUCTION_OPERATION": "construction_operations",
                    "COURSE": "courses",
                    "FRONTIER": "frontiers",
                    "OPENING": "openings",
                }[entity_type]
                require(table, _id_from_ref(reference), f"/derivations/{index}/subject_refs")
        derivation_subjects = {
            derivation_id: {
                (reference["entity_type"], _id_from_ref(reference))
                for reference in derivation["subject_refs"]
            }
            for derivation_id, derivation in tables["derivations"].items()
        }
        for table, entity_type, identifier in (
            ("stitches", "STITCH", "stitch_id"),
            ("construction_operations", "CONSTRUCTION_OPERATION", "operation_id"),
            ("courses", "COURSE", "course_id"),
            ("openings", "OPENING", "opening_id"),
        ):
            for entity in value[table]:
                subject = (entity_type, entity[identifier])
                if subject not in derivation_subjects.get(entity["derivation_id"], set()):
                    collector.add(
                        FailureCode.PROVENANCE,
                        "V2",
                        "derivation.subject_mismatch",
                        "An entity's derivation must name that entity as a subject",
                        refs=(entity[identifier], entity["derivation_id"]),
                        pointers=(f"/{table}", "/derivations"),
                    )
        if design_spec is not None:
            requirements = {
                item["opening_requirement_id"]: item
                for item in design_spec["construction_constraints"]["intentional_openings"]
            }
            requirement_use = Counter(
                opening["design_requirement_id"] for opening in value["openings"]
            )
            for opening in value["openings"]:
                requirement = requirements.get(opening["design_requirement_id"])
                if requirement is None:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V4",
                        "opening.unknown_design_requirement",
                        "Opening must resolve to a DesignSpec requirement",
                        refs=(opening["opening_id"], opening["design_requirement_id"]),
                    )
                elif (
                    opening["purpose"] != requirement["purpose"]
                    or opening["closure_expectation"] != requirement["closure_expectation"]
                ):
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "opening.design_semantics_mismatch",
                        "Opening purpose and closure expectation must match DesignSpec",
                        refs=(opening["opening_id"], opening["design_requirement_id"]),
                        expected=(
                            requirement["purpose"],
                            requirement["closure_expectation"],
                        ),
                        observed=(opening["purpose"], opening["closure_expectation"]),
                    )
                if requirement_use[opening["design_requirement_id"]] != 1:
                    collector.add(
                        FailureCode.COUNT,
                        "V4",
                        "opening.design_requirement_not_unique",
                        "A DesignSpec opening requirement can bind at most one CrochetIR opening",
                        refs=(opening["design_requirement_id"],),
                        observed=requirement_use[opening["design_requirement_id"]],
                    )

    def _validate_sequence(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
    ) -> None:
        events = sorted(value["construction_sequence"], key=lambda item: item["sequence_index"])
        if [item["sequence_index"] for item in events] != list(range(len(events))):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "sequence.noncontiguous",
                "Event indexes must be contiguous",
                pointers=("/construction_sequence",),
            )
        subject_counts = Counter(
            (item["subject_ref"]["entity_type"], _id_from_ref(item["subject_ref"]))
            for item in events
        )
        expected_subjects = {("STITCH", key) for key in tables["stitches"]} | {
            ("CONSTRUCTION_OPERATION", key) for key in tables["construction_operations"]
        }
        if set(subject_counts) != expected_subjects or any(
            count != 1 for count in subject_counts.values()
        ):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "sequence.subject_membership",
                "Each stitch and operation must occur exactly once",
                pointers=("/construction_sequence",),
                expected=sorted(expected_subjects),
                observed=sorted(subject_counts.items()),
            )
        prior = None
        transition_to_event: dict[str, str] = {}
        colors_by_yarn = {yarn_id: yarn["color_id"] for yarn_id, yarn in tables["yarns"].items()}
        for event in events:
            if prior is not None and (
                event["active_yarn_id_before"] != prior["active_yarn_id_after"]
                or event["active_color_id_before"] != prior["active_color_id_after"]
            ):
                collector.add(
                    FailureCode.REFERENCE,
                    "V3",
                    "sequence.active_state_discontinuity",
                    "Active yarn/color state must be continuous",
                    refs=(event["event_id"],),
                )
            for side in ("before", "after"):
                yarn_id = event[f"active_yarn_id_{side}"]
                color_id = event[f"active_color_id_{side}"]
                expected_color = colors_by_yarn.get(yarn_id) if yarn_id is not None else None
                if color_id != expected_color:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "sequence.yarn_color_mismatch",
                        "Active color must be exactly the color bound to the active yarn",
                        refs=(event["event_id"],),
                        expected=expected_color,
                        observed=color_id,
                    )
            subject = event["subject_ref"]
            if subject["entity_type"] == "STITCH":
                stitch = tables["stitches"].get(subject["stitch_id"])
                if stitch is not None:
                    expected_state = (
                        stitch["yarn_id"],
                        stitch["yarn_id"],
                        stitch["color_id"],
                        stitch["color_id"],
                    )
                    observed_state = (
                        event["active_yarn_id_before"],
                        event["active_yarn_id_after"],
                        event["active_color_id_before"],
                        event["active_color_id_after"],
                    )
                    if observed_state != expected_state:
                        collector.add(
                            FailureCode.REFERENCE,
                            "V3",
                            "sequence.stitch_active_state",
                            "A stitch executes with its declared yarn and color unchanged",
                            refs=(event["event_id"], stitch["stitch_id"]),
                            expected=expected_state,
                            observed=observed_state,
                        )
                expected_transition_count = 1
            else:
                operation = tables["construction_operations"].get(subject["operation_id"])
                expected_transition_count = 0
                if operation is not None:
                    operation_type = operation["operation_type"]
                    expected_transition_count = (
                        0 if operation_type in {"COLOR_CHANGE", "CUT_YARN"} else 1
                    )
                    before_yarn = event["active_yarn_id_before"]
                    after_yarn = event["active_yarn_id_after"]
                    expected_yarns: tuple[str | None, str | None]
                    if operation_type in {"MAGIC_RING", "ATTACH"}:
                        expected_yarns = (None, operation["output_yarn_ids"][0])
                    elif operation_type == "COLOR_CHANGE":
                        expected_yarns = (
                            operation["input_yarn_ids"][0],
                            operation["output_yarn_ids"][0],
                        )
                    elif operation_type == "CUT_YARN":
                        expected_yarns = (operation["input_yarn_ids"][0], None)
                    else:
                        expected_yarns = (before_yarn, before_yarn)
                    if (before_yarn, after_yarn) != expected_yarns:
                        collector.add(
                            FailureCode.REFERENCE,
                            "V3",
                            "sequence.operation_active_state",
                            "Operation event yarn state must match its explicit yarn semantics",
                            refs=(event["event_id"], operation["operation_id"]),
                            expected=expected_yarns,
                            observed=(before_yarn, after_yarn),
                        )
            if len(event["frontier_transition_ids"]) != expected_transition_count:
                collector.add(
                    FailureCode.COUNT,
                    "V3",
                    "sequence.subject_transition_count",
                    "Each event must carry exactly the transitions required by its subject",
                    refs=(event["event_id"],),
                    expected=expected_transition_count,
                    observed=len(event["frontier_transition_ids"]),
                )
            prior = event
            for transition_id in event["frontier_transition_ids"]:
                if transition_id in transition_to_event:
                    collector.add(
                        FailureCode.COUNT,
                        "V3",
                        "sequence.transition_reused",
                        "A frontier transition belongs to exactly one event",
                        refs=(transition_id,),
                    )
                transition_to_event[transition_id] = event["event_id"]
        if set(transition_to_event) != set(tables["frontier_transitions"]):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "sequence.transition_membership",
                "Every frontier transition must belong to exactly one event",
                pointers=("/construction_sequence",),
            )
        for transition in value["frontier_transitions"]:
            index = transition["after_event_index"]
            if index >= len(events):
                collector.add(
                    FailureCode.REFERENCE,
                    "V3",
                    "transition.event_index_out_of_range",
                    "Transition after_event_index must resolve to an event",
                    refs=(transition["frontier_transition_id"],),
                    pointers=("/frontier_transitions",),
                    expected=f"0..{len(events) - 1}",
                    observed=index,
                )
                continue
            event = events[index]
            if (
                transition["frontier_transition_id"] not in event["frontier_transition_ids"]
                or transition["caused_by_subject_ref"] != event["subject_ref"]
            ):
                collector.add(
                    FailureCode.REFERENCE,
                    "V3",
                    "transition.event_mismatch",
                    "Transition event index, event membership, and cause must agree",
                    refs=(transition["frontier_transition_id"], event["event_id"]),
                )

    def _validate_courses(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
    ) -> None:
        if len(value["course_order"]) != len(set(value["course_order"])) or set(
            value["course_order"]
        ) != set(tables["courses"]):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "course.order_membership",
                "course_order must contain every course exactly once",
                pointers=("/course_order",),
            )
        course_positions = {
            course_id: index for index, course_id in enumerate(value["course_order"])
        }
        for branch in value["branches"]:
            ordered_courses = sorted(
                (tables["courses"][course_id] for course_id in branch["course_ids"]),
                key=lambda course: course_positions[course["course_id"]],
            )
            observed_ordinals = [course["ordinal"] for course in ordered_courses]
            expected_ordinals = list(range(len(ordered_courses)))
            if observed_ordinals != expected_ordinals:
                collector.add(
                    FailureCode.COUNT,
                    "V3",
                    "course.ordinal_sequence",
                    "Course ordinals must be contiguous in branch-local course order",
                    refs=(branch["branch_id"],),
                    expected=expected_ordinals,
                    observed=observed_ordinals,
                )
        event_to_course: Counter[str] = Counter()
        for course in value["courses"]:
            for event_id in course["member_event_ids"]:
                event_to_course[event_id] += 1
        for stitch in value["stitches"]:
            events = [
                event
                for event in value["construction_sequence"]
                if event["subject_ref"]
                == {"entity_type": "STITCH", "stitch_id": stitch["stitch_id"]}
            ]
            if (
                not events
                or event_to_course[events[0]["event_id"]] != 1
                or events[0]["event_id"]
                not in tables["courses"][stitch["course_id"]]["member_event_ids"]
            ):
                collector.add(
                    FailureCode.COUNT,
                    "V3",
                    "course.stitch_membership",
                    "Each stitch event belongs to exactly its declared course",
                    refs=(stitch["stitch_id"], stitch["course_id"]),
                )

    def _validate_topology_tables(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
    ) -> None:
        branches = tables["branches"]
        components = tables["components"]
        frontiers = tables["frontiers"]
        courses = tables["courses"]
        for component_id, component in components.items():
            expected_branches = {
                branch_id
                for branch_id, branch in branches.items()
                if branch["component_id"] == component_id
            }
            if set(component["branch_ids"]) != expected_branches:
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "component.branch_membership",
                    "Component branch_ids must contain exactly its branches",
                    refs=(component_id,),
                    expected=sorted(expected_branches),
                    observed=sorted(component["branch_ids"]),
                )
        for branch_id, branch in branches.items():
            expected_courses = {
                course_id
                for course_id, course in courses.items()
                if course["branch_id"] == branch_id
            }
            if set(branch["course_ids"]) != expected_courses:
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "branch.course_membership",
                    "Branch course_ids must contain exactly its courses",
                    refs=(branch_id,),
                    expected=sorted(expected_courses),
                    observed=sorted(branch["course_ids"]),
                )
            for frontier_id in branch["entry_frontier_ids"] + branch["terminal_frontier_ids"]:
                frontier = frontiers.get(frontier_id)
                if frontier is not None and (
                    frontier["branch_id"] != branch_id
                    or frontier["component_id"] != branch["component_id"]
                ):
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "branch.frontier_membership",
                        "Branch entry and terminal frontiers must belong to that branch/component",
                        refs=(branch_id, frontier_id),
                    )
        for course_id, course in courses.items():
            course_branch = branches.get(course["branch_id"])
            if (
                course_branch is not None
                and course_branch["component_id"] != course["component_id"]
            ):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "course.component_mismatch",
                    "Course component must equal its branch component",
                    refs=(course_id, course["branch_id"]),
                )
            member_indexes = [
                tables["construction_sequence"][event_id]["sequence_index"]
                for event_id in course["member_event_ids"]
                if event_id in tables["construction_sequence"]
            ]
            if member_indexes != sorted(member_indexes):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "course.member_order",
                    "Course member events must preserve global execution order",
                    refs=(course_id,),
                )
            current_frontiers = list(course["input_frontier_ids"])
            course_replay_valid = True
            for event_id in course["member_event_ids"]:
                event = tables["construction_sequence"].get(event_id)
                if event is None:
                    course_replay_valid = False
                    continue
                for transition_id in event["frontier_transition_ids"]:
                    transition = tables["frontier_transitions"].get(transition_id)
                    if transition is None:
                        course_replay_valid = False
                        continue
                    inputs = transition["input_frontier_ids"]
                    if any(frontier_id not in current_frontiers for frontier_id in inputs):
                        course_replay_valid = False
                        continue
                    current_frontiers = [
                        frontier_id
                        for frontier_id in current_frontiers
                        if frontier_id not in inputs
                    ]
                    current_frontiers.extend(transition["output_frontier_ids"])
            if not course_replay_valid or current_frontiers != course["output_frontier_ids"]:
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "course.frontier_boundary_mismatch",
                    "Course input/member/output frontiers must form one explicit replay boundary",
                    refs=(course_id,),
                    expected=course["output_frontier_ids"],
                    observed=current_frontiers,
                )
            for frontier_id in course["input_frontier_ids"] + course["output_frontier_ids"]:
                frontier = frontiers.get(frontier_id)
                if frontier is not None and (
                    frontier["branch_id"] != course["branch_id"]
                    or frontier["component_id"] != course["component_id"]
                ):
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "course.frontier_membership",
                        "Course frontiers must belong to its branch/component",
                        refs=(course_id, frontier_id),
                    )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(branch_id: str) -> None:
            if branch_id in visiting:
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "branch.parent_cycle",
                    "Branch parent relationships must form an acyclic graph",
                    refs=(branch_id,),
                )
                return
            if branch_id in visited:
                return
            visiting.add(branch_id)
            for parent_id in branches[branch_id]["parent_branch_ids"]:
                if parent_id in branches:
                    visit(parent_id)
            visiting.remove(branch_id)
            visited.add(branch_id)

        for branch_id in branches:
            visit(branch_id)
        consumed_frontiers = {
            frontier_id
            for transition in value["frontier_transitions"]
            for frontier_id in transition["input_frontier_ids"]
        }
        transitions_by_input: dict[str, list[dict[str, Any]]] = {}
        for transition in value["frontier_transitions"]:
            for frontier_id in transition["input_frontier_ids"]:
                transitions_by_input.setdefault(frontier_id, []).append(transition)
        for branch_id, branch in branches.items():
            for frontier_id in branch["terminal_frontier_ids"]:
                continues_same_branch = any(
                    any(
                        frontiers[output_id]["branch_id"] == branch_id
                        for output_id in transition["output_frontier_ids"]
                        if output_id in frontiers
                    )
                    for transition in transitions_by_input.get(frontier_id, [])
                )
                if continues_same_branch:
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "branch.nonterminal_frontier",
                        "A branch terminal frontier cannot continue into the same branch",
                        refs=(branch_id, frontier_id),
                    )
        for component_id, component in components.items():
            for frontier_id in component["initial_frontier_ids"]:
                frontier = frontiers.get(frontier_id)
                if frontier is None:
                    continue
                transition = tables["frontier_transitions"].get(
                    frontier["created_by_transition_id"]
                )
                if transition is None or transition["transition_type"] != "CREATE":
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "component.initial_frontier",
                        "Component initial frontiers must be introduced by CREATE",
                        refs=(component_id, frontier_id),
                    )
            for frontier_id in component["terminal_frontier_ids"]:
                frontier = frontiers.get(frontier_id)
                if frontier is not None and (
                    frontier["lifecycle_state"] not in {"CLOSED", "DECLARED_OPEN"}
                    or frontier_id in consumed_frontiers
                ):
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "component.terminal_frontier",
                        "Component terminal frontiers must be unconsumed CLOSED or "
                        "DECLARED_OPEN states",
                        refs=(component_id, frontier_id),
                    )

    def _validate_frontier_replay(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
        design_spec: dict[str, Any] | None,
    ) -> None:
        transitions = sorted(
            value["frontier_transitions"], key=lambda item: item["transition_index"]
        )
        if [item["transition_index"] for item in transitions] != list(range(len(transitions))):
            collector.add(
                FailureCode.COUNT,
                "V4",
                "transition.noncontiguous",
                "Frontier transition indexes must be contiguous",
                pointers=("/frontier_transitions",),
            )
        frontiers = tables["frontiers"]
        locations = tables["attachment_locations"]
        for snapshot in frontiers.values():
            if (
                snapshot["topology"] == "CYCLIC"
                and snapshot["lifecycle_state"] in {"ACTIVE", "RESERVED"}
                and snapshot["attachment_location_ids"][0]
                != snapshot["anchor_attachment_location_id"]
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "frontier.cyclic_anchor_origin",
                    "A live cyclic frontier must serialize from its declared anchor",
                    refs=(snapshot["frontier_id"], snapshot["anchor_attachment_location_id"]),
                    pointers=("/frontiers",),
                    expected=snapshot["anchor_attachment_location_id"],
                    observed=snapshot["attachment_location_ids"][0],
                )
        current: set[str] = set()
        produced_frontiers: set[str] = set()
        ownership: dict[str, str] = {}
        for transition in transitions:
            transition_id = transition["frontier_transition_id"]
            inputs = transition["input_frontier_ids"]
            outputs = transition["output_frontier_ids"]
            if any(frontier_id not in current for frontier_id in inputs):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "frontier.input_not_current",
                    "A transition must consume current frontier obligations",
                    refs=(transition_id, *inputs),
                )
            if len(inputs) != len(set(inputs)) or any(
                frontier_id in produced_frontiers for frontier_id in outputs
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "frontier.reuse",
                    "Frontier inputs and outputs must be unique immutable snapshots",
                    refs=(transition_id,),
                )
            for output_id in outputs:
                if (
                    output_id in frontiers
                    and frontiers[output_id]["created_by_transition_id"] != transition_id
                ):
                    collector.add(
                        FailureCode.REFERENCE,
                        "V4",
                        "frontier.creator_mismatch",
                        "Frontier creator must match its producing transition",
                        refs=(transition_id, output_id),
                    )
            transition_type = transition["transition_type"]
            subject = transition["caused_by_subject_ref"]
            if (
                transition_type == "ADVANCE"
                and subject["entity_type"] == "STITCH"
                and inputs
                and outputs
            ):
                stitch = tables["stitches"].get(subject["stitch_id"])
                if stitch is not None:
                    self._validate_advance(stitch, transition, frontiers, locations, collector)
            elif subject["entity_type"] == "CONSTRUCTION_OPERATION":
                operation = tables["construction_operations"].get(subject["operation_id"])
                if operation is not None:
                    self._validate_operation_transition(
                        operation, transition, frontiers, collector, design_spec, tables,
                        value["semantics_profile"],
                    )
            else:
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "transition.invalid_cause",
                    "Non-ADVANCE transitions must be caused by construction operations",
                    refs=(transition_id,),
                )
            current.difference_update(inputs)
            current.update(outputs)
            produced_frontiers.update(outputs)
            for location_id in transition["retired_attachment_location_ids"]:
                if ownership.get(location_id) not in {"ACTIVE", "RESERVED"}:
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "ownership.illegal_retire",
                        "Only a live attachment location can retire",
                        refs=(transition_id, location_id),
                        observed=ownership.get(location_id),
                    )
                ownership[location_id] = "RETIRED"
            for ordinal, location_id in enumerate(transition["created_attachment_location_ids"]):
                if location_id in ownership:
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "ownership.recreated",
                        "Attachment locations have exactly one creation",
                        refs=(transition_id, location_id),
                    )
                location = locations.get(location_id)
                if location is not None and (
                    location["producer_ref"] != transition["caused_by_subject_ref"]
                    or location["ordinal_within_producer"] != ordinal
                ):
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "attachment.producer_transition_mismatch",
                        "A created location must name the transition subject and matching ordinal",
                        refs=(transition_id, location_id),
                        expected=(transition["caused_by_subject_ref"], ordinal),
                        observed=(
                            location["producer_ref"],
                            location["ordinal_within_producer"],
                        ),
                    )
                ownership[location_id] = "ACTIVE"
            output_live: dict[str, str] = {}
            for output_id in outputs:
                frontier = frontiers.get(output_id)
                if frontier is None:
                    continue
                state = frontier["lifecycle_state"]
                ledger_state = {
                    "ACTIVE": "ACTIVE",
                    "RESERVED": "RESERVED",
                    "DECLARED_OPEN": "DECLARED_OPEN",
                }.get(state)
                for location_id in frontier["attachment_location_ids"]:
                    if location_id in output_live:
                        collector.add(
                            FailureCode.FRONTIER,
                            "V4",
                            "ownership.shared_live_location",
                            "A location cannot be live in two output frontiers",
                            refs=(transition_id, location_id, output_live[location_id], output_id),
                        )
                    output_live[location_id] = output_id
                    if ledger_state is not None:
                        ownership[location_id] = ledger_state
            for location_id in transition["reserved_attachment_location_ids"]:
                if ownership.get(location_id) != "RESERVED":
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "ownership.reserve_delta_mismatch",
                        "Reserved delta must equal locations on reserved outputs",
                        refs=(transition_id, location_id),
                    )
        terminal_invalid = [
            frontier_id
            for frontier_id in current
            if frontiers[frontier_id]["lifecycle_state"] in {"ACTIVE", "RESERVED"}
        ]
        for frontier_id in sorted(terminal_invalid):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "frontier.unintended_terminal_boundary",
                "Every terminal obligation must be closed or explicitly declared open",
                refs=(frontier_id,),
            )
        if produced_frontiers != set(frontiers):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "frontier.creation_membership",
                "Every frontier table entry must be produced by exactly one replayed transition",
                expected=sorted(frontiers),
                observed=sorted(produced_frontiers),
            )
        if set(ownership) != set(locations):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "ownership.incomplete",
                "Every attachment location must enter the ownership ledger exactly once",
                expected=sorted(locations),
                observed=sorted(ownership),
            )
        terminal_states = {"RETIRED", "DECLARED_OPEN"}
        for location_id, state in ownership.items():
            if state not in terminal_states:
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "ownership.unresolved",
                    "Every location must be retired or retained on a declared opening "
                    "at completion",
                    refs=(location_id,),
                    observed=state,
                )

    def _validate_advance(
        self,
        stitch: dict[str, Any],
        transition: dict[str, Any],
        frontiers: dict[str, dict[str, Any]],
        locations: dict[str, dict[str, Any]],
        collector: _Collector,
    ) -> None:
        stitch_id = stitch["stitch_id"]
        bases = stitch["base_attachment_location_ids"]
        tops = stitch["top_attachment_location_ids"]
        if stitch["base_arity"] != len(bases) or stitch["top_arity"] != len(tops):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "stitch.arity_mismatch",
                "Declared arities must equal authoritative attachment lists",
                refs=(stitch_id,),
            )
        supported = (
            (
                stitch["stitch_type"] == "CHAIN"
                and stitch["shaping"] == "PLAIN"
                and (len(bases), len(tops)) == (0, 1)
            )
            or (
                stitch["stitch_type"] != "CHAIN"
                and stitch["shaping"] == "PLAIN"
                and (len(bases), len(tops)) == (1, 1)
            )
            or (
                stitch["stitch_type"] == "SINGLE_CROCHET"
                and stitch["shaping"] == "INCREASE"
                and (len(bases), len(tops)) == (1, 2)
            )
            or (
                stitch["stitch_type"] == "SINGLE_CROCHET"
                and stitch["shaping"] == "DECREASE"
                and (len(bases), len(tops)) == (2, 1)
            )
        )
        if not supported:
            collector.add(
                FailureCode.UNSUPPORTED_FEATURE,
                "V3",
                "stitch.unsupported_form",
                "Stitch family, shaping, and arity tuple is outside CROCHET_CORE_1.0.0",
                refs=(stitch_id,),
                observed=(stitch["stitch_type"], stitch["shaping"], len(bases), len(tops)),
            )
        if (
            transition["input_frontier_ids"] != [stitch["frontier_edit"]["frontier_id"]]
            or len(transition["output_frontier_ids"]) != 1
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "advance.edit_frontier_mismatch",
                "ADVANCE input must equal the stitch's explicit frontier edit target",
                refs=(stitch_id, transition["frontier_transition_id"]),
            )
            return
        if (
            transition["retired_attachment_location_ids"] != bases
            or transition["created_attachment_location_ids"] != tops
            or transition["reserved_attachment_location_ids"]
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "advance.delta_mismatch",
                "ADVANCE retired/created deltas must equal stitch bases/tops",
                refs=(stitch_id, transition["frontier_transition_id"]),
            )
        for ordinal, location_id in enumerate(tops):
            location = locations.get(location_id)
            expected_ref = {"entity_type": "STITCH", "stitch_id": stitch_id}
            if location is not None and (
                location["producer_ref"] != expected_ref
                or location["ordinal_within_producer"] != ordinal
            ):
                collector.add(
                    FailureCode.REFERENCE,
                    "V3",
                    "stitch.top_producer_mismatch",
                    "Top locations must identify their stitch producer and ordinal",
                    refs=(stitch_id, location_id),
                )
        input_frontier = frontiers[transition["input_frontier_ids"][0]]
        output_frontier = frontiers[transition["output_frontier_ids"][0]]
        if (
            input_frontier["lifecycle_state"] != "ACTIVE"
            or output_frontier["lifecycle_state"] != "ACTIVE"
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "advance.lifecycle",
                "ADVANCE consumes and produces ACTIVE frontiers",
                refs=(stitch_id,),
            )
        if (
            input_frontier["topology"] != output_frontier["topology"]
            or input_frontier["component_id"] != output_frontier["component_id"]
            or input_frontier["branch_id"] != output_frontier["branch_id"]
        ):
            collector.add(
                FailureCode.TOPOLOGY,
                "V4",
                "advance.identity_drift",
                "ADVANCE cannot implicitly change topology, component, or branch",
                refs=(stitch_id,),
            )
        expected = self._apply_frontier_edit(stitch, input_frontier, output_frontier, collector)
        if expected is not None and expected != output_frontier["attachment_location_ids"]:
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "advance.output_sequence",
                "Output frontier must be the exact explicit edit result",
                refs=(stitch_id, output_frontier["frontier_id"]),
                expected=expected,
                observed=output_frontier["attachment_location_ids"],
            )

    def _apply_frontier_edit(
        self,
        stitch: dict[str, Any],
        input_frontier: dict[str, Any],
        output_frontier: dict[str, Any],
        collector: _Collector,
    ) -> list[str] | None:
        values = input_frontier["attachment_location_ids"]
        bases = stitch["base_attachment_location_ids"]
        tops = stitch["top_attachment_location_ids"]
        edit = stitch["frontier_edit"]
        cyclic = input_frontier["topology"] == "CYCLIC"
        candidate: list[str] | None = None
        if edit["edit_type"] == "REPLACE_SPAN":
            if not bases:
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "edit.empty_replace_span",
                    "REPLACE_SPAN requires a non-empty base span",
                    refs=(stitch["stitch_id"],),
                )
                return None
            if cyclic:
                if (
                    not values
                    or bases[0] not in values
                    or any(
                        values[(values.index(bases[0]) + offset) % len(values)] != location_id
                        for offset, location_id in enumerate(bases)
                    )
                    or len(bases) > len(values)
                ):
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "edit.noncontiguous_cyclic_span",
                        "Cyclic REPLACE_SPAN bases must be consecutive in canonical orientation",
                        refs=(stitch["stitch_id"],),
                    )
                    return None
                start = values.index(bases[0])
                remaining = [
                    values[(start + len(bases) + offset) % len(values)]
                    for offset in range(len(values) - len(bases))
                ]
                candidate = tops + remaining
            else:
                matches = [
                    index
                    for index in range(len(values) - len(bases) + 1)
                    if values[index : index + len(bases)] == bases
                ]
                if len(matches) != 1:
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "edit.noncontiguous_linear_span",
                        "Linear REPLACE_SPAN bases must identify one consecutive span",
                        refs=(stitch["stitch_id"],),
                    )
                    return None
                start = matches[0]
                candidate = values[:start] + tops + values[start + len(bases) :]
        else:
            if bases:
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "edit.insert_has_bases",
                    "INSERT_AT_GAP requires an empty base list",
                    refs=(stitch["stitch_id"],),
                )
                return None
            left, right = edit["left_location_id"], edit["right_location_id"]
            if cyclic:
                if (
                    left is None
                    or right is None
                    or left not in values
                    or right not in values
                    or not values
                    or values[(values.index(left) + 1) % len(values)] != right
                ):
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "edit.illegal_cyclic_gap",
                        "Cyclic insertion requires an explicit oriented adjacent neighbor pair",
                        refs=(stitch["stitch_id"],),
                        observed=(left, right),
                    )
                    return None
                index = values.index(left)
                candidate = values[: index + 1] + tops + values[index + 1 :]
            else:
                if not values:
                    legal = left is None and right is None
                    candidate = tops if legal else None
                elif left is None and right == values[0]:
                    candidate = tops + values
                elif left == values[-1] and right is None:
                    candidate = values + tops
                elif (
                    left in values
                    and right in values
                    and values.index(right) == values.index(left) + 1
                ):
                    index = values.index(left)
                    candidate = values[: index + 1] + tops + values[index + 1 :]
                else:
                    candidate = None
                if candidate is None:
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "edit.illegal_linear_gap",
                        "Linear insertion anchor must identify the exact beginning, end, "
                        "internal, or empty gap",
                        refs=(stitch["stitch_id"],),
                        observed=(left, right),
                    )
                    return None
        if cyclic:
            candidate = _rotate_to(candidate, output_frontier["anchor_attachment_location_id"])
        return candidate

    def _validate_operation_transition(
        self,
        operation: dict[str, Any],
        transition: dict[str, Any],
        frontiers: dict[str, dict[str, Any]],
        collector: _Collector,
        design_spec: dict[str, Any] | None,
        tables: dict[str, dict[str, dict[str, Any]]],
        semantics_profile: str,
    ) -> None:
        operation_id = operation["operation_id"]
        if (
            transition["input_frontier_ids"] != operation["input_frontier_ids"]
            or transition["output_frontier_ids"] != operation["output_frontier_ids"]
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "operation.transition_frontiers",
                "Operation and paired transition frontier lists must agree exactly",
                refs=(operation_id, transition["frontier_transition_id"]),
            )
        transition_type = transition["transition_type"]
        expected_type = {
            "MAGIC_RING": "CREATE",
            "SPLIT": "SPLIT",
            "RESERVE": "RESERVE",
            "JOIN": "JOIN",
            "CLOSE": "CLOSE",
            "DECLARE_OPENING": "DECLARE_OPENING",
            "ATTACH": "CREATE" if not operation["input_frontier_ids"] else "REATTACH",
        }.get(operation["operation_type"])
        if expected_type is not None and transition_type != expected_type:
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "operation.transition_type",
                "Construction operation must use its defined frontier transition class",
                refs=(operation_id,),
                expected=expected_type,
                observed=transition_type,
            )
            return
        if operation["operation_type"] in {"COLOR_CHANGE", "CUT_YARN"}:
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "operation.spurious_transition",
                "Yarn-only operation must not cause a frontier transition",
                refs=(operation_id,),
            )
            return
        inputs = [frontiers[key] for key in transition["input_frontier_ids"]]
        outputs = [frontiers[key] for key in transition["output_frontier_ids"]]
        retired = transition["retired_attachment_location_ids"]
        created = transition["created_attachment_location_ids"]
        reserved = transition["reserved_attachment_location_ids"]
        if transition_type == "CREATE":
            if (
                inputs
                or len(outputs) != 1
                or outputs[0]["lifecycle_state"] != "ACTIVE"
                or retired
                or reserved
                or created != operation["attachment_location_ids"]
                or outputs[0]["attachment_location_ids"] != created
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "create.contract",
                    "CREATE must introduce exactly its operation-produced active frontier",
                    refs=(operation_id,),
                )
            if operation["operation_type"] == "MAGIC_RING" and (
                outputs[0]["topology"] != "CYCLIC"
                or (semantics_profile == "CROCHET_CORE_1.0.0"
                    and len(outputs[0]["attachment_location_ids"]) != 1)
            ):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "magic_ring.frontier_shape",
                    "MAGIC_RING must create one anchored cyclic frontier",
                    refs=(operation_id, outputs[0]["frontier_id"]),
                )
        elif transition_type in {"SPLIT", "RESERVE"}:
            if len(inputs) != 1 or len(outputs) < 2 or retired or created:
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "partition.cardinality",
                    "SPLIT/RESERVE is a delta-free one-to-many partition",
                    refs=(operation_id,),
                )
                return
            if inputs[0]["lifecycle_state"] != "ACTIVE":
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "partition.input_lifecycle",
                    "SPLIT and RESERVE consume an ACTIVE frontier",
                    refs=(operation_id, inputs[0]["frontier_id"]),
                    observed=inputs[0]["lifecycle_state"],
                )
            source = inputs[0]["attachment_location_ids"]
            flattened = [
                location for output in outputs for location in output["attachment_location_ids"]
            ]
            if Counter(flattened) != Counter(source) or any(
                not _is_subsequence(output["attachment_location_ids"], source) for output in outputs
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "partition.not_exact",
                    "Partition outputs must be disjoint ordered subsequences whose union "
                    "is the input",
                    refs=(operation_id,),
                )
            states = [output["lifecycle_state"] for output in outputs]
            if transition_type == "SPLIT" and any(state != "ACTIVE" for state in states):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "split.lifecycle",
                    "Every SPLIT output is ACTIVE",
                    refs=(operation_id,),
                )
            if transition_type == "SPLIT":
                parent_branch_id = inputs[0]["branch_id"]
                child_branch_ids = [output["branch_id"] for output in outputs]
                if (
                    len(child_branch_ids) != len(set(child_branch_ids))
                    or parent_branch_id in child_branch_ids
                ):
                    collector.add(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "split.branch_identity",
                        "SPLIT outputs must introduce distinct child branches",
                        refs=(operation_id,),
                    )
                for child_branch_id in child_branch_ids:
                    branch = tables["branches"].get(child_branch_id)
                    if branch is not None and (
                        branch["created_by_transition_id"] != transition["frontier_transition_id"]
                        or parent_branch_id not in branch["parent_branch_ids"]
                    ):
                        collector.add(
                            FailureCode.TOPOLOGY,
                            "V4",
                            "split.branch_lineage",
                            "Each split child branch must name the split transition and parent",
                            refs=(operation_id, child_branch_id),
                        )
            if transition_type == "RESERVE":
                expected_reserved = [
                    location
                    for output in outputs
                    if output["lifecycle_state"] == "RESERVED"
                    for location in output["attachment_location_ids"]
                ]
                if (
                    states.count("ACTIVE") != 1
                    or states.count("RESERVED") < 1
                    or reserved != expected_reserved
                ):
                    collector.add(
                        FailureCode.FRONTIER,
                        "V4",
                        "reserve.lifecycle_or_delta",
                        "RESERVE has one ACTIVE output and one or more RESERVED outputs "
                        "with exact delta",
                        refs=(operation_id,),
                    )
        elif transition_type == "REATTACH":
            if (
                len(inputs) != 1
                or len(outputs) != 1
                or inputs[0]["lifecycle_state"] != "RESERVED"
                or outputs[0]["lifecycle_state"] != "ACTIVE"
                or inputs[0]["attachment_location_ids"] != outputs[0]["attachment_location_ids"]
                or retired
                or created
                or reserved
                or operation["attachment_location_ids"][0]
                not in inputs[0]["attachment_location_ids"]
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "reattach.contract",
                    "REATTACH preserves the exact reserved sequence and changes only "
                    "lifecycle/yarn ownership at an explicit member attachment",
                    refs=(operation_id,),
                )
        elif transition_type == "JOIN":
            if any(
                frontier["lifecycle_state"] not in {"ACTIVE", "RESERVED"} for frontier in inputs
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "join.input_lifecycle",
                    "JOIN consumes only ACTIVE or RESERVED frontier obligations",
                    refs=(operation_id,),
                )
            self._validate_join(operation, transition, inputs, outputs, collector)
            output_branch = tables["branches"].get(outputs[0]["branch_id"])
            expected_parents = {frontier["branch_id"] for frontier in inputs}
            if output_branch is not None and (
                output_branch["created_by_transition_id"] != transition["frontier_transition_id"]
                or set(output_branch["parent_branch_ids"]) != expected_parents
            ):
                collector.add(
                    FailureCode.TOPOLOGY,
                    "V4",
                    "join.branch_lineage",
                    "JOIN output branch must name the join transition and all input branches",
                    refs=(operation_id, output_branch["branch_id"]),
                    expected=sorted(expected_parents),
                    observed=sorted(output_branch["parent_branch_ids"]),
                )
        elif transition_type == "CLOSE":
            if (
                len(inputs) != 1
                or len(outputs) != 1
                or inputs[0]["lifecycle_state"] not in {"ACTIVE", "RESERVED"}
                or outputs[0]["lifecycle_state"] != "CLOSED"
                or outputs[0]["attachment_location_ids"]
                or retired != inputs[0]["attachment_location_ids"]
                or created
                or reserved
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "close.contract",
                    "CLOSE retires the complete input boundary and emits an empty CLOSED frontier",
                    refs=(operation_id,),
                )
        elif transition_type == "DECLARE_OPENING":
            if (
                len(inputs) != 1
                or len(outputs) != 1
                or inputs[0]["lifecycle_state"] not in {"ACTIVE", "RESERVED"}
                or outputs[0]["lifecycle_state"] != "DECLARED_OPEN"
                or outputs[0]["attachment_location_ids"] != inputs[0]["attachment_location_ids"]
                or retired
                or created
                or reserved
                or operation["opening_id"] != transition["opening_id"]
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "opening.contract",
                    "DECLARE_OPENING retains exactly the input boundary under one opening identity",
                    refs=(operation_id,),
                )
            opening = tables["openings"].get(operation["opening_id"])
            if opening is not None and (
                opening["declared_by_operation_id"] != operation_id
                or opening["design_requirement_id"] != operation["design_requirement_id"]
                or opening["boundary_attachment_location_ids"]
                != outputs[0]["attachment_location_ids"]
            ):
                collector.add(
                    FailureCode.REFERENCE,
                    "V4",
                    "opening.cross_link",
                    "Operation, transition, frontier, and opening record must cross-link exactly",
                    refs=(operation_id, opening["opening_id"]),
                )

    @staticmethod
    def _validate_join(
        operation: dict[str, Any],
        transition: dict[str, Any],
        inputs: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        collector: _Collector,
    ) -> None:
        mappings = operation["join_input_mappings"]
        if (
            len(inputs) < 2
            or len(outputs) != 1
            or [item["input_frontier_id"] for item in mappings] != operation["input_frontier_ids"]
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "join.mapping_order",
                "JOIN mappings must cover distinct inputs in declared input order",
                refs=(operation["operation_id"],),
            )
            return
        expected: list[str] = []
        consumed: list[str] = []
        for frontier, mapping in zip(inputs, mappings, strict=True):
            oriented = list(frontier["attachment_location_ids"])
            if mapping["orientation"] == "REVERSED":
                oriented.reverse()
            mapped = mapping["consumed_attachment_location_ids"]
            if len(mapped) != len(set(mapped)) or any(
                location not in oriented for location in mapped
            ):
                collector.add(
                    FailureCode.FRONTIER,
                    "V4",
                    "join.invalid_consumed_site",
                    "JOIN consumed sites must be unique members of their mapped input",
                    refs=(operation["operation_id"],),
                )
            consumed.extend(mapped)
            expected.extend(location for location in oriented if location not in set(mapped))
        output = outputs[0]
        expected_state = "CLOSED" if not expected else "ACTIVE"
        if (
            operation["attachment_location_ids"] != consumed
            or transition["retired_attachment_location_ids"] != consumed
            or transition["created_attachment_location_ids"]
            or transition["reserved_attachment_location_ids"]
            or output["attachment_location_ids"] != expected
            or output["lifecycle_state"] != expected_state
        ):
            collector.add(
                FailureCode.FRONTIER,
                "V4",
                "join.contract",
                "JOIN must retire exactly mapped sites and concatenate oriented unconsumed "
                "remainders",
                refs=(operation["operation_id"],),
                expected=(consumed, expected, expected_state),
                observed=(
                    transition["retired_attachment_location_ids"],
                    output["attachment_location_ids"],
                    output["lifecycle_state"],
                ),
            )

    def _validate_yarn_paths(
        self,
        value: dict[str, Any],
        tables: dict[str, dict[str, dict[str, Any]]],
        collector: _Collector,
    ) -> None:
        path_yarns = [path["yarn_id"] for path in value["yarn_paths"]]
        if len(path_yarns) != len(set(path_yarns)) or set(path_yarns) != set(tables["yarns"]):
            collector.add(
                FailureCode.COUNT,
                "V3",
                "yarn_path.membership",
                "Each yarn source must have exactly one yarn path",
                pointers=("/yarn_paths",),
            )
        events = sorted(value["construction_sequence"], key=lambda item: item["sequence_index"])
        event_indexes = {event["event_id"]: event["sequence_index"] for event in events}
        operation_events = {
            event["subject_ref"]["operation_id"]: event
            for event in events
            if event["subject_ref"]["entity_type"] == "CONSTRUCTION_OPERATION"
        }
        expected_work: dict[str, set[str]] = {yarn_id: set() for yarn_id in tables["yarns"]}
        boundary_operations = {"ATTACH", "MAGIC_RING", "COLOR_CHANGE", "CUT_YARN"}
        for event in events:
            subject = event["subject_ref"]
            if subject["entity_type"] == "STITCH":
                stitch = tables["stitches"].get(subject["stitch_id"])
                if stitch is not None and stitch["yarn_id"] in expected_work:
                    expected_work[stitch["yarn_id"]].add(event["event_id"])
            else:
                operation = tables["construction_operations"].get(subject["operation_id"])
                yarn_id = event["active_yarn_id_before"]
                if (
                    operation is not None
                    and operation["operation_type"] not in boundary_operations
                    and yarn_id is not None
                    and event["active_yarn_id_after"] == yarn_id
                    and yarn_id in expected_work
                ):
                    expected_work[yarn_id].add(event["event_id"])
        seen_segments: set[str] = set()
        observed_work: dict[str, Counter[str]] = {yarn_id: Counter() for yarn_id in tables["yarns"]}
        for path in value["yarn_paths"]:
            previous_boundary = -1
            for segment_index, segment in enumerate(path["segments"]):
                segment_id = segment["yarn_segment_id"]
                if segment_id in seen_segments:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "yarn_segment.duplicate_id",
                        "Yarn segment IDs must be globally unique",
                        refs=(segment_id,),
                    )
                seen_segments.add(segment_id)
                start_operation = tables["construction_operations"].get(
                    segment["start_operation_id"]
                )
                start_event = operation_events.get(segment["start_operation_id"])
                if (
                    start_operation is None
                    or start_event is None
                    or start_operation["operation_type"] != segment["start_operation_type"]
                    or start_operation["operation_type"]
                    not in {"ATTACH", "MAGIC_RING", "COLOR_CHANGE"}
                    or path["yarn_id"] not in start_operation["output_yarn_ids"]
                ):
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "yarn_segment.invalid_start_boundary",
                        "Yarn segment start must resolve to a matching yarn-output boundary",
                        refs=(segment_id, segment["start_operation_id"]),
                    )
                    start_index = -1
                else:
                    start_index = start_event["sequence_index"]
                end_operation_id = segment["end_operation_id"]
                if end_operation_id is None:
                    end_index = len(events)
                    if segment_index != len(path["segments"]) - 1 or (
                        events and events[-1]["active_yarn_id_after"] != path["yarn_id"]
                    ):
                        collector.add(
                            FailureCode.REFERENCE,
                            "V3",
                            "yarn_segment.invalid_live_terminal",
                            "Only the final live segment may omit its end boundary",
                            refs=(segment_id,),
                        )
                else:
                    end_operation = tables["construction_operations"].get(end_operation_id)
                    end_event = operation_events.get(end_operation_id)
                    if (
                        end_operation is None
                        or end_event is None
                        or end_operation["operation_type"] != segment["end_operation_type"]
                        or end_operation["operation_type"] not in {"CUT_YARN", "COLOR_CHANGE"}
                        or path["yarn_id"] not in end_operation["input_yarn_ids"]
                    ):
                        collector.add(
                            FailureCode.REFERENCE,
                            "V3",
                            "yarn_segment.invalid_end_boundary",
                            "Yarn segment end must resolve to a matching yarn-input boundary",
                            refs=(segment_id, end_operation_id),
                        )
                        end_index = len(events)
                    else:
                        end_index = end_event["sequence_index"]
                missing_events = [
                    event_id for event_id in segment["event_ids"] if event_id not in event_indexes
                ]
                for event_id in missing_events:
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "yarn_segment.dangling_event",
                        "Yarn segment event IDs must resolve exactly",
                        refs=(segment_id, event_id),
                    )
                indexes = [
                    event_indexes[event_id]
                    for event_id in segment["event_ids"]
                    if event_id in event_indexes
                ]
                if (
                    indexes != sorted(indexes)
                    or any(index <= start_index or index >= end_index for index in indexes)
                    or start_index < previous_boundary
                    or end_index <= start_index
                ):
                    collector.add(
                        FailureCode.REFERENCE,
                        "V3",
                        "yarn_segment.event_order",
                        "Yarn segment events must be strictly inside ordered boundaries",
                        refs=(segment_id,),
                    )
                previous_boundary = end_index
                observed_work[path["yarn_id"]].update(segment["event_ids"])
        for yarn_id, expected in expected_work.items():
            observed = observed_work[yarn_id]
            if set(observed) != expected or any(count != 1 for count in observed.values()):
                collector.add(
                    FailureCode.COUNT,
                    "V3",
                    "yarn_path.work_membership",
                    "Every non-boundary yarn work event belongs to exactly one matching segment",
                    refs=(yarn_id,),
                    expected=sorted(expected),
                    observed=sorted(observed.items()),
                )
