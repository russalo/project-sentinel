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


@pytest.mark.parametrize("bad", [0, 12345, b"bytes.token", [], {}, object(), 3.14])
def test_non_string_token_is_false_not_typeerror(bad):
    # The docstring guarantees "never raises". A non-str token (None already
    # covered above, plus ints/bytes/lists/etc. that callers might mishandle)
    # must surface as False, not a TypeError on the first str method.
    # (gemini-medium on PR #125.)
    assert world_token.verify(bad, WID, secret=SECRET) is False


def test_mint_rejects_non_uuid_world_id():
    with pytest.raises(ValueError):
        world_token.mint("not-a-uuid", secret=SECRET, ttl_seconds=10)


def test_non_canonical_world_id_spelling_verifies():
    # A token minted for the canonical id must verify against any spelling of
    # the same UUID (uppercase, braces) — mint/verify both canonicalize.
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token, WID.upper(), secret=SECRET) is True
    assert world_token.verify(token, "{" + WID + "}", secret=SECRET) is True


def test_verify_non_uuid_world_id_is_false():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(token, "not-a-uuid", secret=SECRET) is False


# ── Per-tester (username-bound) tokens ─────────────────────────────────
#
# A username-bound token verifies only against the same world AND the same
# username. The wire format is a third dot-separated segment; the HMAC payload
# is a distinct shape so an empty-string username fallback cannot accidentally
# recover the legacy HMAC.


def test_username_bound_mint_verify_roundtrip():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    assert world_token.verify(token, WID, secret=SECRET) is True


def test_username_bound_token_has_three_part_wire_format():
    # Wire shape is "<expiry>.<username>.<mac>" — distinguishable from the
    # legacy two-part shape just by counting top-level dots when the username
    # contains none.
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    parts = token.split(".")
    assert len(parts) == 3
    assert parts[1] == "russell"


def test_username_bound_for_one_user_rejected_for_another():
    # The MAC binds to the username — handing the same token to a different
    # caller can't be verified as theirs (verify recomputes against the
    # username embedded in the wire, so this isn't an "X tries Y's username"
    # case; the relevant test is a forged wire below).
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    # Forge a token: same MAC but a different middle field. The recomputed MAC
    # changes because the HMAC payload includes the username.
    expiry_str, _user, sig = token.split(".")
    forged = f"{expiry_str}.johnny.{sig}"
    assert world_token.verify(forged, WID, secret=SECRET) is False


def test_legacy_token_still_verifies_after_username_feature():
    # The critical compat case: a token minted by code that predates the
    # username binding must keep verifying through its TTL. This is the
    # gemini-medium fix from PR #117 — without it every pre-deploy token would
    # invalidate at the cutover, locking every active tester out for 7 days.
    legacy = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    assert world_token.verify(legacy, WID, secret=SECRET) is True


def test_username_with_dots_survives_round_trip():
    # Usernames are free-form text (Russell 2026-06-08), so they can contain
    # dots — e.g. "first.last", "alpha.tester.3", an email-like handle. The
    # parser peels MAC and expiry from the outside; whatever is left in the
    # middle is the username, dots and all.
    token = world_token.mint(
        WID, secret=SECRET, ttl_seconds=3600, username="first.last.3"
    )
    assert token.count(".") >= 3  # at least expiry, user-parts, mac
    assert world_token.verify(token, WID, secret=SECRET) is True


def test_empty_username_in_three_part_wire_format_rejected():
    # An empty middle (``"<expiry>..<mac>"``) was the codex P2 footgun the
    # earlier spec tripped on. We never mint it, but verify must also refuse
    # to accept it — an attacker forging this shape against a known legacy
    # token must not validate.
    legacy = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    expiry_str, sig = legacy.split(".")
    bad = f"{expiry_str}..{sig}"
    assert world_token.verify(bad, WID, secret=SECRET) is False


def test_username_bound_token_for_wrong_world_rejected():
    # Same property as the legacy world-binding test — bound tokens still
    # bind to the world.
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    assert world_token.verify(token, OTHER_WID, secret=SECRET) is False


def test_username_bound_token_with_wrong_secret_rejected():
    token = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    assert world_token.verify(token, WID, secret="a-different-secret") is False


def test_username_bound_expired_token_rejected():
    token = world_token.mint(
        WID, secret=SECRET, ttl_seconds=10, username="russell", _now=1000
    )
    assert world_token.verify(token, WID, secret=SECRET, _now=1005) is True
    assert world_token.verify(token, WID, secret=SECRET, _now=2000) is False


def test_swapping_legacy_and_new_macs_rejected():
    # A new-shape wire whose MAC was computed without the username (and vice
    # versa) must not verify — the two HMAC payload shapes are not
    # interchangeable. This guards against a regression where _sign() drops
    # the username branch or falls back to empty-string concatenation.
    legacy = world_token.mint(WID, secret=SECRET, ttl_seconds=3600)
    bound = world_token.mint(WID, secret=SECRET, ttl_seconds=3600, username="russell")
    legacy_expiry, legacy_sig = legacy.split(".")
    bound_expiry, bound_user, bound_sig = bound.split(".")
    # Take the legacy MAC and try to pass it off as a username-bound token.
    forged_to_bound = f"{legacy_expiry}.russell.{legacy_sig}"
    assert world_token.verify(forged_to_bound, WID, secret=SECRET) is False
    # And the inverse: take the bound MAC and try to pass it off as a legacy
    # token (drops the username from the wire).
    forged_to_legacy = f"{bound_expiry}.{bound_sig}"
    assert world_token.verify(forged_to_legacy, WID, secret=SECRET) is False
