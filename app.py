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


# --------------------------------------------------------------------------- #
# cargas (cache)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Lendo relatório de perdas…")
def _perdas(path, mtime):
    return core.load_perdas(path)


@st.cache_data(show_spinner="Lendo cadastro (1ª vez demora)…")
def _cadastro(paths, sig):
    return core.load_cadastro(list(paths))


@st.cache_data(show_spinner="Lendo faturamento…")
def _fat_arquivo(path, mtime):
    return core.load_faturamento(path)


@st.cache_data(show_spinner="Cruzando vencidos com o cadastro…")
def _vclass(perdas_sig, cad_sig, _perdas_df, _cad_df):
    enr = core.enriquecer_vencidos(_perdas_df, _cad_df, ("vencido",))
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

    vclass = None
    if cad is not None:
        psig = (fonte, len(perdas))              # cache na base cheia; filtra depois
        csig = (len(cad), int(cad["produto"].nunique()))
        vclass = _vclass(psig, csig, perdas, cad)
        if lojas_sel:
            vclass = vclass[vclass["loja"].isin(lojas_sel)]
        if meses_sel:
            vclass = vclass[vclass["ano_mes"].isin(meses_sel)]

    return dict(perdas=perdas_f, perdas_full=perdas, cad=cad, fat=fat_f, fonte=fonte,
                escopo=escopo, meta=meta, incluir_dep=incluir_dep, taxa_lm=taxa_lm,
                mensal=mensal, cob=cob, vclass=vclass, n_meses=n_meses_perda,
                lojas_sel=lojas_sel, meses_sel=meses_sel)


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


# =========================================================================== #
# TELA 1 — VEREDITO
# =========================================================================== #
def tela_veredito():
    st.title("A perda é aceitável?")
    m, esc = CTX["mensal"], CTX["escopo"]
    st.caption(f"Escopo: {core.ESCOPOS[esc]} · recorte: {_recorte_txt()} · "
               f"fonte `{CTX['fonte']}`")

    if m.empty:
        _sem_faturamento_aviso()
        mm = (CTX["perdas"][CTX["perdas"]["motivo_cat"].map(lambda c: core.in_escopo(c, esc))]
              .groupby("ano_mes")["valor_total"].sum().reset_index())
        st.subheader("Valor da perda por mês")
        st.bar_chart(mm, x="ano_mes", y="valor_total", height=260)
        return

    nivel, frase = ("sem_dados", "")
    if CTX["vclass"] is not None:
        nivel, frase = core.frase_diagnostico(m, CTX["vclass"], CTX["meta"])
    taxa = m["taxa"].mean()
    ult = m.iloc[-1]
    recuperavel = 0.0
    if CTX["vclass"] is not None:
        rb = core.resumo_baldes(CTX["vclass"], CTX["n_meses"])
        recuperavel = rb.loc[rb["balde"].isin(["compra", "cadastro"]), "valor_mes"].sum()

    with st.container(border=True):
        c1, c2 = st.columns([1, 2], vertical_alignment="center")
        with c1:
            rot = {"ok": "ACEITÁVEL", "atencao": "ATENÇÃO", "critico": "CRÍTICO",
                   "sem_dados": "—"}[nivel]
            st.markdown(
                f"<div style='font-size:0.8rem;color:#94A3B8;text-transform:uppercase;"
                f"letter-spacing:.08em'>Taxa média do período</div>"
                f"<div style='font-size:3rem;font-weight:700;line-height:1.1'>{PCT(taxa)}</div>"
                f"<div style='display:inline-block;margin-top:.4rem;padding:.15rem .6rem;"
                f"border-radius:999px;background:{COR[nivel]}22;color:{COR[nivel]};"
                f"font-weight:600;font-size:.85rem'>{rot}</div>",
                unsafe_allow_html=True)
        with c2:
            st.markdown(f"**Diagnóstico.** {frase}" if frase else
                        "Envie o cadastro (DADOS) para o diagnóstico automático.")

    with st.container(horizontal=True):
        st.metric("Taxa no mês", PCT(ult["taxa"]),
                  delta=PCT(ult["taxa"] - m.iloc[-2]["taxa"]) if len(m) > 1 else None,
                  delta_color="inverse", border=True,
                  chart_data=(m["taxa"] * 100).tolist(), chart_type="line")
        st.metric("Perda no mês", BRL(ult["perda"]), border=True)
        st.metric("Faturamento no mês", BRL(ult["faturamento"]), border=True)
        st.metric("Recuperável / mês", BRL(recuperavel), border=True,
                  help="Valor médio nos baldes 'excesso de compra' e 'item suspenso' — "
                       "atacável por política de compra e cadastro, não por disciplina de loja.")

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            st.markdown("**Taxa de perdas por mês** (% do faturamento)")
            d = m[["ano_mes", "taxa"]].copy()
            d["taxa"] *= 100
            d["meta"] = CTX["meta"] * 100
            base = alt.Chart(d).encode(x=alt.X("ano_mes:N", title=None))
            linha = base.mark_line(point=True, strokeWidth=2, color=COR["atencao"]).encode(
                y=alt.Y("taxa:Q", title="%"),
                tooltip=["ano_mes", alt.Tooltip("taxa:Q", format=".2f")])
            meta_l = base.mark_rule(strokeDash=[4, 4], color="#94A3B8").encode(y="meta:Q")
            st.altair_chart(linha + meta_l, width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Bater com o número da reunião**")
            v = st.number_input("Valor apresentado (R$/mês)", value=0.0, step=1000.0)
            pp = st.number_input("ou % apresentado", value=0.0, step=0.1) / 100
            pm = m["perda"].mean()
            if v and pm:
                st.write(f"Dados: **{BRL(pm)}/mês** · diferença "
                         f"**{BRL(v - pm)}** ({(v/pm-1)*100:+.0f}%)")
            elif v:
                st.write(f"Dados: **{BRL(pm)}/mês** · diferença **{BRL(v - pm)}**")
            if pp and taxa:
                st.write(f"Dados: **{PCT(taxa)}** · diferença **{(pp-taxa)*100:+.2f} p.p.**")

    cob = CTX["cob"]
    meses_sf = cob["meses_sem_faturamento"]
    if meses_sf:
        p = CTX["perdas"]
        if not CTX["incluir_dep"]:
            p = p[~p["is_dep"]]
        p = p[p["motivo_cat"].map(lambda c: core.in_escopo(c, esc))
              & p["ano_mes"].isin(meses_sf)]
        mm = p.groupby("ano_mes", as_index=False)["valor_total"].sum()
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
CLASSE_COR = {"Vencido": "#F87171", "Outra perda real": "#FB923C", "Não é perda": "#94A3B8"}


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

    sel = sorted(p["ano_mes"].unique())            # meses já vêm do filtro global
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


def tela_anatomia():
    st.title("O que são esses itens?")
    if _falta_cadastro():
        return
    vc = CTX["vclass"].copy()
    st.caption("Recorte (filtro global): " + _recorte_txt())

    if vc.empty:
        st.info("Sem vencidos nesse recorte.", icon=":material/info:")
        return
    tot = vc["valor_total"].sum() or 1.0

    cr, cm = st.columns(2)
    # qual curva usar p/ agrupar (vale p/ o gráfico "Tem curva?" e o filtro da tabela)
    qual = cr.radio("Curva para os gráficos",
                    ["Curva de valor", "Curva de quantidade"],
                    horizontal=True, key="anat_curva")
    col_curva = "curva_qtd" if qual == "Curva de quantidade" else "curva_valor"
    # medida do eixo dos gráficos: R$ vencido ou nº de unidades vencidas
    medida = cm.radio("Medida dos gráficos", ["R$ vencido", "Unidades"],
                      horizontal=True, key="anat_medida")
    mcol = "valor_total" if medida == "R$ vencido" else "itens"
    mtitle = "R$ vencido" if medida == "R$ vencido" else "Unidades vencidas"
    tip_val = alt.Tooltip("valor_total:Q", title="R$ vencido", format=",.0f")
    tip_itens = alt.Tooltip("itens:Q", title="Unidades", format=",.0f")
    ORD_CURVA = ["A–D (relevante)", "E–G (média)", "H–I (cauda)", "Sem cadastro"]

    def _cg(s):
        x = str(s).upper()
        if x in list("ABCD"):
            return ORD_CURVA[0]
        if x in list("EFG"):
            return ORD_CURVA[1]
        if x in list("HI"):
            return ORD_CURVA[2]
        return ORD_CURVA[3]

    vc["cg"] = vc[col_curva].map(_cg)

    macro = (vc.groupby("macro", as_index=False)["valor_total"].sum()
             .sort_values("valor_total", ascending=False))
    macro["pct"] = macro["valor_total"] / tot
    with st.container(horizontal=True):
        for _, r in macro.iterrows():
            st.metric(r["macro"].capitalize(), BRL(r["valor_total"]),
                      delta=f"{r['pct']*100:.0f}% do vencido", delta_color="off", border=True)

    st.caption("Clique numa barra dos gráficos abaixo para filtrar a tabela de "
               "produtos no fim da página. Clique de novo na mesma barra para limpar.")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Por categoria da árvore mercadológica**")
            gsel = st.segmented_control(
                "Ver", ["Todas", "Só medicamento", "Só não-medicamento"],
                default="Todas", label_visibility="collapsed", key="anat_ver")
            d = vc
            if gsel == "Só medicamento":
                d = vc[vc["macro"] == "medicamento"]
            elif gsel == "Só não-medicamento":
                d = vc[vc["macro"] == "nao-medicamento"]
            cat = (d.groupby("cat1", as_index=False)
                   .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum"))
                   .sort_values(mcol, ascending=False).head(12))
            sel_cat = alt.selection_point(fields=["cat1"], name="pcat")
            ch = (alt.Chart(cat).mark_bar(color="#60A5FA").encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("cat1:N", sort="-x", title=None),
                opacity=alt.condition(sel_cat, alt.value(1.0), alt.value(0.35)),
                tooltip=["cat1", tip_val, tip_itens])
                .add_params(sel_cat))
            ev_cat = st.altair_chart(ch, width="stretch", on_select="rerun",
                                     key="anat_ch_cat")
    with right:
        with st.container(border=True):
            st.markdown(f"**Tem curva?** ({qual.lower()} · {mtitle.lower()})")
            g = (vc.groupby("cg", as_index=False)
                 .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum")))
            sel_cv = alt.selection_point(fields=["cg"], name="pcg")
            ch = (alt.Chart(g).mark_bar().encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("cg:N", sort=ORD_CURVA, title=None),
                color=alt.Color("cg:N", scale=alt.Scale(
                    domain=ORD_CURVA, range=["#34D399", "#FBBF24", "#F87171", "#94A3B8"]),
                    legend=None),
                opacity=alt.condition(sel_cv, alt.value(1.0), alt.value(0.35)),
                tooltip=["cg", tip_val, tip_itens])
                .add_params(sel_cv))
            ev_cv = st.altair_chart(ch, width="stretch", on_select="rerun",
                                    key="anat_ch_cv")
            st.markdown("**Quanto tempo parado quando venceu**")
            fg = (vc.groupby("faixa_giro", as_index=False)
                  .agg(valor_total=("valor_total", "sum"), itens=("itens", "sum")))
            ordem_g = [x[2] for x in core.FAIXAS_GIRO] + ["Sem cadastro"]
            sel_g = alt.selection_point(fields=["faixa_giro"], name="pgiro")
            ch2 = (alt.Chart(fg).mark_bar(color="#FB923C").encode(
                x=alt.X(f"{mcol}:Q", title=mtitle),
                y=alt.Y("faixa_giro:N", sort=ordem_g, title=None),
                opacity=alt.condition(sel_g, alt.value(1.0), alt.value(0.35)),
                tooltip=["faixa_giro", tip_val, tip_itens])
                .add_params(sel_g))
            ev_g = st.altair_chart(ch2, width="stretch", on_select="rerun",
                                   key="anat_ch_giro")

    # ---- tabela de produtos, filtrada pelo que foi clicado nos gráficos ---- #
    d = vc
    filtros = []
    cats_sel = _picked(ev_cat, "cat1")
    if cats_sel:
        d = d[d["cat1"].isin(cats_sel)]
        filtros.append(("Categoria da árvore", ", ".join(map(str, cats_sel)),
                        "Por categoria da árvore mercadológica"))
    cg_sel = _picked(ev_cv, "cg")
    if cg_sel:
        d = d[d["cg"].isin(cg_sel)]
        filtros.append((qual, ", ".join(map(str, cg_sel)), "Tem curva?"))
    giro_sel = _picked(ev_g, "faixa_giro")
    if giro_sel:
        d = d[d["faixa_giro"].isin(giro_sel)]
        filtros.append(("Tempo parado", ", ".join(map(str, giro_sel)),
                        "Quanto tempo parado quando venceu"))

    with st.container(border=True):
        if filtros:
            st.markdown("**Produtos — " +
                        " · ".join(f"{k}: {v}" for k, v, _ in filtros) + "**")
            st.caption("Origem: " +
                       " ; ".join(f'gráfico "{src}" → {v}' for _, v, src in filtros)
                       + f". {len(d)} linhas de vencido, "
                       + f"{BRL(d['valor_total'].sum())} no recorte. "
                       "Clique de novo na barra para limpar o filtro.")
        else:
            st.markdown("**Produtos** — todos os itens vencidos do recorte")
            st.caption("Clique numa barra dos gráficos acima para filtrar aqui. "
                       "Clique nos cabeçalhos da tabela para ordenar.")
        tab = (d.groupby("produto", as_index=False)
               .agg(valor=("valor_total", "sum"), itens=("itens", "sum"),
                    curva_valor=("curva_valor", "first"), curva_qtd=("curva_qtd", "first"),
                    macro=("macro", "first"), cat=("cat1", "first"),
                    faixa_giro=("faixa_giro", "first"),
                    dias_sem_vender=("ult_venda_dias", "max"), lojas=("loja", "nunique"))
               .sort_values("valor", ascending=False).head(300))
        st.dataframe(tab, hide_index=True, width="stretch", height=360,
                     column_config={
                         "valor": st.column_config.NumberColumn("R$ vencido", format="R$ %.0f"),
                         "curva_valor": "Curva valor", "curva_qtd": "Curva qtd",
                         "faixa_giro": "Tempo parado",
                         "dias_sem_vender": "Dias s/ vender"})
        st.download_button("Baixar (CSV)", tab.to_csv(index=False).encode("utf-8-sig"),
                           "anatomia_produtos.csv", "text/csv",
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
    nm = CTX["n_meses"]
    if vc.empty:
        st.info("Sem vencidos nesse recorte.", icon=":material/info:")
        return
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
    nm = CTX["n_meses"]
    if vc.empty:
        st.info("Sem vencidos nesse recorte.", icon=":material/info:")
        return

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
    st.Page(tela_veredito, title="Veredito", icon=":material/speed:", default=True),
    st.Page(tela_motivos, title="Motivos", icon=":material/category:"),
    st.Page(tela_anatomia, title="Anatomia da perda", icon=":material/account_tree:"),
    st.Page(tela_baldes, title="Evitável x estrutural", icon=":material/rule:"),
    st.Page(tela_regras, title="Regras e simulação", icon=":material/tune:"),
])
nav.run()
