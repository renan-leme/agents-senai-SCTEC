"""Dados 100% fictícios (nenhuma pessoa, transportadora ou pedido real).

Cenário de referência: "hoje" é 18/11/2026. As datas são fixas para que os
exemplos e os testes sejam sempre reproduzíveis.

Os campos `nota_interna`, `cliente_id_interno` e `metadata_operacional` são
INTERNOS: existem aqui, mas nenhum modelo público os possui.
"""

from app.schemas import PedidoInterno


def ev(data_hora: str, descricao: str, local: str | None = None) -> dict:
    """Atalho para criar um evento. Formato: 'AAAA-MM-DD HH:MM'."""
    return {"data_hora": f"{data_hora}:00-03:00", "descricao": descricao, "local": local}


_PEDIDOS_BRUTOS: list[dict] = [
    # ---- Entregue no prazo ------------------------------------------------
    {
        "codigo": "PED-3107",
        "data_compra": "2026-11-02",
        "status": "entregue",
        "transportadora": "TransRápido Express",
        "previsao_entrega": "2026-11-09",
        "entregue_em": "2026-11-08",
        "atraso_registrado": False,
        "produtos": [{"nome": "Teclado mecânico compacto", "quantidade": 1}],
        "eventos": [
            ev("2026-11-02 09:15", "Pedido recebido", "Loja virtual"),
            ev("2026-11-02 09:40", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-03 14:00", "Pedido separado no estoque", "CD São Paulo/SP"),
            ev("2026-11-04 08:30", "Objeto postado na transportadora", "CD São Paulo/SP"),
            ev("2026-11-06 19:10", "Objeto em trânsito", "Campinas/SP"),
            ev("2026-11-08 10:25", "Objeto saiu para entrega ao destinatário", "Curitiba/PR"),
            ev("2026-11-08 15:42", "Objeto entregue ao destinatário", "Curitiba/PR"),
        ],
        "nota_interna": "Cliente pediu embalagem para presente (fictício).",
        "cliente_id_interno": "CLI-88120",
        "metadata_operacional": {"lote": "L-2211", "operador": "op-07", "peso_kg": 0.9},
    },
    # ---- Em transporte, dentro do prazo ------------------------------------
    {
        "codigo": "PED-3108",
        "data_compra": "2026-11-12",
        "status": "em_transporte",
        "transportadora": "TransRápido Express",
        "previsao_entrega": "2026-11-20",
        "entregue_em": None,
        "atraso_registrado": False,
        "produtos": [
            {"nome": "Mouse sem fio", "quantidade": 2},
            {"nome": "Mousepad grande", "quantidade": 1},
        ],
        "eventos": [
            ev("2026-11-12 18:05", "Pedido recebido", "Loja virtual"),
            ev("2026-11-12 18:20", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-13 11:00", "Pedido separado no estoque", "CD São Paulo/SP"),
            ev("2026-11-14 09:00", "Objeto postado na transportadora", "CD São Paulo/SP"),
            ev("2026-11-17 06:50", "Objeto em trânsito para a unidade de destino", "Belo Horizonte/MG"),
        ],
        "nota_interna": "Rota padrão, sem observações.",
        "cliente_id_interno": "CLI-45003",
        "metadata_operacional": {"lote": "L-2234", "operador": "op-02", "peso_kg": 1.4},
    },
    # ---- Em transporte, com atraso registrado ------------------------------
    {
        "codigo": "PED-3109",
        "data_compra": "2026-11-03",
        "status": "em_transporte",
        "transportadora": "LogiNorte",
        "previsao_entrega": "2026-11-12",
        "entregue_em": None,
        "atraso_registrado": True,
        "produtos": [{"nome": "Monitor 24 polegadas", "quantidade": 1}],
        "eventos": [
            ev("2026-11-03 10:00", "Pedido recebido", "Loja virtual"),
            ev("2026-11-03 10:12", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-04 15:30", "Pedido separado no estoque", "CD Recife/PE"),
            ev("2026-11-05 09:45", "Objeto postado na transportadora", "CD Recife/PE"),
            ev("2026-11-09 13:20", "Objeto em trânsito", "Salvador/BA"),
            ev("2026-11-12 08:00", "Atraso registrado: greve de caminhoneiros na rota", "Salvador/BA"),
            ev("2026-11-16 17:35", "Objeto em trânsito, rota retomada", "Feira de Santana/BA"),
        ],
        "nota_interna": "Avaliar reembolso do frete se passar de 20/11 (fictício).",
        "cliente_id_interno": "CLI-12977",
        "metadata_operacional": {"lote": "L-2190", "operador": "op-11", "peso_kg": 4.2},
    },
    # ---- Em preparação -----------------------------------------------------
    {
        "codigo": "PED-3110",
        "data_compra": "2026-11-17",
        "status": "em_preparacao",
        "transportadora": None,
        "previsao_entrega": "2026-11-26",
        "entregue_em": None,
        "atraso_registrado": False,
        "produtos": [{"nome": "Cadeira ergonômica", "quantidade": 1}],
        "eventos": [
            ev("2026-11-17 20:10", "Pedido recebido", "Loja virtual"),
            ev("2026-11-17 20:25", "Pagamento confirmado", "Loja virtual"),
        ],
        "nota_interna": "Aguardando reposição de estoque da cor preta.",
        "cliente_id_interno": "CLI-70311",
        "metadata_operacional": {"lote": None, "operador": "op-04", "peso_kg": 12.0},
    },
    # ---- Em separação ------------------------------------------------------
    {
        "codigo": "PED-3111",
        "data_compra": "2026-11-16",
        "status": "em_separacao",
        "transportadora": None,
        "previsao_entrega": "2026-11-25",
        "entregue_em": None,
        "atraso_registrado": False,
        "produtos": [
            {"nome": "Webcam Full HD", "quantidade": 1},
            {"nome": "Hub USB 4 portas", "quantidade": 1},
        ],
        "eventos": [
            ev("2026-11-16 13:00", "Pedido recebido", "Loja virtual"),
            ev("2026-11-16 13:08", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-18 08:15", "Pedido em separação no estoque", "CD São Paulo/SP"),
        ],
        "nota_interna": "Prioridade normal.",
        "cliente_id_interno": "CLI-33458",
        "metadata_operacional": {"lote": "L-2251", "operador": "op-09", "peso_kg": 0.7},
    },
    # ---- Enviado (postado, ainda sem movimentação) -------------------------
    {
        "codigo": "PED-3112",
        "data_compra": "2026-11-15",
        "status": "enviado",
        "transportadora": "LogiNorte",
        "previsao_entrega": "2026-11-23",
        "entregue_em": None,
        "atraso_registrado": False,
        "produtos": [{"nome": "Notebook 14 polegadas", "quantidade": 1}],
        "eventos": [
            ev("2026-11-15 11:30", "Pedido recebido", "Loja virtual"),
            ev("2026-11-15 11:42", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-16 10:00", "Pedido separado no estoque", "CD Recife/PE"),
            ev("2026-11-17 16:20", "Objeto postado na transportadora", "CD Recife/PE"),
        ],
        "nota_interna": "Seguro adicional contratado.",
        "cliente_id_interno": "CLI-90214",
        "metadata_operacional": {"lote": "L-2247", "operador": "op-11", "peso_kg": 2.1},
    },
    # ---- Cancelado ---------------------------------------------------------
    {
        "codigo": "PED-3113",
        "data_compra": "2026-11-10",
        "status": "cancelado",
        "transportadora": None,
        "previsao_entrega": None,
        "entregue_em": None,
        "atraso_registrado": False,
        "produtos": [{"nome": "Headset gamer", "quantidade": 1}],
        "eventos": [
            ev("2026-11-10 21:00", "Pedido recebido", "Loja virtual"),
            ev("2026-11-11 08:30", "Cancelamento solicitado pelo cliente", "Loja virtual"),
            ev("2026-11-11 09:10", "Pedido cancelado e pagamento estornado", "Loja virtual"),
        ],
        "nota_interna": "Estorno processado no mesmo dia.",
        "cliente_id_interno": "CLI-56790",
        "metadata_operacional": {"lote": None, "operador": "op-01", "peso_kg": 0.5},
    },
    # ---- Devolvido ---------------------------------------------------------
    {
        "codigo": "PED-3114",
        "data_compra": "2026-10-20",
        "status": "devolvido",
        "transportadora": "TransRápido Express",
        "previsao_entrega": "2026-10-28",
        "entregue_em": "2026-10-27",
        "atraso_registrado": False,
        "produtos": [{"nome": "Caixa de som bluetooth", "quantidade": 1}],
        "eventos": [
            ev("2026-10-20 15:00", "Pedido recebido", "Loja virtual"),
            ev("2026-10-20 15:10", "Pagamento confirmado", "Loja virtual"),
            ev("2026-10-21 10:00", "Pedido separado no estoque", "CD São Paulo/SP"),
            ev("2026-10-22 09:00", "Objeto postado na transportadora", "CD São Paulo/SP"),
            ev("2026-10-27 14:05", "Objeto entregue ao destinatário", "Porto Alegre/RS"),
            ev("2026-10-29 09:30", "Devolução solicitada pelo cliente (produto com defeito)", "Loja virtual"),
            ev("2026-11-03 11:15", "Objeto coletado para devolução", "Porto Alegre/RS"),
            ev("2026-11-10 16:40", "Devolução recebida no centro de distribuição", "CD São Paulo/SP"),
        ],
        "nota_interna": "Defeito confirmado pela assistência; abrir lote para o fornecedor.",
        "cliente_id_interno": "CLI-21045",
        "metadata_operacional": {"lote": "L-2102", "operador": "op-05", "peso_kg": 1.1},
    },
    # ---- Entregue COM atraso -----------------------------------------------
    {
        "codigo": "PED-3115",
        "data_compra": "2026-10-28",
        "status": "entregue",
        "transportadora": "LogiNorte",
        "previsao_entrega": "2026-11-05",
        "entregue_em": "2026-11-08",
        "atraso_registrado": True,
        "produtos": [
            {"nome": "Impressora multifuncional", "quantidade": 1},
            {"nome": "Cartucho de tinta preta", "quantidade": 2},
        ],
        "eventos": [
            ev("2026-10-28 09:00", "Pedido recebido", "Loja virtual"),
            ev("2026-10-28 09:14", "Pagamento confirmado", "Loja virtual"),
            ev("2026-10-29 13:00", "Pedido separado no estoque", "CD Recife/PE"),
            ev("2026-10-30 08:00", "Objeto postado na transportadora", "CD Recife/PE"),
            ev("2026-11-05 12:00", "Atraso registrado: extravio temporário na unidade de triagem", "Fortaleza/CE"),
            ev("2026-11-07 18:30", "Objeto localizado e reencaminhado", "Fortaleza/CE"),
            ev("2026-11-08 16:05", "Objeto entregue ao destinatário", "Natal/RN"),
        ],
        "nota_interna": "Cliente recebeu cupom de desconto pelo atraso.",
        "cliente_id_interno": "CLI-67432",
        "metadata_operacional": {"lote": "L-2150", "operador": "op-11", "peso_kg": 8.3},
    },
    # ---- Em transporte, atraso por tentativa de entrega frustrada ----------
    {
        "codigo": "PED-3116",
        "data_compra": "2026-11-05",
        "status": "em_transporte",
        "transportadora": "TransRápido Express",
        "previsao_entrega": "2026-11-16",
        "entregue_em": None,
        "atraso_registrado": True,
        "produtos": [{"nome": "Tablet 10 polegadas", "quantidade": 1}],
        "eventos": [
            ev("2026-11-05 16:45", "Pedido recebido", "Loja virtual"),
            ev("2026-11-05 16:58", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-06 14:00", "Pedido separado no estoque", "CD São Paulo/SP"),
            ev("2026-11-07 09:30", "Objeto postado na transportadora", "CD São Paulo/SP"),
            ev("2026-11-14 10:20", "Objeto saiu para entrega ao destinatário", "Goiânia/GO"),
            ev("2026-11-14 16:55", "Tentativa de entrega sem sucesso: destinatário ausente", "Goiânia/GO"),
            ev("2026-11-17 09:05", "Atraso registrado: nova tentativa de entrega agendada", "Goiânia/GO"),
        ],
        "nota_interna": "Duas tentativas restantes antes de devolver à origem.",
        "cliente_id_interno": "CLI-10586",
        "metadata_operacional": {"lote": "L-2203", "operador": "op-02", "peso_kg": 0.6},
    },
    # ---- Entregue no prazo (vários itens) ----------------------------------
    {
        "codigo": "PED-3117",
        "data_compra": "2026-11-06",
        "status": "entregue",
        "transportadora": "LogiNorte",
        "previsao_entrega": "2026-11-14",
        "entregue_em": "2026-11-13",
        "atraso_registrado": False,
        "produtos": [
            {"nome": "Cabo HDMI 2m", "quantidade": 3},
            {"nome": "Suporte para monitor", "quantidade": 1},
        ],
        "eventos": [
            ev("2026-11-06 12:00", "Pedido recebido", "Loja virtual"),
            ev("2026-11-06 12:09", "Pagamento confirmado", "Loja virtual"),
            ev("2026-11-07 10:30", "Pedido separado no estoque", "CD Recife/PE"),
            ev("2026-11-08 09:00", "Objeto postado na transportadora", "CD Recife/PE"),
            ev("2026-11-11 20:15", "Objeto em trânsito", "Maceió/AL"),
            ev("2026-11-13 11:50", "Objeto entregue ao destinatário", "Aracaju/SE"),
        ],
        "nota_interna": "Sem ocorrências.",
        "cliente_id_interno": "CLI-38871",
        "metadata_operacional": {"lote": "L-2178", "operador": "op-07", "peso_kg": 2.0},
    },
]

# Valida tudo na importação: dado incoerente derruba a aplicação já na subida.
PEDIDOS: dict[str, PedidoInterno] = {
    p.codigo: p for p in (PedidoInterno.model_validate(bruto) for bruto in _PEDIDOS_BRUTOS)
}
