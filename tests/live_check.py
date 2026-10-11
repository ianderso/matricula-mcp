"""Ask the live site what the recorded pages cannot. Run by hand.

    uv run python -m tests.live_check

About ten requests to Matricula's catalogue pages, paced by the client itself
(one at a time, two seconds apart) and one place search. They check that the
tools still read the pages they were built against: the holdings and a
country page, the diocese of Passau's parish list and map features, Krimml's
registers and its first baptism book, an Aholming baptism book labelled by
folio, a Baden-Württemberg parish whose registers are shown elsewhere, a
place search, and an unknown register.

It never calls Matricula's image host. Image access is forced off whatever
the environment says, and the check that the image tool answers with the
viewer link also checks that no request went to that host.

It is not a test module: pytest does not collect it, and CI never runs it,
because the suite must never depend on someone else's server being up. The
cache is a temporary directory, so every page is fetched afresh.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from matricula_mcp import server
from matricula_mcp.client import IMAGE_HOST, MatriculaHttp
from matricula_mcp.config import load_config

KRIMML = "oesterreich/salzburg/krimml"
KRIMML_TFBI = f"{KRIMML}/TFBI"
AHOLMING_001_03 = "deutschland/passau/aholming/001_03"

#: (tool, arguments, check, what the check means).
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "matricula_sections",
        {"country": "oesterreich"},
        lambda r: any(
            s["section"] == "oesterreich/salzburg" and s["parishes"] > 100
            for s in r["countries"][0]["sections"]
        ),
        "the holdings and Austria's page list the archdiocese of Salzburg",
    ),
    (
        "matricula_parishes",
        {"section": "deutschland/passau", "query": "aholming"},
        lambda r: (
            r["total"] > 250
            and r["parishes"][0]["parish"] == "deutschland/passau/aholming"
            and 48.5 < r["parishes"][0]["lat"] < 49
        ),
        "Passau's parish list and map features: Aholming, with its point",
    ),
    (
        "matricula_registers",
        {"parish": KRIMML},
        lambda r: (
            any(
                x.get("register") == KRIMML_TFBI and x["kind"] == "baptisms" for x in r["registers"]
            )
            and 47 < r["lat"] < 48
        ),
        "Krimml's register table, with TFBI as a baptism book, and the parish's point",
    ),
    (
        "matricula_register",
        {"register": KRIMML_TFBI, "count": 3},
        lambda r: r["total_pages"] == 122 and r["pages"][2]["label"] == "02-Taufe_0001",
        "TFBI's viewer settings: 122 pages, page 3 labelled 02-Taufe_0001",
    ),
    (
        "matricula_register",
        {"register": AHOLMING_001_03, "count": 1},
        lambda r: r["pages"][0]["label"] == "001-03_0002-r" and r.get("held_at") == "ABP",
        "a Passau book labelled by folio, with where the original is held",
    ),
    (
        "matricula_registers",
        {"parish": "deutschland/baden_wuerttemberg/bw-17317"},
        lambda r: (
            r["registers"]
            and r["registers"][0]
            .get("hosted_elsewhere", "")
            .startswith("https://www.landesarchiv-bw.de/plink/")
        ),
        "the Landesarchiv Baden-Württemberg's registers still link to its permalinks",
    ),
    (
        "matricula_search",
        {"place": "Altenmarkt", "section": "oesterreich/gurk"},
        lambda r: r["total"] > 10 and r["in_section"] >= 1,
        "the place search answers, and finds Altenmarkt in the diocese of Gurk",
    ),
    (
        "matricula_page_image",
        {"register": KRIMML_TFBI, "page": 3},
        lambda r: (
            r["error"] == "images_not_enabled"
            and r["label"] == "02-Taufe_0001"
            and r["viewer_url"].endswith("/TFBI/?pg=3")
        ),
        "with image access off, the image tool answers with the viewer link",
    ),
    (
        "matricula_register",
        {"register": f"{KRIMML}/NOSUCH"},
        lambda r: r["error"] == "not_found",
        "an unknown register is a 404, reported as not_found",
    ),
]

#: Checks whose expected answer is an error envelope.
REFUSALS = {
    "with image access off, the image tool answers with the viewer link",
    "an unknown register is a 404, reported as not_found",
}


async def main() -> int:
    cfg = dataclasses.replace(load_config(), image_access=False)
    failed = 0
    with tempfile.TemporaryDirectory() as cache:
        http = MatriculaHttp(
            Path(cache),
            timeout=cfg.timeout,
            min_interval=cfg.min_interval,
            search_interval=cfg.search_interval,
            contact=cfg.contact,
            image_access=False,
        )
        server.runtime.config = cfg
        server.runtime.http = http
        for tool, args, check, meaning in CHECKS:
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            try:
                ok = ("error" not in result or meaning in REFUSALS) and bool(check(result))
            except (KeyError, IndexError, TypeError):
                ok = False
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result, ensure_ascii=False)[:400]}")
        untouched = IMAGE_HOST not in http.hosts_called
        failed += not untouched
        print(f"{'PASS' if untouched else 'FAIL'}  the image host was never called")
        print(
            f"\n{http.live_calls} requests ({http.searches} search) to "
            f"{', '.join(sorted(http.hosts_called))}"
        )
        await http.aclose()
    total = len(CHECKS) + 1
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
