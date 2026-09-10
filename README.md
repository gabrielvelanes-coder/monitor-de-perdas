# Monitor de Perdas — Grupo Velanes

Dashboard para acompanhar a **taxa de perdas por mês** (perda ÷ faturamento),
separar o que é perda de verdade do que não é, e diagnosticar de onde vem o
vencimento cruzando com curva / giro / estoque.

## As 4 telas

| Tela | Pergunta que responde |
|---|---|
| **Veredito** | A perda é aceitável? Semáforo taxa vs faixa de mercado + diagnóstico automático + quanto é recuperável. |
| **Anatomia da perda** | O que são esses itens? Medicamento × não-medicamento (pela sua árvore mercadológica), por categoria, por curva, por tempo parado ao vencer. |
| **Evitável × estrutural** | Estou dando perda em item que vende? 4 baldes — PDV / excesso de compra / item suspenso / fora do mix — com ação por item e ranking de lojas. |
| **Regras e simulação** | O que mudar e quanto economiza. Simula teto de estoque por curva/categoria e estima a economia/mês. |

## Por que existe

Numa reunião foi apresentada uma taxa de perdas que parecia alta demais.
Cruzando o relatório de baixa de estoque com o faturamento real por loja
(Power BI *Visão geral - trimestre*, T1 e T2/2026), a taxa fica em:

| Recorte | % do faturamento | R$/mês |
|---|---:|---:|
| Somente vencidos | **0,51 %** | ~44 mil |
| Perda real (venc.+danif.+furto+descont.) | **0,54 %** | ~47 mil |
| Todos os motivos | **0,62 %** | ~54 mil |

Confere com a própria coluna `%perda/fat` do Power BI (0,63 % no T1, 0,59 % no T2).
Vencido responde por ~79 % do valor. Faixa normal de varejo farma é 0,3 %–0,8 %.
Distorções comuns num número inflado:

- somar a linha **"Total"** do relatório (ela já é a soma de tudo → dobra o valor);
- contar **AÇÃO DE MARKETING, CONSUMO LOJA, REEMBOLSO PELO FORNECEDOR** como
  perda (juntos ~14 % do valor lançado, e não são perda);
- usar o **acumulado do ano** como se fosse de um mês;
- dividir por lucro / CMV em vez de faturamento.

A aba **"Bater com o número da reunião"** faz essa comparação na tela.

## Como rodar

```bash
cd "C:\Users\E.C Velanes\OneDrive\Área de Trabalho\PERDAS"
pip install -r requirements.txt
streamlit run app.py
```

## Entradas (colocar nesta pasta ou enviar pela barra lateral)

| # | Arquivo | O que é |
|---|---------|---------|
| 1 | `perdas ... com motivo e loja.xls` | Análise de Baixa de Estoque (produto, motivo, loja, mês, valor). **Obrigatório.** |
| 2 | `DADOS *.xlsx` | Cadastro por loja: curva, média de venda, dias sem vender, estoque, motivo de suspensão. Um ou vários arquivos. Habilita a aba de diagnóstico. |
| 3 | `faturamento.csv` | Faturamento por loja e mês. Sem ele os valores aparecem em R$, mas não em %. |

### Formato do faturamento

Longo (recomendado) — uma linha por loja e mês:

```csv
loja,ano_mes,faturamento
2,2026-01,132256.54
3,2026-01,232022.80
```

Também aceita formato largo (lojas nas linhas, meses `2026-01`, `jan`... nas colunas).
A origem é o Power BI *Visão geral - mês* → coluna **Receita** por **Und. ID**,
um mês fechado por vez (ou trimestre em *Visão geral - trimestre*, ou o ERP).
O `faturamento.csv` que acompanha traz jan–jun/2026 (T1+T2 do Power BI); falta jul em diante.

Dá pra digitar na barra lateral (**Digitar faturamento**); fica salvo em `faturamento.json`.

## Escopos de perda

- **Somente vencidos** — o que interessa monitorar de fato.
- **Perda real** — vencido + danificado + furto + descontinuado + não classificado.
- **Todos os motivos** — inclui marketing, consumo de loja, reembolso, devolução,
  bonificação, doação, treinamento. Serve para reproduzir um número "cheio".

## Notas técnicas

- 1ª leitura dos `DADOS*.xlsx` demora (~10 s por arquivo com `calamine`,
  mais sem ele); depois fica em cache em `.cache/*.parquet` e é instantânea até
  o arquivo mudar.
- O relatório `.xls` vem com acentos corrompidos (`A��O DE MARKENTIG`);
  a classificação de motivos é feita por trecho sem acento, então funciona
  mesmo assim.
- Lojas que aparecem na perda mas não no faturamento (ex.: 12, 21, DEP) são
  listadas no Veredito e ficam fora do cálculo de %.
- Medicamento × não-medicamento sai do nível 1 da árvore mercadológica
  (`Classificação Principal` do cadastro): PROPAGADO/GENÉRICOS/SIMILARES = medicamento;
  DERMO/SUPLEMENTOS/HIGIENE/INFANTIL... = não. ~6% fica "sem classificação".
- Tema: `.streamlit/config.toml` (financial-dashboard, dark).
- `core.py` = carga + cálculo (funções puras). `app.py` = 4 telas via `st.navigation`.
