"""CodeSentinel - AI-powered code review tool."""

from importlib.metadata import PackageNotFoundError, version

__version__ = "0.1.0"

try:
    __version__ = version("codesentinel")
except PackageNotFoundError:
    pass
