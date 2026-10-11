"""The tools, called the way a client calls them, against the recorded pages."""

from __future__ import annotations

import httpx

from .conftest import (
    AHOLMING,
    AHOLMING_001_03,
    KRIMML,
    KRIMML_TFBI,
    LABW_PARISH,
    PASSAU,
    SITE,
    call_tool,
    site_responder,
)


def replace(site, **paths) -> None:
    """Answer some paths differently, and the rest from the recordings."""
    site["site"].mock(side_effect=lambda request: site_responder(request, **paths))


# --------------------------------------------------------------------------- #
# matricula_sections
# --------------------------------------------------------------------------- #
async def test_sections_lists_every_country_and_its_sections(served, site):
    out = await call_tool("matricula_sections")
    assert [c["country"] for c in out["countries"]][:2] == ["deutschland", "oesterreich"]
    assert len(out["countries"]) == 10 and out["failed"] == []
    germany = out["countries"][0]
    assert germany["parishes"] == 9125
    assert {"section": PASSAU, "name": "Passau, rk. Bistum", "parishes": 290} in germany["sections"]


async def test_sections_for_one_country_reads_two_pages(served, site):
    out = await call_tool("matricula_sections", country="oesterreich")
    [austria] = out["countries"]
    assert austria["name"] == "Österreich"
    assert any(s["section"] == "oesterreich/salzburg" for s in austria["sections"])
    assert site["site"].call_count == 2


async def test_a_country_may_be_named_in_english_or_german(served, site):
    for name in ("Austria", "Österreich", "oesterreich", "OESTERREICH"):
        out = await call_tool("matricula_sections", country=name)
        assert out["countries"][0]["country"] == "oesterreich", name
    out = await call_tool("matricula_sections", country="Switzerland")
    assert out["countries"][0]["country"] == "CH"


async def test_an_unknown_country_lists_the_ones_there_are(served, site):
    out = await call_tool("matricula_sections", country="Atlantis")
    assert out["error"] == "unknown_country" and "oesterreich (Österreich)" in out["message"]


async def test_a_country_page_that_fails_is_reported_and_the_rest_still_listed(served, site):
    replace(site, **{"/de/polen/": httpx.Response(503)})
    out = await call_tool("matricula_sections")
    assert len(out["countries"]) == 9
    assert out["failed"] == [
        {
            "country": "polen",
            "error": "upstream_error",
            "status": 503,
            "message": out["failed"][0]["message"],
        }
    ]


# --------------------------------------------------------------------------- #
# matricula_parishes
# --------------------------------------------------------------------------- #
async def test_parishes_come_with_coordinates_and_the_sections_note(served, site):
    out = await call_tool("matricula_parishes", section=PASSAU)
    assert out["name"] == "Passau, rk. Bistum" and out["country"] == "Deutschland"
    assert out["total"] == 290 and out["returned"] == 100
    assert out["parishes"][1] == {
        "parish": AHOLMING,
        "name": "Aholming",
        "lat": 48.735446,
        "lon": 12.912979,
    }
    assert "archiv@bistum-passau.de" in out["about"]
    assert out["url"] == f"{SITE}/de/{PASSAU}/"


async def test_parishes_are_matched_ignoring_case_accents_and_hyphens(served, site):
    out = await call_tool("matricula_parishes", section=PASSAU, query="kirchberg im wald")
    assert [p["name"] for p in out["parishes"]] == ["Kirchberg-im-Wald"]
    out = await call_tool("matricula_parishes", section=PASSAU, query="ALTÖTTING")
    assert out["matched"] == 4 and all("altoetting" in p["parish"] for p in out["parishes"])


async def test_no_matching_parish_points_to_the_search(served, site):
    out = await call_tool("matricula_parishes", section=PASSAU, query="Nowhereville")
    assert out["matched"] == 0 and "matricula_search" in out["note"]


async def test_parishes_without_coordinates_are_still_listed(served, site):
    replace(site, **{"/de/landkarte-features/diocese/passau/": httpx.Response(500)})
    out = await call_tool("matricula_parishes", section=PASSAU, count=5)
    assert out["returned"] == 5 and "lat" not in out["parishes"][0]
    assert "matricula_registers" in out["coordinates_note"]


async def test_parishes_take_a_section_address(served, site):
    out = await call_tool("matricula_parishes", section=f"{SITE}/en/{PASSAU}/", count=1)
    assert out["section"] == PASSAU


async def test_an_unknown_section_is_not_found(served, site):
    out = await call_tool("matricula_parishes", section="deutschland/nowhere")
    assert out["error"] == "not_found"


async def test_a_malformed_section_is_refused_before_any_request(served, site):
    out = await call_tool("matricula_parishes", section="deutschland/../../etc")
    assert out["error"] == "invalid_key" and site["site"].call_count == 0


# --------------------------------------------------------------------------- #
# matricula_registers
# --------------------------------------------------------------------------- #
async def test_registers_list_each_with_its_key_type_and_dates(served, site):
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["name"] == "Krimml" and out["archive"] == "Salzburg: Rk. Erzdiözese Salzburg"
    assert (out["lat"], out["lon"]) == (47.222107, 12.175426)
    assert out["total"] == out["returned"] == 8 and "note" not in out
    tfbi = next(r for r in out["registers"] if r["signature"] == "TFBI")
    assert tfbi == {
        "signature": "TFBI",
        "title": "Taufbuch",
        "type": "Taufen",
        "kind": "baptisms",
        "dates": "1784–1855",
        "from": "1784-01-01",
        "to": "1855-12-31",
        "register": KRIMML_TFBI,
        "url": f"{SITE}/de/{KRIMML_TFBI}/",
    }
    assert out["citation"]["parish"] == "Krimml"


async def test_registers_filter_by_kind_and_mark_indexes(served, site):
    out = await call_tool("matricula_registers", parish=AHOLMING, kind="baptisms")
    assert out["total"] == 40 and 0 < out["returned"] < 40
    assert {r["kind"] for r in out["registers"]} == {"baptisms"}
    indexes = [r for r in out["registers"] if r.get("index")]
    assert indexes and all(r["type"] == "Index - Taufen" for r in indexes)
    first = out["registers"][0]
    assert first["held_at"] == "ABP" and first["contents"].startswith("1: Foliierung")


async def test_registers_shown_elsewhere_carry_the_outside_link_not_a_key(served, site):
    out = await call_tool("matricula_registers", parish=LABW_PARISH)
    first = out["registers"][0]
    assert first["hosted_elsewhere"] == "https://www.landesarchiv-bw.de/plink/?f=2-180676"
    assert "register" not in first and first["kind"] == "baptisms"


async def test_a_short_table_is_noted(served, site):
    page = site_responder(httpx.Request("GET", f"{SITE}/de/{KRIMML}/")).text
    replace(
        site, **{f"/de/{KRIMML}/": httpx.Response(200, text=page.replace("8 gesamt", "9 gesamt"))}
    )
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert "states 9 registers" in out["note"]


async def test_a_redesigned_parish_page_is_a_changed_layout_not_an_empty_one(served, site):
    replace(
        site,
        **{
            f"/de/{KRIMML}/": httpx.Response(
                200, text='<div id="page-main-content"><h1>Krimml</h1></div>'
            )
        },
    )
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "layout_changed" and "not an empty result" in out["message"]


# --------------------------------------------------------------------------- #
# matricula_register
# --------------------------------------------------------------------------- #
async def test_a_register_lists_its_pages_with_viewer_links(served, site):
    out = await call_tool("matricula_register", register=KRIMML_TFBI, count=3)
    assert out["signature"] == "TFBI" and out["type"] == "Taufbuch" and out["kind"] == "baptisms"
    assert out["parish"] == KRIMML and out["parish_name"] == "Krimml"
    assert out["archive"] == "Salzburg: Rk. Erzdiözese Salzburg" and out["country"] == "Österreich"
    assert out["total_pages"] == 122 and out["returned"] == 3 and out["next_first"] == 4
    assert out["pages"][2] == {
        "page": 3,
        "label": "02-Taufe_0001",
        "url": f"{SITE}/de/{KRIMML_TFBI}/?pg=3",
    }
    assert out["citation"]["cite_as"].startswith(
        "Salzburg: Rk. Erzdiözese Salzburg, Krimml, Taufbuch TFBI (1784–1855)."
    )
    assert "viewer" in out["images"]


async def test_register_pages_page_on(served, site):
    out = await call_tool("matricula_register", register=KRIMML_TFBI, first=121, count=10)
    assert [p["page"] for p in out["pages"]] == [121, 122] and out["next_first"] is None


async def test_register_pages_filter_by_label_keeping_their_positions(served, site):
    out = await call_tool("matricula_register", register=KRIMML_TFBI, label_contains="index")
    assert out["matched_pages"] == 25 and out["pages"][0]["label"] == "05-Index-Taufe_0001"
    assert out["pages"][-1]["page"] == 122


async def test_a_register_carries_its_storage_and_contents(served, site):
    out = await call_tool("matricula_register", register=AHOLMING_001_03, count=1)
    assert out["held_at"] == "ABP" and out["contents"].startswith("1: Foliierung")
    assert out["pages"][0]["label"] == "001-03_0002-r"
    assert "original held at ABP" in out["citation"]["cite_as"]


async def test_a_register_with_no_images_says_why_it_may_be(served, site):
    page = site_responder(httpx.Request("GET", f"{SITE}/de/{KRIMML_TFBI}/")).text
    start = page.index("dv1 = new arc.imageview.MatriculaDocView")
    page = page[:start] + page[page.index("update_toolbar();", start) :]
    replace(site, **{f"/de/{KRIMML_TFBI}/": httpx.Response(200, text=page)})
    out = await call_tool("matricula_register", register=KRIMML_TFBI)
    assert out["total_pages"] == 0 and out["pages"] == [] and "law" in out["note"]


async def test_a_register_address_with_a_page_is_read_as_the_register(served, site):
    out = await call_tool("matricula_register", register=f"{SITE}/de/{KRIMML_TFBI}/?pg=7", count=1)
    assert out["register"] == KRIMML_TFBI


async def test_an_unknown_register_is_not_found_with_the_reasons(served, site):
    out = await call_tool("matricula_register", register=f"{KRIMML}/NOSUCH")
    assert out["error"] == "not_found" and "closed by law" in out["message"]


# --------------------------------------------------------------------------- #
# matricula_search
# --------------------------------------------------------------------------- #
async def test_search_finds_parishes_and_villages_within_them(served, site, http):
    out = await call_tool("matricula_search", place="Altenmarkt", count=100)
    assert out["total"] == out["returned"] == 37
    first = out["results"][0]
    assert first["parish"] == "oesterreich/st-poelten/altenmarkt-im-yspertal"
    assert first["section"] == "oesterreich/st-poelten" and first["country"] == "Österreich"
    assert first["archive"] == "Niederösterreich (Westen): Rk. Diözese St. Pölten"
    assert served.searches == 1


async def test_search_is_kept_to_one_section(served, site):
    out = await call_tool("matricula_search", place="Altenmarkt", section="oesterreich/gurk")
    assert out["total"] == 37 and out["in_section"] == out["returned"] > 0
    assert all(r["section"] == "oesterreich/gurk" for r in out["results"])


async def test_search_passes_the_years_to_the_site(served, site):
    out = await call_tool("matricula_search", place="Gastein", from_year=1700, to_year=1800)
    assert [r["parish"] for r in out["results"]] == ["oesterreich/salzburg/bad-gastein"]
    sent = site["site"].calls[-1].request.url.params
    assert sent["date_filter"] == "on" and sent["date_range"] == "1700,1800"


async def test_a_search_that_finds_nothing_says_what_it_covers(served, site):
    out = await call_tool("matricula_search", place="Qxzvbnm")
    assert out["total"] == 0 and out["results"] == [] and "whole words" in out["note"]


async def test_search_arguments_are_checked_before_any_request(served, site):
    for args, error in (
        ({"place": "x"}, "bad_place"),
        ({"place": "Altenmarkt", "from_year": 1700}, "bad_years"),
        ({"place": "Altenmarkt", "from_year": 1800, "to_year": 1700}, "bad_years"),
        ({"place": "Altenmarkt", "section": "../x"}, "invalid_key"),
    ):
        assert (await call_tool("matricula_search", **args))["error"] == error
    assert site["site"].call_count == 0


async def test_search_answers_are_cached_for_a_day(served, site):
    await call_tool("matricula_search", place="Altenmarkt")
    await call_tool("matricula_search", place="Altenmarkt")
    assert site["site"].call_count == 1 and served.searches == 1


# --------------------------------------------------------------------------- #
# Failures
# --------------------------------------------------------------------------- #
async def test_an_outage_is_not_an_empty_result(served, site):
    site["site"].mock(return_value=httpx.Response(502))
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "upstream_error" and "not an empty result" in out["message"]


async def test_a_timeout_is_not_an_empty_result(served, site):
    site["site"].mock(side_effect=httpx.ReadTimeout("slow"))
    out = await call_tool("matricula_register", register=KRIMML_TFBI)
    assert out["error"] == "timed_out" and "not an empty result" in out["message"]


async def test_a_bot_check_is_reported_as_blocked(served, site):
    site["site"].mock(return_value=httpx.Response(403, headers={"cf-mitigated": "challenge"}))
    out = await call_tool("matricula_parishes", section=PASSAU)
    assert out["error"] == "blocked"


async def test_a_bad_setting_is_reported_on_the_first_call(monkeypatch, tmp_path):
    from matricula_mcp import server

    monkeypatch.setattr(server.runtime, "http", None)
    monkeypatch.setattr(server.runtime, "config", None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MATRICULA_MIN_INTERVAL", "0.5")
    out = await call_tool("matricula_sections")
    assert out["error"] == "not_configured" and "MATRICULA_MIN_INTERVAL" in out["message"]


async def test_cache_status_reports_pacing_and_use(served, site):
    await call_tool("matricula_registers", parish=KRIMML)
    await call_tool("matricula_registers", parish=KRIMML)
    out = await call_tool("cache_status")
    assert out["live_calls_this_session"] == 1 and out["cache_hits_this_session"] == 1
    assert out["calls_by_host"] == {"data.matricula-online.eu": 1}
