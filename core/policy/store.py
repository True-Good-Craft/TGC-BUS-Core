# SPDX-License-Identifier: AGPL-3.0-or-later
# TGC BUS Core (Business Utility System Core)
# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

from core.config.manager import load_policy_config, save_policy_config
from core.config.writes import (
    get_writes_enabled as _get_writes_enabled,
    set_writes_enabled as _set_writes_enabled,
)

from .model import Policy, Role

DEFAULT_POLICY = Policy(role=Role.OWNER, plan_only=False)  # framework present, OFF by default


def load_policy() -> Policy:
    data = load_policy_config()
    try:
        role = Role(str(data.get("role", DEFAULT_POLICY.role.value)))
    except Exception:
        role = DEFAULT_POLICY.role
    plan_only = bool(data.get("plan_only", DEFAULT_POLICY.plan_only))
    return Policy(role=role, plan_only=plan_only)


def save_policy(policy: Policy) -> None:
    save_policy_config(role=policy.role.value, plan_only=bool(policy.plan_only))


def get_writes_enabled() -> bool:
    return _get_writes_enabled()


def set_writes_enabled(enabled: bool) -> None:
    _set_writes_enabled(enabled)

