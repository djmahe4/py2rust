from . import BasePlugin
from ..frontend.ast_nodes import ExternalPythonType, FunctionCall, Name, ListType, HeapType, Assign, MethodCall

class HeapqPlugin(BasePlugin):
    """
    Plugin for the standard 'heapq' library.
    Identifies lists that are used with heapq functions and upgrades them to HeapType.
    """
    
    @property
    def module_name(self) -> str:
        return "heapq"
    
    def register(self, st):
        # Register heapq module
        st.register_external_name("heapq", ExternalPythonType(module="heapq"))
        # Register common functions
        for name in ("heappush", "heappop", "heapify", "heapreplace", "heappushpop"):
            ext = ExternalPythonType(module="heapq", name=name)
            st.register_external_name(name, ext)
            st.register_external_name(f"heapq.{name}", ext)

    def transform_ast(self, node, checker):
        """
        Intercept heapq calls and upgrade list types to HeapType in the symbol table.
        Normalizes 'heapq.method(args)' from MethodCall to FunctionCall.
        """
        if isinstance(node, MethodCall):
            if isinstance(node.value, Name) and node.value.name == "heapq":
                # Normalize 'import heapq; heapq.heappush(h, 1)' to FunctionCall
                func_name = f"heapq.{node.method}"
                node = FunctionCall(
                    name=func_name,
                    args=node.args,
                    line=node.line,
                    col=node.col
                )
        
        if isinstance(node, (FunctionCall, MethodCall)):
            self._handle_heapq_call(node, checker)
        
        return node

    def _handle_heapq_call(self, call, checker):
        if not checker:
            return
            
        # Determine if it's a heapq call
        is_heapq = False
        func_name = ""
        heap_arg_idx = 0
        
        if isinstance(call, FunctionCall):
            # from heapq import heappush; heappush(h, 1)
            func_name = call.name
            if func_name in ("heappush", "heappop", "heapify", "heapreplace", "heappushpop"):
                is_heapq = True
            elif func_name.startswith("heapq."):
                func_name = func_name[6:]
                is_heapq = True
        elif isinstance(call, MethodCall):
            # import heapq; heapq.heappush(h, 1)
            if isinstance(call.value, Name) and call.value.name == "heapq":
                func_name = call.method
                if func_name in ("heappush", "heappop", "heapify", "heapreplace", "heappushpop"):
                    is_heapq = True
        
        if is_heapq and len(call.args) > heap_arg_idx:
            heap_arg = call.args[heap_arg_idx]
            if isinstance(heap_arg, Name):
                var_name = heap_arg.name
                
                # Look up current type in SymbolTable
                current_type = checker.st.lookup(var_name)
                
                # Try to infer element type from heappush if it is Unknown
                elem_type = getattr(current_type, "element_type", None)
                if func_name == "heappush" and len(call.args) > 1:
                    push_val = call.args[1]
                    val_type = checker.inferencer.infer(push_val)
                    if elem_type is None or str(elem_type) == "unknown":
                        elem_type = val_type

                if isinstance(current_type, ListType) and not isinstance(current_type, HeapType):
                    # Upgrade to HeapType
                    new_type = HeapType(element_type=elem_type or current_type.element_type)
                    checker.st.define(var_name, new_type)
                elif isinstance(current_type, HeapType) and str(current_type.element_type) == "unknown" and elem_type:
                    # Update element type of existing heap
                    current_type.element_type = elem_type
