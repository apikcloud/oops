"""
oops sync — Synchronise des fichiers depuis un repo distant (sans parenté).

Flow:
    1. Clone sparse du repo distant dans un répertoire temporaire
    2. Affiche le diff avec le repo local
    3. Applique les changements et crée un commit (avec confirmation)

Usage:
    oops sync
    oops sync --dry-run
    oops sync --yes
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import click
import git

from oops.core.config import config
from oops.core.messages import commit_messages

# ---------------------------------------------------------------------------
# Commande Click
# ---------------------------------------------------------------------------


@click.command("sync")
@click.option("--dry-run", is_flag=True, help="Affiche le diff sans appliquer les changements.")
@click.option("--yes", "-y", is_flag=True, help="Applique sans demander de confirmation.")
def main(dry_run: bool, yes: bool) -> None:
    """Synchronise les fichiers depuis le repo distant configuré."""

    remote_url = config.sync.remote_url
    files = config.sync.files

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. FETCH
        click.echo(f"↓ Clonage de {remote_url} …")
        try:
            _fetch(remote_url, tmpdir, files)
        except git.GitCommandError as exc:
            raise click.ClickException(f"Échec du clone : {exc.stderr.strip()}") from exc

        # 2. DIFF
        click.echo("")
        has_changes = _show_diff(Path(tmpdir), files)

        if not has_changes:
            click.echo(click.style("✓ Déjà à jour.", fg="green"))
            return

        if dry_run:
            click.echo(click.style("\n[dry-run] Aucun changement appliqué.", fg="yellow"))
            return

        # 3. APPLY + COMMIT
        click.echo("")
        if not yes:
            click.confirm("Appliquer ces changements ?", abort=True)

        _apply(Path(tmpdir), files)

        """Crée un commit avec les fichiers synchronisés."""
        local_repo = git.Repo(Path.cwd(), search_parent_directories=True)

        local_repo.index.add(files)

        # Vérifie qu'il y a effectivement quelque chose à committer
        if not local_repo.index.diff("HEAD"):
            click.echo(click.style("⚠ Rien à committer (index identique à HEAD).", fg="yellow"))
            return

        commit = local_repo.index.commit(commit_messages.project_sync)
        click.echo(
            click.style(
                f"\n✓ Commit {commit.hexsha[:8]} — {commit_messages.project_sync}", fg="green"
            )
        )


# ---------------------------------------------------------------------------
# 1. Fetch — clone sparse du repo distant
# ---------------------------------------------------------------------------


def _fetch(remote_url: str, tmpdir: str, files: list[str]) -> None:
    """Clone uniquement les fichiers/dossiers listés (sparse checkout, depth=1)."""
    remote_repo = git.Repo.clone_from(
        remote_url,
        tmpdir,
        depth=1,
        no_checkout=True,
    )

    # Active le sparse checkout
    with remote_repo.config_writer() as cw:
        cw.set_value("core", "sparseCheckout", True)

    # Écrit la liste des patterns dans .git/info/sparse-checkout
    sparse_file = Path(tmpdir) / ".git" / "info" / "sparse-checkout"
    sparse_file.write_text("\n".join(files) + "\n", encoding="utf-8")

    # Checkout effectif
    remote_repo.git.checkout("HEAD")


# ---------------------------------------------------------------------------
# 2. Diff — affiche les différences avant application
# ---------------------------------------------------------------------------


def _show_diff(tmpdir: Path, files: list[str]) -> bool:
    """
    Affiche le diff entre les fichiers distants (tmpdir) et locaux.
    Retourne True si au moins un fichier diffère.
    """
    local_repo = git.Repo(Path.cwd(), search_parent_directories=True)
    repo_root = Path(local_repo.working_tree_dir)
    has_changes = False

    for f in files:
        src = tmpdir / f
        dst = repo_root / f

        if not src.exists():
            click.echo(click.style(f"[SKIP] {f}", fg="yellow") + " — absent du repo distant")
            continue

        if not dst.exists():
            click.echo(click.style(f"[NEW]  {f}", fg="green") + " — sera créé")
            has_changes = True
            continue

        # git diff --no-index compare deux chemins arbitraires (hors repo)
        try:
            diff_output = local_repo.git.diff(
                "--no-index",
                "--color",
                str(dst),
                str(src),
            )
            # Pas d'exception = exit code 0 = pas de différence
        except git.GitCommandError as exc:
            # exit code 1 = différences trouvées ; stdout contient le diff
            diff_output = exc.stdout

        if diff_output:
            click.echo(diff_output)
            has_changes = True

    return has_changes


# ---------------------------------------------------------------------------
# 3a. Apply — copie les fichiers distants vers le repo local
# ---------------------------------------------------------------------------


def _apply(tmpdir: Path, files: list[str]) -> None:
    """Copie les fichiers/dossiers depuis tmpdir vers le repo local."""
    local_repo = git.Repo(Path.cwd(), search_parent_directories=True)
    repo_root = Path(local_repo.working_tree_dir)

    for f in files:
        src = tmpdir / f
        dst = repo_root / f

        if not src.exists():
            continue

        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        click.echo(f"  ✓ {f}")
