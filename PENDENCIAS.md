# Pendências e histórico — Monitor de Perdas

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — "Fontes de dados" oculto)

Gabriel perguntou se o expander **"Fontes de dados"** (uploaders manuais na
barra lateral) ainda tinha necessidade, já que o app auto-detecta os 5
arquivos pela pasta. Decisão: manter a funcionalidade (fallback útil pra
testar um relatório pontual sem mover pra pasta), mas **ocultar** da UI —
mesmo tratamento dado a Motivos/Evitável/Regras. `app.py`: nova constante
`MOSTRAR_FONTES_DADOS = False` no topo; o bloco dos 5 `st.file_uploader`
só roda se `True` (os `up_*` viram `None` quando oculto — o resto do código
já testava `is not None`, nada mais mudou). Reativa voltando a constante
pra `True`.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — limpeza do Painel)

Removido o expander **"Bater com o número da reunião"** do rodapé do
Painel — campo pra digitar um valor/% apresentado numa reunião e ver a
diferença contra o dado da ferramenta. Era uma muleta da fase inicial
(quando a taxa da ferramenta divergia do Power BI e precisava provar/
comparar número a número); hoje o "Bridge de escopo" já mostra os 3
recortes lado a lado, então virou redundante. A pedido do Gabriel.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — números em pt-BR em tabelas e gráficos)

Gabriel pediu pra revisar **todos** os números de venda/perda em tabelas e
gráficos e formatar em pt-BR (milhar com ponto, decimal com vírgula).
Achado: várias tabelas usavam `st.column_config.NumberColumn(format="R$
%.0f")` (Python `%`-format — sem separador de milhar nenhum, ex. "R$
388455") e quase todos os gráficos usavam `alt.Tooltip(..., format=",.0f")`
(d3-format americano — vírgula como milhar, ex. "388,455") tanto nas
tooltips quanto nos rótulos de valor em cima das barras (`mark_text`). O
texto do "Diagnóstico" no Painel também tinha `.2f` cru (`0.67%` em vez de
`0,67%`).

**Correção sistemática** (`app.py` + `core.py`):
- `PTNUM(v, d=0)` novo — formatador pt-BR genérico (milhar `.`, decimal
  `,`), usa `str.translate` pra trocar os separadores de uma vez só (evita
  o bug clássico de `.replace()` em cadeia embaralhar milhar com decimal).
- `_fmtcol(df, col, fmt)` novo — cria `<col>_fmt` (string já em pt-BR) num
  dataframe e devolve o nome da coluna, pra usar em `Tooltip`/`Text` do
  Altair como campo **Nominal** (`:N`) em vez de `Quantitative` com
  `format=`. O Vega-Lite não tem como trocar milhar/decimal por um format
  string (isso exigiria configurar um *locale* D3 no embed, que o
  `st.altair_chart` não expõe) — pré-formatar a string em Python e tratar
  como texto é o jeito confiável, já usado desde a sessão de 09-11 na
  tabela "Todos os motivos".
- Todas as tabelas (`NumberColumn` → coluna já formatada + `column_config`
  só com o rótulo) e todos os gráficos (tooltip + rótulo em cima da barra)
  do Painel, Anatomia, Itens a vencer e das telas ocultas (Motivos,
  Evitável, Regras) passaram por essa troca.
- `core.frase_diagnostico`: os `.2f` da taxa/meta agora trocam `.`→`,`.
- **Achado no caminho:** 2 gráficos tinham a *mesma* string de título no
  eixo (`title="R$"`) e na tooltip customizada — title duplicado colide na
  descrição de acessibilidade do Vega-Lite (não afeta o hover visual, mas
  por clareza os títulos da tooltip viraram "R$ perda"/"R$ no mês").

**Limitação conhecida, avisada ao Gabriel:** os **números dos eixos** dos
gráficos (as marcações de escala, tipo "20,000" no eixo X) continuam no
padrão americano — trocar isso exigiria configurar um *locale* D3 global no
Vega, que o `st.altair_chart` do Streamlit não expõe hoje. Só os valores
que aparecem em tabelas, tooltips (ao passar o mouse) e rótulos em cima das
barras foram corrigidos — que é o que normalmente se lê.

Verificado no app rodando (Chrome, via árvore de acessibilidade dos
gráficos): tooltips mostram "taxa %: 1,23", "perda: R$ 36.066", "R$ perda:
388.455", etc. — todos com separador pt-BR correto. `streamlit.testing`
smoke test: 0 exceções.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — bug de alinhamento na Anatomia)

Gabriel reparou que na "Anatomia da perda", bloco "Todos os motivos no
recorte", a ordem das barras do gráfico não batia com a ordem da tabela ao
lado (tabela: maior R$ primeiro; gráfico: alfabético). Causa: `y=alt.Y(...,
sort="-x")` em duas camadas (`ch_m` + `lbl_m`, barra e rótulo de valor)
construídas como dois `alt.Chart(gmot)` **independentes** — `sort="-x"` não
fica estável entre camadas independentes nesse caso (mesma classe de bug já
resolvida antes no gráfico "Por urgência" do Itens a vencer, ali com uma
lista explícita `core.ORDEM_URGENCIA`). Corrigido do mesmo jeito: `ordem_mot
= gmot["motivo_label"].tolist()` (já vem ordenado por valor) passado como
`sort=ordem_mot` nas duas camadas. Testado no browser: gráfico agora segue
a mesma ordem decrescente da tabela. Os outros 3 gráficos da Anatomia
(categoria/curva/tempo) não tinham esse bug — usam um `base` compartilhado
entre a camada de barra e a de rótulo, em vez de dois `Chart(...)`
separados.

## CONCLUÍDO NESTA SESSÃO (2026-09-12, continuação — terminologia sem viés)

Gabriel notou que "Perda real" (no seletor "Escopo da perda") dá a entender
que os outros escopos não são reais — viés de linguagem, bem na contramão do
que a mudança do item 2 (perda = todos os motivos) queria resolver. Pediu
sugestão neutra.

Termos trocados em **todo o app** (não só o seletor do Painel — a Anatomia
tinha o mesmo seletor, e o gráfico "Top motivos" a mesma classificação):
- **"Perda real"** → **"Perda direta"** (vencido + danificado + furto +
  descontinuado + outros — sai do estoque sem nenhuma compensação).
- **"Outra perda real"** → **"Outra perda direta"** e **"Não é perda"** →
  **"Baixa comercial"** (`core.CLASSES_PERDA`/`_CLASSE_MOTIVO`, usados no
  gráfico "Top motivos" do Painel e na tela Motivos oculta) — descreve o que
  é (tem contrapartida comercial: marketing/reembolso/consumo/doação) em vez
  de negar que seja perda.
- `core.ESCOPOS["perda_real"]` e todo texto de ajuda/rótulo correspondente
  em `app.py` (Painel, Anatomia, Bridge de escopo) e no `README.md`
  atualizados junto. A chave interna `"perda_real"`/`IS_PERDA_REAL` no código
  não mudou (só o texto visível ao usuário).

Verificado no app rodando: seletor do Painel, Bridge de escopo, legenda "Top
motivos" e seletor "Motivos" da Anatomia todos mostram os termos novos.

## CONCLUÍDO NESTA SESSÃO (2026-09-12)

Lista de 5 pedidos do Gabriel, resolvidos um a um (a lista virou seção
"PENDENTE" abaixo pro que ainda falta — item 5).

**1. Itens a vencer — faixas de urgência viraram cumulativas.** `core.py`:
`_faixa_urgencia`/`ORDEM_URGENCIA` trocaram os baldes exclusivos antigos
(Até 30 / 31-60 / 61-90 / 91-180 / Mais de 180 dias) pelos novos, pedidos
pelo Gabriel: **Até 30 dias / Até 90 dias / Até 180 dias / Até 12 meses /
Mais de 12 meses** (+ Sem data). `app.py`: KPI "Vence em até 90 dias"
ajustado pra somar os baldes novos.

**2. Painel — perda passa a somar todos os motivos por padrão, com filtro.**
Gabriel formalizou o entendimento: **perda = toda baixa do sistema**,
independente do motivo (marketing, reembolso, consumo, doação também contam
— não só vencido/danificado/furto/descontinuado) — mas ele ainda precisa
enxergar os motivos individualmente pra achar gargalos (por isso a "Bridge
de escopo" e "Top motivos" continuam na tela). `ESCOPO_PADRAO` (`app.py`)
virou `"todos"` (era `"vencido"`). `tela_veredito` ganhou de volta um
seletor **"Escopo da perda"** (segmented control: Vencido / Perda real /
Todos os motivos, default Todos os motivos) — a taxa do topo, o gráfico de
evolução e o ranking de lojas recalculam com o escopo escolhido. Testado no
browser: Todos os motivos → 0,66% (R$ 463.227); Vencido → 0,53%
(R$ 368.815, bate com o número de antes da mudança).

**3. Removido o texto "A perda é aceitável? · escopo: ... · recorte
global: ... · fonte ..."** do topo do Painel (poluía ao lado do novo
seletor de escopo).

**4. Menu "Motivos" ocultado.** Gabriel pediu pra não mexer nele por
enquanto (a tela ainda existe no código, comentada em `st.navigation`,
igual Evitável/Regras). Menu agora tem só 3 itens: Painel · Anatomia da
perda · Itens a vencer. Docstring do topo do `app.py` atualizada.

**5. Anatomia — clicar numa 2ª barra do mesmo gráfico agora substitui a
1ª (em vez de somar).** Gabriel confirmou o cenário exato: dentro do MESMO
gráfico (ex. Categoria), clicar em GENÉRICOS depois PROPAGADO deixava os
dois somados na tabela — só resetava clicando "Limpar filtros". Causa:
`alt.selection_point(..., toggle="true")` nos 3 gráficos força todo clique
a ser aditivo (multi-seleção), mesmo sem Shift. Corrigido: `toggle="true"`
removido dos 3 (`sel_cat`/`sel_cv`/`sel_g`) — volta ao padrão do Vega-Lite
(clique normal **substitui** a seleção; Shift+clique estende pra
multi-seleção quem quiser). Efeito colateral aceito: clicar 2x na mesma
barra não "solta" mais sozinho — usa o botão "Limpar filtros dos gráficos"
pra isso (Gabriel topou essa troca). Testado no browser: clicar PROPAGADO →
tabela "Categoria: PROPAGADO"; clicar GENÉRICOS em seguida → tabela vira
"Categoria: GENÉRICOS" (não mais "PROPAGADO, GENÉRICOS").

## CONCLUÍDO NESTA SESSÃO (2026-09-11, continuação)

### Correção: "Itens a vencer" usava a coluna errada para o valor exposto
Gabriel explicou os 4 campos do relatório do ERP (que a tela tratava como se
`Estoque Atual` fosse o "estoque pré-vencido"):
- **Quantidade Inicial** (`qtd_inicial`) — quantidade lançada no lote pré-vencido.
- **Qtd. Movimentada** (`qtd_movimentada`) — quantidade já vendida *dentro* desse
  pré-vencido.
- **Saldo** (`saldo`) = Quantidade Inicial − Qtd. Movimentada — o que **ainda
  resta** daquele lote pré-vencido. **É isso que expõe risco de perda.**
- **Estoque Atual** (`estoque_atual`) — estoque **geral** da loja pro produto,
  **não** restrito a esse lote (pode incluir outros lotes normais, ou não
  refletir ainda a baixa do pré-vencido) — só referência.

O código usava `estoque_atual` (clipado ≥0) como base de `valor_exposto`. Nos
dados reais, `saldo` ≠ `estoque_atual` em **2.648 das 4.249 linhas (62%)** —
em alguns casos o estoque geral é maior (mistura outros lotes), em outros é
menor (a baixa do pré-vencido ainda não bateu no estoque geral). Corrigido:
`core.enriquecer_a_vencer` agora usa `saldo` (com fallback pra `estoque_atual`
só se o relatório não trouxer a coluna Saldo — com aviso na tela). `core.py`:
`_AVENCER_MAP` ganhou `qtd_inicial`/`qtd_movimentada`/`saldo`. `app.py`: tabela
da tela mostra **Saldo (pré-vencido)** e **Estoque atual (geral)** lado a lado;
caption do topo trocou "Estoque atual" por "Saldo do pré-vencido".

**Efeito real medido:** total de estoque exposto caiu de **R$ 396.050**
(errado, base `estoque_atual`) para **R$ 277.439** (correto, base `saldo`) —
o número antigo superestimava o risco ao contar estoque de outros lotes como
se fosse tudo pré-vencido. Por urgência (novo): ≤30d R$ 57.671 · 31-60d
R$ 81.662 · 61-90d R$ 63.760 · 91-180d R$ 56.681 · >180d R$ 17.666.

## CONCLUÍDO NESTA SESSÃO (2026-09-11)

Lista de mudanças pedida pelo Gabriel, feita em lote (commit `22414b1` + o
commit do "Itens a vencer" logo abaixo).

**Simplificação geral.** Barra lateral perdeu as seções "Filtros" (Lojas/
Período globais) e "Parâmetros" (Escopo/Meta/DEP) — viraram constantes fixas
no topo do `app.py` (`ESCOPO_PADRAO = "vencido"`, `META_PADRAO = 0.004`,
`incluir_dep = False`). Cada tela mantém seu filtro local de loja/mês
(`_loja_local`/`_mes_local`), só o filtro *global* saiu. `st.navigation` perdeu
"Evitável x estrutural" e "Regras e simulação" do menu (funções continuam no
arquivo, comentadas na lista — reativa descomentando 2 linhas).

**Anatomia da perda — 3 simplificações:**
- Removido o filtro **"Status no catálogo"** (Ativos/Inativos/Fora do
  catálogo) que ficava no topo — junto com o aviso de "quanto foi escondido".
- Removido o seletor **Curva de valor / Curva de quantidade** — agora só
  existe curva de quantidade (era o que o Gabriel queria acompanhar). Gráfico
  "Curva" (que mostrava A…I) virou **2 barras**: `_grupo_giro()` classifica
  A–H = "Com giro", I = "Sem giro" (+ "Sem cadastro"). Coluna "Curva valor"
  saiu da tabela de produtos.
- Gráfico "Quanto tempo parado quando venceu" → renomeado **"Tempo da última
  venda"**; `_grupo_tempo()` simplifica os 7 baldes antigos (`core.FAIXAS_GIRO`)
  em 3: **Até 90 dias / Até 180 dias / Acima de 180 dias** (+ "Sem cadastro").
  A interatividade clique-no-gráfico-filtra-tabela (já existia pros 3 gráficos)
  foi migrada pros novos campos (`giro_grupo`, `tempo_grupo`).

**Tabela "Todos os motivos no recorte":** coluna **"No escopo"** removida (o
gráfico ao lado ainda colore por dentro/fora do escopo, só a coluna da tabela
saiu). Números formatados em pt-BR de verdade (`BRLc()`/`NUM()` novos no
`app.py` — milhar com ponto, decimal com vírgula) em vez do `NumberColumn`
padrão do Streamlit (que não tem separador de milhar).

**Textos removidos** entre gráficos/tabelas na Anatomia (o "clique numa barra
pra filtrar", o "ignora o filtro de escopo/status", o "as lojas são número...",
o "uma linha por produto e motivo...") — quando a informação valia a pena,
virou `help=` (tooltip) de um metric em vez de texto solto na tela.

**Bug corrigido:** "Gap vs meta" mostrava `+0,13 p,p,` (a troca de separador
`.`→`,` também comia a abreviação "p.p."). Agora troca só o número.

### Itens a vencer — nova tela, com dado real
O Gabriel mandou `itens a vencer out26.xlsx` (relatório do ERP: estoque atual
com lote e validade, por loja — 4.249 linhas, 23 lojas, `Status` sempre
"Ativo", `Dias até vencimento` de 20 a 1538). Copiado pra
`PERDAS\itens a vencer.xlsx` (fora do git, como os outros dados).

`core.py`: `load_itens_a_vencer(source)` (mapa de colunas `_AVENCER_MAP`, só
`Status = Ativo`) + `enriquecer_a_vencer(av, cad)` (merge por loja+produto só
pra trazer `custo_medio`; `valor_exposto = estoque_atual.clip(0) × custo_medio`;
`macro` via `macro_categoria(classif)` reaproveitado; `urgencia` em 5 faixas —
`ORDEM_URGENCIA` = Até 30 / 31-60 / 61-90 / 91-180 / Mais de 180 dias / Sem
data). `app.py`: `_a_vencer` cache + auto-detect (`itens*a*vencer*.xls*`) +
uploader; `tela_itens_a_vencer()` substituiu o placeholder — KPIs (valor
exposto total, ≤30d, ≤90d, unidades), gráfico por urgência, gráfico por loja,
tabela (produto/lote/estoque/dias/validade/curva/categoria) + CSV.

Números (23 lojas, cadastro casou 98,3%): **R$ 396.050 de estoque exposto**,
R$ 83.985 vence em ≤30 dias, R$ 284.477 em ≤90 dias. Medicamento R$ 195.243 /
não-medicamento R$ 200.806 (bem mais equilibrado que o vencido histórico —
faz sentido, isso é o mix de estoque, não o mix do que já foi perdido). Loja
com mais valor exposto: **13** (diferente do ranking histórico de vencido,
onde 20 lidera) — vale olhar se é fruto de uma compra/transferência recente
que ainda dá tempo de agir.

## PENDENTE

### 1. Faturamento de setembro/2026 — ÚNICA PENDÊNCIA ABERTA
`faturamento.csv` vai até **2026-08**. Setembro ainda não fechou (dado de perda
também é parcial). Quando fechar: pegar no Power BI *Visão geral - mês*, mês = set,
a coluna **Receita** por **Und. ID** (22 lojas: 2–11, 13–20, 22–25; não há 12 nem 21),
e acrescentar as linhas `loja,2026-09,valor` no `faturamento.csv`.
Conferir sempre: soma das 22 lojas = Total exibido no rodapé do relatório.
Agora dá para puxar isso pela extensão do Chrome (ver item 2).

---

## CONCLUÍDO NESTA SESSÃO (2026-09-10)

### 0. Reestruturação combinada com o Gabriel — ✅ CONCLUÍDA (a–d)
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
catálogo". A `BASE CADASTRO COM EAN.xlsx` **não** entrou (perda não tem EAN).
Os 2 xlsx saíram do versionamento (`.gitignore`, dados sensíveis).

Efeito real medido (vencido jan–set): "sem classificação" R$ 22.039 → **R$ 4.174**
(residual "fora do catálogo"); os R$ 17.865 / 299 SKUs classificados foram para
medicamento (219.827 → **231.003**) e não-medicamento (146.589 → **153.278**).
Vencido de itens `Status = Inativo`: ~R$ 2,8 mil. Isso **fecha** a dúvida antiga
"os R$ 22 mil sem classificação" (commit `46d77bf`).

### Ajustes de leitura da Anatomia (feedback do Gabriel, commit `c5ecc70`)
Cartão **"Total — <motivo>"** na linha de KPIs. Gráfico "Tem curva?" → **"Curva"**,
estratificado por letra **A…I**. **Rótulo de valor em cada barra** dos 3 gráficos.
Coluna "R$" da tabela → "Total perda (R$)".

### Filtro clique-nos-gráficos da Anatomia — ✅ verificado no browser
Era a dúvida "não está voltando". `selection_point(toggle="true")` (re-clique na
mesma barra solta) + botão "Limpar filtros dos gráficos" (reset via nonce nas
`key` dos charts). Testado no Chrome: OK.

### 2. Extensão Claude no Chrome — ✅ CONECTOU (2026-09-10, mais tarde)
Voltou a conectar ("Browser 1", Windows local). Verificado no app rodando:
Painel, Motivos e Anatomia renderizam certo (cartão Total R$ 388.455, gráfico
"Curva" A–I, rótulos nas barras, tabela "Total perda (R$)"). Observação: o
`Page.captureScreenshot` dá timeout às vezes — o renderizador do Streamlit é
pesado (dataframes grandes + Altair em camadas); espera + repete resolve.
Agora dá para puxar dados do Power BI pela extensão em vez de print manual.

---

## FEITO NESTA SESSÃO (2026-09-10)

### Commit `85fd382` — Títulos = menu; Anatomia sempre com todos os motivos
- **Títulos:** `st.title()` de cada tela passa a ser igual ao rótulo do menu
  (Painel / Motivos / Anatomia da perda / Evitável x estrutural / Regras e
  simulação). A "pergunta" antiga virou início da legenda.
- **Anatomia:** escopo "Motivos" abre em **Todos** (era Vencido). Bloco fixo
  **"Todos os motivos no recorte"** (não é mais expander) — tabela + barra do
  conjunto completo de motivos da loja/mês, **ignorando** o filtro de
  escopo/status. Coluna/cor "No escopo" marca o que entra na análise abaixo.
  Uma linha grande (ex. marketing R$ 10,5 mil) nunca some, mesmo analisando só
  vencido. `vfull = _vclass_recorte(_cats_do_escopo("todos"))`.

### Commit `f30429b` — Anatomia: motivo flexível + "ver tudo" (feedback do Gabriel)
Gabriel comparou o relatório do sistema (loja 16, ago, AÇÃO DE MARKETING → item
LANCETA ACCU CHECK R$ 10.029,36) e não achou o item na Anatomia. Causa: o filtro
**"Status no catálogo = Ativos"** escondia silenciosamente a linha — o produto
`LANCETA ACCU CHECK SAFE-T-PRO UNO CX C/ 200` **não casa** com o catálogo (que
tem `... UNO`, sem o `CX C/ 200`), então caiu em "fora do catálogo".
- Seletor de motivo: segmented **Vencido / Perda real / Todos** + multiselect
  **"…ou motivos específicos"** que sobrepõe. (`_cats_do_escopo`; `MOTIVO_OPCOES`
  saiu.)
- Novo expander **"Motivos no recorte"** — tabela R$/unid/linhas/produtos/% +
  barra por motivo.
- Tabela de produtos agrupa por **(produto, motivo)**, ganha coluna **Motivo**;
  head 300→500; CSV baixa tudo.
- **Avisos de linha escondida:** warning quando "Status no catálogo" ≠ Todos
  esconde R$; caption do R$ fora do filtro dos gráficos.
- **Fragilidade conhecida:** o join catálogo↔perda é por descrição exata
  normalizada; variações de embalagem no nome ("... UNO" vs "... UNO CX C/ 200")
  não casam → item vira "fora do catálogo". Cobertura ~99 %, mas linhas grandes
  podem cair fora. Se virar problema, casar por `Código` em vez de descrição.

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
- (O clique-para-filtrar da Anatomia foi ajustado depois com `toggle="true"` +
  botão de limpar, e verificado no browser — ver seção CONCLUÍDO acima.)

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

## Estado do app (fim da sessão 2026-09-10)
- **5 telas** via `st.navigation`, `st.title` = rótulo do menu: Painel · Motivos ·
  Anatomia da perda · Evitável x estrutural · Regras e simulação.
- **Filtros:** global na sidebar (Lojas + Período) + `Meses/Lojas (nesta tela)`
  em todas as telas. Parâmetros: Escopo, Meta (default 0,40 %), Incluir DEP.
- **Anatomia:** abre em "Todos os motivos"; bloco fixo "Todos os motivos no
  recorte" mostra a foto completa da loja/mês sempre; tabela é 1 linha por
  produto × motivo. Join catálogo por descrição exata — item com nome de
  embalagem diferente cai em "fora do catálogo".
- **Entradas:** `perdas*.xls` (obrigatório) · `DADOS*.xlsx` (cadastro por loja) ·
  `BASE CADASTRO COM GRUPOS.xlsx` (catálogo, só enriquece) · `faturamento.csv`
  (jan–ago/2026). Os 4 auto-detectados na pasta; todos com uploader na sidebar.
  `BASE CADASTRO COM EAN.xlsx` não é usada. Os 2 xlsx de catálogo estão fora do
  git (`.gitignore`).
- Roda em `http://localhost:8501` (headless, `--server.fileWatcherType none` →
  mudança de código só entra com restart do servidor).
- Comando: `streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none`
- Python: `C:\Users\E.C Velanes\AppData\Local\Programs\Python\Python314\python.exe`
- Doc de uso e visão geral: `README.md`.
