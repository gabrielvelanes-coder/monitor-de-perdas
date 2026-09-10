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


# ----------------------------------------------------------------------------- #
# 1. classificação de motivo
# ----------------------------------------------------------------------------- #
# categoria -> (rótulo amigável, conta como "perda real"?)
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
    "perda_real": "Perda real (vencido + danificado + furto + descontinuado + outros)",
    "todos":      "Todos os motivos (inclui marketing, consumo, reembolso...)",
}


def in_escopo(cat: str, escopo: str) -> bool:
    if escopo == "todos":
        return cat != "ignorar"
    if escopo == "perda_real":
        return IS_PERDA_REAL.get(cat, True)
    return cat == "vencido"


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


def _cache_path(paths: list[Path]) -> Path:
    key = "|".join(f"{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}" for p in paths)
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    d = paths[0].parent / ".cache"
    d.mkdir(exist_ok=True)
    return d / f"cadastro_{h}.parquet"


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


def enriquecer_vencidos(perdas: pd.DataFrame, cad: pd.DataFrame,
                        cats=("vencido",), incluir_dep: bool = False) -> pd.DataFrame:
    p = perdas[perdas["motivo_cat"].isin(cats)].copy()
    if not incluir_dep:
        p = p[~p["is_dep"]]
    m = p.merge(cad, on=["loja", "produto"], how="left", suffixes=("", "_cad"))
    m["faixa_giro"] = m["ult_venda_dias"].map(_faixa)
    m["curva_valor"] = m["curva_valor"].fillna("sem cadastro")
    m["item_suspenso"] = m["motivo_susp"].notna() & (m["motivo_susp"].astype(str).str.strip() != "")
    m["sem_cadastro"] = m["curva_qtd"].isna() & m["mvm"].isna()
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
