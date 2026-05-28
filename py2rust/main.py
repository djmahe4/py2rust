from __future__ import annotations
import sys
import subprocess
from pathlib import Path

from .config import CompilerConfig
from .frontend.parser import parse
from .middleend.ir_builder import build_ir
from .middleend.dependency_manager import DependencyManager
from .backend.rust_codegen import generate_rust
from .backend.rust_formatter import format_rust
from .utils.errors import CompilerError
from .utils.logger import setup_logger, get_logger
import ast
import re

class RustToken:
    def __init__(self, token_type: str, value: str, start: int, end: int):
        self.type = token_type
        self.value = value
        self.start = start
        self.end = end

    def __repr__(self):
        return f"RustToken({self.type!r}, {self.value!r}, {self.start}, {self.end})"


def lex_rust(code: str) -> list[RustToken]:
    tokens = []
    idx = 0
    n = len(code)
    
    while idx < n:
        char = code[idx]
        
        # 1. Whitespace
        if char.isspace():
            start = idx
            while idx < n and code[idx].isspace():
                idx += 1
            tokens.append(RustToken("WHITESPACE", code[start:idx], start, idx))
            continue
            
        # 2. Line comment
        if char == '/' and idx + 1 < n and code[idx + 1] == '/':
            start = idx
            idx += 2
            while idx < n and code[idx] != '\n':
                idx += 1
            if idx < n:
                idx += 1
            tokens.append(RustToken("COMMENT", code[start:idx], start, idx))
            continue
            
        # 3. Block comment (supporting nesting)
        if char == '/' and idx + 1 < n and code[idx + 1] == '*':
            start = idx
            idx += 2
            comment_depth = 1
            while idx < n and comment_depth > 0:
                if idx + 1 < n and code[idx] == '/' and code[idx + 1] == '*':
                    comment_depth += 1
                    idx += 2
                elif idx + 1 < n and code[idx] == '*' and code[idx + 1] == '/':
                    comment_depth -= 1
                    idx += 2
                else:
                    idx += 1
            tokens.append(RustToken("COMMENT", code[start:idx], start, idx))
            continue
            
        # 4. Raw String
        if char == 'r' and idx + 1 < n and (code[idx + 1] == '"' or code[idx + 1] == '#'):
            hashes = 0
            temp_idx = idx + 1
            while temp_idx < n and code[temp_idx] == '#':
                hashes += 1
                temp_idx += 1
            if temp_idx < n and code[temp_idx] == '"':
                start = idx
                idx = temp_idx + 1
                found_end = False
                while idx < n:
                    if code[idx] == '"':
                        check_idx = idx + 1
                        match_hashes = 0
                        while check_idx < n and code[check_idx] == '#':
                            match_hashes += 1
                            check_idx += 1
                        if match_hashes == hashes:
                            idx = check_idx
                            found_end = True
                            break
                    idx += 1
                if not found_end:
                    idx = n
                tokens.append(RustToken("STRING", code[start:idx], start, idx))
                continue
                
        # 5. Normal String
        if char == '"':
            start = idx
            idx += 1
            escaped = False
            while idx < n:
                if escaped:
                    escaped = False
                    idx += 1
                    continue
                c = code[idx]
                if c == '\\':
                    escaped = True
                    idx += 1
                elif c == '"':
                    idx += 1
                    break
                else:
                    idx += 1
            tokens.append(RustToken("STRING", code[start:idx], start, idx))
            continue
            
        # 6. Character / Lifetime
        if char == "'":
            start = idx
            idx += 1
            if idx < n and code[idx] == '\\':
                idx += 1
                if idx < n:
                    idx += 1
                if idx < n and code[idx] == "'":
                    idx += 1
                tokens.append(RustToken("CHAR", code[start:idx], start, idx))
                continue
            if idx + 1 < n and code[idx + 1] == "'":
                idx += 2
                tokens.append(RustToken("CHAR", code[start:idx], start, idx))
                continue
            if idx < n and (code[idx].isalpha() or code[idx] == '_'):
                while idx < n and (code[idx].isalnum() or code[idx] == '_'):
                    idx += 1
                tokens.append(RustToken("LIFETIME", code[start:idx], start, idx))
                continue
            tokens.append(RustToken("CHAR", code[start:idx], start, idx))
            continue
            
        # 7. Identifier (including keywords)
        if char.isalpha() or char == '_':
            start = idx
            while idx < n and (code[idx].isalnum() or code[idx] == '_'):
                idx += 1
            tokens.append(RustToken("IDENTIFIER", code[start:idx], start, idx))
            continue
            
        # 8. Numeric Literals
        if char.isdigit():
            start = idx
            while idx < n and (code[idx].isalnum() or code[idx] in ('.', '_')):
                idx += 1
            tokens.append(RustToken("NUMBER", code[start:idx], start, idx))
            continue
            
        # 9. Punctuation
        tokens.append(RustToken("PUNCTUATION", char, idx, idx + 1))
        idx += 1
        
    return tokens


def extract_rust_fn(rust_code: str, func_name: str) -> str:
    tokens = lex_rust(rust_code)
    
    # Filter trivia to check token sequence
    non_trivia = []
    for i, t in enumerate(tokens):
        if t.type not in ("WHITESPACE", "COMMENT"):
            non_trivia.append((i, t))
            
    match_start_token_idx = -1
    for k in range(len(non_trivia) - 1):
        idx_in_tokens, tok = non_trivia[k]
        next_idx_in_tokens, next_tok = non_trivia[k + 1]
        
        if tok.type == "IDENTIFIER" and tok.value == "fn" and next_tok.type == "IDENTIFIER" and next_tok.value == func_name:
            match_start_token_idx = idx_in_tokens
            break
            
    if match_start_token_idx == -1:
        return None
        
    start_idx = tokens[match_start_token_idx].start
    brace_count = 0
    started = False
    end_idx = len(rust_code)
    
    for i in range(match_start_token_idx, len(tokens)):
        t = tokens[i]
        if t.type == "PUNCTUATION":
            if t.value == "{":
                brace_count += 1
                started = True
            elif t.value == "}":
                brace_count -= 1
            elif t.value == ";" and not started:
                end_idx = t.end
                break
                
        if started and brace_count == 0:
            end_idx = t.end
            break
            
    return rust_code[start_idx:end_idx]



def _handle_py2rust_compiler_error(e: CompilerError, source: str, config: CompilerConfig, logger) -> None:
    if not config.validate:
        return
        
    from .learning_system.validation.semantic_validator import SemanticValidator
    import os
    import sys
    import subprocess
    
    validator = SemanticValidator(model=config.ollama_model, host=config.ollama_host)
    if not validator.client.is_available():
        return
        
    prompt = f"""TASK: Analyze a py2rust compilation error and suggest an alternative implementation in Python.

PYTHON SOURCE CODE:
{source}

COMPILER ERROR DIAGNOSTICS:
{str(e)}

Please provide:
1. An explanation of what went wrong in the static subset compilation (e.g. dynamic typing, unsupported libraries, complex scopes, etc.).
2. A suggested alternative Python implementation that accomplishes the same logic but complies with the statically-typed py2rust subset requirements.

Format your response exactly as:
EXPLANATION: [detailed reasoning]
SUGGESTED_FIX: [compliant Python code snippet]
"""
    
    llm_res = validator.client.generate(prompt)
    explanation = "Unable to analyze"
    suggested_fix = ""
    for line in llm_res.splitlines():
        if line.startswith("EXPLANATION:"):
            explanation = line.split(":", 1)[1].strip()
        elif line.startswith("SUGGESTED_FIX:"):
            suggested_fix = line.split(":", 1)[1].strip()
            
    print("\n" + "="*80, file=sys.stderr)
    print("LLM COMPILER ERROR ANALYSIS:", file=sys.stderr)
    print(f"Explanation: {explanation}", file=sys.stderr)
    if suggested_fix:
        print(f"Suggested Python Fix:\n{suggested_fix}", file=sys.stderr)
    print("="*80 + "\n", file=sys.stderr)
    
    if config.review_failures:
        triage_loop = True
        while triage_loop:
            print("\n" + "="*80)
            print("TRIAGE: py2rust Compilation FAILED")
            print("="*80)
            print("\n--- PYTHON SOURCE ---")
            print(source)
            print(f"\n--- COMPILER DIAGNOSTICS ---\n{str(e)}")
            print(f"\n--- LLM ANALYSIS ---\n{explanation}")
            if suggested_fix:
                print(f"\n--- SUGGESTED REFACTOR ---\n{suggested_fix}")
            print("\nACTIONS:")
            print("  [e] Edit Python Source")
            print("  [s] Skip and exit")
            print("  [q] Quit compilation")
            
            try:
                choice = input("\nEnter choice [e/s/q]: ").strip().lower()
            except EOFError:
                choice = 's'
                
            if choice == 'e':
                editor = os.environ.get("EDITOR", "nano")
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".py", mode="w+", delete=False, encoding="utf-8") as temp_py:
                    temp_py.write(source)
                    temp_py_path = temp_py.name
                try:
                    subprocess.run([editor, temp_py_path])
                    with open(temp_py_path, "r", encoding="utf-8") as f:
                        new_py = f.read()
                    if new_py != source:
                        logger.info("Source code updated. Exiting compilation to allow recompile.")
                        sys.exit(0)
                finally:
                    try:
                        os.unlink(temp_py_path)
                    except Exception:
                        pass
            elif choice == 's':
                triage_loop = False
            elif choice == 'q':
                sys.exit(1)


def compile_file(config: CompilerConfig) -> bool:
    from .learning_system.validation.translation_context import TranslationContext
    config.translation_context = TranslationContext()

    source_path = Path(config.input_file)
    if source_path.exists() and source_path.is_dir():
        from .project.repo_compiler import compile_repo
        return compile_repo(config)

    logger = setup_logger(config.verbose)
    dep_manager = DependencyManager()

    if not source_path.exists():
        print(f"Error: file not found: {config.input_file}", file=sys.stderr)
        return False

    source = source_path.read_text()
    source_lines = source.splitlines()
    filename = str(source_path)

    logger.debug(f"Parsing {filename}")
    try:
        module = parse(source, filename)
    except CompilerError as e:
        print(str(e), file=sys.stderr)
        _handle_py2rust_compiler_error(e, source, config, logger)
        return False

    if config.emit_ast:
        print(repr(module))

    logger.debug("Building IR")
    try:
        ir_module = build_ir(module, filename, source_lines, config, dependency_manager=dep_manager)
    except CompilerError as e:
        print(str(e), file=sys.stderr)
        _handle_py2rust_compiler_error(e, source, config, logger)
        return False

    if config.emit_ir:
        print(repr(ir_module))

    if config.check_only:
        print("OK: no errors found")
        return True

    logger.debug("Generating Rust code")
    rust_code = generate_rust(ir_module, dependency_manager=dep_manager, config=config)

    if config.format_output:
        rust_code = format_rust(rust_code)

    if config.output_file:
        output_path = Path(config.output_file)
        output_path.write_text(rust_code)
        logger.info(f"Written: {output_path}")
    else:
        print(rust_code)

    if config.validate:
        logger.info("Starting Semantic Validation Loop...")
        from .learning_system.validation.semantic_validator import SemanticValidator
        from .learning_system.validation.validation_store import ValidationStore
        from .learning_system.learning.pattern_store import PatternStore
        from .learning_system.learning.pattern_extractor import PatternExtractor
        from .learning_system.learning.pattern_applicator import PatternApplicator

        validator = SemanticValidator(model=config.ollama_model, host=config.ollama_host)
        val_store = ValidationStore()
        pat_store = PatternStore()

        # Parse python source into functions
        try:
            py_ast = ast.parse(source)
            has_mismatch = False
            
            for node in ast.walk(py_ast):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    py_source_seg = ast.get_source_segment(source, node)
                    rust_source_seg = extract_rust_fn(rust_code, func_name)
                    
                    if py_source_seg and rust_source_seg:
                        # SQLite cache check
                        cached = val_store.get_cached_validation(py_source_seg, rust_source_seg)
                        if cached and not config.force:
                            logger.info(f"Cache hit for function: '{func_name}' with verdict {cached['verdict']}")
                            res = {
                                "verdict": cached["verdict"],
                                "confidence": cached["confidence"],
                                "reasoning": cached["reasoning"],
                                "suggested_fix": cached.get("suggested_fix", "")
                            }
                        else:
                            logger.info(f"Cache miss. Validating equivalence for function: '{func_name}'")
                            res = validator.validate_equivalence(py_source_seg, rust_source_seg, func_name, config.translation_context)
                            
                            # Save validation record to SQLite cache
                            record = {
                                "symbol_name": func_name,
                                "python_source": py_source_seg,
                                "generated_rust": rust_source_seg,
                                "verdict": res["verdict"],
                                "confidence": res["confidence"],
                                "reasoning": res["reasoning"],
                                "suggested_fix": res.get("suggested_fix", "")
                            }
                            val_store.save_validation(record)
                        
                        if res["verdict"] == "FAIL":
                            if config.review_failures:
                                triage_loop = True
                                while triage_loop:
                                    print("\n" + "="*80)
                                    print(f"TRIAGE: Equivalence validation FAILED for function '{func_name}'")
                                    print("="*80)
                                    print("\n--- PYTHON SOURCE ---")
                                    print(py_source_seg)
                                    print("\n--- GENERATED RUST ---")
                                    print(rust_source_seg)
                                    if config.translation_context:
                                        print("\n" + config.translation_context.to_markdown())
                                    if res.get("suggested_fix"):
                                        print("\n--- LLM SUGGESTED FIX ---")
                                        print(res["suggested_fix"])
                                    print(f"\n--- REASONING ---\n{res['reasoning']}")
                                    print("\nACTIONS:")
                                    print("  [a] Accept Current Rust (Force PASS cache and proceed)")
                                    print("  [e] Edit Python Source")
                                    print("  [r] Retry Validation")
                                    print("  [s] Skip function validation and proceed")
                                    print("  [q] Quit compilation")
                                    
                                    try:
                                        choice = input("\nEnter choice [a/e/r/s/q]: ").strip().lower()
                                    except EOFError:
                                        logger.warning("Standard input EOF reached. Skipping triage.")
                                        choice = 's'
                                        
                                    if choice == 'a':
                                        logger.info(f"Overriding verdict to PASS for '{func_name}'")
                                        res["verdict"] = "PASS"
                                        record = {
                                            "symbol_name": func_name,
                                            "python_source": py_source_seg,
                                            "generated_rust": rust_source_seg,
                                            "verdict": "PASS",
                                            "confidence": 1.0,
                                            "reasoning": "Manually approved by developer in Triage CLI",
                                            "suggested_fix": ""
                                        }
                                        val_store.save_validation(record)
                                        triage_loop = False
                                    elif choice == 'e':
                                        editor = os.environ.get("EDITOR", "nano")
                                        import tempfile
                                        with tempfile.NamedTemporaryFile(suffix=".py", mode="w+", delete=False, encoding="utf-8") as temp_py:
                                            temp_py.write(py_source_seg)
                                            temp_py_path = temp_py.name
                                        try:
                                            subprocess.run([editor, temp_py_path])
                                            with open(temp_py_path, "r", encoding="utf-8") as f:
                                                new_py = f.read()
                                            if new_py != py_source_seg:
                                                logger.info("Source code updated. Exiting compilation to allow recompile.")
                                                sys.exit(0)
                                        finally:
                                            try:
                                                os.unlink(temp_py_path)
                                            except Exception:
                                                pass
                                    elif choice == 'r':
                                        logger.info("Retrying semantic validation...")
                                        res = validator.validate_equivalence(py_source_seg, rust_source_seg, func_name, config.translation_context)
                                        if res["verdict"] == "PASS":
                                            logger.info("Validation PASSED on retry!")
                                            triage_loop = False
                                    elif choice == 's':
                                        logger.info(f"Skipped failure for function '{func_name}'")
                                        res["verdict"] = "PASS"
                                        triage_loop = False
                                    elif choice == 'q':
                                        sys.exit(1)
                            
                            # Re-check verdict after potential manual triage approval
                            if res["verdict"] == "FAIL":
                                has_mismatch = True
                                logger.warning(f"Equivalence validation failed for function '{func_name}'!")
                                logger.warning(f"Reasoning: {res['reasoning']}")
                                
                                # Learn patterns if enabled
                                if config.learn_patterns:
                                    logger.info("Generalizing compiler improvement patterns from validation failures...")
                                    all_vals = val_store.get_validations()
                                    failures = [v for v in all_vals if v["verdict"] == "FAIL" and v["symbol_name"] == func_name]
                                    extractor = PatternExtractor(pattern_store=pat_store, evidence_threshold=1, client=validator.client)
                                    extractor.extract_from_failures(failures)
                                    
                                # Apply learned patterns if enabled
                                if config.apply_learned_patterns:
                                    logger.info("Matching learned patterns for improvements...")
                                    patterns = pat_store.get_patterns()
                                    applicator = PatternApplicator(patterns=patterns)
                                    suggestion = applicator.suggest_fix(rust_source_seg, func_name)
                                    if suggestion:
                                        print(suggestion)
                                    
            if has_mismatch and config.strict_validation:
                print("Strict validation failed: one or more semantic equivalence checks failed.", file=sys.stderr)
                return False
                
        except Exception as e:
            logger.error(f"Semantic validation error: {str(e)}")
            if config.strict_validation:
                return False

    if config.verify and config.output_file:
        import tempfile
        import os
        import shutil
        
        logger.debug("Verifying with cargo check")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            
            env = os.environ.copy()
            cargo_bin = os.path.expanduser("~/.cargo/bin")
            if cargo_bin not in env.get("PATH", ""):
                env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"
            env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
            
            # Initialize a new cargo project
            try:
                subprocess.run(
                    ['cargo', 'init', '--bin', '--name', 'verification_project', str(tmp_dir_path)],
                    capture_output=True, check=True, env=env
                )
                
                # Write Cargo.toml with dependencies
                cargo_toml_path = tmp_dir_path / "Cargo.toml"
                cargo_toml_content = dep_manager.generate_cargo_toml(project_name="verification_project")
                cargo_toml_path.write_text(cargo_toml_content)
                
                # Write main.rs
                main_rs_path = tmp_dir_path / "src" / "main.rs"
                main_rs_path.write_text(rust_code)
                
                # Run cargo check
                # We use --offline if possible to speed up, but first run might need network
                # For now, let it run normally.
                result = subprocess.run(
                    ['cargo', 'check'],
                    cwd=tmp_dir_path,
                    env=env,
                    capture_output=True, text=True
                )
                
                if result.returncode != 0:
                    print(f"Cargo verification failed:\n{result.stderr}", file=sys.stderr)
                    # Also print stdout if stderr is empty or for more context
                    if not result.stderr.strip() and result.stdout.strip():
                         print(result.stdout, file=sys.stderr)
                         
                    if config.validate:
                        from .learning_system.validation.semantic_validator import SemanticValidator
                        validator = SemanticValidator(model=config.ollama_model, host=config.ollama_host)
                        if validator.client.is_available():
                            prompt = f"""TASK: Analyze Rust compilation failure and suggest a fix.

PYTHON SOURCE CODE:
{source}

GENERATED RUST CODE:
{rust_code}

COMPILER ERROR FROM CARGO:
{result.stderr}

Please provide:
1. A concise explanation of why the compilation failed (lifetime, borrow check, type mismatch, etc.).
2. A suggested fix or pattern correction for the generated Rust code.

Format your response exactly as:
EXPLANATION: [detailed reason]
SUGGESTED_FIX: [fix snippet]
"""
                            llm_res = validator.client.generate(prompt)
                            explanation = "Unable to analyze"
                            suggested_fix = ""
                            for line in llm_res.splitlines():
                                if line.startswith("EXPLANATION:"):
                                    explanation = line.split(":", 1)[1].strip()
                                elif line.startswith("SUGGESTED_FIX:"):
                                    suggested_fix = line.split(":", 1)[1].strip()
                            
                            print("\n" + "="*80, file=sys.stderr)
                            print("LLM COMPILER ERROR ANALYSIS:", file=sys.stderr)
                            print(f"Explanation: {explanation}", file=sys.stderr)
                            if suggested_fix:
                                print(f"Suggested Fix:\n{suggested_fix}", file=sys.stderr)
                            print("="*80 + "\n", file=sys.stderr)
                            
                            if config.review_failures:
                                triage_loop = True
                                while triage_loop:
                                    print("\n" + "="*80)
                                    print("TRIAGE: Rust Compilation (cargo check) FAILED")
                                    print("="*80)
                                    print("\n--- PYTHON SOURCE ---")
                                    print(source)
                                    print("\n--- GENERATED RUST ---")
                                    print(rust_code)
                                    print(f"\n--- CARGO COMPILER ERROR ---\n{result.stderr}")
                                    print(f"\n--- LLM ANALYSIS ---\n{explanation}")
                                    if suggested_fix:
                                        print(f"\n--- SUGGESTED RUST FIX ---\n{suggested_fix}")
                                    print("\nACTIONS:")
                                    print("  [e] Edit Python Source")
                                    print("  [s] Skip and exit")
                                    print("  [q] Quit compilation")
                                    
                                    try:
                                        choice = input("\nEnter choice [e/s/q]: ").strip().lower()
                                    except EOFError:
                                        choice = 's'
                                        
                                    if choice == 'e':
                                        editor = os.environ.get("EDITOR", "nano")
                                        import tempfile
                                        with tempfile.NamedTemporaryFile(suffix=".py", mode="w+", delete=False, encoding="utf-8") as temp_py:
                                            temp_py.write(source)
                                            temp_py_path = temp_py.name
                                        try:
                                            subprocess.run([editor, temp_py_path])
                                            with open(temp_py_path, "r", encoding="utf-8") as f:
                                                new_py = f.read()
                                            if new_py != source:
                                                logger.info("Source code updated. Exiting compilation to allow recompile.")
                                                sys.exit(0)
                                        finally:
                                            try:
                                                os.unlink(temp_py_path)
                                            except Exception:
                                                pass
                                    elif choice == 's':
                                        triage_loop = False
                                    elif choice == 'q':
                                        sys.exit(1)
                                        
                    return False
                
                logger.info("Cargo verification passed")
            except subprocess.CalledProcessError as e:
                print(f"Failed to initialize cargo project: {e.stderr.decode() if e.stderr else str(e)}", file=sys.stderr)
                return False
            except Exception as e:
                print(f"Verification error: {str(e)}", file=sys.stderr)
                return False

    return True
