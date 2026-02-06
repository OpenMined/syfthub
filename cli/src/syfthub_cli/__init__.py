"""SyftHub CLI - Command-line interface for SyftHub."""

__version__ = "0.1.0"

from syfthub_cli.config import SyftConfig, load_config, save_config

__all__ = [
    "__version__",
    "SyftConfig",
    "load_config",
    "save_config",
]
