"""
Python Parser

Parse Python source code into TypedGraph using the stdlib ast module.
This is the core parsing logic extracted from io/builder.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

from graph_transform.core.typed_graph import EdgeType, GraphEdge, GraphNode, NodeType, TypedGraph


class PythonParser:
    """Parser for Python source code.

    Uses the stdlib ast module to parse Python source code into a TypedGraph.
    This class provides the core parsing functionality used by PythonAdapter.
    """

    def parse(self, source: str, filename: str = "<source>") -> TypedGraph:
        """Parse Python source code into a TypedGraph.

        Args:
            source: The Python source code as a string.
            filename: The filename for error messages and node metadata.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            SyntaxError: If the source code cannot be parsed.
        """
        tree = ast.parse(source, filename=filename)
        graph = TypedGraph()
        builder = _ASTGraphBuilder(filename, graph)
        builder.visit(tree)
        builder.finalize_exports()  # Create EXPORTS edges after all nodes exist
        return graph

    def parse_file(self, file_path: str | Path) -> TypedGraph:
        """Parse a Python file into a TypedGraph.

        Args:
            file_path: Path to the Python file.

        Returns:
            A TypedGraph representing the code structure.

        Raises:
            FileNotFoundError: If the file does not exist.
            SyntaxError: If the source code cannot be parsed.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        source = path.read_text()
        return self.parse(source, str(file_path))


class _ASTGraphBuilder(ast.NodeVisitor):
    """AST visitor that builds a TypedGraph from Python source.

    This class walks the Python AST and creates corresponding nodes and edges
    in the TypedGraph. It handles:
    - Module, class, and function definitions
    - Method parameters
    - Class fields (from __init__ and class-level annotations)
    - Call sites and arguments
    - Imports
    """

    def __init__(self, file_path: str, graph: TypedGraph) -> None:
        self.file = file_path
        self.graph = graph
        self._current_class: str | None = None
        self._current_func: str | None = None
        self._call_counter = 0
        self._pending_exports: list[str] = []  # Store __all__ symbols for deferred edge creation

        # Add module node
        # Derive dotted module path from file path (e.g., lib/ansible/inventory/manager.py -> ansible.inventory.manager)
        mod_name = self._derive_module_name(file_path)
        self._module_id = f"module:{mod_name}"
        if not graph.has_node(self._module_id):
            graph.add_node(GraphNode(
                id=self._module_id,
                node_type=NodeType.MODULE,
                attrs={"name": mod_name, "file": file_path},
            ))

    def _derive_module_name(self, file_path: str) -> str:
        """Derive a dotted module name from a file path.

        Examples:
            lib/ansible/inventory/manager.py -> ansible.inventory.manager
            src/requests/utils.py -> requests.utils
            tornado/netutil.py -> tornado.netutil
            /tmp/.../mod.py -> mod (temp files use just the stem)
        """
        path = Path(file_path)
        parts = list(path.with_suffix("").parts)

        # For absolute paths in temp directories, just use the stem
        # This handles pytest tmp_path and similar
        if path.is_absolute():
            for i, part in enumerate(parts):
                if part.startswith("tmp") or part == "tmp":
                    # It's a temp path, just use the file stem
                    return path.stem

        # Remove common source directory prefixes
        prefixes_to_remove = {"lib", "src", "source", "sources"}
        while parts and parts[0].lower() in prefixes_to_remove:
            parts = parts[1:]

        # Also remove leading path separators or root
        while parts and (parts[0] == "" or parts[0] == "/"):
            parts = parts[1:]

        # If no parts left, use the stem
        if not parts:
            return path.stem

        return ".".join(parts)

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

        # Defined in module - add both DEFINED_IN (class -> module) and CONTAINS (module -> class)
        self.graph.add_edge(GraphEdge(cls_id, self._module_id, EdgeType.DEFINED_IN))
        self.graph.add_edge(GraphEdge(self._module_id, cls_id, EdgeType.CONTAINS))

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
            # Add both DEFINED_IN (func -> module) and CONTAINS (module -> func) for compatibility
            self.graph.add_edge(GraphEdge(func_id, self._module_id, EdgeType.DEFINED_IN))
            self.graph.add_edge(GraphEdge(self._module_id, func_id, EdgeType.CONTAINS))

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
                    "call_type": "method" if isinstance(node.func, ast.Attribute) else "direct",
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

    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle assignments, specifically __all__ at module level."""
        # Only process module-level __all__ assignments
        if self._current_class is None and self._current_func is None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    # Parse __all__ value
                    all_symbols = self._parse_all_value(node.value)
                    if all_symbols is not None:
                        # Store __all__ as module attribute
                        mod_node = self.graph.get_node(self._module_id)
                        if mod_node:
                            mod_node.attrs["__all__"] = all_symbols
                            mod_node.attrs["__all__line"] = node.lineno

                        # Store symbols for deferred EXPORTS edge creation
                        # (nodes may not exist yet since __all__ is typically at the top)
                        self._pending_exports.extend(all_symbols)
        self.generic_visit(node)

    def finalize_exports(self) -> None:
        """Create EXPORTS edges for __all__ symbols after all nodes have been added."""
        for symbol in self._pending_exports:
            # Look for function or class with this name
            func_id = f"func:{symbol}"
            cls_id = f"class:{symbol}"
            if self.graph.has_node(func_id):
                self.graph.add_edge(GraphEdge(
                    self._module_id, func_id, EdgeType.EXPORTS
                ))
            elif self.graph.has_node(cls_id):
                self.graph.add_edge(GraphEdge(
                    self._module_id, cls_id, EdgeType.EXPORTS
                ))

    def _parse_all_value(self, node: ast.expr) -> list[str] | None:
        """Parse the value of an __all__ assignment."""
        # Handle both list and tuple forms of __all__
        if isinstance(node, (ast.List, ast.Tuple)):
            symbols = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    symbols.append(elt.value)
            return symbols
        return None

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "") if node.level else (node.module or "")
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
