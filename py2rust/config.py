from dataclasses import dataclass
from enum import Enum


class AsyncRuntime(Enum):
    TOKIO = "tokio"
    FUTURES = "futures"


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
    mock_mode: bool = False
    async_runtime: AsyncRuntime = AsyncRuntime.TOKIO
    repo_root: str = ""
    package_dir: str = ""

