from __future__ import annotations
import sys
import subprocess
from pathlib import Path

from .config import CompilerConfig
from .frontend.parser import parse
from .middleend.ir_builder import build_ir
from .backend.rust_codegen import generate_rust
from .backend.rust_formatter import format_rust
from .utils.errors import CompilerError
from .utils.logger import setup_logger, get_logger


def compile_file(config: CompilerConfig) -> bool:
    logger = setup_logger(config.verbose)
    source_path = Path(config.input_file)

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
        ir_module = build_ir(module, filename, source_lines)
    except CompilerError as e:
        print(str(e), file=sys.stderr)
        return False

    if config.emit_ir:
        print(repr(ir_module))

    if config.check_only:
        print("OK: no errors found")
        return True

    logger.debug("Generating Rust code")
    rust_code = generate_rust(ir_module)

    if config.format_output:
        rust_code = format_rust(rust_code)

    if config.output_file:
        output_path = Path(config.output_file)
        output_path.write_text(rust_code)
        logger.info(f"Written: {output_path}")
    else:
        print(rust_code)

    if config.verify and config.output_file:
        logger.debug("Verifying with rustc")
        result = subprocess.run(
            ['rustc', config.output_file, '--edition', '2021', '--crate-type', 'bin', '-o', '/dev/null'],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"rustc verification failed:\n{result.stderr}", file=sys.stderr)
            return False
        logger.info("rustc verification passed")

    return True
