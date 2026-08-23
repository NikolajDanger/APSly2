#!/bin/bash

##
# This script takes care of bundling the apworld.
#
# Arguments:
# * $1: Can be "clean" to clean the build environment.
#
# Environment:
# * AP_ROOT (required):
#     Path to an Archipelago checkout whose `worlds/Sly2` links to this
#     repository. It resolves the Archipelago imports for the type check,
#     the test suite is run there (a failure aborts the build), and its
#     apworld container code supplies the manifest's
#     `version`/`compatible_version`.
##

set -eo pipefail
shopt -s globstar

CWD="$(dirname $(realpath $0))"
REQS=("zip" "rsync" "pip" "ruff" "pyright")
SUPPORTED_PLATFORMS=("win_amd64" "manylinux_2_17_x86_64")
PYTHON_VERSIONS=("3.10" "3.11" "3.12")

##
# Make sure all the required utilities are installed.
##
function pre_flight() {
    local bad="0"
    for r in ${REQS[@]}; do
        if ! command -v $r > /dev/null; then
            echo "!=> Unable to locate the '${r}' utility in \$PATH. Make sure it is installed."
            bad="1"
        fi
    done

    [ "${bad}" = "1" ] && exit 1 ||:
}

##
# Make sure $AP_ROOT is an Archipelago checkout that links to this project.
#
# Arguments:
# * $1: project root
##
function check_ap_root() {
    local root="$1"
    if [ -z "${AP_ROOT}" ]; then
        echo "!=> AP_ROOT is not set. Point it at an Archipelago checkout whose"
        echo "!=> worlds/Sly2 links to ${root}."
        exit 1
    fi
    if [ "$(realpath "${AP_ROOT}/worlds/Sly2" 2>/dev/null)" != "${root}" ]; then
        echo "!=> ${AP_ROOT}/worlds/Sly2 does not resolve to ${root}."
        echo "!=> Link this repository into the Archipelago checkout first."
        exit 1
    fi
}

##
# Run the test suite inside the Archipelago checkout.
##
function run_tests() {
    echo "=> Testing (in ${AP_ROOT})"
    pushd "${AP_ROOT}"
    AP_TEST_WORLDS=Sly2 python -m pytest -q -p no:cacheprovider \
        worlds/Sly2 test/general
    popd
}

##
# Run the end-to-end suite against PCSX2 when SLY2_E2E_ISO points at the
# disc image; the harness starts and stops the emulator itself.
##
function run_e2e_tests() {
    if [[ -z "${SLY2_E2E_ISO:-}" ]]; then
        echo "=> Skipping e2e tests (SLY2_E2E_ISO not set)"
        return
    fi
    echo "=> Testing end-to-end against PCSX2 (in ${AP_ROOT})"
    pushd "${AP_ROOT}"
    SLY2_E2E=1 python -m pytest -q -p no:cacheprovider \
        -o python_files='e2e_*.py' worlds/Sly2/e2e
    popd
}

##
# Add the container `version`/`compatible_version` that Archipelago's own
# packager would write to the bundled manifest.
#
# Arguments:
# * $1: path to the bundled archipelago.json
##
function write_manifest() {
    local manifest="$1"
    pushd "${AP_ROOT}"
    python - "${manifest}" <<'PY'
import json
import sys

from worlds.Files import APWorldContainer

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    manifest = json.load(f)
container = APWorldContainer("sly2.apworld")
container.game = manifest["game"]
manifest.update(container.get_manifest())
with open(path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PY
    popd
}

##
# Create the `apworld` file used by Archipelago.
#
# Arguments:
# * $1: project root
# * $2: destination directory
##
function mk_apworld() {
    local root="$1" destdir="$2"
    echo "=> Bundling apworld"
    echo "From: ${root}"
    echo "To: ${destdir}"
    mkdir --parents "${destdir}/sly2"
    rsync --progress \
        --recursive \
        --prune-empty-dirs \
        --exclude-from="${CWD}/apworld.ignore" \
        "${root}/" "${destdir}/sly2"

    echo "${stamp}" > "${destdir}/sly2/version.txt"
    write_manifest "${destdir}/sly2/archipelago.json"

    pushd "${destdir}"
    zip -9r "sly2.apworld" "sly2"
    popd

    rm --force --recursive "${destdir}/sly2"
}

##
# Copy static data into the destination directory.
##
function cp_data() {
    local root="$1" destdir="$2"
    echo "=> Copying over the extra data"
    cp --verbose "${root}/Sly 2.yaml" ${destdir}
}

##
# Main entry point.
##
function main() {
    pre_flight

    local target_path="${CWD}/target"
    local bundle_base="sly2_apworld"
    mkdir --parents ${target_path}

    case "$1" in
    # Clean the build environment.
    clean)
        find "${target_path}" \
            -depth \
            -type d \
            -name "${bundle_base}-*" \
            -exec rm --force --recursive --verbose {} \;
        ;;

    # Create the release bundle.
    *)
        local stamp="$(date '+%Y-%m-%d_%H%M')"
        local project="$(realpath ${CWD}/..)"
        local bundle="${bundle_base}-${stamp}"
        local destdir="${target_path}/${bundle}"

        check_ap_root "${project}"
        echo "=> Linting"
        ruff check "${project}"
        echo "=> Type checking"
        PYTHONPATH="${AP_ROOT}" pyright -p "${CWD}/pyright.json"
        run_tests
        run_e2e_tests

        mk_apworld "${project}" "${destdir}"
        cp_data "${project}" "${destdir}"
        echo "! Bundle finalized as ${target_path}/${bundle}"
        ;;
    esac
}
main "$@"
