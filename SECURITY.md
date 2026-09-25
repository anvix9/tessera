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

### Trust Tier Self-Declaration (FIXED in Phase 1)

**Status:** Fixed.

**Issue:** The v0.1 MCP server accepted `trust_level` and `can_transact` as caller-supplied fields in the connect request. Any agent could self-declare `trust_level=super_agent` with `can_transact=True`.

**Fix:** The `trust_level` and `can_transact` fields have been removed from `ConnectRequest` entirely. Trust is now derived from Ed25519-signed credentials verified against an operator registry. The field cannot be sent because it does not exist in the request model.

**Regression tests:** `evals/test_trust_regression.py` — 10 tests including:
- `test_trust_level_field_does_not_exist` — the field is gone from the model
- `test_can_transact_field_does_not_exist` — the field is gone from the model
- `test_old_format_ignored` — sending the old format does not grant elevated access
- `test_forged_credential_rejected` — wrong key → 401
- `test_tier_capped_at_operator_max` — credential tier capped at operator's registered max

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
| LLM06 | Excessive Agency | The trust-tier self-declaration bug (now fixed) was a direct instance of this risk. Regression tests verify the fix. |
| LLM07 | Insecure Plugin Design | MCP tools must validate all parameters against the contract before execution |
