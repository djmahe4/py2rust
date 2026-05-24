import subprocess
import shutil
import os
import sys

from .ollama_client import OllamaClient

class SemanticValidator:
    def __init__(self, client=None, model="deepseek-coder", host="http://localhost:11434", db_path=None):
        self.client = client or OllamaClient(model=model, host=host)
        self.db_path = db_path
        self.store = None
        if db_path:
            from .validation_store import ValidationStore
            self.store = ValidationStore(db_path)

    def close(self):
        if self.store:
            self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


    def get_symbol_context(self, symbol_name: str, file_path: str = None) -> str:
        # Platform-aware context gathering checking for tools first
        # 1. On Windows, check for PowerShell 'Select-String' or findstr
        # 2. Check for 'rg' or 'grep' on Linux/Unix
        # 3. Fallback to native python-based text scanning to ensure zero tool errors
        
        # Determine platform commands
        cmd = None
        if sys.platform == "win32":
            # Check Select-String via powershell
            if shutil.which("powershell"):
                cmd = ["powershell", "-NoProfile", "-Command", "& {param($p) Select-String -Pattern $p -Path * -Context 5}", f"def {symbol_name}"]
            elif shutil.which("findstr"):
                cmd = ["findstr", f"def {symbol_name}", "*"]
        else:
            if shutil.which("rg"):
                cmd = ["rg", "-C", "5", f"def {symbol_name}", "."]
            elif shutil.which("grep"):
                cmd = ["grep", "-C", "5", f"def {symbol_name}", "-r", "."]
                
        if cmd:
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.stdout:
                    return res.stdout
            except Exception:
                pass
                
        # Safe, native Python fallback parser to prevent subprocess errors
        context_lines = []
        try:
            for root, _, files in os.walk("."):
                for file in files:
                    if file.endswith(".py"):
                        path = os.path.join(root, file)
                        try:
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                lines = f.readlines()
                            for idx, line in enumerate(lines):
                                if f"def {symbol_name}" in line or f"class {symbol_name}" in line:
                                    start = max(0, idx - 5)
                                    end = min(len(lines), idx + 6)
                                    context_lines.append(f"--- Context from {path} ---\n")
                                    context_lines.extend(lines[start:end])
                        except Exception:
                            pass
        except Exception:
            pass
            
        return "".join(context_lines)

    def validate_equivalence(self, python_code: str, rust_code: str, symbol_name: str, translation_context=None, interactive=False) -> dict:
        context = self.get_symbol_context(symbol_name)
        
        # Build Neo patterns logic
        neo_patterns = []
        try:
            import ast
            parsed_py = ast.parse(python_code)
            for node in ast.walk(parsed_py):
                if isinstance(node, ast.Name):
                    neo_patterns.append(f"Qname({node.id})")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    neo_patterns.append(f"Qcall({node.func.id})")
        except Exception:
            pass
            
        neo_patterns.append(f"Qglobal_flow({symbol_name})")
        neo_str = "NEO REASONING SYMBOLS:\n" + "\n".join(sorted(list(set(neo_patterns))))
        
        tc_str = ""
        if translation_context:
            if hasattr(translation_context, "to_markdown"):
                tc_str = translation_context.to_markdown()
            else:
                tc_str = str(translation_context)
                
        prompt = f"""TASK: Determine if Rust code preserves semantic meaning of Python code.

SURROUNDING CONTEXT:
{context}

{neo_str}

{tc_str if tc_str else ""}

PYTHON SOURCE:
{python_code}

GENERATED RUST:
{rust_code}

CONSIDER:
- Behavioral equivalence for all valid inputs.
- Side effects and mutation patterns.
- Error handling and exception propagation.
- Data flow and aliasing relationships.
- CRITICAL NOTE: The compiler translation mappings (if any) are planned, safe, and correct (e.g. name mangling, wrapper Result patterns, print mappings). Do NOT flag these deliberate transformations as failures.

RESPOND ONLY WITH THE FOLLOWING SCHEMA:
VERDICT: [PASS or FAIL]
CONFIDENCE: [0.0 to 1.0]
REASONING: [detailed explanation]
SUGGESTED_FIX: [optional fix snippet if FAIL]
"""
        response = self.client.generate(prompt) if self.client else "VERDICT: FAIL\nCONFIDENCE: 1.0\nREASONING: No client"
        
        # Simple parser for structured response
        verdict = "FAIL"
        confidence = 0.0
        reasoning = ""
        suggested_fix = ""
        
        for line in response.splitlines():
            if line.startswith("VERDICT:"):
                verdict = line.split(":", 1)[1].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.startswith("SUGGESTED_FIX:"):
                suggested_fix = line.split(":", 1)[1].strip()
                
        res = {
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": reasoning,
            "suggested_fix": suggested_fix,
            "is_hitl": 0
        }

        # Human-in-the-Loop Override
        if interactive and res["verdict"] == "FAIL":
            print(f"\n[HITL ALERT] Validation FAILED for function '{symbol_name}'")
            print(f"Reasoning: {res['reasoning']}")
            choice = input("Do you want to manually override and approve this compiled Rust? [y/n]: ").strip().lower()
            if choice in ('y', 'yes'):
                res["verdict"] = "PASS"
                res["confidence"] = 1.0
                res["reasoning"] = "User manual override (Approved)"
                res["is_hitl"] = 1
            else:
                res["reasoning"] = "User manual override (Rejected)"
                res["is_hitl"] = 1
            
            # Save HITL decision in validation store if configured
            if self.store:
                record = {
                    "symbol_name": symbol_name,
                    "python_source": python_code,
                    "generated_rust": rust_code,
                    "verdict": res["verdict"],
                    "confidence": res["confidence"],
                    "reasoning": res["reasoning"],
                    "suggested_fix": res.get("suggested_fix", ""),
                    "is_hitl": 1
                }
                self.store.save_validation(record)
                
        return res
