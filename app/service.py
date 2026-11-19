"""Lógica de consulta e de cadastro de pedidos.

As consultas leem os pedidos fictícios originais (`PEDIDOS`, nunca alterados)
mais os pedidos cadastrados via POST (persistidos em JSON, ver `repositorio`).
"""

import logging
from datetime import datetime, timedelta, timezone

from app import repositorio, webhook
from app.catalogo import CATALOGO
from app.data import PEDIDOS
from app.schemas import (
    EventoLogistico,
    EventosResposta,
    PedidoCriado,
    PedidoCriar,
    PedidoDetalhe,
    PedidoInterno,
    PedidoItemLista,
    PedidoListaResposta,
    Produto,
    ResumoEntrega,
    StatusPedido,
    TipoEntrega,
)

logger = logging.getLogger("api_pedidos")

FUSO_BRASILIA = timezone(timedelta(hours=-3))  # mesmo fuso (-03:00) dos dados fictícios
PRAZO_ENTREGA_DIAS = {TipoEntrega.NORMAL: 7, TipoEntrega.EXPRESSA: 3}  # previsão fictícia


class ErroApi(Exception):
    """Erro "esperado", convertido em JSON padronizado pelo handler em main.py."""

    def __init__(self, status_code: int, erro: str, mensagem: str):
        self.status_code = status_code
        self.erro = erro
        self.mensagem = mensagem
        super().__init__(mensagem)


def agora() -> datetime:
    return datetime.now(FUSO_BRASILIA)


def _todos() -> dict[str, PedidoInterno]:
    """Pedidos originais + cadastrados. Os originais têm prioridade e nunca são sobrescritos."""
    return {**repositorio.obter().todos(), **PEDIDOS}


def _buscar(codigo: str) -> PedidoInterno:
    pedido = PEDIDOS.get(codigo) or repositorio.obter().get(codigo)
    if pedido is None:
        raise ErroApi(404, "pedido_nao_encontrado", "Pedido não localizado.")
    return pedido


def _eventos_ordenados(pedido: PedidoInterno) -> list[EventoLogistico]:
    return sorted(pedido.eventos, key=lambda e: e.data_hora)


def listar(status: StatusPedido | None = None, atraso_registrado: bool | None = None) -> PedidoListaResposta:
    pedidos = sorted(_todos().values(), key=lambda p: p.codigo)
    if status is not None:
        pedidos = [p for p in pedidos if p.status == status]
    if atraso_registrado is not None:
        pedidos = [p for p in pedidos if p.atraso_registrado == atraso_registrado]
    itens = [PedidoItemLista.model_validate(p, from_attributes=True) for p in pedidos]
    return PedidoListaResposta(total=len(itens), pedidos=itens)


def detalhar(codigo: str) -> PedidoDetalhe:
    pedido = _buscar(codigo)
    ultimo = _eventos_ordenados(pedido)[-1]
    return PedidoDetalhe(
        codigo=pedido.codigo,
        status=pedido.status,
        tipo_entrega=pedido.tipo_entrega,
        data_compra=pedido.data_compra,
        transportadora=pedido.transportadora,
        previsao_entrega=pedido.previsao_entrega,
        entregue_em=pedido.entregue_em,
        atraso_registrado=pedido.atraso_registrado,
        produtos=pedido.produtos,
        ultimo_evento=ultimo.descricao,
        data_ultimo_evento=ultimo.data_hora,
    )


def eventos(codigo: str) -> EventosResposta:
    pedido = _buscar(codigo)
    lista = _eventos_ordenados(pedido)
    return EventosResposta(codigo=pedido.codigo, total=len(lista), eventos=lista)


def resumir(codigo: str) -> ResumoEntrega:
    pedido = _buscar(codigo)
    ultimo = _eventos_ordenados(pedido)[-1]
    return ResumoEntrega(
        codigo=pedido.codigo,
        status=pedido.status,
        previsao_entrega=pedido.previsao_entrega,
        entregue_em=pedido.entregue_em,
        ultimo_evento=ultimo.descricao,
        data_ultimo_evento=ultimo.data_hora,
        atraso_registrado=pedido.atraso_registrado,
    )


def cadastrar(dados: PedidoCriar) -> PedidoCriado:
    """Cria o pedido, grava em disco e tenta (uma vez) notificar o n8n.

    A falha da notificação nunca desfaz o cadastro.
    """
    momento = agora()

    def construir(codigo: str) -> PedidoInterno:
        return PedidoInterno(
            codigo=codigo,
            data_compra=momento.date(),
            status=StatusPedido.EM_PREPARACAO,
            transportadora=dados.transportadora,
            previsao_entrega=momento.date() + timedelta(days=PRAZO_ENTREGA_DIAS[dados.tipo_entrega]),
            produtos=[
                Produto(nome=CATALOGO[i.sku], quantidade=i.quantidade, sku=i.sku) for i in dados.produtos
            ],
            eventos=[EventoLogistico(data_hora=momento, descricao="Pedido criado", local="Loja virtual")],
            tipo_entrega=dados.tipo_entrega,
            criado_em=momento,
            nota_interna="Pedido fictício cadastrado via POST /pedidos.",
            cliente_id_interno="CLI-DEMO",
            metadata_operacional={"origem": "post_pedidos"},
        )

    repo = repositorio.obter()
    try:
        pedido = repo.cadastrar(construir, codigos_reservados=PEDIDOS)
    except repositorio.CodigosEsgotados:
        raise ErroApi(503, "capacidade_esgotada", "Não há códigos de pedido disponíveis.") from None

    notificacao = webhook.notificar_pedido_criado(pedido)

    # Registra o resultado da tentativa (campo interno, não exposto pela API).
    pedido.metadata_operacional["notificacao_n8n"] = {"status": notificacao.status, "em": agora().isoformat()}
    try:
        repo.salvar()
    except OSError as exc:
        logger.error("Pedido %s salvo, mas o resultado da notificação não: %s", pedido.codigo, type(exc).__name__)

    return PedidoCriado(
        codigo=pedido.codigo,
        status=pedido.status,
        tipo_entrega=pedido.tipo_entrega,
        transportadora=pedido.transportadora,
        criado_em=momento,
        previsao_entrega=pedido.previsao_entrega,
        produtos=pedido.produtos,
        notificacao=notificacao,
    )
