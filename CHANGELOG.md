# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - YYYY-MM-DD

### Added

- Feature to manage exclusion list in the pre-commit-config.yaml file. There must be an entry and end tag to match the
part to edit. Entry tag: "# [//]: # (exclude)", and end tag: "# [//]: # (end exclude)". 
The command is "oops-addons-exclude", it always replaces the content inside this tag.
- Feature to generate the addon table in the README.md file. The command is "oops-addons-table".
- Feature to extract the Python external dependencies from the manifests of the addons. It possesses a flag to force the
update `--update`, which will edit the content of the `requirements.txt` file. In case there is a change and the flag is
not given, it will show a message telling there are differences between the two versions.
The command is "oops-addons-requirements".
- Core element for the project: `.editorconfig` and `.ruff.toml` files.

### Changed

- Modify the render of the tables, for example for the addons. It now starts the count of addons at 1 instead of 0,
easing the reading of the count of available modules.

### Fixed

- Fix the `oops-submodules-rewrite` command to skip submodules when they already exists in the project. In some cases,
the submodule are both in `third-party` and `.third-party`, so it generates an error.
- Minor issue in the `oops-addons-list` command.

## [v0.1.0] - 2025-11-19

### Added

- First release version with initial features for addons, projects, and submodules.
