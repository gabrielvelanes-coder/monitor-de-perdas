# Monitor de Perdas — Grupo Velanes

Dashboard para acompanhar a **taxa de perdas por mês** (perda ÷ faturamento),
separar o que é perda de verdade do que não é, e diagnosticar de onde vem o
vencimento cruzando com curva / giro / estoque.

## Por que existe

Numa reunião foi apresentada uma taxa de perdas que parecia alta demais.
Cruzando o relatório de baixa de estoque com o faturamento, a perda real fica
em torno de **0,3 % a 0,7 % do faturamento** (vencido responde por ~79 % do
valor). Distorções comuns num número inflado:

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
Baixe `faturamento_modelo.csv` na aba **Dados**. A origem é o Power BI
*Visão geral - mês* → coluna **Receita** por **Und. ID**, um mês fechado por vez
(ou o mesmo dado direto do ERP).

Dá pra digitar na barra lateral (**✏️ digitar faturamento na mão**); fica salvo
em `faturamento.json`.

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
  listadas na Visão geral e ficam fora do cálculo de %.
- `core.py` = carga + cálculo (funções puras). `app.py` = interface.
