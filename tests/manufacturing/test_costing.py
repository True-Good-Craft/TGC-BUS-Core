# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

import pytest

from core.money import round_half_up_cents

pytestmark = pytest.mark.api


@pytest.fixture()
def costing_setup(request: pytest.FixtureRequest):
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    recipes_module = env["recipes"]
    client = env["client"]

    with engine_module.SessionLocal() as db:
        output_item = models_module.Item(name="Output", uom="ea", qty_stored=0)
        input_item = models_module.Item(name="Input", uom="ea", qty_stored=3)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = recipes_module.Recipe(name="Widget", output_item_id=output_item.id, output_qty=6.0)
        db.add(recipe)
        db.flush()

        db.add(
            recipes_module.RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=3.0,
                is_optional=False,
            )
        )

        db.add_all(
            [
                models_module.ItemBatch(
                    item_id=input_item.id,
                    qty_initial=1.0,
                    qty_remaining=1.0,
                    unit_cost_cents=5,
                    source_kind="seed",
                    source_id=None,
                    is_oversold=False,
                ),
                models_module.ItemBatch(
                    item_id=input_item.id,
                    qty_initial=1.0,
                    qty_remaining=1.0,
                    unit_cost_cents=6,
                    source_kind="seed",
                    source_id=None,
                    is_oversold=False,
                ),
                models_module.ItemBatch(
                    item_id=input_item.id,
                    qty_initial=1.0,
                    qty_remaining=1.0,
                    unit_cost_cents=4,
                    source_kind="seed",
                    source_id=None,
                    is_oversold=False,
                ),
            ]
        )
        db.commit()

        recipe_id = recipe.id
        input_item_id = input_item.id
        output_item_id = output_item.id

    return {
        **env,
        "recipe_id": recipe_id,
        "input_item_id": input_item_id,
        "output_item_id": output_item_id,
    }


def test_unit_cost_round_half_up(costing_setup):
    client = costing_setup["client"]
    engine = costing_setup["engine"]
    models = costing_setup["models"]
    recipes = costing_setup["recipes"]

    assert round_half_up_cents(2.5) == 3
    assert round_half_up_cents(123456.5) == 123457
    assert round_half_up_cents(2.49) == 2

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": costing_setup["recipe_id"], "output_qty": 6},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["output_unit_cost_cents"] == 3

    with engine.SessionLocal() as db:
        run = db.get(recipes.ManufacturingRun, data["run_id"])
        assert run.status == "completed"
        meta = json.loads(run.meta)
        assert meta["cost_inputs_cents"] == 15
        assert meta["per_output_cents"] == 3

        output_batch = (
            db.query(models.ItemBatch)
            .filter(models.ItemBatch.source_kind == "manufacturing", models.ItemBatch.source_id == run.id)
            .one()
        )
        assert output_batch.unit_cost_cents == 3
        assert output_batch.qty_remaining == pytest.approx(6.0)
