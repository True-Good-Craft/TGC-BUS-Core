# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from core.api.cost_contract import normalize_cost_to_base_cents

pytestmark = pytest.mark.api


def test_normalize_cost_to_base_cents_count_dimension():
    # $1.00 per ea, 1 ea=1000 base -> 0.1 cents/base -> rounds to 0
    assert normalize_cost_to_base_cents("count", "ea", "1.00") == 0


def test_normalize_cost_to_base_cents_weight_dimension():
    # $1.00 per kg, 1 kg=1,000,000 mg -> 0.0001 cents/base -> rounds to 0
    assert normalize_cost_to_base_cents("weight", "kg", "1.00") == 0


def test_normalize_cost_to_base_cents_invalid_uom_rejected():
    with pytest.raises(Exception):
        normalize_cost_to_base_cents("weight", "ea", "1.00")


def test_normalize_cost_to_base_cents_round_half_up_behavior():
    # $5.00 per ea => 500/1000 = 0.5 cents/base -> rounds half-up to 1
    assert normalize_cost_to_base_cents("count", "ea", "5.00") == 1
