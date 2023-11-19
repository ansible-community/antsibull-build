# Copyright (C) 2023 Maxwell G <maxwell@gtmx.me>
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)

"""
Types used in the antsibull codebase
"""

from __future__ import annotations

from typing import TypeVar

import yaml
from antsibull_core.yaml import load_yaml_file

_T = TypeVar("_T")


class CollectionName(str):
    """
    String subclass that represents a collection with a NAMESPACE.NAME
    """

    __slots__ = ("__namespace", "__name")

    def __init__(self, *args, **kwargs) -> None:  # pylint: disable=unused-argument
        namespace, _, name = self.partition(".")
        if not namespace or not name:
            raise ValueError(f"{self!r} is not a valid collection name")
        # str should be immutable. Make these private and expose via `@property`s.
        self.__namespace = namespace
        self.__name = name

    @property
    def namespace(self) -> str:
        """
        Collection namespace
        """
        return self.__namespace

    @property
    def name(self) -> str:
        """
        Collection name
        """
        return self.__name

    @property
    def parts(self) -> tuple[str, str]:
        """
        Returns a tuple of (self.namespace, self.name)
        """
        return self.namespace, self.name

    def __hash__(self) -> int:
        return hash(type(self)) + super().__hash__()


try:
    cdumper = yaml.CSafeDumper
except AttributeError:
    pass
else:
    cdumper.add_representer(
        CollectionName,
        lambda rep, obj: yaml.representer.SafeRepresenter.represent_str(rep, str(obj)),
    )
yaml.SafeDumper.add_representer(
    CollectionName, yaml.representer.SafeRepresenter.represent_str
)


def make_collection_mapping(mapping: dict[str, _T]) -> dict[CollectionName, _T]:
    """
    Convert `str` keys in a mapping to `CollectionName` objects
    """
    return {CollectionName(collection): value for collection, value in mapping.items()}