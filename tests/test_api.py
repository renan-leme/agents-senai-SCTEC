"""Testes da API. Não usam LLM, internet nem serviços externos."""

import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import service
from app.data import PEDIDOS
from app.main import app
from app.schemas import (
    EventosResposta,
    PedidoDetalhe,
    PedidoInterno,
    PedidoListaResposta,
    ResumoEntrega,
    StatusPedido,
)

CAMPOS_INTERNOS = ["nota_interna", "cliente_id_interno", "metadata_operacional"]


@pytest.fixture(autouse=True)
def _sem_simulacao(monkeypatch):
    """Garante que o ambiente do desenvolvedor não interfira nos testes."""
    for nome in ("API_SIMULACAO_DEV", "API_FORCAR_503", "API_ATRASO_SEGUNDOS"):
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture
def client():
    return TestClient(app)


# 1. Pedido existente ---------------------------------------------------------
def test_consulta_pedido_existente(client):
    r = client.get("/pedidos/PED-3107")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["codigo"] == "PED-3107"
    assert corpo["status"] == "entregue"
    assert corpo["entregue_em"] == "2026-11-08"
    assert corpo["ultimo_evento"] == "Objeto entregue ao destinatário"
    assert corpo["produtos"][0]["nome"] == "Teclado mecânico compacto"


def test_resumo_tem_exatamente_os_campos_do_contrato(client):
    r = client.get("/pedidos/PED-3109/resumo")
    assert r.status_code == 200
    assert set(r.json()) == {
        "codigo",
        "status",
        "previsao_entrega",
        "entregue_em",
        "ultimo_evento",
        "data_ultimo_evento",
        "atraso_registrado",
    }
    assert r.json()["atraso_registrado"] is True


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# 2. Pedido inexistente -------------------------------------------------------
@pytest.mark.parametrize("sufixo", ["", "/eventos", "/resumo"])
def test_pedido_inexistente_retorna_404(client, sufixo):
    r = client.get(f"/pedidos/PED-9999{sufixo}")
    assert r.status_code == 404
    assert r.json() == {"erro": "pedido_nao_encontrado", "mensagem": "Pedido não localizado."}


# 3. Código inválido ----------------------------------------------------------
@pytest.mark.parametrize("codigo", ["PED-12", "PED-12345", "ped-3107", "XYZ-3107", "PED-31A7", "PED-３１０７"])
def test_codigo_invalido_retorna_422(client, codigo):
    r = client.get(f"/pedidos/{codigo}")
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["erro"] == "parametro_invalido"
    assert "PED-NNNN" in corpo["mensagem"]
    assert corpo["detalhes"][0]["campo"] == "codigo"
    assert codigo not in r.text  # o valor enviado não é devolvido


# 4. Filtro por status --------------------------------------------------------
def test_filtra_por_status(client):
    r = client.get("/pedidos", params={"status": "em_transporte"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == len(corpo["pedidos"]) == 3
    assert {p["status"] for p in corpo["pedidos"]} == {"em_transporte"}


def test_lista_sem_filtro_retorna_todos_ordenados(client):
    corpo = client.get("/pedidos").json()
    codigos = [p["codigo"] for p in corpo["pedidos"]]
    assert corpo["total"] == len(PEDIDOS) >= 10
    assert codigos == sorted(codigos)


def test_filtra_por_atraso_registrado(client):
    corpo = client.get("/pedidos", params={"atraso_registrado": "true"}).json()
    assert {p["codigo"] for p in corpo["pedidos"]} == {"PED-3109", "PED-3115", "PED-3116"}


def test_status_fora_do_contrato_retorna_422(client):
    r = client.get("/pedidos", params={"status": "voando"})
    assert r.status_code == 422
    assert r.json()["erro"] == "parametro_invalido"
    assert "em_transporte" in r.json()["mensagem"]


def test_filtro_valido_sem_resultados_retorna_lista_vazia(client, monkeypatch):
    monkeypatch.setattr(service, "PEDIDOS", {})
    assert client.get("/pedidos", params={"status": "entregue"}).json() == {"total": 0, "pedidos": []}


# 5. Histórico de eventos -----------------------------------------------------
def test_eventos_em_ordem_cronologica(client):
    r = client.get("/pedidos/PED-3115/eventos")
    assert r.status_code == 200
    corpo = r.json()
    datas = [e["data_hora"] for e in corpo["eventos"]]
    assert corpo["total"] == len(datas) == 7
    assert datas == sorted(datas)
    assert "entregue" in corpo["eventos"][-1]["descricao"]


def test_eventos_sao_ordenados_mesmo_com_dados_desordenados(client, monkeypatch):
    original = PEDIDOS["PED-3107"]
    desordenado = original.model_copy(update={"eventos": list(reversed(original.eventos))})
    monkeypatch.setitem(PEDIDOS, "PED-3107", desordenado)
    datas = [e["data_hora"] for e in client.get("/pedidos/PED-3107/eventos").json()["eventos"]]
    assert datas == sorted(datas)


# 6. Validação de resposta ----------------------------------------------------
def test_respostas_obedecem_aos_modelos_pydantic(client):
    PedidoListaResposta.model_validate(client.get("/pedidos").json())
    for codigo in PEDIDOS:
        PedidoDetalhe.model_validate(client.get(f"/pedidos/{codigo}").json())
        EventosResposta.model_validate(client.get(f"/pedidos/{codigo}/eventos").json())
        ResumoEntrega.model_validate(client.get(f"/pedidos/{codigo}/resumo").json())


def test_modelo_de_resposta_rejeita_dados_incompletos_ou_invalidos():
    with pytest.raises(ValidationError):
        ResumoEntrega.model_validate({"codigo": "PED-3107"})
    with pytest.raises(ValidationError):
        ResumoEntrega.model_validate(
            {
                "codigo": "PED-3107",
                "status": "status_inventado",
                "previsao_entrega": None,
                "entregue_em": None,
                "ultimo_evento": "x",
                "data_ultimo_evento": "não é data",
                "atraso_registrado": False,
            }
        )


def test_resposta_invalida_do_servico_vira_500_generico(monkeypatch):
    """Se o código gerar um dado fora do contrato, a API não o entrega ao cliente."""
    monkeypatch.setattr(service, "resumir", lambda codigo: {"codigo": codigo, "status": "inventado"})
    r = TestClient(app, raise_server_exceptions=False).get("/pedidos/PED-3107/resumo")
    assert r.status_code == 500
    assert r.json() == {"erro": "erro_interno", "mensagem": "Erro interno do servidor."}
    assert "inventado" not in r.text and "Traceback" not in r.text


# 7. Ausência de campos internos ---------------------------------------------
def test_campos_internos_nunca_aparecem(client):
    caminhos = ["/pedidos"]
    for codigo in PEDIDOS:
        caminhos += [f"/pedidos/{codigo}", f"/pedidos/{codigo}/eventos", f"/pedidos/{codigo}/resumo"]

    valores_internos = []
    for p in PEDIDOS.values():
        valores_internos += [p.nota_interna, p.cliente_id_interno]

    for caminho in caminhos:
        texto = client.get(caminho).text
        for campo in CAMPOS_INTERNOS:
            assert campo not in texto, f"{campo} vazou em {caminho}"
        for valor in valores_internos:
            assert valor not in texto, f"valor interno vazou em {caminho}"


def test_openapi_nao_declara_campos_internos(client):
    texto = client.get("/openapi.json").text
    for campo in CAMPOS_INTERNOS:
        assert campo not in texto


# 8. Simulação de indisponibilidade ------------------------------------------
def test_simulacao_desabilitada_por_padrao_ignora_cabecalhos(client):
    r = client.get("/pedidos/PED-3107/resumo", headers={"X-Dev-Simular": "503", "X-Dev-Atraso": "5"})
    assert r.status_code == 200


def test_simulacao_503_por_cabecalho(client, monkeypatch):
    monkeypatch.setenv("API_SIMULACAO_DEV", "true")
    r = client.get("/pedidos/PED-3107/resumo", headers={"X-Dev-Simular": "503"})
    assert r.status_code == 503
    assert r.json()["erro"] == "servico_indisponivel"
    # sem o cabeçalho, continua funcionando
    assert client.get("/pedidos/PED-3107/resumo").status_code == 200


def test_simulacao_503_por_variavel_de_ambiente(client, monkeypatch):
    monkeypatch.setenv("API_SIMULACAO_DEV", "true")
    monkeypatch.setenv("API_FORCAR_503", "true")
    assert client.get("/pedidos").status_code == 503
    assert client.get("/health").status_code == 200  # health nunca é afetado


def test_forcar_503_sem_chave_geral_nao_tem_efeito(client, monkeypatch):
    monkeypatch.setenv("API_FORCAR_503", "true")
    assert client.get("/pedidos").status_code == 200


def test_simulacao_de_atraso(client, monkeypatch):
    monkeypatch.setenv("API_SIMULACAO_DEV", "true")
    inicio = time.perf_counter()
    r = client.get("/pedidos/PED-3107/resumo", headers={"X-Dev-Atraso": "0.3"})
    assert r.status_code == 200
    assert time.perf_counter() - inicio >= 0.3


# Segurança / robustez --------------------------------------------------------
@pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
def test_escrita_nao_permitida_em_pedido_existente(client, metodo):
    r = getattr(client, metodo)("/pedidos/PED-3107")
    assert r.status_code == 405
    assert r.json()["erro"] == "metodo_nao_permitido"


def test_rota_inexistente_usa_formato_padrao_de_erro(client):
    r = client.get("/nao-existe")
    assert r.status_code == 404
    assert r.json()["erro"] == "rota_nao_encontrada"


# Consistência dos dados fictícios --------------------------------------------
def test_dados_cobrem_todos_os_cenarios_pedidos():
    assert len(PEDIDOS) >= 10
    assert {p.status for p in PEDIDOS.values()} == set(StatusPedido)
    assert any(p.atraso_registrado for p in PEDIDOS.values())


@pytest.mark.parametrize("pedido", PEDIDOS.values(), ids=lambda p: p.codigo)
def test_dados_sao_coerentes(pedido):
    eventos = sorted(pedido.eventos, key=lambda e: e.data_hora)
    ultimo = eventos[-1]

    assert all(e.data_hora.date() >= pedido.data_compra for e in eventos)
    if pedido.status == StatusPedido.ENTREGUE:
        assert pedido.entregue_em is not None
        assert "entregue ao destinatário" in ultimo.descricao
        assert ultimo.data_hora.date() == pedido.entregue_em
    if pedido.status == StatusPedido.CANCELADO:
        assert "cancelado" in ultimo.descricao.lower()
        assert pedido.entregue_em is None
    if pedido.status == StatusPedido.DEVOLVIDO:
        assert any(e.data_hora.date() == pedido.entregue_em for e in eventos)
        assert "evolução" in ultimo.descricao
    if pedido.entregue_em and pedido.previsao_entrega and pedido.status == StatusPedido.ENTREGUE:
        assert pedido.atraso_registrado == (pedido.entregue_em > pedido.previsao_entrega)
    if pedido.status in (StatusPedido.EM_TRANSPORTE, StatusPedido.ENVIADO):
        assert pedido.transportadora is not None
        assert any("postado" in e.descricao for e in eventos)


def test_modelo_interno_rejeita_dado_incoerente():
    base = PEDIDOS["PED-3107"].model_dump()
    with pytest.raises(ValidationError):
        PedidoInterno.model_validate({**base, "entregue_em": None})  # entregue sem data de entrega
    with pytest.raises(ValidationError):
        PedidoInterno.model_validate({**base, "campo_inventado": 1})
