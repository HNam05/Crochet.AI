"""3D model upload: STL/OBJ slicing into a custom part profile."""

from __future__ import annotations

import struct
from math import cos, pi, sin

import pytest

from crochet_ai.figure import FigureError, solve_figure
from crochet_ai.figure_mesh import mesh_part, mesh_profile

GAUGE = {"stitches_per_100mm": 25, "rows_per_100mm": 28}
COLORS = [{"id": "main", "label": "Natur", "hex": "#D8C8A8"}]


def _sphere(radius: float = 1.0, center: tuple[float, float, float] = (0, 0, 0), n: int = 24):
    """Closed UV sphere as triangles (z up)."""
    def point(i: int, j: int) -> tuple[float, float, float]:
        theta, phi = pi * i / n, 2 * pi * j / n
        return (center[0] + radius * sin(theta) * cos(phi),
                center[1] + radius * sin(theta) * sin(phi),
                center[2] - radius * cos(theta))

    triangles = []
    for i in range(n):
        for j in range(n):
            a, b, c, d = point(i, j), point(i + 1, j), point(i + 1, j + 1), point(i, j + 1)
            if i > 0:
                triangles.append((a, b, d))
            if i < n - 1:
                triangles.append((b, c, d))
    return triangles


def _binary_stl(triangles) -> bytes:
    body = b"".join(
        struct.pack("<12fH", 0, 0, 0, *a, *b, *c, 0) for a, b, c in triangles
    )
    return b"\0" * 80 + struct.pack("<I", len(triangles)) + body


def _ascii_stl(triangles) -> bytes:
    lines = ["solid test"]
    for tri in triangles:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += [f"vertex {x} {y} {z}" for x, y, z in tri]
        lines += ["endloop", "endfacet"]
    return ("\n".join([*lines, "endsolid test"]) + "\n").encode()


def _obj(triangles, swap_yz: bool = False) -> bytes:
    lines = []
    for tri in triangles:
        for x, y, z in tri:
            lines.append(f"v {x} {z} {y}" if swap_yz else f"v {x} {y} {z}")
    for k in range(len(triangles)):
        lines.append(f"f {3 * k + 1} {3 * k + 2} {3 * k + 3}")
    return "\n".join(lines).encode()


def _figure(part: dict) -> dict:
    return {"name": "Modell", "gauge": GAUGE, "colors": COLORS, "parts": [part]}


def test_sphere_stl_matches_builtin_sphere_counts() -> None:
    upload = mesh_part(_binary_stl(_sphere()), "kugel.stl", height_mm=60)
    part = upload["part"]
    assert part["shape"] == "custom" and abs(part["width_mm"] - 60) < 2
    custom = solve_figure(_figure(part))["parts"][0]
    builtin = solve_figure(_figure({"id": "k", "label": "K", "shape": "sphere",
                                    "width_mm": 60, "height_mm": 60, "color": "main"}))
    counts = [r["count"] for r in custom["rows"]]
    reference = [r["count"] for r in builtin["parts"][0]["rows"]]
    assert counts[0] == 6 and max(counts) == pytest.approx(max(reference), abs=2)
    assert abs(len(counts) - len(reference)) <= 1


def test_ascii_stl_and_obj_give_the_same_profile() -> None:
    triangles = _sphere(n=16)
    binary = mesh_profile(_binary_stl(triangles), "a.stl")
    ascii_ = mesh_profile(_ascii_stl(triangles), "a.stl")
    obj = mesh_profile(_obj(triangles, swap_yz=True), "a.obj")  # OBJ default up is y
    assert binary["profile"] == ascii_["profile"]
    assert [round(r, 2) for _, r in obj["profile"]] == [round(r, 2) for _, r in binary["profile"]]


def test_axis_and_flip_change_orientation() -> None:
    # A cone: wide at the bottom (z=0), point at the top.
    n, triangles = 24, []
    for j in range(n):
        p0 = (cos(2 * pi * j / n), sin(2 * pi * j / n), 0.0)
        p1 = (cos(2 * pi * (j + 1) / n), sin(2 * pi * (j + 1) / n), 0.0)
        triangles += [((0.0, 0.0, 2.0), p0, p1), ((0.0, 0.0, 0.0), p1, p0)]
    upright = mesh_profile(_binary_stl(triangles), "kegel.stl")["profile"]
    flipped = mesh_profile(_binary_stl(triangles), "kegel.stl", flip=True)["profile"]
    assert upright[1][1] > upright[-2][1] and flipped[1][1] < flipped[-2][1]


def test_open_end_keeps_a_rim() -> None:
    part = mesh_part(_binary_stl(_sphere()), "k.stl", height_mm=60, end="open")["part"]
    assert part["profile"][-1][0] == 1.0 and part["profile"][-1][1] > 0
    assert solve_figure(_figure(part))["parts"][0]["end"] == "open"


def test_gap_between_pieces_fails_closed() -> None:
    triangles = _sphere(center=(0, 0, 0)) + _sphere(center=(0, 0, 3))
    with pytest.raises(FigureError) as error:
        mesh_profile(_binary_stl(triangles), "zwei.stl")
    assert error.value.code == "mesh.gap"


def test_branching_model_fails_closed() -> None:
    # Two side-by-side tall legs: branched over the whole height.
    legs = _sphere(radius=1, center=(-1.5, 0, 0)) + _sphere(radius=1, center=(1.5, 0, 0))
    with pytest.raises(FigureError) as error:
        mesh_profile(_binary_stl(legs), "beine.stl")
    assert error.value.code == "mesh.branches"


@pytest.mark.parametrize(
    ("data", "name", "code"),
    [
        (b"", "x.stl", "mesh.empty"),
        (b"hello", "x.txt", "mesh.format"),
        (b"solid nothing\nendsolid\n", "x.stl", "mesh.format"),
        (b"v 0 0 0\nf 1 2 3\n", "x.obj", "mesh.format"),
    ],
)
def test_bad_files_fail_closed(data: bytes, name: str, code: str) -> None:
    with pytest.raises(FigureError) as error:
        mesh_profile(data, name)
    assert error.value.code == code


OPTIONS = {"filename": "kugel.stl", "up": "auto", "flip": False, "end": "closed",
           "height_mm": 60, "color": "main", "label": "Kugel"}


def test_upload_route_on_the_local_server(tmp_path) -> None:
    import json
    import subprocess
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.parse import quote
    from urllib.request import Request, urlopen

    from crochet_ai.prototype_server import make_server

    commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                            text=True).stdout.strip()
    server = make_server(0, tmp_path, commit)
    Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/bootstrap") as response:
            token = json.load(response)["data"]["csrf_token"]

        def post(data: bytes, options: object, content_type: str = "application/octet-stream"):
            return Request(base + "/api/figure/mesh", data=data, method="POST", headers={
                "Origin": base, "X-CSRF-Token": token, "Content-Type": content_type,
                "X-Mesh-Options": quote(json.dumps(options))})

        with urlopen(post(_binary_stl(_sphere()), OPTIONS)) as response:
            reply = json.load(response)
        assert reply["ok"] and reply["data"]["part"]["shape"] == "custom"
        with pytest.raises(HTTPError) as error:
            urlopen(post(b"", dict(OPTIONS, filename="leer.stl")))
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(post(_binary_stl(_sphere()), OPTIONS, "application/json"))
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(post(_binary_stl(_sphere()), {"filename": "x.stl"}))
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_upload_through_the_browser_bridge() -> None:
    import json
    import runpy
    from pathlib import Path

    bridge = runpy.run_path(str(Path(__file__).resolve().parents[1] / "web" / "bridge.py"))
    reply = json.loads(bridge["mesh"](memoryview(_binary_stl(_sphere())), json.dumps(OPTIONS)))
    assert reply["ok"] and reply["data"]["part"]["profile"][0] == [0.0, 0.0]
    bad = json.loads(bridge["mesh"](memoryview(b"xyz"), json.dumps(OPTIONS)))
    assert not bad["ok"] and bad["error"]["reason"].startswith("mesh.")


def test_profile_field_is_strict() -> None:
    part = mesh_part(_binary_stl(_sphere()), "k.stl", height_mm=60)["part"]
    broken = dict(part, profile=[[0, 0], [0.5, 0.5], [1, 0]])
    with pytest.raises(FigureError) as error:
        solve_figure(_figure(broken))
    assert "Radius 1" in error.value.message_de
    with pytest.raises(FigureError):
        solve_figure(_figure(dict(part, shape="sphere")))
