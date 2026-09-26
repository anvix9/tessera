# Tessera Eval Results

## Governance Boundary: 15/15 tasks, 100% pass rate

The governance eval suite tests whether the terminal correctly denies actions that should be denied and allows actions that should be allowed. Each task scripts a specific boundary condition.

### Results by Category

| Category | Tasks | Passed | Description |
|----------|-------|--------|-------------|
| Tier Escalation | 4 | 4 | Anonymous denied buy; identified denied when verified required; verified allowed |
| Spend Limits | 4 | 4 | Transaction over limit denied; contract ceiling caps operator claims |
| Rate Limits | 1 | 1 | Per-minute rate limit blocks after threshold |
| Contract Expiry | 1 | 1 | Expired contract blocks all connections |
| Session Limits | 1 | 1 | Max concurrent sessions enforced |
| Item Limits | 2 | 2 | Quantity over max_items_per_action denied |
| User Consent | 2 | 2 | Actions requiring delegation denied without consent token |
| **Total** | **15** | **15** | **100% pass rate** |

### Denial Correctness Matrix

The differentiator: proving the terminal **stops** things.

| Scenario | Agent | Contract | Action | Expected | Actual |
|----------|-------|----------|--------|----------|--------|
| Anon buys | anonymous | buy requires verified | buy | denied | denied |
| Identified buys | identified | buy requires verified | buy | denied | denied |
| Operator inflates tx limit | verified, claims 999999 | contract says 100 | buy 150 | denied at 100 | denied at 100 |
| Operator inflates daily limit | verified, claims 99999 | contract says 500 | spend 600 | denied at 500 | denied at 500 |
| Expired contract | verified | expires_at in past | connect | denied | denied |
| Over rate limit | identified | 4/min | 5th request | denied | denied |
| Over item limit | verified | max 5 items | qty=20 | denied | denied |
| No consent token | verified, no delegation | buy requires consent | buy | denied | denied |

### What This Proves

1. **Trust tier is binding.** An agent at tier X cannot perform actions requiring tier Y > X.
2. **Contract ceiling is absolute.** The site owner's limits override operator claims — the blocker fix works.
3. **Rate limits fire on all three windows.** Per-minute checked (per-hour and per-day covered in unit tests).
4. **Contract expiration is enforced.** Expired contracts refuse connections.
5. **User consent is required.** Actions in `required_confirmations` need explicit delegation.

### What This Does NOT Cover (yet)

- **LLM agent behavior.** pass@1/pass@k with real language models requires Ollama and is Phase 5b.
- **Injection resistance.** Seeding terminal screens with adversarial prompts is a separate task category.
- **Recovery after failure.** Testing whether an agent can recover from a denied action requires agent intelligence, not scripted sequences.
- **Multi-site routing.** Cross-terminal task completion.

### Eval Framework

The eval harness (`evals/harness.py`) supports:
- Task definitions with expected outcomes per step
- Programmatic ground truth (assert status, not LLM judge)
- JSON export for CI gating
- Category-level pass rates

To run:
```bash
pytest evals/test_phase5_governance.py -v
```

To add tasks: create a new file in `evals/tasks/` returning a list of `TaskDefinition` objects.
