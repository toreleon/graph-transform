# Graph-Transform Migration Architecture Plan

This document outlines the architecture for extending graph-transform from a refactoring tool to a comprehensive code migration platform capable of handling large-scale transformations including language-to-language migration, version upgrades, and framework migrations.

## Table of Contents

1. [Current Limitations](#current-limitations)
2. [Generalized Operator Architecture](#generalized-operator-architecture)
3. [Multi-Layer Architecture](#multi-layer-architecture)
4. [Unified Semantic Graph](#1-unified-semantic-graph-usg)
5. [Idiom Pattern Library](#2-idiom-pattern-library)
6. [Migration Orchestration Engine](#3-migration-orchestration-engine)
7. [Incremental Migration with Mixed-State Support](#4-incremental-migration-with-mixed-state-support)
8. [LLM Integration](#5-llm-integration-for-migration)
9. [Implementation Roadmap](#6-implementation-roadmap)

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

## Generalized Operator Architecture

**Purpose**: Reduce all code transformations to a minimal set of fundamental operators that work for ANY language and ANY transformation task.

### The Insight: Three Primitive Operators

From graph rewriting theory and tree edit distance, **all code transformations reduce to three atomic operations**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     THE THREE PRIMITIVES                                     │
│                                                                              │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│    │    INSERT    │    │    DELETE    │    │    UPDATE    │                │
│    │              │    │              │    │              │                │
│    │  Add node    │    │  Remove node │    │  Modify      │                │
│    │  Add edge    │    │  Remove edge │    │  attribute   │                │
│    └──────────────┘    └──────────────┘    └──────────────┘                │
│                                                                              │
│    Every code transformation is a composition of these three.               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Formal Definition

```python
@dataclass
class Insert:
    """Add element to the code graph."""
    element: Node | Edge
    position: Position          # Where to insert (scope, index, anchor)

@dataclass
class Delete:
    """Remove element from the code graph."""
    target: NodeRef | EdgeRef   # What to remove
    cascade: bool = True        # Remove dependent edges?

@dataclass
class Update:
    """Modify property of existing element."""
    target: NodeRef | EdgeRef   # What to modify
    property: str               # Which property
    value: Any                  # New value
```

**That's it.** Three operators. Everything else is composition.

---

### Why Only Three?

| Candidate | Reduces To |
|-----------|------------|
| MOVE | DELETE(old_location) + INSERT(new_location) |
| RENAME | UPDATE(name_property) |
| COPY | INSERT(clone_of_original) |
| REPLACE | DELETE(old) + INSERT(new) |
| WRAP | INSERT(wrapper) + UPDATE(parent_edge) |
| EXTRACT | INSERT(new_entity) + UPDATE(replace_code_with_ref) |
| INLINE | UPDATE(replace_ref_with_body) + DELETE(entity) |

---

### Composition Examples

#### RENAME (Any Entity, Any Language)

```
RENAME(target, old_name, new_name) =
    UPDATE(target, "name", new_name)
    + for each ref in references(target):
        UPDATE(ref, "target_name", new_name)
```

Works for: Python function, Go struct, Java class, TypeScript interface...

#### MOVE (Any Entity, Any Language)

```
MOVE(entity, from_scope, to_scope) =
    DELETE(edge(from_scope, CONTAINS, entity))
    + INSERT(edge(to_scope, CONTAINS, entity))
    + for each ref in references(entity):
        UPDATE(ref, "qualified_path", new_path)
```

Works for: Move method to another class, move function to another module...

#### EXTRACT_METHOD (Any Language)

```
EXTRACT_METHOD(code_range, new_name) =
    INSERT(node(CALLABLE, name=new_name, body=code_range.code))
    + INSERT(edge(scope, CONTAINS, new_node))
    + UPDATE(code_range, replace_with=CALL(new_name, captured_vars))
    + INSERT(edge(original, CALLS, new_node))
```

Works for: Python, Go, Java, Rust, TypeScript...

#### Python try/except → Go error return

```
MIGRATE_ERROR_HANDLING(try_block) =
    DELETE(try_block)
    + INSERT(call_with_error_return)
    + INSERT(if_err_check)
    + UPDATE(handler_body, context=error_branch)
```

---

### The Position System

The key to making INSERT work across languages is a **universal position system**:

```python
@dataclass
class Position:
    """Where to insert an element."""

    # Scope (container)
    scope: NodeRef              # module, class, function, block

    # Relative position
    anchor: NodeRef | None      # Insert relative to this element
    relation: Relation          # BEFORE | AFTER | FIRST_CHILD | LAST_CHILD

    # Optional constraints
    index: int | None           # Absolute position (if applicable)
    slot: str | None            # Named slot (e.g., "parameters", "body", "decorators")


class Relation(Enum):
    BEFORE = "before"           # Insert before anchor
    AFTER = "after"             # Insert after anchor
    FIRST_CHILD = "first"       # Insert as first child of scope
    LAST_CHILD = "last"         # Insert as last child of scope
    REPLACE = "replace"         # Replace anchor
```

---

### Node and Edge Types (Language-Agnostic)

```python
class NodeKind(Enum):
    """Universal node types for any language."""

    # Definitions
    CALLABLE = "callable"       # function, method, lambda, closure
    TYPE = "type"               # class, struct, interface, enum, trait
    BINDING = "binding"         # variable, constant, parameter, field
    CONTAINER = "container"     # module, package, namespace, file

    # References
    REFERENCE = "reference"     # import, use, require, include
    CALL = "call"               # function/method invocation
    ACCESS = "access"           # field/property access

    # Control
    BLOCK = "block"             # scope block, compound statement
    BRANCH = "branch"           # if, match, switch
    LOOP = "loop"               # for, while, loop

    # Literals
    LITERAL = "literal"         # string, number, boolean, null


class EdgeKind(Enum):
    """Universal edge types."""

    CONTAINS = "contains"       # Parent contains child
    REFERENCES = "references"   # Uses/calls/accesses
    INHERITS = "inherits"       # Type inheritance
    IMPLEMENTS = "implements"   # Interface implementation
    DEPENDS = "depends"         # Dependency relationship
    FLOWS_TO = "flows_to"       # Data/control flow
```

---

### Derived Operators (Compositions)

For convenience, we define **derived operators** as named compositions:

```python
# Level 1: Direct compositions of primitives
RENAME = Compose(UPDATE)                           # Single UPDATE
REMOVE = Compose(DELETE)                           # Single DELETE
ADD = Compose(INSERT)                              # Single INSERT

# Level 2: Multi-step compositions
MOVE = Compose(DELETE, INSERT)                     # Relocate
REPLACE = Compose(DELETE, INSERT)                  # Substitute
COPY = Compose(INSERT)                             # Clone

# Level 3: Pattern compositions (refactoring)
EXTRACT = Compose(INSERT, UPDATE, INSERT)          # Extract entity
INLINE = Compose(UPDATE, DELETE)                   # Inline entity
WRAP = Compose(INSERT, UPDATE)                     # Add wrapper
UNWRAP = Compose(UPDATE, DELETE)                   # Remove wrapper

# Level 4: Complex compositions (migration, fixing)
MIGRATE_PATTERN = Compose(DELETE, INSERT*, UPDATE*)  # Idiom translation
ADD_GUARD = Compose(INSERT, UPDATE)                  # Safety check
CHANGE_SIGNATURE = Compose(UPDATE, UPDATE*)          # API change
```

---

### How Current 41 Operators Map to Primitives

| Current Operator | Primitive Composition |
|------------------|----------------------|
| ADD_METHOD | INSERT(node) + INSERT(edge) |
| REMOVE_METHOD | DELETE(node) |
| RENAME_METHOD | UPDATE(name) + UPDATE*(refs) |
| MOVE_METHOD | DELETE(edge) + INSERT(edge) + UPDATE*(refs) |
| EXTRACT_METHOD | INSERT(node) + INSERT(edge) + UPDATE(body) |
| INLINE_METHOD | UPDATE(call_sites) + DELETE(node) |
| PULL_UP_METHOD | DELETE(edge) + INSERT(edge) |
| PUSH_DOWN_METHOD | DELETE(edge) + INSERT(edge) |
| CHANGE_SIGNATURE | UPDATE(params) + UPDATE*(call_sites) |
| ADD_FIELD | INSERT(node) + INSERT(edge) |
| REMOVE_FIELD | DELETE(node) |
| ENCAPSULATE_FIELD | INSERT(getter) + INSERT(setter) + UPDATE*(refs) |
| ADD_IMPORT | INSERT(node) |
| REMOVE_IMPORT | DELETE(node) |
| UPDATE_IMPORT | UPDATE(target) |
| UPDATE_CALL | UPDATE(callee) |
| ... | ... |

**All 41 operators** reduce to combinations of INSERT, DELETE, UPDATE.

---

### Implementation Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER-FACING OPERATIONS                               │
│   Refactoring    Migration    Code Fixing    Upgrade    Security            │
│   ───────────    ─────────    ───────────    ───────    ────────            │
│   rename         translate    add_guard      deprecate  sanitize            │
│   extract        convert      fix_null       update_api add_auth            │
│   move           bridge       add_cleanup    migrate    encrypt             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DERIVED OPERATORS                                    │
│   RENAME  MOVE  EXTRACT  INLINE  WRAP  UNWRAP  REPLACE  COPY               │
│   (named compositions for common patterns)                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         THREE PRIMITIVES                                     │
│                                                                              │
│              INSERT          DELETE          UPDATE                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GRAPH REWRITING ENGINE                               │
│   DPO/SPO semantics    Gluing conditions    Preconditions                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LANGUAGE ADAPTERS                                    │
│   ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐              │
│   │ Python │  │   Go   │  │  Java  │  │  Rust  │  │   TS   │              │
│   └────────┘  └────────┘  └────────┘  └────────┘  └────────┘              │
│   Parse, emit syntax; map NodeKind/EdgeKind to language constructs          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Language Adapter Interface

```python
class LanguageAdapter(Protocol):
    """Minimal interface for language support."""

    language: str

    def parse(self, source: str) -> Graph:
        """Parse source code into universal graph."""
        ...

    def emit(self, graph: Graph) -> str:
        """Generate source code from graph."""
        ...

    def map_node(self, kind: NodeKind, attrs: dict) -> LanguageNode:
        """Map universal node to language-specific construct."""
        ...

    def map_position(self, pos: Position) -> LanguagePosition:
        """Map universal position to language-specific location."""
        ...
```

The adapter handles **syntax**; the primitives handle **semantics**.

---

### Benefits of This Design

| Aspect | Benefit |
|--------|---------|
| **Simplicity** | Only 3 operations to implement per language |
| **Composability** | Complex transforms built from simple parts |
| **Provability** | Easier to verify correctness of 3 ops than 41 |
| **Extensibility** | New transforms = new compositions, not new primitives |
| **Cross-language** | Same primitives work for any language |
| **Optimization** | Can optimize at primitive level (batch INSERTs, etc.) |

---

### Example: Cross-Language Migration

**Python async/await → Go goroutine**

```python
# High-level: MIGRATE_ASYNC_TO_GOROUTINE

def migrate_async_to_goroutine(async_func: NodeRef) -> list[Primitive]:
    return [
        # Remove async keyword
        UPDATE(async_func, "async", False),

        # For each await call, wrap in goroutine
        *[
            Compose(
                INSERT(Node(CALL, name="go", args=[await_expr.func])),
                INSERT(Node(CALLABLE, name="anonymous", body=await_expr)),
                DELETE(await_expr),
            )
            for await_expr in find_awaits(async_func)
        ],

        # Add channel for result
        INSERT(Node(BINDING, name="resultChan", type="chan Result")),

        # Update return to channel send
        UPDATE(return_stmt, kind="channel_send", target="resultChan"),
    ]
```

Same three primitives, completely different languages.

---

### Comparison: 41 Specific vs 3 Fundamental

| Approach | Operators | Languages | Use Cases | Maintenance |
|----------|-----------|-----------|-----------|-------------|
| Current (specific) | 41 | Python only | Refactoring only | O(operators × languages) |
| Fundamental (3) | 3 | Any | Any transformation | O(languages) |

**The math**:
- Current: 41 operators × N languages = 41N implementations
- Fundamental: 3 operators × N languages = 3N implementations + compositions

For 5 languages: 205 vs 15 + reusable compositions

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

### Phase 1: Three Primitives Core

**Goal**: Implement the fundamental INSERT, DELETE, UPDATE operators with DPO/SPO semantics.

```
src/graph_transform/
├── core/
│   ├── primitives.py            # INSERT, DELETE, UPDATE definitions
│   ├── position.py              # Universal position system
│   ├── node_kinds.py            # NodeKind, EdgeKind enums
│   └── graph.py                 # Universal graph representation
├── rewriting/
│   ├── engine.py                # DPO/SPO rewriting engine
│   ├── gluing.py                # Gluing condition checks
│   └── preconditions.py         # Pre/post condition validation
```

**Deliverables**:
- `Insert(element, position)` with scope/anchor/relation support
- `Delete(target, cascade)` with dangling edge handling
- `Update(target, property, value)` with reference propagation
- Formal verification of primitive correctness

---

### Phase 2: Derived Operators (Compositions)

**Goal**: Build standard refactoring/migration operators as compositions of primitives.

```
├── operators/
│   ├── compositions.py          # RENAME, MOVE, EXTRACT, INLINE, etc.
│   ├── refactoring.py           # Standard refactoring compositions
│   ├── migration.py             # Cross-language migration compositions
│   ├── fixing.py                # Code repair compositions
│   └── registry.py              # Operator registry and dispatch
```

**Composition Library**:

```python
# Example compositions defined declaratively
COMPOSITIONS = {
    "RENAME": [
        Update(target="$entity", property="name", value="$new_name"),
        ForEach("$ref", in_="references($entity)",
            Update(target="$ref", property="target_name", value="$new_name")
        ),
    ],

    "MOVE": [
        Delete(edge="($old_scope, CONTAINS, $entity)"),
        Insert(edge="($new_scope, CONTAINS, $entity)"),
        ForEach("$ref", in_="references($entity)",
            Update(target="$ref", property="qualified_path", value="$new_path")
        ),
    ],

    "EXTRACT_CALLABLE": [
        Insert(node="CALLABLE", attrs={"name": "$new_name", "body": "$code"}),
        Insert(edge="($scope, CONTAINS, $new_node)"),
        Update(target="$original", property="body",
               value="CALL($new_name, $captured_vars)"),
        Insert(edge="($original, CALLS, $new_node)"),
    ],
}
```

**Deliverables**:
- All 41 current operators expressed as compositions
- New operators: WRAP, UNWRAP, ADD_GUARD, MIGRATE_PATTERN
- Composition validation (verify primitive sequences are valid)

---

### Phase 3: Language Adapters

**Goal**: Implement parse/emit adapters for multiple languages.

```
├── adapters/
│   ├── base.py                  # LanguageAdapter protocol
│   ├── python/
│   │   ├── parser.py            # Python AST → Universal Graph
│   │   ├── emitter.py           # Universal Graph → Python source
│   │   └── mappings.py          # NodeKind → Python constructs
│   ├── go/
│   │   ├── parser.py
│   │   ├── emitter.py
│   │   └── mappings.py
│   ├── typescript/
│   │   ├── parser.py
│   │   ├── emitter.py
│   │   └── mappings.py
│   └── java/
│       ├── parser.py
│       ├── emitter.py
│       └── mappings.py
```

**Adapter Interface**:

```python
class LanguageAdapter(Protocol):
    language: str

    def parse(self, source: str) -> Graph:
        """Source code → Universal graph."""

    def emit(self, graph: Graph) -> str:
        """Universal graph → Source code."""

    def map_node(self, kind: NodeKind, attrs: dict) -> str:
        """NodeKind → Language-specific syntax."""

    def map_position(self, pos: Position) -> SourceLocation:
        """Universal position → Source location."""
```

**Deliverables**:
- Python adapter (refactor from current implementation)
- Go adapter
- TypeScript adapter
- Adapter test suite (round-trip: parse → emit → parse)

---

### Phase 4: Idiom Patterns & Migration

**Goal**: High-level pattern matching and cross-language migration.

```
├── patterns/
│   ├── matcher.py               # Pattern matching on universal graph
│   ├── dsl.py                   # Pattern definition DSL
│   └── library/                 # Pattern definitions (YAML)
│       ├── error_handling.yaml
│       ├── concurrency.yaml
│       ├── collections.yaml
│       └── frameworks/
│           ├── django_to_fastapi.yaml
│           └── react_class_to_hooks.yaml
├── migration/
│   ├── orchestrator.py          # Multi-phase execution
│   ├── plan.py                  # Migration plan model
│   ├── state.py                 # Progress tracking, checkpoints
│   ├── bridge.py                # FFI bridge generation
│   └── strategies/
│       ├── big_bang.py
│       ├── incremental.py
│       └── strangler.py
```

**Deliverables**:
- Pattern DSL for complex idiom matching
- Migration orchestrator with checkpointing
- Bridge generation for mixed-language codebases

---

### Phase 5: LLM Integration

**Goal**: Hybrid LLM + graph approach for ambiguous cases.

```
├── llm/
│   ├── interface.py             # Abstract LLM protocol
│   ├── planning.py              # LLM-assisted migration planning
│   ├── ambiguity.py             # Handle edge cases
│   └── verification.py          # Semantic equivalence checking
```

**Deliverables**:
- LLM fallback for low-confidence transformations
- LLM-assisted pattern suggestion
- Semantic equivalence verification

---

### CLI Commands

```bash
# === PRIMITIVE OPERATIONS ===
# Direct primitive execution (advanced users)
graph-transform primitive insert --node CALLABLE --name "foo" --scope "MyClass"
graph-transform primitive delete --target "MyClass.old_method"
graph-transform primitive update --target "my_func" --property "name" --value "new_name"

# === DERIVED OPERATIONS ===
# Standard refactoring (compositions)
graph-transform rename --target "old_name" --to "new_name" src/
graph-transform move --target "MyClass.method" --to "OtherClass" src/
graph-transform extract --from "my_func:10-20" --name "helper" src/

# === MIGRATION ===
# Cross-language migration
graph-transform migrate analyze src/ --from python --to go
graph-transform migrate plan src/ --from python:3.11 --to go:1.21 -o plan.yaml
graph-transform migrate run plan.yaml --checkpoint-dir .migration/
graph-transform migrate status plan.yaml
graph-transform migrate bridge src/api/ --manifest manifest.yaml

# === CODE FIXING ===
graph-transform fix null-checks src/
graph-transform fix resource-leaks src/
graph-transform fix deprecated-api --mapping api_changes.yaml src/

# === INSPECTION ===
graph-transform show-composition EXTRACT_METHOD
graph-transform list-operators --category refactoring
graph-transform list-adapters
```

---

## Summary: Three Primitives → Universal Code Transformation

| Layer | Components | Purpose |
|-------|------------|---------|
| **Primitives** | INSERT, DELETE, UPDATE | Atomic operations on graph |
| **Compositions** | RENAME, MOVE, EXTRACT, ... | Named sequences of primitives |
| **Patterns** | Idiom library, DSL | Complex multi-node transformations |
| **Adapters** | Python, Go, TS, Java, ... | Language-specific parse/emit |
| **Orchestration** | Migration engine | Large-scale transformation management |
| **LLM** | Fallback, verification | Handle ambiguity and creativity |

```
                    ┌─────────────────────────────────────────┐
                    │          ALL TRANSFORMATIONS            │
                    │  Refactoring • Migration • Fixing       │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         DERIVED OPERATORS               │
                    │  RENAME • MOVE • EXTRACT • INLINE • ... │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         THREE PRIMITIVES                │
                    │      INSERT  •  DELETE  •  UPDATE       │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         UNIVERSAL GRAPH                 │
                    │   NodeKind • EdgeKind • Position        │
                    └─────────────────┬───────────────────────┘
                                      │
          ┌───────────────┬───────────┴───────────┬───────────────┐
          ▼               ▼                       ▼               ▼
    ┌──────────┐    ┌──────────┐           ┌──────────┐    ┌──────────┐
    │  Python  │    │    Go    │           │    TS    │    │   Java   │
    │ Adapter  │    │ Adapter  │           │ Adapter  │    │ Adapter  │
    └──────────┘    └──────────┘           └──────────┘    └──────────┘
```

**The key insight**: By reducing everything to 3 primitives operating on a universal graph, we achieve:
- **Simplicity**: 3 operations to implement, not 41
- **Universality**: Same primitives for any language
- **Composability**: Complex transforms = primitive sequences
- **Provability**: Easier to verify correctness
- **Extensibility**: New transforms without new primitives
