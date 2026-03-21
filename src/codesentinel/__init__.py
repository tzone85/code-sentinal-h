"""CodeSentinel - AI-powered code review tool."""

import contextlib
from importlib.metadata import PackageNotFoundError, version

__version__ = "0.1.0"

with contextlib.suppress(PackageNotFoundError):
    __version__ = version("codesentinel")
