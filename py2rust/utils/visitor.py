from __future__ import annotations


class NodeVisitor:
    """Generic visitor pattern for walking AST/IR nodes."""

    def visit(self, node):
        cls_name = type(node).__name__
        method = getattr(self, f"visit_{cls_name}", None)
        if method:
            return method(node)
        return self.generic_visit(node)

    def generic_visit(self, node):
        from dataclasses import fields, is_dataclass
        if is_dataclass(node):
            for f in fields(node):
                val = getattr(node, f.name)
                if isinstance(val, (list, tuple)):
                    for item in val:
                        if hasattr(item, "__dataclass_fields__"):
                            self.visit(item)
                elif hasattr(val, "__dataclass_fields__"):
                    self.visit(val)
        return None


class NodeTransformer(NodeVisitor):
    """Generic transformer pattern for modifying AST/IR nodes."""

    def visit(self, node):
        cls_name = type(node).__name__
        method = getattr(self, f"visit_{cls_name}", None)
        if method:
            return method(node)
        return self.generic_visit(node)

    def generic_visit(self, node):
        from dataclasses import fields, is_dataclass, replace
        if not is_dataclass(node):
            return node

        changes = {}
        for f in fields(node):
            val = getattr(node, f.name)
            if isinstance(val, (list, tuple)):
                new_list = []
                for item in val:
                    if hasattr(item, "__dataclass_fields__"):
                        new_item = self.visit(item)
                        if new_item is not None:
                            new_list.append(new_item)
                    else:
                        new_list.append(item)
                changes[f.name] = type(val)(new_list)
            elif hasattr(val, "__dataclass_fields__"):
                new_val = self.visit(val)
                changes[f.name] = new_val

        if not changes:
            return node
        return replace(node, **changes)
