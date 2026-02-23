# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.module_utils.common.validation import check_type_list, check_type_str


_CHECK_TYPE = {
    'list': check_type_list,
    'str': check_type_str,
}


def to_list(data, elements_type = 'str'):
    elt_check = _CHECK_TYPE[elements_type]
    return [elt_check(elt) for elt in check_type_list(data)]


class FilterModule(object):
    ''' Deps file parsing filters '''

    def filters(self):
        filters = {
            '_antsibull_to_list': to_list,
        }

        return filters
