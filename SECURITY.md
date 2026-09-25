# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Tessera, please report it responsibly:

- Email: security@tessera.dev (or open a private GitHub security advisory)
- Do not open a public issue for security vulnerabilities
- We will acknowledge receipt within 48 hours

## Scope

Tessera is a governance layer between AI agents and websites. Security issues in the following areas are in scope:

- Trust tier escalation (agent gaining permissions it shouldn't have)
- Contract enforcement bypass (agent exceeding rate limits, spending caps, or action restrictions)
- Session hijacking or token forgery
- Injection through terminal actions that reach the underlying website
- Information disclosure through the MCP interface

## Known Issues and Mitigations

### Trust Tier Self-Declaration (CRITICAL — fix in progress)

**Status:** Identified, fix planned for Phase 1.

**Issue:** The current MCP server (`mcp/server.py`) accepts `trust_level` and `can_transact` as caller-supplied fields in the connect request. Any agent can self-declare `trust_level=super_agent` with `can_transact=True`, bypassing the entire governance model.

**Impact:** Complete bypass of permission controls. An anonymous agent can claim verified/super_agent status and execute privileged actions including autonomous transactions.

**Mitigation (current):** None in code. The simulation environments do not process real transactions.

**Fix (Phase 1):** Remove caller-supplied trust fields entirely. Trust tiers will be derived from cryptographically verified agent credentials. A regression test will assert that forged trust payloads are rejected.

### Governance Fields Not Enforced

**Status:** Identified, fix planned for Phase 2.

Several contract fields are declared but not checked at runtime:

- `max_transaction_amount` — resolved but never compared to actual amounts
- `max_daily_spend` — passed through, never accumulated
- `requests_per_hour` / `requests_per_day` — declared, only per-minute checked
- `max_concurrent_sessions` — not enforced
- `expires_at` — not honored

**Impact:** Contract terms are advisory, not binding. An agent that accepts a contract is not actually constrained by its limits.

**Fix (Phase 2):** Enforcement per field with a test for each, published as a public enforcement matrix.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes (current development) |
| < 0.2   | No |

## OWASP LLM Top 10 Mapping

| OWASP ID | Risk | Tessera Relevance |
|----------|------|-------------------|
| LLM01 | Prompt Injection | Terminal actions pass through to real APIs — injection in action parameters could reach the website |
| LLM06 | Excessive Agency | The trust-tier self-declaration bug is a direct instance of this risk |
| LLM07 | Insecure Plugin Design | MCP tools must validate all parameters against the contract before execution |
