"""Tests for HD receiving-address derivation from an account xpub.

The vectors are derived from the standard test mnemonic
"abandon abandon ... about" at m/1852'/1815'/0'.
"""

from __future__ import annotations

import pytest

pytest.importorskip("bip_utils")

from devmemory.billing.cardano_hd import CardanoHDError, derive_address

# Account public key (CIP-5) for the test mnemonic.
ACCT_XVK = (
    "acct_xvk1h6m7wu9n6rcex2c29uaxx2zml8hh60jxr425gmt28yga3u8w2hq"
    "tpcklzefc2zqyveyapek4kv5kj426y0e0r6ljmv5pjdvmpkyt69sv4hxhf"
)
# Expected external-chain base address at index 0 on a testnet.
ADDR0 = (
    "addr_test1qq8ac7qqy0vtulyl7wntmsxc6wex80gvcyjy33qffrhm7s"
    "h927ysx5sftuw0dlft05dz3c7revpf7jx0xnlcjz3g69mqkt5dmn"
)


def test_derive_index0_matches_known_vector():
    assert derive_address(ACCT_XVK, 0, "preprod") == ADDR0


def test_indices_are_distinct():
    a0 = derive_address(ACCT_XVK, 0, "preprod")
    a1 = derive_address(ACCT_XVK, 1, "preprod")
    a2 = derive_address(ACCT_XVK, 2, "preprod")
    assert len({a0, a1, a2}) == 3


def test_derivation_is_deterministic():
    assert derive_address(ACCT_XVK, 5, "preprod") == derive_address(ACCT_XVK, 5, "preprod")


def test_mainnet_uses_addr_prefix():
    addr = derive_address(ACCT_XVK, 0, "mainnet")
    assert addr.startswith("addr1")


def test_preprod_uses_testnet_prefix():
    assert derive_address(ACCT_XVK, 0, "preprod").startswith("addr_test1")


def test_invalid_xpub_raises():
    with pytest.raises(CardanoHDError):
        derive_address("not_a_valid_key", 0, "preprod")
