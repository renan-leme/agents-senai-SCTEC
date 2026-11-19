# API de Pedidos e Entregas (fictícia)

API REST com dados **fictícios**, criada para demonstrar como agentes de IA
(Python + LangChain/LangGraph e n8n) consomem APIs HTTP. Feita com FastAPI + Pydantic v2.
Consulta pedidos (`GET`), **cadastra novos pedidos fictícios** (`POST /pedidos`) e, opcionalmente,
**avisa o n8n** por Webhook quando um pedido é criado.

> ⚠️ **Antes de expor publicamente** é obrigatório adicionar autenticação (ex.: API key ou OAuth2)
> e servir somente por HTTPS (proxy reverso com TLS). Esta versão didática não tem nenhum dos dois.

## Estrutura

```
app/main.py        rotas, tratamento de erros, simulação de falhas (dev)
app/schemas.py     contratos Pydantic (modelo interno x modelos públicos x corpo do POST)
app/data.py        11 pedidos fictícios originais (referência; nunca alterados)
app/catalogo.py    catálogo fictício de SKUs aceitos no POST
app/service.py     consultas e cadastro de pedidos
app/repositorio.py persistência local em JSON dos pedidos cadastrados
app/webhook.py     notificação ao Webhook do n8n (httpx, 1 tentativa, timeout curto)
dados/             criado automaticamente; guarda pedidos_criados.json (ignorado pelo Git)
tests/             testes (sem LLM, sem internet, sem n8n real)
.env.example       configuração de exemplo
```

## Executar (Ubuntu)

```bash
# 1. ambiente virtual (separado do ambiente do curso)
python3 -m venv .venv-api
source .venv-api/bin/activate

# 2. dependências
pip install -r requirements.txt

# 3. iniciar a API (somente loopback)
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

* Swagger: <http://127.0.0.1:8000/docs>
* Testes: `pytest -q`

Configuração por variáveis de ambiente (veja `.env.example`). Para usar um arquivo, **não sobrescreva
o `.env` que já existe neste diretório**; use outro nome:

```bash
cp .env.example .env.api
uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env.api
```

## Pedidos fictícios

"Hoje" nos dados originais é 18/11/2026.

| Código   | Status          | Atraso | Observação                                              |
|----------|-----------------|:------:|---------------------------------------------------------|
| PED-3107 | `entregue`      | não    | Entregue antes da previsão                              |
| PED-3108 | `em_transporte` | não    | No prazo (previsão 20/11)                               |
| PED-3109 | `em_transporte` | **sim**| Greve na rota; previsão 12/11 vencida                   |
| PED-3110 | `em_preparacao` | não    | Sem transportadora ainda                                |
| PED-3111 | `em_separacao`  | não    |                                                         |
| PED-3112 | `enviado`       | não    | Postado, sem movimentação posterior                     |
| PED-3113 | `cancelado`     | não    | Sem previsão de entrega                                 |
| PED-3114 | `devolvido`     | não    | Foi entregue e depois devolvido (defeito)               |
| PED-3115 | `entregue`      | **sim**| Entregue 3 dias após a previsão                         |
| PED-3116 | `em_transporte` | **sim**| Tentativa de entrega sem sucesso                        |
| PED-3117 | `entregue`      | não    | Vários itens                                            |

Inexistente (404): `PED-9999`. Código inválido (422): `PED-12`, `abc`.

## Endpoints

| Método | Rota                         | Descrição                                                  |
|--------|------------------------------|------------------------------------------------------------|
| GET    | `/health`                    | Estado da API                                              |
| POST   | `/pedidos`                   | **Cadastra** um pedido fictício (HTTP 201) — veja a próxima seção |
| GET    | `/pedidos`                   | Lista resumida. Filtros: `?status=...` e `?atraso_registrado=true\|false` |
| GET    | `/pedidos/{codigo}`          | Dados públicos do pedido (inclui produtos e último evento) |
| GET    | `/pedidos/{codigo}/eventos`  | Histórico de movimentações em ordem cronológica            |
| GET    | `/pedidos/{codigo}/resumo`   | Só o necessário para o agente responder sobre a entrega    |

`tipo_entrega` (`normal` ou `expressa`) aparece em `GET /pedidos` e `GET /pedidos/{codigo}`. Os pedidos
originais, que não têm esse dado, são exibidos como `normal`. O contrato de `/resumo` não mudou.
Os produtos passaram a ter o campo `sku` (`null` nos pedidos originais).

Status aceitos: `em_preparacao`, `em_separacao`, `enviado`, `em_transporte`, `entregue`, `cancelado`, `devolvido`.

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/pedidos
curl -s "http://127.0.0.1:8000/pedidos?status=em_transporte"
curl -s "http://127.0.0.1:8000/pedidos?atraso_registrado=true"
curl -s http://127.0.0.1:8000/pedidos/PED-3107
curl -s http://127.0.0.1:8000/pedidos/PED-3109/eventos
curl -s http://127.0.0.1:8000/pedidos/PED-3109/resumo
```

Exemplo de `/pedidos/PED-3109/resumo`:

```json
{
  "codigo": "PED-3109",
  "status": "em_transporte",
  "previsao_entrega": "2026-11-12",
  "entregue_em": null,
  "ultimo_evento": "Objeto em trânsito, rota retomada",
  "data_ultimo_evento": "2026-11-16T17:35:00-03:00",
  "atraso_registrado": true
}
```

### Formato de erro (sempre o mesmo)

```json
{"erro": "pedido_nao_encontrado", "mensagem": "Pedido não localizado."}
```

| HTTP | `erro`                  | Quando                                              |
|------|-------------------------|-----------------------------------------------------|
| 404  | `pedido_nao_encontrado` | Código válido, mas inexistente                      |
| 422  | `parametro_invalido`    | Código fora do padrão `PED-NNNN`, status inválido ou corpo do POST inválido (inclui `detalhes`) |
| 405  | `metodo_nao_permitido`  | Método não previsto para a rota (ex.: `DELETE /pedidos/PED-3107`) |
| 503  | `servico_indisponivel`  | Somente com a simulação de falhas ligada            |
| 500  | `erro_interno`          | Falha inesperada (sem stack trace; detalhes só no log do servidor) |

## Cadastrar pedidos (`POST /pedidos`)

Corpo da requisição (JSON):

| Campo            | Obrigatório | Regras                                                              |
|------------------|:-----------:|---------------------------------------------------------------------|
| `tipo_entrega`   | não         | `normal` (padrão) ou `expressa`                                     |
| `transportadora` | não         | texto de até 60 caracteres                                          |
| `produtos`       | **sim**     | de 1 a 20 itens `{"sku": "SKU-101", "quantidade": 2}`; `quantidade` inteira de 1 a 100 |

SKUs do catálogo fictício: `SKU-101` Teclado mecânico compacto, `SKU-102` Mouse sem fio,
`SKU-103` Monitor 24 polegadas, `SKU-104` Webcam Full HD, `SKU-105` Hub USB 4 portas,
`SKU-106` Headset gamer, `SKU-107` Cabo HDMI 2m, `SKU-108` Suporte para monitor.

A API gera sozinha: o código (`PED-4001`, `PED-4002`, ...), a data/hora de criação (fuso -03:00), o status
`em_preparacao`, o evento inicial **"Pedido criado"** e a previsão de entrega fictícia
(`normal` = hoje + 7 dias; `expressa` = hoje + 3 dias). Campos desconhecidos (`status`, `nota_interna`...)
são rejeitados com 422; campos internos nunca são devolvidos.

### Pelo Swagger

1. Abra <http://127.0.0.1:8000/docs>.
2. Expanda **POST /pedidos** → **Try it out**. O corpo de exemplo já vem preenchido.
3. Clique em **Execute**: a resposta deve ser **201** com o `codigo` do novo pedido.
4. Expanda **GET /pedidos/{codigo}/resumo**, cole o código e execute.

### Pelo `curl`

```bash
curl -s -i -X POST http://127.0.0.1:8000/pedidos \
  -H "Content-Type: application/json" \
  -d '{"tipo_entrega": "expressa", "transportadora": "Entrega Express",
       "produtos": [{"sku": "SKU-101", "quantidade": 2}]}'
```

Resposta (`HTTP/1.1 201 Created`, cabeçalho `Location: /pedidos/PED-4001`):

```json
{
  "codigo": "PED-4001",
  "status": "em_preparacao",
  "tipo_entrega": "expressa",
  "transportadora": "Entrega Express",
  "criado_em": "2026-11-19T19:30:00-03:00",
  "previsao_entrega": "2026-11-22",
  "produtos": [{"nome": "Teclado mecânico compacto", "quantidade": 2, "sku": "SKU-101"}],
  "notificacao": {"status": "desabilitada", "mensagem": "Notificação ao n8n desabilitada."}
}
```

`notificacao.status` é `desabilitada`, `enviada` ou `falhou`.

### Consultar o pedido criado

```bash
curl -s http://127.0.0.1:8000/pedidos/PED-4001            # detalhes
curl -s http://127.0.0.1:8000/pedidos/PED-4001/resumo     # resumo para o agente
curl -s http://127.0.0.1:8000/pedidos/PED-4001/eventos    # histórico: "Pedido criado"
curl -s "http://127.0.0.1:8000/pedidos?status=em_preparacao"
```

Erro de validação (HTTP 422), por exemplo quantidade `0` ou `tipo_entrega` inválido:

```json
{"erro": "parametro_invalido", "mensagem": "Tipo de entrega inválido. Valores aceitos: normal, expressa.",
 "detalhes": [{"campo": "tipo_entrega", "mensagem": "Tipo de entrega inválido. Valores aceitos: normal, expressa."}]}
```

### Onde os pedidos ficam guardados

Os 11 pedidos originais ficam no código (`app/data.py`) e **nunca são alterados**. Os pedidos novos são gravados
em `dados/pedidos_criados.json` (ou no caminho de `PEDIDOS_ARQUIVO`) e voltam a existir quando a API é
reiniciada. Para "zerar" a demonstração, pare a API e apague esse arquivo. Pensado para **uma única instância
local** (um processo `uvicorn`, sem `--workers`).

## Integração com o n8n (Webhook)

Depois de cadastrar um pedido, a API pode enviar **uma** requisição `POST` ao Webhook do n8n. Fica
**desabilitada por padrão**.

| Variável                       | Padrão                                         | Função                                         |
|--------------------------------|------------------------------------------------|------------------------------------------------|
| `N8N_WEBHOOK_ENABLED`          | `false`                                        | `true` liga o envio                            |
| `N8N_WEBHOOK_URL`              | `http://127.0.0.1:5678/webhook/novo-pedido`    | endereço do Webhook                            |
| `N8N_WEBHOOK_TOKEN`            | vazio                                          | enviado no cabeçalho `X-Aula-Token`            |
| `N8N_WEBHOOK_TIMEOUT_SEGUNDOS` | `3` (limitado a 0.5–10)                        | tempo máximo de espera (opcional)              |

Como a API roda direto no Ubuntu e o n8n está em Docker com a porta `5678` publicada no Ubuntu, a API o
alcança por `127.0.0.1:5678` (o endereço do **host**, não de dentro do contêiner).

```bash
cp .env.example .env.api     # edite: N8N_WEBHOOK_ENABLED=true e N8N_WEBHOOK_TOKEN=um-token-da-aula
uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env.api
# ou, sem arquivo:
N8N_WEBHOOK_ENABLED=true N8N_WEBHOOK_TOKEN=um-token-da-aula uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Evento enviado (somente estes campos; data/hora geradas na hora do cadastro):

```json
{
  "evento": "pedido.criado",
  "pedido": {
    "codigo": "PED-4001",
    "status": "em_preparacao",
    "tipo_entrega": "expressa",
    "criado_em": "2026-11-19T19:30:00-03:00"
  }
}
```

Cabeçalho: `X-Aula-Token: <N8N_WEBHOOK_TOKEN>` (omitido se o token estiver vazio). O token não vai para
logs nem para as respostas, e o evento não leva campos internos, produtos nem dados de cliente.

### Se o n8n falhar, o pedido continua valendo

O pedido é gravado **antes** da notificação. Indisponibilidade, timeout ou resposta HTTP de erro (4xx/5xx)
resultam em `201` com `"notificacao": {"status": "falhou", ...}`; o pedido segue consultável (inclusive após
reiniciar). Não há retries: uma tentativa, com timeout curto. O resultado também é registrado no log do
servidor (sem URL, token ou detalhes) e no campo interno do pedido salvo.

### Criar o Webhook no n8n

1. No n8n (<http://127.0.0.1:5678>), crie um workflow novo e adicione o nó **Webhook**.
2. Configure: **HTTP Method** `POST`; **Path** `novo-pedido`; **Authentication** `Header Auth` → crie uma
   credencial com **Name** `X-Aula-Token` e **Value** igual ao `N8N_WEBHOOK_TOKEN`; **Respond**
   `Immediately`.
3. Adicione um nó depois do Webhook para ver o resultado (por exemplo, **Edit Fields (Set)** ou um nó de
   mensagem) usando `{{ $json.body.pedido.codigo }}`.
4. O n8n mostra duas URLs no nó: **Test URL** e **Production URL**. Veja a diferença abaixo.

### `/webhook-test/` x `/webhook/`

| URL                                  | Quando funciona                                                                  |
|--------------------------------------|----------------------------------------------------------------------------------|
| `.../webhook-test/novo-pedido`       | Só enquanto você clica em **Listen for test event** (ou *Execute workflow*) no editor; atende **uma** chamada e mostra os dados no editor. Use para montar o fluxo. |
| `.../webhook/novo-pedido`            | Só com o workflow **Active** (chave *Active* ligada). Roda sozinho, sem o editor aberto; as execuções aparecem na aba *Executions*. |

Para a demonstração com o workflow ativo, use a URL padrão (`/webhook/`). Para testar enquanto constrói o
fluxo, troque temporariamente `N8N_WEBHOOK_URL` para a `/webhook-test/` e clique em *Listen for test event*
antes de cada POST. Webhook de teste não escutando, ou workflow inativo, responde 404 → a API informa
`falhou` (e o pedido continua cadastrado).

### Demonstrar uma falha

1. Com a integração ligada e o workflow ativo, cadastre um pedido: `notificacao.status = "enviada"`.
2. Pare o n8n: `docker stop <nome-do-container-n8n>` (veja o nome com `docker ps`).
3. Cadastre outro pedido: continua **201**, agora com `notificacao.status = "falhou"`, e
   `GET /pedidos/{codigo}/resumo` mostra o pedido normalmente.
4. Religue com `docker start <nome-do-container-n8n>`. (Os eventos perdidos **não** são reenviados.)

Alternativas sem parar o Docker: usar a URL `/webhook-test/` sem estar escutando, ou configurar um token
diferente do esperado no n8n (o Webhook responde 403 → `falhou`).

## Reproduzir cenários

| Cenário                    | Comando                                                       |
|----------------------------|---------------------------------------------------------------|
| Sucesso                    | `curl -i localhost:8000/pedidos/PED-3107/resumo`              |
| Pedido atrasado            | `curl -s localhost:8000/pedidos/PED-3109/resumo`              |
| Cancelado / devolvido      | `.../pedidos/PED-3113/resumo`, `.../pedidos/PED-3114/resumo`  |
| Inexistente (404)          | `curl -i localhost:8000/pedidos/PED-9999`                     |
| Código inválido (422)      | `curl -i localhost:8000/pedidos/PED-12`                       |
| Status inválido (422)      | `curl -i "localhost:8000/pedidos?status=voando"`              |

### Simulação de 503 e de lentidão (somente desenvolvimento)

Desabilitada por padrão. Não existe endpoint administrativo: a simulação só funciona se o **processo
for iniciado** com `API_SIMULACAO_DEV=true`. Sem isso, os cabeçalhos `X-Dev-*` são ignorados.
Nunca habilite em implantação pública. `/health` nunca é afetado.

```bash
# Ligar a simulação (apenas nesta execução)
API_SIMULACAO_DEV=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Por requisição (cabeçalhos):

```bash
curl -i -H "X-Dev-Simular: 503" localhost:8000/pedidos/PED-3107/resumo   # HTTP 503
curl -m 3 -H "X-Dev-Atraso: 8" localhost:8000/pedidos/PED-3107/resumo    # demora 8 s -> curl estoura o timeout de 3 s
```

Para todas as requisições (útil no n8n, onde é mais simples reiniciar a API do que mexer no workflow):

```bash
API_SIMULACAO_DEV=true API_FORCAR_503=true     uvicorn app.main:app --host 127.0.0.1 --port 8000   # tudo 503
API_SIMULACAO_DEV=true API_ATRASO_SEGUNDOS=10  uvicorn app.main:app --host 127.0.0.1 --port 8000   # tudo 10 s mais lento
```

O atraso é limitado a 60 s e não bloqueia o servidor para outras requisições.

## Consumir com Python (`httpx`)

```python
import httpx

BASE_URL = "http://127.0.0.1:8000"

def consultar_resumo(codigo: str) -> dict:
    """Função que uma @tool do LangChain pode chamar."""
    try:
        r = httpx.get(f"{BASE_URL}/pedidos/{codigo}/resumo", timeout=5.0)
    except httpx.TimeoutException:
        return {"erro": "timeout", "mensagem": "A API demorou demais para responder."}
    except httpx.ConnectError:
        return {"erro": "api_fora_do_ar", "mensagem": "Não foi possível conectar à API."}

    # 200, 404, 422 e 503 devolvem JSON; erros já vêm no formato {"erro", "mensagem"}
    return r.json()

print(consultar_resumo("PED-3109"))
print(consultar_resumo("PED-9999"))   # {'erro': 'pedido_nao_encontrado', ...}
```

Devolver o erro como dado (em vez de levantar exceção) permite ao agente explicar o problema ao usuário.

## Acessar a API a partir do n8n em Docker

Dentro de um contêiner, `127.0.0.1` é o próprio contêiner, **não** o seu Ubuntu. Então
`http://127.0.0.1:8000` não funciona no n8n; a API precisa escutar em um endereço que o contêiner alcance.

### Opção A (recomendada): escutar só na ponte do Docker

A API fica acessível pelos contêineres e pelo próprio host, **mas não pela rede local**.

```bash
ip -4 addr show docker0          # normalmente 172.17.0.1
uvicorn app.main:app --host 172.17.0.1 --port 8000
```

Inicie o n8n mapeando o nome `host.docker.internal` para o host:

```bash
docker run -it --rm --name n8n -p 5678:5678 \
  --add-host=host.docker.internal:host-gateway \
  -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

(No Docker Compose: `extra_hosts: ["host.docker.internal:host-gateway"]`.)
No n8n use a URL `http://host.docker.internal:8000/pedidos/{codigo}/resumo`
(ou `http://172.17.0.1:8000/...`). Se o `ufw` estiver ativo e bloquear:
`sudo ufw allow from 172.16.0.0/12 to any port 8000 proto tcp`.

### Opção B: escutar em todas as interfaces (`0.0.0.0`)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Qualquer máquina da sua rede passa a alcançar a API (que não tem autenticação). Use só em rede
confiável e/ou restrinja com firewall: `sudo ufw allow from 172.16.0.0/12 to any port 8000 proto tcp`.
Não publique a porta na internet.

### Opção C: n8n com rede do host

`docker run --network host ...` (sem `-p`): o n8n enxerga o `127.0.0.1` do Ubuntu e a API pode continuar
em loopback. (Em Linux, não precisa de `--add-host`.) Em contrapartida, o contêiner perde o isolamento de rede.

### Se a API também rodar em contêiner

Coloque ambos na mesma rede Docker e use o nome do serviço (`http://api:8000`). Não precisa publicar a
porta da API no host (`-p`) se só o n8n a acessa; se publicar, use `-p 127.0.0.1:8000:8000`.

### Configuração do HTTP Request Tool no n8n

* Método `GET`, URL `http://host.docker.internal:8000/pedidos/{codigo}/resumo`
  com `codigo` definido como placeholder da tool (preenchido pelo agente).
* Defina um **timeout** (ex.: 5000 ms) e habilite o tratamento de erros HTTP para que o agente receba o
  JSON `{"erro", "mensagem"}` em 404/422/503 em vez de interromper o workflow.

## Segurança (resumo)

* O único endpoint que grava é `POST /pedidos` (cria pedidos novos). Não há alteração nem cancelamento de
  pedidos, e os pedidos originais nunca são sobrescritos.
* O corpo do POST aceita só `tipo_entrega`, `transportadora` e `produtos`; qualquer outro campo é rejeitado.
* Campos internos (`nota_interna`, `cliente_id_interno`, `metadata_operacional`) existem apenas no modelo
  interno; as respostas usam `response_model` com modelos públicos que não os possuem. Há testes que
  verificam ausência dos nomes e dos valores internos em todas as respostas e no OpenAPI.
* Parâmetros validados no servidor (regex `^PED-[0-9]{4}$`, enum de status); o valor inválido enviado não é
  repetido na resposta.
* Respostas de erro não incluem stack trace nem caminhos; detalhes técnicos ficam apenas no log.
* Sem segredos no código. A simulação de falhas e a notificação ao n8n são opt-in por variável de ambiente.
* O token do n8n (`N8N_WEBHOOK_TOKEN`) só viaja no cabeçalho `X-Aula-Token`; não é logado nem devolvido. Não
  versione o `.env.api`.
* Para uso público: autenticação, HTTPS, rate limiting e `--host` restrito.
