# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.1.0] — 2026-10-11

First release.

### Added

- Seven tools over Matricula Online's catalogue: `matricula_sections`
  (countries and their dioceses and archives), `matricula_parishes` (a
  section's parishes, with coordinates and the section's own note),
  `matricula_registers` (a parish's registers: signature, type, kind,
  dates, contents, where the original is held), `matricula_register` (a
  register's description, citation, and every page's label and viewer
  link), `matricula_search` (Matricula's place search), `matricula_page_image`
  and `cache_status`.
- Everything addressed by Matricula's own path as a key
  (`oesterreich/salzburg/krimml/TFBI`), or by a pasted Matricula address in
  any interface language, with `?pg=N` for a page.
- A citation on every register and page in the order Matricula gives for
  finding a page again (diocese or archive, parish, register signature,
  page), with the viewer link as a locator and the licence, CC BY-NC-ND 2.0.
- `matricula_page_image`, written and tested but **off**: Matricula's image
  host refuses scripted requests, and this server does not imitate a
  browser to get past it. While `MATRICULA_IMAGE_ACCESS` is unset, the image
  host is refused outright and the tool answers `images_not_enabled` with
  the page's viewer link, label and citation. The operator may set it to
  `granted`, with `MATRICULA_CONTACT`, once ICARUS has granted access; the
  tool then saves one page as a new `.jpg` under the sibling servers'
  destination rules, sending only this server's own User-Agent.
- A polite client: one request at a time, at least two seconds apart, place
  searches at least ten; lists cached 28 days, parish and register pages 7,
  searches 1; one retry on 429 and 5xx; no cookies kept; two fixed hosts;
  every connection checked against non-public addresses.
