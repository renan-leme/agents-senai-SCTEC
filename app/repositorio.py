"""Persistência local (JSON) dos pedidos cadastrados via POST /pedidos.

Os pedidos fictícios originais (`app.data.PEDIDOS`) nunca são gravados aqui nem
alterados: este repositório guarda SOMENTE os pedidos novos.

Pensado para uma única instância local (um processo). Não use com vários
workers: não há trava entre processos.
"""

import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable, Container
from pathlib import Path

from pydantic import ValidationError

from app.schemas import PedidoInterno

logger = logging.getLogger("api_pedidos")

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "dados" / "pedidos_criados.json"
VERSAO_ARQUIVO = 1


class CodigosEsgotados(Exception):
    """Todos os códigos PED-NNNN possíveis já estão em uso."""


def caminho_configurado() -> Path:
    """Arquivo definido em PEDIDOS_ARQUIVO (ou o padrão `dados/pedidos_criados.json`)."""
    valor = os.getenv("PEDIDOS_ARQUIVO", "").strip()
    return Path(valor).expanduser().resolve() if valor else ARQUIVO_PADRAO


class RepositorioPedidos:
    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._lock = threading.RLock()
        self._pedidos: dict[str, PedidoInterno] = {}
        self._carregar()

    # -- leitura -----------------------------------------------------------
    def get(self, codigo: str) -> PedidoInterno | None:
        with self._lock:
            return self._pedidos.get(codigo)

    def todos(self) -> dict[str, PedidoInterno]:
        with self._lock:
            return dict(self._pedidos)

    # -- escrita -----------------------------------------------------------
    def cadastrar(
        self,
        construir: Callable[[str], PedidoInterno],
        codigos_reservados: Container[str] = (),
    ) -> PedidoInterno:
        """Gera um código único, monta o pedido com `construir(codigo)` e grava em disco.

        Se a gravação falhar, o pedido não fica na memória (nada de "meio cadastrado").
        """
        with self._lock:
            codigo = self._proximo_codigo(codigos_reservados)
            pedido = construir(codigo)
            self._pedidos[codigo] = pedido
            try:
                self._salvar()
            except Exception:
                del self._pedidos[codigo]
                raise
            return pedido

    def salvar(self) -> None:
        """Regrava o arquivo (usado após registrar o resultado da notificação)."""
        with self._lock:
            self._salvar()

    # -- internos ----------------------------------------------------------
    def _proximo_codigo(self, reservados: Container[str]) -> str:
        # Faixa 4001–9999 primeiro (não colide com os pedidos fictícios 31xx), depois 1000–4000.
        for numero in (*range(4001, 10000), *range(1000, 4001)):
            codigo = f"PED-{numero:04d}"
            if codigo not in self._pedidos and codigo not in reservados:
                return codigo
        raise CodigosEsgotados

    def _carregar(self) -> None:
        if not self.caminho.exists():
            return
        try:
            bruto = json.loads(self.caminho.read_text(encoding="utf-8"))
            pedidos = [PedidoInterno.model_validate(p) for p in bruto["pedidos"]]
        except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
            # Não apaga nem sobrescreve o arquivo ruim: guarda uma cópia e recomeça vazio.
            copia = self.caminho.with_name(self.caminho.name + ".corrompido")
            logger.error("Arquivo de pedidos ilegível (%s); copiado para %s", type(exc).__name__, copia.name)
            try:
                os.replace(self.caminho, copia)
            except OSError:
                pass
            return
        self._pedidos = {p.codigo: p for p in pedidos}

    def _salvar(self) -> None:
        conteudo = {
            "versao": VERSAO_ARQUIVO,
            "pedidos": [p.model_dump(mode="json") for p in self._pedidos.values()],
        }
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: arquivo temporário + rename, para nunca deixar JSON pela metade.
        fd, tmp = tempfile.mkstemp(dir=self.caminho.parent, prefix=".pedidos_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(conteudo, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.caminho)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


# Instância compartilhada. É recriada se PEDIDOS_ARQUIVO mudar (útil nos testes).
_atual: RepositorioPedidos | None = None
_trava_global = threading.Lock()


def obter() -> RepositorioPedidos:
    global _atual
    caminho = caminho_configurado()
    with _trava_global:
        if _atual is None or _atual.caminho != caminho:
            _atual = RepositorioPedidos(caminho)
        return _atual


def reiniciar() -> None:
    """Descarta a memória; o próximo acesso relê o arquivo (simula reiniciar a API)."""
    global _atual
    with _trava_global:
        _atual = None
