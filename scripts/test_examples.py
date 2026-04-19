import os
import subprocess
import sys
import time

def main():
    examples_dir = "examples"
    all_examples = sorted([f for f in os.listdir(examples_dir) if f.endswith(".py")])
    
    if len(sys.argv) > 1:
        requested = [arg.replace("examples/", "") if arg.startswith("examples/") else arg for arg in sys.argv[1:]]
        examples = [f for f in all_examples if f in requested or f.replace(".py", "") in requested]
    else:
        examples = all_examples
    
    results = []
    
    print(f"Found {len(examples)} examples in {examples_dir}/")
    print("-" * 60)
    
    for example in examples:
        py_file = os.path.join(examples_dir, example)
        rs_file = os.path.join(examples_dir, example.replace(".py", ".rs"))
        
        # Read file to check for imports that require mock mode
        with open(py_file, 'r') as f:
            content = f.read()
            needs_mock = any(lib in content for lib in ["import numpy", "import cv2", "import os", "import math", "import json", "import csv"])
        
        cmd = [
            sys.executable, "-m", "py2rust.cli",
            py_file,
            "-o", rs_file,
            "--verify"
        ]
        
        if needs_mock:
            cmd.append("--mock-mode")
            print(f"[{example}] Compiling (MOCK MODE)...")
        else:
            print(f"[{example}] Compiling...")
            
        start_time = time.time()
        try:
            # We run with PYTHONPATH=. to ensure local py2rust is used
            process = subprocess.run(
                cmd,
                env={**os.environ, "PYTHONPATH": "."},
                capture_output=True,
                text=True
            )
            duration = time.time() - start_time
            
            if process.returncode == 0:
                print(f"  ✅ SUCCESS ({duration:.2f}s)")
                results.append((example, "SUCCESS", duration, ""))
            else:
                print(f"  ❌ FAILED ({duration:.2f}s)")
                results.append((example, "FAILED", duration, process.stderr + "\n" + process.stdout))
        except Exception as e:
            duration = time.time() - start_time
            print(f"  ❌ ERROR ({duration:.2f}s): {str(e)}")
            results.append((example, "ERROR", duration, str(e)))
            
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    
    passed = [r for r in results if r[1] == "SUCCESS"]
    failed = [r for r in results if r[1] != "SUCCESS"]
    
    for name, status, duration, error in results:
        indicator = "✅" if status == "SUCCESS" else "❌"
        print(f"{indicator} {name:<30} {status:<10} {duration:>6.2f}s")
        
    print("-" * 60)
    print(f"TOTAL: {len(results)} | PASSED: {len(passed)} | FAILED: {len(failed)}")
    print("-" * 60)
    
    if failed:
        print("\nFAILURE DETAILS:")
        for name, status, duration, error in failed:
            print(f"\n--- {name} ---")
            print(error)
        sys.exit(1)
        
if __name__ == "__main__":
    main()
