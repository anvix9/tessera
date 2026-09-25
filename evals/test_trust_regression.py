"""
Tessera Phase 1 — MCP Server Trust Regression Tests

THE critical test: prove that the self-declared trust vulnerability is fixed.

Before Phase 1:
  POST /tools/tessera_connect {"trust_level": "super_agent", "can_transact": true}
  → 200 OK, full autonomous access. ANY agent could do this.

After Phase 1:
  POST /tools/tessera_connect {"credential": "<signed JWT>"}
  → trust derived from verified signature, not from request body.

  POST /tools/tessera_connect {"trust_level": "super_agent"}
  → field doesn't exist, ignored/rejected.
"""
import pytest
import json
import os
from pathlib import Path

from tessera.contract.operator_registry import (
    OperatorRegistry, OperatorTier, generate_operator_keypair,
)
from tessera.contract.credentials import sign_agent_credential
from tessera.mcp.server import create_mcp_server, ConnectRequest


@pytest.fixture
def setup(tmp_path):
    """Create a minimal contract, registry, and MCP server for testing."""

    # Minimal contract
    contract_data = {
        "contract_id": "test-shop-001",
        "site_name": "Test Shop",
        "site_url": "http://localhost:9999",
        "screens": [],
        "require_identification": False,   # allow anonymous for testing
    }
    contract_path = str(tmp_path / "contract.json")
    with open(contract_path, "w") as f:
        json.dump(contract_data, f)

    # Operator registry with one operator
    registry_path = str(tmp_path / "operators.json")
    registry = OperatorRegistry(registry_path)
    priv_key, pub_key = generate_operator_keypair()
    registry.register("test-op", "Test Operator", pub_key, OperatorTier.VERIFIED)

    # Unregistered key (for forgery tests)
    evil_priv, _ = generate_operator_keypair()

    # Create MCP server WITH registry
    app = create_mcp_server(contract_path, "http://localhost:9999", registry_path)

    # Also create one WITHOUT registry (anonymous-only mode)
    app_no_reg = create_mcp_server(contract_path, "http://localhost:9999")

    from fastapi.testclient import TestClient
    return {
        "client": TestClient(app),
        "client_no_reg": TestClient(app_no_reg),
        "priv_key": priv_key,
        "evil_priv": evil_priv,
        "registry": registry,
    }


class TestSelfDeclaredTrustRejected:
    """
    THE REGRESSION TEST.
    Proves the Phase 1 vulnerability is fixed.
    """

    def test_trust_level_field_does_not_exist(self):
        """The ConnectRequest model must not have a trust_level field."""
        fields = ConnectRequest.model_fields
        assert "trust_level" not in fields, \
            "VULNERABILITY: trust_level field still exists in ConnectRequest"

    def test_can_transact_field_does_not_exist(self):
        """The ConnectRequest model must not have a can_transact field."""
        fields = ConnectRequest.model_fields
        assert "can_transact" not in fields, \
            "VULNERABILITY: can_transact field still exists in ConnectRequest"

    def test_old_format_ignored(self, setup):
        """Sending the old request format with trust_level has no effect."""
        # The old format — this used to grant super_agent access
        response = setup["client"].post("/tools/tessera_connect", json={
            "provider": "evil",
            "agent_name": "hacker",
            "trust_level": "super_agent",
            "can_transact": True,
        })
        # The extra fields are ignored by Pydantic (no credential → anonymous)
        # Should connect as anonymous, NOT as super_agent
        if response.status_code == 200:
            data = response.json()
            # If it connected, it must be anonymous
            perms = data.get("permissions", {})
            assert perms.get("can_transact_autonomously") is not True, \
                "VULNERABILITY: self-declared trust_level was accepted"


class TestCredentialConnect:
    """Test the new credential-based connect flow."""

    def test_valid_credential_connects(self, setup):
        token = sign_agent_credential(
            setup["priv_key"], "test-op", "legit-agent",
            tier="verified", purpose="shopping",
            capabilities={"can_transact": True, "max_transaction": 200.0},
        )
        response = setup["client"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert "session_id" in data

    def test_no_credential_connects_as_anonymous(self, setup):
        response = setup["client"].post("/tools/tessera_connect", json={})
        # Might be 200 (anonymous connected) or 403 (anonymous denied by contract)
        # Either way, it should NOT be super_agent
        if response.status_code == 200:
            data = response.json()
            perms = data.get("permissions", {})
            assert perms.get("can_transact_autonomously") is not True

    def test_forged_credential_rejected(self, setup):
        """Token signed with unregistered key claiming to be test-op."""
        token = sign_agent_credential(
            setup["evil_priv"], "test-op", "forged-agent",
            tier="super_agent",
        )
        response = setup["client"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error"] == "invalid_signature"

    def test_unknown_operator_rejected(self, setup):
        token = sign_agent_credential(
            setup["evil_priv"], "unknown-corp", "rogue-agent",
            tier="super_agent",
        )
        response = setup["client"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "unknown_operator"

    def test_expired_credential_rejected(self, setup):
        token = sign_agent_credential(
            setup["priv_key"], "test-op", "expired-agent",
            tier="identified", ttl_seconds=-1,
        )
        response = setup["client"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "token_expired"

    def test_tier_capped_at_operator_max(self, setup):
        """Operator registered as 'verified' but token claims 'super_agent'."""
        token = sign_agent_credential(
            setup["priv_key"], "test-op", "greedy-agent",
            tier="super_agent",
        )
        response = setup["client"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        # Should connect, but tier is capped to verified
        assert response.status_code == 200
        data = response.json()
        perms = data.get("permissions", {})
        # super_agent would have can_transact_autonomously=True
        # verified does NOT get autonomous transact (needs confirmation)
        assert perms.get("can_transact_autonomously") is not True


class TestNoRegistryMode:
    """When no registry is configured, all agents connect as anonymous."""

    def test_credential_ignored_without_registry(self, setup):
        """Even a valid credential is ignored if no registry is loaded."""
        token = sign_agent_credential(
            setup["priv_key"], "test-op", "agent",
            tier="super_agent",
        )
        response = setup["client_no_reg"].post("/tools/tessera_connect", json={
            "credential": token,
        })
        # Should connect as anonymous (credential not verified without registry)
        if response.status_code == 200:
            data = response.json()
            perms = data.get("permissions", {})
            assert perms.get("can_transact_autonomously") is not True
