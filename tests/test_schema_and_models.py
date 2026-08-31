from __future__ import annotations

import json
from pathlib import Path

import pytest

from crochet_ai import CrochetIR, DesignSpec, MaterialProfile
from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.schema import schema_documents, validate_schema

FIXTURES = Path(__file__).parent / "fixtures" / "schema-valid"


@pytest.mark.parametrize(
    ("kind", "filename"),
    [
        ("material_profile", "material-profile.minimal.valid.json"),
        ("design_spec", "design-spec.analytic-sphere.valid.json"),
        ("crochet_ir", "crochet-ir.magic-ring-single-course.valid.json"),
    ],
)
def test_published_schema_fixture_is_valid(kind: str, filename: str) -> None:
    value = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    assert validate_schema(kind, value).ok


def test_all_authoritative_schemas_compile() -> None:
    assert set(schema_documents()) == {"design_spec", "material_profile", "crochet_ir"}


def test_runtime_models_defensively_copy(
    material_profile: dict[str, object],
    design_spec: dict[str, object],
    closed_ir: dict[str, object],
) -> None:
    models = [
        MaterialProfile.from_dict(material_profile),
        DesignSpec.from_dict(design_spec),
        CrochetIR.from_dict(closed_ir),
    ]
    for model in models:
        first = model.to_dict()
        first["schema_version"] = "corrupted"
        assert model.to_dict()["schema_version"] == "1.0.0"


def test_model_rejects_schema_invalid_value(material_profile: dict[str, object]) -> None:
    del material_profile["profile_id"]
    with pytest.raises(ArtifactValidationError) as error:
        MaterialProfile.from_dict(material_profile)
    assert error.value.report.diagnostics[0].code == "E_SCHEMA"
