"""The image path: written, off by default, and honest when on.

Matricula's image host answered 403 to a scripted request on 2026-10-11, and
its viewer signs each image request in the browser. This server does not get
past that; it waits for ICARUS to grant access. So these tests check three
things: while image access is off, nothing at all is sent to the image host
and the answer is the viewer link; when the operator has turned it on, a page
is saved under the same rules as the sibling servers' image tools, with its
citation; and whatever the setting, the request is this server's own, with
no browser disguise. The image host is always mocked here; nothing in the
suite or the live check calls it.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from matricula_mcp import client, server
from matricula_mcp.client import IMAGE_HOST, SITE_HOST, user_agent

from .conftest import JPEG, KRIMML_TFBI, call_tool, fixture, site_responder

SRC = Path(server.__file__).parent

#: Page 3 of Krimml's first baptism book, as the recorded register page lists it.
PAGE = {"register": KRIMML_TFBI, "page": 3}


# --------------------------------------------------------------------------- #
# Off, by default
# --------------------------------------------------------------------------- #
async def test_while_off_the_answer_is_the_viewer_link_and_nothing_is_fetched(
    served, site, tmp_path
):
    target = tmp_path / "page.jpg"
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["error"] == "images_not_enabled"
    assert out["viewer_url"] == f"https://{SITE_HOST}/de/{KRIMML_TFBI}/?pg=3"
    assert out["label"] == "02-Taufe_0001"
    assert out["citation"]["page"] == 3 and out["citation"]["licence"] == "CC BY-NC-ND 2.0"
    assert "ICARUS" in out["message"] and "MATRICULA_IMAGE_ACCESS" in out["message"]
    assert site["images"].call_count == 0
    assert not target.exists()


async def test_while_off_no_destination_is_needed(served, site):
    out = await call_tool("matricula_page_image", **PAGE)
    assert out["error"] == "images_not_enabled" and site["images"].call_count == 0


async def test_while_off_a_page_address_works_too(served, site):
    out = await call_tool(
        "matricula_page_image", register=f"https://{SITE_HOST}/de/{KRIMML_TFBI}/?pg=12"
    )
    assert out["page"] == 12 and out["label"] == "02-Taufe_0010"


async def test_while_off_the_link_is_given_even_if_the_register_page_fails(served, site):
    site["site"].mock(return_value=httpx.Response(503))
    out = await call_tool("matricula_page_image", **PAGE)
    assert out["error"] == "images_not_enabled" and out["viewer_url"].endswith("?pg=3")
    assert out["register_page"]["error"] == "upstream_error"
    assert site["images"].call_count == 0


async def test_while_off_a_page_past_the_end_is_named(served, site):
    out = await call_tool("matricula_page_image", register=KRIMML_TFBI, page=500)
    assert out["error"] == "images_not_enabled" and "122 pages" in out["note"]


async def test_a_page_is_required(served, site):
    out = await call_tool("matricula_page_image", register=KRIMML_TFBI)
    assert out["error"] == "no_page"


async def test_cache_status_says_images_are_off(served):
    assert (await call_tool("cache_status"))["image_access"] == "off"


# --------------------------------------------------------------------------- #
# On, once ICARUS has granted access
# --------------------------------------------------------------------------- #
async def test_when_granted_a_page_is_saved_with_its_citation(served_with_images, site, tmp_path):
    target = tmp_path / "krimml-tfbi-3.jpg"
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["path"] == str(target.resolve()) and target.read_bytes() == JPEG
    assert out["format"] == "jpeg" and out["bytes"] == len(JPEG)
    assert out["label"] == "02-Taufe_0001" and out["licence"] == "CC BY-NC-ND 2.0"
    assert out["source_url"].startswith(f"https://{IMAGE_HOST}/image/")
    assert out["citation"]["cite_as"].startswith(
        "Salzburg: Rk. Erzdiözese Salzburg, Krimml, Taufbuch TFBI (1784–1855), image 3"
    )
    assert site["images"].call_count == 1


async def test_the_image_request_is_the_servers_own(served_with_images, site, tmp_path):
    await call_tool("matricula_page_image", destination=str(tmp_path / "p.jpg"), **PAGE)
    sent = site["images"].calls[0].request.headers
    assert sent["user-agent"] == user_agent("researcher@example.org")
    assert sent["accept"] == "image/jpeg"
    for header in ("origin", "referer", "cookie", "x-requested-with", "sec-fetch-mode"):
        assert header not in sent, header
    assert "csrf" not in str(site["images"].calls[0].request.url)
    assert "ctrl" not in str(site["images"].calls[0].request.url)


async def test_a_refusal_from_the_image_host_is_reported_and_leaves_nothing(
    served_with_images, site, tmp_path
):
    site["images"].mock(return_value=httpx.Response(403, headers={"vary": "Origin"}))
    target = tmp_path / "p.jpg"
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["error"] == "image_refused" and "ICARUS" in out["message"]
    assert site["images"].call_count == 1  # a refusal is not retried
    assert not target.exists()


async def test_bytes_that_are_not_a_jpeg_leave_nothing(served_with_images, site, tmp_path):
    site["images"].mock(return_value=httpx.Response(200, text="<html>login</html>"))
    target = tmp_path / "p.jpg"
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["error"] == "not_an_image" and not target.exists()


async def test_a_page_past_the_end_is_refused_before_any_image_request(
    served_with_images, site, tmp_path
):
    out = await call_tool(
        "matricula_page_image", register=KRIMML_TFBI, page=123, destination=str(tmp_path / "p.jpg")
    )
    assert out["error"] == "no_such_page" and site["images"].call_count == 0


async def test_a_register_page_naming_another_image_host_is_refused(
    served_with_images, site, tmp_path
):
    moved = fixture("register_krimml_TFBI.html").replace(
        '"path": "https://img.data.matricula-online.eu"', '"path": "https://images.example"'
    )
    replaced = {f"/de/{KRIMML_TFBI}/": httpx.Response(200, text=moved)}
    site["site"].mock(side_effect=lambda request: site_responder(request, **replaced))
    out = await call_tool("matricula_page_image", destination=str(tmp_path / "p.jpg"), **PAGE)
    assert out["error"] == "unexpected_image_host" and site["images"].call_count == 0


async def test_when_granted_a_destination_is_checked_before_any_request(
    served_with_images, site, tmp_path
):
    out = await call_tool("matricula_page_image", destination=str(tmp_path / "p.png"), **PAGE)
    assert out["error"] == "bad_extension"
    assert site["site"].call_count == 0 and site["images"].call_count == 0


async def test_when_granted_a_destination_is_required(served_with_images, site):
    out = await call_tool("matricula_page_image", **PAGE)
    assert out["error"] == "no_destination" and site["images"].call_count == 0


async def test_cache_status_says_images_are_granted(served_with_images):
    assert (await call_tool("cache_status"))["image_access"] == "granted"


# --------------------------------------------------------------------------- #
# No disguise anywhere in the code
# --------------------------------------------------------------------------- #
#: What a browser imitation would need written down somewhere.
DISGUISE = re.compile(
    r"Mozilla/|AppleWebKit|Chrome/\d|Safari/\d|Gecko/|Firefox/\d|"
    r"[\"'](Origin|Referer|Sec-Fetch-[A-Za-z-]+|X-Requested-With)[\"']\s*:",
    re.I,
)


@pytest.mark.parametrize("path", sorted(SRC.glob("*.py")), ids=lambda p: p.name)
def test_no_source_file_carries_a_browser_disguise(path):
    assert DISGUISE.findall(path.read_text(encoding="utf-8")) == []


def test_the_client_sends_only_its_own_two_headers():
    http = client.MatriculaHttp(Path("/nonexistent"), min_interval=0.0)
    assert {k.lower() for k in http._http.headers} >= {"user-agent", "accept"}
    assert http._http.headers["user-agent"].startswith("matricula-mcp/")
    assert "origin" not in http._http.headers and "referer" not in http._http.headers
