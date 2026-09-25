"""
Tessera Phase 1 — Credential Tests

These tests verify the trust model:
  - Valid credentials are accepted with correct tier
  - Forged credentials are rejected
  - Expired credentials are rejected
  - Unknown operators are rejected
  - Revoked operators are rejected
  - Tier capping works (operator can't exceed their max)
  - No credential → anonymous (not identified/verified)
"""
import pytest
import os
import time
from pathlib import Path

from tessera.contract.operator_registry import (
    OperatorRegistry,
    OperatorTier,
    generate_operator_keypair,
)
from tessera.contract.credentials import (
    sign_agent_credential,
    verify_agent_credential,
    VerifiedCredential,
    VerificationError,
)


@pytest.fixture
def registry(tmp_path):
    """Create a fresh operator registry with test operators."""
    reg_path = str(tmp_path / "operators.json")
    reg = OperatorRegistry(reg_path)

    # Register test operators
    priv, pub = generate_operator_keypair()
    reg.register("test-operator", "Test Operator", pub, OperatorTier.VERIFIED)
    # Store private key on the fixture for signing
    reg._test_priv = priv

    priv2, pub2 = generate_operator_keypair()
    reg.register("super-operator", "Super Operator", pub2, OperatorTier.SUPER_AGENT)
    reg._test_priv_super = priv2

    return reg


@pytest.fixture
def unregistered_key():
    """An Ed25519 private key NOT registered with any terminal."""
    priv, _ = generate_operator_keypair()
    return priv


class TestValidCredentials:
    """Test that valid, properly signed credentials are accepted."""

    def test_identified_tier(self, registry):
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "agent-1",
            tier="identified", purpose="browsing",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.derived_tier == "identified"
        assert result.operator_id == "test-operator"
        assert result.agent_name == "agent-1"

    def test_verified_tier(self, registry):
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "agent-2",
            tier="verified", purpose="purchase",
            capabilities={"can_transact": True, "max_transaction": 100.0},
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.derived_tier == "verified"
        assert result.capabilities["can_transact"] is True

    def test_super_agent_with_authorized_operator(self, registry):
        token = sign_agent_credential(
            registry._test_priv_super, "super-operator", "super-agent",
            tier="super_agent", purpose="autonomous",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.derived_tier == "super_agent"
        assert result.was_capped is False


class TestTierCapping:
    """Test that operators cannot issue tiers above their registered max."""

    def test_verified_operator_capped_from_super_agent(self, registry):
        """Operator registered as 'verified' signs 'super_agent' → capped to 'verified'."""
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "ambitious-agent",
            tier="super_agent",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.requested_tier == "super_agent"
        assert result.derived_tier == "verified"  # capped
        assert result.was_capped is True

    def test_below_max_is_not_capped(self, registry):
        """Operator registered as 'super_agent' requesting 'identified' → no cap."""
        token = sign_agent_credential(
            registry._test_priv_super, "super-operator", "humble-agent",
            tier="identified",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.derived_tier == "identified"
        assert result.was_capped is False


class TestRejections:
    """Test that invalid credentials are rejected with correct error codes."""

    def test_unknown_operator(self, registry, unregistered_key):
        token = sign_agent_credential(
            unregistered_key, "unknown-corp", "rogue-agent",
            tier="super_agent",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerificationError)
        assert result.code == "unknown_operator"

    def test_forged_signature(self, registry, unregistered_key):
        """Sign with wrong key but claim to be a known operator."""
        token = sign_agent_credential(
            unregistered_key, "test-operator", "forged-agent",
            tier="super_agent",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerificationError)
        assert result.code == "invalid_signature"

    def test_expired_token(self, registry):
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "old-agent",
            tier="identified", ttl_seconds=-1,
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerificationError)
        assert result.code == "token_expired"

    def test_revoked_operator(self, registry):
        # Sign before revocation
        token = sign_agent_credential(
            registry._test_priv_super, "super-operator", "agent-before-revoke",
            tier="verified",
        )
        # Revoke
        registry.revoke("super-operator", "breach")
        # Verify after revocation → rejected
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerificationError)
        assert result.code == "operator_revoked"

    def test_garbage_token(self, registry):
        result = verify_agent_credential("not-a-jwt", registry)
        assert isinstance(result, VerificationError)
        assert result.code == "invalid_format"

    def test_tampered_payload(self, registry):
        """Sign a valid token, then tamper with the payload."""
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "legit-agent",
            tier="identified",
        )
        # Tamper: change the payload while keeping header and signature
        parts = token.split(".")
        import base64, json
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["tier"] = "super_agent"  # escalate!
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

        result = verify_agent_credential(tampered_token, registry)
        assert isinstance(result, VerificationError)
        assert result.code == "invalid_signature"


class TestEdgeCases:

    def test_no_purpose(self, registry):
        """Missing purpose defaults to 'general'."""
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "minimal-agent",
            tier="identified",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.purpose == "general"

    def test_no_capabilities(self, registry):
        """Missing capabilities defaults to empty dict."""
        token = sign_agent_credential(
            registry._test_priv, "test-operator", "simple-agent",
            tier="identified",
        )
        result = verify_agent_credential(token, registry)
        assert isinstance(result, VerifiedCredential)
        assert result.capabilities == {}

    def test_registry_persistence(self, tmp_path):
        """Registry survives reload from disk."""
        reg_path = str(tmp_path / "persist_test.json")
        reg = OperatorRegistry(reg_path)
        priv, pub = generate_operator_keypair()
        reg.register("persist-op", "Persist", pub, OperatorTier.VERIFIED)

        # Reload
        reg2 = OperatorRegistry(reg_path)
        key = reg2.get_verified_key("persist-op")
        assert key is not None

        # Sign and verify with reloaded registry
        token = sign_agent_credential(priv, "persist-op", "agent", tier="identified")
        result = verify_agent_credential(token, reg2)
        assert isinstance(result, VerifiedCredential)
