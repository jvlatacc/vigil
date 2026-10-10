# LLM Layer

Everything Vigil does with a language model lives here. The layering below is
the point of the package: it is what tells you where a new file goes, and it is
enforced by `tests/unit/llm/test_boundary.py` and the `.importlinter` contracts.

## The harness boundary

The distinction that matters is **loop vs. call**. A *router* call is one
stateless completion. A *harness* runs many of them, executing tools between
turns. Conflating the two is what made `services/` unnavigable.

| Sub-package | Owns | Never does |
|---|---|---|
| `router/` | **One** stateless completion: provider selection, wire-format translation, pre-dispatch sanitization, budget VK resolution | Loop, execute tools, touch SOC domain models |
| `harness/` | The multi-turn agent loop: tool execution via MCP, approval gating, conversation state, streaming | Construct SDK clients or pick providers directly — it calls the router |
| `providers/` | SDK client construction, the model registry, live model discovery, local Ollama supervision | Know about agents or tools |
| `cost/` | Pricing math, pre-call estimation, virtual-key budget enforcement | Call an LLM |
| `bifrost/` | The only place that speaks Bifrost's admin and logging REST APIs | — |
| `gateway/` | The ARQ enqueue side in front of the router | Run the jobs it enqueues — that worker is `services/worker/` |

`security.py` (prompt-injection defenses) sits at the top level because both the
router and every harness need it.

## Rules

1. `router/` must not import `harness/`. The dependency runs one way.
2. Nothing under `core/` (including `core/llm/`) imports the deployables —
   enforced by the import-linter contracts in `.importlinter` ("core is a
   library: it must not import the deployables"), not just by convention.
   (An earlier version of this page described a grandfathered module-scope
   `backend.schemas.tool_schemas` import in `harness/claude.py`; that import
   no longer exists at current HEAD.)
3. `core/llm/providers/registry.py` and `core/llm/bifrost/admin.py` import
   each other lazily, by design. Do not hoist either import to module scope —
   it is a real cycle.
