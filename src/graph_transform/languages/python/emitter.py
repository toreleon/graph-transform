"""
Python Emitter

Generate and modify Python source code from TypedGraph or EditInstructions.
"""

from __future__ import annotations

import re
from typing import Any

from graph_transform.core.typed_graph import NodeType, TypedGraph
from graph_transform.languages.base import EditInstruction


class PythonEmitter:
    """Emitter for Python source code.

    Handles generating Python code from TypedGraph and applying
    edit instructions to existing Python source.
    """

    def emit(self, graph: TypedGraph, original_source: str | None = None) -> str:
        """Generate Python source code from a TypedGraph.

        Note: Full code generation from graph is complex and currently
        provides a skeleton implementation. For refactoring, prefer
        using apply_edit() for targeted changes.

        Args:
            graph: The TypedGraph to convert to source code.
            original_source: Optional original source for formatting hints.

        Returns:
            Generated Python source code.
        """
        lines: list[str] = []

        # Emit imports
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.IMPORT:
                attrs = node.attrs
                if attrs.get("is_from_import"):
                    module = attrs.get("module", "")
                    name = attrs.get("name", "")
                    alias = attrs.get("alias")
                    if alias:
                        lines.append(f"from {module} import {name} as {alias}")
                    else:
                        lines.append(f"from {module} import {name}")
                else:
                    module = attrs.get("module", "")
                    alias = attrs.get("alias")
                    if alias:
                        lines.append(f"import {module} as {alias}")
                    else:
                        lines.append(f"import {module}")

        if lines:
            lines.append("")

        # Emit classes
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.CLASS:
                class_lines = self._emit_class(graph, node_id)
                lines.extend(class_lines)
                lines.append("")

        # Emit module-level functions
        for node_id, node in graph.nodes.items():
            if node.node_type == NodeType.FUNCTION:
                if not node.attrs.get("is_method"):
                    func_lines = self._emit_function(graph, node_id, indent=0)
                    lines.extend(func_lines)
                    lines.append("")

        return "\n".join(lines)

    def _emit_class(self, graph: TypedGraph, class_id: str) -> list[str]:
        """Emit a class definition."""
        lines: list[str] = []
        node = graph.nodes[class_id]
        name = node.attrs.get("name", "Unknown")

        # Inheritance
        bases: list[str] = []
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type.name == "INHERITS":
                base_name = edge.target.replace("class:", "")
                bases.append(base_name)

        if bases:
            lines.append(f"class {name}({', '.join(bases)}):")
        else:
            lines.append(f"class {name}:")

        # Fields
        fields_emitted = False
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type.name == "CONTAINS_FIELD":
                field_node = graph.nodes.get(edge.target)
                if field_node and field_node.attrs.get("is_class_var"):
                    field_name = field_node.attrs.get("name", "")
                    field_type = field_node.attrs.get("field_type")
                    default = field_node.attrs.get("default_value")
                    if field_type and default:
                        lines.append(f"    {field_name}: {field_type} = {default}")
                    elif field_type:
                        lines.append(f"    {field_name}: {field_type}")
                    elif default:
                        lines.append(f"    {field_name} = {default}")
                    fields_emitted = True

        if fields_emitted:
            lines.append("")

        # Methods
        methods_emitted = False
        for edge in graph.edges:
            if edge.source == class_id and edge.edge_type.name == "CONTAINS_METHOD":
                func_lines = self._emit_function(graph, edge.target, indent=1)
                lines.extend(func_lines)
                lines.append("")
                methods_emitted = True

        if not fields_emitted and not methods_emitted:
            lines.append("    pass")

        return lines

    def _emit_function(self, graph: TypedGraph, func_id: str, indent: int = 0) -> list[str]:
        """Emit a function/method definition."""
        lines: list[str] = []
        prefix = "    " * indent
        node = graph.nodes[func_id]
        name = node.attrs.get("name", "unknown")
        is_async = node.attrs.get("is_async", False)

        # Collect parameters
        params: list[str] = []
        for edge in graph.edges:
            if edge.source == func_id and edge.edge_type.name == "HAS_PARAMETER":
                param_node = graph.nodes.get(edge.target)
                if param_node:
                    param_name = param_node.attrs.get("name", "")
                    has_default = param_node.attrs.get("has_default", False)
                    default_value = param_node.attrs.get("default_value")
                    if has_default and default_value:
                        params.append(f"{param_name}={default_value}")
                    else:
                        params.append(param_name)

        # Sort params by position
        # For simplicity, just join them
        params_str = ", ".join(params)

        keyword = "async def" if is_async else "def"
        lines.append(f"{prefix}{keyword} {name}({params_str}):")
        lines.append(f"{prefix}    pass")

        return lines

    def apply_edit(self, source: str, edit: EditInstruction) -> str:
        """Apply a single edit instruction to Python source code.

        Args:
            source: The original Python source code.
            edit: The edit instruction to apply.

        Returns:
            The modified source code.

        Raises:
            ValueError: If the edit cannot be applied.
        """
        edit_type = edit.edit_type.lower()

        if edit_type == "rename":
            return self._apply_rename(source, edit)
        elif edit_type == "add_callable" or edit_type == "add_function":
            return self._apply_add_function(source, edit)
        elif edit_type == "add_type" or edit_type == "add_class":
            return self._apply_add_class(source, edit)
        elif edit_type == "delete_node":
            return self._apply_delete(source, edit)
        elif edit_type == "update":
            return self._apply_update(source, edit)
        elif edit_type == "move":
            return self._apply_move(source, edit)
        else:
            # Unknown edit type - return source unchanged with warning
            return source

    def _apply_rename(self, source: str, edit: EditInstruction) -> str:
        """Apply a rename refactoring."""
        target = edit.details.get("target", "")
        new_name = edit.details.get("new_name", "")

        if not target or not new_name:
            return source

        # Extract old name from target (e.g., "func:old_name" -> "old_name")
        old_name = target.split(":")[-1]
        if "." in old_name:
            old_name = old_name.split(".")[-1]

        # Replace occurrences (word boundary aware)
        pattern = r"\b" + re.escape(old_name) + r"\b"
        return re.sub(pattern, new_name, source)

    def _apply_add_function(self, source: str, edit: EditInstruction) -> str:
        """Add a new function/method definition."""
        name = edit.details.get("name", "new_function")
        line = edit.line

        # Generate function stub
        func_code = f"\ndef {name}():\n    pass\n"

        if line is not None:
            lines = source.split("\n")
            # Insert after the specified line
            insert_idx = min(line, len(lines))
            lines.insert(insert_idx, func_code.strip())
            return "\n".join(lines)
        else:
            # Append to end
            return source.rstrip() + "\n" + func_code

    def _apply_add_class(self, source: str, edit: EditInstruction) -> str:
        """Add a new class definition."""
        name = edit.details.get("name", "NewClass")
        line = edit.line

        # Generate class stub
        class_code = f"\nclass {name}:\n    pass\n"

        if line is not None:
            lines = source.split("\n")
            insert_idx = min(line, len(lines))
            lines.insert(insert_idx, class_code.strip())
            return "\n".join(lines)
        else:
            return source.rstrip() + "\n" + class_code

    def _apply_delete(self, source: str, edit: EditInstruction) -> str:
        """Delete a node from source code."""
        # This is a simplified implementation
        # Full implementation would parse AST and remove the node
        node_id = edit.details.get("node_id", "")
        if not node_id:
            return source

        # Extract name to delete
        name = node_id.split(":")[-1]
        if "." in name:
            name = name.split(".")[-1]

        # Simple removal: remove lines containing def/class with that name
        lines = source.split("\n")
        result = []
        skip_block = False
        indent_to_skip = 0

        for line in lines:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)

            if skip_block:
                if stripped and current_indent <= indent_to_skip:
                    skip_block = False
                else:
                    continue

            if (stripped.startswith(f"def {name}(") or
                stripped.startswith(f"async def {name}(") or
                stripped.startswith(f"class {name}") or
                stripped.startswith(f"class {name}:")):
                skip_block = True
                indent_to_skip = current_indent
                continue

            result.append(line)

        return "\n".join(result)

    def _apply_update(self, source: str, edit: EditInstruction) -> str:
        """Update a property of an element."""
        target = edit.details.get("target", "")
        prop = edit.details.get("property", "")
        value = edit.details.get("value", "")

        if prop == "name":
            # Renaming - delegate to rename logic
            old_name = target.split(":")[-1]
            if "." in old_name:
                old_name = old_name.split(".")[-1]
            pattern = r"\b" + re.escape(old_name) + r"\b"
            return re.sub(pattern, str(value), source)

        # Other properties would require AST manipulation
        return source

    def _apply_move(self, source: str, edit: EditInstruction) -> str:
        """Move an element from one scope to another.

        This is a complex operation that would require full AST manipulation.
        Currently returns source unchanged.
        """
        # TODO: Implement move refactoring
        return source

    def apply_edits(self, source: str, edits: list[EditInstruction]) -> str:
        """Apply multiple edit instructions to source code.

        Args:
            source: The original source code.
            edits: List of edit instructions to apply.

        Returns:
            The modified source code.
        """
        result = source
        for edit in edits:
            result = self.apply_edit(result, edit)
        return result
