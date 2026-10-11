"""The HTTP client: pacing, caching, retries, redirects and what it sends."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from matricula_mcp import __version__
from matricula_mcp.client import (
    IMAGE_HOST,
    SITE_HOST,
    HostNotAllowed,
    ImagesNotEnabled,
    MatError,
    MatriculaHttp,
    user_agent,
)

from .conftest import JPEG, KRIMML, fixture, make_http

PARISH_PATH = f"/de/{KRIMML}/"


class Clock:
    """A clock that only moves when the client sleeps, recording each wait."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(round(seconds, 3))
        self.now += seconds


def paced(tmp_path, clock: Clock, **kwargs) -> MatriculaHttp:
    options = {"min_interval": 2.0, "search_interval": 10.0, "backoff": 0.0}
    options.update(kwargs)
    return MatriculaHttp(tmp_path / "cache", clock=clock, sleep=clock.sleep, **options)


@pytest.fixture
def router():
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as r:
        yield r


def test_the_user_agent_names_the_project_and_the_operator():
    assert (
        user_agent() == f"matricula-mcp/{__version__} (+https://github.com/ianderso/matricula-mcp)"
    )
    assert user_agent("me@example.org").endswith("; me@example.org)")


async def test_requests_are_two_seconds_apart(tmp_path, router):
    router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="<html/>"))
    clock = Clock()
    http = paced(tmp_path, clock)
    for n in range(3):
        await http.get_page(f"/de/a{n}/", ttl_days=1)
    assert clock.waits == [2.0, 2.0]
    await http.aclose()


async def test_searches_are_ten_seconds_apart_and_pages_between_them_still_two(tmp_path, router):
    router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="<html/>"))
    clock = Clock()
    http = paced(tmp_path, clock)
    await http.get_page("/de/suchen/?place=a", ttl_days=1, search=True)
    await http.get_page("/de/x/", ttl_days=1)
    await http.get_page("/de/suchen/?place=b", ttl_days=1, search=True)
    assert clock.waits == [2.0, 8.0]
    assert http.searches == 2 and http.live_calls == 3
    await http.aclose()


async def test_concurrent_calls_still_go_one_at_a_time(tmp_path, router):
    active, peak = 0, 0

    async def slow(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, text="<html/>")

    router.get(host=SITE_HOST).mock(side_effect=slow)
    http = make_http(tmp_path)
    await asyncio.gather(*(http.get_page(f"/de/p{n}/", ttl_days=1) for n in range(5)))
    assert peak == 1
    await http.aclose()


async def test_identical_calls_in_flight_share_one_request(tmp_path, router):
    async def slow(request):
        await asyncio.sleep(0.01)
        return httpx.Response(200, text="<html/>")

    route = router.get(host=SITE_HOST).mock(side_effect=slow)
    http = make_http(tmp_path)
    await asyncio.gather(*(http.get_page(PARISH_PATH, ttl_days=1) for _ in range(4)))
    assert route.call_count == 1 and http.shared_waits == 3
    await http.aclose()


async def test_an_answer_is_cached_for_its_days_and_refresh_asks_again(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="<html/>"))
    http = make_http(tmp_path)
    await http.get_page(PARISH_PATH, ttl_days=7)
    await http.get_page(PARISH_PATH, ttl_days=7)
    assert route.call_count == 1 and http.cache_hits == 1
    await http.get_page(PARISH_PATH, ttl_days=7, refresh=True)
    assert route.call_count == 2
    await http.get_page(PARISH_PATH, ttl_days=0)  # expired at once
    assert route.call_count == 3
    await http.aclose()


async def test_a_failure_is_never_cached(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(
        side_effect=[httpx.Response(404, text="gone"), httpx.Response(200, text="<html/>")]
    )
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=7)
    assert caught.value.code == "not_found"
    assert await http.get_page(PARISH_PATH, ttl_days=7) == "<html/>"
    assert route.call_count == 2
    await http.aclose()


async def test_an_unreadable_cache_entry_is_fetched_again(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="<html/>"))
    http = make_http(tmp_path)
    await http.get_page(PARISH_PATH, ttl_days=7)
    for entry in (tmp_path / "cache").glob("*.json"):
        entry.write_text("{not json")
    await http.get_page(PARISH_PATH, ttl_days=7)
    assert route.call_count == 2
    await http.aclose()


async def test_json_is_cached_as_data(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(
        return_value=httpx.Response(200, json=fixture("features_passau.json"))
    )
    http = make_http(tmp_path)
    path = "/de/landkarte-features/diocese/passau/"
    first = await http.get_json(path, ttl_days=28)
    assert await http.get_json(path, ttl_days=28) == first
    assert route.call_count == 1
    assert route.calls[0].request.headers["accept"] == "application/json"
    await http.aclose()


async def test_json_that_is_not_json_is_named(tmp_path, router):
    router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="<html/>"))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_json("/de/landkarte-features/diocese/x/", ttl_days=1)
    assert caught.value.code == "not_json"
    await http.aclose()


@pytest.mark.parametrize("status", [500, 502, 503, 429])
async def test_a_5xx_or_429_is_retried_once(tmp_path, router, status):
    route = router.get(host=SITE_HOST).mock(
        side_effect=[httpx.Response(status), httpx.Response(200, text="<html/>")]
    )
    http = make_http(tmp_path)
    assert await http.get_page(PARISH_PATH, ttl_days=1) == "<html/>"
    assert route.call_count == 2
    await http.aclose()


async def test_retry_after_is_honoured_up_to_thirty_seconds(tmp_path, router):
    router.get(host=SITE_HOST).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "120"}),
            httpx.Response(200, text="<html/>"),
        ]
    )
    clock = Clock()
    http = paced(tmp_path, clock, min_interval=0.0)
    await http.get_page(PARISH_PATH, ttl_days=1)
    assert clock.waits == [30.0]
    await http.aclose()


async def test_a_second_failure_is_reported(tmp_path, router):
    router.get(host=SITE_HOST).mock(return_value=httpx.Response(503))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.status == 503 and http.last_error["status"] == 503
    await http.aclose()


async def test_a_refusal_is_not_retried(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(return_value=httpx.Response(403))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "refused" and route.call_count == 1
    await http.aclose()


async def test_a_dropped_connection_is_retried_and_then_named(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(side_effect=httpx.ConnectError("reset"))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "no_response" and route.call_count == 2
    await http.aclose()


async def test_a_timeout_is_not_retried(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(side_effect=httpx.ReadTimeout("slow"))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "timeout" and route.call_count == 1
    await http.aclose()


async def test_a_bot_check_is_named(tmp_path, router):
    router.get(host=SITE_HOST).mock(
        return_value=httpx.Response(403, headers={"cf-mitigated": "challenge"})
    )
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "challenge"
    await http.aclose()


async def test_a_redirect_on_the_site_is_followed(tmp_path, router):
    router.get(host=SITE_HOST, path="/de/old/").mock(
        return_value=httpx.Response(301, headers={"location": "/de/new/"})
    )
    router.get(host=SITE_HOST, path="/de/new/").mock(
        return_value=httpx.Response(200, text="moved here")
    )
    http = make_http(tmp_path)
    assert await http.get_page("/de/old/", ttl_days=1) == "moved here"
    await http.aclose()


async def test_a_redirect_to_another_host_is_reported_and_not_followed(tmp_path, router):
    router.get(host=SITE_HOST).mock(
        return_value=httpx.Response(302, headers={"location": "https://elsewhere.example/x"})
    )
    elsewhere = router.get(host="elsewhere.example").mock(return_value=httpx.Response(200))
    http = make_http(tmp_path)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "redirected" and elsewhere.call_count == 0
    await http.aclose()


async def test_a_redirect_to_the_image_host_is_not_followed_either(tmp_path, router):
    router.get(host=SITE_HOST).mock(
        return_value=httpx.Response(302, headers={"location": f"https://{IMAGE_HOST}/image/x/"})
    )
    images = router.get(host=IMAGE_HOST).mock(return_value=httpx.Response(200, content=JPEG))
    http = make_http(tmp_path, image_access=True)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "redirected" and images.call_count == 0
    await http.aclose()


async def test_only_the_user_agent_and_accept_are_sent(tmp_path, router):
    route = router.get(host=SITE_HOST).mock(
        return_value=httpx.Response(
            200,
            text="<html/>",
            headers={"set-cookie": "shared_csrftoken=abc; Domain=.data.matricula-online.eu"},
        )
    )
    http = make_http(tmp_path, contact="me@example.org")
    await http.get_page("/de/a/", ttl_days=1)
    await http.get_page("/de/b/", ttl_days=1)
    sent = route.calls[1].request.headers
    assert sent["user-agent"] == user_agent("me@example.org")
    assert sent["accept"] == "text/html"
    for header in ("origin", "referer", "cookie", "x-requested-with"):
        assert header not in sent, header
    await http.aclose()


async def test_a_page_over_the_cap_is_refused_and_not_cached(tmp_path, router):
    router.get(host=SITE_HOST).mock(return_value=httpx.Response(200, text="x" * 5_000))
    http = make_http(tmp_path, max_page_bytes=1_000)
    with pytest.raises(MatError) as caught:
        await http.get_page(PARISH_PATH, ttl_days=1)
    assert caught.value.code == "too_large"
    assert list((tmp_path / "cache").glob("*.json")) == []
    await http.aclose()


async def test_any_other_host_is_refused_before_a_request(tmp_path, router):
    elsewhere = router.route().mock(return_value=httpx.Response(200))
    http = make_http(tmp_path)
    with pytest.raises(HostNotAllowed):
        await http._http.get("https://attacker.example/")
    with pytest.raises(HostNotAllowed):
        await http._http.get(f"http://{SITE_HOST}/de/")
    assert elsewhere.call_count == 0
    await http.aclose()


async def test_the_image_host_is_refused_while_image_access_is_off(tmp_path, router):
    images = router.route(host=IMAGE_HOST).mock(return_value=httpx.Response(200, content=JPEG))
    http = make_http(tmp_path)
    with pytest.raises(ImagesNotEnabled):
        await http._http.get(f"https://{IMAGE_HOST}/image/abc/")
    with pytest.raises(ImagesNotEnabled):
        await http.download_image("/image/aHR0cDovL2V4YW1wbGU=/", tmp_path / "p.jpg")
    assert images.call_count == 0 and not (tmp_path / "p.jpg").exists()
    await http.aclose()


async def test_an_image_path_must_be_one_a_register_page_names(tmp_path, router):
    images = router.route(host=IMAGE_HOST).mock(return_value=httpx.Response(200, content=JPEG))
    http = make_http(tmp_path, image_access=True)
    for path in ("/../etc/passwd", "/image/x/../../", "https://elsewhere.example/a.jpg"):
        with pytest.raises(MatError) as caught:
            await http.download_image(path, tmp_path / "p.jpg")
        assert caught.value.code == "bad_image_path"
    assert images.call_count == 0
    await http.aclose()


def test_cache_entries_hold_the_answer_and_when_it_was_stored(tmp_path):
    http = make_http(tmp_path)
    http._cache_put("k", "<html/>")
    entry = json.loads((tmp_path / "cache" / "k.json").read_text())
    assert entry["data"] == "<html/>" and isinstance(entry["stored"], float)
