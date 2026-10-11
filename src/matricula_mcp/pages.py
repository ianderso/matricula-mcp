"""Reading Matricula's pages: keys, and the HTML the site serves.

Matricula publishes no API. Its catalogue is a tree of plain HTML pages, each
a Django template, and this module reads the few parts the tools need:

=====================  ==========================================  ============
Page                   Address                                     Gives
=====================  ==========================================  ============
holdings               ``/de/bestande/``                           countries
country                ``/de/<country>/``                          sections
section                ``/de/<country>/<section>/``                parishes
section map features   ``/de/landkarte-features/diocese/<s>/``     coordinates
parish                 ``/de/<country>/<section>/<parish>/``       registers
register               ``/de/<country>/<section>/<parish>/<id>/``  pages
place search           ``/de/suchen/?place=...``                   parishes
=====================  ==========================================  ============

A *section* is what Matricula's breadcrumb puts between a country and a
parish: a diocese, a state or diocesan archive, or a private collection.
Everything is addressed by its path below the language prefix, which this
server calls a key: ``deutschland/passau`` is a section,
``oesterreich/salzburg/krimml`` a parish, ``oesterreich/salzburg/krimml/TFBI``
a register. Matricula's own advice is to find a page again through that
hierarchy (diocese or archive, parish, register signature, page) rather than
through stored links, which it does not promise to keep.

Every parser raises :class:`LayoutChanged` when a landmark it relies on is
missing, so a redesigned page is reported as such and never as "nothing
found". What was observed, and when, is in ``docs/API-NOTES.md``.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

#: The interface language every request uses. German is the portal's own,
#: and the one whose slugs the keys are written in.
LANG = "de"

#: Language prefixes Matricula's addresses may carry; a pasted address in any
#: of them names the same page.
LANGS = frozenset({"de", "en", "sl", "cs", "it", "pl", "hr", "sr", "hu"})

#: One path segment of a key: letters, digits and ``_ . ~ -``, as observed
#: (``BiH``, ``IT-RC``, ``gurk__altenmarkt``, ``bw-17317``, ``001_03``).
SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.~-]{0,99}$")

#: How many segments each kind of key has.
DEPTH = {"country": 1, "section": 2, "parish": 3, "register": 4}

_HOSTS = frozenset({"data.matricula-online.eu"})

_MONTHS = {
    "januar": 1,
    "jänner": 1,
    "jaenner": 1,
    "februar": 2,
    "feber": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


class LayoutChanged(RuntimeError):
    """Raised when a page lacks a landmark the parser relies on."""


class InvalidKey(ValueError):
    """Raised when an argument is not a key or address of the kind expected."""


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #
def parse_key(raw: str, kind: str) -> tuple[str, int | None]:
    """The key a tool argument names, and the page number an address carries.

    Accepts the key itself (``oesterreich/salzburg/krimml``), a path
    (``/de/oesterreich/salzburg/krimml/``), or a full address on
    data.matricula-online.eu in any interface language, with ``?pg=N`` for a
    page of a register.

    Raises
    ------
    InvalidKey
        If the argument has the wrong number of segments, a segment outside
        the observed alphabet, or another host.
    """
    want = DEPTH[kind]
    text = (raw or "").strip()
    page: int | None = None
    if not text:
        raise InvalidKey(f"give a {kind} key, e.g. {_EXAMPLES[kind]}")
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in _HOSTS:
            raise InvalidKey(
                f"{raw!r} is not an address on data.matricula-online.eu; give a {kind} key "
                f"such as {_EXAMPLES[kind]}"
            )
        path = parts.path
        page = _page_from_query(parts.query)
    else:
        path, _, query = text.partition("?")
        page = _page_from_query(query)
    segments = [unquote(s) for s in path.split("/") if s]
    if path.startswith("/") and segments and segments[0] in LANGS:
        segments = segments[1:]
    if len(segments) != want or not all(SEGMENT.match(s) for s in segments):
        raise InvalidKey(
            f"{raw!r} is not a {kind} key: expected {want} part"
            f"{'s' if want > 1 else ''} such as {_EXAMPLES[kind]}"
        )
    return "/".join(segments), page


_EXAMPLES = {
    "country": "'oesterreich'",
    "section": "'deutschland/passau'",
    "parish": "'oesterreich/salzburg/krimml'",
    "register": "'oesterreich/salzburg/krimml/TFBI'",
}


def _page_from_query(query: str) -> int | None:
    match = re.search(r"(?:^|&)pg=(\d{1,6})(?:&|$)", query or "")
    return int(match.group(1)) if match else None


def path_of(key: str) -> str:
    """The site path of a key, in the server's interface language."""
    return f"/{LANG}/{key}/"


def key_of(href: str) -> str | None:
    """The key a site link names (``/de/a/b/`` -> ``a/b``), or None if it is not one."""
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        if (parts.hostname or "").lower() not in _HOSTS:
            return None
    segments = [unquote(s) for s in parts.path.split("/") if s]
    if not segments or segments[0] not in LANGS:
        return None
    segments = segments[1:]
    if not segments or not all(SEGMENT.match(s) for s in segments):
        return None
    return "/".join(segments)


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"(?i)<br\s*/?>|</p\s*>|</li\s*>|</h\d\s*>")


def text_of(fragment: str) -> str:
    """Readable text from an HTML fragment: tags dropped, entities decoded, lines kept."""
    fragment = re.sub(r"(?is)<(script|style)\b.*?</\1>", "", fragment)
    fragment = _BREAK.sub("\n", fragment)
    text = html.unescape(_TAG.sub("", fragment)).replace("\xa0", " ")
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def one_line(fragment: str) -> str:
    """:func:`text_of` on one line."""
    return " ".join(text_of(fragment).split())


def clip(text: str, limit: int) -> str:
    """Shorten text to ``limit`` characters at a word boundary, marking the cut."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(None, 1)[0] if " " in text[:limit] else text[:limit]
    return cut.rstrip(" ,;:") + " …"


def fold(text: str) -> str:
    """Text for matching: case and accents folded, hyphens and dots as spaces."""
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ß", "ss"))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[-_.,/]+", " ", plain).split())


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})


def variants(text: str) -> set[str]:
    """The folded forms a name may be written in: ``Altötting`` is also ``Altoetting``.

    Matricula's archives write German umlauts both ways (``Mühlbach``,
    ``Altoetting``), so a name is matched in both its plain and its expanded
    spelling.
    """
    return {fold(text), fold(text.casefold().translate(_UMLAUTS))}


def matches(query: str, name: str) -> bool:
    """Whether a folded query is in a folded name, in either umlaut spelling."""
    names = variants(name)
    return any(q in n for q in variants(query) for n in names)


def iso_date(text: str) -> str | None:
    """``1. Januar 1651`` -> ``1651-01-01``; None if the text is not such a date."""
    match = re.fullmatch(r"\s*(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\s+(\d{3,4})\s*", text or "")
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(1)):02d}"


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class Entry:
    """One link in a list: a country, a section or a parish."""

    key: str
    name: str
    parishes: int | None = None


@dataclass
class ListPage:
    """A holdings, country or section page."""

    name: str
    crumbs: list[str]
    entries: list[Entry]
    about: str = ""


@dataclass
class RegisterRow:
    """One register as a parish page lists it."""

    signature: str
    title: str
    dates: str
    link: str | None
    details: dict[str, str] = field(default_factory=dict)


@dataclass
class ParishPage:
    """A parish: where it is, what its registers are."""

    name: str
    crumbs: list[str]
    about: str
    coordinates: tuple[float, float] | None
    stated_total: int | None
    span: str
    registers: list[RegisterRow]


@dataclass
class RegisterPage:
    """One register: its description and the pages its viewer shows."""

    crumbs: list[str]
    book_type: str
    info: dict[str, str]
    labels: list[str]
    files: list[str]
    image_path: str


@dataclass
class SearchHit:
    """One parish a place search found."""

    key: str
    name: str
    snippet: str
    where: str


@dataclass
class SearchPage:
    """A place search's answer."""

    total: int
    hits: list[SearchHit]


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def _main(page: str) -> str:
    """The page's own content, without navigation or footer."""
    start = page.find('id="page-main-content"')
    end = page.find('id="footer"')
    if start < 0:
        raise LayoutChanged("the page has no main content block")
    return page[start : end if end > start else len(page)]


def _crumbs(main: str) -> list[str]:
    """The breadcrumb's labels, after the first ("Bestände" or "Startseite")."""
    match = re.search(r'(?s)<(ol|ul) class="breadcrumb">(.*?)</\1>', main)
    if not match:
        return []
    items = re.findall(r'(?s)<li class="breadcrumb-item[^"]*">(.*?)</li>', match.group(2))
    return [one_line(item) for item in items][1:]


def _h1(main: str) -> str:
    match = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", main)
    if not match:
        raise LayoutChanged("the page has no heading")
    return one_line(match.group(1))


_LIST_LINK = re.compile(r'(?s)<a class="list-group-item[^"]*"\s+href="([^"]+)"\s*>(.*?)</a>')


def parse_list(page: str, parent: str = "") -> ListPage:
    """A holdings, country or section page: its heading and the links it lists.

    ``parent`` is the key the listed entries must sit directly under (empty
    for the holdings page), so stray links are never taken for entries.
    """
    main = _main(page)
    depth = parent.count("/") + 1 if parent else 0
    entries = []
    for href, inner in _LIST_LINK.findall(main):
        key = key_of(href)
        if key is None or key.count("/") != depth:
            continue
        if parent and not key.startswith(parent + "/"):
            continue
        badge = re.search(r'<span class="badge[^"]*">\s*(\d*)\s*</span>', inner)
        name = one_line(re.sub(r'(?s)<span class="(badge|fa)[^"]*">.*?</span>', "", inner))
        count = int(badge.group(1)) if badge and badge.group(1) else None
        entries.append(Entry(key=key, name=name, parishes=count))
    if not entries and 'class="list-group' not in main:
        raise LayoutChanged("the page has no list of entries")
    about = ""
    described = re.search(r'(?s)<div id="map"[^>]*>.*?</div>\s*</div>\s*<div>(.*?)</div>', main)
    if described:
        about = text_of(described.group(1))
    return ListPage(name=_h1(main), crumbs=_crumbs(main), entries=entries, about=about)


def parse_features(data: Any, parent: str) -> dict[str, tuple[float, float]]:
    """Each parish's (latitude, longitude) from a section's map features."""
    out: dict[str, tuple[float, float]] = {}
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise LayoutChanged("the map features are not a GeoJSON FeatureCollection")
    for feature in data["features"]:
        try:
            lon, lat = feature["geometry"]["coordinates"][:2]
            key = key_of(feature["properties"]["url"])
        except (KeyError, TypeError, ValueError):
            continue
        if key and key.startswith(parent + "/") and _plausible(lat, lon):
            out[key] = (round(float(lat), 6), round(float(lon), 6))
    return out


def _plausible(lat: Any, lon: Any) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0.0, 0.0)


_ROW = re.compile(
    r"(?s)<tr>\s*<td nowrap>(.*?)</td>\s*<td nowrap>(.*?)</td>\s*<td>(.*?)</td>\s*"
    r"<td>(.*?)</td>\s*</tr>\s*<tr class=\"collapse\" id=\"details-\d+\">(.*?)</tr>"
)


def parse_parish(page: str) -> ParishPage:
    """A parish page: its place, its description and its table of registers."""
    main = _main(page)
    header = re.search(r'(?s)<h3 id="register-header">(.*?)</h3>', main)
    if not header:
        raise LayoutChanged("the parish page has no register table header")
    head = one_line(header.group(1))
    total = re.search(r"(\d+)\s+gesamt", head)
    span = re.search(r"\(([^)]*)\)", head)
    rows = []
    for links, signature, title, dates, details in _ROW.findall(main):
        link = re.search(r'href="([^"#][^"]*)"[^>]*>\s*<span title="Zum Buch"', links)
        rows.append(
            RegisterRow(
                signature=one_line(signature),
                title=one_line(title),
                dates=one_line(dates),
                link=html.unescape(link.group(1)) if link else None,
                details={
                    one_line(dt): text_of(dd)
                    for dt, dd in re.findall(r"(?s)<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", details)
                },
            )
        )
    about = re.search(r'(?s)<div class="description">(.*?)</div>', main)
    point = re.search(r"POINT \((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)", page)
    coordinates = None
    if point and _plausible(point.group(2), point.group(1)):
        coordinates = (round(float(point.group(2)), 6), round(float(point.group(1)), 6))
    return ParishPage(
        name=_h1(main),
        crumbs=_crumbs(main),
        about=text_of(about.group(1)) if about else "",
        coordinates=coordinates,
        stated_total=int(total.group(1)) if total else None,
        span=span.group(1).strip() if span else "",
        registers=rows,
    )


def _js_array(script: str, name: str) -> list[str]:
    match = re.search(r'"' + name + r'"\s*:\s*(\[.*?\])\s*,\s*\n', script, re.S)
    if not match:
        raise LayoutChanged(f"the register viewer has no {name} list")
    try:
        values = json.loads(match.group(1))
    except ValueError:
        raise LayoutChanged(f"the register viewer's {name} list is not readable") from None
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise LayoutChanged(f"the register viewer's {name} list is not a list of strings")
    return values


def parse_register(page: str) -> RegisterPage:
    """A register page: the description in its info panel and its viewer's page list.

    The viewer's settings name each page's label (``01-Einband_0001``,
    ``001-03_0002-r``) and the image it shows. A register Matricula shows no
    images for has no viewer, and comes back with no pages.
    """
    main = _main(page)
    panel = re.search(r'(?s)<div class="modal fade" id="register-info".*?</table>', page)
    if not panel:
        raise LayoutChanged("the register page has no info panel")
    info: dict[str, str] = {}
    cells = re.findall(r"(?s)<tr>\s*<th>(.*?)<td>(.*?)(?=<tr>|</table>)", panel.group(0))
    for label, value in cells:
        info[one_line(label)] = text_of(value)
    title = re.search(r'(?s)<h4 class="modal-title" id="register-title">(.*?)</h4>', panel.group(0))
    labels: list[str] = []
    files: list[str] = []
    image_path = ""
    viewer_at = page.find("MatriculaDocView(")
    if viewer_at >= 0:
        script = page[viewer_at : page.find("</script>", viewer_at)]
        labels = _js_array(script, "labels")
        files = _js_array(script, "files")
        path = re.search(r'"path"\s*:\s*"([^"]*)"', script)
        image_path = path.group(1) if path else ""
        if len(labels) != len(files):
            raise LayoutChanged("the register viewer lists different numbers of labels and files")
    return RegisterPage(
        crumbs=_crumbs(main),
        book_type=one_line(title.group(1)) if title else "",
        info=info,
        labels=labels,
        files=files,
        image_path=image_path,
    )


#: The parts of a search hit that are not its snippet: number, name, place.
_HIT_PARTS = re.compile(r'(?s)<strong>.*?</strong>|<span class="text-(?:primary|muted)">.*?</span>')

_HIT = re.compile(r'(?s)<a class="list-group-item list-group-item-action" href="([^"]+)">(.*?)</a>')


def parse_search(page: str) -> SearchPage:
    """A place search's answer: the stated total and each parish found."""
    main = _main(page)
    if "Suche nicht erfolgreich" in main:
        return SearchPage(total=0, hits=[])
    stated = re.search(r"(\d+)\s+Ergebnis(?:se)?", main)
    if not stated:
        raise LayoutChanged("the search page states no number of results")
    hits = []
    results = main[main.find('class="list-group results"') :]
    for href, inner in _HIT.findall(results):
        key = key_of(href)
        if key is None or key.count("/") != 2:
            continue
        name = re.search(r'(?s)<span class="text-primary">(.*?)</span>', inner)
        where = re.search(r'(?s)<span class="text-muted">(.*?)</span>', inner)
        body = _HIT_PARTS.sub("", inner)
        snippet = one_line(body).lstrip("•").strip()
        hits.append(
            SearchHit(
                key=key,
                name=one_line(name.group(1)) if name else key.rsplit("/", 1)[-1],
                snippet=snippet,
                where=one_line(where.group(1)) if where else "",
            )
        )
    return SearchPage(total=int(stated.group(1)), hits=hits)
