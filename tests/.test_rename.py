import click
import pytest
from oops.submodules import rename as rename_mod


def test_no_gitmodules(monkeypatch, tmp_path):
    # get_root_path returns a repo path without .gitmodules
    monkeypatch.setattr(rename_mod, "get_root_path", lambda: tmp_path)
    # prevent changing working dir in tests
    monkeypatch.setattr(rename_mod.os, "chdir", lambda p: None)
    messages = []
    monkeypatch.setattr(rename_mod.click, "echo", lambda msg: messages.append(msg))

    with pytest.raises(click.Abort):
        rename_mod.main(dry_run=False, no_commit=False)

    assert any("No .gitmodules found." in m for m in messages)


def test_rename_and_commit(monkeypatch, tmp_path):
    # create .gitmodules so the code proceeds
    gm = tmp_path / ".gitmodules"
    gm.write_text(
        '[submodule "oldname"]\n\tpath = some/path\n\turl = git@github.com:org/repo.git\n'
    )

    monkeypatch.setattr(rename_mod, "get_root_path", lambda: tmp_path)
    monkeypatch.setattr(rename_mod.os, "chdir", lambda p: None)

    # set up parsed submodules: one that should be renamed
    subs = {"oldname": {"path": "some/path", "url": "git@github.com:org/repo.git"}}
    monkeypatch.setattr(rename_mod, "parse_submodules", lambda path: subs)

    # not a pull request path
    monkeypatch.setattr(rename_mod, "is_pull_request_path", lambda p: False)

    # guess a different name -> triggers rename
    monkeypatch.setattr(
        rename_mod, "guess_submodule_name", lambda url, pull_request=False: "newname"
    )

    rename_calls = []
    monkeypatch.setattr(
        rename_mod,
        "rename_submodule",
        lambda gm_path, name, new, values, dry: rename_calls.append(
            (gm_path, name, new, values, dry)
        ),
    )

    git_add_calls = []
    monkeypatch.setattr(rename_mod, "git_add", lambda paths: git_add_calls.append(list(paths)))

    commit_calls = []

    def fake_commit(message, skip_hook=False):
        commit_calls.append((message, skip_hook))

    monkeypatch.setattr(rename_mod, "commit", fake_commit)

    messages = []
    monkeypatch.setattr(rename_mod.click, "echo", lambda msg: messages.append(msg))

    rename_mod.main(dry_run=False, no_commit=False)

    # rename_submodule should have been called with dry_run=False
    assert rename_calls == [(str(gm), "oldname", "newname", subs["oldname"], False)]

    # git_add and commit should have been called
    assert git_add_calls == [[str(gm), ".git/config"]]
    assert commit_calls == [(rename_mod.commit_messages.submodules_rename, True)]

    # echoes include rename notice and committing notice
    assert any("Renaming submodule 'oldname' -> 'newname'" in m for m in messages)
    assert any("Committing changes..." in m for m in messages)


def test_dry_run_skips_commit(monkeypatch, tmp_path):
    gm = tmp_path / ".gitmodules"
    gm.write_text(
        '[submodule "oldname"]\n\tpath = some/path\n\turl = git@github.com:org/repo.git\n'
    )

    monkeypatch.setattr(rename_mod, "get_root_path", lambda: tmp_path)
    monkeypatch.setattr(rename_mod.os, "chdir", lambda p: None)

    subs = {"oldname": {"path": "some/path", "url": "git@github.com:org/repo.git"}}
    monkeypatch.setattr(rename_mod, "parse_submodules", lambda path: subs)
    monkeypatch.setattr(rename_mod, "is_pull_request_path", lambda p: False)
    monkeypatch.setattr(
        rename_mod, "guess_submodule_name", lambda url, pull_request=False: "newname"
    )

    rename_calls = []
    monkeypatch.setattr(
        rename_mod,
        "rename_submodule",
        lambda gm_path, name, new, values, dry: rename_calls.append(
            (gm_path, name, new, values, dry)
        ),
    )

    git_add_calls = []
    monkeypatch.setattr(rename_mod, "git_add", lambda paths: git_add_calls.append(list(paths)))

    commit_calls = []
    monkeypatch.setattr(
        rename_mod,
        "commit",
        lambda message, skip_hook=False: commit_calls.append((message, skip_hook)),
    )

    messages = []
    monkeypatch.setattr(rename_mod.click, "echo", lambda msg: messages.append(msg))

    # run in dry-run mode
    rename_mod.main(dry_run=True, no_commit=False)

    # rename_submodule should be called with dry_run=True
    assert rename_calls == [(str(gm), "oldname", "newname", subs["oldname"], True)]

    # commit and git_add should not be called in dry-run
    assert git_add_calls == []
    assert commit_calls == []

    # final message should instruct to commit changes
    assert any(
        "Done. Commit .gitmodules changes to share them with the team." in m for m in messages
    )
