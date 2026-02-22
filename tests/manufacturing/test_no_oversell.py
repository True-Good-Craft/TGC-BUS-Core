# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from core.api.quantity_contract import normalize_quantity_to_base_int

pytestmark = pytest.mark.api


@pytest.fixture()
def manufacturing_no_oversell_setup(request: pytest.FixtureRequest):
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    recipes_module = env["recipes"]
    client = env["client"]

    with engine_module.SessionLocal() as db:
        input_qty_base = normalize_quantity_to_base_int(
            dimension="count",
            uom="ea",
            quantity_decimal="6",
        )
        output_item = models_module.Item(name="Output", uom="ea", qty_stored=0)
        input_item = models_module.Item(name="Input", uom="ea", qty_stored=input_qty_base)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = recipes_module.Recipe(name="Widget", output_item_id=output_item.id, output_qty=1.0)
        db.add(recipe)
        db.flush()

        db.add(
            recipes_module.RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=2.0,
                is_optional=False,
            )
        )

        db.add(
            models_module.ItemBatch(
                item_id=input_item.id,
                qty_initial=input_qty_base,
                qty_remaining=input_qty_base,
                unit_cost_cents=15,
                source_kind="seed",
                source_id=None,
                is_oversold=False,
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


def test_never_sets_is_oversold_on_manufacturing(manufacturing_no_oversell_setup):
    client = manufacturing_no_oversell_setup["client"]
    engine = manufacturing_no_oversell_setup["engine"]
    models = manufacturing_no_oversell_setup["models"]

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": manufacturing_no_oversell_setup["recipe_id"], "output_qty": 2},
    )

    assert resp.status_code == 200

    with engine.SessionLocal() as db:
        movements = (
            db.query(models.ItemMovement)
            .filter(models.ItemMovement.source_kind == "manufacturing")
            .all()
        )
        assert movements
        assert all(m.is_oversold is False for m in movements)


def test_constraint_rejects_oversold_flag(manufacturing_no_oversell_setup):
    engine = manufacturing_no_oversell_setup["engine"]
    models = manufacturing_no_oversell_setup["models"]

    with engine.SessionLocal() as db:
        db.add(
            models.ItemMovement(
                item_id=manufacturing_no_oversell_setup["input_item_id"],
                batch_id=None,
                qty_change=-1.0,
                unit_cost_cents=0,
                source_kind="manufacturing",
                source_id=None,
                is_oversold=True,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
