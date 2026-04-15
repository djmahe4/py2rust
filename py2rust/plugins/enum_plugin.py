from . import BasePlugin
from ..frontend.ast_nodes import ClassDef, EnumDef, ClassType

class EnumPlugin(BasePlugin):
    @property
    def module_name(self) -> str:
        return "enum"

    def register(self, st) -> None:
        st.define_class("Enum", bases=[], fields={}, methods={}, constructors={0: (None, "Enum")})
        st.define_class("IntEnum", bases=["Enum"], fields={}, methods={}, constructors={0: (None, "IntEnum")})

    def transform_ast(self, node, checker):
        if isinstance(node, ClassDef):
            if "Enum" in node.bases or "IntEnum" in node.bases:
                variants = []
                for stmt in node.body:
                    from ..frontend.ast_nodes import Assign, VarDecl
                    if isinstance(stmt, (Assign, VarDecl)):
                        name = stmt.target if isinstance(stmt, Assign) else stmt.name
                        if isinstance(name, str):
                            variants.append((name, stmt.value))
                
                return EnumDef(
                    name=node.name,
                    variants=tuple(variants),
                    line=node.line,
                    col=node.col,
                )
        return node
