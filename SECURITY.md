# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/matricula-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its cache
and, when image access is on, the images `matricula_page_image` saves), and
anything a tool argument or a page's content can make it do.

Out of scope: Matricula itself, which this project does not operate. Report
problems with it to ICARUS.

## The security model, briefly

- **No credentials.** Matricula's catalogue pages need none. The server holds
  no key, keeps no cookie, and sends none.
- **Tool arguments are treated as the attacker's.** A model writes them, and
  the model reads parish descriptions, register notes and other sites that
  may carry injected instructions. Everything below is about what such an
  argument can make the server do.
- **Two fixed hosts.** A request hook refuses anything but https to
  `data.matricula-online.eu`, including an address taken from a page.
  `img.data.matricula-online.eu` is refused as well unless the operator has
  set `MATRICULA_IMAGE_ACCESS=granted`, which a model cannot change.
- **Keys are checked before any request.** A section, parish or register key
  must have the right number of parts, each from the alphabet Matricula's
  slugs use (letters, digits, `_ . ~ -`); a pasted address must be on
  `data.matricula-online.eu`. A `..`, another host or a stray character is
  refused before anything is looked up.
- **Public addresses only, checked at connect time.** The transport resolves
  each host itself, refuses the connection if any address is private,
  loopback, link-local, shared (CGNAT), multicast, reserved, unspecified or
  site-local, in IPv4 or IPv6 (an IPv4-mapped, 6to4 or NAT64 address is
  judged by the IPv4 address inside it), and connects to the address it
  checked. A redirect or a retry is a new connection, checked again, so DNS
  rebinding gains nothing. Proxy settings in the environment are not used.
- **Redirects are followed by hand,** and only on the same host. A redirect
  anywhere else is reported to the caller and not followed.
- **Bounded answers.** A page or JSON answer over 8 MB, or an image over
  60 MB, is refused as it streams in, whether or not its size was declared.
- **An image path is checked twice.** It must have the shape a register page
  gives (`/image/<base64>/`), and the register page must name the expected
  image host; otherwise nothing is fetched.
- **Local writes.** The cache lives under `MATRICULA_CACHE_DIR`, in files
  named by a hash of the request address and written atomically. The image
  tool writes only when image access is on, only the absolute path it is
  given, and only if that path, with its links resolved, ends in `.jpg` or
  `.jpeg`, has no hidden component, is not under `~/Library`, and lies inside
  `MATRICULA_DOWNLOAD_DIR` when that is set (the operator's folder may itself
  be hidden or under `~/Library`; what a model adds below it may not). The
  bytes must be a JPEG by their first bytes. The file is created exclusively
  and removed if writing fails; a refused download writes nothing at all.
- **No disguise.** The client sends its own User-Agent and an `Accept`
  header and nothing else; a test scans the source for browser strings and
  forged `Origin` or `Referer` headers.
- **Site responses carry untrusted text.** Parish descriptions, register
  notes and search snippets are written by archive staff and reach the model
  verbatim, which makes them a channel for prompt injection. The server's
  instructions tell the model to treat that text as material, not as
  instructions, but the model still decides what to do next.
- **`MATRICULA_CONTACT` is checked** for newlines and parentheses before it is
  placed in the User-Agent header.
