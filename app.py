"""
Monitor de Perdas — Grupo Velanes
streamlit run app.py

Quatro telas, cada uma responde uma pergunta:
  1. Veredito .............. a perda é aceitável?
  2. Anatomia da perda .... o que são esses itens? (medicamento? curva? giro?)
  3. Evitável x estrutural  estou dando perda em item que vende?
  4. Regras e simulação ... o que mudar e quanto economiza
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
BRLk = lambda v: ("R$ " + f"{v/1000:,.1f}k").replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(v) else "—"
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

    # parâmetros
    st.sidebar.markdown("### Parâmetros")
    escopo = st.sidebar.segmented_control(
        "Escopo", list(core.ESCOPOS), format_func=lambda k: core.ESCOPOS[k].split(" (")[0],
        default="vencido", selection_mode="single") or "vencido"
    meta = st.sidebar.slider("Meta (% do faturamento)", 0.1, 1.5, 0.5, 0.05,
                             format="%.2f%%") / 100
    incluir_dep = st.sidebar.toggle("Incluir depósito (DEP)", value=False)

    with st.sidebar.expander("Digitar faturamento", icon=":material/edit:"):
        _editor_faturamento(perdas, fat)

    # derivados
    taxa_lm = core.taxa_por_loja_mes(perdas, fat, escopo, incluir_dep)
    mensal = core.resumo_mensal(taxa_lm)
    cob = core.cobertura_faturamento(perdas, fat)
    n_meses_perda = perdas["ano_mes"].nunique()

    vclass = None
    if cad is not None:
        psig = (fonte, len(perdas))
        csig = (len(cad), int(cad["produto"].nunique()))
        vclass = _vclass(psig, csig, perdas, cad)

    return dict(perdas=perdas, cad=cad, fat=fat, fonte=fonte, escopo=escopo,
                meta=meta, incluir_dep=incluir_dep, taxa_lm=taxa_lm, mensal=mensal,
                cob=cob, vclass=vclass, n_meses=n_meses_perda)


def _editor_faturamento(perdas, fat):
    st.caption("Uma linha por loja e mês. Fonte: Power BI → Receita por Und. ID.")
    lojas = sorted(int(x) for x in perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())
    meses = sorted(perdas["ano_mes"].unique())
    base = fat.copy() if not fat.empty else pd.DataFrame(
        [(l, meses[-1] if meses else "2026-01", 0.0) for l in lojas],
        columns=["loja", "ano_mes", "faturamento"])
    ed = st.data_editor(base, num_rows="dynamic", width="stretch", key="fat_ed")
    if st.button("Salvar", icon=":material/save:"):
        c = ed.dropna(subset=["loja", "ano_mes", "faturamento"])
        c = c[c["faturamento"] > 0]
        FAT_JSON.write_text(c.to_json(orient="records"), encoding="utf-8")
        st.toast("Faturamento salvo. Recarregue (R).", icon=":material/check:")


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


# =========================================================================== #
# TELA 1 — VEREDITO
# =========================================================================== #
def tela_veredito():
    st.title("A perda é aceitável?")
    m, esc = CTX["mensal"], CTX["escopo"]
    st.caption(f"Escopo: {core.ESCOPOS[esc]} · fonte `{CTX['fonte']}`")

    if m.empty:
        _sem_faturamento_aviso()
        mm = (CTX["perdas"][CTX["perdas"]["motivo_cat"].map(lambda c: core.in_escopo(c, esc))]
              .groupby("ano_mes")["valor_total"].sum().reset_index())
        st.subheader("Valor da perda por mês")
        st.bar_chart(mm, x="ano_mes", y="valor_total", height=260)
        return

    nivel, frase = ("sem_dados", "")
    if CTX["vclass"] is not None:
        nivel, frase = core.frase_diagnostico(m, CTX["vclass"], esc, CTX["meta"])
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
            if v:
                st.write(f"Dados: **{BRL(m['perda'].mean())}/mês** · diferença "
                         f"**{BRL(v - m['perda'].mean())}** ({(v/m['perda'].mean()-1)*100:+.0f}%)")
            if pp:
                st.write(f"Dados: **{PCT(taxa)}** · diferença **{(pp-taxa)*100:+.2f} p.p.**")

    cob = CTX["cob"]
    if cob["meses_sem_faturamento"] or cob["lojas_sem_faturamento"]:
        avisos = []
        if cob["meses_sem_faturamento"]:
            avisos.append("meses sem faturamento: " + ", ".join(cob["meses_sem_faturamento"]))
        if cob["lojas_sem_faturamento"]:
            avisos.append("lojas sem faturamento: " +
                          ", ".join(str(int(x)) for x in cob["lojas_sem_faturamento"]))
        st.caption(" · ".join(avisos) + " — ficam fora do cálculo de %.")


# =========================================================================== #
# TELA 2 — ANATOMIA DA PERDA
# =========================================================================== #
def tela_anatomia():
    st.title("O que são esses itens?")
    if _falta_cadastro():
        return
    vc = CTX["vclass"].copy()
    meses = sorted(vc["ano_mes"].unique())
    sel = st.multiselect("Meses", meses, default=meses, placeholder="todos os meses")
    if sel:
        vc = vc[vc["ano_mes"].isin(sel)]
    tot = vc["valor_total"].sum() or 1.0

    macro = vc.groupby("macro", as_index=False)["valor_total"].sum().sort_values("valor_total", ascending=False)
    macro["pct"] = macro["valor_total"] / tot
    with st.container(horizontal=True):
        for _, r in macro.iterrows():
            st.metric(r["macro"].capitalize(), BRL(r["valor_total"]),
                      delta=f"{r['pct']*100:.0f}% do vencido", delta_color="off", border=True)

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("**Por categoria da árvore mercadológica**")
            gsel = st.segmented_control("Ver", ["Todas", "Só medicamento", "Só não-medicamento"],
                                        default="Todas", label_visibility="collapsed")
            d = vc
            if gsel == "Só medicamento":
                d = vc[vc["macro"] == "medicamento"]
            elif gsel == "Só não-medicamento":
                d = vc[vc["macro"] == "nao-medicamento"]
            cat = (d.groupby("cat1", as_index=False)["valor_total"].sum()
                   .sort_values("valor_total", ascending=False).head(12))
            ch = alt.Chart(cat).mark_bar(color="#60A5FA").encode(
                x=alt.X("valor_total:Q", title="R$ vencido"),
                y=alt.Y("cat1:N", sort="-x", title=None),
                tooltip=["cat1", alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("**Tem curva?**")
            qual = st.segmented_control("curva", ["Curva de valor", "Curva de quantidade"],
                                        default="Curva de valor", label_visibility="collapsed")
            col_curva = "curva_qtd" if qual == "Curva de quantidade" else "curva_valor"
            cv = vc.copy()
            cv["cg"] = cv[col_curva].astype(str).str.upper().map(
                lambda x: "A–D (relevante)" if x in list("ABCD")
                else ("E–G (média)" if x in list("EFG")
                      else ("H–I (cauda)" if x in list("HI") else "Sem cadastro")))
            g = cv.groupby("cg", as_index=False)["valor_total"].sum()
            ordem = ["A–D (relevante)", "E–G (média)", "H–I (cauda)", "Sem cadastro"]
            ch = alt.Chart(g).mark_bar().encode(
                x=alt.X("valor_total:Q", title="R$ vencido"),
                y=alt.Y("cg:N", sort=ordem, title=None),
                color=alt.Color("cg:N", scale=alt.Scale(
                    domain=ordem, range=["#34D399", "#FBBF24", "#F87171", "#94A3B8"]),
                    legend=None),
                tooltip=["cg", alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch, width="stretch")
            st.markdown("**Quanto tempo parado quando venceu**")
            fg = (vc.groupby("faixa_giro", as_index=False)["valor_total"].sum())
            ordem_g = [x[2] for x in core.FAIXAS_GIRO] + ["Sem cadastro"]
            ch2 = alt.Chart(fg).mark_bar(color="#FB923C").encode(
                x=alt.X("valor_total:Q", title="R$ vencido"),
                y=alt.Y("faixa_giro:N", sort=ordem_g, title=None),
                tooltip=["faixa_giro", alt.Tooltip("valor_total:Q", format=",.0f")])
            st.altair_chart(ch2, width="stretch")

    with st.container(border=True):
        st.markdown("**Produtos** (clique nos cabeçalhos para ordenar)")
        cat_pick = st.selectbox("Filtrar categoria", ["(todas)"] +
                                sorted(vc["cat1"].unique()))
        d = vc if cat_pick == "(todas)" else vc[vc["cat1"] == cat_pick]
        tab = (d.groupby("produto", as_index=False)
               .agg(valor=("valor_total", "sum"), itens=("itens", "sum"),
                    curva_valor=("curva_valor", "first"), curva_qtd=("curva_qtd", "first"),
                    macro=("macro", "first"), cat=("cat1", "first"),
                    dias_sem_vender=("ult_venda_dias", "max"), lojas=("loja", "nunique"))
               .sort_values("valor", ascending=False).head(300))
        st.dataframe(tab, hide_index=True, width="stretch", height=360,
                     column_config={
                         "valor": st.column_config.NumberColumn("R$ vencido", format="R$ %.0f"),
                         "curva_valor": "Curva valor", "curva_qtd": "Curva qtd",
                         "dias_sem_vender": "Dias s/ vender"})


# =========================================================================== #
# TELA 3 — EVITÁVEL x ESTRUTURAL
# =========================================================================== #
def tela_baldes():
    st.title("Estou dando perda em item que vende?")
    if _falta_cadastro():
        return
    vc = CTX["vclass"]
    nm = CTX["n_meses"]
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
# TELA 4 — REGRAS E SIMULAÇÃO
# =========================================================================== #
def tela_regras():
    st.title("O que mudar — e quanto economiza")
    if _falta_cadastro():
        return
    vc = CTX["vclass"]
    nm = CTX["n_meses"]

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
    st.Page(tela_anatomia, title="Anatomia da perda", icon=":material/account_tree:"),
    st.Page(tela_baldes, title="Evitável x estrutural", icon=":material/rule:"),
    st.Page(tela_regras, title="Regras e simulação", icon=":material/tune:"),
])
nav.run()
