# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import pytest

pytestmark = pytest.mark.api


@pytest.fixture()
def manufacturing_journal_setup(tmp_path, monkeypatch, request: pytest.FixtureRequest):
    journal_path = tmp_path / "journals" / "manufacturing.jsonl"
    monkeypatch.setenv("BUS_MANUFACTURING_JOURNAL", str(journal_path))
    env = request.getfixturevalue("bus_client")
    engine_module = env["engine"]
    models_module = env["models"]
    recipes_module = env["recipes"]

    with engine_module.SessionLocal() as db:
        output_item = models_module.Item(name="Output", uom="ea", qty_stored=0)
        input_item = models_module.Item(name="Input", uom="ea", qty_stored=2)
        db.add_all([output_item, input_item])
        db.flush()

        recipe = recipes_module.Recipe(name="Widget", output_item_id=output_item.id, output_qty=1.0)
        db.add(recipe)
        db.flush()

        db.add(
            recipes_module.RecipeItem(
                recipe_id=recipe.id,
                item_id=input_item.id,
                qty_required=1.0,
                is_optional=False,
            )
        )

        db.add(
            models_module.ItemBatch(
                item_id=input_item.id,
                qty_initial=2.0,
                qty_remaining=2.0,
                unit_cost_cents=10,
                source_kind="seed",
                source_id=None,
                is_oversold=False,
            )
        )

        db.commit()

        recipe_id = recipe.id

    return {
        **env,
        "recipe_id": recipe_id,
        "journal_path": journal_path,
    }


def test_append_failure_does_not_rollback(manufacturing_journal_setup, monkeypatch):
    client = manufacturing_journal_setup["client"]
    engine = manufacturing_journal_setup["engine"]
    models = manufacturing_journal_setup["models"]
    recipes = manufacturing_journal_setup["recipes"]
    recipe_id = manufacturing_journal_setup["recipe_id"]

    def boom(_entry):
        raise RuntimeError("fsync failed")

    monkeypatch.setattr("core.api.routes.manufacturing.append_mfg_journal", boom)

    resp = client.post(
        "/app/manufacturing/run",
        json={"recipe_id": recipe_id, "output_qty": 1},
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    with engine.SessionLocal() as db:
        run = db.query(recipes.ManufacturingRun).one()
        assert run.status == "completed"

        movements = db.query(models.ItemMovement).filter(
            models.ItemMovement.source_kind == "manufacturing",
            models.ItemMovement.source_id == run.id,
        )

        assert movements.count() == 2
        qty_total = sum(m.qty_change for m in movements)
        assert abs(qty_total - 0) < 1e-9
