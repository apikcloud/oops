import warnings

from oops.settings import DOCKER_RECOMMENDED_REGISTRIES


class NoManifestFound(Exception):
    pass


class NoGitRepository(Exception):
    pass


class ScriptNotFound(Exception):
    pass


class MissingMandatoryFiles(Exception):
    message = "Mandatory files are missing: {files}"

    def __init__(self, files):
        self.files = files
        self.message = self.message.format(files=", ".join(files))
        super().__init__(self.message)


class MissingRecommendedFiles(MissingMandatoryFiles):
    message = "Recommended files are missing: {files}"


class DeprecatedRegistryWarning(UserWarning):
    pass


class UnusualRegistryWarning(UserWarning):
    pass


def warn_deprecated_registry(name):
    warnings.warn(
        f"You should use one of these registries ({', '.join(DOCKER_RECOMMENDED_REGISTRIES)}) as a replacement for '{name}'.",  # noqa: E501
        DeprecatedRegistryWarning,
        stacklevel=3,
    )


def warn_unusual_registry(name):
    warnings.warn(
        f"You should use one of these registries ({', '.join(DOCKER_RECOMMENDED_REGISTRIES)}) as a replacement for '{name}'.",  # noqa: E501
        UnusualRegistryWarning,
        stacklevel=3,
    )
