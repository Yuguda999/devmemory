"""HD receiving-address derivation for Cardano payments.

Each invoice gets a fresh receiving address derived from the merchant wallet's
CIP-1852 *account* public key (``acct_xvk1...``, exported once from Lace/Eternl).
Because the account key is public and soft-derivation (chain/index) needs no
private key, the server can generate unlimited base addresses that all belong to
the merchant's wallet — letting each invoice be a clean round amount to a unique
address (no odd-amount matching).

``bip_utils`` is an optional dependency (the ``cardano`` extra); it is imported
lazily so the MCP client, which never derives addresses, does not need it.
"""

from __future__ import annotations

from functools import lru_cache


class CardanoHDError(RuntimeError):
    """Raised when address derivation is misconfigured or unavailable."""


def _testnet(network: str) -> bool:
    return network.lower().strip() != "mainnet"


@lru_cache(maxsize=8)
def _account_context(account_xpub: str, network: str):
    """Build a CardanoShelley account context from a CIP-5 account public key.

    Cached per (xpub, network) since decoding + object construction is pure and
    repeated on every invoice.
    """
    try:
        from bip_utils import (
            Bech32Decoder,
            Cip1852,
            Cip1852Coins,
        )
        from bip_utils.bip.bip32 import Bip32KholawEd25519
        from bip_utils.bip.bip32.bip32_key_data import (
            Bip32ChainCode,
            Bip32Depth,
            Bip32FingerPrint,
            Bip32KeyData,
            Bip32KeyIndex,
        )
        from bip_utils.cardano.cip1852.conf import Cip1852ConfGetter
    except ImportError as exc:  # pragma: no cover - import guard
        raise CardanoHDError(
            "Cardano address derivation needs the 'cardano' extra: "
            "pip install 'devmemory-ai[cardano]'"
        ) from exc

    try:
        data = Bech32Decoder.Decode("acct_xvk", account_xpub)
    except Exception as exc:
        raise CardanoHDError(
            "Invalid cardano_account_xpub — expected a CIP-5 account public key "
            "starting with 'acct_xvk1'."
        ) from exc
    if len(data) != 64:
        raise CardanoHDError(
            f"Decoded account key is {len(data)} bytes, expected 64 (32 pubkey + 32 chain code)."
        )

    pub32, chain_code = data[:32], data[32:]
    key_data = Bip32KeyData(
        chain_code=Bip32ChainCode(chain_code),
        depth=Bip32Depth(3),  # m/1852'/1815'/account' — account level
        index=Bip32KeyIndex(0x80000000),
        parent_fprint=Bip32FingerPrint(),
    )
    # bip_utils expects the 33-byte compressed form (0x00 prefix + 32-byte pubkey).
    bip32 = Bip32KholawEd25519.FromPublicKey(b"\x00" + pub32, key_data)
    coin = (
        Cip1852Coins.CARDANO_ICARUS_TESTNET
        if _testnet(network)
        else Cip1852Coins.CARDANO_ICARUS
    )
    return Cip1852(bip32, Cip1852ConfGetter.GetConfig(coin))


def derive_address(account_xpub: str, index: int, network: str) -> str:
    """Derive the external-chain base address at ``index`` for the account key.

    Args:
        account_xpub: CIP-5 account public key (``acct_xvk1...``).
        index: External-chain address index (0, 1, 2, …) — one per invoice.
        network: ``mainnet`` | ``preprod`` | ``preview``.

    Returns:
        A bech32 payment address (``addr1...`` on mainnet, ``addr_test1...`` on testnets).
    """
    from bip_utils import Bip44Changes, CardanoShelley

    acct = _account_context(account_xpub, network)
    return (
        CardanoShelley.FromCip1852Object(acct)
        .Change(Bip44Changes.CHAIN_EXT)
        .AddressIndex(index)
        .PublicKeys()
        .ToAddress()
    )
