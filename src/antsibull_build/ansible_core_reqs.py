# Author: Felix Fontein <felix@fontein.de>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Ansible Project, 2025
"""Check collection ansible-core requirements."""

from __future__ import annotations

import pathlib

from antsibull_fileutils.yaml import load_yaml_file
from packaging.specifiers import SpecifierSet as PypiVerSpec
from packaging.version import Version as PypiVer


def check_ansible_core_requirements(
    collection_dir: pathlib.Path, ansible_core_version: PypiVer, errors: list[str]
) -> None:
    """Check meta/runtime.yml for a collection."""
    file = collection_dir / "meta" / "runtime.yml"
    runtime_meta = load_yaml_file(file)
    try:
        requires_ansible = runtime_meta.get("requires_ansible")
        if not requires_ansible:
            return
        spec = PypiVerSpec(requires_ansible)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        errors.append(
            f"Cannot parse {file}'s requires_ansible value {requires_ansible!r}: {exc}"
        )
        return
    if ansible_core_version not in spec:
        errors.append(
            f"{file} requirements for ansible-core ({requires_ansible})"
            f" do not allow {ansible_core_version}!"
        )


def check_collection_ansible_core_requirements(
    collection_root: str, ansible_core_version: PypiVer
) -> list[str]:
    """Analyze collections' ansible-core requirements."""
    ansible_collection_dir = pathlib.Path(collection_root)
    errors: list[str] = []
    ansible_core_version = PypiVer(ansible_core_version.base_version)

    for namespace_dir in (n for n in ansible_collection_dir.iterdir() if n.is_dir()):
        for collection_dir in (c for c in namespace_dir.iterdir() if c.is_dir()):
            try:
                # Note that ansible-core's requires_ansible check also uses
                # PypiVersion.base_version instead of the raw version.
                # Quote: "ignore prerelease/postrelease/beta/dev flags for simplicity"
                check_ansible_core_requirements(
                    collection_dir, ansible_core_version, errors
                )
            except FileNotFoundError:
                pass
            except Exception as exc:  # pylint: disable=broad-exception-caught
                errors.append(f"Error while processing {collection_dir}: {exc}")

    return errors
