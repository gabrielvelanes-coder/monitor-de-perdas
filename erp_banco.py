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
