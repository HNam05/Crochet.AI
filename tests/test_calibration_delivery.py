from __future__ import annotations

import http.client
import json
from io import BytesIO
from pathlib import Path
from threading import Thread

import pytest
from pypdf import PdfReader
from test_calibration_campaign import bound_campaign, measured_set

from crochet_ai.calibration_pdf import render_calibration_packet
from crochet_ai.cli import main
from crochet_ai.prototype_server import make_server


def test_packet_is_deterministic_four_pages_with_three_separate_specimens() -> None:
    data = render_calibration_packet()
    assert data.startswith(b"%PDF-")
    assert render_calibration_packet() == data
    reader = PdfReader(BytesIO(data))
    assert len(reader.pages) == 4
    pages = [page.extract_text() or "" for page in reader.pages]
    assert "keine physische Freigabe" in pages[0]
    assert "keine verdoppelte" in " ".join(pages[0].lower().split())
    assert "noch nicht implementiert" in pages[0]
    for index in range(1, 4):
        assert f"Messblatt: Probe {index}" in pages[index]
        assert "Anzahl Abstände" in pages[index]
        assert "Umfang in mm" in pages[index]


def test_campaign_bound_packet_contains_exact_hash_and_frozen_measurement_plan() -> None:
    context = bound_campaign()
    reader = PdfReader(BytesIO(render_calibration_packet(context)))
    pages = [page.extract_text() or "" for page in reader.pages]
    assert len(pages) == 4
    assert context.sha256 in pages[0]
    assert "12 Maschen je Runde" in pages[1]
    assert "4 Abstände" in pages[1]
    assert all(f"Messblatt: s{index}" in pages[index] for index in range(1, 4))
    assert "Messblatt: holdout" not in " ".join(pages)


def test_cli_roundtrip_append_only_store_and_review_required_draft(tmp_path: Path, capsys) -> None:
    context = bound_campaign()
    campaign_file = tmp_path / "campaign.json"
    campaign_file.write_text(json.dumps(context.to_dict()), encoding="utf-8")
    db = tmp_path / "records.sqlite3"
    assert (
        main(
            [
                "--json",
                "calibration",
                "register",
                "--db",
                str(db),
                "--record-file",
                str(campaign_file),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["data"]["campaign_sha256"] == context.sha256
    for index, record in enumerate(measured_set(context)):
        record_file = tmp_path / f"measurement-{index}.json"
        record_file.write_text(json.dumps(record.to_dict()), encoding="utf-8")
        assert (
            main(
                [
                    "--json",
                    "calibration",
                    "record",
                    "--db",
                    str(db),
                    "--campaign-sha256",
                    context.sha256,
                    "--record-file",
                    str(record_file),
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["data"]["measurement_sha256"] == record.sha256
    assert (
        main(
            [
                "--json",
                "calibration",
                "derive",
                "--db",
                str(db),
                "--campaign-sha256",
                context.sha256,
                "--profile-id",
                "mp_pilot",
                "--response-id",
                "mr_pilot",
                "--created-at",
                "2026-10-05T12:00:00Z",
            ]
        )
        == 0
    )
    derived = json.loads(capsys.readouterr().out)["data"]
    assert (
        derived["material_profile"]["calibration_responses"][0]["effective_gauge"][
            "effective_stitch_pitch_mm"
        ]
        == 4
    )
    assert derived["physical_status"] == "UNTESTED"
    assert derived["calibration_review"] == "REQUIRED"
    assert (
        main(
            ["--json", "calibration", "show", "--db", str(db), "--campaign-sha256", context.sha256]
        )
        == 0
    )
    assert len(json.loads(capsys.readouterr().out)["data"]["measurements"]) == 3


def test_cli_read_does_not_create_database_and_packet_cannot_overwrite(
    tmp_path: Path, capsys
) -> None:
    db = tmp_path / "missing.sqlite3"
    assert (
        main(["--json", "calibration", "show", "--db", str(db), "--campaign-sha256", "a" * 64]) == 2
    )
    assert not db.exists()
    assert json.loads(capsys.readouterr().out)["error"]["reason"] == "calibration.store_not_found"
    pdf = tmp_path / "packet.pdf"
    pdf.write_bytes(b"existing user data")
    assert main(["--json", "calibration", "packet", "--output", str(pdf)]) == 2
    assert pdf.read_bytes() == b"existing user data"
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "E_STORAGE"


@pytest.fixture
def local_server(tmp_path: Path):
    server = make_server(0, tmp_path, "test-checkpoint")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        server.prototype_store.close()


def test_loopback_serves_new_capabilities_and_actual_pdf_bytes(local_server) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", local_server.server_address[1], timeout=10)
    try:
        connection.request("GET", "/api/capabilities")
        response = connection.getresponse()
        assert response.status == 200
        assert (
            json.loads(response.read())["data"]["capability_matrix"]["backend_release_ready"]
            is False
        )
        connection.request("GET", "/api/calibration-protocol.pdf")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/pdf"
        assert response.getheader("Content-Disposition").endswith(
            '"crochet-calibration-measurements.pdf"'
        )
        assert len(PdfReader(BytesIO(response.read())).pages) == 4
    finally:
        connection.close()
