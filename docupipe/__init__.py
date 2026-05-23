"""docupipe: 通用文档传输 pipeline"""

__version__ = "0.1.0"

from docupipe import sources  # noqa: F401
from docupipe import destinations  # noqa: F401
from docupipe import steps  # noqa: F401
from docupipe import converters  # noqa: F401

from docupipe.plugins import load_plugins  # noqa: E402

load_plugins()

__all__ = ["__version__"]
