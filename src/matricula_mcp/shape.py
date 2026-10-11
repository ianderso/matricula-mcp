"""Turning parsed pages into compact, citable tool results.

Every result that names a register carries a citation in the order Matricula
itself gives for finding a page again: diocese or archive, parish, register
signature, page. The Matricula address goes with it as a locator, with the
licence the images are published under.
"""

from __future__ import annotations

from typing import Any

from .client import SITE
from .pages import fold, path_of

#: The licence Matricula's terms put on every church-book image.
LICENCE = "CC BY-NC-ND 2.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-nc-nd/2.0/"

#: Matricula's terms of use, in German, the version that governs.
TERMS_URL = f"{SITE}/de/nutzungsbedingungen/"

#: Who runs the portal.
PORTAL = "Matricula Online (ICARUS)"

#: Characters kept of a parish's or section's description.
ABOUT_CHARS = 1_200

#: Characters kept of a register's contents note or comment.
NOTE_CHARS = 600

#: What a register is about, recognised by the start of a word in its type
#: (in German, and the other interface languages' commonest words), most
#: specific first. A convenience for filtering; the archive's own wording is
#: ``type``.
_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("family_book", ("familienbuch", "familienbogen", "familienregister")),
    ("parish_census", ("seelen", "status animarum", "stan dusz")),
    ("confirmations", ("firm", "konfirm", "cresim", "birm")),
    ("communicants", ("kommunikant", "erstkommunion")),
    ("baptisms", ("tauf", "geburt", "krst", "rojst", "battes", "nati", "chrzt", "urodz")),
    ("marriages", ("trau", "ehe", "heirat", "copul", "kopul", "poro", "matrimon", "slub")),
    ("burials", ("sterb", "verstorb", "tote", "begr", "beerdig", "mrli", "smrt", "mort", "zgon")),
)

#: The kinds a register filter may name.
KINDS = (
    "baptisms",
    "marriages",
    "burials",
    "confirmations",
    "communicants",
    "family_book",
    "parish_census",
    "mixed",
    "other",
)


def kind_of(register_type: str, title: str = "") -> tuple[str, bool]:
    """What a register is about, and whether it is an index to another.

    Matricula's types are the archives' own words: ``Taufen``, ``Index -
    Trauungen``, ``Sterbebuch``, ``Taufregister`` (in Baden-Württemberg the
    register itself, not an index), ``Register Taufen`` (in Passau an index).
    A book covering two or more kinds of event is ``mixed``.
    """
    text = " " + fold(f"{register_type} {title}")
    index = " index" in text or fold(title).startswith("register ")
    found = [kind for kind, stems in _KINDS if any(" " + stem in text for stem in stems)]
    events = [k for k in found if k in ("baptisms", "marriages", "burials")]
    if len(events) > 1 or " misch" in text:
        return "mixed", index
    if found:
        return found[0], index
    return "other", index


def site_url(key: str) -> str:
    """The Matricula address of a key."""
    return SITE + path_of(key)


def viewer_url(register_key: str, page: int) -> str:
    """The address that opens one page of a register in Matricula's own viewer."""
    return f"{site_url(register_key)}?pg={page}"


def dates(start: str | None, end: str | None, shown: str = "") -> str:
    """A register's date range as one string: whole years as years (``1784–1855``)."""
    if start and end:
        if start.endswith("-01-01") and end.endswith("-12-31"):
            first, last = start[:4], end[:4]
            return first if first == last else f"{first}–{last}"
        return start if start == end else f"{start} – {end}"
    return shown or start or end or ""


def citation(
    *,
    archive: str,
    country: str,
    parish: str,
    url: str,
    register: str = "",
    register_type: str = "",
    span: str = "",
    held_at: str = "",
    page: int | None = None,
    label: str = "",
) -> dict[str, Any]:
    """The citation core for a parish, a register or one page of it."""
    out: dict[str, Any] = {"archive": archive, "country": country, "parish": parish}
    words = [archive, parish]
    if register:
        out["register"] = register
        described = " ".join(part for part in (register_type, register) if part)
        if span:
            out["dates"] = span
            described += f" ({span})"
        words.append(described)
    if held_at:
        out["held_at"] = held_at
    if page is not None:
        out["page"] = page
        if label:
            out["page_label"] = label
        words.append(f"image {page}" + (f" ({label})" if label else ""))
    out["portal"] = PORTAL
    out["url"] = url
    out["licence"] = LICENCE
    sentence = ", ".join(w for w in words if w)
    if held_at:
        sentence += f"; original held at {held_at}"
    out["cite_as"] = f"{sentence}. {PORTAL}, {url}. Image licence {LICENCE}."
    return out
