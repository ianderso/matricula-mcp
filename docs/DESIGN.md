# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The question it answers

"Which parish's books would record this family, and are they on Matricula?"
Matricula holds the scanned registers of dozens of dioceses and archives,
but no transcriptions and no name index: the way in is the place, then the
parish, then the register by its type and years, then the page. The server
answers each of those steps, and stops at the page, which a person reads.

## Matricula's hierarchy, kept

The tools follow the portal's own tree (country, section, parish, register,
page), and address everything by the path Matricula uses, below the language
prefix: `oesterreich/salzburg/krimml/TFBI`. That is a key a model can carry
from one tool to the next, a person can paste from the browser, and a
citation can be checked against. It is also how ICARUS asks users to find a
page again, because it does not promise that links last.

A *section* is what sits between a country and a parish in Matricula's
breadcrumb: a diocese, a state archive (the Landesarchiv Baden-Württemberg),
a private collection. The server does not try to tell these apart; the
section's own name says what it is.

## Few tools, each one level

Seven tools: one per level of the tree, the place search, the image tool and
the cache report. A parish's register list gives no page counts, because the
parish page does not carry them and fetching every register page to count
would cost a request per register; `matricula_register` gives the count.

## Pacing and caching

Matricula publishes no rate. It is one service, run by an association of
archives, so the client sends one request at a time, never less than two
seconds apart, and a place search never less than ten seconds after the
last: a search reads every parish description in the portal. The upper
levels change when an archive adds a parish, so they are kept 28 days;
parish and register pages 7; searches a day. A failure is never cached.

## Page images: written, off, and honest

The earlier survey found that the image host refuses a scripted request,
and the viewer's script signs each image request with a value derived from
the browser session. The decision is that this server reads only
what it may read openly, and that the image path is specified in code for
the day ICARUS grants access:

- **Off by default.** `MATRICULA_IMAGE_ACCESS` unset means the request hook
  refuses the image host outright, and `matricula_page_image` answers
  `images_not_enabled` with the page's viewer link, label and citation.
- **Only the operator turns it on,** with the exact value `granted`, and
  only with `MATRICULA_CONTACT` set: access is granted to an identified
  client, and the contact in the User-Agent is what identifies it. A model
  cannot change either.
- **Honest when on.** The request carries this server's own User-Agent and
  an `Accept` header, nothing more: no browser string, no `Origin` or
  `Referer`, no cookie, no reproduced signature. A source scan in the test
  suite fails if any of those appear. If the host refuses, the refusal is
  the answer, and it is not retried.
- **Ready for the route ICARUS specifies.** If ICARUS grants access some
  other way (an API, a key, a different host), the client changes in a
  release to use that route. No setting here invents one in advance.

Saving follows the sibling servers' rules exactly (`_destination`,
`_within`): an absolute path; a new `.jpg`; no hidden component; nothing
under `~/Library` unless `MATRICULA_DOWNLOAD_DIR` is set there; inside that
folder when it is set; links resolved before every check; the bytes judged
by their first bytes; a refused download leaves nothing.

## Coordinates and robots.txt

The diocese pages do not carry coordinates; their map loads one GeoJSON file
per section, and each parish page carries its own point. `robots.txt` asks
agents other than the named AI crawlers to avoid the map-features path and
the search path, and names ClaudeBot among the crawlers it asks to fetch
nothing. The project records robots.txt as a fact and lets Matricula's terms
decide; the terms say nothing on automated access. So the server reads one
map-features file per section, cached four weeks, and the search, paced at
ten seconds; it never requests the viewer's `?pg=` addresses, which it only
builds for a person to open. The README says all of this, so an operator can
decide otherwise.

## Which hosts a tool reaches

Tool arguments are written by a model that reads text nobody here controls.
The hosts are fixed: `data.matricula-online.eu`, and
`img.data.matricula-online.eu` only when image access is on. A request hook
refuses anything else, including an address taken from a page, and
redirects are followed only on the same host. A key is checked against the
alphabet Matricula's slugs use and the number of parts its kind has, so no
argument can climb out of the catalogue. Every connection is checked where
it is made against private, loopback, link-local and other non-public
addresses, as in the sibling servers.

## Parsing HTML without a parser

The pages are regular Django templates, and the server reads a handful of
landmarks with regular expressions and the standard library, which keeps
the dependency list to what every sibling server has. Each parser raises
`LayoutChanged` when a landmark is missing, so a redesign is reported as
such, never as an empty answer, and the live check is where it shows first.

## Out of scope, by decision

- **Fetching images without permission**, by any means.
- **Reading entries**: there is no text to read; the page is the record.
- **Accounts, comments, anything that writes to the site.**
- **Working around a bot check.** A challenge is reported as `blocked`.
