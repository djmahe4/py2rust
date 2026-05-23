import subprocess
import shutil
import os
import sys

from .ollama_client import OllamaClient

class SemanticValidator:
    def __init__(self, client=None, model="deepseek-coder"):
        self.client = client or OllamaClient(model=model)

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
                cmd = ["powershell", "-Command", f"Select-String -Pattern 'def {symbol_name}' -Path * -Context 5"]
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

    def validate_equivalence(self, python_code: str, rust_code: str, symbol_name: str) -> dict:
        context = self.get_symbol_context(symbol_name)
        prompt = f"""TASK: Determine if Rust code preserves semantic meaning of Python code.

SURROUNDING CONTEXT:
{context}

PYTHON SOURCE:
{python_code}

GENERATED RUST:
{rust_code}

CONSIDER:
- Behavioral equivalence for all valid inputs
- Side effects and mutation patterns
- Error handling and exception propagation
- Data flow and aliasing relationships

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
                
        return {
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": reasoning,
            "suggested_fix": suggested_fix
        }
