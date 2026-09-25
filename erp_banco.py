"""Leitura direta do banco PostgreSQL do ERP (somente leitura) -- mesmo
padrão/credenciais já validado no Painel de Ofertas e no Cestas & Vendas
(`OFERTAS GRUPO VELANES/painel-ofertas/apps/ofertas/erp_banco.py`), com a
consulta própria deste projeto (baixa de estoque com motivo).

Diferente dos outros 2 projetos (Django), o Monitor de Perdas é um app
Streamlit simples -- sem `settings.BASE_DIR`, lê o `.env` relativo a este
próprio arquivo.

Credenciais: arquivo `.env` na raiz do projeto (fora do Git), ver
`.env.exemplo`. Conexão aberta com `default_transaction_read_only=on` --
mesmo que algum código tentasse gravar, o PostgreSQL recusaria.

Tabelas usadas (achadas e validadas em 25/09/26 -- ver PENDENCIAS.md):
`baixaestoque` (1 por baixa: loja, motivo, data) + `itembaixaestoque`
(1 por produto dentro da baixa: quantidade/valor) + `motivo` (descrição).
Equivalente ao relatório "Análise de Baixa de Estoque" (.xls) que o
Gabriel exportava manualmente. Validado: uma linha específica (loja 02,
ABS LONGO MODERADO, set/26, motivo PRODUTO VENCIDO) bate exato (2 itens,
R$13,92) contra `perdas 2026 com motivo e loja.xls`; soma jan-set/26
bate a 0,9% (R$497.294 banco vs R$492.727 planilha -- diferença
esperada, a planilha é um extrato estático de uma data anterior, o
banco é sempre a foto atual).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ARQUIVO_ENV = Path(__file__).resolve().parent / '.env'


def _ler_env() -> dict:
    """Lê `.env` (CHAVE=valor por linha) sem depender de pacote extra.
    Variáveis de ambiente de verdade têm prioridade sobre o arquivo."""
    valores = {}
    if ARQUIVO_ENV.exists():
        for linha in ARQUIVO_ENV.read_text(encoding='utf-8').splitlines():
            linha = linha.strip()
            if not linha or linha.startswith('#') or '=' not in linha:
                continue
            chave, valor = linha.split('=', 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    for chave in ('ERP_HOST', 'ERP_PORTA', 'ERP_BANCO', 'ERP_USUARIO', 'ERP_SENHA'):
        if os.environ.get(chave):
            valores[chave] = os.environ[chave]
    return valores


def disponivel() -> bool:
    """True se há credenciais suficientes pra tentar conectar (não testa a
    conexão de verdade -- só se o .env está preenchido)."""
    env = _ler_env()
    return all(env.get(c) for c in ('ERP_HOST', 'ERP_BANCO', 'ERP_USUARIO', 'ERP_SENHA'))


def conectar():
    """Abre conexão SOMENTE LEITURA com o banco do ERP."""
    import psycopg  # import tardio: o projeto continua rodando sem o pacote

    env = _ler_env()
    faltando = [c for c in ('ERP_HOST', 'ERP_BANCO', 'ERP_USUARIO', 'ERP_SENHA') if not env.get(c)]
    if faltando:
        raise RuntimeError(
            f'Faltam no arquivo .env: {", ".join(faltando)}. '
            'Copie .env.exemplo para .env e preencha (mesma senha do Painel de Ofertas/DBeaver).'
        )
    return psycopg.connect(
        host=env['ERP_HOST'],
        port=env.get('ERP_PORTA', '5432'),
        dbname=env['ERP_BANCO'],
        user=env['ERP_USUARIO'],
        password=env['ERP_SENHA'],
        connect_timeout=15,
        options='-c default_transaction_read_only=on -c statement_timeout=120000',
        application_name='monitor-perdas',
    )


# Filtro `status='F'` nas 2 tabelas -- mesmo achado documentado no Painel
# de Ofertas pra `venda`/`itemvenda`: sem ele, baixa cancelada ('C') ou
# ainda aberta ('A') entra na soma (achado real: sem o filtro, jan-set/26
# soma ~R$21mil A MAIS do que deveria).
CONSULTA_BAIXA_ESTOQUE = """
SELECT u.codigo                                AS loja_raw,
       to_char(b.datahora, 'YYYY-MM')           AS ano_mes,
       e.descricao                              AS produto,
       m.descricao                              AS motivo,
       sum(ib.quantidade)                       AS itens,
       sum(ib.valortotal)                       AS valor_total
FROM baixaestoque b
JOIN itembaixaestoque ib ON ib.baixaestoqueid = b.id
JOIN unidadenegocio u    ON u.id = b.unidadenegocioid
JOIN embalagem e         ON e.id = ib.embalagemid
JOIN motivo m            ON m.id = b.motivoid
WHERE b.status = 'F' AND ib.status = 'F'
  AND b.datahora >= %(desde)s
GROUP BY u.codigo, to_char(b.datahora, 'YYYY-MM'), e.descricao, m.descricao
"""


def consultar_baixa_estoque(desde: str = '2026-01-01') -> pd.DataFrame:
    """-> DataFrame cru do banco (loja_raw, ano_mes, produto, motivo, itens,
    valor_total) -- mesmas colunas que `core.load_perdas` monta a partir do
    .xls, só falta o pós-processamento (motivo_cat, is_dep, valor_unit
    etc.), feito em `core.load_perdas_do_banco`."""
    with conectar() as conn:
        return pd.read_sql(CONSULTA_BAIXA_ESTOQUE, conn, params={'desde': desde})


# `custoproduto` -- custo ATUAL por produto x loja, mantido pelo próprio ERP
# (não é um relatório de sugestão de compra com propósito diferente).
# Achado e validado em 25/09/26 (ver PENDENCIAS.md): nunca tem custo/
# customedio nulo ou <=0 nas 706 mil linhas -- diferente do "Custo Médio"
# do DADOS, que vem zerado/quase-zero em ~26% da base sem motivo aparente.
# Cobertura por (produto, loja) não é 100% -- quando a própria loja nunca
# comprou o item diretamente, não tem linha lá (não é zero, é ausência);
# testado contra 28.450 itens de custo inválido no DADOS: 89,6% resolvido
# combinando `custoproduto` com o fallback já existente em
# `core.calcular_fallback_custo` (maior custo do mesmo EAN em outra loja).
# `historicocusto` é só o log de eventos (1 por nota fiscal/recebimento)
# por trás do `custoproduto` -- não precisa consultar direto, o
# `custoproduto` já é o resumo/atual que ele alimenta.
CONSULTA_CUSTO_PRODUTO = """
SELECT u.codigo        AS loja_raw,
       e.codigobarras  AS ean,
       cp.custo        AS custo,
       cp.customedio   AS customedio
FROM custoproduto cp
JOIN embalagem e         ON e.produtoid = cp.produtoid
JOIN unidadenegocio u    ON u.id = cp.unidadenegocioid
WHERE e.codigobarras IS NOT NULL
"""


def consultar_custo_produto() -> pd.DataFrame:
    """-> DataFrame cru do banco (loja_raw, ean, custo, customedio) --
    pós-processado (EAN validado, loja numérica, escolha custo/customedio)
    em `core.load_custo_do_banco`."""
    with conectar() as conn:
        return pd.read_sql(CONSULTA_CUSTO_PRODUTO, conn)


# Faturamento por loja/mês -- TODO produto, com ou sem oferta (mesma
# consulta/filtros já validados no Painel de Ofertas,
# `consultar_venda_geral_mensal`, só sem a coluna de custo que lá é usada
# pro CMV e aqui não precisa).
CONSULTA_FATURAMENTO_MENSAL = """
SELECT to_char(iv.datahora, 'YYYY-MM') AS ano_mes,
       u.codigo                        AS loja_raw,
       sum(iv.valortotal)              AS faturamento
FROM itemvenda iv
JOIN venda v          ON v.id = iv.vendaid AND v.status = 'F'
JOIN unidadenegocio u ON u.id = iv.unidadenegocioid
WHERE iv.status = 'F'
  AND iv.datahora >= %(desde)s
GROUP BY 1, 2
"""


def consultar_faturamento_mensal(desde: str = '2026-01-01') -> pd.DataFrame:
    with conectar() as conn:
        return pd.read_sql(CONSULTA_FATURAMENTO_MENSAL, conn, params={'desde': desde})


# Itens a vencer -- `itemprevencido` (validado 25/09/26): filtro
# `datavalidade >= hoje` (já vencido não é mais "a vencer", vira Perdas
# quando alguém baixar) + não encerrado + saldo>0 dá 4.696 lotes contra
# 4.761 do último arquivo manual -- bate. Sem esse filtro de validade dá
# 24.942 (tem muito lote já vencido há anos ainda "aberto" no ERP,
# esperando alguém baixar -- não é o que a tela quer mostrar).
CONSULTA_ITENS_A_VENCER = """
SELECT u.codigo                                          AS loja,
       e.descricao                                        AS produto,
       ip.lote                                             AS lote,
       ip.quantidadeinicial                                AS qtd_inicial,
       COALESCE(ip.quantidademovimentada, 0)               AS qtd_movimentada,
       (ip.quantidadeinicial - COALESCE(ip.quantidademovimentada, 0)) AS saldo,
       COALESCE(est.estoque, 0)                            AS estoque_atual,
       (ip.datavalidade::date - CURRENT_DATE)               AS dias_venc,
       ip.datavalidade                                      AS data_validade,
       ip.datafabricacao                                    AS data_fab,
       e.codigobarras                                       AS cod_barras,
       pf.nome                                              AS fabricante,
       c.caminho                                            AS classif,
       cav.nome                                             AS curva_valor,
       caq.nome                                             AS curva_qtd
FROM itemprevencido ip
JOIN embalagem e            ON e.id = ip.embalagemid
JOIN unidadenegocio u       ON u.id = ip.unidadenegocioid
LEFT JOIN produto p          ON p.id = e.produtoid
LEFT JOIN fabricante f       ON f.id = p.fabricanteid
LEFT JOIN pessoa pf          ON pf.id = f.pessoaid
LEFT JOIN classificacaoproduto cp
       ON cp.produtoid = e.produtoid
      AND cp.classificacaoid IN (SELECT id FROM classificacao WHERE caminho ILIKE 'ARVORE NOVA%%')
LEFT JOIN classificacao c    ON c.id = cp.classificacaoid
LEFT JOIN curvaabcprodutounidadenegocio cpu
       ON cpu.produtoid = e.produtoid AND cpu.unidadenegocioid = ip.unidadenegocioid
LEFT JOIN curvaabc cav       ON cav.id = cpu.curvaabcvalorid
LEFT JOIN curvaabc caq       ON caq.id = cpu.curvaabcquantidadeid
LEFT JOIN estoque est        ON est.embalagemid = ip.embalagemid AND est.unidadenegocioid = ip.unidadenegocioid
WHERE ip.status = 'A'
  AND ip.datahoraencerramento IS NULL
  AND (ip.quantidadeinicial - COALESCE(ip.quantidademovimentada, 0)) > 0
  AND ip.datavalidade >= CURRENT_DATE
"""


def consultar_itens_a_vencer() -> pd.DataFrame:
    with conectar() as conn:
        return pd.read_sql(CONSULTA_ITENS_A_VENCER, conn)


# Catálogo (substitui BASE CADASTRO COM GRUPOS) -- mesmo padrão de
# classificação/curva ABC (global, sem loja) já usado no
# cestas-vendas/erp_banco.py CONSULTA_PRODUTOS.
CONSULTA_CATALOGO = """
SELECT e.descricao                             AS produto,
       p.status                                AS status_cadastro,
       c.caminho                                AS classif_cat,
       cav.nome                                 AS curva_valor_cat,
       caq.nome                                 AS curva_qtd_cat,
       pf.nome                                  AS fabricante_cat
FROM produto p
JOIN embalagem e ON e.produtoid = p.id
LEFT JOIN fabricante f  ON f.id = p.fabricanteid
LEFT JOIN pessoa pf     ON pf.id = f.pessoaid
LEFT JOIN classificacaoproduto cp
       ON cp.produtoid = p.id
      AND cp.classificacaoid IN (SELECT id FROM classificacao WHERE caminho ILIKE 'ARVORE NOVA%%')
LEFT JOIN classificacao c ON c.id = cp.classificacaoid
LEFT JOIN curvaabcproduto cabc ON cabc.produtoid = p.id
LEFT JOIN curvaabc cav ON cav.id = cabc.curvaabcvalorid
LEFT JOIN curvaabc caq ON caq.id = cabc.curvaabcquantidadeid
"""


def consultar_catalogo() -> pd.DataFrame:
    with conectar() as conn:
        return pd.read_sql(CONSULTA_CATALOGO, conn)


# Cadastro (substitui os arquivos DADOS*.xlsx) -- curva ABC POR LOJA
# (`curvaabcprodutounidadenegocio`, diferente da curva global usada no
# Catálogo), motivo de suspensão de compra (`suspendecompraprodutounidade
# negocio`), estoque atual (`estoque`) e 3 métricas CALCULADAS (não são
# campo direto do ERP, são a melhor aproximação razoável -- ver
# PENDENCIAS.md pra validar com o Gabriel se bate com o critério real da
# "Sugestão de Compra" dele):
#   - mvm (média venda mensal) = unidades vendidas nos últimos 90 dias / 3
#   - pvm (preço venda médio)  = venda / unidades nos últimos 90 dias
#   - ult_venda_dias / ult_compra_dias = dias desde a última venda/compra
#     (histórico de 365 dias) -- estes 2 são inequívocos, sem suposição.
#
# Achado 25/09/26: buscar o catálogo INTEIRO x 23 lojas (CROSS JOIN) trazia
# muito mais linhas do que o DADOS real (produto que a loja nunca teve,
# sem nenhum sinal) -- trocado por consulta ALVEJADA: só as combinações
# (loja, produto) que já aparecem em Perdas/Itens a vencer (é só isso que
# `enriquecer_vencidos`/`enriquecer_a_vencer` realmente cruzam), bem mais
# rápido e sem ruído.
CONSULTA_CADASTRO = """
WITH alvo(loja, produto) AS (
    SELECT * FROM unnest(%(lojas)s::text[], %(produtos)s::text[])
),
venda_ag AS (
    SELECT u.codigo AS loja, e.produtoid,
           max(iv.datahora)::date AS ultima_venda,
           sum(iv.quantidade) FILTER (WHERE iv.datahora >= now() - interval '90 days') AS unid_90d,
           sum(iv.valortotal) FILTER (WHERE iv.datahora >= now() - interval '90 days') AS venda_90d
    FROM itemvenda iv
    JOIN venda v ON v.id = iv.vendaid AND v.status='F'
    JOIN embalagem e ON e.id = iv.embalagemid
    JOIN unidadenegocio u ON u.id = iv.unidadenegocioid
    WHERE iv.status='F' AND iv.datahora >= now() - interval '365 days'
    GROUP BY u.codigo, e.produtoid
),
compra_ag AS (
    SELECT u.codigo AS loja, hc.produtoid,
           max(hc.datahoraconsiderada)::date AS ultima_compra
    FROM historicocusto hc
    JOIN unidadenegocio u ON u.id = hc.unidadenegocioid
    WHERE hc.datahoraconsiderada >= now() - interval '365 days'
    GROUP BY u.codigo, hc.produtoid
)
SELECT alvo.loja                         AS loja,
       alvo.produto                      AS produto,
       cav.nome                          AS curva_valor,
       caq.nome                          AS curva_qtd,
       COALESCE(est.estoque, 0)          AS estoque,
       mo.descricao                      AS motivo_susp,
       (CURRENT_DATE - va.ultima_venda)  AS ult_venda_dias,
       round(COALESCE(va.unid_90d, 0) / 3.0, 2) AS mvm,
       CASE WHEN COALESCE(va.unid_90d, 0) > 0
            THEN round(va.venda_90d / va.unid_90d, 4) END AS pvm,
       (CURRENT_DATE - ca.ultima_compra) AS ult_compra_dias
FROM alvo
JOIN unidadenegocio u ON u.codigo = alvo.loja
JOIN embalagem e       ON e.descricao = alvo.produto
JOIN produto p          ON p.id = e.produtoid
LEFT JOIN curvaabcprodutounidadenegocio cpu
       ON cpu.produtoid = p.id AND cpu.unidadenegocioid = u.id
LEFT JOIN curvaabc cav ON cav.id = cpu.curvaabcvalorid
LEFT JOIN curvaabc caq ON caq.id = cpu.curvaabcquantidadeid
LEFT JOIN estoque est ON est.embalagemid = e.id AND est.unidadenegocioid = u.id
LEFT JOIN suspendecompraprodutounidadenegocio susp
       ON susp.produtoid = p.id AND susp.unidadenegocioid = u.id
LEFT JOIN motivo mo ON mo.id = susp.motivoid
LEFT JOIN venda_ag va ON va.loja = alvo.loja AND va.produtoid = p.id
LEFT JOIN compra_ag ca ON ca.loja = alvo.loja AND ca.produtoid = p.id
"""


def consultar_cadastro(pares: list[tuple[str, str]]) -> pd.DataFrame:
    """`pares`: lista de (loja_codigo_str, produto_descricao) -- as
    combinações que interessam (de Perdas/Itens a vencer já carregados).
    Lista vazia -> DataFrame vazio, sem consultar o banco."""
    if not pares:
        return pd.DataFrame(columns=["loja", "produto", "curva_valor", "curva_qtd",
                                      "estoque", "motivo_susp", "ult_venda_dias",
                                      "mvm", "pvm", "ult_compra_dias"])
    lojas = [x[0] for x in pares]
    produtos = [x[1] for x in pares]
    with conectar() as conn:
        return pd.read_sql(CONSULTA_CADASTRO, conn, params={'lojas': lojas, 'produtos': produtos})
