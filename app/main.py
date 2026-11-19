"""API REST de pedidos e entregas (consulta e cadastro fictício) — uso didático.

Execução local:  uvicorn app.main:app --host 127.0.0.1 --port 8000
Documentação:    http://127.0.0.1:8000/docs
"""

import asyncio
import logging
import os
from typing import Annotated

from fastapi import Depends, FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import service
from app.schemas import (
    CODIGO_REGEX,
    ErroResposta,
    EventosResposta,
    HealthResposta,
    PedidoCriado,
    PedidoCriar,
    PedidoDetalhe,
    PedidoListaResposta,
    ResumoEntrega,
    StatusPedido,
    TipoEntrega,
)
from app.service import ErroApi

logger = logging.getLogger("api_pedidos")

VERSAO = "1.1.0"
ATRASO_MAXIMO_SEGUNDOS = 60.0

app = FastAPI(
    title="API de Pedidos e Entregas (fictícia)",
    description=(
        "API com dados **fictícios**, criada para demonstrar integração de agentes de IA "
        "(LangChain/LangGraph e n8n) com APIs REST. Consulta pedidos (GET) e cadastra "
        "novos pedidos fictícios (POST /pedidos), com notificação opcional a um Webhook do n8n.\n\n"
        "⚠️ Não possui autenticação nem HTTPS: não exponha publicamente sem adicioná-los."
    ),
    version=VERSAO,
)

# Erros documentados no Swagger (todos usam o mesmo formato).
RESPOSTAS_ERRO = {
    404: {"model": ErroResposta, "description": "Pedido não encontrado."},
    422: {"model": ErroResposta, "description": "Parâmetro inválido."},
    503: {"model": ErroResposta, "description": "Serviço temporariamente indisponível."},
}


# ---------------------------------------------------------------------------
# Simulação de falhas (SOMENTE desenvolvimento) — desabilitada por padrão
# ---------------------------------------------------------------------------
def _ligado(nome: str) -> bool:
    return os.getenv(nome, "false").strip().lower() in {"1", "true", "yes", "sim"}


def _numero(valor: str | None) -> float:
    try:
        return min(max(float(valor), 0.0), ATRASO_MAXIMO_SEGUNDOS)
    except (TypeError, ValueError):
        return 0.0


async def simular_falhas_dev(request: Request) -> None:
    """Dependência dos endpoints /pedidos*.

    Só faz algo se API_SIMULACAO_DEV=true. Não é um endpoint: não há nenhuma
    rota administrativa e nada é alterado no servidor. Quando desligada, os
    cabeçalhos X-Dev-* enviados pelo cliente são simplesmente ignorados.
    """
    if not _ligado("API_SIMULACAO_DEV"):
        return

    atraso = max(
        _numero(os.getenv("API_ATRASO_SEGUNDOS")),
        _numero(request.headers.get("x-dev-atraso")),
    )
    if atraso > 0:
        await asyncio.sleep(atraso)  # não bloqueia o servidor para outras requisições

    if _ligado("API_FORCAR_503") or request.headers.get("x-dev-simular") == "503":
        raise ErroApi(503, "servico_indisponivel", "Serviço temporariamente indisponível. Tente novamente.")


# ---------------------------------------------------------------------------
# Tratamento padronizado de erros: sempre {"erro": ..., "mensagem": ...}
# ---------------------------------------------------------------------------
def _erro(status_code: int, erro: str, mensagem: str, detalhes: list[dict] | None = None) -> JSONResponse:
    corpo = {"erro": erro, "mensagem": mensagem}
    if detalhes:
        corpo["detalhes"] = detalhes
    return JSONResponse(status_code=status_code, content=corpo)


@app.exception_handler(ErroApi)
async def tratar_erro_api(_: Request, exc: ErroApi) -> JSONResponse:
    return _erro(exc.status_code, exc.erro, exc.mensagem)


MENSAGENS_CAMPO = {
    "codigo": "Código inválido. Use o formato PED-NNNN, com quatro dígitos (ex.: PED-3107).",
    "status": "Status inválido. Valores aceitos: " + ", ".join(s.value for s in StatusPedido) + ".",
    "atraso_registrado": "Valor inválido. Use true ou false.",
    "tipo_entrega": "Tipo de entrega inválido. Valores aceitos: " + ", ".join(t.value for t in TipoEntrega) + ".",
    "quantidade": "Quantidade inválida. Use um número inteiro entre 1 e 100.",
    "sku": "SKU inválido ou desconhecido. Use um SKU do catálogo fictício (ex.: SKU-101).",
    "produtos": "Informe de 1 a 20 produtos, cada um com sku e quantidade.",
    "transportadora": "Transportadora inválida (texto de até 60 caracteres).",
}


@app.exception_handler(RequestValidationError)
async def tratar_validacao(_: Request, exc: RequestValidationError) -> JSONResponse:
    detalhes = []
    for e in exc.errors():
        # Último elemento textual do caminho (ignora índices de lista).
        campo = next((str(p) for p in reversed(e["loc"]) if isinstance(p, str)), "body")
        if e["type"] == "json_invalid":
            msg = "O corpo da requisição não é um JSON válido."
        elif e["type"] == "extra_forbidden":
            msg = "Campo não permitido."
        elif e["type"] == "missing":
            msg = "Campo obrigatório ausente."
        else:
            msg = MENSAGENS_CAMPO.get(campo, "Valor inválido.")
        # O valor enviado pelo cliente (e["input"]) não é devolvido de propósito.
        detalhes.append({"campo": campo, "mensagem": msg})
    return _erro(422, "parametro_invalido", detalhes[0]["mensagem"], detalhes)


@app.exception_handler(StarletteHTTPException)
async def tratar_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _erro(404, "rota_nao_encontrada", "Rota não encontrada.")
    if exc.status_code == 405:
        return _erro(405, "metodo_nao_permitido", "Método não permitido para esta rota.")
    return _erro(exc.status_code, "erro_http", "Requisição não pôde ser atendida.")


@app.exception_handler(Exception)
async def tratar_erro_inesperado(_: Request, exc: Exception) -> JSONResponse:
    # Detalhes técnicos vão para o log do servidor, nunca para o cliente.
    logger.error("Erro inesperado: %s", type(exc).__name__, exc_info=exc)
    return _erro(500, "erro_interno", "Erro interno do servidor.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
CodigoPedido = Annotated[
    str,
    Path(
        pattern=CODIGO_REGEX,
        description="Código do pedido no formato PED-NNNN.",
        examples=["PED-3107"],
    ),
]


@app.get("/health", response_model=HealthResposta, tags=["Sistema"], summary="Estado da API")
def health() -> HealthResposta:
    return HealthResposta(status="ok", servico="api-pedidos-entregas", versao=VERSAO)


@app.get(
    "/pedidos",
    response_model=PedidoListaResposta,
    responses=RESPOSTAS_ERRO,
    dependencies=[Depends(simular_falhas_dev)],
    tags=["Pedidos"],
    summary="Lista pedidos (resumo)",
)
def listar_pedidos(
    status: Annotated[StatusPedido | None, Query(description="Filtra pelo status do pedido.")] = None,
    atraso_registrado: Annotated[
        bool | None, Query(description="Filtra pedidos com (true) ou sem (false) atraso registrado.")
    ] = None,
) -> PedidoListaResposta:
    return service.listar(status, atraso_registrado)


@app.post(
    "/pedidos",
    status_code=201,
    response_model=PedidoCriado,
    responses={k: v for k, v in RESPOSTAS_ERRO.items() if k != 404},
    dependencies=[Depends(simular_falhas_dev)],
    tags=["Pedidos"],
    summary="Cadastra um pedido fictício",
    description=(
        "Gera o código `PED-NNNN`, registra o evento inicial *Pedido criado* e define o status "
        "`em_preparacao`. Se `N8N_WEBHOOK_ENABLED=true`, envia o evento `pedido.criado` ao n8n; "
        "uma falha nessa notificação **não** cancela o pedido (veja o campo `notificacao`)."
    ),
)
def criar_pedido(dados: PedidoCriar, response: Response) -> PedidoCriado:
    pedido = service.cadastrar(dados)
    response.headers["Location"] = f"/pedidos/{pedido.codigo}"
    return pedido


@app.get(
    "/pedidos/{codigo}",
    response_model=PedidoDetalhe,
    responses=RESPOSTAS_ERRO,
    dependencies=[Depends(simular_falhas_dev)],
    tags=["Pedidos"],
    summary="Detalhes públicos de um pedido",
)
def obter_pedido(codigo: CodigoPedido) -> PedidoDetalhe:
    return service.detalhar(codigo)


@app.get(
    "/pedidos/{codigo}/eventos",
    response_model=EventosResposta,
    responses=RESPOSTAS_ERRO,
    dependencies=[Depends(simular_falhas_dev)],
    tags=["Pedidos"],
    summary="Histórico de movimentações (ordem cronológica)",
)
def obter_eventos(codigo: CodigoPedido) -> EventosResposta:
    return service.eventos(codigo)


@app.get(
    "/pedidos/{codigo}/resumo",
    response_model=ResumoEntrega,
    responses=RESPOSTAS_ERRO,
    dependencies=[Depends(simular_falhas_dev)],
    tags=["Pedidos"],
    summary="Resumo de entrega (ideal para agentes)",
    description="Somente os campos necessários para responder 'onde está meu pedido?'.",
)
def obter_resumo(codigo: CodigoPedido) -> ResumoEntrega:
    return service.resumir(codigo)
