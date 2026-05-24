import threading

class TranslationContext:
    """
    Captures compiler transformation facts and metadata (Neo Patterns) to ground
    semantic equivalence validations and eliminate false equivalence mismatches.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.names: dict[str, str] = {}
        self.global_flows: list[str] = []
        self.calls: dict[str, str] = {}

    def add_name_mapping(self, py_name: str, rust_name: str):
        with self._lock:
            self.names[py_name] = rust_name

    def add_global_flow(self, rule: str):
        with self._lock:
            if rule not in self.global_flows:
                self.global_flows.append(rule)

    def add_call_mapping(self, py_call: str, rust_call: str):
        with self._lock:
            self.calls[py_call] = rust_call

    def clear(self):
        with self._lock:
            self.names.clear()
            self.global_flows.clear()
            self.calls.clear()

    def to_markdown(self) -> str:
        with self._lock:
            lines = ["### Compiler Translation Context (Neo Mapping Mappings)"]
            
            if self.names:
                lines.append("\n**Symbol Name Mappings (Qname):**")
                for py, rust in sorted(self.names.items()):
                    lines.append(f"- Python name `{py}` maps to Rust `{rust}`")
            
            if self.global_flows:
                lines.append("\n**Global Data & Exception Flows (Qglobal_flow):**")
                for flow in self.global_flows:
                    lines.append(f"- {flow}")
                    
            if self.calls:
                lines.append("\n**Invocation & API Calls (Qcall):**")
                for py, rust in sorted(self.calls.items()):
                    lines.append(f"- `{py}` call maps to `{rust}`")
                    
            if not self.names and not self.global_flows and not self.calls:
                lines.append("\n*No specific compiler remappings were applied.*")
                
            return "\n".join(lines)
