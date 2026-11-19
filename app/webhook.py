"""Notificação opcional (Webhook do n8n) após o cadastro de um pedido.

* Desabilitada por padrão (N8N_WEBHOOK_ENABLED=false).
* Uma única tentativa, com timeout curto. Sem retries.
* NUNCA levanta exceção: falha de notificação não pode desfazer o pedido.
* O token (N8N_WEBHOOK_TOKEN) só vai no cabeçalho X-Aula-Token; não é logado
  nem devolvido ao cliente, assim como a URL e os detalhes do erro.
"""

import logging
import os

import httpx

from app.schemas import NotificacaoN8n, PedidoInterno

logger = logging.getLogger("api_pedidos")

URL_PADRAO = "http://127.0.0.1:5678/webhook/novo-pedido"
TIMEOUT_PADRAO_SEGUNDOS = 3.0
TIMEOUT_MAXIMO_SEGUNDOS = 10.0
EVENTO_PEDIDO_CRIADO = "pedido.criado"


def _habilitado() -> bool:
    return os.getenv("N8N_WEBHOOK_ENABLED", "false").strip().lower() in {"1", "true", "yes", "sim"}


def _timeout() -> float:
    try:
        valor = float(os.getenv("N8N_WEBHOOK_TIMEOUT_SEGUNDOS", ""))
    except ValueError:
        return TIMEOUT_PADRAO_SEGUNDOS
    return min(max(valor, 0.5), TIMEOUT_MAXIMO_SEGUNDOS)


def montar_evento(pedido: PedidoInterno) -> dict:
    """Somente dados públicos e mínimos: nada de campos internos, produtos ou cliente."""
    return {
        "evento": EVENTO_PEDIDO_CRIADO,
        "pedido": {
            "codigo": pedido.codigo,
            "status": pedido.status.value,
            "tipo_entrega": pedido.tipo_entrega.value,
            "criado_em": pedido.criado_em.isoformat() if pedido.criado_em else None,
        },
    }


def notificar_pedido_criado(pedido: PedidoInterno) -> NotificacaoN8n:
    if not _habilitado():
        return NotificacaoN8n(status="desabilitada", mensagem="Notificação ao n8n desabilitada.")

    url = os.getenv("N8N_WEBHOOK_URL", "").strip() or URL_PADRAO
    token = os.getenv("N8N_WEBHOOK_TOKEN", "")
    cabecalhos = {"X-Aula-Token": token} if token else {}

    try:
        resposta = httpx.post(url, json=montar_evento(pedido), headers=cabecalhos, timeout=_timeout())
    except httpx.TimeoutException:
        logger.warning("Webhook n8n: timeout (pedido %s mantido).", pedido.codigo)
        return _falha()
    except Exception as exc:  # indisponível, URL inválida etc. — o pedido já está salvo
        logger.warning("Webhook n8n: falha %s (pedido %s mantido).", type(exc).__name__, pedido.codigo)
        return _falha()

    if not resposta.is_success:
        logger.warning("Webhook n8n: HTTP %s (pedido %s mantido).", resposta.status_code, pedido.codigo)
        return _falha()

    logger.info("Webhook n8n: evento %s enviado (pedido %s).", EVENTO_PEDIDO_CRIADO, pedido.codigo)
    return NotificacaoN8n(status="enviada", mensagem="Evento enviado ao n8n.")


def _falha() -> NotificacaoN8n:
    return NotificacaoN8n(
        status="falhou",
        mensagem="Não foi possível notificar o n8n. O pedido foi cadastrado normalmente.",
    )
