# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations


def test_openapi_schema_returns_200_and_has_unique_operation_ids(bus_client):
    response = bus_client["client"].get("/openapi.json")

    assert response.status_code == 200, response.text
    schema = response.json()
    operation_ids: list[str] = []
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and operation.get("operationId"):
                operation_ids.append(str(operation["operationId"]))

    duplicates = sorted({operation_id for operation_id in operation_ids if operation_ids.count(operation_id) > 1})
    assert duplicates == []
