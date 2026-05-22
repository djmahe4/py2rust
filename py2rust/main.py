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


def compile_file(config: CompilerConfig) -> bool:
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
        return False

    if config.emit_ast:
        print(repr(module))

    logger.debug("Building IR")
    try:
        ir_module = build_ir(module, filename, source_lines, config, dependency_manager=dep_manager)
    except CompilerError as e:
        print(str(e), file=sys.stderr)
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
                    return False
                
                logger.info("Cargo verification passed")
            except subprocess.CalledProcessError as e:
                print(f"Failed to initialize cargo project: {e.stderr.decode() if e.stderr else str(e)}", file=sys.stderr)
                return False
            except Exception as e:
                print(f"Verification error: {str(e)}", file=sys.stderr)
                return False

    return True
