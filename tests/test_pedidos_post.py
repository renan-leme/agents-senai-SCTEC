"""Testes do cadastro de pedidos (POST /pedidos) e da integração com o Webhook do n8n.

Nenhum teste usa um n8n real: as chamadas HTTP ao Webhook são simuladas.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app import repositorio, service
from app.data import PEDIDOS
from app.main import app

CAMPOS_INTERNOS = ["nota_interna", "cliente_id_interno", "metadata_operacional"]
VALORES_INTERNOS = ["CLI-DEMO", "Pedido fictício cadastrado via POST", "post_pedidos", "notificacao_n8n"]
TOKEN = "token-secreto-da-aula"
URL_N8N = "http://127.0.0.1:5678/webhook/novo-pedido"

CORPO = {
    "tipo_entrega": "expressa",
    "transportadora": "Entrega Express",
    "produtos": [{"sku": "SKU-101", "quantidade": 2}],
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def n8n_ligado(monkeypatch):
    monkeypatch.setenv("N8N_WEBHOOK_ENABLED", "true")
    monkeypatch.setenv("N8N_WEBHOOK_URL", URL_N8N)
    monkeypatch.setenv("N8N_WEBHOOK_TOKEN", TOKEN)


class FalsoPost:
    """Substitui httpx.post, registrando as chamadas."""

    def __init__(self, resultado):
        self.resultado = resultado  # Response ou exceção a levantar
        self.chamadas = []

    def __call__(self, url, **kwargs):
        self.chamadas.append({"url": url, **kwargs})
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


def _falso_post(monkeypatch, resultado):
    falso = FalsoPost(resultado)
    monkeypatch.setattr(httpx, "post", falso)
    return falso


# 1. Cadastro bem-sucedido ------------------------------------------------------
def test_cadastro_retorna_201_com_dados_publicos(client):
    r = client.post("/pedidos", json=CORPO)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["codigo"].startswith("PED-") and len(corpo["codigo"]) == 8
    assert r.headers["location"] == f"/pedidos/{corpo['codigo']}"
    assert corpo["status"] == "em_preparacao"
    assert corpo["tipo_entrega"] == "expressa"
    assert corpo["transportadora"] == "Entrega Express"
    assert corpo["produtos"] == [{"nome": "Teclado mecânico compacto", "quantidade": 2, "sku": "SKU-101"}]
    assert datetime.fromisoformat(corpo["criado_em"]).utcoffset() == timedelta(hours=-3)
    assert corpo["notificacao"]["status"] == "desabilitada"  # padrão: integração desligada


def test_tipo_entrega_padrao_e_normal_e_transportadora_opcional(client):
    r = client.post("/pedidos", json={"produtos": [{"sku": "SKU-102", "quantidade": 1}]})
    assert r.status_code == 201
    assert r.json()["tipo_entrega"] == "normal"
    assert r.json()["transportadora"] is None


def test_previsao_depende_do_tipo_de_entrega(client, monkeypatch):
    fixo = datetime(2026, 11, 19, 19, 30, tzinfo=timezone(timedelta(hours=-3)))
    monkeypatch.setattr(service, "agora", lambda: fixo)
    normal = client.post("/pedidos", json={**CORPO, "tipo_entrega": "normal"}).json()
    expressa = client.post("/pedidos", json={**CORPO, "tipo_entrega": "expressa"}).json()
    assert normal["previsao_entrega"] == "2026-11-26"
    assert expressa["previsao_entrega"] == "2026-11-22"
    assert normal["criado_em"] == "2026-11-19T19:30:00-03:00"


# 2. Códigos únicos --------------------------------------------------------------
def test_codigos_sao_unicos_e_nao_colidem_com_os_ficticios(client):
    codigos = [client.post("/pedidos", json=CORPO).json()["codigo"] for _ in range(25)]
    assert len(set(codigos)) == 25
    assert not set(codigos) & set(PEDIDOS)


# 3. Dados inválidos -------------------------------------------------------------
@pytest.mark.parametrize(
    "corpo, campo",
    [
        ({**CORPO, "tipo_entrega": "voador"}, "tipo_entrega"),
        ({**CORPO, "produtos": [{"sku": "SKU-101", "quantidade": 0}]}, "quantidade"),
        ({**CORPO, "produtos": [{"sku": "SKU-101", "quantidade": -3}]}, "quantidade"),
        ({**CORPO, "produtos": [{"sku": "SKU-101", "quantidade": "2"}]}, "quantidade"),
        ({**CORPO, "produtos": [{"sku": "SKU-101", "quantidade": 1.5}]}, "quantidade"),
        ({**CORPO, "produtos": [{"sku": "SKU-101", "quantidade": 101}]}, "quantidade"),
        ({**CORPO, "produtos": [{"sku": "SKU-999", "quantidade": 1}]}, "sku"),
        ({**CORPO, "produtos": []}, "produtos"),
        ({"tipo_entrega": "normal"}, "produtos"),
        ({**CORPO, "produtos": [{"sku": "SKU-101"}]}, "quantidade"),
        ({**CORPO, "transportadora": "x" * 61}, "transportadora"),
        # campos internos / desconhecidos não são aceitos (sem "mass assignment")
        ({**CORPO, "status": "entregue"}, "status"),
        ({**CORPO, "nota_interna": "x"}, "nota_interna"),
    ],
)
def test_dados_invalidos_retornam_422(client, corpo, campo):
    r = client.post("/pedidos", json=corpo)
    assert r.status_code == 422
    assert r.json()["erro"] == "parametro_invalido"
    assert r.json()["detalhes"][0]["campo"] == campo
    assert client.get("/pedidos").json()["total"] == len(PEDIDOS)  # nada foi cadastrado


def test_json_malformado_e_corpo_ausente_retornam_422(client):
    r = client.post("/pedidos", content="{não é json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["erro"] == "parametro_invalido"
    assert client.post("/pedidos").status_code == 422


def test_422_nao_devolve_o_valor_enviado(client):
    r = client.post("/pedidos", json={**CORPO, "tipo_entrega": "valor-malicioso-123"})
    assert "valor-malicioso-123" not in r.text


# 4 e 5. Consultas ao pedido recém-criado e histórico ------------------------------
def test_pedido_criado_aparece_nos_endpoints_get(client):
    criado = client.post("/pedidos", json=CORPO).json()
    codigo = criado["codigo"]

    detalhe = client.get(f"/pedidos/{codigo}")
    assert detalhe.status_code == 200
    assert detalhe.json()["status"] == "em_preparacao"
    assert detalhe.json()["tipo_entrega"] == "expressa"
    assert detalhe.json()["ultimo_evento"] == "Pedido criado"
    assert detalhe.json()["previsao_entrega"] == criado["previsao_entrega"]

    resumo = client.get(f"/pedidos/{codigo}/resumo")
    assert resumo.status_code == 200
    assert resumo.json()["codigo"] == codigo
    assert resumo.json()["atraso_registrado"] is False

    lista = client.get("/pedidos").json()
    assert lista["total"] == len(PEDIDOS) + 1
    assert codigo in [p["codigo"] for p in lista["pedidos"]]
    assert [p["codigo"] for p in lista["pedidos"]] == sorted(p["codigo"] for p in lista["pedidos"])
    assert codigo in [p["codigo"] for p in client.get("/pedidos", params={"status": "em_preparacao"}).json()["pedidos"]]


def test_historico_contem_o_evento_de_criacao(client):
    codigo = client.post("/pedidos", json=CORPO).json()["codigo"]
    corpo = client.get(f"/pedidos/{codigo}/eventos").json()
    assert corpo["total"] == 1
    assert corpo["eventos"][0]["descricao"] == "Pedido criado"
    assert datetime.fromisoformat(corpo["eventos"][0]["data_hora"]).utcoffset() == timedelta(hours=-3)


def test_pedidos_antigos_ganham_tipo_entrega_normal_e_continuam_iguais(client):
    antigo = client.get("/pedidos/PED-3107").json()
    assert antigo["tipo_entrega"] == "normal"
    assert antigo["status"] == "entregue"
    assert {p["tipo_entrega"] for p in client.get("/pedidos").json()["pedidos"]} == {"normal"}


def test_pedidos_originais_nao_sao_alterados(client):
    antes = {c: p.model_dump() for c, p in PEDIDOS.items()}
    client.post("/pedidos", json=CORPO)
    assert {c: p.model_dump() for c, p in PEDIDOS.items()} == antes


# 6. Persistência -----------------------------------------------------------------
def test_pedido_persiste_apos_recarregar_os_dados(client):
    codigo = client.post("/pedidos", json=CORPO).json()["codigo"]
    antes = client.get(f"/pedidos/{codigo}").json()

    repositorio.reiniciar()  # equivale a reiniciar a API: memória descartada, arquivo relido

    depois = client.get(f"/pedidos/{codigo}")
    assert depois.status_code == 200
    assert depois.json() == antes
    assert client.get(f"/pedidos/{codigo}/eventos").json()["eventos"][0]["descricao"] == "Pedido criado"
    # e o próximo código não repete o anterior
    assert client.post("/pedidos", json=CORPO).json()["codigo"] != codigo


def test_arquivo_json_contem_somente_pedidos_criados(client, tmp_path):
    codigo = client.post("/pedidos", json=CORPO).json()["codigo"]
    gravado = json.loads((tmp_path / "pedidos_criados.json").read_text(encoding="utf-8"))
    assert [p["codigo"] for p in gravado["pedidos"]] == [codigo]


def test_arquivo_corrompido_nao_derruba_a_api_e_e_preservado(client, tmp_path):
    arquivo = tmp_path / "pedidos_criados.json"
    arquivo.write_text("{lixo", encoding="utf-8")
    repositorio.reiniciar()
    assert client.get("/pedidos").json()["total"] == len(PEDIDOS)
    assert (tmp_path / "pedidos_criados.json.corrompido").read_text(encoding="utf-8") == "{lixo"
    assert client.post("/pedidos", json=CORPO).status_code == 201


def test_falha_ao_gravar_nao_deixa_pedido_pela_metade(monkeypatch):
    def quebrar(self):
        raise OSError("disco cheio")

    monkeypatch.setattr(repositorio.RepositorioPedidos, "_salvar", quebrar)
    r = TestClient(app, raise_server_exceptions=False).post("/pedidos", json=CORPO)
    assert r.status_code == 500
    assert r.json() == {"erro": "erro_interno", "mensagem": "Erro interno do servidor."}
    assert repositorio.obter().todos() == {}


# 7. Envio do evento ao Webhook ----------------------------------------------------
def test_webhook_desabilitado_por_padrao_nao_faz_chamada_http(client, monkeypatch):
    falso = _falso_post(monkeypatch, httpx.Response(200))
    r = client.post("/pedidos", json=CORPO)
    assert r.status_code == 201
    assert falso.chamadas == []


def test_envia_evento_pedido_criado_ao_webhook(client, monkeypatch, n8n_ligado):
    falso = _falso_post(monkeypatch, httpx.Response(200))
    r = client.post("/pedidos", json=CORPO)
    criado = r.json()

    assert r.status_code == 201
    assert criado["notificacao"]["status"] == "enviada"
    assert len(falso.chamadas) == 1  # uma tentativa, sem retries
    chamada = falso.chamadas[0]
    assert chamada["url"] == URL_N8N
    assert chamada["headers"] == {"X-Aula-Token": TOKEN}
    assert 0 < chamada["timeout"] <= 10
    assert chamada["json"] == {
        "evento": "pedido.criado",
        "pedido": {
            "codigo": criado["codigo"],
            "status": "em_preparacao",
            "tipo_entrega": "expressa",
            "criado_em": criado["criado_em"],
        },
    }


def test_sem_token_configurado_nao_envia_cabecalho(client, monkeypatch, n8n_ligado):
    monkeypatch.setenv("N8N_WEBHOOK_TOKEN", "")
    falso = _falso_post(monkeypatch, httpx.Response(200))
    client.post("/pedidos", json=CORPO)
    assert falso.chamadas[0]["headers"] == {}


def test_envio_real_pelo_httpx_com_transporte_simulado(client, monkeypatch, n8n_ligado):
    """Sem mock de httpx.post: passa por um cliente httpx real com transporte falso."""
    recebidas = []

    def handler(request: httpx.Request) -> httpx.Response:
        recebidas.append(request)
        return httpx.Response(200, json={"ok": True})

    transporte = httpx.MockTransport(handler)
    original = httpx.Client
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _post_com(original, transporte, url, **kw))
    r = client.post("/pedidos", json=CORPO)
    assert r.json()["notificacao"]["status"] == "enviada"
    assert recebidas[0].method == "POST"
    assert recebidas[0].headers["x-aula-token"] == TOKEN
    assert recebidas[0].headers["content-type"] == "application/json"
    assert json.loads(recebidas[0].content)["evento"] == "pedido.criado"


def _post_com(cliente_cls, transporte, url, **kw):
    with cliente_cls(transport=transporte) as c:
        return c.post(url, **kw)


# 8. Falha do Webhook sem perder o pedido -----------------------------------------
@pytest.mark.parametrize(
    "falha",
    [
        httpx.ConnectError("conexão recusada"),
        httpx.ConnectTimeout("timeout"),
        httpx.ReadTimeout("timeout"),
        httpx.Response(500),
        httpx.Response(404),
        httpx.Response(403),
        httpx.InvalidURL("url ruim"),
    ],
    ids=["indisponivel", "timeout-conexao", "timeout-leitura", "http-500", "http-404", "http-403", "url-invalida"],
)
def test_falha_do_webhook_nao_cancela_o_pedido(client, monkeypatch, n8n_ligado, falha):
    falso = _falso_post(monkeypatch, falha)
    r = client.post("/pedidos", json=CORPO)

    assert r.status_code == 201
    corpo = r.json()
    assert corpo["notificacao"]["status"] == "falhou"
    assert len(falso.chamadas) == 1  # sem retry

    # pedido continua disponível e persistido
    assert client.get(f"/pedidos/{corpo['codigo']}/resumo").status_code == 200
    repositorio.reiniciar()
    assert client.get(f"/pedidos/{corpo['codigo']}").status_code == 200


def test_resultado_da_notificacao_e_registrado_internamente(client, monkeypatch, n8n_ligado, tmp_path):
    _falso_post(monkeypatch, httpx.ConnectError("x"))
    codigo = client.post("/pedidos", json=CORPO).json()["codigo"]
    gravado = json.loads((tmp_path / "pedidos_criados.json").read_text(encoding="utf-8"))
    pedido = next(p for p in gravado["pedidos"] if p["codigo"] == codigo)
    assert pedido["metadata_operacional"]["notificacao_n8n"]["status"] == "falhou"


def test_token_e_detalhes_internos_nao_vazam_na_resposta_nem_nos_logs(client, monkeypatch, n8n_ligado, caplog):
    caplog.set_level("DEBUG")
    _falso_post(monkeypatch, httpx.ConnectError(f"falha {TOKEN} {URL_N8N}"))
    r = client.post("/pedidos", json=CORPO)
    assert TOKEN not in r.text and URL_N8N not in r.text and "ConnectError" not in r.text
    assert TOKEN not in caplog.text
    assert URL_N8N not in caplog.text

    _falso_post(monkeypatch, httpx.Response(200))
    client.post("/pedidos", json=CORPO)
    assert TOKEN not in caplog.text


# 9. Ausência de informações internas ---------------------------------------------
def test_respostas_e_evento_nao_expoem_campos_internos(client, monkeypatch, n8n_ligado):
    falso = _falso_post(monkeypatch, httpx.Response(200))
    r = client.post("/pedidos", json=CORPO)
    codigo = r.json()["codigo"]

    textos = [r.text, str(falso.chamadas[0]["json"]), json.dumps(falso.chamadas[0]["json"])]
    textos += [client.get(c).text for c in ("/pedidos", f"/pedidos/{codigo}", f"/pedidos/{codigo}/eventos", f"/pedidos/{codigo}/resumo")]
    for texto in textos:
        for proibido in CAMPOS_INTERNOS + VALORES_INTERNOS + [TOKEN]:
            assert proibido not in texto, f"{proibido} vazou"


def test_evento_do_webhook_tem_apenas_os_campos_minimos(client, monkeypatch, n8n_ligado):
    falso = _falso_post(monkeypatch, httpx.Response(200))
    client.post("/pedidos", json=CORPO)
    evento = falso.chamadas[0]["json"]
    assert set(evento) == {"evento", "pedido"}
    assert set(evento["pedido"]) == {"codigo", "status", "tipo_entrega", "criado_em"}


def test_openapi_documenta_post_sem_campos_internos(client):
    spec = client.get("/openapi.json")
    assert "post" in spec.json()["paths"]["/pedidos"]
    for campo in CAMPOS_INTERNOS:
        assert campo not in spec.text
