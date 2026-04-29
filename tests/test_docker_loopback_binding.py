# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE = REPO_ROOT / "docker-compose.yml"


def _published_ports(path: Path) -> list[str]:
    values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.split("#", 1)[0].strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip().strip('"').strip("'")
        if ":" in value:
            values.append(value)
    return values


def test_default_docker_compose_binds_bus_core_port_to_loopback() -> None:
    ports = _published_ports(DEFAULT_COMPOSE)

    assert "127.0.0.1:8765:8765" in ports
    assert "8765:8765" not in ports, (
        "docker-compose.yml must not publish BUS Core as a bare host port. "
        "Default Docker exposure must stay loopback-only because /session/token "
        "is designed for local bootstrap, not LAN/public hosting."
    )


def test_bare_bus_core_port_publish_only_allowed_in_documented_lan_override() -> None:
    for compose_file in REPO_ROOT.glob("docker-compose*.yml"):
        if compose_file.name == DEFAULT_COMPOSE.name:
            continue
        ports = _published_ports(compose_file)
        if "8765:8765" not in ports:
            continue

        lower_name = compose_file.name.lower()
        lower_text = compose_file.read_text(encoding="utf-8").lower()
        assert "lan" in lower_name, (
            f"{compose_file.name} publishes BUS Core beyond loopback but is not a clearly named LAN override."
        )
        assert "unsafe" in lower_text and "advanced" in lower_text, (
            f"{compose_file.name} must document LAN/non-loopback exposure as unsafe/advanced."
        )
