# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: exceptions.py — oops/core/exceptions.py


class ConfigurationError(Exception):
    """Raised when required configuration values are missing."""


class NoManifestFound(Exception):
    """Raised when no manifest file is found in an addon."""


class NoGitRepository(Exception):
    """Raised when the current directory is not part of a git repository."""


class ScriptNotFound(Exception):
    """Raised when a required script is not found."""


class MarkersNotFound(Exception):
    """Raised when the addons table markers are missing or malformed in a README."""


class MissingMandatoryFiles(Exception):
    """Raised when mandatory files are missing."""

    message = "Mandatory files are missing: {files}"

    def __init__(self, files):
        self.files = files
        self.message = self.message.format(files=", ".join(files))
        super().__init__(self.message)


class MissingRecommendedFiles(MissingMandatoryFiles):
    """Raised when recommended files are missing."""

    message = "Recommended files are missing: {files}"


class DeprecatedRegistryWarning(UserWarning):
    """Warning for deprecated Docker registries."""


class UnusualRegistryWarning(UserWarning):
    """Warning for unusual Docker registries."""
