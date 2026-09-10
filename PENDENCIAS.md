# Pendências e histórico — Monitor de Perdas

## PENDENTE

### 0. Reestruturação combinada com o Gabriel (2026-09-10) — ✅ CONCLUÍDA (a–d)
O Gabriel pediu para documentar e continuar depois. Sequência acordada (proposta
minha, ele topou a direção geral; encadear na ordem, commit a cada etapa).
Todos os quatro itens feitos nesta sessão + rodada de ajustes de filtro/tela.

**a) Filtros globais na barra lateral.** ✅ FEITO — commit `57f2dec`. Loja +
Período viraram dois multiselect no `build_context` (vazio = tudo), aplicados em
`perdas`/`fat` antes dos derivados e no resultado do cache `_vclass`. `CTX` expõe
`lojas_sel` / `meses_sel` / `perdas_full`. `tela_motivos` e `tela_anatomia`
perderam os multiselect locais; todas as telas mostram "Recorte (filtro global)".

**b) Veredito → "Painel".** ✅ FEITO — commit `55eb5d6`. `st.Page` renomeado.
Topo com 4 KPIs (faturamento no período · perda no escopo · taxa ponderada · gap
vs meta em p.p.). Diagnóstico (semáforo + frase) mantido. Evolução mensal ao lado
de ranking de lojas por taxa (barras no semáforo + régua da meta). Bridge de
escopo + top motivos reaproveitados da tela Motivos. "Bater com o número da
reunião" foi para um expander. Helpers novos: `CLASSE_COR`, `_cor_taxa`.

**c) Anatomia com seletor de motivo.** ✅ FEITO — commit `3c38334`. `_vclass`
recebe `cats` e cacheia por conjunto de motivos; `build_context` passa
`("vencido",)` p/ o `CTX["vclass"]` e expõe `psig`/`csig`. Helper
`_vclass_recorte(cats)` roda o cache com outro conjunto e reaplica o recorte
global. `tela_anatomia` tem selectbox "Motivo da baixa" (Vencido / Danificado /
Furto / Descontinuado / Perda real / Todos os motivos).

**d) Integrar o catálogo (BASE CADASTRO COM GRUPOS).** ✅ FEITO — commit `9268722`.
`core.load_catalogo` (nível produto, chave = Descrição normalizada);
`enriquecer_vencidos(catalogo=)` coalesce `classif` / `curva_valor` / `curva_qtd`
após o merge do DADOS (DADOS tem prioridade; `sem_cadastro` fixado antes).
`_vclass` recebe `cat_sig` + `_cat_df`. Anatomia ganhou radio "Status no
catálogo" (Todos / Ativos / Inativos / Fora do catálogo) e coluna "Status
catálogo". A `BASE CADASTRO COM EAN.xlsx` **não** entrou (perda não tem EAP).
Os 2 xlsx saíram do versionamento (`.gitignore`, dados sensíveis).

Efeito real medido (vencido jan–set): "sem classificação" R$ 22.039 → **R$ 4.174**
(residual "fora do catálogo"); os R$ 17.865 / 299 SKUs classificados foram para
medicamento (219.827 → **231.003**) e não-medicamento (146.589 → **153.278**).
Vencido de itens `Status = Inativo`: ~R$ 2,8 mil.

### 1. Faturamento de setembro/2026
`faturamento.csv` vai até **2026-08**. Setembro ainda não fechou (dado de perda
também é parcial). Quando fechar: pegar no Power BI *Visão geral - mês*, mês = set,
a coluna **Receita** por **Und. ID** (22 lojas: 2–11, 13–20, 22–25; não há 12 nem 21),
e acrescentar as linhas `loja,2026-09,valor` no `faturamento.csv`.
Conferir sempre: soma das 22 lojas = Total exibido no rodapé do relatório.

### 2. Extensão Claude no Chrome — ✅ CONECTOU (2026-09-10, mais tarde)
Voltou a conectar ("Browser 1", Windows local). Verificado no app rodando:
Painel, Motivos e Anatomia renderizam certo (cartão Total R$ 388.455, gráfico
"Curva" A–I, rótulos nas barras, tabela "Total perda (R$)"). Observação: o
`Page.captureScreenshot` dá timeout às vezes — o renderizador do Streamlit é
pesado (dataframes grandes + Altair em camadas); espera + repete resolve.
Agora dá para puxar dados do Power BI pela extensão em vez de print manual.

---

## FEITO NESTA SESSÃO (2026-09-10)

### Commit `c5ecc70` — Anatomia: ajustes de leitura (feedback do Gabriel)
Cartão **"Total — <motivo>"** na linha de KPIs (R$ + unidades + linhas). Gráfico
"Tem curva?" → **"Curva"**, estratificado por letra **A…I** (+ "Sem cadastro")
em vez dos baldes A–D/E–G/H–I (`_cletra`/`ORD_LETRA` no lugar de `_cg`/`ORD_CURVA`;
filtro da tabela usa `cletra`). **Rótulo de valor em cada barra** dos 3 gráficos
(categoria, curva, tempo parado) via camada `mark_text`. Coluna "R$" da tabela →
"Total perda (R$)".

### Commit `9268722` — Catálogo BASE CADASTRO COM GRUPOS na Anatomia (item 0d)
`core.load_catalogo(sources)` lê a BASE CADASTRO COM GRUPOS (nível produto, sem
loja), chave = `Descrição` normalizada (`_norm_produto` = `_ascii`), dedup por
produto (Ativo vence Inativo), cache parquet próprio (`_cache_path(..., "catalogo")`).
`enriquecer_vencidos(..., catalogo=None)`: após o merge `(loja, produto)` com o
DADOS, merge extra por descrição normalizada + `_coalesce` de `classif` /
`curva_valor` / `curva_qtd` (DADOS tem prioridade). `sem_cadastro` continua sinal
do DADOS (fixado antes do coalesce). Novo `status_cadastro`. `_vclass` recebe
`cat_sig` + `_cat_df`; `CTX` expõe `catalogo`/`catsig`. `_catalogo` cache +
auto-find `*GRUPOS*.xlsx` + uploader. Anatomia: radio "Status no catálogo" +
coluna "Status catálogo". `BASE CADASTRO COM EAN.xlsx` não usado. Os 2 xlsx
saíram do versionamento (`.gitignore`).

### Commit `3c38334` — Anatomia com seletor de motivo (item 0c)
`_vclass(perdas_sig, cad_sig, cats, _perdas, _cad)` — `cats` entra na chave do
cache. `build_context` chama com `("vencido",)` p/ o `CTX["vclass"]` (Painel /
Evitável / Regras seguem só-vencido) e devolve `psig`/`csig`. Módulo:
`MOTIVO_OPCOES` (6 opções) + `_vclass_recorte(cats)` que roda o cache e reaplica
loja/mês do filtro global. `tela_anatomia`: selectbox "Motivo da baixa" ao lado
de mês/loja; Vencido reusa o CTX, os demais recalculam. Números: Vencido
219.827 / 146.589 / 22.039 · Perda real 224.232 / 162.558 / 23.367 · Todos
235.839 / 219.156 / 34.616 (medicamento / não-medic. / sem classificação).

### Commit `da48837` — Filtro de mês na tela em todas as telas
Helper `_mes_local(df, key, container=)` espelhando `_loja_local` (some quando o
recorte já tem ≤ 1 mês). **Evitável x estrutural** e **Regras e simulação**
ganham mês + loja na tela (antes: só loja / nada); `n_meses` recalculado do
recorte local. **Motivos** ganha "Meses (nesta tela)". **Painel** e **Anatomia**
passam a usar o helper. Agora todas as 5 telas têm mês + loja na própria tela,
além do filtro global da barra lateral.

### Commit `7fb754d` — Painel com filtro de mês/loja na tela
Feedback do Gabriel: o Painel também precisa de filtro e informações no recorte.
- Multiselect **"Meses (nesta tela)"** e **"Lojas (nesta tela)"** no topo do
  Painel (dentro do recorte global). `taxa_lm` / `mensal` / `cobertura` / `vclass`
  passam a ser recalculados a partir do recorte da tela — os 4 KPIs, o ranking de
  lojas, o bridge de escopo e o bloco "meses sem faturamento" respondem aos
  filtros. Conferido: mês = 2026-08 → fat 8.637.085 · perda 52.576 · taxa 0,61 % ·
  bridge 52.576 / 56.588 / 83.265 (bate com a decomposição de agosto abaixo).

### Commits `82fb613` + `e770596` — Seletores por tela + revisão da Anatomia
Feedback do Gabriel: além do filtro global, quer seletor de loja/mês nas telas.
- `82fb613`: helper `_loja_local(df, key)` — multiselect "Lojas (nesta tela)" em
  Motivos, Anatomia e Evitável x estrutural, restringe dentro do recorte global;
  some quando o recorte já tem ≤ 1 loja.
- `e770596` (Anatomia): filtro de **Meses (nesta tela)** ao lado do de Lojas
  (`_loja_local` aceita `container=`). Radios **Medida** (R$/Unidades) e **Curva**
  (Valor/Qtd) movidos para dentro dos containers dos gráficos. Cliques nos
  gráficos com `selection_point(toggle="true")` (re-clique solta) + botão
  **"Limpar filtros dos gráficos"** que reseta via nonce nas `key` dos charts.
  "Sem classificação" com rótulo próprio + aviso + opção "Só sem classificação"
  no seletor *Ver*. Tabela: coluna `lojas` (nunique) virou **Nº lojas** +
  **Lojas (ID)** (lista dos números); `itens` → "Unidades vencidas". Não há nome
  de loja no relatório de perdas, só número (2–25).
- **A verificar com o Gabriel no app:** o clique-para-filtrar da Anatomia (se o
  problema era "não limpa", o `toggle="true"` resolve; se era "não filtra nada",
  precisa de teste no navegador — a extensão Chrome não conecta nesta máquina).

### Commit `55eb5d6` — Veredito vira "Painel" (item 0b)
- `st.Page` renomeado Veredito → **Painel**. Topo com 4 KPIs: Faturamento no
  período · Perda no período (escopo) · Taxa ponderada (perda ÷ fat) · Gap vs
  meta em p.p. Diagnóstico (semáforo + frase) mantido; cai para
  `_cor_taxa(taxa_ponderada)` quando falta cadastro.
- Evolução mensal (taxa × meta) ao lado de **ranking de lojas por taxa** (barras
  no semáforo + régua da meta, vindo de `CTX["taxa_lm"]`).
- **Bridge de escopo** (vencido / perda real / todos — R$/mês + % fat) e **top
  motivos** (barra colorida por classe) reaproveitados da tela Motivos.
- "Meses sem faturamento" mantido; "Bater com o número da reunião" foi p/ um
  expander no rodapé. Helpers novos no topo: `CLASSE_COR`, `_cor_taxa(taxa, meta)`
  (mesma régua de `core.frase_diagnostico`); `CLASSE_COR` duplicado saiu de Motivos.
- Conferência sem filtro: fat R$ 69,69 M · taxa 0,53 % · bridge 0,55 / 0,58 /
  0,69 % — bate com a tabela do faturamento mensal.

### Commit `57f2dec` — Filtros globais de Loja e Período (item 0a)
- `build_context`: bloco "### Filtros" na sidebar com dois multiselect —
  **Lojas** e **Período (meses)**, vazio = tudo (`key="g_lojas"` / `"g_meses"`).
- O recorte é aplicado em `perdas`/`fat` **antes** dos derivados (`taxa_lm`,
  `mensal`, `cob`, `n_meses`) e no **resultado** do cache `_vclass` — o cross
  vencido×cadastro continua sendo calculado na base cheia (cache estável) e só
  depois filtrado por loja/mês.
- `CTX` agora expõe: `perdas` (já filtrado), `perdas_full` (base cheia, usada só
  pelo editor de faturamento), `fat` (filtrado), `lojas_sel`, `meses_sel`.
- `tela_motivos` e `tela_anatomia`: removidos os multiselect locais de Loja/Mês.
  `tela_motivos` ganhou guard para recorte sem lançamentos; `tela_baldes` e
  `tela_regras`, guard para `vclass` vazio.
- Helper `_recorte_txt()` + legenda "Recorte (filtro global): …" no topo das 5
  telas. Smoke test (`streamlit.testing`) nas 5 telas, com e sem filtro: 0 exc.

### Commit `45afa58` — Motivos c/ filtro de loja; Anatomia R$/unidades; meta 0,40%
- `tela_motivos`: multiselect de **Lojas** (vazio = todas), ao lado de Meses;
  filtra `perdas` e `fat` juntos p/ o % não distorcer.
- `tela_anatomia`: novo radio **"Medida dos gráficos"** (R$ vencido / Unidades)
  que rege o eixo x dos 3 gráficos; tooltip de todos passa a mostrar R$ **e**
  unidades sempre. Groupby dos 3 agora agrega `valor_total` **e** `itens`.
- **Meta de perdas: default do slider 0,50% → 0,40%** (definição do Gabriel,
  `app.py` `build_context`). É a meta oficial agora.

### Commit `46d77bf` — Anatomia: loja, curva e gráficos clicáveis
- `core.macro_categoria()` simplificada pela regra do Gabriel: no nível 1 da
  árvore, só GENÉRICO / SIMILAR / PROPAGADO é `medicamento`; qualquer outra
  categoria é `nao-medicamento`; sem categoria é `sem classificacao`. Sumiu o
  balde `indefinido` (CAMPANHA, HIGIENE PESSOAL/BUCAL, MUNDO HOMEM, PRIMEIROS
  SOCORROS caíram em não-medicamento). Efeito no vencido jan–set: medicamento
  R$ 219.827 · não-medicamento R$ 146.589 · sem classificação R$ 22.039.
  **A confirmar com o Gabriel:** os R$ 22 mil "sem classificação" são itens com
  `classif` em branco no cadastro — mantidos num balde à parte (não viraram
  não-medicamento). Se ele quiser, é 1 linha juntar.
- `tela_anatomia`: multiselect de **Lojas** (vazio = todas) ao lado de Meses;
  seletor de curva virou `st.radio` com `key` (o `segmented_control` não
  alternava) e agora rege o gráfico "Tem curva?"; os 3 gráficos (categoria /
  curva / tempo parado) viraram clicáveis via `alt.selection_point` +
  `st.altair_chart(on_select="rerun")` — clicar numa barra filtra a tabela de
  Produtos no rodapé, com título e legenda dizendo de qual gráfico e qual valor
  veio. Tabela ganhou coluna "Tempo parado" e download CSV.

### Commit `a787f5f` — tela "Motivos" (de-para de escopo)
Entregue conforme a spec que estava aqui. `core.py`: `classe_motivo(motivo_cat)`
+ `CLASSES_PERDA` (3 baldes: `Vencido` / `Outra perda real` / `Não é perda`,
coerente com `IS_PERDA_REAL` — só destaca o vencido). `app.py`: `tela_motivos()`,
2ª tela do `st.navigation` (ícone `category`).

- Filtro de meses (multiselect), default = meses com faturamento.
- 3 cartões de bridge de escopo (reusa `core.in_escopo`): Somente vencidos /
  Perda real / Todos os motivos — cada um com R$/mês + % do faturamento.
- Tabela por motivo: Motivo | Classe | R$ no período | R$/mês | % do faturamento
  | % do lançado | Linhas, ordenada por valor.
- Barra por motivo colorida pela classe + barra mensal empilhada por classe.
- % do faturamento usa só os meses da seleção que têm faturamento; meses sem
  faturamento entram no R$/mês e aparecem num aviso (`:material/info:`).
- Cálculo inline no `app.py` (não usa `core.perda_por_motivo`, que não entrega
  corte por mês nem % do faturamento).

Conferência jan–ago/2026 (todas as lojas, sem DEP): somente vencidos 0,55% ·
perda real 0,58% · todos os motivos 0,69% do faturamento acumulado. Para
reproduzir o 0,96% do BI de agosto, filtrar só `2026-08` no multiselect.

### Commit `5b681c3` — correções da revisão do app
- **`frase_diagnostico` (core.py):** agora usa a **meta do slider** para o semáforo
  (ok / atenção / crítico). Antes o parâmetro `meta` era ignorado e o nível vinha
  de uma faixa fixa 0,3–0,8%. Regra nova: `≤ meta+5%` → ok; `≤ meta+30%` → atenção;
  acima → crítico. A frase cita a meta **e** a faixa de mercado. Removido o
  parâmetro `escopo`, que não era usado.
- **Tela Veredito (app.py):** bloco novo "Meses sem faturamento informado" —
  gráfico de perda em R$ dos meses que têm baixa mas ainda não têm faturamento
  (jul+ sumiam sem aviso claro).
- **`load_perdas` (core.py):** cria `valor_unit` quando a coluna falta
  (evita `KeyError` em relatório sem coluna de valor unitário).
- **Editor de faturamento na sidebar:** `st.rerun()` ao salvar + aviso de que
  `faturamento.csv` na pasta **tem prioridade** sobre o valor digitado
  (era pegadinha: com o CSV presente, digitar/salvar não tinha efeito).
- **"Bater com o número da reunião":** protegida divisão por zero.
- **Limpeza:** removidos `BRLk` e a coluna `evitavel_pdv` (mortos).
- **`requirements.txt`:** `streamlit>=1.49` (era `>=1.40`; o app usa
  `container(horizontal=)`, `width="stretch"`, `metric(chart_data=)`).
- **`.gitignore`:** `_run.log`.

### `faturamento.csv` — reconstruído com valores MENSAIS reais (NÃO versionado)
Antes: jan–jun estavam **chapados pela média do trimestre** (T1/T2 do Power BI
"Visão geral - trimestre"). Agora: valor real de cada mês, **jan a ago/2026**,
fonte Power BI *Visão geral - mês* → Receita por Und. ID. Cada mês foi conferido
somando as 22 lojas contra o Total do relatório (maio fecha com 2 centavos de
diferença — arredondamento de leitura de print, irrelevante).

Taxa de perdas por mês (escopo "somente vencidos"), com o dado mensal real:

| Mês | Perda (vencidos) | Faturamento | Taxa |
|---|---:|---:|---:|
| 2026-01 | R$ 43.434 | R$ 8.830.034 | 0,49% |
| 2026-02 | R$ 43.533 | R$ 7.906.261 | 0,55% |
| 2026-03 | R$ 47.073 | R$ 8.903.328 | 0,53% |
| 2026-04 | R$ 45.320 | R$ 8.672.600 | 0,52% |
| 2026-05 | R$ 42.173 | R$ 8.890.939 | 0,47% |
| 2026-06 | R$ 44.716 | R$ 8.714.910 | 0,51% |
| 2026-07 | R$ 49.990 | R$ 9.139.575 | 0,55% |
| 2026-08 | R$ 52.576 | R$ 8.637.085 | 0,61% |

Média jan–ago: **0,53%**. Tendência de alta jun→jul→ago (0,51 → 0,55 → 0,61%).
Agosto é o pior mês da série.

### Por que a ferramenta mostra 0,61% e o Power BI mostra 0,96% (agosto)
Mesmo relatório, filtros diferentes. Decomposição de agosto (sem depósito):

| Motivo | Valor | % do fat | É perda? |
|---|---:|---:|:--:|
| Produto vencido | R$ 52.576 | 0,61% | sim |
| Ação de marketing | R$ 15.089 | 0,17% | não (troca/brinde) |
| Reembolso pelo fornecedor | R$ 6.529 | 0,08% | não (fornecedor paga de volta) |
| Doação / brinde | R$ 2.530 | 0,03% | não |
| Consumo da loja | R$ 1.945 | 0,02% | não |
| Danificado | R$ 1.755 | 0,02% | sim |
| Furto | R$ 1.653 | 0,02% | sim |
| Descontinuado | R$ 604 | 0,01% | sim |
| Devolução ao fornecedor | R$ 583 | 0,01% | não |
| **Todos os motivos** | **R$ 83.265** | **0,964% ≈ 0,96%** | |

- Somente vencidos: R$ 52.576 → **0,61%**
- Perda real (venc + danif + furto + descont): R$ 56.588 → 0,66%
- Todos os motivos: R$ 83.265 → **0,96%** (bate com o `%perda/fat` do Power BI)

O 0,96% do BI está inflado ~0,28 p.p. por marketing + reembolso + doação (~R$ 24 mil),
que não são perda. É essa separação que a tela "Motivos" (pendência 1) vai deixar
explícita. Hoje já dá para ver na barra lateral: **Parâmetros → Escopo →
"Todos os motivos"** faz a taxa de agosto virar 0,96%.

---

## Estado do app
- Roda em `http://localhost:8501` (headless, `--server.fileWatcherType none` →
  mudança de código só entra com restart do servidor).
- Comando: `streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none`
- Python: `C:\Users\E.C Velanes\AppData\Local\Programs\Python\Python314\python.exe`
