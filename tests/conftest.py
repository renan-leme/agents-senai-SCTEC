"""Isolamento dos testes: nunca tocam o JSON real nem um n8n real."""

import pytest

from app import repositorio


@pytest.fixture(autouse=True)
def _ambiente_isolado(monkeypatch, tmp_path):
    monkeypatch.setenv("PEDIDOS_ARQUIVO", str(tmp_path / "pedidos_criados.json"))
    for nome in (
        "N8N_WEBHOOK_ENABLED",
        "N8N_WEBHOOK_URL",
        "N8N_WEBHOOK_TOKEN",
        "N8N_WEBHOOK_TIMEOUT_SEGUNDOS",
    ):
        monkeypatch.delenv(nome, raising=False)
    repositorio.reiniciar()
    yield
    repositorio.reiniciar()
