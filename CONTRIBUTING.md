# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/matricula-mcp
cd matricula-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded Matricula pages. It must never touch the live site: Matricula is one
service run by an association of archives, and CI should not depend on it
being up. Nothing in the suite or the live check calls the image host.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/matricula_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. Also the destination rules for a saved image. |
| `src/matricula_mcp/pages.py` | Keys, and reading Matricula's pages: holdings, country, section, map features, parish, register, search. |
| `src/matricula_mcp/client.py` | The cached, paced HTTP client, the two-host allowlist and the image gate, the redirect rule, the public-address check made at connect time, and the size caps. |
| `src/matricula_mcp/shape.py` | Kinds of register, date ranges, viewer links, the citation core. |
| `src/matricula_mcp/config.py` | Settings from the environment and `.env`, including the image-access gate. |
| `docs/API-NOTES.md` | What the site was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded pages and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/test_images.py` | The image gate: off by default, honest when on, no disguise in the source. |
| `tests/test_security.py` | Every refusal against a steered model: keys, hosts, addresses, sizes, files. |
| `tests/live_check.py` | The one script that talks to the live site, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own. They
are dedented at import, so the budget measures the same text on every Python.

**The evidence distinction, kept.** A register's type and dates, a page label
and a search snippet are finding aids to the page, never the record.

**A citation on every register and page,** in Matricula's order: diocese or
archive, parish, register signature, page.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with the site
failing and fails if one raises.

**Nothing that gets past an access control.** The image path stays off until
ICARUS grants access, and when on it sends this server's own User-Agent and
nothing that passes for a browser. A pull request that adds a browser
User-Agent, a forged `Origin` or `Referer`, a session cookie or a
reproduction of the viewer's token will not be merged, and
`tests/test_images.py` fails on most of them. If ICARUS specifies a route,
implement exactly that route, and say in the pull request where the
permission is recorded.

**Nothing that widens what an argument can reach.** Treat every argument as
written by someone else's text. A new kind of address goes through
`pages.parse_key` and the client's host hook, a new place to write through
`server._destination`, and each comes with a test in `tests/test_security.py`
showing that the refusals still come before the harm.

**A new fixture recorded, not invented,** when a change depends on how the
site answers, with what was observed and when added to `docs/API-NOTES.md`.
Record neutral examples. Pace yourself as the client does: two seconds
between pages, ten between searches.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## Releasing

A maintainer bumps `__version__` in `src/matricula_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
