# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


@pytest.fixture()
def manufacturing_setup(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    monkeypatch.setenv("BUS_DEV", "1")
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    recipes_module = env["recipes"]
    client = env["client"]

    with engine_module.SessionLocal() as db:
        output_item = models_module.Item(name="Output", uom="ea", qty_stored=0)
        input_item = models_module.Item(name="Input", uom="ea", qty_stored=0)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = recipes_module.Recipe(name="Widget", output_item_id=output_item.id, output_qty=1)
        db.add(recipe)
        db.flush()

        db.add(
            recipes_module.RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=5,
                is_optional=False,
            )
        )
        db.commit()

        recipe_id = recipe.id
        input_item_id = input_item.id

    return {
        **env,
        "recipe_id": recipe_id,
        "input_item_id": input_item_id,
    }


def test_shortage_returns_400_and_no_movements(manufacturing_setup):
    client = manufacturing_setup["client"]
    engine = manufacturing_setup["engine"]
    models = manufacturing_setup["models"]
    recipes = manufacturing_setup["recipes"]

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": manufacturing_setup["recipe_id"], "output_qty": 1},
    )

    assert resp.status_code == 400
    payload = resp.json()["detail"]
    assert payload["error"] == "insufficient_stock"
    assert payload["message"] == "Insufficient stock for required components."
    assert payload["shortages"] == [
        {
            "component": manufacturing_setup["input_item_id"],
            "required": 5,
            "available": 0,
        }
    ]
    assert payload["run_id"]

    with engine.SessionLocal() as db:
        runs = db.query(recipes.ManufacturingRun).all()
        assert len(runs) == 1
        assert runs[0].status == "failed_insufficient_stock"
        assert db.query(models.ItemMovement).count() == 0
        assert db.query(models.ItemBatch).count() == 0
