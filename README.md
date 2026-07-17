# Comer Fora — Backend (MVP real, multi-canal)

Backend real do produto de avaliação por voz/texto/foto do Comer Fora (iFood),
já estendido para cobrir o feed multi-canal, PDV-lite e respostas com IA
descritos nos protótipos de dashboard mais recentes (`dashboard_v2.html`,
`comer_fora_painel_saas_premium.html`, `comer_fora_experiencia_completa.html`).

**Decisão de escopo importante**: nenhuma integração externa de verdade
(Instagram, Google, WhatsApp, PDV real, Databricks) está implementada ainda.
Onde o produto precisa desses dados, a entrada é **manual** pelo gerente —
mas todo o processamento de IA por trás (sentimento, pilar, plausibilidade,
link com comanda, rascunho de resposta) é real. Trocar a fonte manual por uma
integração de verdade no futuro não deve exigir mudar essa camada de IA.

## Stack

- **FastAPI** (Python) — API
- **SQLite** via SQLAlchemy, com migração fácil pra Postgres depois (dado próprio; ver nota sobre Databricks abaixo)
- **Whisper API** (OpenAI) — transcrição de áudio
- **Gemini API** (Google) — sentimento, pilar, plausibilidade, link de PDV, rascunho de resposta
- **Docker Compose** — ambiente local

## Como rodar localmente

```bash
cp .env.example .env
# preencha GEMINI_API_KEY (obrigatório pra análise/resposta real — pegue em
# https://aistudio.google.com/apikey)
# OPENAI_API_KEY é opcional — sem ela, a transcrição vira um placeholder

docker compose up --build
docker compose exec api python -m scripts.seed
```

Não precisa de Postgres nem de nenhuma instalação de banco — SQLite já vem
pronto (um arquivo `comer_fora.db` é criado sozinho na primeira vez que o
servidor sobe). Quando for migrar pro piloto, troque `DATABASE_URL` no `.env`
pra uma URL de Postgres gerenciado (Neon, Supabase, etc.) — o código não muda.

API em `http://localhost:8000`, documentação interativa em `/docs`.
Testes: `python -m pytest tests/ -v` (inclui um teste de ponta a ponta que
não depende de nenhuma chave de API — usa SQLite em memória e o heurístico
local de IA).

## Estrutura

```
app/
  models.py      → Restaurant, RestaurantTable, Customer, Review (multi-canal),
                    ReviewTag, RewardRedemption, PDVOrder, ReviewResponseDraft
  routers/
    customers.py → POST /customers/lookup
    reviews.py   → fluxo de avaliação (áudio/texto/externo) + resposta com IA
    hub.py       → hub modular do cliente: preview de IA + fechamento único
    pdv.py       → PDV-lite (comandas manuais + link sugerido por IA)
    dashboard.py → feed unificado, KPIs, pilares, ISR
  services/
    transcription.py  → Whisper (fallback se sem chave)
    ai_analysis.py     → sentimento + pilar + plausibilidade (fallback heurístico)
    pdv_linking.py     → IA sugere a qual comanda uma reclamação se refere
    response_draft.py  → IA rascunha resposta no tom escolhido
    points.py          → fórmulas de pontuação
    security.py        → hash de CPF
tests/
  test_health.py    → smoke test
  test_pipeline.py  → ponta a ponta: CPF → review → PDV → resposta → dashboard
  test_hub.py       → ponta a ponta do hub modular (múltiplos módulos + CPF no final)
```

## Canais suportados (`Channel`)

| Canal | Fonte no MVP | Vira integração real quando |
|---|---|---|
| `voz_local` / `texto_local` | Nosso próprio app (QR na mesa) | Já é real |
| `estrelas_local` / `fotos_local` | Módulos do hub do cliente (a implementar no front) | Já é real |
| `instagram`, `google`, `whatsapp` | Gerente cola manualmente via `POST /reviews/external` | Social listening (Brandwatch etc.) — pós-piloto |
| `ifood_pedido` | Gerente lança manualmente | Integração com pedido real do iFood — pós-piloto |

## PDV-lite

`POST /pdv/orders` cria uma comanda manualmente (mesa, valor, itens).
`POST /pdv/reviews/{review_id}/suggest-link` pede pra IA comparar o texto da
avaliação com os itens das comandas abertas e sugerir qual delas está
relacionada, com confiança e justificativa — é a mesma ideia do "94% de
confiança" do mockup, só que a fonte da comanda é manual, não um PDV real.
`POST /pdv/orders/{order_id}/link/{review_id}` confirma o vínculo.

## IA de resposta com tom

`POST /reviews/{review_id}/generate-response` com `{"tone": "friendly"}` (ou
`apologetic`, `professional`, `assertive`) gera um rascunho de resposta.
**Isso nunca envia nada sozinho** — é só o texto pro gerente copiar. Enviar
mensagem de verdade é sempre uma ação manual do gerente.

## Métrica-norte

`PATCH /reviews/{id}/mark-actioned` é o endpoint que o gerente usa pra marcar
"agi em cima disso". `GET /dashboard/{id}/summary` calcula `percent_actioned`
em cima disso — essa é a métrica que decide se o produto está funcionando.

## Nota sobre Databricks

O iFood usa Databricks internamente, mas o time decidiu **não integrar dado
existente agora** e manter banco próprio (SQLite, migrável pra Postgres depois)
— decisão certa pro MVP: evita depender de acesso/permissão de outro time
enquanto o produto ainda está mudando de forma toda semana. O schema aqui é
relacional e limpo de propósito, então gerar um export (batch, noturno) pro
Databricks mais tarde é um job de ETL simples — não deveria exigir redesenhar
o banco, seja ele SQLite ou Postgres.

## O que é real vs. placeholder

| Peça | Estado | Antes do piloto |
|---|---|---|
| Sentimento, pilar, plausibilidade | **Real** (Gemini API) | Rodar eval set (Semana 2–3) |
| Transcrição de áudio | **Real** (Whisper API) | Testar qualidade em PT-BR |
| Link review ↔ comanda | **Real** (IA), fonte da comanda é manual | Integração de PDV real |
| Rascunho de resposta com tom | **Real** (Gemini API) | Validar tom com gerentes reais |
| Feed multi-canal | Real no processamento, manual na entrada | Social listening licenciado |
| Cálculo de pontos | **Real** | Ajustar fórmula com dado do piloto |
| Autenticação do cliente | Placeholder (CPF + hash) | QR logado no app iFood |
| Autenticação do gerente | Placeholder (chave fixa em header) | Login real por restaurante |
| Armazenamento de áudio | Placeholder (disco local) | Storage de objeto + retenção real |
| Migrations de banco | Placeholder (`create_all`) | Alembic antes de dado de produção |

## Frontends — já conectados (não são mais mockups isolados)

Este pacote tem **dois** HTMLs prontos, ambos chamando os endpoints reais
acima diretamente via `fetch`, sem build step nenhum:

### `comer-fora-experiencia-conectada.html` — app do cliente
Hub modular (áudio/estrelas/fotos/texto + CPF por último). Chama
`/ai/analyze-preview` durante a digitação/revisão e `/reviews/hub-submit`
no fechamento. Cai num heurístico local se o backend estiver fora do ar.

**Configurar**: edite a constante `BACKEND.restaurantId` no `<script>`.

### `comer-fora-painel-gerente.html` — painel do gerente
Feed unificado com filtro por canal/sentimento, KPIs (total do dia, ISR,
% ações tomadas, pontos), pilares, PDV-lite (lançar comanda + IA sugerindo
vínculo com uma avaliação), e rascunho de resposta com IA em 4 tons. Cada
ação (marcar ação tomada, confirmar vínculo, gerar resposta) chama a API
na hora — não tem dado mockado.

**Configurar**: abra o arquivo, cole o `restaurant_id` (impresso por
`scripts/seed.py`) e a chave do gerente (do seu `.env`) nos campos do topo,
clique em "Carregar painel".

**Para rodar os dois**: suba o backend, rode o seed, abra os dois HTMLs
com a extensão Live Server do VS Code (ou qualquer servidor estático) —
o CORS já está liberado (`allow_origins=["*"]`) pra isso funcionar sem
configuração extra em desenvolvimento.

## Próximos passos

- Trocar `BACKEND.restaurantId` fixo por resolução real via QR code
  (a URL do QR já viria com o `restaurant_id`/mesa embutidos).
- Trocar a chave fixa do gerente por login real por restaurante.
- Semana 2–3 do roadmap: eval set de 30–40 avaliações reais/simuladas antes
  de confiar na IA na frente de um gerente de verdade.
- Restringir CORS ao domínio real antes de qualquer piloto (hoje está
  liberado geral, de propósito, só pra desenvolvimento local).
