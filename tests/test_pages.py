"""Reading Matricula's pages and keys, against the recorded pages."""

from __future__ import annotations

import pytest

from matricula_mcp.pages import (
    InvalidKey,
    LayoutChanged,
    clip,
    fold,
    iso_date,
    key_of,
    matches,
    parse_features,
    parse_key,
    parse_list,
    parse_parish,
    parse_register,
    parse_search,
    text_of,
)
from matricula_mcp.shape import citation, dates, kind_of, viewer_url

from .conftest import AHOLMING, KRIMML, KRIMML_TFBI, PASSAU, fixture


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "kind", "key", "page"),
    [
        ("oesterreich", "country", "oesterreich", None),
        ("deutschland/passau", "section", "deutschland/passau", None),
        ("/de/deutschland/passau/", "section", "deutschland/passau", None),
        (KRIMML, "parish", KRIMML, None),
        (f"https://data.matricula-online.eu/de/{KRIMML}/", "parish", KRIMML, None),
        (f"https://data.matricula-online.eu/en/{KRIMML_TFBI}/?pg=12", "register", KRIMML_TFBI, 12),
        (f"{KRIMML_TFBI}?pg=3", "register", KRIMML_TFBI, 3),
        ("deutschland/baden_wuerttemberg/bw-17317", "parish", None, None),
        ("  BiH/banjaluka  ", "section", "BiH/banjaluka", None),
        # Only the path names the page; nothing else in a query is ever sent.
        ("oesterreich/salzburg?x=1#frag", "section", "oesterreich/salzburg", None),
    ],
)
def test_a_key_is_read_from_a_key_a_path_or_an_address(raw, kind, key, page):
    expected = key or raw.strip()
    assert parse_key(raw, kind) == (expected, page)


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("", "parish"),
        ("oesterreich/salzburg", "parish"),
        ("oesterreich/salzburg/krimml/TFBI/extra", "register"),
        ("oesterreich/../etc", "section"),
        ("oesterreich/salz burg", "section"),
        ("https://attacker.example/de/oesterreich/salzburg/", "section"),
        ("ftp://data.matricula-online.eu/de/oesterreich/salzburg/", "section"),
        ("oesterreich/%2e%2e", "section"),
    ],
)
def test_anything_else_is_not_a_key(raw, kind):
    with pytest.raises(InvalidKey):
        parse_key(raw, kind)


def test_a_site_link_names_its_key():
    assert key_of("/de/oesterreich/salzburg/krimml/") == KRIMML
    assert key_of("https://data.matricula-online.eu/de/LU/luxemburg/") == "LU/luxemburg"
    assert key_of("https://www.landesarchiv-bw.de/plink/?f=2-180676") is None
    assert key_of("/static/css/styles.css") is None


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def test_text_keeps_lines_and_decodes_entities():
    assert text_of("<p>A&amp;B<br>C&nbsp;D</p><p> E </p>") == "A&B\nC D\nE"


def test_folding_ignores_case_accents_and_hyphens():
    assert fold("Kirchberg-im-Wald") == fold("kirchberg im wald")
    assert fold("Mühlbach am Hochkönig") == "muhlbach am hochkonig"
    assert fold("Straßwalchen") == "strasswalchen"


def test_umlauts_match_in_either_spelling():
    assert matches("Altötting", "Altoetting-StJosef")
    assert matches("muhlbach", "Mühlbach am Hochkönig")
    assert matches("muehlbach", "Mühlbach am Hochkönig")
    assert not matches("Mailand", "Mühlbach am Hochkönig")


def test_clip_marks_the_cut_at_a_word():
    assert clip("one two three", 9) == "one two …"
    assert clip("short", 9) == "short"


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("1. Januar 1651", "1651-01-01"),
        ("31. Dezember 1855", "1855-12-31"),
        ("3. Februar 1808", "1808-02-03"),
        ("1. Jänner 1784", "1784-01-01"),
        ("1651", None),
        ("1. Brumaire 1801", None),
    ],
)
def test_german_dates_become_iso(text, iso):
    assert iso_date(text) == iso


# --------------------------------------------------------------------------- #
# Lists
# --------------------------------------------------------------------------- #
def test_the_holdings_page_lists_ten_countries():
    page = parse_list(fixture("holdings.html"))
    assert [e.key for e in page.entries] == [
        "deutschland",
        "oesterreich",
        "polen",
        "serbien",
        "LU",
        "BiH",
        "slovenia",
        "italien",
        "Privatarchiv",
        "CH",
    ]
    assert page.entries[0].name == "Deutschland" and page.entries[0].parishes == 9125


def test_a_country_page_lists_its_sections():
    page = parse_list(fixture("country_deutschland.html"), "deutschland")
    assert page.name == "Deutschland" and len(page.entries) == 24
    passau = next(e for e in page.entries if e.key == PASSAU)
    assert passau.name == "Passau, rk. Bistum" and passau.parishes == 290
    labw = next(e for e in page.entries if e.key == "deutschland/baden_wuerttemberg")
    assert labw.parishes == 3483


def test_a_section_page_lists_its_parishes_and_its_note():
    page = parse_list(fixture("section_passau.html"), PASSAU)
    assert page.name == "Passau, rk. Bistum" and page.crumbs == ["Deutschland", page.name]
    assert len(page.entries) == 290
    assert page.entries[1].key == AHOLMING and page.entries[1].name == "Aholming"
    assert "archiv@bistum-passau.de" in page.about


def test_entries_under_another_parent_are_not_taken():
    assert parse_list(fixture("section_passau.html"), "oesterreich/salzburg").entries == []


def test_map_features_give_each_parish_a_point():
    points = parse_features(fixture("features_passau.json"), PASSAU)
    assert len(points) == 290
    assert points[AHOLMING] == (48.735446, 12.912979)


@pytest.mark.parametrize("data", [[], {"type": "FeatureCollection"}, "nonsense"])
def test_features_that_are_not_geojson_are_a_changed_layout(data):
    with pytest.raises(LayoutChanged):
        parse_features(data, PASSAU)


# --------------------------------------------------------------------------- #
# Parishes
# --------------------------------------------------------------------------- #
def test_a_parish_page_gives_its_place_and_registers():
    page = parse_parish(fixture("parish_krimml.html"))
    assert page.name == "Krimml"
    assert page.crumbs == ["Österreich", "Salzburg: Rk. Erzdiözese Salzburg", "Krimml"]
    assert page.coordinates == (47.222107, 12.175426)
    assert page.stated_total == 8 and len(page.registers) == 8 and page.span == "1784 - 1938"
    tfbi = next(r for r in page.registers if r.signature == "TFBI")
    assert tfbi.title == "Taufbuch" and tfbi.dates == "1784–1855"
    assert tfbi.link == f"/de/{KRIMML_TFBI}/"
    assert tfbi.details["Matrikeltyp"] == "Taufen"
    assert tfbi.details["Beginn Datumsbereich"] == "1. Januar 1784"


def test_a_parish_page_carries_contents_comments_and_storage():
    page = parse_parish(fixture("parish_aholming.html"))
    assert page.stated_total == 40 and len(page.registers) == 40
    first = page.registers[0]
    assert first.signature == "001_01" and first.details["Lagerungsort"] == "ABP"
    assert first.details["Inhalt"].startswith("1: Foliierung")
    assert "Kommentar" in first.details
    index = next(r for r in page.registers if r.title == "Register Taufen")
    assert index.details["Matrikeltyp"] == "Index - Taufen"


def test_a_register_shown_elsewhere_keeps_its_outside_link():
    page = parse_parish(fixture("parish_bw-17317.html"))
    assert page.about == "Kirchberg an der Iller BC | 4409824-8"
    first = page.registers[0]
    assert first.signature == "LABW, StAL F 901 Bd 812 (1)"
    assert first.link == "https://www.landesarchiv-bw.de/plink/?f=2-180676"


def test_a_page_without_a_register_table_is_a_changed_layout():
    with pytest.raises(LayoutChanged):
        parse_parish(fixture("section_passau.html"))


def test_a_page_without_main_content_is_a_changed_layout():
    with pytest.raises(LayoutChanged):
        parse_list("<html><body><p>maintenance</p></body></html>")


# --------------------------------------------------------------------------- #
# Registers
# --------------------------------------------------------------------------- #
def test_a_register_page_gives_its_description_and_pages():
    page = parse_register(fixture("register_krimml_TFBI.html"))
    assert page.info["Pfarre"] == "Krimml | Salzburg: Rk. Erzdiözese Salzburg | Österreich"
    assert page.info["Signatur"] == "TFBI" and page.book_type == "Taufbuch"
    assert len(page.labels) == len(page.files) == 122
    assert page.labels[:3] == ["01-Einband_0001", "01-Einband_0002", "02-Taufe_0001"]
    assert page.image_path == "https://img.data.matricula-online.eu"
    assert page.files[0].startswith("/image/") and page.files[0].endswith("/")


def test_folio_labels_are_read_as_given():
    page = parse_register(fixture("register_aholming_001_03.html"))
    assert len(page.labels) == 80
    assert page.labels[:2] == ["001-03_0002-r", "001-03_0002-v"]
    assert page.info["Lagerungsort"] == "ABP"


def test_a_register_with_no_viewer_has_no_pages():
    without = fixture("register_krimml_TFBI.html")
    start = without.index("dv1 = new arc.imageview.MatriculaDocView")
    without = without[:start] + without[without.index("update_toolbar();", start) :]
    page = parse_register(without)
    assert page.labels == [] and page.files == [] and page.info["Signatur"] == "TFBI"


def test_a_viewer_whose_lists_disagree_is_a_changed_layout():
    broken = fixture("register_krimml_TFBI.html").replace(
        '"labels": ["01-Einband_0001", ', '"labels": [', 1
    )
    with pytest.raises(LayoutChanged, match="different numbers"):
        parse_register(broken)


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
def test_a_search_lists_parishes_with_where_the_word_was_found():
    page = parse_search(fixture("search_altenmarkt.html"))
    assert page.total == 37 and len(page.hits) == 37
    first = page.hits[0]
    assert first.key == "oesterreich/st-poelten/altenmarkt-im-yspertal"
    assert first.name == "Altenmarkt im Yspertal"
    assert first.snippet.startswith("Altenmarkt (kirchl. Friedhof)")
    assert first.where == "Österreich • Niederösterreich (Westen): Rk. Diözese St. Pölten"
    village = next(h for h in page.hits if h.key == "oesterreich/gurk/gloednitz")
    assert "Altenmarkt" in village.snippet and village.name == "Gloednitz"


def test_a_search_with_a_hit_by_name_alone_has_no_snippet():
    page = parse_search(fixture("search_gastein_1700_1800.html"))
    assert page.total == 1 and page.hits[0].key == "oesterreich/salzburg/bad-gastein"
    assert page.hits[0].snippet == ""


def test_a_search_that_finds_nothing_says_so():
    page = parse_search(fixture("search_none.html"))
    assert page.total == 0 and page.hits == []


def test_a_search_page_that_states_no_count_is_a_changed_layout():
    with pytest.raises(LayoutChanged):
        parse_search(fixture("section_passau.html"))


# --------------------------------------------------------------------------- #
# Kinds and citations
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("register_type", "title", "kind", "index"),
    [
        ("Taufen", "Taufen", "baptisms", False),
        ("Index - Trauungen", "Register Trauungen", "marriages", True),
        ("Sterben", "Sterbebuch", "burials", False),
        ("Taufregister", "Kath. Gem., Taufregister vom 3.1.1808", "baptisms", False),
        ("Eheregister", "", "marriages", False),
        ("Totenregister", "", "burials", False),
        ("Sterben - Trauungen", "Trauungsbuch Sterbebuch", "mixed", False),
        ("Seelenregister", "", "parish_census", False),
        ("Firmungen", "", "confirmations", False),
        ("Matrikenabschriften", "", "other", False),
    ],
)
def test_a_registers_kind_is_read_from_its_type(register_type, title, kind, index):
    assert kind_of(register_type, title) == (kind, index)


def test_date_ranges_read_as_years_when_whole():
    assert dates("1784-01-01", "1855-12-31") == "1784–1855"
    assert dates("1639-01-01", "1639-12-31") == "1639"
    assert dates("1808-01-03", "1848-12-30") == "1808-01-03 – 1848-12-30"
    assert dates(None, None, "1784–1855") == "1784–1855"


def test_a_page_citation_names_the_hierarchy_and_the_licence():
    cite = citation(
        archive="Salzburg: Rk. Erzdiözese Salzburg",
        country="Österreich",
        parish="Krimml",
        register="TFBI",
        register_type="Taufbuch",
        span="1784–1855",
        page=3,
        label="02-Taufe_0001",
        url=viewer_url(KRIMML_TFBI, 3),
    )
    assert cite["cite_as"] == (
        "Salzburg: Rk. Erzdiözese Salzburg, Krimml, Taufbuch TFBI (1784–1855), image 3 "
        "(02-Taufe_0001). Matricula Online (ICARUS), "
        "https://data.matricula-online.eu/de/oesterreich/salzburg/krimml/TFBI/?pg=3. "
        "Image licence CC BY-NC-ND 2.0."
    )
    assert cite["licence"] == "CC BY-NC-ND 2.0" and cite["page_label"] == "02-Taufe_0001"
