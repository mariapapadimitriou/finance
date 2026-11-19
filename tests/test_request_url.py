"""TEST-33: ids are percent-encoded once, by RequestURL.swift (what APIClient
sends), never by the screens as well. A trip ask's id has ":" in it, and a
bill's key can have spaces and "&"; encoded twice the server got "%253A" and
answered 404, so Skip and Yes on a trip did nothing."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from test_trips import away, client, home  # noqa: F401  (client is a fixture)

ROOT = Path(__file__).resolve().parent.parent
PEARL = ROOT / "ios/Pearl"
SOURCE = PEARL / "API/RequestURL.swift"
CHECK = ROOT / "tests/swift/request_url_check.swift"

needs_swiftc = pytest.mark.skipif(shutil.which("swiftc") is None, reason="needs swiftc")


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    folder = tmp_path_factory.mktemp("request_url")
    main = folder / "main.swift"
    main.write_text(CHECK.read_text())
    out = folder / "request_url"
    subprocess.run(["swiftc", "-o", str(out), str(SOURCE), str(main)], check=True,
                   capture_output=True, timeout=300)

    def urls(*paths: str) -> list[str]:
        run = subprocess.run([str(out), *paths], capture_output=True, text=True, timeout=60, check=True)
        return run.stdout.splitlines()
    return urls


@needs_swiftc
def test_each_id_is_encoded_once(build):
    paths = ["api/trips/asks/2026-10-28:2026-10-30/skip",
             "api/income-bills/bills/PG&E Electric",
             "api/rules/dining: 100% thai"]
    for path, url in zip(paths, build(*paths)):
        sent = urlsplit(url).path
        if "%" not in path:
            assert "%25" not in sent, url               # no "%" encoded a second time
        assert unquote(sent) == "/" + path, url        # the server reads back what she sent
    assert build("api/trips/asks/2026-10-28:2026-10-30/skip")[0].endswith("/2026-10-28:2026-10-30/skip")


@needs_swiftc
def test_trip_yes_and_skip_reach_the_server(build, client):  # noqa: F811
    home(client)
    away(client)
    [ask] = client.get("/api/trips/asks").get_json()["asks"]
    assert ":" in ask["id"]
    [url] = build(f"api/trips/asks/{ask['id']}/skip")
    assert client.post(urlsplit(url).path).status_code == 200
    assert client.get("/api/trips/asks").get_json()["asks"] == []


@needs_swiftc
def test_trip_yes_reaches_the_server(build, client):  # noqa: F811
    home(client)
    away(client)
    [ask] = client.get("/api/trips/asks").get_json()["asks"]
    [url] = build(f"api/trips/asks/{ask['id']}/yes")
    r = client.post(urlsplit(url).path)
    assert r.status_code == 200 and r.get_json()["trip"]["name"] == "Trip to Montréal"


def test_no_screen_encodes_a_path_itself():
    """APIClient goes through RequestURL; nothing else percent-encodes."""
    assert "RequestURL.make(" in (PEARL / "API/APIClient.swift").read_text()
    offenders = [str(p.relative_to(PEARL)) for p in PEARL.rglob("*.swift")
                 if p != SOURCE and re.search(r"addingPercentEncoding|urlPathAllowed", p.read_text())]
    assert offenders == []
