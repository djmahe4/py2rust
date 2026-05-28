from . import BasePlugin
from ..frontend.ast_nodes import ExternalPythonType, DequeType, ClassType, FunctionCall, Name, MethodCall

class CollectionsPlugin(BasePlugin):
    """
    Plugin for the standard 'collections' library.
    Primarily supports 'deque' by mapping it to DequeType.
    """
    
    @property
    def module_name(self) -> str:
        return "collections"
    
    def register(self, st):
        # Register collections module
        st.register_external_name("collections", ExternalPythonType(module="collections"))
        # Register deque explicitly if needed
        st.register_external_name("deque", ExternalPythonType(module="collections", name="deque"))

    def transform_ast(self, node, checker):
        # Intercept deque() calls
        if isinstance(node, FunctionCall):
            is_deque = False
            if isinstance(node.name, str):
                if node.name == "deque":
                    is_deque = True
                elif node.name == "collections.deque":
                    is_deque = True
            
            if is_deque:
                # We can't fully infer the element type here without deeper analysis,
                # but we can return a DequeType placeholder or a specialized FunctionCall.
                # For now, let's keep it as is and let the Inferencer handle it if it can.
                pass

        return node
