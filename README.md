# Tessera — Agent Terminal for the Web

Tessera compiles any website into a structured, governed terminal that AI agents navigate via MCP. Instead of parsing DOM trees or taking screenshots, agents get named screens with typed actions — a CLI for the web.

## Install

```bash
pip install -e ".[dev]"
pytest evals/ conformance/ -v
```

## What it does

1. **Compiler** reads your route definitions from source code (10 web frameworks)
2. **Contract** wraps discovered routes in governance (permissions, rate limits, spend ceilings, trust tiers)
3. **Terminal** exposes the contract as MCP tools over JSON-RPC
4. **Agent** navigates the terminal to complete tasks

## Trust model

Trust is derived from cryptographically signed credentials, never self-declared.

An operator generates an Ed25519 key pair, registers the public key with the terminal, and signs JWTs for their agents. The terminal verifies the signature, checks expiration, validates the audience, rejects replayed tokens, and caps the trust tier at the operator's registered maximum.

No field in the connect request lets an agent choose its own permissions.

See [docs/trust-model.md](docs/trust-model.md) for the full architecture.

## Governance enforcement

Every contract field actually binds at runtime:

| Field | Enforcement |
|-------|-------------|
| `requests_per_minute/hour/day` | Sliding window on audit log |
| `max_concurrent_sessions` | Checked at connect |
| `max_items_per_action` | Validated against quantity params |
| `max_transaction_amount` | min(operator claim, contract ceiling) |
| `max_daily_spend` | Rolling 24h accumulator, capped by contract |
| `expires_at` | Expired contracts refuse all connections |
| `user_consent_token` | Required for actions in `required_confirmations` |

Contract validation catches dangerous omissions: a contract that permits transactions but omits `max_transaction_amount` fails validation.

## MCP server

The server uses the official MCP Python SDK (v2.2.0) and speaks JSON-RPC 2.0:

| Transport | Use case |
|-----------|----------|
| Streamable HTTP | Web-accessible terminal |
| stdio | Claude Desktop, local MCP clients |

Five tools: `tessera_connect`, `tessera_get_screen`, `tessera_execute`, `tessera_audit_log`, `tessera_disconnect`.

## Supported frameworks

| Framework | Pattern | Tested on |
|-----------|---------|-----------|
| FastAPI | `@app.get("/path")` | RealWorld, FastAPI Full-Stack |
| Rails | `resources :name` | Forem/dev.to (341 routes) |
| Go (Chi/Echo) | `m.Get("/path")` | Gitea (162 routes) |
| NestJS | `@Controller()` + `@Get()` | Twenty CRM (101 routes) |
| Next.js files | `_get.ts`, `_post.ts` | Cal.com (131 routes) |
| Next.js App Router | `route.ts` | Medusa (51 routes) |
| Next.js pages | `export default` + `req.method` | Papermark (379 routes) |
| tRPC | `router({})` procedures | Documenso (102 routes) |
| PHP/Utopia | `Http::get('/path')` | Appwrite (186 routes) |
| Laravel | `Route::get()`, `Route::apiResource()` | Firefly III (502 routes) |

## Benchmarks

Source parser tested against 13 real GitHub repos: **2,203 routes extracted, 100% precision (zero false positives).**

Full evaluation data: [BENCHMARKS.md](BENCHMARKS.md). Governance eval results: [RESULTS.md](RESULTS.md).

## Test suite

```bash
pytest evals/ conformance/ -v
```

162 tests across 8 test files:

| File | Tests | What it covers |
|------|-------|----------------|
| `test_integration.py` | 19 | Schema, parser, package hygiene |
| `test_credentials.py` | 23 | Sign, verify, audience, replay, TTL, validation |
| `test_trust_regression.py` | 10 | Self-declared trust is rejected |
| `test_mcp_server.py` | 23 | MCP tools, sessions, errors |
| `test_enforcement.py` | 38 | Every governance field binds |
| `test_enforcement_integration.py` | 15 | Enforcement through terminal engine |
| `test_phase5_governance.py` | 18 | Governance boundary eval (15 tasks) |
| `test_mcp_conformance.py` | 16 | MCP protocol conformance |

## Project structure

```
tessera-project/
├── tessera/               # Python package (Apache-2.0)
│   ├── compiler/          # Route discovery (source parser, HTTP probing, OpenAPI)
│   ├── contract/          # Schema, resolver, enforcement, credentials, validation
│   ├── terminal/          # Engine, agents, registry
│   └── mcp/               # MCP server (official SDK)
├── simulations/           # 18 test sites (525+ endpoints)
├── evals/                 # Test suite + Phase 5 governance eval harness
├── conformance/           # MCP protocol conformance tests
├── docs/                  # Published documentation
│   └── trust-model.md     # Trust model architecture
├── BENCHMARKS.md          # Compiler evaluation data
├── RESULTS.md             # Governance eval results
├── SECURITY.md            # Security policy, fixed vulnerabilities
└── CONTRIBUTING.md        # Contributor guide + boundary rule
```

## Known limitations

- **Workflow inference:** The compiler extracts routes, not workflows. It knows `GET /products` and `POST /orders` exist but doesn't know the ordering `search → cart → checkout → payment`.
- **LLM agent evals:** The governance eval suite uses scripted sequences. pass@1 with real LLM agents (Phase 5b) requires Ollama and is not yet built.

## License

Apache-2.0 — see [LICENSE](LICENSE).

The open core is fully functional standalone. Commercial features (registry, analytics, audit) live in a separate repository and import `tessera` as a dependency — never the inverse.
