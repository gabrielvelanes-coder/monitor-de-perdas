"""
Monitor de Perdas — Grupo Velanes
streamlit run app.py

Cinco telas, cada uma responde uma pergunta:
  1. Veredito .............. a perda é aceitável?
  2. Motivos ............... o que é perda de verdade e o que não é? (de-para c/ o BI)
  3. Anatomia da perda .... o que são esses itens? (medicamento? curva? giro?)
  4. Evitável x estrutural  estou dando perda em item que vende?
  5. Regras e simulação ... o que mudar e quanto economiza
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import core

st.set_page_config(page_title="Monitor de Perdas — Velanes",
                   page_icon=":material/monitoring:", layout="wide")

PASTA = Path(__file__).parent
FAT_JSON = PASTA / "faturamento.json"

BRL = lambda v: ("R$ " + f"{v:,.0f}").replace(",", ".") if pd.notna(v) else "—"
PCT = lambda v, d=2: f"{v*100:,.{d}f}%".replace(".", ",") if pd.notna(v) else "—"

COR = {"ok": "#34D399", "atencao": "#FBBF24", "critico": "#F87171", "sem_dados": "#94A3B8"}
COR_BALDE = {"pdv": "#34D399", "compra": "#FB923C", "cadastro": "#F87171", "sem_cadastro": "#94A3B8"}
CLASSE_COR = {"Vencido": "#F87171", "Outra perda real": "#FB923C", "Não é perda": "#94A3B8"}


def _cor_taxa(taxa: float, meta: float) -> str:
    """Semáforo de uma taxa contra a meta (mesma régua de frase_diagnostico)."""
    if pd.isna(taxa):
        return "sem_dados"
    if taxa <= meta * 1.05:
        return "ok"
    if taxa <= meta * 1.3:
        return "atencao"
    return "critico"


# --------------------------------------------------------------------------- #
# cargas (cache)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Lendo relatório de perdas…")
def _perdas(path, mtime):
    return core.load_perdas(path)


@st.cache_data(show_spinner="Lendo cadastro (1ª vez demora)…")
def _cadastro(paths, sig):
    return core.load_cadastro(list(paths))


@st.cache_data(show_spinner="Lendo catálogo (BASE CADASTRO COM GRUPOS)…")
def _catalogo(paths, sig):
    return core.load_catalogo(list(paths))


@st.cache_data(show_spinner="Lendo faturamento…")
def _fat_arquivo(path, mtime):
    return core.load_faturamento(path)


@st.cache_data(show_spinner="Cruzando com o cadastro…")
def _vclass(perdas_sig, cad_sig, cat_sig, cats, _perdas_df, _cad_df, _cat_df):
    enr = core.enriquecer_vencidos(_perdas_df, _cad_df, tuple(cats), catalogo=_cat_df)
    return core.classificar_vencidos(enr)


def _achar(*padroes):
    for pad in padroes:
        hits = sorted(glob.glob(str(PASTA / pad)))
        if hits:
            return hits
    return []


# --------------------------------------------------------------------------- #
# contexto: roda a cada rerun, monta sidebar e carrega tudo
# --------------------------------------------------------------------------- #
def build_context() -> dict:
    st.sidebar.markdown("### :material/monitoring: Monitor de Perdas")
    st.sidebar.caption("Grupo Velanes")

    with st.sidebar.expander("Fontes de dados", icon=":material/folder:", expanded=False):
        up_p = st.file_uploader("Relatório de perdas (.xls/.xlsx)", type=["xls", "xlsx"])
        up_c = st.file_uploader("Cadastro — arquivos DADOS (.xlsx)", type=["xlsx"],
                                accept_multiple_files=True)
        up_cat = st.file_uploader("Catálogo — BASE CADASTRO COM GRUPOS (.xlsx)",
                                  type=["xlsx"])
        up_f = st.file_uploader("Faturamento (.csv/.xlsx)", type=["csv", "xlsx"])

    # perdas (obrigatório)
    auto_p = _achar("perdas*.xls", "perdas*.xlsx", "*Baixa*Estoque*.xls*")
    if up_p is not None:
        perdas, fonte = core.load_perdas(up_p), up_p.name
    elif auto_p:
        perdas = _perdas(auto_p[0], Path(auto_p[0]).stat().st_mtime)
        fonte = Path(auto_p[0]).name
    else:
        st.error("Coloque o relatório de perdas na pasta ou envie na barra lateral.",
                 icon=":material/upload_file:")
        st.stop()

    # cadastro (opcional)
    auto_c = _achar("DADOS*.xlsx", "*cadastro*.xlsx")
    cad = None
    if up_c:
        cad = core.load_cadastro(up_c)
    elif auto_c:
        sig = tuple((Path(x).name, Path(x).stat().st_size) for x in auto_c)
        cad = _cadastro(tuple(auto_c), sig)

    # catálogo nível-produto (opcional) — só enriquece classif/curva
    auto_cat = _achar("BASE CADASTRO COM GRUPOS.xlsx", "*GRUPOS*.xlsx",
                      "*cadastro*grupos*.xlsx")
    catalogo = None
    if up_cat is not None:
        catalogo = core.load_catalogo([up_cat])
    elif auto_cat:
        csig_cat = tuple((Path(x).name, Path(x).stat().st_size) for x in auto_cat)
        catalogo = _catalogo(tuple(auto_cat), csig_cat)

    # faturamento (opcional)
    auto_f = _achar("faturamento.csv", "faturamento.xlsx", "*faturamento*.csv")
    fat = pd.DataFrame(columns=["loja", "ano_mes", "faturamento"])
    if up_f is not None:
        fat = core.load_faturamento(up_f)
    elif auto_f:
        fat = _fat_arquivo(auto_f[0], Path(auto_f[0]).stat().st_mtime)
    elif FAT_JSON.exists():
        fat = pd.DataFrame(json.loads(FAT_JSON.read_text(encoding="utf-8")))

    # filtros globais — saem de dentro das telas e valem para todas
    st.sidebar.markdown("### Filtros")
    lojas_all = sorted(int(x) for x in
                       perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())
    meses_all = sorted(perdas["ano_mes"].unique())
    lojas_sel = st.sidebar.multiselect("Lojas", lojas_all, default=[],
                                       placeholder="todas as lojas", key="g_lojas")
    meses_sel = st.sidebar.multiselect("Período (meses)", meses_all, default=[],
                                       placeholder="todo o período", key="g_meses")

    # parâmetros
    st.sidebar.markdown("### Parâmetros")
    escopo = st.sidebar.segmented_control(
        "Escopo", list(core.ESCOPOS), format_func=lambda k: core.ESCOPOS[k].split(" (")[0],
        default="vencido", selection_mode="single") or "vencido"
    meta = st.sidebar.slider("Meta (% do faturamento)", 0.1, 1.5, 0.40, 0.05,
                             format="%.2f%%") / 100
    incluir_dep = st.sidebar.toggle("Incluir depósito (DEP)", value=False)

    with st.sidebar.expander("Digitar faturamento", icon=":material/edit:"):
        _editor_faturamento(perdas, fat)

    # aplica o recorte global no que as telas consomem
    perdas_f, fat_f = perdas, fat
    if lojas_sel:
        perdas_f = perdas_f[perdas_f["loja"].isin(lojas_sel)]
        fat_f = fat_f[fat_f["loja"].isin(lojas_sel)] if not fat_f.empty else fat_f
    if meses_sel:
        perdas_f = perdas_f[perdas_f["ano_mes"].isin(meses_sel)]
        fat_f = fat_f[fat_f["ano_mes"].isin(meses_sel)] if not fat_f.empty else fat_f

    # derivados (já no recorte global)
    taxa_lm = core.taxa_por_loja_mes(perdas_f, fat_f, escopo, incluir_dep)
    mensal = core.resumo_mensal(taxa_lm)
    cob = core.cobertura_faturamento(perdas_f, fat_f)
    n_meses_perda = max(perdas_f["ano_mes"].nunique(), 1)

    psig = csig = catsig = None
    vclass = None
    if cad is not None:
        psig = (fonte, len(perdas))              # cache na base cheia; filtra depois
        csig = (len(cad), int(cad["produto"].nunique()))
        catsig = (len(catalogo),) if catalogo is not None else None
        vclass = _vclass(psig, csig, catsig, ("vencido",), perdas, cad, catalogo)
        if lojas_sel:
            vclass = vclass[vclass["loja"].isin(lojas_sel)]
        if meses_sel:
            vclass = vclass[vclass["ano_mes"].isin(meses_sel)]

    return dict(perdas=perdas_f, perdas_full=perdas, cad=cad, catalogo=catalogo,
                fat=fat_f, fonte=fonte, escopo=escopo, meta=meta,
                incluir_dep=incluir_dep, taxa_lm=taxa_lm, mensal=mensal, cob=cob,
                vclass=vclass, n_meses=n_meses_perda, lojas_sel=lojas_sel,
                meses_sel=meses_sel, psig=psig, csig=csig, catsig=catsig)


def _editor_faturamento(perdas, fat):
    st.caption("Uma linha por loja e mês. Fonte: Power BI → Receita por Und. ID.")
    lojas = sorted(int(x) for x in perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())
    meses = sorted(perdas["ano_mes"].unique())
    base = fat.copy() if not fat.empty else pd.DataFrame(
        [(l, meses[-1] if meses else "2026-01", 0.0) for l in lojas],
        columns=["loja", "ano_mes", "faturamento"])
    ed = st.data_editor(base, num_rows="dynamic", width="stretch", key="fat_ed")
    st.caption("Só é usado quando **não há** `faturamento.csv` na pasta — o arquivo "
               "tem prioridade sobre o que for digitado aqui.")
    if st.button("Salvar", icon=":material/save:"):
        c = ed.dropna(subset=["loja", "ano_mes", "faturamento"])
        c = c[c["faturamento"] > 0]
        FAT_JSON.write_text(c.to_json(orient="records"), encoding="utf-8")
        st.toast("Faturamento salvo.", icon=":material/check:")
        st.rerun()


CTX = build_context()


# --------------------------------------------------------------------------- #
# helpers de UI
# --------------------------------------------------------------------------- #
def _sem_faturamento_aviso():
    if CTX["fat"].empty:
        st.warning("Sem faturamento informado — os percentuais não são calculados. "
                   "Envie um arquivo ou digite na barra lateral.",
                   icon=":material/warning:")
        return True
    return False


def _falta_cadastro():
    if CTX["vclass"] is None:
        st.info("Envie os arquivos **DADOS** (cadastro) na barra lateral para esta análise.",
                icon=":material/dataset:")
        return True
    return False


def _recorte_txt() -> str:
    """Descrição do filtro global ativo, para o cabeçalho de cada tela."""
    ls, ms = CTX["lojas_sel"], CTX["meses_sel"]
    a = "todas as lojas" if not ls else "lojas " + ", ".join(str(x) for x in ls)
    b = "todo o período" if not ms else ", ".join(ms)
    return f"{a} · {b}"


def _loja_local(df: pd.DataFrame, key: str, container=None) -> list[int]:
    """Multiselect de Lojas dentro da tela, restringindo o recorte global.
    Não aparece quando o recorte já tem 0 ou 1 loja."""
    c = container if container is not None else st
    lojas = sorted(int(x) for x in df["loja"].dropna().unique())
    if len(lojas) <= 1:
        return []
    return c.multiselect(
        "Lojas (nesta tela)", lojas, default=[], key=key,
        placeholder="todas as lojas do recorte",
        help="Restringe ainda mais dentro do filtro global da barra lateral.")


def _mes_local(df: pd.DataFrame, key: str, container=None) -> list[str]:
    """Multiselect de Meses dentro da tela, restringindo o recorte global.
    Não aparece quando o recorte já tem 0 ou 1 mês."""
    c = container if container is not None else st
    meses = sorted(df["ano_mes"].dropna().unique())
    if len(meses) <= 1:
        return []
    return c.multiselect(
        "Meses (nesta tela)", meses, default=[], key=key,
        placeholder="todos os meses do recorte",
        help="Vazio = todos os meses do filtro global.")


# motivos que a Anatomia pode enxergar (além do vencido, que é o default do CTX)
MOTIVO_OPCOES = {
    "Vencido": ("vencido",),
    "Danificado": ("danificado",),
    "Furto ou roubo": ("furto",),
    "Descontinuado": ("descontinuado",),
    "Perda real (venc.+danif.+furto+descont.+outros)":
        tuple(k for k in core.CATS if k != "ignorar" and core.IS_PERDA_REAL.get(k, True)),
    "Todos os motivos": tuple(k for k in core.CATS if k != "ignorar"),
}


def _vclass_recorte(cats):
    """vclass (enriquecido + classificado) para um conjunto de motivos, já
    aplicado o recorte global de loja/mês. Cacheado por motivo em `_vclass`."""
    v = _vclass(CTX["psig"], CTX["csig"], CTX["catsig"], tuple(cats),
                CTX["perdas_full"], CTX["cad"], CTX["catalogo"])
    if CTX["lojas_sel"]:
        v = v[v["loja"].isin(CTX["lojas_sel"])]
    if CTX["meses_sel"]:
        v = v[v["ano_mes"].isin(CTX["meses_sel"])]
    return v


# =========================================================================== #
# TELA 1 — PAINEL (resumo executivo — respeita o filtro global)
# =========================================================================== #
def tela_veredito():
    st.title("Painel")
    esc, meta, incluir_dep = CTX["escopo"], CTX["meta"], CTX["incluir_dep"]
    st.caption(f"Escopo: {core.ESCOPOS[esc]} · recorte global: {_recorte_txt()} · "
               f"fonte `{CTX['fonte']}`")

    # ---- filtros da tela: mês e loja (dentro do recorte global) --------- #
    perdas, fat = CTX["perdas"], CTX["fat"]
    c_mes, c_loja = st.columns(2)
    msel = _mes_local(perdas, "pnl_meses", c_mes)
    if msel:
        perdas = perdas[perdas["ano_mes"].isin(msel)]
        fat = fat[fat["ano_mes"].isin(msel)] if not fat.empty else fat
    lsel = _loja_local(perdas, "pnl_lojas", c_loja)
    if lsel:
        perdas = perdas[perdas["loja"].isin(lsel)]
        fat = fat[fat["loja"].isin(lsel)] if not fat.empty else fat
    if msel or lsel:
        st.caption("Refinado nesta tela: "
                   + (", ".join(sorted(msel)) if msel else "todos os meses") + " · "
                   + ("lojas " + ", ".join(str(x) for x in lsel) if lsel else "todas as lojas"))

    if perdas.empty:
        st.info("Sem lançamentos nesse recorte.", icon=":material/info:")
        return

    # ---- derivados no recorte da tela --------------------------------- #
    taxa_lm = core.taxa_por_loja_mes(perdas, fat, esc, incluir_dep)
    m = core.resumo_mensal(taxa_lm)
    cob = core.cobertura_faturamento(perdas, fat)
    nmes = max(perdas["ano_mes"].nunique(), 1)
    vc = CTX["vclass"]
    if vc is not None:
        if msel:
            vc = vc[vc["ano_mes"].isin(msel)]
        if lsel:
            vc = vc[vc["loja"].isin(lsel)]

    if m.empty:
        _sem_faturamento_aviso()
        mm = (perdas[perdas["motivo_cat"].map(lambda c: core.in_escopo(c, esc))]
              .groupby("ano_mes")["valor_total"].sum().reset_index())
        st.subheader("Valor da perda por mês")
        st.bar_chart(mm, x="ano_mes", y="valor_total", height=260)
        return

    fat_tot = m["faturamento"].sum()
    perda_tot = m["perda"].sum()
    taxa_pond = perda_tot / fat_tot if fat_tot else float("nan")
    taxa_media = m["taxa"].mean()
    gap_pp = (taxa_pond - meta) * 100
    n = len(m)
    periodo_txt = (f"{m['ano_mes'].iloc[0]}…{m['ano_mes'].iloc[-1]}" if n > 1
                   else m["ano_mes"].iloc[0])

    nivel, frase = ("sem_dados", "")
    recuperavel = 0.0
    if vc is not None and not vc.empty:
        nivel, frase = core.frase_diagnostico(m, vc, meta)
        rb = core.resumo_baldes(vc, nmes)
        recuperavel = rb.loc[rb["balde"].isin(["compra", "cadastro"]), "valor_mes"].sum()
    nivel_show = nivel if nivel != "sem_dados" else _cor_taxa(taxa_pond, meta)

    # ---- KPIs do topo -------------------------------------------------- #
    with st.container(horizontal=True):
        st.metric(f"Faturamento ({n} {'mês' if n == 1 else 'meses'})", BRL(fat_tot),
                  border=True, help=f"Meses com faturamento no recorte: {periodo_txt}.")
        st.metric("Perda no período", BRL(perda_tot), border=True,
                  help=f"Motivos no escopo '{core.ESCOPOS[esc].split(' (')[0]}'.")
        st.metric("Taxa de perdas", PCT(taxa_pond), border=True,
                  help="Ponderada: perda total ÷ faturamento total do recorte.")
        st.metric("Gap vs meta", f"{gap_pp:+.2f} p.p.".replace(".", ","),
                  delta=f"meta {PCT(meta)}", delta_color="off", border=True)

    # ---- diagnóstico (semáforo + frase) ------------------------------- #
    with st.container(border=True):
        c1, c2 = st.columns([1, 2], vertical_alignment="center")
        with c1:
            rot = {"ok": "ACEITÁVEL", "atencao": "ATENÇÃO", "critico": "CRÍTICO",
                   "sem_dados": "—"}[nivel_show]
            cor = COR[nivel_show]
            st.markdown(
                f"<div style='font-size:0.8rem;color:#94A3B8;text-transform:uppercase;"
                f"letter-spacing:.08em'>Taxa média mensal</div>"
                f"<div style='font-size:3rem;font-weight:700;line-height:1.1'>{PCT(taxa_media)}</div>"
                f"<div style='display:inline-block;margin-top:.4rem;padding:.15rem .6rem;"
                f"border-radius:999px;background:{cor}22;color:{cor};"
                f"font-weight:600;font-size:.85rem'>{rot}</div>",
                unsafe_allow_html=True)
        with c2:
            st.markdown(f"**Diagnóstico.** {frase}" if frase else
                        "Envie o cadastro (DADOS) para o diagnóstico automático.")
            if recuperavel:
                st.caption(f":material/savings: Recuperável ~{BRL(recuperavel)}/mês nos "
                           "baldes 'excesso de compra' + 'item suspenso' — alavanca de "
                           "compra e cadastro, não de disciplina de loja.")

    # ---- evolução mensal + ranking de lojas -------------------------- #
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Taxa de perdas por mês** (% do faturamento · tracejado = meta)")
            d = m[["ano_mes", "taxa"]].copy()
            d["taxa"] *= 100
            d["meta"] = meta * 100
            base = alt.Chart(d).encode(x=alt.X("ano_mes:N", title=None))
            linha = base.mark_line(point=True, strokeWidth=2, color=COR["atencao"]).encode(
                y=alt.Y("taxa:Q", title="%"),
                tooltip=["ano_mes", alt.Tooltip("taxa:Q", format=".2f")])
            meta_l = base.mark_rule(strokeDash=[4, 4], color="#94A3B8").encode(y="meta:Q")
            st.altair_chart(linha + meta_l, width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Lojas por taxa de perdas** (% no período · tracejado = meta)")
            rl = (taxa_lm.dropna(subset=["faturamento"])
                  .groupby("loja", as_index=False)
                  .agg(perda=("perda", "sum"), faturamento=("faturamento", "sum")))
            if rl.empty:
                st.caption("Nenhuma loja com faturamento no recorte.")
            else:
                rl["taxa"] = rl["perda"] / rl["faturamento"] * 100
                rl["loja"] = rl["loja"].astype("Int64").astype(str)
                rl["nivel"] = rl["taxa"].map(lambda t: _cor_taxa(t / 100, meta))
                barras = alt.Chart(rl).mark_bar().encode(
                    x=alt.X("taxa:Q", title="% do faturamento"),
                    y=alt.Y("loja:N", sort="-x", title="Loja"),
                    color=alt.Color("nivel:N", scale=alt.Scale(
                        domain=["ok", "atencao", "critico"],
                        range=[COR["ok"], COR["atencao"], COR["critico"]]), legend=None),
                    tooltip=["loja", alt.Tooltip("taxa:Q", title="taxa %", format=".2f"),
                             alt.Tooltip("perda:Q", title="perda R$", format=",.0f"),
                             alt.Tooltip("faturamento:Q", title="faturamento R$", format=",.0f")])
                meta_r = alt.Chart(pd.DataFrame({"m": [meta * 100]})).mark_rule(
                    strokeDash=[4, 4], color="#94A3B8").encode(x="m:Q")
                st.altair_chart(barras + meta_r, width="stretch")

    # ---- bridge de escopo + top motivos ---------------------------- #
    p = perdas
    if not incluir_dep:
        p = p[~p["is_dep"]]
    p = p[p["motivo_cat"] != "ignorar"].copy()
    meses_cf = cob["meses_com_faturamento"]
    p_cf = p[p["ano_mes"].isin(meses_cf)]

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Bridge de escopo** — mesmo relatório, três recortes")
            for key, rot in [("vencido", "Somente vencidos"),
                             ("perda_real", "Perda real"),
                             ("todos", "Todos os motivos")]:
                v_mes = p.loc[p["motivo_cat"].map(lambda c: core.in_escopo(c, key)),
                              "valor_total"].sum() / nmes
                pf = ((p_cf.loc[p_cf["motivo_cat"].map(lambda c: core.in_escopo(c, key)),
                                "valor_total"].sum() / fat_tot) if fat_tot else float("nan"))
                st.metric(rot, BRL(v_mes) + " /mês",
                          delta=PCT(pf) + " do faturamento", delta_color="off", border=True)
    with right:
        with st.container(border=True):
            st.markdown("**Top motivos** (R$ no período · cor = classe)")
            gm = (p.assign(classe=p["motivo_cat"].map(core.classe_motivo))
                  .groupby(["motivo_label", "classe"], as_index=False)["valor_total"].sum()
                  .sort_values("valor_total", ascending=False).head(8))
            ch = alt.Chart(gm).mark_bar().encode(
                x=alt.X("valor_total:Q", title="R$ no período"),
                y=alt.Y("motivo_label:N", sort="-x", title=None),
                color=alt.Color("classe:N", scale=alt.Scale(
                    domain=list(CLASSE_COR), range=list(CLASSE_COR.values())),
                    legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["motivo_label", "classe",
                         alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")

    # ---- meses sem faturamento (perda em R$) ---------------------- #
    meses_sf = cob["meses_sem_faturamento"]
    if meses_sf:
        ps = p[p["motivo_cat"].map(lambda c: core.in_escopo(c, esc))
               & p["ano_mes"].isin(meses_sf)]
        mm = ps.groupby("ano_mes", as_index=False)["valor_total"].sum()
        if not mm.empty:
            with st.container(border=True):
                st.markdown("**Meses sem faturamento informado** — perda em R$ "
                            "(taxa % indisponível)")
                st.caption("Complete o `faturamento.csv` (ou a barra lateral) com "
                           + ", ".join(meses_sf) + " para ver a taxa desses meses.")
                ch = alt.Chart(mm).mark_bar(color="#94A3B8").encode(
                    x=alt.X("ano_mes:N", title=None),
                    y=alt.Y("valor_total:Q", title="R$ perda"),
                    tooltip=["ano_mes", alt.Tooltip("valor_total:Q", format=",.0f")])
                st.altair_chart(ch, width="stretch")

    # ---- bater com o número da reunião --------------------------- #
    with st.expander("Bater com o número da reunião", icon=":material/calculate:"):
        v = st.number_input("Valor apresentado (R$/mês)", value=0.0, step=1000.0)
        pp = st.number_input("ou % apresentado", value=0.0, step=0.1) / 100
        pm = m["perda"].mean()
        if v and pm:
            st.write(f"Dados: **{BRL(pm)}/mês** · diferença "
                     f"**{BRL(v - pm)}** ({(v/pm-1)*100:+.0f}%)")
        elif v:
            st.write(f"Dados: **{BRL(pm)}/mês** · diferença **{BRL(v - pm)}**")
        if pp and taxa_pond:
            st.write(f"Dados: **{PCT(taxa_pond)}** · diferença **{(pp-taxa_pond)*100:+.2f} p.p.**")

    if meses_sf or cob["lojas_sem_faturamento"]:
        avisos = []
        if meses_sf:
            avisos.append("meses sem faturamento: " + ", ".join(meses_sf))
        if cob["lojas_sem_faturamento"]:
            avisos.append("lojas sem faturamento: " +
                          ", ".join(str(int(x)) for x in cob["lojas_sem_faturamento"]))
        st.caption(" · ".join(avisos) + " — ficam fora do cálculo de %.")


# =========================================================================== #
# TELA 2 — MOTIVOS (de-para: o que é perda de verdade e o que não é)
# =========================================================================== #
def tela_motivos():
    st.title("O que é o quê?")
    st.caption("Cada motivo de baixa de estoque: quanto pesa em R$ e em % do faturamento, "
               "e se é perda de verdade. É o de-para que explica a diferença entre a taxa "
               "da ferramenta (só vencidos) e o %perda/fat do Power BI (todos os motivos).")

    p = CTX["perdas"]
    if not CTX["incluir_dep"]:
        p = p[~p["is_dep"]]
    p = p[p["motivo_cat"] != "ignorar"].copy()
    p["classe"] = p["motivo_cat"].map(core.classe_motivo)

    fat = CTX["fat"]
    st.caption("Recorte (filtro global): " + _recorte_txt())
    if p.empty:
        st.info("Sem lançamentos nesse recorte.", icon=":material/info:")
        return

    c_mes, c_loja = st.columns(2)
    msel = _mes_local(p, "mot_meses", c_mes)
    if msel:
        p = p[p["ano_mes"].isin(msel)]
        fat = fat[fat["ano_mes"].isin(msel)] if not fat.empty else fat
    lsel = _loja_local(p, "mot_lojas", c_loja)
    if lsel:
        p = p[p["loja"].isin(lsel)]
        fat = fat[fat["loja"].isin(lsel)] if not fat.empty else fat
    if p.empty:
        st.info("Sem lançamentos nesse recorte da tela.", icon=":material/info:")
        return

    sel = sorted(p["ano_mes"].unique())            # meses do recorte (global + tela)
    meses_com_fat = (sorted(set(fat["ano_mes"].unique()) & set(sel))
                     if not fat.empty else [])
    n_meses = max(len(sel), 1)

    meses_sel_com_fat = [m for m in sel if m in meses_com_fat]
    meses_sel_sem_fat = [m for m in sel if m not in meses_com_fat]
    fat_com = (fat.loc[fat["ano_mes"].isin(meses_sel_com_fat), "faturamento"].sum()
               if meses_sel_com_fat else 0.0)
    p_fat = p[p["ano_mes"].isin(meses_sel_com_fat)]

    def _pct_fat(valor_nos_meses_com_fat):
        return valor_nos_meses_com_fat / fat_com if fat_com else float("nan")

    # ---- 3 cartões: bridge de escopo ------------------------------------- #
    st.markdown("**Bridge de escopo** — mesmo relatório, três recortes")
    escs = [("vencido", "Somente vencidos"),
            ("perda_real", "Perda real"),
            ("todos", "Todos os motivos")]
    with st.container(horizontal=True):
        for key, rot in escs:
            mask = p["motivo_cat"].map(lambda c: core.in_escopo(c, key))
            valor_mes = p.loc[mask, "valor_total"].sum() / n_meses
            mask_f = p_fat["motivo_cat"].map(lambda c: core.in_escopo(c, key))
            pct = _pct_fat(p_fat.loc[mask_f, "valor_total"].sum())
            st.metric(rot, BRL(valor_mes) + " /mês",
                      delta=PCT(pct) + " do faturamento", delta_color="off", border=True)

    if meses_sel_sem_fat:
        st.caption(f":material/info: {', '.join(meses_sel_sem_fat)} sem faturamento "
                   "informado — entra no R$/mês, mas fica fora do cálculo de %.")

    # ---- tabela por motivo --------------------------------------------- #
    g = (p.groupby(["motivo_cat", "motivo_label", "classe"], as_index=False)
         .agg(valor=("valor_total", "sum"), linhas=("valor_total", "size")))
    g["valor_mes"] = g["valor"] / n_meses
    total_lancado = g["valor"].sum() or 1.0
    g["pct_lancado"] = g["valor"] / total_lancado
    vfat = p_fat.groupby("motivo_cat")["valor_total"].sum()
    g["pct_fat"] = g["motivo_cat"].map(lambda c: _pct_fat(vfat.get(c, 0.0)))
    g = g.sort_values("valor", ascending=False).reset_index(drop=True)

    with st.container(border=True):
        st.markdown("**Por motivo** (período: " + ", ".join(sel) + ")")
        st.dataframe(
            g[["motivo_label", "classe", "valor", "valor_mes", "pct_fat",
               "pct_lancado", "linhas"]],
            hide_index=True, width="stretch",
            column_config={
                "motivo_label": "Motivo",
                "classe": "Classe",
                "valor": st.column_config.NumberColumn("R$ no período", format="R$ %.0f"),
                "valor_mes": st.column_config.NumberColumn("R$/mês", format="R$ %.0f"),
                "pct_fat": st.column_config.NumberColumn("% do faturamento", format="percent"),
                "pct_lancado": st.column_config.NumberColumn("% do lançado", format="percent"),
                "linhas": "Linhas"})

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Peso de cada motivo** (R$ no período, cor = classe)")
            ch = alt.Chart(g).mark_bar().encode(
                x=alt.X("valor:Q", title="R$ no período"),
                y=alt.Y("motivo_label:N", sort="-x", title=None),
                color=alt.Color("classe:N", scale=alt.Scale(
                    domain=list(CLASSE_COR), range=list(CLASSE_COR.values())),
                    legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["motivo_label", "classe",
                         alt.Tooltip("valor:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Por mês, empilhado por classe**")
            gm = p.groupby(["ano_mes", "classe"], as_index=False)["valor_total"].sum()
            ch2 = alt.Chart(gm).mark_bar().encode(
                x=alt.X("ano_mes:N", title=None),
                y=alt.Y("valor_total:Q", title="R$"),
                color=alt.Color("classe:N", scale=alt.Scale(
                    domain=list(CLASSE_COR), range=list(CLASSE_COR.values())),
                    legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["ano_mes", "classe",
                         alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch2, width="stretch")


# =========================================================================== #
# TELA 3 — ANATOMIA DA PERDA
# =========================================================================== #
def _picked(event, field):
    """Valores selecionados num st.altair_chart(on_select=...) — tolera formatos."""
    try:
        sel = event["selection"]
    except (KeyError, TypeError):
        return []
    linhas = []
    for v in sel.values():
        if isinstance(v, list):
            linhas.extend(v)
    return [r[field] for r in linhas if isinstance(r, dict) and field in r]


MACRO_ROT = {"medicamento": "Medicamento", "nao-medicamento": "Não-medicamento",
             "sem classificacao": "Sem classificação"}
ORD_LETRA = list("ABCDEFGHI") + ["Sem cadastro"]


def _cletra(s) -> str:
    """Letra da curva (A…I) ou 'Sem cadastro'."""
    x = str(s).strip().upper()
    return x if x in set("ABCDEFGHI") else "Sem cadastro"


def tela_anatomia():
    st.title("O que são esses itens?")
    if _falta_cadastro():
        return
    st.caption("Recorte (filtro global): " + _recorte_txt())

    # ---- motivo + filtros da tela (mês e loja, dentro do recorte global) --- #
    c_mot, c_mes, c_loja = st.columns([2, 1, 1])
    mot_label = c_mot.selectbox(
        "Motivo da baixa", list(MOTIVO_OPCOES), key="anat_motivo",
        help="A Anatomia olha vencidos por padrão. Troque para ver a mesma "
             "anatomia (medicamento / curva / giro) de outro motivo de baixa.")
    cats = MOTIVO_OPCOES[mot_label]
    vc = (CTX["vclass"] if cats == ("vencido",) else _vclass_recorte(cats)).copy()
    mot_curto = mot_label.split(" (")[0]
    unidade = "do total" if cats != ("vencido",) else "do vencido"

    msel = _mes_local(vc, "anat_meses", c_mes)
    if msel:
        vc = vc[vc["ano_mes"].isin(msel)]
    lsel = _loja_local(vc, "anat_lojas", c_loja)
    if lsel:
        vc = vc[vc["loja"].isin(lsel)]

    # filtro por status no catálogo (só quando o catálogo está carregado)
    tem_cat = CTX["catalogo"] is not None and "status_cadastro" in vc.columns
    if tem_cat:
        _s = vc["status_cadastro"].astype(str).str.strip().str.lower()
        fora_cat = vc["status_cadastro"].isna() | _s.isin(["", "nan", "none"])
        stat = st.radio("Status no catálogo",
                        ["Todos", "Ativos", "Inativos", "Fora do catálogo"],
                        horizontal=True, key="anat_status",
                        help="Status do produto na BASE CADASTRO COM GRUPOS.")
        if stat == "Ativos":
            vc = vc[_s.eq("ativo")]
        elif stat == "Inativos":
            vc = vc[_s.eq("inativo")]
        elif stat == "Fora do catálogo":
            vc = vc[fora_cat]

    if vc.empty:
        st.info(f"Sem baixas de \"{mot_curto}\" nesse recorte.", icon=":material/info:")
        return
    tot_real = vc["valor_total"].sum()
    tot = tot_real or 1.0
    und_real = int(vc["itens"].sum())
    tip_val = alt.Tooltip("valor_total:Q", title="R$ perda", format=",.0f")
    tip_itens = alt.Tooltip("itens:Q", title="Unidades", format=",.0f")

    # ---- macro: total + medicamento / não / sem classificação --------- #
    macro = (vc.groupby("macro", as_index=False)["valor_total"].sum()
             .sort_values("valor_total", ascending=False))
    macro["pct"] = macro["valor_total"] / tot
    with st.container(horizontal=True):
        st.metric(f"Total — {mot_curto.lower()}", BRL(tot_real),
                  delta=f"{und_real:,} unid · {len(vc):,} linhas".replace(",", "."),
                  delta_color="off", border=True)
        for _, r in macro.iterrows():
            st.metric(MACRO_ROT.get(r["macro"], r["macro"].capitalize()),
                      BRL(r["valor_total"]),
                      delta=f"{r['pct']*100:.0f}% {unidade}", delta_color="off", border=True)
    sc = macro.loc[macro["macro"] == "sem classificacao", "valor_total"].sum()
    if sc:
        st.caption(f":material/help: **Sem classificação** = {BRL(sc)} em itens sem "
                   "`classif` no cadastro (não caem em medicamento nem não-medicamento). "
                   "Escolha \"Só sem classificação\" no seletor **Ver** para listá-los "
                   "na tabela do fim da página.")

    if "anat_nonce" not in st.session_state:
        st.session_state["anat_nonce"] = 0
    nk = st.session_state["anat_nonce"]

    st.caption("Clique numa barra para filtrar a tabela de produtos no fim da página; "
               "clique de novo na mesma barra para soltar. Ou use "
               "\"Limpar filtros dos gráficos\".")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            h, ctrl = st.columns([3, 2], vertical_alignment="center")
            h.markdown("**Por categoria da árvore mercadológica**")
            medida = ctrl.radio("Medida", ["R$ vencido", "Unidades"], horizontal=True,
                                key="anat_medida", label_visibility="collapsed",
                                help="Eixo dos três gráficos: R$ vencido ou nº de unidades.")
            mcol = "valor_total" if medida == "R$ vencido" else "itens"
            mtitle = "R$ vencido" if medida == "R$ vencido" else "Unidades vencidas"
            gsel = st.segmented_control(
                "Ver", ["Todas", "Só medicamento", "Só não-medicamento",
                        "Só sem classificação"],
                default="Todas", label_visibility="collapsed", key="anat_ver")
            d0 = vc
            if gsel == "Só medicamento":
                d0 = vc[vc["macro"] == "medicamento"]
            elif gsel == "Só não-medicamento":
                d0 = vc[vc["macro"] == "nao-medicamento"]
            elif gsel == "Só sem classificação":
                d0 = vc[vc["macro"] == "sem classificacao"]
            cat = (d0.groupby("cat1", as_index=False)
                   .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum"))
                   .sort_values(mcol, ascending=False).head(12))
            sel_cat = alt.selection_point(fields=["cat1"], name="pcat", toggle="true")
            base_cat = alt.Chart(cat).encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("cat1:N", sort="-x", title=None))
            ch = (base_cat.mark_bar(color="#60A5FA").encode(
                opacity=alt.condition(sel_cat, alt.value(1.0), alt.value(0.35)),
                tooltip=["cat1", tip_val, tip_itens]).add_params(sel_cat))
            lbl_cat = base_cat.mark_text(align="left", dx=4, color="#CBD5E1",
                                         fontSize=11).encode(
                text=alt.Text(f"{mcol}:Q", format=",.0f"))
            ev_cat = st.altair_chart(ch + lbl_cat, width="stretch", on_select="rerun",
                                     key=f"anat_ch_cat_{nk}")
    with right:
        with st.container(border=True):
            h, ctrl = st.columns([3, 2], vertical_alignment="center")
            h.markdown("**Curva**")
            qual = ctrl.radio("Curva", ["Valor", "Quantidade"], horizontal=True,
                              key="anat_curva", label_visibility="collapsed",
                              help="Curva de valor ou curva de quantidade do cadastro.")
            col_curva = "curva_qtd" if qual == "Quantidade" else "curva_valor"
            vc["cletra"] = vc[col_curva].map(_cletra)
            g = (vc.groupby("cletra", as_index=False)
                 .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum")))
            sel_cv = alt.selection_point(fields=["cletra"], name="pcg", toggle="true")
            base_cv = alt.Chart(g).encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("cletra:N", sort=ORD_LETRA, title=None))
            ch = (base_cv.mark_bar(color="#60A5FA").encode(
                opacity=alt.condition(sel_cv, alt.value(1.0), alt.value(0.35)),
                tooltip=["cletra", tip_val, tip_itens]).add_params(sel_cv))
            lbl_cv = base_cv.mark_text(align="left", dx=4, color="#CBD5E1", fontSize=11).encode(
                text=alt.Text(f"{mcol}:Q", format=",.0f"))
            ev_cv = st.altair_chart(ch + lbl_cv, width="stretch", on_select="rerun",
                                    key=f"anat_ch_cv_{nk}")
            st.markdown("**Quanto tempo parado quando venceu**")
            fg = (vc.groupby("faixa_giro", as_index=False)
                  .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum")))
            ordem_g = [x[2] for x in core.FAIXAS_GIRO] + ["Sem cadastro"]
            sel_g = alt.selection_point(fields=["faixa_giro"], name="pgiro", toggle="true")
            base_g = alt.Chart(fg).encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("faixa_giro:N", sort=ordem_g, title=None))
            ch2 = (base_g.mark_bar(color="#FB923C").encode(
                opacity=alt.condition(sel_g, alt.value(1.0), alt.value(0.35)),
                tooltip=["faixa_giro", tip_val, tip_itens]).add_params(sel_g))
            lbl_g = base_g.mark_text(align="left", dx=4, color="#CBD5E1", fontSize=11).encode(
                text=alt.Text(f"{mcol}:Q", format=",.0f"))
            ev_g = st.altair_chart(ch2 + lbl_g, width="stretch", on_select="rerun",
                                   key=f"anat_ch_giro_{nk}")

    # ---- tabela de produtos, filtrada pelo que foi clicado nos gráficos ---- #
    d = vc
    filtros = []
    cats_sel = _picked(ev_cat, "cat1")
    if cats_sel:
        d = d[d["cat1"].isin(cats_sel)]
        filtros.append(("Categoria", ", ".join(map(str, cats_sel))))
    cg_sel = _picked(ev_cv, "cletra")
    if cg_sel:
        d = d[d["cletra"].isin(cg_sel)]
        filtros.append((f"Curva ({qual.lower()})", ", ".join(map(str, cg_sel))))
    giro_sel = _picked(ev_g, "faixa_giro")
    if giro_sel:
        d = d[d["faixa_giro"].isin(giro_sel)]
        filtros.append(("Tempo parado", ", ".join(map(str, giro_sel))))

    if filtros and st.button("Limpar filtros dos gráficos",
                             icon=":material/filter_alt_off:", key="anat_clear"):
        st.session_state["anat_nonce"] += 1
        st.rerun()

    with st.container(border=True):
        if filtros:
            st.markdown("**Produtos — " +
                        " · ".join(f"{k}: {v}" for k, v in filtros) + "**")
            st.caption(f"{len(d)} linhas de {mot_curto.lower()} · "
                       f"{BRL(d['valor_total'].sum())} · "
                       f"{d['itens'].sum():,.0f} unidades no recorte filtrado."
                       .replace(",", "."))
        else:
            st.markdown(f"**Produtos** — todos os itens de \"{mot_curto}\" no recorte")
            st.caption("Clique numa barra dos gráficos acima para filtrar aqui. "
                       "Clique nos cabeçalhos da tabela para ordenar.")
        agg = dict(valor=("valor_total", "sum"), itens=("itens", "sum"),
                   curva_valor=("curva_valor", "first"), curva_qtd=("curva_qtd", "first"),
                   macro=("macro", "first"), cat=("cat1", "first"),
                   faixa_giro=("faixa_giro", "first"),
                   dias_sem_vender=("ult_venda_dias", "max"),
                   n_lojas=("loja", "nunique"),
                   lojas_ids=("loja", lambda s: ", ".join(
                       str(int(x)) for x in sorted(s.dropna().unique()))))
        if tem_cat:
            agg["status_cadastro"] = ("status_cadastro", "first")
        tab = (d.groupby("produto", as_index=False).agg(**agg)
               .sort_values("valor", ascending=False).head(300))
        st.dataframe(tab, hide_index=True, width="stretch", height=360,
                     column_config={
                         "produto": "Produto",
                         "valor": st.column_config.NumberColumn("Total perda (R$)",
                                                                format="R$ %.0f"),
                         "itens": st.column_config.NumberColumn("Unidades", format="%.0f"),
                         "curva_valor": "Curva valor", "curva_qtd": "Curva qtd",
                         "macro": "Categoria", "cat": "Árvore nível 1",
                         "faixa_giro": "Tempo parado",
                         "dias_sem_vender": "Dias s/ vender",
                         "n_lojas": "Nº lojas",
                         "lojas_ids": "Lojas (ID)",
                         "status_cadastro": "Status catálogo"})
        st.caption("As lojas são identificadas por número (2–25); não há nome de loja "
                   "no relatório de perdas. **Lojas (ID)** lista as lojas que "
                   f"baixaram o item por \"{mot_curto.lower()}\"; **Unidades** é a "
                   "quantidade total.")
        slug = re.sub(r"[^a-z0-9]+", "_", mot_curto.lower()).strip("_")
        st.download_button("Baixar (CSV)", tab.to_csv(index=False).encode("utf-8-sig"),
                           f"anatomia_{slug}.csv", "text/csv",
                           icon=":material/download:", key="anat_dl")


# =========================================================================== #
# TELA 4 — EVITÁVEL x ESTRUTURAL
# =========================================================================== #
def tela_baldes():
    st.title("Estou dando perda em item que vende?")
    if _falta_cadastro():
        return
    st.caption("Recorte (filtro global): " + _recorte_txt())
    vc = CTX["vclass"]
    c_mes, c_loja = st.columns(2)
    msel = _mes_local(vc, "bald_meses", c_mes)
    if msel:
        vc = vc[vc["ano_mes"].isin(msel)]
    lsel = _loja_local(vc, "bald_lojas", c_loja)
    if lsel:
        vc = vc[vc["loja"].isin(lsel)]
    if vc.empty:
        st.info("Sem vencidos nesse recorte.", icon=":material/info:")
        return
    nm = max(vc["ano_mes"].nunique(), 1)
    rb = core.resumo_baldes(vc, nm)
    tot_mes = rb["valor_mes"].sum()

    st.caption("Cada real de vencido classificado por **onde a perda foi decidida**.")
    with st.container(horizontal=True):
        for _, r in rb.iterrows():
            st.metric(r["balde_label"].split(" (")[0], BRL(r["valor_mes"]) + " /mês",
                      delta=f"{r['pct']*100:.0f}% do vencido", delta_color="off",
                      border=True, help=r["acao"])

    left, right = st.columns([2, 3])
    with left:
        with st.container(border=True):
            st.markdown("**Composição**")
            d = rb.copy()
            d["k"] = d["balde_label"].str.split(" \\(").str[0]
            ch = alt.Chart(d).mark_bar().encode(
                x=alt.X("valor:Q", stack="normalize", title="% do vencido", axis=alt.Axis(format="%")),
                y=alt.Y("k:N", sort=list(d["k"]), title=None),
                color=alt.Color("balde:N", scale=alt.Scale(
                    domain=list(COR_BALDE), range=list(COR_BALDE.values())), legend=None),
                tooltip=["balde_label", alt.Tooltip("valor:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Lojas — perda por balde** (R$ no período)")
            gl = (vc.groupby(["loja", "balde"], as_index=False)["valor_total"].sum())
            gl["loja"] = gl["loja"].astype("Int64").astype(str)
            ordem_loja = (gl.groupby("loja")["valor_total"].sum()
                          .sort_values(ascending=False).index.tolist())
            ch = alt.Chart(gl).mark_bar().encode(
                x=alt.X("valor_total:Q", title="R$ vencido"),
                y=alt.Y("loja:N", sort=ordem_loja, title="Loja"),
                color=alt.Color("balde:N", scale=alt.Scale(
                    domain=list(COR_BALDE), range=list(COR_BALDE.values())),
                    legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["loja", "balde", alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")

    st.markdown("### Detalhe por balde")
    for _, r in rb.iterrows():
        with st.expander(f"{r['balde_label']} — {BRL(r['valor'])}  ·  {r['produtos']} produtos",
                         icon=":material/list:"):
            st.caption(f":material/bolt: **Ação:** {r['acao']}")
            d = vc[vc["balde"] == r["balde"]]
            tab = (d.groupby("produto", as_index=False)
                   .agg(valor=("valor_total", "sum"), curva_valor=("curva_valor", "first"),
                        curva_qtd=("curva_qtd", "first"), macro=("macro", "first"),
                        dias_sem_vender=("ult_venda_dias", "max"), lojas=("loja", "nunique"))
                   .sort_values("valor", ascending=False).head(80))
            st.dataframe(tab, hide_index=True, width="stretch", height=280,
                         column_config={"valor": st.column_config.NumberColumn("R$", format="R$ %.0f"),
                                        "curva_valor": "Curva valor", "curva_qtd": "Curva qtd",
                                        "dias_sem_vender": "Dias s/ vender"})


# =========================================================================== #
# TELA 5 — REGRAS E SIMULAÇÃO
# =========================================================================== #
def tela_regras():
    st.title("O que mudar — e quanto economiza")
    if _falta_cadastro():
        return
    st.caption("Recorte (filtro global): " + _recorte_txt())
    vc = CTX["vclass"]
    c_mes, c_loja = st.columns(2)
    msel = _mes_local(vc, "reg_meses", c_mes)
    if msel:
        vc = vc[vc["ano_mes"].isin(msel)]
    lsel = _loja_local(vc, "reg_lojas", c_loja)
    if lsel:
        vc = vc[vc["loja"].isin(lsel)]
    if vc.empty:
        st.info("Sem vencidos nesse recorte.", icon=":material/info:")
        return
    nm = max(vc["ano_mes"].nunique(), 1)

    st.markdown(
        "A perda é **cauda longa** (milhares de SKUs, cada um pouco), então não adianta "
        "lista de 30 itens — tem que ser **regra**. Simule abaixo o efeito de limitar a "
        "compra/estoque de um recorte.")

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        curvas = c1.segmented_control("Curvas alvo", ["H e I", "F a I", "E a I"],
                                      default="H e I")
        mp = {"H e I": ("H", "I"), "F a I": ("F", "G", "H", "I"),
              "E a I": ("E", "F", "G", "H", "I")}[curvas]
        macro = c2.selectbox("Categoria", ["todas", "medicamento", "nao-medicamento"])
        red = c3.slider("% do excesso que dá pra evitar", 30, 90, 70, 5) / 100
        sim = core.simular_teto(vc, curvas=mp, macro=None if macro == "todas" else macro,
                                reducao=red, n_meses=nm)

        a, b, c = st.columns(3)
        a.metric("Economia estimada", BRL(sim["economia_mes"]) + " /mês", border=True)
        b.metric("No período analisado", BRL(sim["economia_periodo"]), border=True)
        c.metric("SKUs afetados pela regra", f"{sim['produtos']:,}".replace(",", "."),
                 border=True)
        st.caption(
            f"Base: R$ {sim['base_periodo']:,.0f} de vencido caiu no balde "
            f"'excesso de compra' nesse recorte no período. A regra assume que "
            f"{red*100:.0f}% disso é evitável não comprando / não repondo item sem giro.")

    st.markdown("### Política sugerida")
    st.markdown(f"""
- **Curva {curvas.replace(' e ', '/').replace(' a ', '–')} sem giro:** teto de estoque = 1 unidade,
  sem reposição automática; compra só sob demanda (encomenda).
- **Medicamento propagado curva H–I:** exige aprovação do comprador; bloquear
  transferência de sobra entre lojas para item já parado.
- **Item marcado como suspenso/descontinuado no cadastro:** rotina mensal de
  devolução ao fornecedor ou rebaixa de preço 90 dias antes do vencimento.
- **Alerta de validade:** item curva A–D com estoque > 2× média de venda e
  validade < 120 dias → aviso pra loja (essa parte hoje já vaza pouco: {PCT(
      CTX['vclass'].query("balde=='pdv'").valor_total.sum() /
      (CTX['vclass'].valor_total.sum() or 1))} do vencido).
""")

    with st.container(border=True):
        st.markdown("**Itens que a regra pegaria** (maior valor primeiro)")
        d = vc[(vc["balde"] == "compra") &
               (vc["curva_valor"].astype(str).str.upper().isin([x.upper() for x in mp]))]
        if macro != "todas":
            d = d[d["macro"] == macro]
        tab = (d.groupby("produto", as_index=False)
               .agg(valor=("valor_total", "sum"), curva_valor=("curva_valor", "first"),
                    curva_qtd=("curva_qtd", "first"), macro=("macro", "first"),
                    cat=("cat1", "first"), dias_sem_vender=("ult_venda_dias", "max"),
                    lojas=("loja", "nunique"))
               .sort_values("valor", ascending=False).head(200))
        st.dataframe(tab, hide_index=True, width="stretch", height=340,
                     column_config={
                         "valor": st.column_config.NumberColumn("R$ vencido", format="R$ %.0f"),
                         "curva_valor": "Curva valor", "curva_qtd": "Curva qtd",
                         "dias_sem_vender": "Dias s/ vender"})
        st.download_button("Baixar lista completa (CSV)",
                           d.to_csv(index=False).encode("utf-8-sig"),
                           "itens_regra.csv", "text/csv", icon=":material/download:")


# --------------------------------------------------------------------------- #
nav = st.navigation([
    st.Page(tela_veredito, title="Painel", icon=":material/speed:", default=True),
    st.Page(tela_motivos, title="Motivos", icon=":material/category:"),
    st.Page(tela_anatomia, title="Anatomia da perda", icon=":material/account_tree:"),
    st.Page(tela_baldes, title="Evitável x estrutural", icon=":material/rule:"),
    st.Page(tela_regras, title="Regras e simulação", icon=":material/tune:"),
])
nav.run()
