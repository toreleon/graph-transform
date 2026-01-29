"""
Graph Builder

Build a TypedGraph from Python source files using AST parsing.
No external dependencies -- uses only the stdlib ast module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph


def build_graph_from_source(source_path: str | Path) -> TypedGraph:
    """Build a TypedGraph from a Python source file or directory.

    If source_path is a directory, recursively processes all .py files
    and produces a single unified TypedGraph.

    Args:
        source_path: Path to a .py file or a directory.

    Returns:
        A TypedGraph representing the code structure.

    Raises:
        FileNotFoundError: If the path does not exist.
        SyntaxError: If a Python file cannot be parsed.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {source_path}")

    graph = TypedGraph()

    if path.is_file():
        _build_from_file(path, graph)
    elif path.is_dir():
        py_files = sorted(path.rglob("*.py"))
        if not py_files:
            raise FileNotFoundError(f"No .py files found in: {source_path}")
        for py_file in py_files:
            _build_from_file(py_file, graph)
    else:
        raise ValueError(f"Path is neither a file nor a directory: {source_path}")

    return graph


def _build_from_file(file_path: Path, graph: TypedGraph) -> None:
    """Parse a single Python file and add its nodes/edges to graph."""
    source = file_path.read_text()
    tree = ast.parse(source, filename=str(file_path))
    builder = _ASTGraphBuilder(str(file_path), graph)
    builder.visit(tree)


class _ASTGraphBuilder(ast.NodeVisitor):
    """AST visitor that builds a TypedGraph from Python source."""

    def __init__(self, file_path: str, graph: TypedGraph) -> None:
        self.file = file_path
        self.graph = graph
        self._current_class: str | None = None
        self._current_func: str | None = None
        self._call_counter = 0

        # Add module node
        mod_name = Path(file_path).stem
        self._module_id = f"module:{mod_name}"
        if not graph.has_node(self._module_id):
            graph.add_node(GraphNode(
                id=self._module_id,
                node_type=NodeType.MODULE,
                attrs={"name": mod_name, "file": file_path},
            ))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        cls_id = f"class:{node.name}"
        self.graph.add_node(GraphNode(
            id=cls_id,
            node_type=NodeType.CLASS,
            attrs={
                "name": node.name,
                "file": self.file,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", None),
                "is_abstract": _is_abstract_class(node),
            },
        ))

        # Defined in module
        self.graph.add_edge(GraphEdge(cls_id, self._module_id, EdgeType.DEFINED_IN))

        # Inheritance
        for base in node.bases:
            base_name = _resolve_name(base)
            if base_name:
                base_id = f"class:{base_name}"
                self.graph.add_edge(GraphEdge(cls_id, base_id, EdgeType.INHERITS))

        # Visit children with class context
        prev_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool = False
    ) -> None:
        is_method = self._current_class is not None
        func_name = node.name
        func_id = f"func:{func_name}"

        # Avoid ID collisions for methods with the same name in different classes
        if is_method:
            func_id = f"func:{self._current_class}.{func_name}"

        self.graph.add_node(GraphNode(
            id=func_id,
            node_type=NodeType.FUNCTION,
            attrs={
                "name": func_name,
                "file": self.file,
                "line": node.lineno,
                "end_line": getattr(node, "end_lineno", None),
                "is_method": is_method,
                "is_async": is_async or isinstance(node, ast.AsyncFunctionDef),
            },
        ))

        # Link to class or module
        if is_method and self._current_class:
            cls_id = f"class:{self._current_class}"
            self.graph.add_edge(GraphEdge(cls_id, func_id, EdgeType.CONTAINS_METHOD))
        else:
            self.graph.add_edge(GraphEdge(func_id, self._module_id, EdgeType.DEFINED_IN))

        # Parameters
        self._add_parameters(func_id, node)

        # Fields (class-level assignments in __init__)
        if is_method and func_name == "__init__" and self._current_class:
            self._extract_fields(node, self._current_class)

        # Visit function body for calls
        prev_func = self._current_func
        self._current_func = func_id
        self.generic_visit(node)
        self._current_func = prev_func

    def _add_parameters(
        self, func_id: str, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        """Add parameter nodes from function arguments."""
        args = node.args

        # Collect all parameters in order
        all_params: list[tuple[str, int, bool, str | None, bool]] = []
        # (name, position, has_default, default_value, is_keyword_only)

        # Positional args
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        for i, arg in enumerate(args.args):
            default_idx = i - (num_args - num_defaults)
            has_default = default_idx >= 0
            default_value = None
            if has_default:
                default_value = _ast_to_str(args.defaults[default_idx])
            all_params.append((arg.arg, i, has_default, default_value, False))

        # Keyword-only args
        offset = len(args.args)
        for i, arg in enumerate(args.kwonlyargs):
            default_node = args.kw_defaults[i] if i < len(args.kw_defaults) else None
            has_default = default_node is not None
            default_value = _ast_to_str(default_node) if default_node else None
            all_params.append((arg.arg, offset + i, has_default, default_value, True))

        for name, position, has_default, default_value, is_kw_only in all_params:
            param_id = f"param:{func_id.split(':', 1)[1]}.{name}"
            self.graph.add_node(GraphNode(
                id=param_id,
                node_type=NodeType.PARAMETER,
                attrs={
                    "name": name,
                    "position": position,
                    "has_default": has_default,
                    "default_value": default_value,
                    "is_keyword_only": is_kw_only,
                },
            ))
            self.graph.add_edge(GraphEdge(func_id, param_id, EdgeType.HAS_PARAMETER))

    def _extract_fields(self, node: ast.FunctionDef, class_name: str) -> None:
        """Extract self.x = ... assignments from __init__ as fields."""
        for stmt in ast.walk(node):
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    field_name = target.attr
                    field_id = f"field:{class_name}.{field_name}"
                    if not self.graph.has_node(field_id):
                        self.graph.add_node(GraphNode(
                            id=field_id,
                            node_type=NodeType.FIELD,
                            attrs={
                                "name": field_name,
                                "file": self.file,
                                "line": stmt.lineno,
                                "class_name": class_name,
                                "field_type": None,
                                "has_default": True,
                                "default_value": _ast_to_str(stmt.value),
                                "is_class_var": False,
                            },
                        ))
                        cls_id = f"class:{class_name}"
                        self.graph.add_edge(GraphEdge(
                            cls_id, field_id, EdgeType.CONTAINS_FIELD
                        ))

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle annotated class-level assignments (class variables/fields)."""
        if self._current_class and self._current_func is None:
            target = node.target
            if isinstance(target, ast.Name):
                field_name = target.id
                field_id = f"field:{self._current_class}.{field_name}"
                if not self.graph.has_node(field_id):
                    field_type = _ast_to_str(node.annotation) if node.annotation else None
                    has_default = node.value is not None
                    default_value = _ast_to_str(node.value) if node.value else None
                    self.graph.add_node(GraphNode(
                        id=field_id,
                        node_type=NodeType.FIELD,
                        attrs={
                            "name": field_name,
                            "file": self.file,
                            "line": node.lineno,
                            "class_name": self._current_class,
                            "field_type": field_type,
                            "has_default": has_default,
                            "default_value": default_value,
                            "is_class_var": True,
                        },
                    ))
                    cls_id = f"class:{self._current_class}"
                    self.graph.add_edge(GraphEdge(
                        cls_id, field_id, EdgeType.CONTAINS_FIELD
                    ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Record call sites."""
        callee = _resolve_name(node.func)
        if callee:
            self._call_counter += 1
            call_id = f"call:{self.file}:{node.lineno}:{self._call_counter}"
            caller = self._current_func

            self.graph.add_node(GraphNode(
                id=call_id,
                node_type=NodeType.CALL,
                attrs={
                    "callee": callee,
                    "file": self.file,
                    "line": node.lineno,
                    "caller": caller,
                    "is_method_call": isinstance(node.func, ast.Attribute),
                },
            ))

            # Edge: call -> callee function
            callee_id = f"func:{callee}"
            if self.graph.has_node(callee_id):
                self.graph.add_edge(GraphEdge(call_id, callee_id, EdgeType.CALLS))

            # Edge: caller -> call
            if caller and self.graph.has_node(caller):
                self.graph.add_edge(GraphEdge(caller, call_id, EdgeType.CALLER_OF))

            # Arguments
            for i, arg_node in enumerate(node.args):
                arg_id = f"arg:{call_id}.pos{i}"
                self.graph.add_node(GraphNode(
                    id=arg_id,
                    node_type=NodeType.ARGUMENT,
                    attrs={
                        "position": i,
                        "name": None,
                        "value": _ast_to_str(arg_node),
                        "is_keyword": False,
                    },
                ))
                self.graph.add_edge(GraphEdge(call_id, arg_id, EdgeType.HAS_ARGUMENT))

            for kw in node.keywords:
                kw_name = kw.arg or "**"
                arg_id = f"arg:{call_id}.{kw_name}"
                self.graph.add_node(GraphNode(
                    id=arg_id,
                    node_type=NodeType.ARGUMENT,
                    attrs={
                        "name": kw_name,
                        "value": _ast_to_str(kw.value),
                        "is_keyword": True,
                    },
                ))
                self.graph.add_edge(GraphEdge(call_id, arg_id, EdgeType.HAS_ARGUMENT))

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            imp_name = alias.asname or alias.name
            imp_id = f"import:{self.file}:{imp_name}"
            self.graph.add_node(GraphNode(
                id=imp_id,
                node_type=NodeType.IMPORT,
                attrs={
                    "module": alias.name,
                    "name": None,
                    "alias": alias.asname,
                    "file": self.file,
                    "line": node.lineno,
                    "is_from_import": False,
                },
            ))
            self.graph.add_edge(GraphEdge(
                self._module_id, imp_id, EdgeType.IMPORTS
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in (node.names or []):
            imp_name = alias.asname or alias.name
            imp_id = f"import:{self.file}:{imp_name}"
            self.graph.add_node(GraphNode(
                id=imp_id,
                node_type=NodeType.IMPORT,
                attrs={
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "file": self.file,
                    "line": node.lineno,
                    "is_from_import": True,
                },
            ))
            self.graph.add_edge(GraphEdge(
                self._module_id, imp_id, EdgeType.IMPORTS
            ))


# =============================================================================
# Helpers
# =============================================================================


def _resolve_name(node: ast.expr) -> str | None:
    """Resolve a Name or Attribute AST node to a dotted string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _ast_to_str(node: ast.expr | None) -> str | None:
    """Best-effort conversion of an AST expression to its source string."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _is_abstract_class(node: ast.ClassDef) -> bool:
    """Heuristic: class is abstract if it inherits from ABC or has abstractmethod."""
    for base in node.bases:
        name = _resolve_name(base)
        if name and name in ("ABC", "ABCMeta"):
            return True
    for item in ast.walk(node):
        if isinstance(item, ast.FunctionDef):
            for dec in item.decorator_list:
                dec_name = _resolve_name(dec)
                if dec_name and "abstract" in dec_name.lower():
                    return True
    return False
