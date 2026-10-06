"""Versioned implementation inventory, separate from artifact verification."""

from __future__ import annotations

CAPABILITY_MATRIX_VERSION = "BACKEND_CAPABILITY_MATRIX_V1"


def backend_capability_matrix() -> dict[str, object]:
    """Return a fresh inventory; IMPLEMENTED never means physically accepted."""
    rows = (
        (
            "B0",
            "IMPLEMENTED_SUBSET",
            "Canonical core 1.0/1.1 and exact semantic validation",
            "Release conformance must be rerun",
        ),
        (
            "B1",
            "IMPLEMENTED_SUBSET",
            "M1A DE/US/UK text and prototype PDF",
            "M1B and complete V9/V10 acceptance",
        ),
        (
            "B2",
            "IMPLEMENTED_SUBSET",
            "Mesh V0, sphere/ellipsoid targets, cardinal closed coordinate admission",
            "Other coordinate scopes, coordinate generation/V7, flat and lace adapters",
        ),
        (
            "B3",
            "IMPLEMENTED_SUBSET",
            "Closed-pole SC proposals, bounded traces, independent final-relation audit",
            "Full independent V5 and full domain acceptance",
        ),
        (
            "B4",
            "EXPERIMENTAL",
            "Target-free stretch/shear/bending prototype and topology-only shaped closed cells",
            "Physical shaping/rest model, contact response, convergence and calibration",
        ),
        (
            "B5",
            "IMPLEMENTED_SUBSET",
            "V0-V10 orchestration, closed SC topology, sphere replay and scoped final relation",
            "Broader V4/target scopes, physical selection and V6-V10",
        ),
        (
            "B6",
            "IMPLEMENTED_SUBSET",
            "Versioned local API and offline CLI",
            "Whole-chain release contract",
        ),
        (
            "B7",
            "IMPLEMENTED_SUBSET",
            "Durable bounded SQLite jobs",
            "Whole-chain recovery and operational acceptance",
        ),
        (
            "B8",
            "IMPLEMENTED_SUBSET",
            "Request limits, process isolation and wheel packaging",
            "Complete operational and security acceptance",
        ),
        (
            "B9",
            "MISSING",
            "No accepted free-mesh/geodesic/branch solver",
            "P14-P16 implementation and independent acceptance",
        ),
        (
            "B10",
            "MISSING",
            "No accepted flat/garment/lace solver",
            "P17-P19 implementation and independent acceptance",
        ),
        (
            "B11",
            "IMPLEMENTED_SUBSET",
            "Frozen calibration campaigns and draft gauge derivation",
            "Real specimens, uncertainty extensions, review and frozen holdouts",
        ),
        (
            "B12",
            "NOT_READY",
            "No backend release claim",
            "Every promised package and physical gate must be accepted",
        ),
    )
    return {
        "matrix_version": CAPABILITY_MATRIX_VERSION,
        "backend_release_ready": False,
        "release_levels": {
            "R0": "LOCAL_PILOT",
            "R1": "NOT_ACCEPTED",
            "R2": "NOT_ACCEPTED",
            "R3": "NOT_ACCEPTED",
            "R4": "NOT_ACCEPTED",
        },
        "packages": [
            {
                "package_id": package,
                "implementation_state": state,
                "implemented_scope": scope,
                "remaining_acceptance": remaining,
            }
            for package, state, scope, remaining in rows
        ],
    }
