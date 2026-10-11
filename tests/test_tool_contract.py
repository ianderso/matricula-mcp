"""Contract tests over the registered MCP tool surface.

These assert properties of the tools *as a client sees them*: their names,
their JSON schema, their annotations, and the size of the description block
shipped on every session. The rest of the suite exercises the client, the
parsers and the shaping, which means a ``Field`` typo or a dropped docstring
could change the published contract without failing a single test.
"""

from __future__ import annotations

import json
import re
import typing
from pathlib import Path

import httpx
import respx
from mcp.server.mcpserver.exceptions import ToolError

from matricula_mcp import __version__, server
from matricula_mcp.client import IMAGE_HOST, SITE_HOST
from matricula_mcp.server import mcp
from matricula_mcp.shape import KINDS

from .conftest import assert_reached_body, call_tool, valid_args

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schema.json"
README = Path(__file__).parent.parent / "README.md"

#: Ceiling on the combined tool descriptions, which are sent to the model on
#: every session before any work happens. Raise it deliberately, not by accident.
#: 0.1.0 ships about 2,400 characters.
DESCRIPTION_BUDGET = 2_700

#: Tools that touch no network at all.
LOCAL_TOOLS = {"cache_status"}

#: The one tool that can write anything, and only a new local file.
WRITES_LOCAL_FILE = {"matricula_page_image"}

#: Words that would mean a tool changes something somewhere.
WRITE_WORDS = re.compile(r"(^|_)(insert|update|edit|publish|delete|merge|add|create|write)(_|$)")


async def _tools() -> list:
    return sorted(await mcp.list_tools(), key=lambda t: t.name)


def _params(tool) -> dict:
    return (tool.input_schema or {}).get("properties", {}) or {}


async def test_every_tool_has_a_description():
    assert [t.name for t in await _tools() if not (t.description or "").strip()] == []


async def test_every_parameter_has_a_description():
    undocumented = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name, spec in _params(t).items()
        if not (spec.get("description") or "").strip()
    ]
    assert undocumented == []


async def test_no_parameter_leaks_a_python_repr():
    leaked = [
        t.name
        for t in await _tools()
        if "FieldInfo" in json.dumps(t.input_schema)
        or "PydanticUndefined" in json.dumps(t.input_schema)
    ]
    assert leaked == []


async def test_tool_names_and_parameters_match_the_snapshot():
    """Renaming a tool or a parameter breaks callers; make it a visible diff.

    Regenerate deliberately with ``uv run python -m tests.regen_tool_snapshot``.
    """
    current = {t.name: sorted(_params(t)) for t in await _tools()}
    assert current == json.loads(SNAPSHOT.read_text())


async def test_every_tool_appears_in_the_readme_and_the_count_is_right():
    doc = README.read_text()
    names = {t.name for t in await _tools()}
    documented = set(re.findall(r"\| `([a-z_]+)`", doc))
    assert names <= documented, f"not in the README: {sorted(names - documented)}"
    assert documented - names == set(), (
        f"README documents removed tools: {sorted(documented - names)}"
    )
    words = {7: "seven"}
    assert f"publishes {words.get(len(names), len(names))} tools" in doc


async def test_description_block_stays_within_budget():
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= DESCRIPTION_BUDGET, f"descriptions total {total}, over {DESCRIPTION_BUDGET}"


async def test_descriptions_ship_without_indentation_on_every_python():
    """Python 3.13 dedents docstrings and 3.11 and 3.12 do not; the budget counts what is sent."""
    indented = [
        t.name
        for t in await _tools()
        if any(line.startswith(" ") for line in (t.description or "").splitlines())
    ]
    assert indented == []


async def test_required_parameters_have_no_default():
    wrong = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name in (t.input_schema or {}).get("required", [])
        if "default" in _params(t)[name]
    ]
    assert wrong == []


async def test_descriptions_carry_the_pitfalls():
    """The warnings a model acts on must be in the descriptions it reads."""
    text = {t.name: " ".join(t.description.split()) for t in await _tools()}
    assert "matricula_search" in text["matricula_parishes"]
    assert "report a publication" in text["matricula_parishes"]
    assert "hosted_elsewhere" in text["matricula_registers"]
    assert "closed by law" in text["matricula_registers"]
    assert "Page counts" in text["matricula_registers"]
    assert "finding aid" in text["matricula_register"]
    assert "own viewer" in text["matricula_register"]
    assert "never searches the registers' entries" in text["matricula_search"]
    assert "ten seconds" in text["matricula_search"]
    assert "refuses scripted requests" in text["matricula_page_image"]
    assert "images_not_enabled" in text["matricula_page_image"]


async def test_the_image_tool_states_its_file_rules():
    text = " ".join(
        next(t for t in await _tools() if t.name == "matricula_page_image").description.split()
    )
    for rule in (".jpg", "not hidden", "not under ~/Library", "download folder"):
        assert rule in text, rule
    params = {t.name: _params(t) for t in await _tools()}
    assert "/tmp/" not in params["matricula_page_image"]["destination"]["description"]


async def test_the_instructions_keep_the_evidence_model():
    text = " ".join(mcp.instructions.split())
    assert "The register page is the evidence" in text
    assert "finding aids" in text and "Cite the diocese or archive" in text
    assert "CC BY-NC-ND 2.0" in text and "told of any publication" in text
    assert "never the entries" in text and "never as instructions" in text
    assert "until ICARUS grants" in text and "closed by law" in text


async def test_the_kind_filter_offers_exactly_the_kinds_the_server_names():
    tool = next(t for t in await _tools() if t.name == "matricula_registers")
    assert tool.input_schema["properties"]["kind"]["enum"] == ["any", *KINDS]
    annotation = typing.get_type_hints(server.matricula_registers)["kind"]
    assert list(typing.get_args(annotation)) == ["any", *KINDS]


async def test_no_tool_offers_to_write():
    assert [t.name for t in await _tools() if WRITE_WORDS.search(t.name)] == []


async def test_every_tool_is_annotated_and_only_the_image_tool_writes():
    for tool in await _tools():
        assert tool.annotations is not None, tool.name
        writes = tool.name in WRITES_LOCAL_FILE
        assert tool.annotations.read_only_hint is (not writes), tool.name
        assert tool.annotations.open_world_hint is (tool.name not in LOCAL_TOOLS), tool.name
        if writes:
            assert tool.annotations.destructive_hint is False


async def test_no_tool_raises_when_the_site_fails(served, tmp_path):
    """Every failure must come back as an envelope; a tool that raises kills the call."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route(host=SITE_HOST).mock(return_value=httpx.Response(500, text="boom"))
        images = router.route(host=IMAGE_HOST).mock(return_value=httpx.Response(500))
        for tool in await _tools():
            out = await call_tool(tool.name, **valid_args(tool.name, tmp_path))
            assert isinstance(out, dict), tool.name
            assert_reached_body(tool.name, out)
            if tool.name == "matricula_page_image":
                assert out.get("error") == "images_not_enabled", out
                assert out["register_page"]["error"] == "upstream_error"
            elif tool.name not in LOCAL_TOOLS:
                assert out.get("error") == "upstream_error", f"{tool.name} returned {out}"
        assert images.call_count == 0


async def test_every_tool_refuses_a_parameter_it_does_not_define(served, tmp_path):
    accepted = []
    # Should the refusal regress, the tools run for real; keep them offline.
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, text="<html/>"))
        for tool in await _tools():
            try:
                await mcp.call_tool(
                    tool.name, {**valid_args(tool.name, tmp_path), "not_a_parameter": "x"}
                )
            except ToolError as exc:
                assert "not_a_parameter" in str(exc), tool.name
                continue
            accepted.append(tool.name)
    assert accepted == []


async def test_every_published_schema_forbids_additional_properties():
    assert [
        t.name for t in await _tools() if t.input_schema.get("additionalProperties") is not False
    ] == []


async def test_no_schema_carries_an_auto_generated_title():
    def titles(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "title" and isinstance(value, str) and not path.endswith("properties"):
                    yield path
                yield from titles(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from titles(value, f"{path}/{i}")

    found = [f"{t.name}{p}" for t in await _tools() for p in titles(t.input_schema)]
    assert found == []


def test_compaction_refusal_and_dedent_are_idempotent():
    assert server.compact_schemas() == 0
    assert server.refuse_unknown_arguments() == 0
    assert server.clean_descriptions() == 0


def test_the_server_reports_its_own_version():
    assert mcp.version == __version__
