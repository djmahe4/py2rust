from __future__ import annotations
import argparse
import sys
from .config import CompilerConfig, AsyncRuntime
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
    parser.add_argument("--mock-mode", "-M", action="store_true", help="Mock missing imports as ExternalPythonType")
    parser.add_argument("--runtime", choices=["tokio", "futures"], default="tokio", help="Async runtime to use (default: tokio)")
    parser.add_argument("--repo-root", default="", help="Root of python repository to compile")
    parser.add_argument("--package-dir", default="", help="Subdirectory containing python package")
    # Wave 33: Semantic validation and learning flags
    parser.add_argument("--validate", action="store_true", help="Enable semantic validation using local Ollama model")
    parser.add_argument("--ollama-model", default="deepseek-coder", help="Ollama model to use for validation (default: deepseek-coder)")
    parser.add_argument("--ollama-host", default="http://localhost:11434", help="Ollama host URL (default: http://localhost:11434)")
    parser.add_argument("--strict-validation", action="store_true", help="Fail compilation if semantic validation fails")
    parser.add_argument("--learn-patterns", action="store_true", help="Extract and store architectural patterns from validation results")
    parser.add_argument("--apply-learned-patterns", action="store_true", help="Apply previously learned patterns during compilation")
    parser.add_argument("--review-failures", action="store_true", help="Interactively review validation failures")
    parser.add_argument("--force", "-f", action="store_true", help="Force recompile all modules, bypassing the build cache.")

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
        mock_mode=args.mock_mode,
        async_runtime=AsyncRuntime(args.runtime),
        repo_root=args.repo_root,
        package_dir=args.package_dir,
        validate=args.validate,
        ollama_model=args.ollama_model,
        ollama_host=args.ollama_host,
        strict_validation=args.strict_validation,
        learn_patterns=args.learn_patterns,
        apply_learned_patterns=args.apply_learned_patterns,
        review_failures=args.review_failures,
        force=args.force,
    )



    success = compile_file(config)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
