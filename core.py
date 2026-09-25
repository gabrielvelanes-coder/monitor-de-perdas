"""
core.py — carga e cálculo do Monitor de Perdas.

Três entradas:
  1. Relatório de perdas  (Análise de Baixa de Estoque)  -> .xls / .xlsx
  2. Cadastro de produtos  (curva, giro, estoque)          -> 1..N .xlsx  (arquivos "DADOS ...")
  3. Faturamento por loja / mês                            -> .csv / .xlsx  (ou digitado no app)

Tudo aqui são funções puras. O Streamlit (app.py) só orquestra e desenha.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------------- #
# util de texto
# ----------------------------------------------------------------------------- #

def _ascii(s) -> str:
    """Maiúsculas, sem acento, sem caractere estranho. Tolera o mojibake do .xls."""
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if ord(c) < 128)          # dropa acento e U+FFFD
    return re.sub(r"\s+", " ", s).strip().upper()


def _norm_produto(s) -> str:
    """Chave de join por descrição de produto: maiúsculas, espaços colapsados,
    acento removido. Usada para casar o catálogo (nível produto) com a perda."""
    return _ascii(s)


# ----------------------------------------------------------------------------- #
# 1. classificação de motivo
# ----------------------------------------------------------------------------- #
# categoria -> (rótulo amigável, conta como "perda direta"? — sai do estoque
# sem nenhuma compensação, ao contrário de marketing/reembolso/consumo/doação)
CATS = {
    "vencido":              ("Produto vencido",            True),
    "danificado":           ("Produto danificado",         True),
    "furto":                ("Furto ou roubo",             True),
    "descontinuado":        ("Produto descontinuado",      True),
    "outros":               ("Outros / não classificado",  True),
    "consumo_loja":         ("Consumo da loja",            False),
    "marketing":            ("Ação de marketing",          False),
    "reembolso_fornecedor": ("Reembolso pelo fornecedor",  False),
    "devolucao_fornecedor": ("Devolução ao fornecedor",    False),
    "bonificado":           ("Produto bonificado",         False),
    "doacao":               ("Doação / brinde",            False),
    "treinamento":          ("Uso treinamento RH",         False),
    "ignorar":              ("(não usar esse)",            False),
}
LABEL = {k: v[0] for k, v in CATS.items()}
IS_PERDA_REAL = {k: v[1] for k, v in CATS.items()}


def classify_motivo(motivo: str) -> str:
    m = _ascii(motivo)
    if not m:
        return "outros"
    if "USAR ESSE" in m:
        return "ignorar"
    if "MARKENTIG" in m or "MARKETING" in m:
        return "marketing"
    if "REEMBOLSO" in m:
        return "reembolso_fornecedor"
    if "DEVOLU" in m and "FORNECEDOR" in m:
        return "devolucao_fornecedor"
    if "CONSUMO" in m:
        return "consumo_loja"
    if "BONIFICAD" in m:
        return "bonificado"
    if "DOACAO" in m or "BRINDE" in m:
        return "doacao"
    if "TREINAMENTO" in m:
        return "treinamento"
    if "VENCID" in m or "VENCIMENTO" in m or "VALIDADE" in m:
        return "vencido"
    if "DANIFICAD" in m or "AVARIA" in m or "QUEBRA" in m:
        return "danificado"
    if "FURTO" in m or "ROUBO" in m:
        return "furto"
    if "DESCONTINUAD" in m:
        return "descontinuado"
    return "outros"


ESCOPOS = {
    "vencido":    "Somente vencidos",
    "perda_real": "Perda direta (vencido + danificado + furto + descontinuado + outros)",
    "todos":      "Todos os motivos (inclui marketing, consumo, reembolso...)",
}


def in_escopo(cat: str, escopo: str) -> bool:
    if escopo == "todos":
        return cat != "ignorar"
    if escopo == "perda_real":
        return IS_PERDA_REAL.get(cat, True)
    return cat == "vencido"


# categoria de motivo -> classe (3 baldes, usados na tela "Motivos"). Nomes
# descritivos, sem julgar o que é "real" ou "não é perda" — todo motivo tira
# item do estoque; a diferença é se tem compensação (marketing/reembolso/
# consumo/doação) ou não (quebra: vencido/danificado/furto/descontinuado).
CLASSES_PERDA = ["Vencido", "Outra perda direta", "Baixa comercial"]

_CLASSE_MOTIVO = {
    "vencido":              "Vencido",
    "danificado":           "Outra perda direta",
    "furto":                "Outra perda direta",
    "descontinuado":        "Outra perda direta",
    "outros":               "Outra perda direta",
    "consumo_loja":         "Baixa comercial",
    "marketing":            "Baixa comercial",
    "reembolso_fornecedor": "Baixa comercial",
    "devolucao_fornecedor": "Baixa comercial",
    "bonificado":           "Baixa comercial",
    "doacao":               "Baixa comercial",
    "treinamento":          "Baixa comercial",
    "ignorar":              "Baixa comercial",
}


def classe_motivo(motivo_cat: str) -> str:
    """Balde de 3 níveis p/ a tela Motivos: Vencido / Outra perda direta / Baixa
    comercial. Coerente com IS_PERDA_REAL (só separa o vencido do resto da
    perda direta)."""
    return _CLASSE_MOTIVO.get(motivo_cat, "Outra perda direta")


# ----------------------------------------------------------------------------- #
# 2. carga do relatório de perdas
# ----------------------------------------------------------------------------- #

def _find_header(df0: pd.DataFrame) -> int:
    for i in range(min(15, len(df0))):
        row = [_ascii(x) for x in df0.iloc[i].tolist()]
        if any("NEG" in c for c in row) and any(c == "MOTIVO" for c in row):
            return i
    return 0


def _map_perdas_cols(cols) -> dict:
    out = {}
    for c in cols:
        n = _ascii(c)
        if "NEG" in n and "loja" not in out.values():
            out[c] = "loja"
        elif n in ("EMBALAGEM", "PRODUTO", "DESCRICAO") and "produto" not in out.values():
            out[c] = "produto"
        elif n == "MOTIVO":
            out[c] = "motivo"
        elif n.startswith("ANO") or n in ("COMPETENCIA", "MES", "ANO-MS", "ANO-MES"):
            out[c] = "ano_mes"
        elif n == "ITENS" or n in ("QTD", "QUANTIDADE"):
            out[c] = "itens"
        elif "UNIT" in n:
            out[c] = "valor_unit"
        elif "TOTAL" in n and "%" not in n:
            out[c] = "valor_total"
        elif ("MEDIO" in n or "MDIO" in n) and "%" not in n:
            out[c] = "valor_medio"
    return out


def load_perdas(src) -> pd.DataFrame:
    """-> colunas: loja, ano_mes, produto, motivo, motivo_cat, is_perda_real,
                   itens, valor_unit, valor_total, is_dep"""
    name = getattr(src, "name", str(src))
    eng = "xlrd" if name.lower().endswith(".xls") else "openpyxl"
    df0 = pd.read_excel(src, header=None, nrows=15, engine=eng)
    h = _find_header(df0)
    if hasattr(src, "seek"):
        src.seek(0)
    df = pd.read_excel(src, header=h, engine=eng)

    ren = _map_perdas_cols(df.columns)
    df = df.rename(columns=ren)
    need = {"loja", "ano_mes", "motivo", "valor_total"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Relatório de perdas sem as colunas {missing}. "
                         f"Colunas lidas: {list(df.columns)}")

    df["loja_raw"] = df["loja"].astype(str).str.strip()
    df = df[~df["loja_raw"].str.upper().isin(["TOTAL", "NAN", ""])].copy()
    df["is_dep"] = df["loja_raw"].str.upper().eq("DEP")
    df["loja"] = pd.to_numeric(df["loja_raw"], errors="coerce")

    df["ano_mes"] = (df["ano_mes"].astype(str).str.strip()
                     .str.replace("/", "-", regex=False).str[:7])
    df = df[df["ano_mes"].str.match(r"\d{4}-\d{2}")].copy()

    for c in ("itens", "valor_unit", "valor_total", "valor_medio"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "produto" not in df.columns:
        df["produto"] = ""
    if "itens" not in df.columns:
        df["itens"] = pd.NA
    if "valor_unit" not in df.columns:
        df["valor_unit"] = pd.NA

    df["produto"] = df["produto"].astype(str).str.strip()
    df["motivo"] = df["motivo"].astype(str).str.strip()
    df["motivo_cat"] = df["motivo"].map(classify_motivo)
    df["motivo_label"] = df["motivo_cat"].map(LABEL)
    df["is_perda_real"] = df["motivo_cat"].map(IS_PERDA_REAL)

    df = df.dropna(subset=["valor_total"])
    cols = ["loja", "loja_raw", "is_dep", "ano_mes", "produto", "motivo",
            "motivo_cat", "motivo_label", "is_perda_real", "itens",
            "valor_unit", "valor_total"]
    return df[cols].reset_index(drop=True)


def load_perdas_do_banco(desde: str = "2026-01-01") -> pd.DataFrame:
    """Mesma saída de `load_perdas` (loja, ano_mes, produto, motivo, ...),
    só que direto do banco do ERP (`erp_banco.consultar_baixa_estoque`) em
    vez do .xls exportado à mão -- ver `erp_banco.py` pro mapeamento de
    tabelas e a validação feita em 25/09/26 (bate ~99% com a planilha)."""
    import erp_banco

    df = erp_banco.consultar_baixa_estoque(desde)
    if df.empty:
        raise ValueError("Banco do ERP devolveu 0 linhas de baixa de estoque "
                          f"desde {desde} — confira a data ou o filtro de status.")

    df["loja_raw"] = df["loja_raw"].astype(str).str.strip()
    df["is_dep"] = df["loja_raw"].str.upper().eq("DEP")
    df["loja"] = pd.to_numeric(df["loja_raw"], errors="coerce")

    df["itens"] = pd.to_numeric(df["itens"], errors="coerce")
    df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce")
    df["valor_unit"] = (df["valor_total"] / df["itens"]).where(df["itens"] > 0)

    df["produto"] = df["produto"].astype(str).str.strip()
    df["motivo"] = df["motivo"].astype(str).str.strip()
    df["motivo_cat"] = df["motivo"].map(classify_motivo)
    df["motivo_label"] = df["motivo_cat"].map(LABEL)
    df["is_perda_real"] = df["motivo_cat"].map(IS_PERDA_REAL)

    df = df.dropna(subset=["valor_total"])
    cols = ["loja", "loja_raw", "is_dep", "ano_mes", "produto", "motivo",
            "motivo_cat", "motivo_label", "is_perda_real", "itens",
            "valor_unit", "valor_total"]
    return df[cols].reset_index(drop=True)


# ----------------------------------------------------------------------------- #
# 3. carga do cadastro de produtos (com cache em parquet)
# ----------------------------------------------------------------------------- #
_CAD_MAP = [
    ("loja",            lambda n: n.startswith("UN. NEG") or n == "UN NEG" or n == "UND ID"),
    ("produto",         lambda n: n == "PRODUTO"),
    ("custo_medio",     lambda n: "CUSTO MEDIO" in n),
    ("curva_qtd",       lambda n: "CURVA QTD" in n),
    ("curva_valor",     lambda n: "CURVA VALOR" in n),
    ("mvm",             lambda n: "MEDIA VENDA MENSAL" in n),
    ("mvd",             lambda n: "MEDIA VENDA DIARIA" in n),
    ("ult_venda_dias",  lambda n: "ULT" in n and "VENDA" in n and "DIA" in n),
    ("ult_compra_dias", lambda n: "ULT" in n and "COMPRA" in n and "DIA" in n),
    ("estoque_dias",    lambda n: n == "ESTOQUE (DIAS)" or n == "ESTOQUE DIAS"),
    ("estoque",         lambda n: n == "ESTOQUE"),
    ("pvm",             lambda n: "PRECO VENDA MEDIO" in n),
    ("classif",         lambda n: "CLASSIFICACAO PRINCIPAL" in n),
    ("motivo_susp",     lambda n: "MOTIVO DE SUSPENSAO" in n),
    ("fabricante",      lambda n: n == "FABRICANTE"),
    ("principio",       lambda n: "PRINCIPIO ATIVO" in n),
    ("cod_barras",      lambda n: "COD" in n and "BARRA" in n),
]


def _read_xlsx(src) -> pd.DataFrame:
    """Lê .xlsx. Tenta calamine (rápido) e cai pra openpyxl."""
    for eng in ("calamine", "openpyxl"):
        try:
            return pd.read_excel(src, engine=eng)
        except Exception:
            if hasattr(src, "seek"):
                src.seek(0)
    return pd.read_excel(src)


def _cache_path(paths: list[Path], prefix: str = "cadastro") -> Path:
    key = "|".join(f"{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}" for p in paths)
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    d = paths[0].parent / ".cache"
    d.mkdir(exist_ok=True)
    return d / f"{prefix}_{h}.parquet"


def load_cadastro(sources, use_cache: bool = True) -> pd.DataFrame:
    """sources: lista de caminhos (str/Path) OU de uploads do Streamlit.
       -> loja, produto, curva_valor, curva_qtd, mvm, ult_venda_dias, ... """
    are_paths = all(isinstance(s, (str, Path)) for s in sources)
    if are_paths:
        paths = [Path(s) for s in sources]
        cp = _cache_path(paths)
        if use_cache and cp.exists():
            return pd.read_parquet(cp)

    frames = []
    for s in sources:
        raw = _read_xlsx(s)
        ren = {}
        for c in raw.columns:
            n = _ascii(c)
            for dest, test in _CAD_MAP:
                if dest not in ren.values() and test(n):
                    ren[c] = dest
                    break
        raw = raw.rename(columns=ren)
        keep = [c for c in raw.columns if c in {d for d, _ in _CAD_MAP}]
        raw = raw[keep]
        frames.append(raw)

    cad = pd.concat(frames, ignore_index=True)
    cad["loja"] = pd.to_numeric(cad["loja"], errors="coerce")
    cad["produto"] = cad["produto"].astype(str).str.strip()
    for c in ("custo_medio", "mvm", "mvd", "ult_venda_dias", "ult_compra_dias",
              "estoque_dias", "estoque", "pvm"):
        if c in cad.columns:
            cad[c] = pd.to_numeric(cad[c], errors="coerce")
    cad = cad.dropna(subset=["loja", "produto"]).drop_duplicates(["loja", "produto"])

    if are_paths and use_cache:
        try:
            cad.to_parquet(cp)
        except Exception:
            pass
    return cad.reset_index(drop=True)


def load_cadastro_do_banco(pares: list[tuple[int, str]]) -> pd.DataFrame:
    """Cadastro direto do banco (substitui os arquivos DADOS*.xlsx) --
    curva ABC POR LOJA, motivo de suspensão de compra e estoque atual são
    campo direto do ERP; `mvm`/`pvm`/`ult_venda_dias`/`ult_compra_dias`
    são CALCULADOS (ver `erp_banco.CONSULTA_CADASTRO` pra definição exata
    e ressalva) -- ainda não confirmados com o Gabriel se batem com o
    critério da "Sugestão de Compra" original, vale validar.

    `pares`: lista de (loja, produto) -- só busca as combinações que
    Perdas/Itens a vencer já carregaram (achado 25/09/26: o catálogo
    inteiro x 23 lojas trazia muito mais ruído do que os arquivos DADOS
    reais tinham). `custo_medio` não vem daqui — usar `load_custo_do_banco`
    (grão EAN, cobertura bem melhor).

    -> loja, produto, curva_valor, curva_qtd, estoque, motivo_susp, mvm,
       pvm, ult_venda_dias, ult_compra_dias (mesmos nomes de `load_cadastro`,
       sem custo_medio/fabricante/principio)."""
    import erp_banco

    # unidadenegocio.codigo é zero-padded ("02", não "2") -- sem isso o
    # JOIN falha silenciosamente pra toda loja de 1 dígito (achado real
    # 25/09/26: 3.165 de 8.106 pares sem match nenhum, todos de lojas < 10).
    pares_str = [(str(int(loja)).zfill(2), str(produto)) for loja, produto in pares]
    cad = erp_banco.consultar_cadastro(pares_str)
    if cad.empty:
        return cad

    cad["loja"] = pd.to_numeric(cad["loja"], errors="coerce")
    cad["produto"] = cad["produto"].astype(str).str.strip()
    for c in ("mvm", "pvm", "ult_venda_dias", "ult_compra_dias", "estoque"):
        cad[c] = pd.to_numeric(cad[c], errors="coerce")
    cad = cad.dropna(subset=["loja", "produto"]).drop_duplicates(["loja", "produto"])
    return cad.reset_index(drop=True)


_SUGES_MAP = [
    ("loja",       lambda n: n.startswith("UN. NEG") or n == "UN NEG" or n == "UND ID"),
    ("custo",      lambda n: n == "CUSTO"),
    ("cod_barras", lambda n: "COD" in n and "BARRA" in n),
]


def load_base_suges(sources, use_cache: bool = True) -> pd.DataFrame:
    """"Base suges" (sugestão de compra do ERP) -- fonte de custo mais
    confiável que o "Custo Médio" do cadastro/DADOS. Achado real (17/09/26,
    com Gabriel): comparando com um exemplo de caderno pré-vencido, o campo
    "Custo Médio" (tanto aqui quanto no DADOS) fica zerado ou quase-zero em
    ~26% da base inteira, sem motivo aparente -- mas o campo **"Custo"**
    (coluna DIFERENTE, mesma planilha) continua plausível nesses mesmos
    casos (813 confirmados: Custo Médio < 20% do Preço Referencial, Custo
    entre 40%-105% dele). Junta por (loja, EAN) -- essa base tem
    "Cód. de Barras" de verdade, não o "Cód. Barras/Etiqueta" ambíguo do
    relatório de itens a vencer. Cobre ~61% dos itens a vencer (não é
    universal; ver `calcular_fallback_custo` pro resto). -> loja, ean, custo.
    """
    are_paths = all(isinstance(s, (str, Path)) for s in sources)
    if are_paths:
        paths = [Path(s) for s in sources]
        cp = _cache_path(paths, "suges")
        if use_cache and cp.exists():
            return pd.read_parquet(cp)

    frames = []
    for s in sources:
        raw = _read_xlsx(s)
        ren = {}
        for c in raw.columns:
            n = _ascii(c)
            for dest, test in _SUGES_MAP:
                if dest not in ren.values() and test(n):
                    ren[c] = dest
                    break
        raw = raw.rename(columns=ren)
        keep = [c for c in raw.columns if c in {d for d, _ in _SUGES_MAP}]
        frames.append(raw[keep])

    m = pd.concat(frames, ignore_index=True)
    m["loja"] = pd.to_numeric(m["loja"], errors="coerce")
    m["ean"] = m["cod_barras"].map(_ean_str)
    m["custo"] = pd.to_numeric(m["custo"], errors="coerce")
    m = m.dropna(subset=["loja"])
    m = m[m["ean"] != ""]
    m = m.drop_duplicates(["loja", "ean"])[["loja", "ean", "custo"]].reset_index(drop=True)

    if are_paths and use_cache:
        try:
            m.to_parquet(cp)
        except Exception:
            pass
    return m


def load_custo_do_banco() -> pd.DataFrame:
    """Custo direto do banco do ERP (`custoproduto` -- custo atual por
    produto x loja, ver `erp_banco.py`) -- mesma saída de `load_base_suges`
    (loja, ean, custo), serve como substituto dela em `enriquecer_a_vencer`/
    `calcular_fallback_custo` sem precisar mudar mais nada. Prioriza
    `customedio` (custo médio ponderado, mais estável) sobre `custo`
    (última compra); cai pro `custo` só quando `customedio` não é válido.
    Achado 25/09/26: melhor fonte que a "base suges" -- ver
    `erp_banco.CONSULTA_CUSTO_PRODUTO` e PENDENCIAS.md pra validação."""
    import erp_banco

    df = erp_banco.consultar_custo_produto()
    if df.empty:
        raise ValueError("Banco do ERP devolveu 0 linhas de custoproduto.")

    df["loja"] = pd.to_numeric(df["loja_raw"], errors="coerce")
    df["ean"] = df["ean"].astype(str).str.strip()
    df = df[df["ean"].map(_ean_valido)]

    df["custo"] = pd.to_numeric(df["custo"], errors="coerce")
    df["customedio"] = pd.to_numeric(df["customedio"], errors="coerce")
    custo_final = df["customedio"].where(df["customedio"] > 0.01, df["custo"])

    m = df.assign(custo=custo_final)
    m = m.dropna(subset=["loja"])
    m = m[m["custo"] > 0.01]
    m = m.drop_duplicates(["loja", "ean"])[["loja", "ean", "custo"]].reset_index(drop=True)
    return m


# catálogo nível-produto (BASE CADASTRO COM GRUPOS) — sem loja, chave = descrição
_CAT_MAP = [
    ("produto",          lambda n: n in ("DESCRICAO", "PRODUTO")),
    ("cod_catalogo",     lambda n: n == "CODIGO"),
    ("status_cadastro",  lambda n: n == "STATUS"),
    ("classif_cat",      lambda n: n == "CLASSIFICACAO"),
    ("curva_valor_cat",  lambda n: "CURVA VALOR" in n),
    ("curva_qtd_cat",    lambda n: "CURVA QTD" in n),
    ("principio_cat",    lambda n: "PRINCIPIO ATIVO" in n),
    ("fabricante_cat",   lambda n: n == "FABRICANTE"),
    ("natureza_receita", lambda n: "NATUREZA RECEITA" in n),
]


def load_catalogo(sources, use_cache: bool = True) -> pd.DataFrame:
    """BASE CADASTRO COM GRUPOS: catálogo nível-produto (sem loja).
       -> produto (chave normalizada), classif_cat, curva_valor_cat, curva_qtd_cat,
          status_cadastro (Ativo/Inativo), principio_cat, fabricante_cat.
       Só enriquece — a base operacional (giro/mvm/estoque) segue sendo o DADOS."""
    are_paths = all(isinstance(s, (str, Path)) for s in sources)
    if are_paths:
        paths = [Path(s) for s in sources]
        cp = _cache_path(paths, "catalogo")
        if use_cache and cp.exists():
            return pd.read_parquet(cp)

    frames = []
    for s in sources:
        raw = _read_xlsx(s)
        ren = {}
        for c in raw.columns:
            n = _ascii(c)
            for dest, test in _CAT_MAP:
                if dest not in ren.values() and test(n):
                    ren[c] = dest
                    break
        raw = raw.rename(columns=ren)
        keep = [c for c in raw.columns if c in {d for d, _ in _CAT_MAP}]
        frames.append(raw[keep])

    cat = pd.concat(frames, ignore_index=True)
    if "produto" not in cat.columns:
        raise ValueError(f"Catálogo sem coluna de descrição. Colunas: {list(cat.columns)}")
    cat["produto"] = cat["produto"].map(_norm_produto)
    cat = cat[cat["produto"].str.len() > 0]
    # 1 linha por produto; Ativo vence Inativo (ordena antes de dropar duplicata)
    if "status_cadastro" in cat.columns:
        cat = cat.sort_values("status_cadastro", na_position="last")
    cat = cat.drop_duplicates("produto", keep="first").reset_index(drop=True)

    if are_paths and use_cache:
        try:
            cat.to_parquet(cp)
        except Exception:
            pass
    return cat


def load_catalogo_do_banco() -> pd.DataFrame:
    """Catálogo direto do banco (substitui BASE CADASTRO COM GRUPOS.xlsx) --
    classificação (árvore ARVORE NOVA) + curva ABC global (produto, sem
    loja — ver `load_cadastro_do_banco` pra curva por loja). Mesma saída
    de `load_catalogo` (produto normalizado, classif_cat, curva_valor_cat,
    curva_qtd_cat, status_cadastro, fabricante_cat)."""
    import erp_banco

    cat = erp_banco.consultar_catalogo()
    if cat.empty:
        raise ValueError("Banco do ERP devolveu 0 linhas de catálogo.")

    cat["produto"] = cat["produto"].map(_norm_produto)
    cat = cat[cat["produto"].str.len() > 0]
    cat = cat.sort_values("status_cadastro", na_position="last")
    cat = cat.drop_duplicates("produto", keep="first").reset_index(drop=True)
    return cat


# ----------------------------------------------------------------------------- #
# 3b. itens a vencer (estoque atual com lote/validade, por loja)
# ----------------------------------------------------------------------------- #
_AVENCER_MAP = [
    ("loja",          lambda n: "NEG" in n and "CODIGO" in n),
    ("loja_nome",     lambda n: "NEG" in n and "NOME" in n),
    ("status",        lambda n: n == "STATUS"),
    ("produto",       lambda n: n == "EMBALAGEM"),
    ("lote",          lambda n: n == "LOTE"),
    ("qtd_inicial",   lambda n: "QUANTIDADE INICIAL" in n),
    ("qtd_movimentada", lambda n: "MOVIMENTADA" in n),
    ("saldo",         lambda n: n == "SALDO"),
    ("estoque_atual", lambda n: n == "ESTOQUE ATUAL"),
    ("dias_venc",     lambda n: "DIAS" in n and "VENCIMENTO" in n),
    ("data_fab",      lambda n: "FABRICA" in n),
    ("data_validade", lambda n: "VALIDADE" in n),
    ("fabricante",    lambda n: "FABRICANTE" in n),
    ("classif",       lambda n: "CLASSIFICACAO" in n),
    ("curva_qtd",     lambda n: "CURVA" in n and "QUANTIDADE" in n),
    ("curva_valor",   lambda n: "CURVA" in n and "VALOR" in n),
    ("mvm",           lambda n: "MEDIA VENDA MENSAL" in n),
    ("demanda_30d",   lambda n: "DEMANDA" in n),
    ("cod_barras",    lambda n: "BARRA" in n),
]


def load_itens_a_vencer(source) -> pd.DataFrame:
    """Relatório de estoque com lote/validade (ERP) -> loja, loja_nome, produto,
       lote, qtd_inicial, qtd_movimentada, saldo, estoque_atual, dias_venc,
       data_validade, classif, curva_qtd, curva_valor, mvm, demanda_30d. Só
       linhas com Status = Ativo.

       qtd_inicial = quantidade lançada no lote pré-vencido; qtd_movimentada =
       quantidade já vendida dentro desse pré-vencido; saldo = qtd_inicial -
       qtd_movimentada = o que ainda resta desse lote pré-vencido (é isso que
       expõe risco de perda, não o estoque geral). estoque_atual = estoque
       geral da loja para o produto, **não** restrito a esse lote pré-vencido
       — pode ser maior (tem estoque de outros lotes) ou menor (o lote
       pré-vencido ainda não foi baixado do sistema) que o saldo."""
    name = getattr(source, "name", str(source))
    raw = _read_xlsx(source) if name.lower().endswith(("xlsx", "xlsm")) else pd.read_csv(source)
    ren = {}
    for c in raw.columns:
        n = _ascii(c)
        for dest, test in _AVENCER_MAP:
            if dest not in ren.values() and test(n):
                ren[c] = dest
                break
    raw = raw.rename(columns=ren)
    need = {"loja", "produto", "estoque_atual", "dias_venc", "data_validade"}
    missing = need - set(raw.columns)
    if missing:
        raise ValueError(f"Relatório de itens a vencer sem as colunas {missing}. "
                         f"Colunas lidas: {list(raw.columns)}")
    keep = [c for c in raw.columns if c in {d for d, _ in _AVENCER_MAP}]
    av = raw[keep].copy()
    if "status" in av.columns:
        av = av[av["status"].astype(str).str.strip().str.casefold() == "ativo"]
    av["loja"] = pd.to_numeric(av["loja"], errors="coerce")
    av["produto"] = av["produto"].astype(str).str.strip()
    for c in ("estoque_atual", "qtd_inicial", "qtd_movimentada", "saldo",
              "dias_venc", "mvm", "demanda_30d"):
        if c in av.columns:
            av[c] = pd.to_numeric(av[c], errors="coerce")
    av["data_validade"] = pd.to_datetime(av["data_validade"], errors="coerce")
    av = av.dropna(subset=["loja", "produto"])
    return av.reset_index(drop=True)


# Achado real 25/09/26: 1 lote (LANCETA ACCU CHEK FASTCLIX, lote WPK193A)
# tinha `quantidadeinicial = 31.122.025` no ERP -- erro de digitação na
# origem (o mesmo lote no arquivo manual antigo tinha saldo=1). Sem filtro,
# esse 1 registro sozinho inflava o "estoque exposto" de ~R$300 mil pra
# R$1,7 BILHÃO. Not a bug daqui -- distribuição real confirma outlier
# isolado (2º maior saldo real é 119, ou seja 260 mil x menor que esse).
# `LIMITE_SALDO_PLAUSIVEL` bem folgado (não teria excluído nenhum saldo
# real já visto) só pra blindar contra erro de digitação como esse.
LIMITE_SALDO_PLAUSIVEL = 100_000


def load_itens_a_vencer_do_banco() -> pd.DataFrame:
    """Itens a vencer direto do banco (`itemprevencido`) -- mesma saída de
    `load_itens_a_vencer`. Filtro `datavalidade >= hoje` (já vencido não é
    mais "a vencer", vira Perdas quando alguém baixar) validado em 25/09/26
    contra o arquivo manual: 4.696 lotes no banco vs. 4.761 no último
    arquivo — bate. Também filtra saldo implausível (ver
    `LIMITE_SALDO_PLAUSIVEL`) -- vale o Gabriel corrigir o lote na origem
    (ERP) quando puder, aqui só evita que 1 erro de digitação estoure o
    "estoque exposto" da tela inteira."""
    import erp_banco

    av = erp_banco.consultar_itens_a_vencer()
    if av.empty:
        raise ValueError("Banco do ERP devolveu 0 linhas de itens a vencer.")

    av["loja"] = pd.to_numeric(av["loja"], errors="coerce")
    av["produto"] = av["produto"].astype(str).str.strip()
    for c in ("estoque_atual", "qtd_inicial", "qtd_movimentada", "saldo", "dias_venc"):
        av[c] = pd.to_numeric(av[c], errors="coerce")
    av["data_validade"] = pd.to_datetime(av["data_validade"], errors="coerce")
    av = av.dropna(subset=["loja", "produto"])
    av = av[av["saldo"].fillna(0) <= LIMITE_SALDO_PLAUSIVEL]
    return av.reset_index(drop=True)


def enriquecer_a_vencer(
    av: pd.DataFrame, cad: pd.DataFrame | None, custo_suges: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Cruza itens a vencer com o cadastro (loja, produto) só para trazer custo
    médio (e `pvm`, Preço Venda Médio — referência de venda já cadastrada,
    usada só como fallback quando não existe custo válido em loja nenhuma,
    ver `calcular_fallback_custo`); estima valor_exposto = saldo do lote
    pré-vencido (não-negativo) x custo médio. Usa `saldo` (o que resta do
    pré-vencido) e não `estoque_atual` (estoque geral, que pode não bater
    com o saldo do lote — ver `load_itens_a_vencer`); cai para
    `estoque_atual` só se o relatório não trouxer a coluna Saldo.

    `custo_suges` (opcional, ver `load_base_suges`): quando dado, o campo
    "Custo" de lá GANHA do "Custo Médio" do `cad` -- achado real (17/09/26):
    "Custo Médio" (tanto no `cad`/DADOS quanto na própria base suges) fica
    zerado/quase-zero sem motivo em ~26% da base, enquanto "Custo" continua
    plausível nos mesmos casos. Junta por (loja, EAN), não (loja, produto)
    -- EAN de verdade, sem a ambiguidade do "Cód. Barras/Etiqueta"."""
    m = av.copy()
    # custo_medio e pvm são independentes -- `cad` vindo do banco
    # (`load_cadastro_do_banco`) não traz custo_medio (usar
    # `load_custo_do_banco`, grão EAN, cobertura melhor) mas traz pvm; sem
    # isso o merge de pvm nunca acontecia quando só faltava custo_medio.
    if cad is not None and not cad.empty and {"loja", "produto"} <= set(cad.columns):
        cols_cad = ["loja", "produto"]
        cols_cad += [c for c in ("custo_medio", "pvm") if c in cad.columns]
        m = m.merge(cad[cols_cad], on=["loja", "produto"], how="left")
    if "custo_medio" not in m.columns:
        m["custo_medio"] = pd.Series(float("nan"), index=m.index, dtype="float64")
    if custo_suges is not None and not custo_suges.empty:
        m["ean"] = m["cod_barras"].map(_ean_str)
        m = m.merge(custo_suges[["loja", "ean", "custo"]], on=["loja", "ean"], how="left")
        m["custo_medio"] = m["custo"].combine_first(m["custo_medio"])
        m = m.drop(columns=["custo"])
    base_col = "saldo" if "saldo" in m.columns else "estoque_atual"
    m["estoque_pos"] = m[base_col].clip(lower=0)
    m["valor_exposto"] = m["estoque_pos"] * m["custo_medio"]
    m["macro"] = m["classif"].map(macro_categoria) if "classif" in m.columns else "sem classificacao"

    def _faixa_urgencia(d):
        if pd.isna(d):
            return "Sem data"
        if d <= 30:
            return "Até 30 dias"
        if d <= 90:
            return "Até 90 dias"
        if d <= 180:
            return "Até 180 dias"
        if d <= 365:
            return "Até 12 meses"
        return "Mais de 12 meses"

    m["urgencia"] = m["dias_venc"].map(_faixa_urgencia)
    return m


ORDEM_URGENCIA = ["Até 30 dias", "Até 90 dias", "Até 180 dias", "Até 12 meses",
                  "Mais de 12 meses", "Sem data"]


# ----------------------------------------------------------------------------- #
# 4. carga do faturamento
# ----------------------------------------------------------------------------- #
_MES_ABBR = {m: f"{i:02d}" for i, m in enumerate(
    ["jan", "fev", "mar", "abr", "mai", "jun",
     "jul", "ago", "set", "out", "nov", "dez"], start=1)}


def _to_ano_mes(v, ano_fallback=None) -> str | None:
    s = str(v).strip().lower()
    m = re.match(r"(\d{4})[-/.](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r"(\d{1,2})[-/.](\d{4})", s)          # mm/yyyy
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    for abbr, num in _MES_ABBR.items():
        if s.startswith(abbr) and ano_fallback:
            return f"{ano_fallback}-{num}"
    try:
        d = pd.to_datetime(v)
        return f"{d.year}-{d.month:02d}"
    except Exception:
        return None


def _parse_num(x) -> float | None:
    """Converte valor monetário em float, tolerando formato BR (1.234,56),
    US (1,234.56), 'R$', e número já limpo (1234.56)."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^\d,.\-]", "", str(x).strip())
    if not s or s in ("-", ".", ","):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):            # 1.234,56  -> BR
            s = s.replace(".", "").replace(",", ".")
        else:                                      # 1,234.56  -> US
            s = s.replace(",", "")
    elif "," in s:                                 # só vírgula
        s = s.replace(",", ".") if len(s.rsplit(",", 1)[-1]) <= 2 else s.replace(",", "")
    # só ponto (ou nada): ponto = decimal
    try:
        return float(s)
    except ValueError:
        return None


def load_faturamento(src, ano_fallback: int | None = None) -> pd.DataFrame:
    """Aceita formato LONGO (loja, mês, faturamento) ou LARGO (loja nas linhas,
       meses nas colunas). -> loja, ano_mes, faturamento"""
    name = getattr(src, "name", str(src))
    if name.lower().endswith((".csv", ".txt")):
        df = pd.read_csv(src, sep=None, engine="python", dtype=str)
    else:
        df = pd.read_excel(src)
    df.columns = [str(c).strip() for c in df.columns]
    norm = {c: _ascii(c) for c in df.columns}

    def pick(*keys):
        for c, n in norm.items():
            if any(k in n for k in keys):
                return c
        return None

    c_loja = pick("LOJA", "UND", "UNIDADE", "NEG", "FILIAL")
    c_fat = pick("FATURAMENTO", "RECEITA", "VENDA", "VALOR", "LIQUIDO")
    c_mes = pick("ANO_MES", "ANOMES", "ANO-MS", "COMPETENCIA", "MES", "PERIODO", "DATA")

    if c_loja is None:
        raise ValueError(f"Não achei a coluna de loja. Colunas: {list(df.columns)}")

    if c_mes and c_fat:                                    # formato longo
        out = df[[c_loja, c_mes, c_fat]].copy()
        out.columns = ["loja", "ano_mes", "faturamento"]
        out["ano_mes"] = out["ano_mes"].map(lambda v: _to_ano_mes(v, ano_fallback))
    else:                                                  # formato largo
        val_cols = [c for c in df.columns
                    if c != c_loja and _to_ano_mes(c, ano_fallback)]
        if not val_cols:
            raise ValueError("Formato de faturamento não reconhecido "
                             "(esperava colunas de mês ou colunas loja/mês/valor).")
        out = df.melt(id_vars=[c_loja], value_vars=val_cols,
                      var_name="ano_mes", value_name="faturamento")
        out.columns = ["loja", "ano_mes", "faturamento"]
        out["ano_mes"] = out["ano_mes"].map(lambda v: _to_ano_mes(v, ano_fallback))

    def _loja(v):
        n = pd.to_numeric(v, errors="coerce")
        if pd.notna(n):
            return float(n)
        m = re.search(r"\d+", str(v))
        return float(m.group()) if m else None

    out["loja"] = out["loja"].map(_loja)
    out["faturamento"] = out["faturamento"].map(_parse_num)
    out = out.dropna(subset=["loja", "ano_mes", "faturamento"])
    out = out[out["faturamento"] > 0]
    return out.groupby(["loja", "ano_mes"], as_index=False)["faturamento"].sum()


def load_faturamento_do_banco(desde: str = "2026-01-01") -> pd.DataFrame:
    """Faturamento direto do banco do ERP (itemvenda, TODO produto, com ou
    sem oferta -- mesmo filtro `status='F'` validado no Painel de Ofertas).
    -> loja, ano_mes, faturamento (mesma saída de `load_faturamento`)."""
    import erp_banco

    df = erp_banco.consultar_faturamento_mensal(desde)
    if df.empty:
        raise ValueError(f"Banco do ERP devolveu 0 linhas de faturamento desde {desde}.")
    df["loja"] = pd.to_numeric(df["loja_raw"], errors="coerce")
    df["faturamento"] = pd.to_numeric(df["faturamento"], errors="coerce")
    df = df.dropna(subset=["loja", "ano_mes", "faturamento"])
    return df.groupby(["loja", "ano_mes"], as_index=False)["faturamento"].sum()


def load_regionais(src) -> dict:
    """`regionais.csv` (loja, regional) -> {loja: regional}. Loja -> regional é
    rotativo (supervisores trocam de grupo de vez em quando), por isso vem de
    um arquivo próprio (editável pelo Gabriel) em vez de hardcode no código."""
    name = getattr(src, "name", str(src))
    df = (pd.read_csv(src, sep=None, engine="python", dtype=str)
          if name.lower().endswith((".csv", ".txt")) else pd.read_excel(src, dtype=str))
    df.columns = [_ascii(c) for c in df.columns]
    c_loja = next((c for c in df.columns if "LOJA" in c or "UND" in c or "NEG" in c), None)
    c_reg = next((c for c in df.columns if "REGIONAL" in c or "SUPERVISOR" in c), None)
    if c_loja is None or c_reg is None:
        raise ValueError(f"regionais.csv precisa de colunas loja/regional. "
                         f"Colunas lidas: {list(df.columns)}")
    out = {}
    for _, r in df.iterrows():
        loja = pd.to_numeric(r[c_loja], errors="coerce")
        if pd.notna(loja) and str(r[c_reg]).strip():
            out[int(loja)] = str(r[c_reg]).strip()
    return out


# ----------------------------------------------------------------------------- #
# 5. métricas
# ----------------------------------------------------------------------------- #

def taxa_por_loja_mes(perdas: pd.DataFrame, fat: pd.DataFrame,
                      escopo: str = "vencido", incluir_dep: bool = False) -> pd.DataFrame:
    p = perdas.copy()
    if not incluir_dep:
        p = p[~p["is_dep"]]
    p = p[p["motivo_cat"].map(lambda c: in_escopo(c, escopo))]
    g = (p.groupby(["loja", "ano_mes"], as_index=False)
           .agg(perda=("valor_total", "sum"), itens=("itens", "sum"),
                linhas=("valor_total", "size")))
    out = g.merge(fat, on=["loja", "ano_mes"], how="outer")
    out["perda"] = out["perda"].fillna(0.0)
    out["taxa"] = out["perda"] / out["faturamento"]
    return out.sort_values(["ano_mes", "loja"]).reset_index(drop=True)


def resumo_mensal(taxa_lm: pd.DataFrame) -> pd.DataFrame:
    """Agrega as lojas -> 1 linha por mês (só meses com faturamento informado)."""
    d = taxa_lm.dropna(subset=["faturamento"])
    g = (d.groupby("ano_mes", as_index=False)
           .agg(perda=("perda", "sum"), faturamento=("faturamento", "sum"),
                lojas=("loja", "nunique")))
    g["taxa"] = g["perda"] / g["faturamento"]
    return g.sort_values("ano_mes").reset_index(drop=True)


def perda_por_motivo(perdas: pd.DataFrame, incluir_dep: bool = False,
                     meses: list[str] | None = None) -> pd.DataFrame:
    p = perdas.copy()
    if not incluir_dep:
        p = p[~p["is_dep"]]
    if meses:
        p = p[p["ano_mes"].isin(meses)]
    n_meses = max(p["ano_mes"].nunique(), 1)
    g = (p.groupby(["motivo_cat", "motivo_label", "is_perda_real"], as_index=False)
           .agg(valor=("valor_total", "sum"), itens=("itens", "sum"),
                linhas=("valor_total", "size")))
    g["valor_mes"] = g["valor"] / n_meses
    g["pct"] = g["valor"] / g["valor"].sum()
    return g.sort_values("valor", ascending=False).reset_index(drop=True)


FAIXAS_GIRO = [(-1, 0, "Sem venda no periodo"), (0, 30, "Vendeu ate 30 dias"),
               (30, 60, "31 a 60 dias"), (60, 90, "61 a 90 dias"),
               (90, 180, "91 a 180 dias"), (180, 360, "181 a 360 dias"),
               (360, 10**9, "Sem vender ha +360 dias")]


def _faixa(d):
    if pd.isna(d):
        return "Sem cadastro"
    for lo, hi, lab in FAIXAS_GIRO:
        if lo < d <= hi:
            return lab
    return "Sem cadastro"


def _vazio(s: pd.Series) -> pd.Series:
    """True onde o valor é NaN, '', 'nan' ou 'none' (texto sujo do Excel)."""
    t = s.astype(str).str.strip().str.lower()
    return s.isna() | t.isin(("", "nan", "none"))


def _coalesce(a: pd.Series, b: pd.Series) -> pd.Series:
    """a onde a tem valor; senão b."""
    return a.where(~_vazio(a), b)


def enriquecer_vencidos(perdas: pd.DataFrame, cad: pd.DataFrame,
                        cats=("vencido",), incluir_dep: bool = False,
                        catalogo: pd.DataFrame | None = None) -> pd.DataFrame:
    p = perdas[perdas["motivo_cat"].isin(cats)].copy()
    if not incluir_dep:
        p = p[~p["is_dep"]]
    m = p.merge(cad, on=["loja", "produto"], how="left", suffixes=("", "_cad"))
    # 'sem cadastro' é sinal do DADOS (base operacional) — fixa antes de coalescer
    m["sem_cadastro"] = m["curva_qtd"].isna() & m["mvm"].isna()

    if catalogo is not None and not catalogo.empty:
        cj = catalogo.rename(columns={"produto": "_pkey"})
        m["_pkey"] = m["produto"].map(_norm_produto)
        m = m.merge(cj, on="_pkey", how="left").drop(columns="_pkey")
        if "classif_cat" in m.columns:
            if "classif" not in m.columns:
                m["classif"] = pd.NA
            m["classif"] = _coalesce(m["classif"], m["classif_cat"])
        if "curva_valor_cat" in m.columns:
            m["curva_valor"] = _coalesce(m["curva_valor"], m["curva_valor_cat"])
        if "curva_qtd_cat" in m.columns:
            m["curva_qtd"] = _coalesce(m["curva_qtd"], m["curva_qtd_cat"])
    if "status_cadastro" not in m.columns:
        m["status_cadastro"] = pd.NA

    m["faixa_giro"] = m["ult_venda_dias"].map(_faixa)
    m["curva_valor"] = m["curva_valor"].fillna("sem cadastro")
    m["item_suspenso"] = m["motivo_susp"].notna() & (m["motivo_susp"].astype(str).str.strip() != "")
    return m


def cobertura_faturamento(perdas: pd.DataFrame, fat: pd.DataFrame) -> dict:
    """Diagnóstico: o que ficou sem cruzar."""
    lojas_perda = set(perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())
    lojas_fat = set(fat["loja"].unique())
    meses_perda = set(perdas["ano_mes"].unique())
    meses_fat = set(fat["ano_mes"].unique())
    return {
        "lojas_sem_faturamento": sorted(lojas_perda - lojas_fat),
        "lojas_sem_perda":       sorted(lojas_fat - lojas_perda),
        "meses_sem_faturamento": sorted(meses_perda - meses_fat),
        "meses_com_faturamento": sorted(meses_perda & meses_fat),
    }


# ----------------------------------------------------------------------------- #
# 6. anatomia dos vencidos: medicamento x não, categoria, curva, diagnóstico
# ----------------------------------------------------------------------------- #

# Regra do cliente (Gabriel, 2026-09-10): no nível 1 da árvore mercadológica,
# só GENÉRICO / SIMILAR / PROPAGADO são medicamento; todo o resto que tem
# categoria é não-medicamento; sem categoria fica "sem classificacao".
_N1_MEDICAMENTO_PREFIXOS = ("GENERIC", "SIMILAR", "PROPAGAD")


def _arvore_niveis(classif) -> tuple[str, str]:
    """('PROPAGADO', 'PBM - RX') a partir de 'ARVORE NOVA > PROPAGADO > PBM - RX'."""
    s = str(classif or "").replace(">", "|")
    partes = [p.strip() for p in s.split("|") if p.strip()]
    partes = [p for p in partes if _ascii(p) not in ("ARVORE NOVA", "ARVORE", "NAN", "NONE", "")]
    n1 = partes[0].upper() if partes else ""
    n2 = partes[1].upper() if len(partes) > 1 else ""
    return n1, n2


def macro_categoria(classif) -> str:
    """medicamento se o nível 1 for genérico / similar / propagado; qualquer outra
    categoria é não-medicamento; sem categoria vira 'sem classificacao'."""
    n1, _ = _arvore_niveis(classif)
    a1 = _ascii(n1)
    if not a1:
        return "sem classificacao"
    if a1.startswith(_N1_MEDICAMENTO_PREFIXOS):
        return "medicamento"
    return "nao-medicamento"


# ----------------------------------------------------------------------------- #
# 6.1 preço sugerido do pré-vencido (planejamento fechado com o Gabriel em
#     14/09/26 — ver PENDENCIAS.md, seção PLANEJAMENTO, pro histórico da decisão)
# ----------------------------------------------------------------------------- #

# faixas de dias até vencer usadas SÓ pra precificação — diferentes das
# faixas de urgência da tela (ORDEM_URGENCIA/_faixa_urgencia, acima), que
# são pra agrupar/visualizar, não pra decidir preço.
FAIXAS_PRECO = [30, 60, 90, 120]

# fator sobre o custo médio, por faixa — regra padrão desconta (prioriza
# girar o estoque a deixar vencer). CAMPANHA é a única exceção hoje, com
# markup CRESCENTE conforme aproxima do vencimento (confirmado pelo
# Gabriel — provável subsídio por verba de campanha, não é objetivo do
# painel questionar a lógica de negócio, só aplicar certo).
_FATOR_PRECO_PADRAO = {30: 0.75, 60: 0.85, 90: 1.00, 120: 1.15}
_FATOR_PRECO_CAMPANHA = {30: 1.30, 60: 1.40, 90: 1.50, 120: 1.60}
# (14/09/26) regra própria de medicamento (0,90/1,00/1,05/1,10) foi
# implementada e depois REVERTIDA no mesmo dia — Gabriel simulou e achou
# alguns itens altos demais, pediu pra voltar à regra padrão. Deixa a
# tabela comentada aqui pra não perder o número se ele quiser retomar
# com valores ajustados: _FATOR_PRECO_MEDICAMENTO = {30: 0.90, 60: 1.00,
# 90: 1.05, 120: 1.10} — ver PENDENCIAS.md pro histórico completo.

# nome do arquivo de importação do ERP, por faixa — confirmado pelo Gabriel
NOME_ARQUIVO_PRECO = {30: "oferta_30dias.txt", 60: "oferta_60dias.txt",
                       90: "oferta_90dias.txt", 120: "oferta_120dias.txt"}


def faixa_preco(dias_venc) -> int | None:
    """Dias até vencer -> faixa de preço (30/60/90/120), ou None quando não
    entra em nenhum caderno (sem dado, negativo, ou acima de 120 dias —
    fica no preço normal da loja, sem arquivo)."""
    if pd.isna(dias_venc) or dias_venc < 0:
        return None
    for lim in FAIXAS_PRECO:
        if dias_venc <= lim:
            return lim
    return None


def sugerir_preco(dias_venc, custo_medio, classif=None) -> float | None:
    """Preço sugerido do pré-vencido pra 1 item — None quando falta custo
    médio, o custo está zerado, ou a faixa não existe (ver `faixa_preco`).
    Categoria CAMPANHA (nível 1 de `classif`) usa a tabela de markup; as
    demais — incluindo medicamento, sem tratamento especial — usam a
    padrão.

    Achado real (17/09/26): alguns itens têm custo médio cadastrado como
    R$0,00 (ou poucos centavos) no próprio ERP — não é "sem cadastro", tem
    valor, só que zerado/errado na origem. Sem essa checagem, 0 (ou quase
    0) × fator ainda dá 0/frações de centavo (ex. R$0,002), e o ERP recusa
    preço abaixo de 1 centavo na importação (menor valor de moeda real).
    Tratado igual "sem custo": vira None, mesmo caminho de exclusão que já
    existe pra falta de cadastro."""
    if pd.isna(custo_medio) or custo_medio is None or custo_medio <= 0:
        return None
    faixa = faixa_preco(dias_venc)
    if faixa is None:
        return None
    n1, _ = _arvore_niveis(classif)
    fatores = _FATOR_PRECO_CAMPANHA if n1 == "CAMPANHA" else _FATOR_PRECO_PADRAO
    preco = round(float(custo_medio) * fatores[faixa], 4)
    return preco if preco >= 0.01 else None


def enriquecer_precos(enr: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta `faixa_preco`/`preco_sugerido` ao df de itens a vencer já
    enriquecido — usado pela tela (coluna na tabela) e por
    `exportar_erp_precos` (mesmo cálculo, sem duplicar)."""
    m = enr.copy()
    if "classif" not in m.columns:
        m["classif"] = None
    m["faixa_preco"] = m["dias_venc"].map(faixa_preco)
    m["preco_sugerido"] = m.apply(
        lambda row: sugerir_preco(row["dias_venc"], row["custo_medio"], row["classif"]), axis=1)
    return m


def _ean_str(v) -> str:
    """Código de barras vem como int/float dependendo do arquivo — normaliza
    pra string de dígitos, sem casas decimais nem notação científica."""
    if pd.isna(v):
        return ""
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v).strip()


def _ean_valido(ean: str) -> bool:
    """A coluna do relatório de itens a vencer se chama 'Cód. Barras/Etiqueta'
    — mistura o EAN de verdade com o código interno (etiqueta) quando o ERP
    não tem o EAN cadastrado pro lote. Achado real (17/09/26): isso gerava
    arquivo de importação do ERP com código de etiqueta em vez de EAN
    (ex. "38493", "78945456"), e o ERP rejeitava o arquivo inteiro na
    importação. Formatos de código de barras de verdade têm 8+ dígitos
    (EAN-8/UPC-A/EAN-13) — abaixo disso é etiqueta interna, não EAN."""
    return ean.isdigit() and len(ean) >= 8


def calcular_fallback_custo(enr: pd.DataFrame) -> dict[tuple[str, int], float]:
    """Quando um item não tem custo médio válido (ver `sugerir_preco`) pra
    uma faixa, tenta resgatar o preço em 2 níveis, nessa ordem — decidido
    com Gabriel (17/09/26) depois de medir o tamanho de cada caso:

    1. Maior custo médio válido do MESMO EAN em OUTRA loja (o produto é o
       mesmo, só não foi bem cadastrado nessa loja específica — achado:
       15 de 99 EANs com custo inválido em algum lugar se resolvem assim).
    2. Se nem isso existir (custo inválido em TODAS as lojas), usa o maior
       Preço Venda Médio (`pvm`) encontrado pro EAN como base, aplicando o
       MESMO fator de desconto por faixa que se aplicaria ao custo — achado:
       37 dos 86 EANs sem custo em lugar nenhum tinham preço de referência
       utilizável.

    O que sobra sem solução nas duas tentativas (49 EANs + os com EAN
    inválido) precisa de correção manual no ERP mesmo -- não dá pra
    inventar preço sem nenhuma base de dado real.

    -> `{(ean, faixa): preco}` só com os casos resgatados -- NÃO mexe em
    item que já tem custo válido. Passar como (parte do) `overrides` de
    `exportar_erp_precos`."""
    m = enr.copy()
    m["ean"] = m["cod_barras"].map(_ean_str)
    base = m[(m["ean"] != "") & m["faixa_preco"].notna()].copy()
    if base.empty:
        return {}

    def _valido(row):
        return sugerir_preco(row["dias_venc"], row["custo_medio"], row.get("classif")) is not None
    base["custo_valido"] = base.apply(_valido, axis=1)

    tem_pvm = "pvm" in base.columns
    overrides: dict[tuple[str, int], float] = {}
    for ean, grupo in base.groupby("ean"):
        invalidos_grupo = grupo[~grupo["custo_valido"]]
        if invalidos_grupo.empty:
            continue
        validos = grupo[grupo["custo_valido"]]
        maior_custo = validos["custo_medio"].max() if not validos.empty else None
        maior_pvm = None
        if tem_pvm:
            pvm_valido = grupo[grupo["pvm"] > 0]
            maior_pvm = pvm_valido["pvm"].max() if not pvm_valido.empty else None
        base_custo = maior_custo if maior_custo is not None else maior_pvm
        if base_custo is None:
            continue  # sem custo E sem pvm em lugar nenhum -- fica sem solução automática
        classif = invalidos_grupo["classif"].iloc[0] if "classif" in invalidos_grupo.columns else None
        for faixa in invalidos_grupo["faixa_preco"].unique():
            faixa_int = int(faixa)
            if (ean, faixa_int) in overrides:
                continue
            # `faixa_preco(faixa_int) == faixa_int` sempre (limite exato de
            # FAIXAS_PRECO), então passar a própria faixa como "dias_venc"
            # devolve o fator certo sem duplicar a lógica de `sugerir_preco`.
            preco = sugerir_preco(faixa_int, base_custo, classif)
            if preco is not None:
                overrides[(ean, faixa_int)] = preco
    return overrides


def exportar_erp_precos(
    enr: pd.DataFrame, overrides: dict[tuple[str, int], float] | None = None,
) -> tuple[dict[str, str], int, int]:
    """A partir do df de itens a vencer já enriquecido (`enriquecer_a_vencer`
    — precisa de dias_venc/custo_medio/cod_barras; classif é opcional, sem
    ela cai sempre na regra padrão), gera o texto dos arquivos de
    importação do ERP no layout `A|EAN|||PREÇO` (4 casas decimais),
    1 arquivo por faixa de dias.

    O mesmo EAN pode aparecer em mais de 1 arquivo (lotes em faixas
    diferentes) — é esperado, o ERP escolhe o preço certo pelo lote real
    selecionado na venda (ver PENDENCIAS.md). Dentro de uma mesma faixa,
    2 lotes do mesmo EAN geram o mesmo preço (mesma fórmula), então só 1
    linha por EAN.

    `overrides` (opcional): `{(ean, faixa): preco}` pra sobrescrever o preço
    calculado em casos específicos (resgate automático de
    `calcular_fallback_custo` e/ou edição manual do Gabriel na tela "Itens
    a vencer") — aplicado ANTES de descartar linha sem preço válido (senão
    um item com custo inválido, que só existe graças ao override, nunca
    chegaria a receber o preço editado — bug real corrigido 17/09/26: a
    ordem antiga descartava a linha antes de checar `overrides`).

    -> ({nome_do_arquivo: texto} só com as faixas que tiverem algum item,
    quantidade de linhas descartadas por código de barras inválido — ver
    `_ean_valido` —, quantidade descartada por custo médio zerado/negativo
    cadastrado no ERP (depois de aplicar `overrides`) — ver `sugerir_preco`).
    """
    faltando = {"dias_venc", "custo_medio", "cod_barras"} - set(enr.columns)
    if faltando:
        raise ValueError(f"Faltam colunas pra gerar o arquivo do ERP: {faltando}")

    m = enriquecer_precos(enr)
    m["ean"] = m["cod_barras"].map(_ean_str)
    m = m[(m["ean"] != "") & m["faixa_preco"].notna()]

    if overrides:
        for (ean_o, faixa_o), preco_o in overrides.items():
            m.loc[(m["ean"] == ean_o) & (m["faixa_preco"] == faixa_o), "preco_sugerido"] = preco_o

    # custo INVÁLIDO (zerado, negativo, ou baixo demais pro preço final dar
    # 1 centavo) é diferente de SEM custo (NaN) -- aqui tem cadastro, só que
    # com valor que não sustenta um preço de venda real. Contado DEPOIS de
    # aplicar overrides (um item resgatado ou editado não conta mais como
    # pendência) pra avisar Gabriel só do que realmente ainda falta.
    n_custo_zerado = int((m["custo_medio"].notna() & m["preco_sugerido"].isna()).sum())

    m = m[m["preco_sugerido"].notna()]

    n_invalidos = int((~m["ean"].map(_ean_valido)).sum())
    m = m[m["ean"].map(_ean_valido)]

    saidas = {}
    for faixa in FAIXAS_PRECO:
        sub = m[m["faixa_preco"] == faixa]
        if sub.empty:
            continue
        por_ean = sub.groupby("ean", as_index=False)["preco_sugerido"].first()
        linhas = [f"A|{ean}|||{preco:.4f}" for ean, preco in
                  zip(por_ean["ean"], por_ean["preco_sugerido"])]
        saidas[NOME_ARQUIVO_PRECO[faixa]] = "\n".join(linhas)
    return saidas, n_invalidos, n_custo_zerado


# baldes de diagnóstico: onde a perda foi decidida
BALDES = {
    "pdv":          ("Evitável no PDV (item que gira venceu na gôndola)",
                     "Reforçar rotina de validade / PVPS na loja."),
    "compra":       ("Excesso de compra / giro fraco",
                     "Rever parâmetro de compra e estoque mínimo; não repor."),
    "cadastro":     ("Item suspenso / descontinuado",
                     "Bloquear compra, devolver ao fornecedor ou rebaixar antes de vencer."),
    "sem_cadastro": ("Fora do mix atual (sem cadastro ativo)",
                     "Apurar origem; provável encalhe antigo ou transferência de sobra."),
}


def classificar_vencidos(enr: pd.DataFrame) -> pd.DataFrame:
    """Adiciona: macro (medicamento x não), cat1/cat2 da árvore, balde."""
    m = enr.copy()
    niveis = m["classif"].map(_arvore_niveis)
    m["cat1"] = niveis.map(lambda t: t[0] or "Sem categoria")
    m["cat2"] = niveis.map(lambda t: t[1] or "—")
    m["macro"] = m["classif"].map(macro_categoria)

    mvm = pd.to_numeric(m.get("mvm"), errors="coerce").fillna(0)
    ult = pd.to_numeric(m.get("ult_venda_dias"), errors="coerce")
    curva = m["curva_valor"].astype(str).str.upper()
    susp = m["item_suspenso"].fillna(False)
    semc = m["sem_cadastro"].fillna(False)

    vivo = (mvm > 0) & (ult <= 90)
    curva_rel = curva.isin(list("ABCDE"))

    def balde(i):
        if semc.iloc[i]:
            return "sem_cadastro"
        if susp.iloc[i]:
            return "cadastro"
        if vivo.iloc[i] and curva_rel.iloc[i]:
            return "pdv"
        return "compra"

    m["balde"] = [balde(i) for i in range(len(m))]
    m["balde_label"] = m["balde"].map(lambda b: BALDES[b][0])
    return m


def resumo_baldes(vclass: pd.DataFrame, n_meses: int = 1) -> pd.DataFrame:
    tot = vclass["valor_total"].sum() or 1.0
    g = (vclass.groupby(["balde", "balde_label"], as_index=False)
         .agg(valor=("valor_total", "sum"), linhas=("valor_total", "size"),
              produtos=("produto", "nunique")))
    g["valor_mes"] = g["valor"] / max(n_meses, 1)
    g["pct"] = g["valor"] / tot
    g["acao"] = g["balde"].map(lambda b: BALDES[b][1])
    ordem = {"pdv": 0, "compra": 1, "cadastro": 2, "sem_cadastro": 3}
    return g.sort_values("balde", key=lambda s: s.map(ordem)).reset_index(drop=True)


def frase_diagnostico(mensal: pd.DataFrame, vclass: pd.DataFrame,
                      meta: float = 0.005,
                      faixa=(0.003, 0.008)) -> tuple[str, str]:
    """(nivel, frase). nivel ∈ {ok, atencao, critico}, medido contra a `meta`."""
    if mensal.empty:
        return "sem_dados", "Informe o faturamento para avaliar a taxa."
    taxa = mensal["taxa"].mean()
    lo, hi = faixa
    if taxa <= meta * 1.05:       # 5% de folga: bater a meta na margem ainda é "ok"
        nivel = "ok"
    elif taxa <= meta * 1.3:      # até 30% acima da meta = atenção
        nivel = "atencao"
    else:
        nivel = "critico"

    tot = vclass["valor_total"].sum() or 1.0
    pct_med = vclass.loc[vclass.macro == "medicamento", "valor_total"].sum() / tot
    pct_pdv = vclass.loc[vclass.balde == "pdv", "valor_total"].sum() / tot
    top_cat = (vclass.groupby("cat1")["valor_total"].sum().sort_values(ascending=False))
    cat_nome = top_cat.index[0] if len(top_cat) else "—"
    cat_pct = (top_cat.iloc[0] / tot) if len(top_cat) else 0

    meta_pct = f"{meta*100:.2f}".replace(".", ",")
    taxa_pct = f"{taxa*100:.2f}".replace(".", ",")
    meta_txt = {"ok": f"na meta de {meta_pct}% (ou abaixo)",
                "atencao": f"até 30% acima da meta de {meta_pct}%",
                "critico": f"acima da meta de {meta_pct}%"}[nivel]
    if taxa > hi:
        banda_txt = "e acima da faixa de mercado de varejo farma (0,3%–0,8%)"
    elif taxa < lo:
        banda_txt = "e abaixo da faixa de mercado de varejo farma (0,3%–0,8%)"
    else:
        banda_txt = "e dentro da faixa de mercado de varejo farma (0,3%–0,8%)"
    return nivel, (
        f"Taxa média de {taxa_pct}% do faturamento — {meta_txt}, {banda_txt}. "
        f"{pct_med*100:.0f}% da perda é medicamento e {cat_pct*100:.0f}% vem de "
        f"{cat_nome.title()}. Apenas {pct_pdv*100:.0f}% é item com giro que venceu na "
        f"gôndola — a alavanca está na compra e no cadastro, não na disciplina de loja."
    )


def simular_teto(vclass: pd.DataFrame, curvas=("H", "I"), macro=None,
                 reducao: float = 0.7, n_meses: int = 6) -> dict:
    """Economia estimada se a compra de itens curva X (macro Y) fosse limitada.
    Assume que `reducao` do valor que hoje cai no balde 'compra' desse recorte é evitável."""
    d = vclass[vclass["balde"] == "compra"].copy()
    d = d[d["curva_valor"].astype(str).str.upper().isin([c.upper() for c in curvas])]
    if macro:
        d = d[d["macro"] == macro]
    base = d["valor_total"].sum()
    economia_periodo = base * reducao
    return {
        "base_periodo": base,
        "economia_periodo": economia_periodo,
        "economia_mes": economia_periodo / max(n_meses, 1),
        "produtos": int(d["produto"].nunique()),
        "linhas": int(len(d)),
    }
