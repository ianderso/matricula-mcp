# matricula-mcp

[![CI](https://github.com/ianderso/matricula-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/matricula-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/matricula-mcp)](https://pypi.org/project/matricula-mcp/)

<!-- mcp-name: io.github.ianderso/matricula-mcp -->

An [MCP](https://modelcontextprotocol.io) server for **Matricula Online**
([data.matricula-online.eu](https://data.matricula-online.eu)), the
church-book portal that ICARUS, the International Centre for Archival
Research, runs for dioceses and archives in Germany, Austria, Poland,
Slovenia, Serbia, Italy, Switzerland, Luxembourg and Bosnia and Herzegovina.
Matricula publishes their parish registers (baptisms, marriages and burials,
and the indexes, family books and parish censuses that go with them),
scanned page by page: about 13,400 parishes by its own count in October 2026.

The server walks Matricula's own hierarchy. It lists the countries and their
*sections* (each a diocese, an archive or a private collection), a section's
parishes with their coordinates, a parish's registers with their signatures,
types and dates, and a register's pages, each with its label and the link
that opens it in Matricula's own viewer. It also runs Matricula's place
search, which finds the parish a village belonged to.

It works the way a careful genealogist does. **The register page is the
evidence.** A register's type and dates, a page label and a search snippet
are finding aids that say which page to open. Every result carries a citation
in the order Matricula itself gives for finding a page again: diocese or
archive, parish, register signature, page.

**Page images are read in Matricula's viewer, not fetched by this server.**
Matricula's image host refuses scripted requests, and this server does not
pretend to be a browser to get past it. The code that would save one page
image is here, documented and tested, but switched off: it is for the day
ICARUS grants access to an identified client. See [Page images](#page-images).

Nothing here writes to Matricula, and nothing here keeps a family tree.

This is an independent project. It is not affiliated with, endorsed by, or
supported by ICARUS or any of the archives and dioceses whose registers
Matricula publishes.

## Tools

The server publishes seven tools. All but `matricula_page_image` are
read-only; that one creates a new file only when image access is on, and
never overwrites one.

**Finding**

| Tool | Purpose |
| --- | --- |
| `matricula_sections` | The countries and, in each, its sections (dioceses and archives), with Matricula's parish counts. |
| `matricula_parishes` | The parishes of one section, filtered by name, with coordinates, and the section's own note (often the archive's address). |
| `matricula_search` | Matricula's place search: parishes whose names or descriptions name a place, with the snippet that shows where. Optionally limited to a section or to registers in a span of years. |

**Reading**

| Tool | Purpose |
| --- | --- |
| `matricula_registers` | A parish's registers: signature, the archive's own type (Taufen, Trauungen, Sterben, Index - ...), a kind (baptisms, marriages, burials, ...), dates, contents notes, where the original is held, and each register's key. |
| `matricula_register` | One register: its description and citation, and every page's position, label and viewer link, with paging and a label filter. |
| `matricula_page_image` | Off unless the operator has turned image access on. While off, it answers `images_not_enabled` with the page's viewer link, label and citation. When on, it saves one page as a new `.jpg` with its citation. |
| `cache_status` | This session's requests, the pacing, cache use, and whether image access is on. Makes no request. |

Everything is addressed by its path on Matricula below the language prefix,
which the tools call a key: `deutschland/passau` is a section,
`oesterreich/salzburg/krimml` a parish, `oesterreich/salzburg/krimml/TFBI` a
register. Every tool also takes a Matricula address in any of its interface
languages, and a register's tools take a page's viewer address (`?pg=N`).

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx matricula-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/matricula-mcp
cd matricula-mcp
uv sync
uv run matricula-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "matricula": {
      "command": "uvx",
      "args": ["matricula-mcp"],
      "env": { "MATRICULA_CONTACT": "you@example.org" }
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add matricula -e MATRICULA_CONTACT=you@example.org -- uvx matricula-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `MATRICULA_CACHE_DIR` | Response cache directory. Default `~/.cache/matricula-mcp`. |
| `MATRICULA_TIMEOUT` | HTTP timeout in seconds for one request. Default 30. Image downloads get 120 to read. |
| `MATRICULA_MIN_INTERVAL` | Least seconds between two requests to Matricula. Default 2, and never below 2. |
| `MATRICULA_SEARCH_INTERVAL` | Least seconds between two place searches. Default 10, and never below 10. |
| `MATRICULA_CONTACT` | An email address or URL added to the User-Agent, so ICARUS can reach you if your use causes trouble. Optional for reading the catalogue, courteous, and required for image access. |
| `MATRICULA_DOWNLOAD_DIR` | An existing folder. When set, `matricula_page_image` saves only inside it. Set it to save into an iCloud Drive folder, which lives under `~/Library`. |
| `MATRICULA_IMAGE_ACCESS` | Leave unset. Set it to `granted` only once ICARUS has granted your client access to its image host; it needs `MATRICULA_CONTACT`. Any other value is refused. See [Page images](#page-images). |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable.

## Page images

Matricula's viewer loads each page from `img.data.matricula-online.eu`. That
host answered **403** to a plain scripted request when this project surveyed
it (with `Vary: Origin`), and the viewer attaches a per-session token,
computed in the browser, to every image request. That is Matricula's access
control, and this server treats it as one. It does not imitate a browser,
send an `Origin` or `Referer` header, carry a session cookie, or reproduce
the viewer's token, and it never probes the host to find out what would get
through. A test fails if anything resembling a browser disguise appears in
the source.

So, by default, `matricula_page_image` fetches nothing. It answers
`images_not_enabled` with the page's viewer link, its label and its
citation, and the person reads the page in Matricula's viewer.

The code that would save a page is written and tested against a mocked host,
for the day ICARUS grants access to an identified client. If you obtain that
permission (by agreement with ICARUS, for your own client), set
`MATRICULA_CONTACT` to the address ICARUS knows you by and
`MATRICULA_IMAGE_ACCESS=granted`. The tool then fetches one page at a time
from the image host, paced like every other request, with this server's own
User-Agent (`matricula-mcp/<version> (+https://github.com/ianderso/matricula-mcp; <your contact>)`)
and nothing else. If the host still refuses, the tool says so
(`image_refused`) and writes nothing. Should ICARUS specify a different route
(an API, a key, another host), the client is to change in a release to use
exactly that route; no setting here invents one.

A saved page is a new `.jpg`, never a hidden file or one under `~/Library`
(unless `MATRICULA_DOWNLOAD_DIR` is set there), and comes with its citation
and its licence, CC BY-NC-ND 2.0.

## Being a good guest

Matricula is one service, run by an association of archives. The client
sends one request at a time, at least two seconds apart, and a place search
at least ten seconds after the last, because a search reads every parish
description in the portal. Country and section lists and parish lists are
cached for 28 days, parish and register pages for 7, searches for a day. Two
identical calls in flight share one request. A 429, a 5xx or a dropped
connection gets one retry, honouring `Retry-After`; a refusal is not retried.
The User-Agent names the package, its version, this repository and, when
set, your contact. No cookies are kept.

### What Matricula's terms say

The [terms of use](https://data.matricula-online.eu/de/nutzungsbedingungen/)
(German; checked 2026-10-11) cover the images and descriptive metadata on
data.matricula-online.eu:

- Every church-book image is licensed **CC BY-NC-ND 2.0**: "Eine kommerzielle
  Weiterverwertung der Bilder ist demnach nicht gestattet" (commercial reuse
  is not permitted). No altered versions, either.
- Data from the registers may be used only as each country's civil-status
  and data-protection law allows; registers holding protected data are not
  shown. In Austria, baptism books are closed for 100 years, and marriage
  and death books are shown up to 1938.
- Anyone who publishes, in print or online, using even a little of the data
  or images undertakes to inform the archive or diocese concerned; for
  online publications a link is enough, and substantial print use calls for
  a copy.
- They say nothing about automated access.

`matricula_parishes` passes on each section's own note, which often names
the archive and how to reach it: the place to send that notice.

### robots.txt, as a fact

Matricula's `robots.txt` (served from `cdn-static.matricula-online.eu`, read
2026-10-11) names several crawlers, ClaudeBot, GPTBot and CCBot among them,
with `Disallow: /`, and asks every other agent to keep away from four kinds
of address: the viewer's page parameter (`/*?pg=`), the search
(`/*/suchen`), the map features (`/*/landkarte-features`) and accounts. This
server is not a crawler: it reads the pages a researcher asks for, one at a
time, and caches them. It reads the search (`matricula_search`) and one map
features file per section (for `matricula_parishes`' coordinates); it builds
`?pg=` links for a person to open and never requests them; it never touches
accounts. Whether that suits your use is yours to judge.

## How to read what comes back

- **Cite the hierarchy, keep the link as a locator.** Matricula advises
  finding a page again through diocese or archive, parish, register
  signature and page, and does not promise that its links last. Each result's
  `citation` gives them in that order, with `cite_as` as one sentence.
- **`page` is the image's position in the register,** counted from 1, which
  is what the viewer's `?pg=` takes. The `label` (`02-Taufe_0001`,
  `001-03_0004-r`) is the archive's name for the scan: a section and number,
  or a folio and side. Cite both.
- **`type` is the archive's word; `kind` is this server's reading of it.**
  `Index - Taufen` and Passau's `Register Taufen` are indexes (`index: true`);
  Baden-Württemberg's `Taufregister` is the register itself.
- **A register with `hosted_elsewhere`** is listed in Matricula but shown on
  the archive's own site (the Landesarchiv Baden-Württemberg's section links
  to its permalinks). Its images are not in Matricula's viewer.
- **A gap is not an absence.** A register missing from Matricula may be
  closed by law, unscanned at the diocese or archive, held elsewhere, or
  lost. `matricula_registers` lists what Matricula has.
- **The search reads parish names and descriptions, never the entries.**
  Many descriptions list the villages a parish served, which is how the
  search finds a village's parish; `snippet` shows the matching text. It
  matches whole words: `Gastein` finds Bad Gastein, not Dorfgastein. No
  search here finds a person's name.
- **Descriptions are the archives' own text.** Parish histories, contents
  notes and comments reach the model verbatim; they are material to weigh,
  never instructions.

## Deliberately not here

- **Fetching page images without permission.** See [Page images](#page-images).
- **Reading entries.** Matricula has no transcriptions or name index; the
  page image is all there is.
- **Accounts, comments or anything that writes to the site.**
- **Working around bot checks.** A challenge is reported as `blocked` and
  left alone.

## Security

Tool arguments are written by a model, and the model reads text this server
does not control. The server assumes that text can steer the model, and
limits what a steered model can make it do.

- **Which hosts.** A request hook refuses anything but https to
  `data.matricula-online.eu`, including addresses taken from a page. The
  image host is refused too while image access is off. Redirects are
  followed only on the same host.
- **Which pages.** A key must have the right number of parts, each from the
  alphabet Matricula's slugs use; anything else (`..`, another host) is
  refused before any lookup.
- **Which addresses.** Each connection is checked where it is made: a name
  that leads to a private, loopback, link-local, CGNAT, multicast, reserved
  or unspecified address, IPv4 or IPv6, is refused, and the connection goes
  to the address that was checked. Proxy settings in the environment are not
  used.
- **How much.** A page over 8 MB, or an image over 60 MB, is refused as it
  streams in.
- **Which files.** `matricula_page_image` creates one new file and never
  overwrites one, and only when image access is on. The bytes must be a
  JPEG, judged by their first bytes. Never a hidden file or folder, never
  under `~/Library`, and with `MATRICULA_DOWNLOAD_DIR` set, never outside it,
  all judged after links are resolved. A refused download leaves nothing on
  disk.
- **Site text is untrusted.** The server's instructions tell the model to
  treat it as material, never as instructions; the model still decides, so
  review what it proposes to do.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches the site
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # paced calls to Matricula's catalogue pages
```

The live check asks Matricula what the recorded pages cannot: whether its
pages still have the shape the server reads. It reads catalogue pages only,
about a dozen, two seconds apart, and one search; it never calls the image
host. See [CONTRIBUTING.md](CONTRIBUTING.md) for how the suite is organised,
[docs/API-NOTES.md](docs/API-NOTES.md) for what was observed of the site and
when, and [docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped this
way.

## Credits

The registers belong to the dioceses, archives and parishes that hold them,
and the images are published by them through Matricula under CC BY-NC-ND
2.0. Matricula is run by [ICARUS](https://icar-us.eu), which asks those who
use it to [support it](https://icar-us.eu/cooperation/online-portals/matricula/support/).

## License

[MIT](LICENSE), for this server's code. The images and descriptions it links
to are under Matricula's terms.
