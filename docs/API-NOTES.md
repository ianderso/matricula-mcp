# Matricula notes

What Matricula Online (`data.matricula-online.eu`) was observed to serve,
and when. Matricula publishes no API and no documentation for automated use;
everything here was read from its pages.

Observed 2026-10-11, about 50 requests in all to the catalogue host, two to
three seconds apart (searches ten), with this project's User-Agent and no
cookies kept. **Nothing was requested from the image host**
(`img.data.matricula-online.eu`); what is said of it below comes from an
earlier survey and from the viewer's own script.

## Transport

- Plain HTML, server-rendered by Django behind Apache (`Server:
  Apache/2.4.29 (Ubuntu)`), UTF-8. No key, no account. Every page sets a
  `shared_csrftoken` cookie for `.data.matricula-online.eu`; the catalogue
  pages do not need it, and the client keeps none.
- Every address has a language prefix: `/de/`, `/en/`, `/sl/`, `/cs/`, `/it/`.
  The path below it is the same in every language; the server uses `/de/`,
  the portal's own.
- An unknown address answers **404** with a 77-byte page (`<h1>Not
  Found</h1>...`), for a country, a section, a parish or a register alike.
- No bot check was met on any page.

## The hierarchy

| Level | Address | What it holds |
| --- | --- | --- |
| holdings | `/de/bestande/` | One `list-group-item` link per country, with a badge counting its parishes: Deutschland 9125, Österreich 2871, Polen 5, Serbien 5, Luxemburg/Luxembourg 277, Bosnien und Herzegowina 2, Slovenia 723, Italien 106, Privatarchiv 3, Schweiz 292. |
| country | `/de/<country>/` | One link per section (diocese, archive or collection) with a parish count. 24 for Germany, 20 for Austria. Keys are the site's slugs, mixed case (`LU`, `CH`, `BiH`, `Privatarchiv`). |
| section | `/de/<country>/<section>/` | Every parish on one page (290 for Passau, 115 KB; no paging), with the section's own note in the left column (Passau's names the diocesan archive's address and email). |
| map features | `/de/landkarte-features/diocese/<section>/` | A GeoJSON FeatureCollection: one Point per parish, `[lon, lat, 0.0]`, with `name` and `url`. 290 features for Passau, 52 KB. The section page's map loads it. |
| parish | `/de/<country>/<section>/<parish>/` | The parish's description, a WKT `POINT (lon lat)` for its own map, and a table of registers (see below). |
| register | `/de/<country>/<section>/<parish>/<signature>/` | The register's info panel and the viewer's settings (see below). |
| search | `/de/suchen/?place=...&diocese=...` | See [Search](#search). |

The section slug in the map-features address is the section's own slug
(`passau`, `salzburg`), without the country.

## Parish pages

- Header: `<h3 id="register-header">Matriken (1784 - 1938) <small>8
  gesamt</small></h3>`: the span and the number of registers.
- Each register is two rows: a summary (`<td nowrap>` links, `<td
  nowrap>` signature, `<td>` title, `<td>` dates) and a collapsed details
  row (`<tr class="collapse" id="details-NNN">`) holding a `<dl>`:
  `Matrikeltyp`, `Beginn Datumsbereich`, `Ende Datumsbereich`, and where
  given `Inhalt`, `Kommentar`, `Lagerungsort`. Dates are written `1. Januar
  1784`.
- The first cell's camera link ("Zum Buch") points to the register page for
  Matricula-hosted registers. In the Landesarchiv Baden-Württemberg's
  section it points to the archive's own permalink
  (`https://www.landesarchiv-bw.de/plink/?f=2-180676`), and the signature is
  the archive's (`LABW, StAL F 901 Bd 812 (1)`).
- Types seen: `Taufen`, `Trauungen`, `Sterben`, `Index - Taufen`, `Index -
  Trauungen`, `Index - Sterben` (Passau, whose titles say `Register Taufen`
  for the indexes); `Sterben - Trauungen` for a combined book (Krimml); and
  in Baden-Württemberg `Taufregister`, `Eheregister`, `Totenregister`,
  `Seelenregister`. The title column can differ from the type (`Taufbuch`
  against `Taufen`).
- The table can be filtered with `?by_type=` and `?year_from=`/`?year_to=`
  query parameters; the server reads the whole table and filters itself.
- Parish pages embed a map tile key for a third-party map service; the
  recorded fixtures replace it with `REDACTED-IN-FIXTURE`.

## Register pages

- The info panel is a Bootstrap modal, `id="register-info"`, whose table
  rows are written without closing tags (`<tr><th>Signatur<td>TFBI`).
  `Pfarre` reads `Krimml | Salzburg: Rk. Erzdiözese Salzburg | Österreich`:
  parish, section, country. `Matrikeltyp` here is the book type (`Taufbuch`),
  where the parish page has `Taufen`.
- The viewer is created by
  `new arc.imageview.MatriculaDocView("document", {...})` with:
  - `"labels"`: one label per page, as the archive named the scans:
    `01-Einband_0001`, `02-Taufe_0001`, ..., `05-Index-Taufe_0025` (Krimml
    TFBI, 122 pages), or `001-03_0002-r`, `001-03_0002-v` by folio and side
    (Aholming 001_03, 80 pages);
  - `"files"`: one `/image/<base64>/` path per page, the base64 encoding an
    address on `hosted-images.matricula-online.eu` (plain http), which the
    server never contacts;
  - `"path": "https://img.data.matricula-online.eu"`, the image host.
- **A page is opened in the viewer by `?pg=N`**, 1-based. The viewer reads
  `pg` from the query when it loads (and writes it back as the reader turns
  pages), clamped to the page count. The server builds these links for a
  person to open and never requests them.
- The share dialog says ICARUS cannot guarantee that such links last, advises
  against storing many, and gives the hierarchy to find a document again:
  diocese or archive, parish, register signature, page or folio.
- A register Matricula shows no images for answers its load-error dialog:
  images withheld for legal reasons, or not found.

## Images

- `img.data.matricula-online.eu/image/<...>/` answered **403** to a scripted
  request in a survey made for a sibling project in October 2026, with
  `Vary: Origin`. `data.matricula-online.eu/image/<...>/` redirects to
  `/de/image/<...>/`, which is a 404.
- The viewer's script adds a query string to every image request, built in
  the browser from the session cookie and a signature computed from it.
  That is an access control. This project did not request any image, did
  not test which headers the host accepts, and does not reproduce the
  signature; the image tool is off until ICARUS grants access (see the
  README).

## Search

- `GET /de/suchen/?place=<words>&diocese=<id>` with, optionally,
  `date_filter=on&date_range=<from>,<to>`. `diocese` is a numeric id from
  the form's own list (Passau is 1, Salzburg 9); empty searches everywhere.
  The server always sends it empty and filters by section itself.
- Every result is on one page: 93 for `Kirchberg`, 37 for `Altenmarkt`,
  each a link to a parish with the parish's name, a snippet of its
  description with the matched word in `<mark>`, and `Country • Section`.
  The count is stated as `37 Ergebnisse`; no result is `Suche nicht
  erfolgreich`.
- It matches whole words in parish names and descriptions: `Gastein` with
  1700–1800 found Bad Gastein only, not Dorfgastein or Bad Hofgastein.
  Descriptions often list the villages a parish served ("Ortschaften in der
  Pfarrei"), which is what makes the search useful.
- Answers took 0.7 to 1.4 seconds.

## Terms and robots.txt

- Terms of use, `/de/nutzungsbedingungen/` (German), read 2026-10-11:
  images CC BY-NC-ND 2.0, no commercial reuse; data only as each state's
  civil-status and data-protection law allows; registers with protected data
  not shown (in Austria baptisms for 100 years, marriages and deaths to
  1938); users undertake to inform the archive or diocese of any publication
  using the data or images, with a copy for substantial print use and a link
  for online use. Nothing on automated access.
- `robots.txt`, served from `cdn-static.matricula-online.eu/static/robots.txt`
  (the site's own address redirects there): GPTBot, Amazonbot, ClaudeBot,
  CCBot, Bytespider, meta-externalagent, Google-Extended, Applebot-Extended
  and several SEO crawlers `Disallow: /`; every other agent `Disallow:` for
  `/*?pg=`, `/*/suchen`, `/*/landkarte-features` and `/*/accounts`.
