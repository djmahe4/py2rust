from . import BasePlugin
from ..frontend.ast_nodes import ExternalPythonType

class CSVPlugin(BasePlugin):
    """
    Plugin for the standard 'csv' library.
    Registers 'csv' crate requirements.
    """
    
    @property
    def module_name(self) -> str:
        return "csv"
    
    def register(self, st):
        from ..frontend.ast_nodes import ClassType, UnknownType
        # Register standard 'csv' module
        st.register_external_name("csv", ExternalPythonType(module="csv"))
        
        # Register native helpers used by the plugin
        # csv.reader(f) -> ExternalObject
        st.define_function("__py2rust_native_csv_reader", [UnknownType()], ClassType("ExternalObject"))

        if hasattr(st, "dependency_manager") and st.dependency_manager:
            st.dependency_manager.add_dependency("csv", version="1.1")

    def transform_ast(self, node, checker):
        from ..frontend.ast_nodes import FunctionCall, MethodCall, Name, ExternalPythonType
        
        # Helper to check if a symbol is a specific csv function
        def is_csv_func(node):
            if isinstance(node, Name):
                symbol = checker.st.lookup(node.name)
                if isinstance(symbol, ExternalPythonType) and symbol.module == "csv":
                    return symbol.name
                if node.name.startswith("csv."):
                    return node.name.split(".", 1)[1]
            return None

        # Intercept reader calls
        if isinstance(node, FunctionCall):
            func_name = is_csv_func(Name(node.name)) if isinstance(node.name, str) else None
            if func_name == "reader":
                return FunctionCall(
                    name="__py2rust_native_csv_reader",
                    args=node.args,
                    line=node.line,
                    col=node.col
                )
        
        # Intercept attribute access if it's csv.reader (e.g. c.reader(...))
        if isinstance(node, MethodCall):
            if isinstance(node.value, Name):
                symbol = checker.st.lookup(node.value.name)
                if isinstance(symbol, ExternalPythonType) and symbol.module == "csv":
                    if node.method == "reader":
                        return FunctionCall(
                            name="__py2rust_native_csv_reader",
                            args=node.args,
                            line=node.line,
                            col=node.col
                        )
        
        return node
