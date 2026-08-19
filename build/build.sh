#!/bin/bash

##
# This script takes care of bundling the apworld.
#
# Arguments:
# * $1: Can be "clean" to clean the build environment.
#
# Environment:
# * TAG:
#     A string used to tag the bundle name
#     eg: "v1.1.1" will name the bundle "sly2_apworld-v1.1.1"
#     (default: current date and time)
##

set -eo pipefail
shopt -s globstar

CWD="$(dirname $(realpath $0))"
REQS=("zip" "rsync" "pip" "ruff")
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

    echo "${tag}" > "${destdir}/sly2/version.txt"

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
        local tag="${TAG:-$(date '+%Y-%m-%d_%H%M')}"
        local project="$(realpath ${CWD}/..)"
        local bundle="${bundle_base}-${tag}"
        local destdir="${target_path}/${bundle}"

        echo "=> Linting"
        ruff check "${project}"

        mk_apworld "${project}" "${destdir}"
        cp_data "${project}" "${destdir}"
        echo "! Bundle finalized as ${target_path}/${bundle}"
        ;;
    esac
}
main "$@"
