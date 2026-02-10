# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration


def bootstrap_app(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    monkeypatch.setenv("BUS_DEV", "1")
    return request.getfixturevalue("bus_client")


def snapshot_counts(db, models, recipes):
    return {
        "runs": db.query(recipes.ManufacturingRun).count(),
        "movements": db.query(models.ItemMovement).count(),
        "batches": db.query(models.ItemBatch).count(),
    }


def assert_counts_delta(before, after, *, runs=0, movements=0, batches=0):
    assert after["runs"] - before["runs"] == runs
    assert after["movements"] - before["movements"] == movements
    assert after["batches"] - before["batches"] == batches


@pytest.fixture()
def manufacturing_failfast_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    env = bootstrap_app(monkeypatch, request)

    with env["engine"].SessionLocal() as db:
        output_item = env["models"].Item(name="Output", uom="ea", qty_stored=0)
        input_item = env["models"].Item(name="Input", uom="ea", qty_stored=0)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = env["recipes"].Recipe(name="Widget", output_item_id=output_item.id, output_qty=1.0)
        db.add(recipe)
        db.flush()

        db.add(
            env["recipes"].RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=5.0,
                is_optional=False,
            )
        )
        db.commit()

        recipe_id = recipe.id
        input_item_id = input_item.id

    yield {**env, "recipe_id": recipe_id, "input_item_id": input_item_id}


@pytest.fixture()
def manufacturing_success_env(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    env = bootstrap_app(monkeypatch, request)

    with env["engine"].SessionLocal() as db:
        output_item = env["models"].Item(name="Output", uom="ea", qty_stored=0)
        input_item = env["models"].Item(name="Input", uom="ea", qty_stored=8)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = env["recipes"].Recipe(name="Widget", output_item_id=output_item.id, output_qty=1.0)
        db.add(recipe)
        db.flush()

        db.add(
            env["recipes"].RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=3.0,
                is_optional=False,
            )
        )

        db.add_all(
            [
                env["models"].ItemBatch(
                    item_id=input_item.id,
                    qty_initial=4.0,
                    qty_remaining=4.0,
                    unit_cost_cents=10,
                    source_kind="seed",
                    source_id=None,
                    is_oversold=False,
                ),
                env["models"].ItemBatch(
                    item_id=input_item.id,
                    qty_initial=4.0,
                    qty_remaining=4.0,
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

    yield {
        **env,
        "recipe_id": recipe_id,
        "input_item_id": input_item_id,
        "output_item_id": output_item_id,
    }


def test_fail_fast_has_zero_new_movements_and_batches(manufacturing_failfast_env):
    client = manufacturing_failfast_env["client"]
    engine = manufacturing_failfast_env["engine"]
    models = manufacturing_failfast_env["models"]
    recipes = manufacturing_failfast_env["recipes"]

    with engine.SessionLocal() as db:
        before = snapshot_counts(db, models, recipes)

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": manufacturing_failfast_env["recipe_id"], "output_qty": 1},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "insufficient_stock"
    assert detail["shortages"] == [
        {
            "component": manufacturing_failfast_env["input_item_id"],
            "required": 5.0,
            "available": 0.0,
        }
    ]
    assert detail["run_id"]

    with engine.SessionLocal() as db:
        after = snapshot_counts(db, models, recipes)

    assert_counts_delta(before, after, runs=1, movements=0, batches=0)


def test_success_has_expected_negative_moves_and_one_output_positive(manufacturing_success_env):
    client = manufacturing_success_env["client"]
    engine = manufacturing_success_env["engine"]
    models = manufacturing_success_env["models"]
    recipes = manufacturing_success_env["recipes"]

    with engine.SessionLocal() as db:
        before = snapshot_counts(db, models, recipes)

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": manufacturing_success_env["recipe_id"], "output_qty": 2},
    )

    assert resp.status_code == 200
    data = resp.json()

    with engine.SessionLocal() as db:
        after = snapshot_counts(db, models, recipes)
        assert_counts_delta(before, after, runs=1, movements=3, batches=1)

        run = db.get(recipes.ManufacturingRun, data["run_id"])
        assert run.status == "completed"
        meta = json.loads(run.meta)

        movements = (
            db.query(models.ItemMovement)
            .filter(models.ItemMovement.source_kind == "manufacturing", models.ItemMovement.source_id == run.id)
            .order_by(models.ItemMovement.id)
            .all()
        )
        negatives = [m for m in movements if m.qty_change < 0]
        positives = [m for m in movements if m.qty_change > 0]

        assert sorted([(m.batch_id, m.qty_change, m.unit_cost_cents) for m in negatives]) == [
            (1, -4.0, 10),
            (2, -2.0, 20),
        ]
        assert len(positives) == 1
        assert positives[0].qty_change == pytest.approx(2.0)
        assert positives[0].batch_id == meta["output_batch_id"]
        assert all(not movement.is_oversold for movement in movements)
        assert meta["cost_inputs_cents"] == 80
        assert meta["per_output_cents"] == 40
