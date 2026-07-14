"""Unit tests for the Blockfrost-backed Cardano payment detection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from devmemory.billing import cardano
from devmemory.billing.cardano import (
    CardanoConfigError,
    ada_to_lovelace,
    find_matching_payment,
    lovelace_to_ada,
)


def test_ada_lovelace_roundtrip():
    assert ada_to_lovelace(1) == 1_000_000
    assert ada_to_lovelace(10.5) == 10_500_000
    assert lovelace_to_ada(1_000_000) == 1.0
    assert lovelace_to_ada(10_500_001) == 10.500001


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal async httpx.AsyncClient stand-in keyed by URL substring."""

    def __init__(self, routes):
        self._routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **_):
        for needle, resp in self._routes.items():
            if needle in url:
                return resp
        return _FakeResp(404, {})


def _with_client(routes):
    return patch.object(cardano.httpx, "AsyncClient", lambda *a, **k: _FakeClient(routes))


ADDR = "addr_test1qxyz"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    monkeypatch.setattr(cardano.settings, "blockfrost_project_id", "preprodTEST")
    monkeypatch.setattr(cardano.settings, "blockfrost_network", "preprod")


async def test_match_found():
    routes = {
        f"/addresses/{ADDR}/transactions": _FakeResp(200, [{"tx_hash": "tx123"}]),
        "/txs/tx123/utxos": _FakeResp(
            200,
            {"outputs": [{"address": ADDR, "amount": [{"unit": "lovelace", "quantity": "10500000"}]}]},
        ),
    }
    with _with_client(routes):
        assert await find_matching_payment(ADDR, 10_500_000) == "tx123"


async def test_no_match_wrong_amount():
    routes = {
        f"/addresses/{ADDR}/transactions": _FakeResp(200, [{"tx_hash": "tx123"}]),
        "/txs/tx123/utxos": _FakeResp(
            200,
            {"outputs": [{"address": ADDR, "amount": [{"unit": "lovelace", "quantity": "9000000"}]}]},
        ),
    }
    with _with_client(routes):
        assert await find_matching_payment(ADDR, 10_500_000) is None


async def test_ignores_outputs_to_other_addresses():
    routes = {
        f"/addresses/{ADDR}/transactions": _FakeResp(200, [{"tx_hash": "tx123"}]),
        "/txs/tx123/utxos": _FakeResp(
            200,
            {
                "outputs": [
                    {"address": "addr_other", "amount": [{"unit": "lovelace", "quantity": "10500000"}]},
                    {"address": ADDR, "amount": [{"unit": "lovelace", "quantity": "500000"}]},
                ]
            },
        ),
    }
    with _with_client(routes):
        # Only 500000 went to ADDR — no match for 10.5 ADA.
        assert await find_matching_payment(ADDR, 10_500_000) is None
        # ...but it does match the real 0.5 ADA delivered.
        assert await find_matching_payment(ADDR, 500_000) == "tx123"


async def test_unknown_address_returns_none():
    routes = {f"/addresses/{ADDR}/transactions": _FakeResp(404, {})}
    with _with_client(routes):
        assert await find_matching_payment(ADDR, 10_500_000) is None


async def test_missing_project_id_raises(monkeypatch):
    monkeypatch.setattr(cardano.settings, "blockfrost_project_id", None)
    with pytest.raises(CardanoConfigError):
        await find_matching_payment(ADDR, 1)
