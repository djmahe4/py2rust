from . import BasePlugin
from ..frontend.ast_nodes import TypeVarType, ClassType, GenericType, Assign, FunctionCall, Name, PassStmt

class TypingPlugin(BasePlugin):
    @property
    def module_name(self) -> str:
        return "typing"

    def register(self, st) -> None:
        # Register TypeVar as a callable that returns TypeVarType
        from ..frontend.ast_nodes import StrType
        st.define_function("TypeVar", [StrType()], TypeVarType("T"), is_async=False)
        st.define("Protocol", ClassType(name="Protocol"))

    def transform_ast(self, node, checker):
        if isinstance(node, Assign):
            if isinstance(node.value, FunctionCall) and node.value.name == "TypeVar":
                # intercepted T = TypeVar('T')
                target_name = node.target if isinstance(node.target, str) else node.target.name
                checker.st.define(target_name, TypeVarType(name=target_name))
                return PassStmt(line=node.line, col=node.col)
        
        if isinstance(node, GenericType):
            return node
        return node
