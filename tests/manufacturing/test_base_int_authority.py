# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

from core.api.schemas.manufacturing import RecipeRunRequest
from core.manufacturing.service import validate_run

pytestmark = pytest.mark.api


def test_validate_run_uses_base_int_shortage_math(request: pytest.FixtureRequest):
    env = request.getfixturevalue("bus_client")

    with env["engine"].SessionLocal() as db:
        output_item = env["models"].Item(name="Dough", uom="g", dimension="weight", qty_stored=0)
        input_item = env["models"].Item(name="Flour", uom="g", dimension="weight", qty_stored=26000)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = env["recipes"].Recipe(name="Loaf", output_item_id=output_item.id, output_qty=1000)
        db.add(recipe)
        db.flush()
        db.add(
            env["recipes"].RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=6000,
                is_optional=False,
            )
        )
        db.add(
            env["models"].ItemBatch(
                item_id=input_item.id,
                qty_initial=26000,
                qty_remaining=26000,
                unit_cost_cents=1,
                source_kind="seed",
                source_id=None,
                is_oversold=False,
            )
        )
        db.commit()
        output_item_id_expected = int(output_item.id)
        input_item_id_expected = int(input_item.id)

        body = RecipeRunRequest(recipe_id=recipe.id, quantity_decimal="1", uom="g", output_qty=999999.0)
        output_item_id, required_components, output_qty_base, shortages = validate_run(db, body)

    assert output_item_id == output_item_id_expected
    assert output_qty_base == 1000
    assert required_components == [
        {"item_id": input_item_id_expected, "required_base": 6000, "is_optional": False},
    ]
    assert shortages == []


def test_canonical_manufacture_accepts_human_inputs_and_hides_base_fields(request: pytest.FixtureRequest):
    env = request.getfixturevalue("bus_client")
    client = env["client"]

    with env["engine"].SessionLocal() as db:
        output_item = env["models"].Item(name="Output", uom="ea", qty_stored=0)
        input_item = env["models"].Item(name="Input", uom="ea", qty_stored=3)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = env["recipes"].Recipe(name="Widget", output_item_id=output_item.id, output_qty=1)
        db.add(recipe)
        db.flush()
        db.add(
            env["recipes"].RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=3,
                is_optional=False,
            )
        )

        db.add(
            env["models"].ItemBatch(
                item_id=input_item.id,
                qty_initial=3,
                qty_remaining=3,
                unit_cost_cents=10,
                source_kind="seed",
                source_id=None,
                is_oversold=False,
            )
        )
        db.commit()
        recipe_id = int(recipe.id)

    resp = client.post(
        "/app/manufacture",
        json={"recipe_id": recipe_id, "quantity_decimal": "1", "uom": "mc"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["ok"] is True
    assert "output_qty_base" not in payload
    assert "required_components" not in payload
