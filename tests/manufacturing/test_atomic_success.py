# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

import pytest

from core.api.quantity_contract import normalize_quantity_to_base_int
from core.api.schemas.manufacturing import RecipeRunRequest
from core.manufacturing.service import execute_run_txn, validate_run

pytestmark = pytest.mark.api


@pytest.fixture()
def manufacturing_success_setup(request: pytest.FixtureRequest):
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    recipes_module = env["recipes"]
    client = env["client"]

    with engine_module.SessionLocal() as db:
        input_qty_base = normalize_quantity_to_base_int(
            dimension="count",
            uom="ea",
            quantity_decimal="8",
        )
        batch_qty_base = normalize_quantity_to_base_int(
            dimension="count",
            uom="ea",
            quantity_decimal="4",
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
                qty_required=3.0,
                is_optional=False,
            )
        )

        db.add_all(
            [
                models_module.ItemBatch(
                    item_id=input_item.id,
                    qty_initial=batch_qty_base,
                    qty_remaining=batch_qty_base,
                    unit_cost_cents=10,
                    source_kind="seed",
                    source_id=None,
                    is_oversold=False,
                ),
                models_module.ItemBatch(
                    item_id=input_item.id,
                    qty_initial=batch_qty_base,
                    qty_remaining=batch_qty_base,
                    unit_cost_cents=20,
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


def test_atomic_multiple_input_batches_one_output_batch(manufacturing_success_setup):
    client = manufacturing_success_setup["client"]
    engine = manufacturing_success_setup["engine"]
    models = manufacturing_success_setup["models"]
    recipes = manufacturing_success_setup["recipes"]

    with engine.SessionLocal() as db:
        body = RecipeRunRequest(recipe_id=manufacturing_success_setup["recipe_id"], output_qty=1)
        output_item_id, required, k, shortages = validate_run(db, body)
        assert shortages == []
        with pytest.raises(RuntimeError):
            execute_run_txn(
                db,
                body,
                output_item_id,
                required,
                k,
                on_before_commit=lambda _res: (_ for _ in ()).throw(RuntimeError("boom")),
            )

        assert db.query(recipes.ManufacturingRun).count() == 0
        assert db.query(models.ItemMovement).filter(models.ItemMovement.source_kind == "manufacturing").count() == 0
        remaining_batches = db.query(models.ItemBatch).order_by(models.ItemBatch.id).all()
        expected_batch_qty = normalize_quantity_to_base_int(
            dimension="count",
            uom="ea",
            quantity_decimal="4",
        )
        assert [b.qty_remaining for b in remaining_batches] == [
            expected_batch_qty,
            expected_batch_qty,
        ]

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": manufacturing_success_setup["recipe_id"], "output_qty": 2},
    )

    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    with engine.SessionLocal() as db:
        run = db.get(recipes.ManufacturingRun, run_id)
        assert run.status == "completed"
        assert run.executed_at is not None

        movements = (
            db.query(models.ItemMovement)
            .filter(models.ItemMovement.source_kind == "manufacturing", models.ItemMovement.source_id == run.id)
            .order_by(models.ItemMovement.id)
            .all()
        )
        assert len(movements) == 3
        negative = [m for m in movements if m.qty_change < 0]
        expected_4 = normalize_quantity_to_base_int("count", "ea", "4")
        expected_2 = normalize_quantity_to_base_int("count", "ea", "2")
        assert sorted([(m.batch_id, m.qty_change, m.unit_cost_cents) for m in negative]) == [
            (1, -expected_4, 10),
            (2, -expected_2, 20),
        ]
        positive = [m for m in movements if m.qty_change > 0]
        assert len(positive) == 1
        expected_output = normalize_quantity_to_base_int("count", "ea", "2")
        assert positive[0].qty_change == expected_output

        remaining_batches = db.query(models.ItemBatch).order_by(models.ItemBatch.id).all()
        expected_0 = 0
        expected_2 = normalize_quantity_to_base_int("count", "ea", "2")

        assert [b.qty_remaining for b in remaining_batches] == [
            expected_0,
            expected_2,
            expected_2,
        ]

        meta = json.loads(run.meta)
        assert meta["cost_inputs_cents"] == 80
        assert meta["per_output_cents"] == 40
