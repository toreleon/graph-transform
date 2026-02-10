---
active: true
iteration: 1
max_iterations: 25
completion_promise: "EPIC 3
COMPLETE"
started_at: "2026-02-10T05:50:37Z"
---

# graph-transform Development Loop

## Your Role

You are implementing **graph-transform**, an MCP server providing verified code transformations for AI coding agents. You work iteratively, completing one story at a time.

## Source of Truth - BMAD Planning Artifacts

All planning documents are in `_bmad-output/planning-artifacts/`:

| Document | Purpose | When to Read |
|----------|---------|--------------|
| `epics.md` | Story breakdown with acceptance criteria (Given/When/Then) | Every story - contains FR references |
| `architecture.md` | Module structure, patterns, boundaries, code examples | When implementing - contains exact patterns to follow |
| `prd.md` | Full FR/NFR requirements with rationale | When clarifying requirements |
| `product-brief-graph-transform-2026-02-09.md` | High-level vision and constraints | For context on design decisions |

### Key Architecture Decisions (from architecture.md)

**Graph Model:**
- NodeKind: 8 types (CALLABLE, TYPE, BINDING, CONTAINER, REFERENCE, CALL, ACCESS, BLOCK)
- EdgeKind: 7 types (CONTAINS, CALLS, IMPORTS, INHERITS, REFERENCES, HAS_PARAMETER, HAS_RETURN_TYPE)
- Node ID format: `{kind}:{file}:{qualified_name}` (deterministic)

**Module Boundaries (STRICT):**
```
mcp/ → core/ → verification/ → adapters/
```
- `core/` NEVER imports from `mcp/`
- `verification/` NEVER imports from `mcp/`
- `adapters/` NEVER imports from `mcp/`

**Primitives:**
- INSERT, DELETE, UPDATE (immutable dataclasses, frozen=True)
- Return new graph, never mutate
- Preconditions fail fast, postconditions collect all

**MCP Response Format:**
```json
{
  "status": "ok|error",
  "data": { ... },
  "error": { "code": "...", "message": "...", "suggestions": [...] }
}
```

**Error Codes:** TARGET_NOT_FOUND, NAME_CONFLICT, SCOPE_NOT_FOUND, DANGLING_EDGE, INVALID_EDGE_TARGET, UNRESOLVED_REFERENCE, ORPHAN_NODE, PARSE_ERROR, INTERNAL_ERROR

## Progress Tracking

Track your progress in `PROGRESS.md` at project root:
- Mark stories as: `[ ]` pending, `[~]` in progress, `[x]` complete
- Update after each story completion
- If PROGRESS.md doesn't exist, create it from epics.md story list

## Implementation Rules

### Story Sequence
1. Work through stories IN ORDER within each epic
2. Complete Epic N before starting Epic N+1
3. Never skip ahead - dependencies matter

### Per-Story Workflow
For each story:
1. Read the story's acceptance criteria from epics.md
2. Check architecture.md for relevant patterns and code examples
3. Write tests FIRST that verify the acceptance criteria
4. Implement code to pass the tests
5. Run tests: `.venv/bin/pytest tests/ -x --tb=short`
6. If tests fail, fix and retry
7. When tests pass, commit with message: `feat(epicN): Story N.M - {story title}`
8. Update PROGRESS.md marking story complete
9. Move to next story

### Code Standards
- All code in `src/graph_transform/`
- Type hints required (mypy strict)
- Tests in `tests/` mirroring src structure
- Primitives must be immutable dataclasses (frozen=True)
- Follow patterns EXACTLY as shown in architecture.md

### Project Structure (from architecture.md)
```
src/graph_transform/
├── mcp/                        # MCP Server (Epic 1)
│   ├── __init__.py
│   ├── __main__.py             # Entry: python -m graph_transform.mcp
│   ├── server.py               # Tool registration
│   ├── registry.py             # Operator metadata
│   └── tools/
│       ├── spec.py             # Operator discovery
│       ├── query.py            # Node lookup
│       ├── plan.py             # Transformation
│       └── verify.py           # Verification
│
├── core/                       # Domain Logic (Epic 2, 3, 4)
│   ├── graph.py                # TypedGraph, Node, Edge
│   ├── node_kinds.py           # NodeKind, EdgeKind
│   ├── node_id.py              # ID generation
│   ├── query.py                # Query engine
│   ├── references.py           # Reference tracking
│   ├── errors.py               # ErrorCode enum
│   │
│   ├── primitives/
│   │   ├── base.py             # Primitive protocol
│   │   ├── insert.py
│   │   ├── delete.py
│   │   └── update.py
│   │
│   └── compositions/
│       ├── base.py             # Composition protocol
│       ├── rename.py
│       ├── move.py
│       ├── extract.py
│       ├── inline.py
│       ├── add_guard.py
│       ├── change_signature.py
│       └── wrap.py
│
├── verification/               # Verification (Epic 5)
│   ├── gluing.py               # DPO conditions
│   ├── preconditions.py
│   ├── postconditions.py
│   └── invariants.py
│
└── adapters/                   # Language Adapters (Epic 2, 6)
    ├── base.py                 # LanguageAdapter protocol
    └── python/
        ├── parser.py           # Python → Graph
        └── emitter.py          # Graph → Python
```

## Current State Assessment

Each iteration:
1. Read PROGRESS.md to find current story
2. Check git log for recent commits
3. Run tests to see current state
4. Read relevant architecture.md sections for the current epic
5. Continue from where you left off

## Completion Criteria

### Story Complete When:
- All acceptance criteria tests pass
- Code committed with proper message
- PROGRESS.md updated

### Epic Complete When:
- All stories in epic marked complete
- Integration tests for epic pass

### Project Complete When:
- All 6 epics complete (42 stories)
- Full test suite passes
- Output: `<promise>GRAPH-TRANSFORM COMPLETE</promise>`

## Commands

```bash
# Run tests
.venv/bin/pytest tests/ -x --tb=short

# Type check
.venv/bin/mypy src/graph_transform --strict

# Check current progress
cat PROGRESS.md

# See recent work
git log --oneline -10

# Read architecture decisions
cat _bmad-output/planning-artifacts/architecture.md

# Read full requirements
cat _bmad-output/planning-artifacts/prd.md
```

## Error Recovery

If stuck on a story:
1. Read the acceptance criteria again from epics.md
2. Check architecture.md for the exact pattern to follow
3. Check if dependencies from previous stories are complete
4. Look at test failures for specific guidance
5. Simplify - implement minimum to pass tests

If tests keep failing:
1. Check if test itself is correct per acceptance criteria
2. Verify imports and module structure match architecture.md
3. Check for missing dependencies from earlier stories

## Start

1. Read `_bmad-output/planning-artifacts/epics.md` for story list
2. Read `_bmad-output/planning-artifacts/architecture.md` for patterns
3. Check or create PROGRESS.md
4. Find first incomplete story
5. Begin implementation

When ALL stories complete across ALL epics, output:
```
<promise>GRAPH-TRANSFORM COMPLETE</promise>
``` Focus on Epic 3 only. Output <promise>EPIC 3 COMPLETE</promise> when done.
