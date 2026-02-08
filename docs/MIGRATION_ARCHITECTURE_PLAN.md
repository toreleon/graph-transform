# Graph-Transform Migration Architecture Plan

This document outlines the architecture for extending graph-transform from a refactoring tool to a comprehensive code migration platform capable of handling large-scale transformations including language-to-language migration, version upgrades, and framework migrations.

## Table of Contents

1. [Current Limitations](#current-limitations)
2. [Multi-Layer Architecture](#multi-layer-architecture)
3. [Unified Semantic Graph](#1-unified-semantic-graph-usg)
4. [Idiom Pattern Library](#2-idiom-pattern-library)
5. [Migration Orchestration Engine](#3-migration-orchestration-engine)
6. [Incremental Migration with Mixed-State Support](#4-incremental-migration-with-mixed-state-support)
7. [LLM Integration](#5-llm-integration-for-migration)
8. [Implementation Roadmap](#6-implementation-roadmap)

---

## Current Limitations

| Aspect | Current State | Needed for Migration |
|--------|---------------|---------------------|
| Graph Scope | Single language | Multi-language, semantic graph |
| Pattern Size | 2-10 nodes | Complex idioms (20+ nodes) |
| Rule Creation | Manual L-K-R | Pattern templates, learning |
| Execution | Sequential | Phased, incremental, resumable |
| Validation | Syntactic invariants | Semantic equivalence |
| State | Stateless per-run | Track migration progress |

---

## Multi-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MIGRATION ORCHESTRATOR                            │
│  • Migration plan management    • Progress tracking                      │
│  • Rollback support             • Incremental execution                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼───────────────────────────────────┐
│                          SEMANTIC LAYER                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ Concept      │  │ Idiom        │  │ API          │                 │
│  │ Mapping      │  │ Patterns     │  │ Mappings     │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
└───────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼───────────────────────────────────┐
│                     UNIFIED SEMANTIC GRAPH                             │
│  Language-agnostic intermediate representation                         │
│  • Semantic nodes (Function, Type, Effect, Contract)                   │
│  • Cross-language edges (EQUIVALENT_TO, TRANSLATES_TO)                │
└───────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Python Graph   │      │  TypeScript     │      │  Go Graph       │
│  (source)       │      │  Graph          │      │  (target)       │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## 1. Unified Semantic Graph (USG)

**Purpose**: Language-agnostic representation that captures *meaning*, not syntax.

### Semantic Node Types

```python
class SemanticNodeType(Enum):
    # Computation
    COMPUTATION = "computation"      # Any callable (function, method, lambda)
    EFFECT = "effect"                # Side effect (IO, mutation, exception)
    CONTRACT = "contract"            # Pre/post conditions, invariants

    # Data
    DATA_TYPE = "data_type"          # Type definition
    PRODUCT_TYPE = "product_type"    # Struct/class/record
    SUM_TYPE = "sum_type"            # Enum/union/variant
    COLLECTION = "collection"        # List/array/set/map

    # Control
    ITERATION = "iteration"          # Loop/map/fold
    BRANCHING = "branching"          # If/match/switch
    CONCURRENCY = "concurrency"      # Async/thread/channel

    # Relationships
    DEPENDENCY = "dependency"        # Import/require/use
    INTERFACE = "interface"          # Protocol/trait/interface
```

### Semantic Edge Types

```python
class SemanticEdgeType(Enum):
    # Cross-language relationships
    EQUIVALENT_TO = "equivalent_to"    # Same semantics, different syntax
    APPROXIMATES = "approximates"      # Similar but not exact
    REQUIRES_MANUAL = "requires_manual" # Cannot auto-translate

    # Semantic relationships
    HAS_EFFECT = "has_effect"          # Function → Effect
    SATISFIES = "satisfies"            # Impl → Interface
    TRANSFORMS = "transforms"          # Input type → Output type
    DEPENDS_ON = "depends_on"          # Semantic dependency
```

### Cross-Language Mapping Example: Python → Go

```
Python                    Semantic Graph              Go
──────                    ──────────────              ──
def process(x: int)  ──►  COMPUTATION        ──►  func process(x int)
    -> str:                 │                         string
                            ├─ HAS_PARAM: int
                            └─ RETURNS: str

class User:          ──►  PRODUCT_TYPE       ──►  type User struct {
    name: str                │                       Name string
    age: int                 ├─ FIELD: name:str      Age  int
                             └─ FIELD: age:int    }

async def fetch():   ──►  COMPUTATION        ──►  func fetch() chan Result
                            │
                            └─ CONCURRENCY: async

list[int]            ──►  COLLECTION         ──►  []int
                            └─ ELEMENT: int

dict[str, User]      ──►  COLLECTION         ──►  map[string]User
                            ├─ KEY: str
                            └─ VALUE: User
```

---

## 2. Idiom Pattern Library

**Purpose**: Recognize high-level patterns in source, map to target idioms.

### Pattern Definition Language

```yaml
# patterns/python_to_go/error_handling.yaml
pattern:
  name: "try_except_to_error_return"
  source_language: python
  target_language: go
  description: "Convert Python try/except to Go error returns"

  # What to match in source
  match:
    type: try_block
    body:
      - type: call
        target: $operation
        bind: $call
    handlers:
      - type: except_handler
        exception: $ExceptionType
        body: $handler_body

  # What to generate in target
  emit:
    type: multi_return_call
    call: $operation
    returns:
      - name: result
        type: infer($call.return_type)
      - name: err
        type: error
    error_check:
      condition: "err != nil"
      body:
        translate: $handler_body
        context: error_handler

  # Confidence and limitations
  confidence: 0.85
  limitations:
    - "Multiple except clauses require manual review"
    - "Exception chaining not preserved"
```

### Pattern Categories

```python
IDIOM_PATTERNS = {
    # Error Handling
    "error_handling": [
        "try_except_to_error_return",      # Python → Go
        "try_except_to_result_type",       # Python → Rust
        "callback_error_to_try_catch",     # Node.js → Python
        "exception_to_either",             # Java → Scala
    ],

    # Concurrency
    "concurrency": [
        "async_await_to_goroutine",        # Python → Go
        "threading_to_async",              # Python 2 → Python 3
        "callback_to_promise",             # JS ES5 → ES6
        "promise_to_async_await",          # JS Promise → async/await
        "futures_to_async",                # Java → Kotlin
    ],

    # Data Structures
    "collections": [
        "list_comprehension_to_stream",    # Python → Java
        "dict_to_map_literal",             # Python → Go
        "dataclass_to_struct",             # Python → Go
        "namedtuple_to_record",            # Python → Java 16+
    ],

    # OOP → FP / FP → OOP
    "paradigm_shift": [
        "class_to_module_functions",       # Python OOP → Go
        "inheritance_to_composition",      # Java → Go
        "visitor_to_pattern_match",        # Java → Scala/Rust
        "strategy_to_function_param",      # OOP → FP
    ],

    # Framework-specific
    "framework": [
        "django_to_fastapi",               # Django → FastAPI
        "express_to_fastify",              # Express → Fastify
        "react_class_to_hooks",            # React 16 → 18
        "junit4_to_junit5",                # JUnit migration
    ],
}
```

### Idiom Matcher Implementation

```python
class IdiomMatcher:
    """Match complex idiom patterns across AST/graph."""

    def __init__(self, pattern_library: PatternLibrary):
        self.patterns = pattern_library
        self.match_finder = MatchFinder()  # Existing

    def find_idiom_matches(
        self,
        graph: TypedGraph,
        source_lang: str,
        target_lang: str,
    ) -> list[IdiomMatch]:
        """Find all idiom patterns applicable for this migration."""

        applicable = self.patterns.get_patterns(source_lang, target_lang)
        matches = []

        for pattern in applicable:
            # Convert idiom pattern to graph pattern
            graph_pattern = pattern.to_graph_pattern()

            # Use existing MatchFinder
            raw_matches = self.match_finder.find_matches(
                graph_pattern,
                host_graph=graph,
                max_matches=1000
            )

            for match in raw_matches:
                matches.append(IdiomMatch(
                    pattern=pattern,
                    location=match,
                    confidence=pattern.confidence,
                    bindings=self._extract_bindings(match, pattern)
                ))

        return sorted(matches, key=lambda m: -m.confidence)
```

---

## 3. Migration Orchestration Engine

### Multi-Phase Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MIGRATION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Phase 1: ANALYSIS                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Parse &     │→ │ Semantic    │→ │ Pattern     │→ │ Dependency  │   │
│  │ Build Graph │  │ Lifting     │  │ Recognition │  │ Analysis    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
│                                                                         │
│  Phase 2: PLANNING                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Strategy    │→ │ Ordering &  │→ │ Conflict    │→ │ Checkpoint  │   │
│  │ Selection   │  │ Batching    │  │ Resolution  │  │ Planning    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
│                                                                         │
│  Phase 3: EXECUTION (Incremental, Resumable)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Transform   │→ │ Generate    │→ │ Validate    │→ │ Commit &    │   │
│  │ Batch       │  │ Target Code │  │ Semantics   │  │ Checkpoint  │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
│                                                                         │
│  Phase 4: VERIFICATION                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │
│  │ Type Check  │→ │ Test        │→ │ Semantic    │                     │
│  │ Target      │  │ Equivalence │  │ Diff Report │                     │
│  └─────────────┘  └─────────────┘  └─────────────┘                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Migration Plan Data Model

```python
@dataclass
class MigrationPlan:
    """Complete specification for a codebase migration."""

    # Scope
    source_language: str
    target_language: str
    source_version: str | None       # e.g., "3.8" for Python
    target_version: str | None       # e.g., "1.21" for Go

    # What to migrate
    scope: MigrationScope            # files, modules, packages
    exclusions: list[str]            # glob patterns to skip

    # Strategy
    strategy: MigrationStrategy      # BIG_BANG | INCREMENTAL | STRANGLER
    batch_size: int                  # files per batch
    checkpoint_frequency: int        # batches between checkpoints

    # Phases
    phases: list[MigrationPhase]
    current_phase: int

    # State (persisted)
    completed_items: set[str]        # file paths or node IDs
    pending_manual_review: list[ManualReviewItem]
    checkpoints: list[Checkpoint]


@dataclass
class MigrationPhase:
    """A phase within the migration."""

    name: str
    description: str

    # What this phase handles
    node_types: list[NodeType]       # Which graph nodes
    patterns: list[str]              # Which idiom patterns

    # Dependencies
    depends_on: list[str]            # Phase names that must complete first

    # Execution
    parallel: bool                   # Can items run in parallel?
    require_tests_pass: bool         # Gate on test success?

    # Progress
    status: PhaseStatus              # PENDING | IN_PROGRESS | COMPLETED | BLOCKED
    items: list[MigrationItem]


@dataclass
class MigrationItem:
    """Single unit of migration work."""

    id: str
    source_nodes: list[str]          # Node IDs in source graph
    target_pattern: str              # Idiom pattern to apply

    # Execution
    status: ItemStatus               # PENDING | TRANSFORMED | VALIDATED | COMMITTED | FAILED
    confidence: float                # Auto-migration confidence
    requires_review: bool            # Needs human/LLM review?

    # Results
    generated_code: str | None
    validation_errors: list[str]
    manual_notes: str | None
```

### Execution Strategies

```python
class MigrationStrategy(Enum):
    # All at once (for small codebases or low-risk migrations)
    BIG_BANG = "big_bang"

    # Module by module (for medium codebases)
    INCREMENTAL = "incremental"

    # Strangler fig (run old + new in parallel, gradually shift traffic)
    STRANGLER = "strangler"

    # Feature flag controlled (toggle between implementations)
    FEATURE_FLAG = "feature_flag"


class MigrationOrchestrator:
    """Orchestrates large-scale migration execution."""

    def __init__(
        self,
        plan: MigrationPlan,
        engine: GraphTransformationEngine,
        pattern_library: PatternLibrary,
        llm: LLMInterface | None = None,  # For ambiguous cases
    ):
        self.plan = plan
        self.engine = engine
        self.patterns = pattern_library
        self.llm = llm
        self.state = MigrationState.load(plan.id)

    async def execute(self) -> MigrationResult:
        """Execute migration with checkpointing and resumability."""

        for phase in self.plan.phases:
            if phase.status == PhaseStatus.COMPLETED:
                continue

            # Check dependencies
            if not self._dependencies_met(phase):
                phase.status = PhaseStatus.BLOCKED
                continue

            phase.status = PhaseStatus.IN_PROGRESS

            # Process items in batches
            for batch in self._batch_items(phase.items):
                results = await self._process_batch(batch, phase)

                # Handle failures
                failed = [r for r in results if r.status == ItemStatus.FAILED]
                if failed and phase.require_tests_pass:
                    return MigrationResult(
                        status="blocked",
                        failed_items=failed,
                        checkpoint=self._save_checkpoint()
                    )

                # Checkpoint periodically
                if self._should_checkpoint():
                    self._save_checkpoint()

            phase.status = PhaseStatus.COMPLETED

        return MigrationResult(status="completed", ...)

    async def _process_batch(
        self,
        batch: list[MigrationItem],
        phase: MigrationPhase
    ) -> list[ItemResult]:
        """Process a batch of migration items."""

        results = []
        for item in batch:
            # 1. Apply graph transformation
            transform_result = self._apply_transformation(item)

            # 2. Generate target code
            if transform_result.success:
                code = self._generate_code(transform_result.graph)
            else:
                # Fallback to LLM for complex cases
                if self.llm and item.confidence < 0.7:
                    code = await self.llm.generate_migration(item)
                else:
                    item.status = ItemStatus.FAILED
                    item.requires_review = True
                    continue

            # 3. Validate
            validation = self._validate(code, item)
            if validation.errors:
                if self.llm:
                    code = await self.llm.fix_errors(code, validation.errors)
                    validation = self._validate(code, item)

            # 4. Commit or mark for review
            if validation.passed:
                item.status = ItemStatus.COMMITTED
                item.generated_code = code
            else:
                item.status = ItemStatus.FAILED
                item.requires_review = True
                item.validation_errors = validation.errors

            results.append(ItemResult(item=item, code=code))

        return results
```

---

## 4. Incremental Migration with Mixed-State Support

### The Mixed-State Problem

During migration, the codebase has **both** source and target code coexisting:

```
Before:        During Migration:           After:
─────────      ────────────────            ─────
Python only    Python + Go + FFI bridges   Go only
```

### Interoperability Layer

```python
@dataclass
class InteropBridge:
    """Generates glue code for mixed-language execution."""

    source_lang: str
    target_lang: str

    # Strategies per language pair
    BRIDGES = {
        ("python", "go"): "cgo_bridge",      # Python ↔ Go via cgo
        ("python", "rust"): "pyo3_bridge",   # Python ↔ Rust via PyO3
        ("javascript", "typescript"): None,  # Direct (TS compiles to JS)
        ("java", "kotlin"): None,            # Direct (same JVM)
    }

    def generate_bridge(
        self,
        migrated_module: str,
        exported_symbols: list[Symbol]
    ) -> BridgeCode:
        """Generate interop code for migrated module."""

        strategy = self.BRIDGES.get((self.source_lang, self.target_lang))

        if strategy is None:
            # No bridge needed (compatible runtimes)
            return BridgeCode(source_stub=None, target_stub=None)

        if strategy == "cgo_bridge":
            return self._generate_cgo_bridge(migrated_module, exported_symbols)
        # ... other strategies
```

### Migration State Machine (Per-Module)

```
                    ┌─────────────┐
                    │   SOURCE    │  (Original Python)
                    │   ONLY      │
                    └──────┬──────┘
                           │ migrate_start()
                           ▼
                    ┌─────────────┐
                    │  MIGRATING  │  (Python + Go skeleton)
                    │             │
                    └──────┬──────┘
                           │ tests_pass()
                           ▼
                    ┌─────────────┐
                    │   DUAL      │  (Both implementations exist)
                    │   MODE      │  (Traffic can go to either)
                    └──────┬──────┘
                           │ confidence_high()
                           ▼
                    ┌─────────────┐
                    │  SHADOWING  │  (Target primary, source fallback)
                    │             │
                    └──────┬──────┘
                           │ stable()
                           ▼
                    ┌─────────────┐
                    │   TARGET    │  (Go only, Python removed)
                    │   ONLY      │
                    └─────────────┘
```

### Migration Manifest

```yaml
# migration_manifest.yaml - tracks migration progress
migration:
  id: "api-python-to-go-2024"
  source: {language: python, version: "3.11"}
  target: {language: go, version: "1.21"}
  started: "2024-01-15"

modules:
  - path: "src/auth/"
    status: TARGET_ONLY           # Fully migrated
    migrated_at: "2024-02-01"

  - path: "src/api/handlers/"
    status: DUAL_MODE             # Both exist
    bridge: "bridges/handlers_bridge.go"
    traffic_split: {source: 10, target: 90}

  - path: "src/api/models/"
    status: MIGRATING             # In progress
    items_remaining: 12

  - path: "src/legacy/"
    status: SOURCE_ONLY           # Not started
    blocked_by: ["src/api/models/"]

dependencies:
  # Tracks cross-module dependencies for ordering
  - {from: "src/api/handlers/", to: "src/api/models/"}
  - {from: "src/api/models/", to: "src/auth/"}
```

---

## 5. LLM Integration for Migration

### Hybrid LLM + Graph Approach

```python
class MigrationLLMInterface:
    """LLM integration for migration tasks."""

    async def suggest_migration_plan(
        self,
        source_graph: TypedGraph,
        source_lang: str,
        target_lang: str,
    ) -> MigrationPlan:
        """LLM analyzes codebase and suggests migration strategy."""

        # Provide graph summary as context
        context = {
            "modules": source_graph.get_module_summary(),
            "dependencies": source_graph.get_dependency_graph(),
            "complexity_metrics": analyze_complexity(source_graph),
            "available_patterns": self.patterns.list_patterns(source_lang, target_lang),
        }

        plan = await self.llm.generate(
            prompt=MIGRATION_PLANNING_PROMPT,
            context=context,
        )

        return MigrationPlan.from_llm_response(plan)

    async def handle_ambiguous_pattern(
        self,
        source_code: str,
        source_graph: TypedGraph,
        attempted_pattern: IdiomPattern,
        error: str,
    ) -> str:
        """LLM handles cases where pattern matching fails."""

        return await self.llm.generate(
            prompt=f"""
            The following code could not be automatically migrated:

            ```{source_lang}
            {source_code}
            ```

            Attempted pattern: {attempted_pattern.name}
            Error: {error}

            Target language: {target_lang}

            Generate the equivalent code in {target_lang}.
            Explain any semantic differences.
            """,
            context={"graph": source_graph.to_dict()}
        )

    async def verify_semantic_equivalence(
        self,
        source_code: str,
        target_code: str,
        source_graph: TypedGraph,
        target_graph: TypedGraph,
    ) -> EquivalenceReport:
        """LLM verifies the migration preserves semantics."""

        return await self.llm.generate(
            prompt=EQUIVALENCE_CHECK_PROMPT,
            context={
                "source": source_code,
                "target": target_code,
                "source_graph": source_graph.to_dict(),
                "target_graph": target_graph.to_dict(),
            }
        )
```

### Division of Labor: Graph vs LLM

| Capability | Graph-Transform | LLM |
|------------|-----------------|-----|
| Parse code structure | ✅ Exact | ❌ Hallucinate |
| Find all references | ✅ Complete | ❌ May miss |
| Apply rename consistently | ✅ Guaranteed | ⚠️ May miss sites |
| Check invariants | ✅ Formal | ❌ Cannot |
| Understand intent | ❌ Needs structure | ✅ Natural |
| Handle ambiguity | ❌ Needs rules | ✅ Judgment |
| Explain changes | ❌ Just data | ✅ Natural |
| Novel refactorings | ❌ Only defined ops | ✅ Creative |

**The sweet spot**: LLM handles intent/ambiguity/creativity, graph-transform handles correctness/completeness/consistency.

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Extends Current)

```
src/graph_transform/
├── semantic/                    # NEW: Semantic layer
│   ├── unified_graph.py         # Language-agnostic USG
│   ├── concept_mapping.py       # Type/concept translations
│   └── lifters/                 # AST → Semantic per language
│       ├── python_lifter.py
│       └── go_lifter.py
├── patterns/                    # NEW: Idiom patterns
│   ├── pattern_dsl.py           # Pattern definition language
│   ├── idiom_matcher.py         # Extended MatchFinder
│   └── library/                 # Pattern YAML files
│       ├── python_to_go/
│       ├── react_class_to_hooks/
│       └── django_to_fastapi/
```

### Phase 2: Migration Engine

```
├── migration/                   # NEW: Orchestration
│   ├── orchestrator.py          # Multi-phase execution
│   ├── plan.py                  # MigrationPlan data model
│   ├── state.py                 # Progress tracking, checkpoints
│   ├── interop/                 # Bridge generation
│   │   ├── cgo_bridge.py
│   │   └── pyo3_bridge.py
│   └── strategies/
│       ├── big_bang.py
│       ├── incremental.py
│       └── strangler.py
```

### Phase 3: LLM Integration

```
├── llm/                         # NEW: LLM interface
│   ├── interface.py             # Abstract LLM protocol
│   ├── planning.py              # Migration planning
│   ├── ambiguity.py             # Handle edge cases
│   └── verification.py          # Semantic equivalence
```

### New CLI Commands

```bash
# Analyze codebase for migration
graph-transform migrate analyze src/ --from python --to go

# Generate migration plan
graph-transform migrate plan src/ --from python:3.11 --to go:1.21 -o plan.yaml

# Execute migration (incremental, resumable)
graph-transform migrate run plan.yaml --batch-size 10 --checkpoint-dir .migration/

# Check migration status
graph-transform migrate status plan.yaml

# Generate interop bridges for dual-mode
graph-transform migrate bridge src/api/ --manifest migration_manifest.yaml

# Verify semantic equivalence
graph-transform migrate verify --source src/auth.py --target src/auth.go
```

---

## Summary: From Refactoring Tool to Migration Platform

| Capability | Current | With Migration Extensions |
|------------|---------|--------------------------|
| **Scope** | Single file/module | Entire codebase |
| **Languages** | Python only | Multi-language + semantic layer |
| **Patterns** | 41 refactoring operators | + Idiom patterns, framework migrations |
| **Execution** | One-shot | Phased, incremental, resumable |
| **State** | Stateless | Checkpointed, mixed-state aware |
| **Validation** | Syntactic invariants | + Semantic equivalence |
| **LLM Role** | Intent translation | + Ambiguity handling, verification |
| **Output** | Edit instructions | + Bridge code, migration manifest |

The key insight: **graph-transform provides the formal foundation** (DPO rewriting, pattern matching, invariants), while the migration layer adds **orchestration, state management, and semantic awareness** needed for large-scale transformations.
