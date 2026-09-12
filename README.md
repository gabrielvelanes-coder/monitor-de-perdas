# Monitor de Perdas — Grupo Velanes

Dashboard Streamlit para acompanhar a **taxa de perdas por mês** (perda ÷
faturamento), abrir essa perda por motivo — separando o que sai do estoque
sem compensação (quebra: vencido/danificado/furto/descontinuado) do que tem
alguma contrapartida (marketing/reembolso/consumo/doação) — e diagnosticar de
onde vem o vencimento cruzando com curva / giro / estoque / catálogo.

## As telas (`st.navigation`)

Visíveis no menu:

| Tela | Pergunta que responde |
|---|---|
| **Painel** | A perda é aceitável? Escopo escolhível na própria tela (**Vencido / Perda direta / Todos os motivos** — perda = toda baixa do sistema por padrão). 4 KPIs (faturamento · perda no escopo · taxa ponderada · gap vs meta), semáforo + diagnóstico automático, evolução mensal vs meta, ranking de lojas por taxa, bridge de escopo (3 recortes lado a lado), top motivos. |
| **Anatomia da perda** | O que são esses itens? Abre em **Todos os motivos** e traz um bloco fixo "Todos os motivos no recorte" (R$/unid/linhas/produtos por motivo). Escopo Vencido / Perda direta / Todos + motivos específicos. Medicamento × não-medicamento × sem classificação, por categoria da árvore, por curva de quantidade (**Com giro A–H** / **Sem giro I**), por **tempo da última venda** (até 90 / até 180 / acima de 180 dias). Os 3 gráficos são clicáveis (clique substitui a seleção anterior no mesmo gráfico) e filtram a tabela de produtos (uma linha por produto **e motivo**). |
| **Itens a vencer** | **Saldo do pré-vencido** (o que resta do lote a vencer, não o estoque geral) com data de validade, por loja — para agir antes de virar perda. Urgência em 4 faixas cumulativas: **Até 30 / 90 / 180 dias / 12 meses**. KPIs de valor exposto por urgência, gráfico por urgência e por loja, tabela com lote/validade/curva. Cruza com o DADOS só para trazer custo médio (valor = saldo × custo). |

Ocultas do menu (código continua em `app.py`, é só remover o comentário de
`st.navigation` para reativar): **Motivos** (de-para de cada motivo de baixa
com % do faturamento e classe Vencido/Outra perda direta/Baixa comercial —
pausada a pedido do Gabriel, sem mexer por ora), **Evitável × estrutural**
(4 baldes — PDV / excesso de compra / item suspenso / fora do mix — com ação
por item) e **Regras e simulação** (simula teto de estoque por curva/categoria
e estima economia/mês).

## Filtros

- **Por tela:** cada tela tem `Meses (nesta tela)` + `Lojas (nesta tela)`
  (Painel/Motivos/Anatomia) — some quando o recorte já tem ≤ 1 mês/loja. O
  Painel tem seu próprio seletor de **Escopo da perda** (Vencido / Perda
  direta / Todos os motivos, default Todos) e a Anatomia tem o dela também
  (Vencido / Perda direta / Todos / específicos) — são independentes.
- **Regional (nesta tela):** Painel, Anatomia e Itens a vencer têm um
  multiselect de regional (2 supervisores, cada um cuida de um grupo de
  lojas) — vem de `regionais.csv` (loja, regional), arquivo próprio fora do
  git porque a divisão é rotativa. Sem esse arquivo na pasta, o filtro
  simplesmente não aparece.
- **Sem filtro global de loja/período na barra lateral** (removido a pedido em
  2026-09-11) — meta e "incluir depósito" ficam fixos no código
  (`META_PADRAO` = 0,40 %, sem DEP) em vez de widgets.

## Por que existe

Numa reunião foi apresentada uma taxa de perdas que parecia alta demais.
Cruzando o relatório de baixa de estoque com o faturamento **mensal real** por
loja (Power BI *Visão geral - mês* → Receita por Und. ID), a taxa acumulada
jan–ago/2026 (todas as lojas, sem DEP) fica em:

| Recorte | % do faturamento | R$/mês |
|---|---:|---:|
| Somente vencidos | **0,55 %** | ~43 mil |
| Perda direta (venc.+danif.+furto+descont.+outros) | **0,58 %** | ~46 mil |
| Todos os motivos | **0,69 %** | ~54 mil |

Média mensal da taxa (somente vencidos) jan–ago: **0,53 %**, com tendência de alta
jun→jul→ago (0,51 → 0,55 → 0,61 %). Faixa normal de varejo farma: 0,3 %–0,8 %.
Vencido responde por ~79 % do valor lançado.

Distorções comuns num número inflado (ex.: o 0,96 % do BI em agosto):

- contar **AÇÃO DE MARKETING, REEMBOLSO PELO FORNECEDOR, DOAÇÃO, CONSUMO LOJA**
  como perda (juntos ~0,28 p.p. em agosto, e não são perda);
- somar a linha **"Total"** do relatório (já é a soma de tudo);
- usar o **acumulado do ano** como se fosse de um mês;
- dividir por lucro / CMV em vez de faturamento.

O expander **"Bater com o número da reunião"** (no Painel) faz essa comparação
na tela; a tela **Motivos** mostra o de-para completo.

## Como rodar

```bash
cd "C:\Users\E.C Velanes\OneDrive\Área de Trabalho\PERDAS"
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none
```

`--server.fileWatcherType none` → mudança de código só entra com restart do
servidor. `iniciar.bat` faz o duplo-clique. Python usado:
`C:\Users\E.C Velanes\AppData\Local\Programs\Python\Python314\python.exe`.

## Entradas (colocar nesta pasta ou enviar pela barra lateral)

| # | Arquivo | O que é |
|---|---------|---------|
| 1 | `perdas ... com motivo e loja.xls` | Análise de Baixa de Estoque (produto, motivo, loja, mês, valor). **Obrigatório.** |
| 2 | `DADOS *.xlsx` | Cadastro **por loja**: curva, média de venda, dias sem vender, estoque, motivo de suspensão. Um ou vários arquivos. Base operacional (giro/mvm/estoque) — habilita Anatomia / Evitável / Regras. |
| 3 | `BASE CADASTRO COM GRUPOS.xlsx` | Catálogo **nível produto** (sem loja): `Classificação` (árvore), `Curva Valor`/`Qtd.`, `Status` (Ativo/Inativo). **Só enriquece** — preenche `classif`/`curva` que faltam no DADOS. Opcional. |
| 4 | `faturamento.csv` | Faturamento por loja e mês. Sem ele os valores aparecem em R$, mas não em %. |
| 5 | `itens a vencer.xlsx` | Saldo do pré-vencido com lote/validade, por loja (relatório do ERP: *controle de validade* / *produtos a vencer*). Traz `Saldo` (o que resta do lote pré-vencido — usado na exposição) e `Estoque Atual` (estoque geral, só de referência). Opcional — habilita a tela **Itens a vencer**. |
| 6 | `regionais.csv` | De-para **loja → regional** (2 colunas: loja, regional). Rotativo — edita à mão quando a divisão dos supervisores mudar. Opcional — habilita o filtro **Regional (nesta tela)** no Painel/Anatomia/Itens a vencer. |

`BASE CADASTRO COM EAN.xlsx` **não é usada** (o relatório de perdas não tem EAN).

### Formato do faturamento

Longo (recomendado) — uma linha por loja e mês:

```csv
loja,ano_mes,faturamento
2,2026-01,132256.54
3,2026-01,232022.80
```

Também aceita formato largo (lojas nas linhas, meses `2026-01`, `jan`... nas
colunas). Origem: Power BI *Visão geral - mês* → coluna **Receita** por
**Und. ID**, um mês fechado por vez. O `faturamento.csv` que acompanha traz
**jan–ago/2026** (valores mensais reais); falta **setembro** (mês não fechado).
Conferir sempre: soma das 22 lojas (2–11, 13–20, 22–25) = Total do relatório.

Dá para digitar na barra lateral (**Digitar faturamento**); fica salvo em
`faturamento.json` — mas o `faturamento.csv` na pasta **tem prioridade**.

## Escopos de perda

Nomes descritivos de propósito — nenhum escopo é "mais real" que outro, a
diferença é só o que cada um inclui:

- **Somente vencidos** — só o motivo "produto vencido".
- **Perda direta** — vencido + danificado + furto + descontinuado + outros:
  sai do estoque sem nenhuma compensação.
- **Todos os motivos** — soma tudo, incluindo marketing, consumo de loja,
  reembolso, devolução, bonificação, doação, treinamento — motivos que
  também tiram item do estoque, mas com alguma contrapartida (o fornecedor
  reembolsa, o item vira uso interno, etc.). Padrão do Painel desde
  2026-09-12, a pedido do Gabriel — perda = toda baixa do sistema.

## Medicamento × não-medicamento

Sai do **nível 1 da árvore mercadológica** (`Classificação` — do DADOS, e do
catálogo quando o DADOS não tem): só **GENÉRICO / SIMILAR / PROPAGADO** é
`medicamento`; qualquer outra categoria é `nao-medicamento`; sem categoria é
`sem classificacao`. Com o catálogo integrado, "sem classificação" no vencido
jan–set caiu de R$ 22.039 para **R$ 4.174** (residual de itens fora de qualquer
base) — o resto virou medicamento (R$ 231.003) / não-medicamento (R$ 153.278).

## Notas técnicas

- 1ª leitura dos `DADOS*.xlsx` e do catálogo demora (segundos por arquivo com
  `calamine`); depois fica em cache em `.cache/*.parquet` até o arquivo mudar.
- O relatório `.xls` vem com acentos corrompidos (`A��O DE MARKENTIG`);
  a classificação de motivos e a chave de join do catálogo são feitas por trecho
  sem acento (`_ascii` / `_norm_produto`), então funciona mesmo assim.
- **Join catálogo ↔ perda é por descrição exata normalizada.** Variações de
  embalagem no nome (`... UNO` vs `... UNO CX C/ 200`) não casam → o item vira
  "fora do catálogo" e some se você filtrar "Status no catálogo = Ativos"
  (a Anatomia avisa quanto foi escondido). Cobertura ~99 %. Se virar problema,
  casar por `Código` em vez de descrição.
- Lojas que aparecem na perda mas não no faturamento (ex.: 12, DEP) são listadas
  no Painel e ficam fora do cálculo de %.
- `_vclass` (cross cadastro × catálogo) é cacheado por **conjunto de motivos**;
  Painel/Evitável/Regras usam `("vencido",)`; a Anatomia troca via
  `_vclass_recorte(cats)` e mostra o bloco "Todos os motivos" com
  `_cats_do_escopo("todos")`.
- Tema: `.streamlit/config.toml` (financial-dashboard, dark, sem toggle).
- `core.py` = carga + cálculo (funções puras). `app.py` = 5 telas via
  `st.navigation` + `build_context()` (sidebar + cargas + `CTX`). O `st.title()`
  de cada tela é igual ao rótulo do menu; a pergunta que a tela responde fica na
  legenda logo abaixo.
- Histórico e pendências detalhados em `PENDENCIAS.md`.
