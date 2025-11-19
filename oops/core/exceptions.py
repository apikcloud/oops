import warnings

from oops.core.config import config


class NoManifestFound(Exception):
    """Raised when no manifest file is found in an addon."""

    pass


class NoGitRepository(Exception):
    """Raised when the current directory is not part of a git repository."""

    pass


class ScriptNotFound(Exception):
    """Raised when a required script is not found."""

    pass


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

    pass


class UnusualRegistryWarning(UserWarning):
    """Warning for unusual Docker registries."""

    pass


def warn_deprecated_registry(name):
    warnings.warn(
        f"You should use one of these registries ({', '.join(config.docker_recommended_registries)}) as a replacement for '{name}'.",  # noqa: E501
        DeprecatedRegistryWarning,
        stacklevel=3,
    )


def warn_unusual_registry(name):
    warnings.warn(
        f"You should use one of these registries ({', '.join(config.docker_recommended_registries)}) as a replacement for '{name}'.",  # noqa: E501
        UnusualRegistryWarning,
        stacklevel=3,
    )
