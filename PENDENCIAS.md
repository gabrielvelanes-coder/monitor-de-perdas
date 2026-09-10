# Pendências e histórico — Monitor de Perdas

## PENDENTE

### 1. Tela "Motivos" — decompor o que é o quê (PEDIDO, não feito)
Objetivo: uma tela nova que mostra **cada motivo de baixa de estoque**, quanto pesa
em R$ e em % do faturamento, e a **classe** (perda de verdade ou não). É o "de-para"
que explica por que a ferramenta mostra 0,61% e o Power BI mostra 0,96% (ago/2026).

Especificação combinada:

- **Filtro de meses** (multiselect), default = meses que têm faturamento.
- **3 cartões (bridge de escopo):**
  - Somente vencidos — só `PRODUTO VENCIDO`.
  - Perda real — vencido + danificado + furto + descontinuado + não classificado.
  - Todos os motivos — inclui marketing, consumo de loja, reembolso, doação, etc.
    (é o que reproduz o `%perda/fat` do Power BI).
  - Cada cartão: R$/mês + % do faturamento.
- **Tabela por motivo:** Motivo | Classe | R$ no período | R$/mês | % do faturamento |
  % do lançado | Linhas. Ordenada por valor.
- **Gráfico de barras** por motivo, colorido pela classe.
- **Gráfico por mês** empilhado por classe (mostra o salto de agosto).
- Classe em 3 baldes: `Vencido` / `Outra perda real` / `Não é perda`.
- Aviso quando a seleção inclui mês sem faturamento (entra no R$/mês, não na %).

Implementação sugerida:
- `core.py`: adicionar `classe_motivo(motivo_cat) -> str` e `CLASSES_PERDA`
  (lista ordenada), perto de `in_escopo`. Assim a regra "o que conta como o quê"
  fica num lugar só, junto de `CATS` / `ESCOPOS`.
- `app.py`: função `tela_motivos()` e registrar em `st.navigation` como 2ª tela
  (depois de Veredito, antes de Anatomia).
- `core.perda_por_motivo()` já existe e hoje está sem uso — pode servir de base,
  mas a tela precisa também de corte por mês e da coluna % do faturamento, que
  ela não entrega; provavelmente mais simples calcular inline no `app.py`.

Cores por classe: Vencido `#F87171`, Outra perda real `#FB923C`, Não é perda `#94A3B8`.

### 2. Faturamento de setembro/2026
`faturamento.csv` vai até **2026-08**. Setembro ainda não fechou (dado de perda
também é parcial). Quando fechar: pegar no Power BI *Visão geral - mês*, mês = set,
a coluna **Receita** por **Und. ID** (22 lojas: 2–11, 13–20, 22–25; não há 12 nem 21),
e acrescentar as linhas `loja,2026-09,valor` no `faturamento.csv`.
Conferir sempre: soma das 22 lojas = Total exibido no rodapé do relatório.

### 3. Extensão Claude no Chrome não conecta
Tentado várias vezes nesta sessão; `list_connected_browsers` volta vazio.
A extensão instalada é a "Claude" comum (chat lateral). O controle de navegador
pelo Claude Code é preview liberado por conta — pode não estar habilitado.
Enquanto não conectar, dados do Power BI entram por print/export manual.

---

## FEITO NESTA SESSÃO (2026-09-10)

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
