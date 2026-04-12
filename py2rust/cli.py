from __future__ import annotations
import argparse
import sys
from .config import CompilerConfig
from .main import compile_file


def main():
    parser = argparse.ArgumentParser(
        prog="py2rust",
        description="Compile a Python subset to Rust",
    )
    parser.add_argument("input", help="Input Python file")
    parser.add_argument("-o", "--output", default="", help="Output Rust file")
    parser.add_argument("--emit-ast", action="store_true", help="Print the AST")
    parser.add_argument("--emit-ir", action="store_true", help="Print the IR")
    parser.add_argument("--check-only", action="store_true", help="Only type-check")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--verify", action="store_true", help="Run rustc on the output")
    parser.add_argument("--no-format", action="store_true", help="Disable rustfmt formatting")

    args = parser.parse_args()

    config = CompilerConfig(
        input_file=args.input,
        output_file=args.output,
        emit_ast=args.emit_ast,
        emit_ir=args.emit_ir,
        check_only=args.check_only,
        verbose=args.verbose,
        verify=args.verify,
        format_output=not args.no_format,
    )

    success = compile_file(config)
    sys.exit(0 if success else 1)
