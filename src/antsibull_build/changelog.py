# Author: Felix Fontein <felix@fontein.de>
# Author: Toshio Kuratomi <tkuratom@redhat.com>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Ansible Project, 2020
"""Changelog handling and processing code."""

# pylint: disable=too-many-lines

from __future__ import annotations

import asyncio
import datetime
import glob
import os
import os.path
import tarfile
import tempfile
import typing as t
from collections import defaultdict
from collections.abc import Callable

import aiohttp
import asyncio_pool  # type: ignore[import]
import pydantic as p
from antsibull_changelog.changes import ChangesData, add_release
from antsibull_changelog.config import (
    ChangelogConfig,
    CollectionDetails,
    PathsConfig,
    TextFormat,
)
from antsibull_changelog.fragment import ChangelogFragment
from antsibull_changelog.rendering.changelog import ChangelogGenerator
from antsibull_changelog.utils import collect_versions
from antsibull_core import app_context
from antsibull_core.ansible_core import get_ansible_core
from antsibull_core.dependency_files import DependencyFileData, DepsFile
from antsibull_core.galaxy import CollectionDownloader, GalaxyContext
from antsibull_core.logging import log
from antsibull_core.schemas.collection_meta import (
    CollectionsMetadata,
    RemovalInformation,
    RemovalUpdate,
    RemovedRemovalInformation,
)
from antsibull_docs_parser.parser import Context as _AnsibleMarkupContext
from antsibull_docs_parser.parser import Whitespace as _AnsibleMarkupWhitespace
from antsibull_docs_parser.parser import parse as _parse_ansible_markup
from antsibull_docs_parser.rst import to_rst_plain as _ansible_markup_to_rst
from antsibull_fileutils.yaml import load_yaml_bytes
from packaging.version import Version as PypiVer
from semantic_version import Version as SemVer

from antsibull_build.utils.urls import get_documentation_repo_raw_url

mlog = log.fields(mod=__name__)


class RemoveCollectionVersionSchema(p.BaseModel):
    changes: dict[str, list[str]]


RemoveCollectionVersionsSchema = p.RootModel[dict[str, RemoveCollectionVersionSchema]]

RemoveCollectionChangelogEntries = p.RootModel[
    dict[str, RemoveCollectionVersionsSchema]
]


def _extract_extra_data(
    data: dict,
    store: Callable[[dict[str, dict[SemVer, RemoveCollectionVersionSchema]]], None],
) -> None:
    try:
        rcce_obj = RemoveCollectionChangelogEntries.model_validate(
            data.get("remove_collection_changelog_entries") or {}
        )
        rcce = {
            collection_name: {
                SemVer(version): data for version, data in versions.root.items()
            }
            for collection_name, versions in rcce_obj.root.items()
        }
    except (p.ValidationError, ValueError):
        # ignore error; linting should complain, not us
        rcce = {}
    store(rcce)


class ChangelogData:
    """
    Data for a single changelog (for a collection, for ansible-core, for Ansible)
    """

    paths: PathsConfig
    config: ChangelogConfig
    changes: ChangesData
    generator: ChangelogGenerator
    generator_flatmap: bool

    remove_collection_changelog_entries: (
        dict[str, dict[SemVer, RemoveCollectionVersionSchema]] | None
    )

    def __init__(
        self,
        paths: PathsConfig,
        config: ChangelogConfig,
        changes: ChangesData,
        flatmap: bool = False,
    ):
        self.paths = paths
        self.config = config
        self.changes = changes
        self.generator_flatmap = flatmap
        self.generator = ChangelogGenerator(self.config, self.changes, flatmap=flatmap)
        self.remove_collection_changelog_entries = None

    @classmethod
    def collection(
        cls, collection_name: str, version: str, changelog_data: t.Any | None = None
    ) -> ChangelogData:
        paths = PathsConfig.force_collection("")
        collection_details = CollectionDetails(paths)
        collection_details.namespace, collection_details.name = collection_name.split(
            ".", 1
        )
        collection_details.version = version
        collection_details.flatmap = False  # TODO!
        config = ChangelogConfig.default(paths, collection_details)
        return cls(
            paths, config, ChangesData(config, "", changelog_data), flatmap=True
        )  # TODO!

    @classmethod
    def ansible_core(cls, changelog_data: t.Any | None = None) -> ChangelogData:
        paths = PathsConfig.force_ansible("")
        collection_details = CollectionDetails(paths)
        config = ChangelogConfig.default(paths, collection_details)
        return cls(
            paths, config, ChangesData(config, "", changelog_data), flatmap=False
        )

    @classmethod
    def ansible(
        cls, directory: str | None, output_directory: str | None = None
    ) -> ChangelogData:
        paths = PathsConfig.force_ansible("")

        config = ChangelogConfig.default(paths, CollectionDetails(paths), "Ansible")
        config.changelog_nice_yaml = True
        config.changelog_sort = "version"
        # While Ansible uses semantic versioning, the version numbers must be PyPI compatible
        config.use_semantic_versioning = False
        config.release_tag_re = r"""(v(?:[\d.ab\-]|rc)+)"""
        config.pre_release_tag_re = r"""(?P<pre_release>(?:[ab]|rc)+\d*)$"""

        remove_collection_changelog_entries = {}

        def store_extra_data(
            rcce: dict[str, dict[SemVer, RemoveCollectionVersionSchema]],
        ) -> None:
            remove_collection_changelog_entries.update(rcce)

        changelog_path = ""
        if directory is not None:
            changelog_path = os.path.join(directory, "changelog.yaml")
        changes = ChangesData(
            config,
            changelog_path,
            extra_data_extractor=lambda data: _extract_extra_data(
                data, store_extra_data
            ),
        )
        if output_directory is not None:
            changes.path = os.path.join(output_directory, "changelog.yaml")
        result = cls(paths, config, changes, flatmap=True)
        result.remove_collection_changelog_entries = remove_collection_changelog_entries
        return result

    @classmethod
    def concatenate(cls, changelogs: list[ChangelogData]) -> ChangelogData:
        return cls(
            changelogs[0].paths,
            changelogs[0].config,
            ChangesData.concatenate([changelog.changes for changelog in changelogs]),
            flatmap=changelogs[0].generator_flatmap,
        )

    def add_ansible_release(
        self,
        version: str,
        date: datetime.date,
        release_summary: str,
        overwrite_release_summary: bool = True,
    ) -> None:
        add_release(
            self.config,
            self.changes,
            [],
            [],
            version,
            codename=None,
            date=date,
            update_existing=True,
            show_release_summary_warning=False,
        )
        release_date = self.changes.releases[version]
        if "changes" not in release_date:
            release_date["changes"] = {}
        if (
            "release_summary" not in release_date["changes"]
            or overwrite_release_summary
        ):
            release_date["changes"]["release_summary"] = release_summary

    def save(self):
        extra_data = {}
        if self.remove_collection_changelog_entries is not None:
            extra_data["remove_collection_changelog_entries"] = {
                collection_name: {
                    str(version): changes.model_dump()
                    for version, changes in versions.items()
                }
                for collection_name, versions in self.remove_collection_changelog_entries.items()
            }
        self.changes.save(extra_data=extra_data or None)


def read_file(tarball_path: str, matcher: t.Callable[[str], bool]) -> bytes | None:
    with tarfile.open(tarball_path, "r:gz") as tar:
        for file in tar:
            if matcher(file.name):
                file_p = tar.extractfile(file)
                if file_p:
                    with file_p:
                        return file_p.read()
    return None


def read_changelog_file(tarball_path: str, is_ansible_core=False) -> bytes | None:
    def matcher(filename: str) -> bool:
        if is_ansible_core:
            return filename.endswith("changelogs/changelog.yaml")
        return filename in ("changelogs/changelog.yaml", "changelog.yaml")

    return read_file(tarball_path, matcher)


def get_core_porting_guide_url(version: PypiVer):
    major_minor = f"{version.major}.{version.minor}"
    return (
        get_documentation_repo_raw_url(version)
        + f"/v{version}"
        + "/docs/docsite/rst/porting_guides"
        + f"/porting_guide_core_{major_minor}.rst"
    )


class CollectionChangelogCollector:
    collection: str
    versions: list[SemVer]
    earliest: SemVer
    latest: SemVer

    changelog: ChangelogData | None

    def __init__(self, collection: str, versions: t.ValuesView[str]):
        self.collection = collection
        self.versions = sorted(SemVer(version) for version in versions)
        self.earliest = self.versions[0]
        self.latest = self.versions[-1]
        self.changelog = None

    async def _get_changelog(
        self, version: SemVer, collection_downloader: CollectionDownloader
    ) -> ChangelogData | None:
        flog = mlog.fields(func="_get_changelog")
        path = await collection_downloader.download(self.collection, version)
        changelog_bytes = read_changelog_file(path)
        if changelog_bytes is None:
            return None
        try:
            changelog_data = load_yaml_bytes(changelog_bytes)
            return ChangelogData.collection(
                self.collection, str(version), changelog_data
            )
        except Exception as exc:  # pylint: disable=broad-except
            flog.warning(
                f"Cannot load changelog of {self.collection} {version} due to {exc}"
            )
            return None

    async def _download_changelog_stream(
        self, start_version: SemVer, collection_downloader: CollectionDownloader
    ) -> ChangelogData | None:
        changelog = await self._get_changelog(start_version, collection_downloader)
        if changelog is None:
            return None

        changelog.changes.prune_versions(
            versions_after=None, versions_until=str(start_version)
        )
        changelogs = [changelog]
        ancestor = changelog.changes.ancestor
        while ancestor is not None:
            ancestor_ver = SemVer(ancestor)
            if ancestor_ver < self.earliest:
                break
            changelog = await self._get_changelog(ancestor_ver, collection_downloader)
            if changelog is None:
                break
            changelog.changes.prune_versions(
                versions_after=None, versions_until=ancestor
            )
            changelogs.append(changelog)
            ancestor = changelog.changes.ancestor

        return ChangelogData.concatenate(changelogs)

    async def download(self, collection_downloader: CollectionDownloader):
        missing_versions = set(self.versions)

        while missing_versions:
            missing_version = max(missing_versions)

            # Try to get hold of changelog for this version
            changelog = await self._download_changelog_stream(
                missing_version, collection_downloader
            )
            if changelog:
                current_changelog = self.changelog
                if current_changelog is None:
                    # If we didn't have a changelog so far, start with it
                    self.changelog = changelog
                    missing_versions -= {
                        SemVer(version) for version in changelog.changes.releases
                    }
                else:
                    # Insert entries from changelog into combined changelog that are missing there
                    for version, entry in changelog.changes.releases.items():
                        sem_version = SemVer(version)
                        if sem_version in missing_versions:
                            current_changelog.changes.releases[version] = entry
                            missing_versions.remove(sem_version)

            # Make sure that this version isn't checked again
            missing_versions -= {missing_version}


class AnsibleCoreChangelogCollector:
    versions: list[PypiVer]
    earliest: PypiVer
    latest: PypiVer

    changelog: ChangelogData | None

    porting_guide: bytes | None

    def __init__(self, versions: t.ValuesView[str]):
        self.versions = sorted(PypiVer(version) for version in versions)
        self.earliest = self.versions[0]
        self.latest = self.versions[-1]
        self.changelog = None
        self.porting_guide = None

    @staticmethod
    async def _get_changelog_file(
        version: PypiVer, core_downloader: t.Callable[[str], t.Awaitable[str]]
    ) -> ChangelogData | None:
        path = await core_downloader(str(version))
        if os.path.isdir(path):
            changelog: ChangelogData | None = None
            for root, dummy, files in os.walk(path):
                if "changelog.yaml" in files:
                    with open(os.path.join(root, "changelog.yaml"), "rb") as f:
                        changelog_bytes = f.read()
                    changelog_data = load_yaml_bytes(changelog_bytes)
                    changelog = ChangelogData.ansible_core(changelog_data)
            return changelog
        if os.path.isfile(path) and path.endswith(".tar.gz"):
            maybe_changelog_bytes = read_changelog_file(path, is_ansible_core=True)
            if maybe_changelog_bytes is None:
                return None
            changelog_data = load_yaml_bytes(maybe_changelog_bytes)
            return ChangelogData.ansible_core(changelog_data)
        return None

    async def download_changelog(
        self, core_downloader: t.Callable[[str], t.Awaitable[str]]
    ):
        changelog = await self._get_changelog_file(self.latest, core_downloader)
        if changelog is None:
            return

        changelog.changes.prune_versions(
            versions_after=None, versions_until=str(self.latest)
        )

        changelogs = [changelog]
        ancestor = changelog.changes.ancestor
        while ancestor is not None:
            ancestor_ver = PypiVer(ancestor)
            if ancestor_ver < self.earliest:
                break
            changelog = await self._get_changelog_file(ancestor_ver, core_downloader)
            if changelog is None:
                break
            changelog.changes.prune_versions(
                versions_after=None, versions_until=ancestor
            )
            changelogs.append(changelog)
            ancestor = changelog.changes.ancestor

        self.changelog = ChangelogData.concatenate(changelogs)

    async def download_porting_guide(self, aio_session: aiohttp.client.ClientSession):
        query_url = get_core_porting_guide_url(self.latest)
        async with aio_session.get(query_url) as response:
            self.porting_guide = await response.read()


async def collect_changelogs(
    collectors: list[CollectionChangelogCollector],
    core_collector: AnsibleCoreChangelogCollector,
    collection_cache: str | None,
    galaxy_context: GalaxyContext | None = None,
):
    lib_ctx = app_context.lib_ctx.get()
    with tempfile.TemporaryDirectory() as tmp_dir:
        async with aiohttp.ClientSession(trust_env=True) as aio_session:
            if galaxy_context is None:
                galaxy_context = await GalaxyContext.create(aio_session)
            async with asyncio_pool.AioPool(size=lib_ctx.thread_max) as pool:
                downloader = CollectionDownloader(
                    aio_session,
                    tmp_dir,
                    context=galaxy_context,
                    collection_cache=collection_cache,
                )

                async def core_downloader(version):
                    return await get_ansible_core(aio_session, version, tmp_dir)

                requestors = [
                    await pool.spawn(collector.download(downloader))
                    for collector in collectors
                ]
                requestors.append(
                    await pool.spawn(core_collector.download_changelog(core_downloader))
                )
                requestors.append(
                    await pool.spawn(core_collector.download_porting_guide(aio_session))
                )
                await asyncio.gather(*requestors)


class ChangelogEntry:
    version: PypiVer
    version_str: str
    is_ancestor: bool

    prev_version: PypiVer | None
    core_versions: dict[PypiVer, str]
    versions_per_collection: dict[str, dict[PypiVer, str]]

    core_collector: AnsibleCoreChangelogCollector
    ansible_changelog: ChangelogData
    collectors: list[CollectionChangelogCollector]

    ansible_core_version: str
    prev_ansible_core_version: str | None

    removed_collections: list[tuple[CollectionChangelogCollector, str]]
    added_collections: list[tuple[CollectionChangelogCollector, str]]
    unchanged_collections: list[tuple[CollectionChangelogCollector, str]]
    changed_collections: list[
        tuple[CollectionChangelogCollector, str, str | None, bool]
    ]

    def __init__(
        self,
        version: PypiVer,
        version_str: str,
        prev_version: PypiVer | None,
        ancestor_version: PypiVer | None,
        core_versions: dict[PypiVer, str],
        versions_per_collection: dict[str, dict[PypiVer, str]],
        core_collector: AnsibleCoreChangelogCollector,
        ansible_changelog: ChangelogData,
        collectors: list[CollectionChangelogCollector],
    ):
        self.version = version
        self.version_str = version_str
        self.is_ancestor = (
            False if ancestor_version is None else ancestor_version == version
        )
        self.prev_version = prev_version = prev_version or ancestor_version
        self.core_versions = core_versions
        self.versions_per_collection = versions_per_collection
        self.core_collector = core_collector
        self.ansible_changelog = ansible_changelog
        self.collectors = collectors

        self.ansible_core_version = core_versions[version]
        self.prev_ansible_core_version = (
            core_versions.get(prev_version) if prev_version else None
        )

        self.removed_collections = []
        self.added_collections = []
        self.unchanged_collections = []
        self.changed_collections = []
        for collector in collectors:
            if version not in versions_per_collection[collector.collection]:
                if (
                    prev_version
                    and prev_version in versions_per_collection[collector.collection]
                ):
                    self.removed_collections.append(
                        (
                            collector,
                            versions_per_collection[collector.collection][prev_version],
                        )
                    )

                continue

            collection_version: str = versions_per_collection[collector.collection][
                version
            ]

            prev_collection_version: str | None = (
                versions_per_collection[collector.collection].get(prev_version)
                if prev_version
                else None
            )
            added = False
            if prev_version:
                if not prev_collection_version:
                    self.added_collections.append((collector, collection_version))
                    added = True
                elif prev_collection_version == collection_version:
                    self.unchanged_collections.append((collector, collection_version))
                    continue

            self.changed_collections.append(
                (collector, collection_version, prev_collection_version, added)
            )


class Changelog:
    ansible_version: PypiVer
    ansible_ancestor_version: PypiVer | None
    entries: list[ChangelogEntry]
    core_collector: AnsibleCoreChangelogCollector
    ansible_changelog: ChangelogData
    collection_collectors: list[CollectionChangelogCollector]
    collection_metadata: CollectionsMetadata

    def __init__(
        self,
        ansible_version: PypiVer,
        ansible_ancestor_version: PypiVer | None,
        entries: list[ChangelogEntry],
        core_collector: AnsibleCoreChangelogCollector,
        ansible_changelog: ChangelogData,
        collection_collectors: list[CollectionChangelogCollector],
        collection_metadata: CollectionsMetadata,
    ):
        self.ansible_version = ansible_version
        self.ansible_ancestor_version = ansible_ancestor_version
        self.entries = entries
        self.core_collector = core_collector
        self.ansible_changelog = ansible_changelog
        self.collection_collectors = collection_collectors
        self.collection_metadata = collection_metadata


def _markup_to_rst(markup: str) -> str:
    return _ansible_markup_to_rst(
        _parse_ansible_markup(
            markup,
            _AnsibleMarkupContext(),
            whitespace=_AnsibleMarkupWhitespace.KEEP_SINGLE_NEWLINES,
        )
    )


def _get_link(
    removal: RemovedRemovalInformation | RemovalInformation,
    /,
    override: str | None = None,
) -> str:
    url = override or removal.discussion
    return f" (`{url} <{url}>`__)" if url else ""


def _create_fragment(
    section: str, sentences: list[str | None] | list[str]
) -> ChangelogFragment:
    return ChangelogFragment(
        content={
            section: [
                "\n".join(sentence for sentence in sentences if sentence),
            ],
        },
        path="<internal>",
        fragment_format=TextFormat.RESTRUCTURED_TEXT,
    )


def _get_removal_entry(  # noqa: C901, pylint:disable=too-many-branches
    collection: str,
    removal: RemovalInformation,
    /,
    announce_version: PypiVer,
    ansible_version: PypiVer,
    discussion_override: str | None = None,
    reason_override: str | None = None,
    reason_text_override: str | None = None,
) -> tuple[ChangelogFragment, str] | None:
    if announce_version.major != ansible_version.major:
        return None

    sentences = []
    link = _get_link(removal, override=discussion_override)

    reason = reason_override or removal.reason
    reason_text = reason_text_override or removal.reason_text

    if reason == "deprecated":
        sentences.append(f"The ``{collection}`` collection has been deprecated.")
        sentences.append(
            f"It will be removed from Ansible {removal.major_version} if no one"
            f" starts maintaining it again before Ansible {removal.major_version}."
        )
        sentences.append(
            "See `Collections Removal Process for unmaintained collections"
            " <https://docs.ansible.com/ansible/devel/community/collection_contributors/"
            "collection_package_removal.html#unmaintained-collections"
            f">`__ for more details{link}."
        )

    elif reason == "considered-unmaintained":
        sentences.append(
            f"The ``{collection}`` collection is considered unmaintained"
            f" and will be removed from Ansible {removal.major_version}"
            f" if no one starts maintaining it again before Ansible {removal.major_version}."
        )
        sentences.append(
            "See `Collections Removal Process for unmaintained collections"
            " <https://docs.ansible.com/ansible/devel/community/collection_contributors/"
            "collection_package_removal.html#unmaintained-collections"
            f">`__ for more details, including for how this can be cancelled{link}."
        )

    elif reason == "renamed":
        sentences.append(
            f"The collection ``{collection}`` was renamed to ``{removal.new_name}``."
        )
        sentences.append("For now both collections are included in Ansible.")
        if removal.redirect_replacement_major_version is not None:
            if ansible_version.major < removal.redirect_replacement_major_version:
                sentences.append(
                    f"The content in ``{collection}`` will be replaced by deprecated"
                    f" redirects in Ansible {removal.redirect_replacement_major_version}.0.0."
                )
            else:
                sentences.append(
                    f"The content in ``{collection}`` has been replaced by deprecated"
                    f" redirects in Ansible {removal.redirect_replacement_major_version}.0.0."
                )
        if removal.major_version != "TBD":
            sentences.append(
                f"The collection will be completely removed from Ansible {removal.major_version}."
            )
        else:
            sentences.append(
                "The collection will be completely removed from Ansible eventually."
            )
        sentences.append(
            f"Please update your FQCNs from ``{collection}`` to ``{removal.new_name}``{link}."
        )

    elif reason == "guidelines-violation":
        sentences.append(
            f"The {collection} collection will be removed from Ansible {removal.major_version}"
            " due to violations of the Ansible inclusion requirements."
        )
        if reason_text:
            sentences.append(_markup_to_rst(reason_text))
        sentences.append(
            "See `Collections Removal Process for collections"
            " not satisfying the collection requirements"
            " <https://docs.ansible.com/ansible/devel/community/collection_contributors/"
            "collection_package_removal.html#collections-not-satisfying-the-collection-requirements"
            f">`__ for more details, including for how this can be cancelled{link}."
        )

    elif reason == "other":
        sentences.append(
            f"The {collection} collection will be removed from Ansible {removal.major_version}."
        )
        if reason_text:
            sentences.append(_markup_to_rst(reason_text))
        if removal.discussion:
            sentences.append(
                f"See `the removal discussion for details <{removal.discussion}>`__."
            )
        else:
            sentences.append(
                "To discuss this, please `create a community topic"
                " <https://docs.ansible.com/ansible/devel/community/steering/"
                "community_steering_committee.html#creating-community-topic>`__."
            )

    if sentences and reason not in ("renamed", "deprecated"):
        sentences.append(
            "After removal, users can still install this collection with "
            f"``ansible-galaxy collection install {collection}``."
        )

    if not sentences:
        return None
    return _create_fragment("deprecated_features", sentences), str(announce_version)


def _get_removed_entry(  # noqa: C901, pylint:disable=too-many-branches
    collection: str,
    removal: RemovedRemovalInformation | RemovalInformation,
    /,
    removal_version: PypiVer,
    ansible_version: PypiVer,
    discussion_override: str | None = None,
    reason_override: str | None = None,
    reason_text_override: str | None = None,
) -> tuple[ChangelogFragment, str] | None:
    if ansible_version.major != removal_version.major:
        return None

    sentences = []
    link = _get_link(removal, override=discussion_override)

    reason = reason_override or removal.reason
    reason_text = reason_text_override or removal.reason_text

    if reason == "deprecated":
        sentences.append(
            f"The deprecated ``{collection}`` collection has been removed{link}."
        )

    elif reason == "considered-unmaintained":
        sentences.append(
            f"The ``{collection}`` collection was considered unmaintained"
            f" and has been removed from Ansible {removal_version.major}{link}."
        )

    elif reason == "renamed":
        sentences.append(
            f"The collection ``{collection}`` has been completely removed from Ansible."
        )
        sentences.append(f"It has been renamed to ``{removal.new_name}``.")
        if removal.redirect_replacement_major_version is not None:
            sentences.append(
                f"``{collection}`` has been replaced by deprecated redirects to"
                f" ``{removal.new_name}``"
                f" in Ansible {removal.redirect_replacement_major_version}.0.0."
            )
        else:
            sentences.append(
                "The collection will be completely removed from Ansible eventually."
            )
        sentences.append(
            f"Please update your FQCNs from ``{collection}`` to ``{removal.new_name}``{link}."
        )

    elif reason == "guidelines-violation":
        sentences.append(
            f"The {collection} collection has been removed from Ansible {removal_version.major}"
            " due to violations of the Ansible inclusion requirements."
        )
        if reason_text:
            sentences.append(_markup_to_rst(reason_text))
        sentences.append(
            "See `Collections Removal Process for collections"
            " not satisfying the collection requirements"
            " <https://docs.ansible.com/ansible/devel/community/collection_contributors/"
            "collection_package_removal.html#collections-not-satisfying-the-collection-requirements"
            f">`__ for more details{link}."
        )

    elif reason == "other":
        sentences.append(
            f"The {collection} collection has been removed from Ansible {removal_version.major}."
        )
        if reason_text:
            sentences.append(_markup_to_rst(reason_text))
        if removal.discussion:
            sentences.append(
                f"See `the removal discussion <{removal.discussion}>`__ for details."
            )
        else:
            sentences.append(
                "To discuss this, please `create a community topic"
                " <https://docs.ansible.com/ansible/devel/community/steering/"
                "community_steering_committee.html#creating-community-topic>`__."
            )

    if sentences and reason not in ("renamed", "deprecated"):
        sentences.append(
            "Users can still install this collection with "
            f"``ansible-galaxy collection install {collection}``."
        )

    if not sentences:
        return None
    return _create_fragment("removed_features", sentences), str(removal_version)


def _get_update_entry(
    collection: str,
    removal: RemovalInformation,
    update: RemovalUpdate,
    ansible_version: PypiVer,
) -> tuple[ChangelogFragment, str] | None:
    if update.cancelled_version:
        link = _get_link(removal)
        return _create_fragment(
            "major_changes",
            [
                f"The removal of {collection} was cancelled. The collection will"
                f" not be removed from Ansible {removal.major_version}{link}.",
                update.reason_text,
            ],
        ), str(update.cancelled_version)
    if update.readded_version:
        link = _get_link(removal)
        return _create_fragment(
            "major_changes",
            [
                f"The previously removed collection {collection} was"
                f" re-added to Ansible {ansible_version.major}{link}.",
                update.reason_text,
            ],
        ), str(update.readded_version)
    if update.deprecated_version:
        return _get_removal_entry(
            collection,
            removal,
            announce_version=update.deprecated_version,
            ansible_version=ansible_version,
            discussion_override=update.discussion,
            reason_override=update.reason,
            reason_text_override=update.reason_text,
        )
    if update.redeprecated_version:
        # TODO: adjust message when re-deprecating?
        return _get_removal_entry(
            collection,
            removal,
            announce_version=update.redeprecated_version,
            ansible_version=ansible_version,
            discussion_override=update.discussion,
            reason_override=update.reason,
            reason_text_override=update.reason_text,
        )
    if update.removed_version:
        return _get_removed_entry(
            collection,
            removal,
            removal_version=update.removed_version,
            ansible_version=ansible_version,
            discussion_override=update.discussion,
            reason_override=update.reason,
            reason_text_override=update.reason_text,
        )
    return None


def _extract_fragment_text(fragment: ChangelogFragment) -> str:
    if len(fragment.content) == 1:
        key, value = list(fragment.content.items())[0]
        if len(value) == 1:
            return f"{key}: {value[0]}"
    return repr(fragment.content)


def _populate_ansible_changelog(
    ansible_changelog: ChangelogData,
    collection_metadata: CollectionsMetadata,
    ansible_version: PypiVer,
) -> None:
    flog = mlog.fields(func="_populate_ansible_changelog")

    # Figure out whether GA (x.0.0 release) of this Ansible major version is already out
    collapse_first_version = (
        ansible_version.minor > 0
        or ansible_version.micro > 0
        or not ansible_version.pre
    )
    ga_release = PypiVer(f"{ansible_version.major}.0.0")

    for collection, metadata in collection_metadata.collections.items():
        if metadata.removal:
            updates = metadata.removal.get_updates_including_indirect()

            # If (1) the first two updates are removal and re-adding the collection,
            # and (2) both happened before GA, and (3) we already reached GA, then
            # both messages will appear under the GA release. This is somewhat
            # confusing, so we remove them both.
            if (
                collapse_first_version
                and len(updates) >= 2
                and updates[0].removed_version
                and updates[1].readded_version
                and updates[1].readded_version < ga_release
            ):
                updates = updates[2:]

            for update in updates:
                fragment_version = _get_update_entry(
                    collection, metadata.removal, update, ansible_version
                )
                if fragment_version:
                    fragment, version = fragment_version
                    if version in ansible_changelog.changes.releases:
                        ansible_changelog.changes.add_fragment(fragment, version)
                    else:
                        flog.warning(
                            f"Found changelog entry for {version}, which does not yet exist: {{}}",
                            _extract_fragment_text(fragment),
                        )

    for collection, removed_metadata in collection_metadata.removed_collections.items():
        fragment_version = _get_removed_entry(
            collection,
            removed_metadata.removal,
            removed_metadata.removal.version,
            ansible_version,
        )
        if fragment_version:
            fragment, version = fragment_version
            if version in ansible_changelog.changes.releases:
                ansible_changelog.changes.add_fragment(fragment, version)
            else:
                flog.warning(
                    f"Found changelog entry for {version}, which does not yet exist: {{}}",
                    _extract_fragment_text(fragment),
                )


def _cleanup_collection_version(
    collection_name: str,
    collection_data: dict[SemVer, RemoveCollectionVersionSchema],
    changelog: ChangelogData,
) -> None:
    flog = mlog.fields(func="_cleanup_collection_version")
    for version, data in collection_data.items():
        release = changelog.changes.releases.get(str(version))
        changes = (release or {}).get("changes")
        if not changes:
            flog.warning(
                f"Trying to remove changelog entries from {collection_name} {version},"
                " but found no release"
            )
            continue
        for category, entries in data.changes.items():
            if category not in changes:
                flog.warning(
                    f"Trying to remove {category!r} changelog entries from"
                    f" {collection_name} {version}, but found no entries"
                )
                continue
            for entry in entries:
                try:
                    changes[category].remove(entry)
                except ValueError:
                    flog.warning(
                        f"Cannot find {category!r} changelog entry for"
                        f" {collection_name} {version}: {entry!r}"
                    )


def _cleanup_collection_changelogs(
    ansible_changelog: ChangelogData,
    collection_collectors: list[CollectionChangelogCollector],
) -> None:
    flog = mlog.fields(func="_populate_ansible_changelog")
    rcce = ansible_changelog.remove_collection_changelog_entries
    if not rcce:
        return

    for collection_collector in collection_collectors:
        collection_data = rcce.get(collection_collector.collection)
        if not collection_data:
            continue
        changelog = collection_collector.changelog
        if not changelog:
            flog.warning(
                f"Trying to remove changelog entries from {collection_collector.collection},"
                " but found no changelog"
            )
            continue
        _cleanup_collection_version(
            collection_collector.collection, collection_data, changelog
        )


def get_changelog(
    ansible_version: PypiVer,
    deps_dir: str | None,
    deps_data: list[DependencyFileData] | None = None,
    collection_cache: str | None = None,
    ansible_changelog: ChangelogData | None = None,
    galaxy_context: GalaxyContext | None = None,
) -> Changelog:
    flog = mlog.fields(func="get_changelog")
    dependencies: dict[str, DependencyFileData] = {}

    ansible_changelog = ansible_changelog or ChangelogData.ansible(directory=deps_dir)
    ansible_ancestor_version_str = ansible_changelog.changes.ancestor
    ansible_ancestor_version = (
        PypiVer(ansible_ancestor_version_str) if ansible_ancestor_version_str else None
    )

    collection_metadata = CollectionsMetadata.load_from(deps_dir)
    _populate_ansible_changelog(ansible_changelog, collection_metadata, ansible_version)

    if deps_dir is not None:
        for path in glob.glob(os.path.join(deps_dir, "*.deps"), recursive=False):
            deps_file = DepsFile(path)
            deps = deps_file.parse()
            deps.deps.pop("_python", None)
            version = PypiVer(deps.ansible_version)
            if version > ansible_version:
                flog.info(
                    f"Ignoring {path}, since {deps.ansible_version}"
                    f" is newer than {ansible_version}"
                )
                continue
            dependencies[deps.ansible_version] = deps
    if deps_data:
        for deps in deps_data:
            dependencies[deps.ansible_version] = deps

    core_versions: dict[PypiVer, str] = {}
    versions: dict[str, tuple[PypiVer, DependencyFileData]] = {}
    versions_per_collection: dict[str, dict[PypiVer, str]] = defaultdict(dict)
    for deps in dependencies.values():
        version = PypiVer(deps.ansible_version)
        versions[deps.ansible_version] = (version, deps)
        core_versions[version] = deps.ansible_core_version
        for collection_name, collection_version in deps.deps.items():
            versions_per_collection[collection_name][version] = collection_version

    core_collector = AnsibleCoreChangelogCollector(core_versions.values())
    collectors = [
        CollectionChangelogCollector(
            collection, versions_per_collection[collection].values()
        )
        for collection in sorted(versions_per_collection.keys())
    ]
    asyncio.run(
        collect_changelogs(collectors, core_collector, collection_cache, galaxy_context)
    )

    _cleanup_collection_changelogs(ansible_changelog, collectors)

    changelog = []

    sorted_versions = collect_versions(versions, ansible_changelog.config)
    for index, (version_str, dummy) in enumerate(sorted_versions):
        version, deps = versions[version_str]
        prev_version = None
        if index + 1 < len(sorted_versions):
            prev_version = versions[sorted_versions[index + 1][0]][0]

        changelog.append(
            ChangelogEntry(
                version,
                version_str,
                prev_version,
                ansible_ancestor_version,
                core_versions,
                versions_per_collection,
                core_collector,
                ansible_changelog,
                collectors,
            )
        )

    return Changelog(
        ansible_version,
        ansible_ancestor_version,
        changelog,
        core_collector,
        ansible_changelog,
        collectors,
        collection_metadata,
    )
