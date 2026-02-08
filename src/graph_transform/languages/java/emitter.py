"""
Java Emitter

Generate Java source code from TypedGraph.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graph_transform.core.typed_graph import EdgeType, NodeType, TypedGraph


# Python -> Java type mapping
TYPE_MAP = {
    "str": "String",
    "int": "int",
    "float": "double",
    "bool": "boolean",
    "list": "List<Object>",
    "list[str]": "List<String>",
    "list[int]": "List<Integer>",
    "dict": "Map<String, Object>",
    "dict[str, int]": "Map<String, Integer>",
    "dict[str, str]": "Map<String, String>",
    "None": "void",
    "bytes": "byte[]",
    "Any": "Object",
}


def to_camel_case(snake_str: str) -> str:
    """Convert snake_case to camelCase."""
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def to_pascal_case(snake_str: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(x.title() for x in snake_str.split("_"))


def map_type(py_type: str | None) -> str:
    """Map Python type to Java type."""
    if py_type is None:
        return "Object"

    # Handle generic types like list[str]
    py_type_lower = py_type.lower().strip()
    if py_type_lower in TYPE_MAP:
        return TYPE_MAP[py_type_lower]

    # Handle List[X] or list[X]
    match = re.match(r"(?:list|List)\[(\w+)\]", py_type)
    if match:
        inner = map_type(match.group(1))
        # Wrap primitives in boxed types for generics
        if inner == "int":
            inner = "Integer"
        elif inner == "double":
            inner = "Double"
        elif inner == "boolean":
            inner = "Boolean"
        return f"List<{inner}>"

    # Handle Dict[K, V]
    match = re.match(r"(?:dict|Dict)\[(\w+),\s*(\w+)\]", py_type)
    if match:
        key = map_type(match.group(1))
        val = map_type(match.group(2))
        return f"Map<{key}, {val}>"

    # Return as-is (might be a class name)
    return py_type


class JavaEmitter:
    """Emitter for Java source code from TypedGraph."""

    def __init__(self):
        self._imports: set[str] = set()

    def emit(self, graph: TypedGraph, output_dir: str | Path | None = None) -> dict[str, str]:
        """Generate Java source files from a TypedGraph.

        Args:
            graph: The TypedGraph to convert.
            output_dir: Optional directory to write files. If None, returns dict only.

        Returns:
            Dictionary mapping filename to Java source code.
        """
        files: dict[str, str] = {}
        self._imports = set()

        # Find all classes
        classes = {
            nid: n for nid, n in graph.nodes.items()
            if n.node_type == NodeType.CLASS
        }

        # Emit each class to its own file
        for class_id, class_node in classes.items():
            name = class_node.attrs.get("name", "Unknown")
            java_code = self._emit_class(graph, class_id)
            filename = f"{name}.java"
            files[filename] = java_code

        # Find module-level functions
        module_funcs = {
            nid: n for nid, n in graph.nodes.items()
            if n.node_type == NodeType.FUNCTION and not n.attrs.get("is_method")
        }

        if module_funcs:
            # Find module name
            module_name = "Main"
            for nid, n in graph.nodes.items():
                if n.node_type == NodeType.MODULE:
                    module_name = to_pascal_case(n.attrs.get("name", "Main"))
                    break

            java_code = self._emit_module_class(graph, module_name, module_funcs)
            files[f"{module_name}.java"] = java_code

        # Write files if output_dir provided
        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            for filename, content in files.items():
                (out_path / filename).write_text(content)

        return files

    def _emit_class(self, graph: TypedGraph, class_id: str) -> str:
        """Emit a single class as a Java file."""
        lines: list[str] = []
        self._imports = {"java.util.List", "java.util.Map", "java.util.ArrayList", "java.util.HashMap"}

        node = graph.nodes[class_id]
        name = node.attrs.get("name", "Unknown")

        # Find parent class
        parent = None
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type == EdgeType.INHERITS:
                parent = edge.target.replace("class:", "")
                break

        # Collect fields
        fields: list[tuple[str, str, str | None]] = []  # (name, type, default)
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type == EdgeType.CONTAINS_FIELD:
                field = graph.nodes.get(edge.target)
                if field:
                    fname = field.attrs.get("name", "")
                    ftype = map_type(field.attrs.get("field_type"))
                    default = field.attrs.get("default_value")
                    fields.append((fname, ftype, default))

        # Collect methods
        methods: list[tuple[str, dict]] = []
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type == EdgeType.CONTAINS_METHOD:
                func = graph.nodes.get(edge.target)
                if func:
                    mname = func.attrs.get("name", "")
                    if not mname.startswith("__"):  # Skip dunder methods
                        methods.append((edge.target, func.attrs))

        # Build imports
        import_lines = sorted(f"import {imp};" for imp in self._imports)

        # Build class
        class_lines = []
        if parent:
            class_lines.append(f"public class {name} extends {parent} {{")
        else:
            class_lines.append(f"public class {name} {{")

        # Fields
        for fname, ftype, default in fields:
            java_name = to_camel_case(fname)
            if default is not None:
                # Convert Python literals to Java
                java_default = self._convert_literal(default)
                class_lines.append(f"    private {ftype} {java_name} = {java_default};")
            else:
                class_lines.append(f"    private {ftype} {java_name};")

        if fields:
            class_lines.append("")

        # Constructor for fields from __init__
        init_fields = self._get_init_fields(graph, class_id)
        if init_fields:
            class_lines.append(f"    public {name}() {{")
            for fname, _ in init_fields:
                class_lines.append(f"        this.{to_camel_case(fname)} = null;")
            class_lines.append("    }")
            class_lines.append("")

        # Methods
        for method_id, method_attrs in methods:
            method_lines = self._emit_method(graph, method_id, method_attrs)
            class_lines.extend(method_lines)
            class_lines.append("")

        class_lines.append("}")

        # Combine
        lines.extend(import_lines)
        if import_lines:
            lines.append("")
        lines.extend(class_lines)

        return "\n".join(lines)

    def _emit_method(self, graph: TypedGraph, method_id: str, attrs: dict) -> list[str]:
        """Emit a method definition."""
        lines: list[str] = []
        name = attrs.get("name", "unknown")
        java_name = to_camel_case(name)
        is_async = attrs.get("is_async", False)

        # Collect parameters (skip 'self')
        params: list[tuple[str, str]] = []  # (name, type)
        for edge in graph.edges:
            if edge.source == method_id and edge.edge_type == EdgeType.HAS_PARAMETER:
                param = graph.nodes.get(edge.target)
                if param:
                    pname = param.attrs.get("name", "")
                    if pname != "self":
                        # Try to infer type from name or annotation
                        ptype = self._infer_param_type(pname)
                        params.append((pname, ptype))

        params_str = ", ".join(f"{ptype} {to_camel_case(pname)}" for pname, ptype in params)

        # Infer return type
        ret_type = self._infer_return_type(name, params)

        if is_async:
            lines.append(f"    // async in Python")
        lines.append(f"    public {ret_type} {java_name}({params_str}) {{")
        lines.append(f"        // TODO: Implement - migrated from Python")
        if ret_type != "void":
            if ret_type.startswith("List"):
                lines.append(f"        return new ArrayList<>();")
            elif ret_type.startswith("Map"):
                lines.append(f"        return new HashMap<>();")
            elif ret_type == "String":
                lines.append(f"        return \"\";")
            elif ret_type in ("int", "double", "float"):
                lines.append(f"        return 0;")
            elif ret_type == "boolean":
                lines.append(f"        return false;")
            else:
                lines.append(f"        return null;")
        lines.append("    }")

        return lines

    def _emit_module_class(
        self, graph: TypedGraph, class_name: str, funcs: dict
    ) -> str:
        """Emit module-level functions as a utility class."""
        lines: list[str] = []
        self._imports = {"java.util.List", "java.util.Map", "java.util.ArrayList", "java.util.HashMap"}

        import_lines = sorted(f"import {imp};" for imp in self._imports)
        lines.extend(import_lines)
        if import_lines:
            lines.append("")

        lines.append(f"public class {class_name} {{")

        for func_id, func in funcs.items():
            name = func.attrs.get("name", "unknown")
            java_name = to_camel_case(name)

            # Get parameters
            params: list[str] = []
            for edge in graph.edges:
                if edge.source == func_id and edge.edge_type == EdgeType.HAS_PARAMETER:
                    param = graph.nodes.get(edge.target)
                    if param:
                        pname = param.attrs.get("name", "")
                        ptype = self._infer_param_type(pname)
                        params.append(f"{ptype} {to_camel_case(pname)}")

            params_str = ", ".join(params)

            # Special handling for main
            if name == "main":
                lines.append("    public static void main(String[] args) {")
                lines.append("        // TODO: Implement - migrated from Python")
                lines.append("    }")
            else:
                lines.append(f"    public static void {java_name}({params_str}) {{")
                lines.append("        // TODO: Implement - migrated from Python")
                lines.append("    }")
            lines.append("")

        lines.append("}")

        return "\n".join(lines)

    def _get_init_fields(self, graph: TypedGraph, class_id: str) -> list[tuple[str, str]]:
        """Get fields defined in __init__."""
        fields = []
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type == EdgeType.CONTAINS_FIELD:
                field = graph.nodes.get(edge.target)
                if field and not field.attrs.get("is_class_var"):
                    fname = field.attrs.get("name", "")
                    ftype = map_type(field.attrs.get("field_type"))
                    fields.append((fname, ftype))
        return fields

    def _infer_param_type(self, param_name: str) -> str:
        """Infer Java type from parameter name."""
        name_lower = param_name.lower()
        if name_lower in ("host", "name", "query", "path", "url", "message", "text"):
            return "String"
        if name_lower in ("count", "size", "index", "id", "num", "number"):
            return "int"
        if name_lower in ("enabled", "active", "flag", "is_valid"):
            return "boolean"
        if name_lower in ("data", "items", "results", "values"):
            return "List<Object>"
        if name_lower in ("config", "options", "params", "kwargs"):
            return "Map<String, Object>"
        return "Object"

    def _infer_return_type(self, method_name: str, params: list) -> str:
        """Infer return type from method name."""
        name_lower = method_name.lower()
        if name_lower.startswith("get_") or name_lower.startswith("fetch_"):
            if "data" in name_lower or "list" in name_lower or "all" in name_lower:
                return "List<Object>"
            return "Object"
        if name_lower.startswith("is_") or name_lower.startswith("has_") or name_lower.startswith("can_"):
            return "boolean"
        if name_lower == "process" or name_lower.endswith("_to_dict"):
            return "Map<String, Object>"
        if name_lower in ("connect", "disconnect", "close", "open", "start", "stop"):
            return "void"
        if name_lower == "count" or name_lower.startswith("count_"):
            return "int"
        return "void"

    def _convert_literal(self, value: str) -> str:
        """Convert Python literal to Java literal."""
        if value == "True":
            return "true"
        if value == "False":
            return "false"
        if value == "None":
            return "null"
        if value.startswith('"') or value.startswith("'"):
            # String literal - use double quotes
            return f'"{value[1:-1]}"'
        if value.startswith("["):
            return "new ArrayList<>()"
        if value.startswith("{"):
            return "new HashMap<>()"
        return value
