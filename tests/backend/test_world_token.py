"""Unit tests for the stateless per-world session token (ADR 0003 Slice A).

The token is an HMAC over (world_id, expiry). These assert the security
properties that matter: a token only validates for its own world, only with the
minting secret, only before expiry, and any malformed input is a clean False
(never an exception, so callers map straight to 403).
"""

import pytest

from backend.auth import world_token

SECRET = "unit-test-secret"
WID = "11111111-1111-1111-1111-111111111111"
OTHER_WID = "22222222-2222-2222-2222-222222222222"


def test_mint_verify_roundtrip():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token, WID, secret=SECRET) is True


def test_token_for_one_world_rejected_for_another():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token, OTHER_WID, secret=SECRET) is False


def test_wrong_secret_rejected():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token, WID, secret="a-different-secret") is False


def test_tampered_signature_rejected():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token + "x", WID, secret=SECRET) is False


def test_tampered_expiry_rejected():
    # Extending the expiry without re-signing must fail the MAC.
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=10, _now=1000)
    expiry_str, sig = token.split(".", 1)
    forged = f"{int(expiry_str) + 100000}.{sig}"
    assert world_token.verify(forged, WID, secret=SECRET, _now=1005) is False


def test_expired_token_rejected():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=10, _now=1000)
    assert world_token.verify(token, WID, secret=SECRET, _now=1005) is True
    assert world_token.verify(token, WID, secret=SECRET, _now=2000) is False


@pytest.mark.parametrize("bad", ["", "no-separator", "abc.def", ".", "....", None])
def test_malformed_token_is_false_not_exception(bad):
    assert world_token.verify(bad, WID, secret=SECRET) is False


def test_mint_rejects_non_uuid_world_id():
    with pytest.raises(ValueError):
        world_token.mint("not-a-uuid", secret=SECRET, ttl_seconds=10)
