# Copyright (C) 2023 Maxwell G <maxwell@gtmx.me>
# SPDX-License-Identifier: GPL-3.0-or-later
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from pathlib import Path
from unittest.mock import patch

import pytest
from antsibull_core.yaml import load_yaml_file

from antsibull_build.cli.antsibull_build import run


@pytest.mark.parametrize(
    "args, expected, ret",
    [
        pytest.param(
            [],
            [
                "ansible.windows 3.3.0 is not tagged in https://github.com/ansible-collections/ansible.windows",
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
            ],
            1,
            id="simple",
        ),
        pytest.param(
            ["-I", "ansible.windows"],
            [
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
            ],
            1,
            id="one-ignore",
        ),
        pytest.param(
            ["-I", "ansible.windows", "-I", "xyz"],
            [
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
                "invalid ignore 'xyz': xyz does not match any collection",
            ],
            1,
            id="one-ignore-with-invalid",
        ),
        pytest.param(
            [
                "-I",
                "ansible.windows",
                "-I",
                "check_point.mgmt",
                "-I",
                "cisco.ios",
                "-I",
                "community.postgresql",
            ],
            [],
            0,
            id="ignore-all",
        ),
        pytest.param(
            [
                "-I",
                "ansible.windows",
                "-I",
                "check_point.mgmt",
                "-I",
                "cisco.ios",
                "-I",
                "community.postgresql",
                "-I",
                "asdf",
                "-I",
                "community.general",
            ],
            [
                "invalid ignore 'asdf': asdf does not match any collection",
                "useless ignore 'community.general':"
                " community.general 11.4.2 is properly tagged",
            ],
            1,
            id="ignore-all-with-invalid",
        ),
    ],
)
def test_validate_tags_file(
    test_data_path: Path,
    capsys: pytest.CaptureFixture,
    args: list[str],
    expected: list[str],
    ret: int,
):
    path = test_data_path / "ansible-12.3.0-tags.yaml"
    assert run(["antsibull-build", "validate-tags-file", str(path), *args]) == ret
    out, err = capsys.readouterr()
    assert sorted(err.splitlines()) == sorted(expected)


@pytest.mark.parametrize(
    "args, ignore_file_contents, expected, ret",
    [
        pytest.param(
            [],
            [],
            [
                "ansible.windows 3.3.0 is not tagged in https://github.com/ansible-collections/ansible.windows",
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
            ],
            1,
            id="simple",
        ),
        pytest.param(
            [],
            ["ansible.windows"],
            [
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
            ],
            1,
            id="one-ignore",
        ),
        pytest.param(
            [],
            ["ansible.windows", "xyz"],
            [
                "check_point.mgmt 6.7.0 is not tagged in https://github.com/CheckPointSW/CheckPointAnsibleMgmtCollection",
                "cisco.ios 11.1.1 is not tagged in https://github.com/ansible-collections/cisco.ios",
                "community.postgresql 4.2.0 is not tagged in https://github.com/ansible-collections/community.postgresql",
                "invalid ignore 'xyz': xyz does not match any collection",
            ],
            1,
            id="one-ignore-with-invalid",
        ),
        pytest.param(
            [],
            [
                "ansible.windows",
                "check_point.mgmt",
                "cisco.ios",
                "community.postgresql",
            ],
            [],
            0,
            id="ignore-all",
        ),
        pytest.param(
            [],
            [
                "ansible.windows",
                "check_point.mgmt",
                "cisco.ios",
                "community.postgresql",
                "asdf",
            ],
            ["invalid ignore 'asdf': asdf does not match any collection"],
            1,
            id="ignore-all-with-invalid",
        ),
        pytest.param(
            ["-I", "ansible.windows", "-I", "xyz"],
            [
                "check_point.mgmt",
                "cisco.ios",
                "community.postgresql",
                "asdf",
            ],
            [
                "invalid ignore 'xyz': xyz does not match any collection",
                "invalid ignore 'asdf': asdf does not match any collection",
            ],
            1,
            id="mixed",
        ),
    ],
)
def test_validate_tags_file_ignore_file(
    test_data_path: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    args: list[str],
    ignore_file_contents: list[str],
    expected: list[str],
    ret: int,
):
    path = test_data_path / "ansible-12.3.0-tags.yaml"
    ignores_file = tmp_path / "ignores_file"
    ignores_file.write_text("\n".join(ignore_file_contents))
    ran = run(
        [
            "antsibull-build",
            "validate-tags-file",
            str(path),
            "--ignores-file",
            str(ignores_file),
            *args,
        ]
    )
    assert ran == ret
    out, err = capsys.readouterr()
    assert sorted(err.splitlines()) == sorted(expected)


def test_validate_tags(test_data_path: Path, tmp_path: Path):
    ignores_file = test_data_path / "validate-tags-ignores"
    name = "ansible-12.3.0-tags.yaml"
    expected_data_path = test_data_path / name
    expected_data = load_yaml_file(expected_data_path)
    output_data_path = tmp_path / name
    with patch(
        "antsibull_build.tagging.get_collections_tags", return_value=expected_data
    ):
        ran = run(
            [
                "antsibull-build",
                "validate-tags",
                f"--data-dir={test_data_path}",
                f"--ignores-file={ignores_file}",
                f"--output={output_data_path}",
                "--error-on-useless-ignores",
                "12.3.0",
            ]
        )
    assert ran == 0
    output_data = load_yaml_file(output_data_path)
    assert expected_data == output_data
