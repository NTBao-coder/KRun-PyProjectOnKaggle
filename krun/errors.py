class KrunError(Exception):
    """Base class for errors that can be shown directly to CLI users."""


class ConfigError(KrunError):
    """Raised when krun.yaml is invalid."""


class CommandError(KrunError):
    """Raised when an external command fails."""

