"""Contratos Pydantic da API.

Há dois grupos de modelos:

* `PedidoInterno` (+ `Produto`, `EventoLogistico`): representa o dado como ele
  existe "no sistema", inclusive campos internos. NUNCA é usado como resposta.
* Modelos públicos (`PedidoDetalhe`, `ResumoEntrega`, ...): são os únicos
  usados em `response_model`. Não possuem campos internos, então eles não
  conseguem vazar nem por acidente.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalogo import CATALOGO

CODIGO_REGEX = r"^PED-[0-9]{4}$"  # [0-9] (e não \d) para aceitar só dígitos ASCII


class StatusPedido(StrEnum):
    EM_PREPARACAO = "em_preparacao"
    EM_SEPARACAO = "em_separacao"
    ENVIADO = "enviado"
    EM_TRANSPORTE = "em_transporte"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"
    DEVOLVIDO = "devolvido"


class TipoEntrega(StrEnum):
    NORMAL = "normal"
    EXPRESSA = "expressa"


# --------------------------------------------------------------------------
# Blocos reutilizados (públicos)
# --------------------------------------------------------------------------
class Produto(BaseModel):
    nome: str
    quantidade: int = Field(ge=1)
    sku: str | None = Field(default=None, description="Preenchido nos pedidos cadastrados via POST /pedidos.")


class EventoLogistico(BaseModel):
    data_hora: datetime = Field(description="Data/hora do evento (fuso de Brasília, -03:00).")
    descricao: str
    local: str | None = None


# --------------------------------------------------------------------------
# Modelo INTERNO (nunca retornado diretamente)
# --------------------------------------------------------------------------
class PedidoInterno(BaseModel):
    model_config = ConfigDict(extra="forbid")  # pega erros de digitação nos dados

    codigo: str = Field(pattern=CODIGO_REGEX)
    data_compra: date
    status: StatusPedido
    transportadora: str | None = None
    previsao_entrega: date | None = None
    entregue_em: date | None = None
    atraso_registrado: bool = False
    produtos: list[Produto]
    eventos: list[EventoLogistico] = Field(min_length=1)
    # Pedidos fictícios originais não têm estes dois campos: assumem os padrões abaixo.
    tipo_entrega: TipoEntrega = TipoEntrega.NORMAL
    criado_em: datetime | None = None

    # Campos exclusivamente internos
    nota_interna: str
    cliente_id_interno: str
    metadata_operacional: dict[str, Any]

    @model_validator(mode="after")
    def _checar_coerencia(self) -> "PedidoInterno":
        if self.status == StatusPedido.ENTREGUE and self.entregue_em is None:
            raise ValueError(f"{self.codigo}: pedido entregue exige entregue_em")
        if self.entregue_em is not None and self.status not in (
            StatusPedido.ENTREGUE,
            StatusPedido.DEVOLVIDO,
        ):
            raise ValueError(f"{self.codigo}: entregue_em só faz sentido para entregue/devolvido")
        return self


# --------------------------------------------------------------------------
# Modelos PÚBLICOS (usados em response_model)
# --------------------------------------------------------------------------
class PedidoItemLista(BaseModel):
    codigo: str
    status: StatusPedido
    tipo_entrega: TipoEntrega
    data_compra: date
    transportadora: str | None
    previsao_entrega: date | None
    atraso_registrado: bool


class PedidoListaResposta(BaseModel):
    total: int
    pedidos: list[PedidoItemLista]


class PedidoDetalhe(BaseModel):
    codigo: str
    status: StatusPedido
    tipo_entrega: TipoEntrega
    data_compra: date
    transportadora: str | None
    previsao_entrega: date | None
    entregue_em: date | None
    atraso_registrado: bool
    ultimo_evento: str
    data_ultimo_evento: datetime
    produtos: list[Produto]


class EventosResposta(BaseModel):
    codigo: str
    total: int
    eventos: list[EventoLogistico] = Field(description="Ordem cronológica (mais antigo primeiro).")


class ResumoEntrega(BaseModel):
    """Contrato enxuto pensado para um agente responder 'onde está meu pedido?'."""

    codigo: str
    status: StatusPedido
    previsao_entrega: date | None
    entregue_em: date | None
    ultimo_evento: str
    data_ultimo_evento: datetime
    atraso_registrado: bool


class HealthResposta(BaseModel):
    status: str
    servico: str
    versao: str


class DetalheErro(BaseModel):
    campo: str
    mensagem: str


class ErroResposta(BaseModel):
    """Formato único de erro de toda a API."""

    erro: str = Field(examples=["pedido_nao_encontrado"])
    mensagem: str = Field(examples=["Pedido não localizado."])
    detalhes: list[DetalheErro] | None = None


# --------------------------------------------------------------------------
# Cadastro de pedidos (POST /pedidos)
# --------------------------------------------------------------------------
class ItemPedidoCriar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(description="SKU do catálogo fictício (ex.: SKU-101).", examples=["SKU-101"])
    quantidade: int = Field(strict=True, ge=1, le=100, description="Inteiro entre 1 e 100.")

    @field_validator("sku")
    @classmethod
    def _sku_do_catalogo(cls, valor: str) -> str:
        valor = valor.strip().upper()
        if valor not in CATALOGO:
            raise ValueError("SKU desconhecido")
        return valor


class PedidoCriar(BaseModel):
    """Corpo do POST /pedidos. Campos desconhecidos são rejeitados (422)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tipo_entrega": "expressa",
                    "transportadora": "Entrega Express",
                    "produtos": [{"sku": "SKU-101", "quantidade": 2}],
                }
            ]
        },
    )

    tipo_entrega: TipoEntrega = Field(default=TipoEntrega.NORMAL, description="`normal` ou `expressa`.")
    transportadora: str | None = Field(default=None, max_length=60)
    produtos: list[ItemPedidoCriar] = Field(min_length=1, max_length=20)

    @field_validator("transportadora")
    @classmethod
    def _limpar_transportadora(cls, valor: str | None) -> str | None:
        return (valor or "").strip() or None


class NotificacaoN8n(BaseModel):
    status: Literal["enviada", "falhou", "desabilitada"]
    mensagem: str


class PedidoCriado(BaseModel):
    """Dados públicos devolvidos pelo POST /pedidos (HTTP 201)."""

    codigo: str
    status: StatusPedido
    tipo_entrega: TipoEntrega
    transportadora: str | None
    criado_em: datetime
    previsao_entrega: date
    produtos: list[Produto]
    notificacao: NotificacaoN8n
