"""Shared fixtures. Every test runs against a mocked site; nothing touches the network.

The fixtures under ``fixtures/`` are real Matricula pages recorded on
2026-10-11 (see docs/API-NOTES.md). The examples are deliberately neutral:
the holdings and country pages; the diocese of Passau's parish list and map
features; Krimml, a parish in the archdiocese of Salzburg, and its first
baptism book (TFBI, 1784-1855); Aholming, in Passau, and its baptism book
001_03 (1651-1695), whose pages are labelled by folio; Kirchberg an der Iller,
whose registers the Landesarchiv Baden-Württemberg shows on its own site; and
place searches for Altenmarkt, for Gastein in 1700-1800, and for a word that
names nothing.

Trimmed and redacted where noted: the country page for Austria lacks one
entry; Aholming's page lacks its description; the two register pages lack
their side panel (the info panel repeats it); the search pages lack the
search form's list of dioceses; the map key and the per-request form tokens
the pages embed are replaced with ``REDACTED-IN-FIXTURE``.

No page image was ever fetched: the image tests answer with a few bytes made
here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from matricula_mcp import server
from matricula_mcp.client import IMAGE_HOST, SITE_HOST, MatriculaHttp
from matricula_mcp.config import Config

FIXTURES = Path(__file__).parent / "fixtures"

SITE = f"https://{SITE_HOST}"
IMAGES = f"https://{IMAGE_HOST}"

#: Keys of the recorded examples.
PASSAU = "deutschland/passau"
KRIMML = "oesterreich/salzburg/krimml"
KRIMML_TFBI = "oesterreich/salzburg/krimml/TFBI"
AHOLMING = "deutschland/passau/aholming"
AHOLMING_001_03 = "deutschland/passau/aholming/001_03"
LABW_PARISH = "deutschland/baden_wuerttemberg/bw-17317"

#: The smallest JPEG header a download check accepts.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64

#: Every recorded page, by the path it answers.
PAGES: dict[str, str] = {
    "/de/bestande/": "holdings.html",
    "/de/deutschland/": "country_deutschland.html",
    "/de/oesterreich/": "country_oesterreich.html",
    "/de/polen/": "country_polen.html",
    "/de/serbien/": "country_serbien.html",
    "/de/LU/": "country_LU.html",
    "/de/BiH/": "country_BiH.html",
    "/de/slovenia/": "country_slovenia.html",
    "/de/italien/": "country_italien.html",
    "/de/Privatarchiv/": "country_Privatarchiv.html",
    "/de/CH/": "country_CH.html",
    f"/de/{PASSAU}/": "section_passau.html",
    "/de/landkarte-features/diocese/passau/": "features_passau.json",
    f"/de/{KRIMML}/": "parish_krimml.html",
    f"/de/{KRIMML_TFBI}/": "register_krimml_TFBI.html",
    f"/de/{AHOLMING}/": "parish_aholming.html",
    f"/de/{AHOLMING_001_03}/": "register_aholming_001_03.html",
    f"/de/{LABW_PARISH}/": "parish_bw-17317.html",
}

#: Recorded searches, by their ``place`` and ``date_range`` parameters.
SEARCHES: dict[tuple[str, str], str] = {
    ("Altenmarkt", ""): "search_altenmarkt.html",
    ("Gastein", "1700,1800"): "search_gastein_1700_1800.html",
    ("Qxzvbnm", ""): "search_none.html",
}


def fixture(name: str) -> Any:
    """Load one recorded response: JSON for .json files, text otherwise."""
    path = FIXTURES / name
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def answer(name: str) -> httpx.Response:
    """A recorded page or document as a 200 response."""
    if name.endswith(".json"):
        return httpx.Response(200, json=fixture(name))
    return httpx.Response(
        200, text=fixture(name), headers={"content-type": "text/html; charset=utf-8"}
    )


def not_found() -> httpx.Response:
    """Matricula's answer to an address it has no page for, as recorded."""
    return httpx.Response(
        404, text=fixture("not_found.html"), headers={"content-type": "text/html"}
    )


def site_responder(request: httpx.Request, **extra: Any) -> httpx.Response:
    """Answer one request to the catalogue host from the recordings."""
    path = request.url.path
    if path in extra:
        value = extra[path]
        return value(request) if callable(value) else value
    if path == "/de/suchen/":
        key = (request.url.params.get("place", ""), request.url.params.get("date_range", ""))
        return answer(SEARCHES[key]) if key in SEARCHES else answer("search_none.html")
    if path in PAGES:
        return answer(PAGES[path])
    return not_found()


def make_http(tmp_path: Path, **kwargs) -> MatriculaHttp:
    """A client with no pacing and no back-off, caching under ``tmp_path``."""
    options = {"min_interval": 0.0, "search_interval": 0.0, "backoff": 0.0}
    options.update(kwargs)
    return MatriculaHttp(tmp_path / "cache", **options)


@pytest.fixture
def http(tmp_path) -> MatriculaHttp:
    return make_http(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> MatriculaHttp:
    """Install a fast test client as the server's client, image access off."""
    c = make_http(tmp_path)
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return c


@pytest.fixture
def served_with_images(tmp_path, monkeypatch) -> MatriculaHttp:
    """The server's client as it would run once ICARUS granted image access."""
    c = make_http(tmp_path, image_access=True, contact="researcher@example.org")
    monkeypatch.setattr(server.runtime, "http", c)
    monkeypatch.setattr(
        server.runtime,
        "config",
        Config(cache_dir=tmp_path / "cache", image_access=True, contact="researcher@example.org"),
    )
    return c


@pytest.fixture
def site():
    """A respx router answering the catalogue host from the recordings.

    The image host is routed too, so a test can assert it was never called;
    any other host fails the test.
    """
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        router.route(host=SITE_HOST, name="site").mock(side_effect=site_responder)
        router.route(host=IMAGE_HOST, name="images").mock(
            return_value=httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        )
        yield router


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved."""
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


# --------------------------------------------------------------------------- #
# Argument building for whole-surface sweeps
# --------------------------------------------------------------------------- #
#: Errors a tool returns from its own input checks, before any work. A sweep
#: that gets one of these has not tested what it thinks it has.
LOCAL_VALIDATION_ERRORS = frozenset(
    {
        "invalid_key",
        "unknown_country",
        "bad_place",
        "bad_years",
        "no_page",
        "no_destination",
        "relative_destination",
        "destination_exists",
        "no_such_directory",
        "bad_extension",
        "hidden_path",
        "protected_location",
        "outside_download_dir",
    }
)

#: Arguments that carry each tool past its own checks. The image tool's
#: destination is filled in per test, under tmp_path.
VALID_ARGS: dict[str, dict] = {
    "matricula_sections": {"country": "oesterreich"},
    "matricula_parishes": {"section": PASSAU},
    "matricula_registers": {"parish": KRIMML},
    "matricula_register": {"register": KRIMML_TFBI},
    "matricula_search": {"place": "Altenmarkt"},
    "matricula_page_image": {"register": KRIMML_TFBI, "page": 3},
    "cache_status": {},
}


def valid_args(tool_name: str, tmp_path: Path) -> dict:
    """VALID_ARGS for one tool, with a fresh destination for the image tool."""
    args = dict(VALID_ARGS[tool_name])
    if tool_name == "matricula_page_image":
        args["destination"] = str(tmp_path / f"sweep-{len(list(tmp_path.iterdir()))}.jpg")
    return args


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS in tests/conftest.py. Message: {result.get('message')!r}"
        )
