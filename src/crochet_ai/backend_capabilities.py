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
            "Other coordinate scopes, coordinate V7, flat and lace adapters",
        ),
        (
            "B3",
            "IMPLEMENTED_SUBSET",
            "Closed-pole SC proposals; independent sphere/coordinate search and final relation",
            "Full independent V5, numerical-failure replay and full domain acceptance",
        ),
        (
            "B4",
            "EXPERIMENTAL",
            "Closed SC hypothesis mechanics, loading, shell/contact and bounded multistart F0",
            "Identified material/closure laws, physical holdouts and production convergence",
        ),
        (
            "B5",
            "IMPLEMENTED_SUBSET",
            "V0-V10 checkpoint with optional fresh F0 audit, sampled metrics and five scenarios",
            "Broader domains, ideal geometry certification, calibrated selection "
            "and source authentication",
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
            "EXPERIMENTAL",
            "Triangular OBJ, closed graph-distance SC draft and explicit reserve compiler",
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
            "Frozen campaigns, gauge endpoints and append-only reviewed-claim registry",
            "Real specimens, authenticated review, identified uncertainty and frozen holdouts",
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
