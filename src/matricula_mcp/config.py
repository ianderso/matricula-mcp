"""Configuration from environment variables.

=============================  =================================================
``MATRICULA_CACHE_DIR``        Directory for the on-disk response cache.
``MATRICULA_TIMEOUT``          HTTP timeout in seconds for one request.
``MATRICULA_MIN_INTERVAL``     Least seconds between two requests to
                               Matricula. Never below 2.
``MATRICULA_SEARCH_INTERVAL``  Least seconds between two place searches,
                               which cost the site more than a page does.
                               Never below 10.
``MATRICULA_CONTACT``          An email address or URL appended to the
                               User-Agent, so ICARUS can reach whoever runs
                               this server.
``MATRICULA_DOWNLOAD_DIR``     When set, the folder every saved page image
                               must lie inside.
``MATRICULA_IMAGE_ACCESS``     Unset: page images are not fetched at all, and
                               ``matricula_page_image`` answers with the
                               viewer link. ``granted``: ICARUS has granted
                               this client access to its image host, and the
                               tool may fetch one page image at a time. Needs
                               ``MATRICULA_CONTACT``.
=============================  =================================================

None is required: Matricula's catalogue pages need no key and no account. A
``.env`` file in the working directory supplies any of these that the
environment does not. The last three are the operator's to set, never a
model's: they say who is calling, narrow where a tool writes, and decide
whether the image host is reached at all.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

#: Least seconds between two requests to Matricula's pages, and the floor on
#: the setting. Matricula publishes no rate; it is one small service run by
#: an association of archives, so this server keeps well away from it.
MIN_INTERVAL = 2.0

#: Least seconds between two place searches, and the floor on the setting. A
#: search reads every parish description in the portal, which costs the site
#: far more than serving a page.
SEARCH_INTERVAL = 10.0

#: The one value of MATRICULA_IMAGE_ACCESS that turns the image path on.
IMAGE_ACCESS_GRANTED = "granted"


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    cache_dir : Path
        Directory holding cached responses.
    timeout : float
        HTTP timeout in seconds for one request. Image downloads get longer.
    min_interval : float
        Least seconds between the start of one request to a host and the next.
    search_interval : float
        Least seconds between the start of one place search and the next.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    download_dir : Path or None
        When set, ``matricula_page_image`` writes only inside this folder.
    image_access : bool
        True only when the operator has said ICARUS granted image access.
    """

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "matricula-mcp")
    timeout: float = 30.0
    min_interval: float = MIN_INTERVAL
    search_interval: float = SEARCH_INTERVAL
    contact: str = ""
    download_dir: Path | None = None
    image_access: bool = False


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``.

    Raises
    ------
    ConfigError
        If a number is unusable, a contact string could break the header, or
        image access is claimed without a contact. The server loads its
        configuration on the first tool call, so this surfaces there as a
        ``not_configured`` result rather than as a crash.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := os.environ.get("MATRICULA_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("MATRICULA_TIMEOUT"):
        cfg.timeout = _positive("MATRICULA_TIMEOUT", raw)
    if raw := os.environ.get("MATRICULA_MIN_INTERVAL"):
        cfg.min_interval = _at_least("MATRICULA_MIN_INTERVAL", raw, MIN_INTERVAL)
    if raw := os.environ.get("MATRICULA_SEARCH_INTERVAL"):
        cfg.search_interval = _at_least("MATRICULA_SEARCH_INTERVAL", raw, SEARCH_INTERVAL)
    if raw := os.environ.get("MATRICULA_CONTACT"):
        cfg.contact = _contact(raw)
    if raw := os.environ.get("MATRICULA_DOWNLOAD_DIR"):
        cfg.download_dir = _download_dir(raw)
    if raw := os.environ.get("MATRICULA_IMAGE_ACCESS"):
        cfg.image_access = _image_access(raw, cfg.contact)
    return cfg


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable."""
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _at_least(name: str, raw: str, floor: float) -> float:
    """Parse an interval that may be raised but never lowered below ``floor``."""
    value = _positive(name, raw)
    if value < floor:
        raise ConfigError(f"{name} must be at least {floor:g}; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "MATRICULA_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text


def _download_dir(raw: str) -> Path:
    """The folder ``matricula_page_image`` is confined to: absolute, and already there.

    A folder that does not exist yet is refused rather than created, so a
    typing slip cannot confine downloads to somewhere unintended.
    """
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"MATRICULA_DOWNLOAD_DIR must be an absolute path; got {raw!r}.")
    if not path.is_dir():
        raise ConfigError(f"MATRICULA_DOWNLOAD_DIR must be a folder that exists; got {raw!r}.")
    return path


def _image_access(raw: str, contact: str) -> bool:
    """Whether the operator has turned the image path on.

    Matricula's image host refuses scripted requests (it answered 403 to one
    on 2026-10-11, and its viewer signs each image request in the browser).
    This server never imitates a browser to get past that. The image path
    exists for the day ICARUS grants access to an identified client, and
    turning it on is the operator's statement that it has: so the value must
    be exactly ``granted``, and the client must be identified, which means a
    contact in the User-Agent. Should ICARUS specify another route (a key, an
    API), the client changes in a release to use it; no setting here invents
    one.
    """
    value = raw.strip().lower()
    if value != IMAGE_ACCESS_GRANTED:
        raise ConfigError(
            "MATRICULA_IMAGE_ACCESS is either unset (page images are not fetched) or "
            f"'{IMAGE_ACCESS_GRANTED}', set only once ICARUS has granted this client access "
            f"to its image host; got {raw!r}."
        )
    if not contact:
        raise ConfigError(
            "MATRICULA_IMAGE_ACCESS=granted needs MATRICULA_CONTACT: access is granted to an "
            "identified client, and the contact in the User-Agent is what identifies it."
        )
    return True
