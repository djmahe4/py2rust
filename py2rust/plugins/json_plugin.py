from . import BasePlugin
from ..frontend.ast_nodes import ExternalPythonType

class JSONPlugin(BasePlugin):
    """
    Plugin for the standard 'json' library.
    Maps it to the ExternalPythonType for now, but registers 
    serde/serde_json requirements for the generated Rust project.
    """
    
    @property
    def module_name(self) -> str:
        return "json"
    
    def register(self, st):
        from ..frontend.ast_nodes import ClassType, StrType, UnknownType
        # Register standard 'json' module
        st.register_external_name("json", ExternalPythonType(module="json"))
        
        # Register native helpers used by the plugin
        # json.loads(s) -> ExternalObject
        st.define_function("__py2rust_native_json_loads", [StrType()], ClassType("ExternalObject"))
        # json.dumps(obj) -> str
        st.define_function("__py2rust_native_json_dumps", [UnknownType()], StrType())


    def transform_ast(self, node, checker):
        from ..frontend.ast_nodes import FunctionCall, MethodCall, Name, ExternalPythonType
        import sys
        
        # Helper to check if a symbol is a specific json function
        def is_json_func(node):
            if isinstance(node, Name):
                # print(f"Checking Name: {node.name}", file=sys.stderr)
                # Handle direct calls if they were imported via 'from json import loads'
                symbol = checker.st.lookup(node.name)
                if isinstance(symbol, ExternalPythonType) and symbol.module == "json":
                    return symbol.name
                # Also check for 'json.loads' string name which might exist before full resolution
                if node.name.startswith("json."):
                    return node.name.split(".", 1)[1]
            return None

        # Intercept loads/dumps calls
        if isinstance(node, FunctionCall):
            func_name = is_json_func(Name(node.name)) if isinstance(node.name, str) else None
            if func_name in ("loads", "dumps"):
                return FunctionCall(
                    name=f"__py2rust_native_json_{func_name}",
                    args=node.args,
                    line=node.line,
                    col=node.col
                )
        
        # Intercept attribute access if it's json.loads/dumps (e.g. j.loads(...))
        if isinstance(node, MethodCall):
            if isinstance(node.value, Name):
                symbol = checker.st.lookup(node.value.name)
                # If the base object is the 'json' module (possibly renamed)
                if isinstance(symbol, ExternalPythonType) and symbol.module == "json":
                    if node.method in ("loads", "dumps"):
                        return FunctionCall(
                            name=f"__py2rust_native_json_{node.method}",
                            args=node.args,
                            line=node.line,
                            col=node.col
                        )
        
        return node
