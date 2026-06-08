#!/usr/bin/env bash
# oops installer — Linux only (Debian/Ubuntu + Fedora) for now.
#
#   curl -fsSL https://raw.githubusercontent.com/apikcloud/oops/main/install.sh | bash
#
# Options (pass after `-s --` when piping, e.g. `... | bash -s -- --no-gui`):
#   --no-gui          CLI only — skip the desktop dashboard (pywebview[qt]) and its system libs
#   --version vX.Y.Z  install a specific tag (default: latest GitHub release)
#   --help

set -euo pipefail

REPO="apikcloud/oops"
GIT_URL="https://github.com/${REPO}.git"
WITH_GUI=1
VERSION="${OOPS_VERSION:-}"

# ---- pretty output (only when attached to a terminal) ----------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; DIM=$'\033[2m'; RST=$'\033[0m'
else
  BOLD=""; RED=""; GRN=""; YLW=""; DIM=""; RST=""
fi
say()  { printf '%s\n' "${BOLD}oops${RST} $*"; }
warn() { printf '%s\n' "${YLW}oops${RST} $*" >&2; }
die()  { printf '%s\n' "${RED}oops${RST} $*" >&2; exit 1; }

# ---- args ------------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --no-gui)   WITH_GUI=0 ;;
    --version)  VERSION="${2:-}"; shift ;;
    --help|-h)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

# ---- sudo & package manager detection --------------------------------------
[ "$(uname -s)" = "Linux" ] || die "this installer is Linux-only for now."

if [ "$(id -u)" -eq 0 ]; then SUDO=""; else
  command -v sudo >/dev/null 2>&1 && SUDO="sudo" || die "need root or sudo to install system packages."
fi

if command -v apt-get >/dev/null 2>&1; then
  PM="apt"
elif command -v dnf >/dev/null 2>&1; then
  PM="dnf"
else
  die "unsupported distro: need apt-get (Debian/Ubuntu) or dnf (Fedora)."
fi
say "detected ${BOLD}${PM}${RST} package manager."

pkg_install() {
  # $@ = package names
  case "$PM" in
    apt) $SUDO apt-get update -qq && $SUDO apt-get install -y -qq "$@" ;;
    dnf) $SUDO dnf install -y -q "$@" ;;
  esac
}

# ---- base system dependencies ----------------------------------------------
# cloc: lines-of-code counting · git: repo operations · curl: uv bootstrap
say "installing system dependencies (cloc, git)…"
pkg_install git cloc

# ---- uv --------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "installing uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  hash -r
fi
command -v uv >/dev/null 2>&1 || die "uv not found on PATH after install (expected ~/.local/bin)."

# ---- resolve version (latest release unless pinned) ------------------------
if [ -z "$VERSION" ]; then
  VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null \
    | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')" || true
  [ -n "$VERSION" ] || { warn "could not resolve latest release; falling back to 'main'."; VERSION="main"; }
fi
say "installing oops ${BOLD}${VERSION}${RST} from git…"

# ---- optional GUI (pywebview[qt]) system libs ------------------------------
if [ "$WITH_GUI" -eq 1 ]; then
  say "installing desktop (Qt WebEngine) system libraries… ${DIM}(best-effort; desktops usually have these)${RST}"
  case "$PM" in
    apt) pkg_install libgl1 libegl1 libxkbcommon0 libxcb-cursor0 libnss3 libdbus-1-3 libfontconfig1 || warn "some GUI libs failed to install" ;;
    dnf) pkg_install mesa-libGL mesa-libEGL libxkbcommon xcb-util-cursor nss dbus-libs fontconfig || warn "some GUI libs failed to install" ;;
  esac
fi

# ---- install oops as an isolated uv tool -----------------------------------
SPEC="git+${GIT_URL}@${VERSION}"
if [ "$WITH_GUI" -eq 1 ]; then
  uv tool install --force "oops[gui] @ ${SPEC}"
else
  uv tool install --force "${SPEC}"
fi

# ---- PATH guidance ---------------------------------------------------------
uv tool update-shell >/dev/null 2>&1 || true
if command -v oops >/dev/null 2>&1; then
  say "${GRN}done${RST} — $(oops --version 2>/dev/null || echo 'installed')."
else
  say "${GRN}installed.${RST} Add uv's bin dir to your PATH, then restart your shell:"
  printf '       %s\n' 'export PATH="$HOME/.local/bin:$PATH"'
fi
