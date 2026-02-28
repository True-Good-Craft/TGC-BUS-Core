# SPDX-License-Identifier: AGPL-3.0-or-later
from _httpx_stub import Client


def test_json_request_preserves_caller_content_type_header():
    client = Client(base_url="http://example.test")

    req = client.build_request(
        "POST",
        "/demo",
        json={"ok": True},
        headers={"Content-Type": "application/merge-patch+json"},
    )

    assert req.headers.get("content-type") == "application/merge-patch+json"
