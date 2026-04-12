from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CompilerConfig:
    input_file: str = ""
    output_file: str = ""
    emit_ast: bool = False
    emit_ir: bool = False
    check_only: bool = False
    verbose: bool = False
    verify: bool = False
    format_output: bool = True
