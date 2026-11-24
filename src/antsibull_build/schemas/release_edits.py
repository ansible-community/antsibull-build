# Author: Felix Fontein <felix@fontein.de>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Ansible Project, 2026

"""
Classes to encapsulate release edit data from ansible-X.Y.Z-edit.yaml
"""

from __future__ import annotations

import typing as t

import pydantic as p
from antsibull_core.pydantic import get_formatted_error_messages
from antsibull_fileutils.yaml import load_yaml_file

if t.TYPE_CHECKING:
    from _typeshed import StrPath


class DeleteInfo(p.BaseModel):
    """
    Information on deletions.
    """

    recursive: bool = False


class PathInfo(p.BaseModel):
    """
    Stores edits for a path.
    """

    delete: t.Optional[DeleteInfo] = None

    @p.model_validator(mode="after")
    def _check_exactly_one(self) -> t.Self:
        fields = [self.delete]
        not_none = sum(f is not None for f in fields if f is not None)
        if not_none != 1:
            raise ValueError("exactly one field must be present")
        return self


class ReleaseEdits(p.BaseModel):
    """
    Release edits.
    """

    paths: dict[str, PathInfo] = {}


def load_edit_file(file: StrPath) -> ReleaseEdits:
    """
    Lint release edits file.
    """
    try:
        data = load_yaml_file(file)
    except FileNotFoundError:
        return ReleaseEdits()
    return ReleaseEdits.model_validate(data)


def lint_edit_file(file: StrPath) -> list[str]:
    """
    Lint release edits file.
    """
    try:
        data = load_yaml_file(file)
    except Exception as exc:
        return [f"Error while parsing file: {exc}"]
    try:
        ReleaseEdits.model_validate(data, extra="forbid")
        return []
    except p.ValidationError as e:
        return get_formatted_error_messages(e)
