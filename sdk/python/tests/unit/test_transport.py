"""Retry delays, circuit breaker state machine, header redaction."""

from __future__ import annotations

import time

import httpx

from syfthub import CircuitBreaker, Retry
from syfthub._transport import Breakers, ErrorDetail, detail_of, host_of, redact
from syfthub._transport.retry import delays, retryable_status


def test_delays_are_bounded_and_counted() -> None:
    r = Retry(attempts=4, backoff=0.5, max_backoff=1.0)
    ds = list(delays(r))
    assert len(ds) == 3 and all(0 <= d <= 1.0 for d in ds)
    assert list(delays(Retry(attempts=1))) == []
    assert retryable_status(503) and not retryable_status(403) and not retryable_status(402)


def test_breaker_opens_then_half_opens_for_one_probe(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    b = Breakers(settings=CircuitBreaker(failures=2, cooldown=10))
    host = host_of("https://erin.space.test/api/v1/endpoints/x/query")
    assert host == "erin.space.test" and not b.is_open(host) and not b.half_open(host)
    b.failure(host)
    assert not b.is_open(host)
    b.failure(host)
    assert b.is_open(host) and b.reopens_at(host) is not None and not b.half_open(host)
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + 11)
    assert not b.is_open(host) and b.half_open(host)
    assert b.half_open(host)  # reading never changes the state
    b.failure(host)  # the probe failed: open again for a full cooldown
    assert b.is_open(host) and not b.half_open(host)
    monkeypatch.setattr(time, "monotonic", lambda: now + 22)
    assert b.half_open(host)
    b.success(host)
    assert not b.is_open(host) and not b.half_open(host)


def test_redact_hides_secrets_only() -> None:
    out = redact(
        {"Authorization": "Bearer x", "X-Payment": "p", "User-Agent": "ua", "www-authenticate": "c"}
    )
    assert out == {
        "Authorization": "<redacted>",
        "X-Payment": "<redacted>",
        "User-Agent": "ua",
        "www-authenticate": "<redacted>",
    }


def test_error_detail_parses_the_three_fastapi_shapes() -> None:
    def resp(json: object = None, text: str | None = None) -> httpx.Response:
        return (
            httpx.Response(400, json=json)
            if json is not None
            else httpx.Response(400, text=text or "")
        )

    assert ErrorDetail.of(resp({"detail": "plain"})) == ErrorDetail(message="plain")
    coded = ErrorDetail.of(resp({"detail": {"code": "INSUFFICIENT_BALANCE", "message": "empty"}}))
    assert coded.code == "INSUFFICIENT_BALANCE" and str(coded) == "INSUFFICIENT_BALANCE: empty"
    assert ErrorDetail.of(resp({"detail": {"code": "X"}})).message == "{'code': 'X'}"
    assert ErrorDetail.of(resp({"detail": [{"msg": "m"}]})).message.startswith("[{")
    assert (
        ErrorDetail.of(resp(text="<html>")).message == "<html>" and detail_of(resp(text="t")) == "t"
    )


def test_http2_is_opt_in() -> None:
    from syfthub import Options
    from syfthub._transport import Transport

    def pool(transport: Transport):  # type: ignore[no-untyped-def]  # httpcore's pool
        return transport._client._transport._pool  # type: ignore[attr-defined]

    assert pool(Transport())._http2 is False
    assert pool(Transport(Options(http2=True)))._http2 is True  # negotiated by ALPN per host
    assert (
        pool(Transport())._keepalive_expiry == 60.0
    )  # a Hub call after a slow fan-out reconnects less


async def test_a_5xx_is_retried_once_and_network_errors_use_the_full_budget() -> None:
    from syfthub import Options
    from syfthub._transport import Transport

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/flaky-server":
            return httpx.Response(503)
        if request.url.path == "/flaky-network" and len(calls) < 3:
            raise httpx.ConnectError("refused")
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    retry = Retry(attempts=3, server_errors=1, backoff=0, max_backoff=0)
    transport = Transport(Options(http_client=client, retry=retry))

    response = await transport.request("GET", "https://x.test/flaky-server")
    assert response.status_code == 503 and calls.count("/flaky-server") == 2  # one retry, not two

    calls.clear()
    response = await transport.request("GET", "https://x.test/flaky-network")
    assert response.status_code == 200 and calls.count("/flaky-network") == 3  # the full budget

    calls.clear()
    no_server_retries = Transport(
        Options(http_client=client, retry=Retry(server_errors=0, backoff=0))
    )
    await no_server_retries.request("GET", "https://x.test/flaky-server")
    assert calls == ["/flaky-server"]
    await client.aclose()
