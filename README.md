# Tessera — Agent Terminal for the Web

Tessera compiles any website into a structured, governed terminal that AI agents navigate via MCP. Instead of parsing DOM trees or taking screenshots, agents get named screens with typed actions — a CLI for the web.

## Install

```bash
pip install -e ".[dev]"
```

## What it does

1. **Compiler** reads your route definitions from source code (10 web frameworks supported)
2. **Contract** wraps discovered routes in a governance layer (permissions, rate limits, trust tiers)
3. **Terminal** exposes the contract as MCP tools that any agent can call
4. **Agent** navigates the terminal to complete tasks

## Quick start

```python
from tessera.compiler.source_parser import SourceRouteParser

# Point at your codebase — extracts all API routes
parser = SourceRouteParser("/path/to/your/project")
routes = parser.parse()
print(f"Found {len(routes)} routes")
```

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

Verified accuracy on repos with known ground truth:

| Repo | Found/Actual | Precision |
|------|-------------|-----------|
| Appwrite | 186/187 | 100% |
| Cal.com | 82/82 | 100% |
| Medusa | 51/52 | 100% |
| RealWorld | 19/19 | 100% |

Full evaluation data in [BENCHMARKS.md](BENCHMARKS.md).

## Project structure

```
tessera/               # Python package (Apache-2.0)
├── compiler/          # Route discovery (source parser, HTTP probing, OpenAPI)
├── contract/          # Governance schema + permission resolver
├── terminal/          # Engine, agents, registry
└── mcp/               # MCP server
simulations/           # 18 test sites (525 endpoints)
evals/                 # Test suite (pytest)
```

## Running tests

```bash
pytest evals/ -v
```

## Known limitations

- **Workflow inference:** The compiler extracts routes, not workflows. It knows `GET /products` and `POST /orders` exist but doesn't know the ordering `search → cart → checkout → payment`.
- **Governance enforcement:** Several contract fields (`max_transaction_amount`, `max_daily_spend`, `requests_per_hour`) are declared but not yet checked at runtime (Phase 2).
- **MCP compliance:** Server is REST/FastAPI, not yet spec-compliant MCP with JSON-RPC (Phase 3).

## License

Apache-2.0 — see [LICENSE](LICENSE).

The open core is fully functional standalone. Commercial features (registry, analytics, audit) will live in a separate repository and consume `tessera` as a dependency — never the inverse.
