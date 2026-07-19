"""Cardano payment detection via Blockfrost.

Talks to the Blockfrost REST API directly over httpx (already a dependency) —
no Cardano node and no extra SDK. The only operation needed for a pull-model
payment flow is: "did address X receive exactly N lovelace?". We answer it by
listing recent transactions touching the address and summing the lovelace each
one delivered *to* that address.

1 ADA = 1_000_000 lovelace.
"""

from __future__ import annotations

import httpx

from devmemory.config import settings

LOVELACE_PER_ADA = 1_000_000


class CardanoConfigError(RuntimeError):
    """Raised when Cardano payments are called on but not configured."""


class BlockfrostError(RuntimeError):
    """Raised when Blockfrost returns an unexpected error."""


def ada_to_lovelace(ada: float) -> int:
    """Convert an ADA amount to integer lovelace."""
    return int(round(ada * LOVELACE_PER_ADA))


def lovelace_to_ada(lovelace: int) -> float:
    """Convert integer lovelace to an ADA amount."""
    return lovelace / LOVELACE_PER_ADA


def _headers() -> dict[str, str]:
    if not settings.blockfrost_project_id:
        raise CardanoConfigError("BLOCKFROST_PROJECT_ID is not set")
    return {"project_id": settings.blockfrost_project_id}


async def find_matching_payment(
    address: str,
    expected_lovelace: int,
    *,
    scan_count: int = 25,
) -> str | None:
    """Return the tx hash that delivered exactly ``expected_lovelace`` to ``address``.

    Scans the most recent ``scan_count`` transactions touching ``address``. For
    each, sums the lovelace sent to ``address`` across its outputs and compares
    to the expected amount. Returns the first matching transaction hash, or
    ``None`` if no confirmed payment matches yet.

    Raises:
        CardanoConfigError: If Blockfrost is not configured.
        BlockfrostError: On an unexpected Blockfrost API failure.
    """
    base = settings.blockfrost_base_url
    headers = _headers()

    async with httpx.AsyncClient(timeout=20.0) as client:
        tx_resp = await client.get(
            f"{base}/addresses/{address}/transactions",
            headers=headers,
            params={"order": "desc", "count": scan_count},
        )
        # A brand-new address Blockfrost has never seen returns 404 — that just
        # means "no payments yet", not an error.
        if tx_resp.status_code == 404:
            return None
        if tx_resp.status_code != 200:
            raise BlockfrostError(
                f"Blockfrost address txs {tx_resp.status_code}: {tx_resp.text[:200]}"
            )

        for entry in tx_resp.json():
            tx_hash = entry.get("tx_hash")
            if not tx_hash:
                continue
            utxo_resp = await client.get(f"{base}/txs/{tx_hash}/utxos", headers=headers)
            if utxo_resp.status_code != 200:
                # Skip a tx we can't read rather than failing the whole check.
                continue
            received = _lovelace_to_address(utxo_resp.json(), address)
            if received == expected_lovelace:
                return tx_hash

    return None


def _lovelace_to_address(tx_utxos: dict, address: str) -> int:
    """Sum lovelace sent to ``address`` across a transaction's outputs."""
    total = 0
    for output in tx_utxos.get("outputs", []):
        if output.get("address") != address:
            continue
        for amt in output.get("amount", []):
            if amt.get("unit") == "lovelace":
                total += int(amt.get("quantity", 0))
    return total
