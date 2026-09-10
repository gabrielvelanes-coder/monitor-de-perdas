"""
Monitor de Perdas — Grupo Velanes
Roda com:  streamlit run app.py
Coloque na mesma pasta:
  - o relatório "perdas ... com motivo e loja.xls"
  - os arquivos "DADOS ... .xlsx" (cadastro / curva)
  - opcional: faturamento.csv  (loja, ano_mes, faturamento)
"""
from __future__ import annotations

import glob
import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import core

st.set_page_config(page_title="Monitor de Perdas — Velanes", page_icon="📉",
                   layout="wide")

PASTA = Path(__file__).parent
FAT_JSON = PASTA / "faturamento.json"        # faturamento digitado no app

# faturamento por loja do mês corrente parcial, lido do Power BI em 10/09/2026.
# serve só de semente pro editor manual; substitua por meses fechados.
SEMENTE_FAT_2026_09 = {
    2: 132256.54, 3: 232022.80, 4: 186729.42, 5: 107834.15, 6: 78809.50,
    7: 247201.02, 8: 140906.51, 9: 119715.23, 10: 151162.72, 11: 215229.61,
    13: 164402.50, 14: 65152.23, 15: 99762.66, 16: 109869.50, 17: 71411.23,
    18: 172464.33, 19: 89586.07, 20: 123729.84, 22: 66101.00, 23: 90241.39,
    24: 90882.24, 25: 94779.54,
}

BRL = lambda v: ("R$ " + f"{v:,.0f}").replace(",", ".") if pd.notna(v) else "—"
PCT = lambda v: f"{v*100:,.2f}%".replace(".", ",") if pd.notna(v) else "—"


# --------------------------------------------------------------------------- #
# cargas com cache
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Lendo relatório de perdas...")
def _perdas(path, mtime):
    return core.load_perdas(path)


@st.cache_data(show_spinner="Lendo cadastro (pode demorar na 1ª vez)...")
def _cadastro(paths, sig):
    return core.load_cadastro(list(paths))


@st.cache_data(show_spinner="Lendo faturamento...")
def _fat_arquivo(path, mtime):
    return core.load_faturamento(path)


def _achar(*padroes):
    for pad in padroes:
        hits = sorted(glob.glob(str(PASTA / pad)))
        if hits:
            return hits
    return []


# --------------------------------------------------------------------------- #
# SIDEBAR — entradas
# --------------------------------------------------------------------------- #
st.sidebar.title("📉 Monitor de Perdas")
st.sidebar.caption("Grupo Velanes")

# --- relatório de perdas ---
st.sidebar.subheader("1. Relatório de perdas")
up_perdas = st.sidebar.file_uploader("Análise de Baixa de Estoque (.xls/.xlsx)",
                                     type=["xls", "xlsx"])
auto_perdas = _achar("perdas*.xls", "perdas*.xlsx", "*Baixa*Estoque*.xls*")
if up_perdas is not None:
    perdas = core.load_perdas(up_perdas)
    fonte_perdas = up_perdas.name
elif auto_perdas:
    p = auto_perdas[0]
    perdas = _perdas(p, Path(p).stat().st_mtime)
    fonte_perdas = Path(p).name
    st.sidebar.caption(f"📄 auto: `{fonte_perdas}`")
else:
    st.info("👈 Envie o relatório de perdas para começar.")
    st.stop()

# --- cadastro ---
st.sidebar.subheader("2. Cadastro (curva / giro)")
up_cad = st.sidebar.file_uploader("Arquivos DADOS (.xlsx)", type=["xlsx"],
                                  accept_multiple_files=True)
auto_cad = _achar("DADOS*.xlsx", "*cadastro*.xlsx")
cad = None
if up_cad:
    cad = core.load_cadastro(up_cad)
    st.sidebar.caption(f"{len(up_cad)} arquivo(s) enviados")
elif auto_cad:
    sig = tuple((Path(x).name, Path(x).stat().st_size) for x in auto_cad)
    cad = _cadastro(tuple(auto_cad), sig)
    st.sidebar.caption(f"📄 auto: {len(auto_cad)} arquivo(s) DADOS")
else:
    st.sidebar.caption("sem cadastro → aba de diagnóstico fica limitada")

# --- faturamento ---
st.sidebar.subheader("3. Faturamento por loja / mês")
up_fat = st.sidebar.file_uploader("faturamento (.csv/.xlsx)", type=["csv", "xlsx"])
auto_fat = _achar("faturamento.csv", "faturamento.xlsx", "*faturamento*.csv")

fat = pd.DataFrame(columns=["loja", "ano_mes", "faturamento"])
origem_fat = "nenhuma"
if up_fat is not None:
    fat = core.load_faturamento(up_fat)
    origem_fat = f"arquivo enviado ({up_fat.name})"
elif auto_fat:
    fat = _fat_arquivo(auto_fat[0], Path(auto_fat[0]).stat().st_mtime)
    origem_fat = f"arquivo `{Path(auto_fat[0]).name}`"
elif FAT_JSON.exists():
    j = json.loads(FAT_JSON.read_text(encoding="utf-8"))
    fat = pd.DataFrame(j)
    origem_fat = "digitado no app (faturamento.json)"

st.sidebar.caption(f"faturamento: {origem_fat}")

with st.sidebar.expander("✏️ digitar faturamento na mão"):
    st.caption("Formato longo: uma linha por loja e mês. "
               "Exporte do Power BI (Receita por Und. ID) e cole aqui.")
    meses_perda = sorted(perdas["ano_mes"].unique())
    lojas_perda = sorted(int(x) for x in perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())
    if fat.empty:
        base = pd.DataFrame(
            [(l, meses_perda[-1] if meses_perda else "2026-09",
              SEMENTE_FAT_2026_09.get(l, 0.0)) for l in lojas_perda],
            columns=["loja", "ano_mes", "faturamento"])
    else:
        base = fat.copy()
    ed = st.data_editor(base, num_rows="dynamic", use_container_width=True,
                        key="fat_editor")
    if st.button("💾 salvar faturamento digitado"):
        clean = ed.dropna(subset=["loja", "ano_mes", "faturamento"])
        clean = clean[clean["faturamento"] > 0]
        FAT_JSON.write_text(clean.to_json(orient="records"), encoding="utf-8")
        st.success("Salvo. Recarregue a página (R).")

# --- parâmetros ---
st.sidebar.subheader("Parâmetros")
escopo = st.sidebar.radio("Escopo da perda", list(core.ESCOPOS),
                          format_func=lambda k: core.ESCOPOS[k])
meta = st.sidebar.number_input("Meta / alerta (% do faturamento)",
                               value=0.50, step=0.05, format="%.2f") / 100
incluir_dep = st.sidebar.checkbox("Incluir depósito (DEP)", value=False)

# --------------------------------------------------------------------------- #
# cálculo
# --------------------------------------------------------------------------- #
taxa_lm = core.taxa_por_loja_mes(perdas, fat, escopo, incluir_dep)
mensal = core.resumo_mensal(taxa_lm)
cob = core.cobertura_faturamento(perdas, fat)

st.title("Monitor de Perdas")
st.caption(f"Fonte: `{fonte_perdas}` · escopo: **{core.ESCOPOS[escopo]}** · "
           f"{'com' if incluir_dep else 'sem'} depósito")

if fat.empty:
    st.warning("⚠️ Sem faturamento informado ainda — os percentuais não são "
               "calculados. Envie um arquivo ou digite na barra lateral. "
               "Enquanto isso, as abas mostram os valores em R$.")

tab_geral, tab_motivo, tab_lojas, tab_venc, tab_dados = st.tabs(
    ["📊 Visão geral", "🔻 Por motivo", "🏪 Lojas",
     "📅 Vencidos — diagnóstico", "⬇️ Dados"])

# =========================================================================== #
# ABA 1 — VISÃO GERAL
# =========================================================================== #
with tab_geral:
    if not mensal.empty:
        ult = mensal.iloc[-1]
        prev = mensal.iloc[-2] if len(mensal) > 1 else None
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Taxa de perdas — {ult['ano_mes']}", PCT(ult["taxa"]),
                  delta=(PCT(ult["taxa"] - prev["taxa"]) if prev is not None else None),
                  delta_color="inverse")
        c2.metric("Perda no mês", BRL(ult["perda"]))
        c3.metric("Faturamento no mês", BRL(ult["faturamento"]))
        media = mensal["taxa"].mean()
        c4.metric("Média do período", PCT(media),
                  delta=f"meta {PCT(meta)}", delta_color="off")

        proj = mensal["perda"].mean() * 12
        st.caption(f"Projeção anualizada da perda ({core.ESCOPOS[escopo].lower()}): "
                   f"**{BRL(proj)}**  ·  base: {len(mensal)} mês(es) com faturamento.")

        st.subheader("Taxa de perdas por mês")
        ch = mensal.copy()
        ch["Meta"] = meta
        ch = ch.set_index("ano_mes")[["taxa", "Meta"]].rename(columns={"taxa": "Taxa"})
        st.line_chart(ch, height=280)

        st.subheader("Valor da perda por mês (R$)")
        st.bar_chart(mensal.set_index("ano_mes")["perda"], height=240)
    else:
        st.info("Informe o faturamento para ver a evolução da taxa.")
        mm = (perdas[perdas["motivo_cat"].map(lambda c: core.in_escopo(c, escopo))]
              .groupby("ano_mes")["valor_total"].sum())
        st.subheader("Valor da perda por mês (R$) — sem % ainda")
        st.bar_chart(mm, height=260)

    st.divider()
    st.subheader("🔎 Bater com o número da reunião")
    cc1, cc2 = st.columns(2)
    val_reuniao = cc1.number_input("Valor apresentado (R$/mês)", value=0.0, step=1000.0)
    pct_reuniao = cc2.number_input("Ou % apresentado", value=0.0, step=0.1) / 100
    if not mensal.empty:
        real_val = mensal["perda"].mean()
        real_pct = mensal["taxa"].mean()
        linhas = []
        if val_reuniao:
            linhas.append(f"- Valor: reunião **{BRL(val_reuniao)}** vs dados "
                          f"**{BRL(real_val)}**  → diferença **{BRL(val_reuniao-real_val)}** "
                          f"({(val_reuniao/real_val-1)*100:+.0f}%)")
        if pct_reuniao:
            linhas.append(f"- Percentual: reunião **{PCT(pct_reuniao)}** vs dados "
                          f"**{PCT(real_pct)}**  → **{(pct_reuniao-real_pct)*100:+.2f} p.p.**")
        if linhas:
            st.markdown("\n".join(linhas))
        with st.expander("valores de referência (todos os recortes, média mensal do período)"):
            ref = []
            for e in core.ESCOPOS:
                t = core.resumo_mensal(core.taxa_por_loja_mes(perdas, fat, e, incluir_dep))
                if not t.empty:
                    ref.append({"recorte": core.ESCOPOS[e],
                                "R$/mês": t["perda"].mean(),
                                "% faturamento": t["taxa"].mean()})
            if ref:
                rd = pd.DataFrame(ref)
                st.dataframe(rd.style.format({"R$/mês": BRL, "% faturamento": PCT}),
                             use_container_width=True, hide_index=True)

    if cob["meses_sem_faturamento"]:
        st.caption("Meses sem faturamento informado (fora do cálculo de %): "
                   + ", ".join(cob["meses_sem_faturamento"]))
    if cob["lojas_sem_faturamento"]:
        st.caption("Lojas com perda mas sem faturamento informado: "
                   + ", ".join(str(int(x)) for x in cob["lojas_sem_faturamento"]))

# =========================================================================== #
# ABA 2 — POR MOTIVO
# =========================================================================== #
with tab_motivo:
    meses_op = ["(todos)"] + sorted(perdas["ano_mes"].unique())
    sel = st.multiselect("Meses", meses_op, default=["(todos)"])
    meses = None if "(todos)" in sel or not sel else sel
    pm = core.perda_por_motivo(perdas, incluir_dep, meses)

    tot = pm["valor"].sum()
    real = pm.loc[pm["is_perda_real"], "valor"].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("Baixa total no período", BRL(tot))
    c2.metric("Perda real", BRL(real), delta=f"{real/tot*100:.0f}% do total",
              delta_color="off")
    c3.metric("Não é perda (mkt, consumo, reembolso...)", BRL(tot - real),
              delta=f"{(tot-real)/tot*100:.0f}% do total", delta_color="off")

    disp = pm[["motivo_label", "is_perda_real", "valor", "valor_mes", "pct",
               "itens", "linhas"]].rename(columns={
        "motivo_label": "Motivo", "is_perda_real": "Perda real?",
        "valor": "Valor total", "valor_mes": "Valor / mês",
        "pct": "% do total", "itens": "Itens", "linhas": "Lançamentos"})
    st.dataframe(disp.style.format({"Valor total": BRL, "Valor / mês": BRL,
                                    "% do total": PCT}),
                 use_container_width=True, hide_index=True)
    st.bar_chart(pm.set_index("motivo_label")["valor"], height=320,
                 horizontal=True)

# =========================================================================== #
# ABA 3 — LOJAS
# =========================================================================== #
with tab_lojas:
    if taxa_lm["faturamento"].notna().any():
        base = taxa_lm.dropna(subset=["faturamento"])
        rk = (base.groupby("loja", as_index=False)
              .agg(perda=("perda", "sum"), faturamento=("faturamento", "sum"),
                   meses=("ano_mes", "nunique")))
        rk["taxa"] = rk["perda"] / rk["faturamento"]
        rk = rk.sort_values("taxa", ascending=False)
        rk["loja"] = rk["loja"].astype(int)

        st.subheader("Ranking de lojas pela taxa de perdas")
        st.dataframe(
            rk.rename(columns={"loja": "Loja", "perda": "Perda",
                               "faturamento": "Faturamento", "taxa": "Taxa",
                               "meses": "Meses"})
              .style.format({"Perda": BRL, "Faturamento": BRL, "Taxa": PCT})
              .background_gradient(subset=["Taxa"], cmap="Reds"),
            use_container_width=True, hide_index=True, height=430)

        st.subheader("Mapa de calor — taxa por loja × mês")
        piv = (taxa_lm.dropna(subset=["faturamento"])
               .assign(loja=lambda d: d["loja"].astype(int))
               .pivot_table(index="loja", columns="ano_mes", values="taxa"))
        st.dataframe(piv.style.format(PCT).background_gradient(cmap="Reds", axis=None),
                     use_container_width=True)
    else:
        st.info("Informe o faturamento para ranquear as lojas por taxa.")
        rk = (perdas[~perdas["is_dep"] if not incluir_dep else slice(None)]
              .pipe(lambda d: d[d["motivo_cat"].map(lambda c: core.in_escopo(c, escopo))])
              .groupby("loja", as_index=False)["valor_total"].sum()
              .sort_values("valor_total", ascending=False))
        rk["loja"] = rk["loja"].astype("Int64")
        st.dataframe(rk.rename(columns={"loja": "Loja", "valor_total": "Perda R$"})
                     .style.format({"Perda R$": BRL}),
                     use_container_width=True, hide_index=True)

# =========================================================================== #
# ABA 4 — VENCIDOS: DIAGNÓSTICO
# =========================================================================== #
with tab_venc:
    if cad is None:
        st.info("Envie os arquivos DADOS (cadastro) para cruzar os vencidos "
                "com curva, giro e estoque.")
    else:
        cats = ("vencido",) if escopo == "vencido" else tuple(
            c for c in core.CATS if core.IS_PERDA_REAL[c])
        enr = core.enriquecer_vencidos(perdas, cad, cats, incluir_dep)

        f1, f2, f3 = st.columns(3)
        lojas = sorted(int(x) for x in enr["loja"].dropna().unique())
        fl = f1.multiselect("Loja", lojas, default=[])
        meses_v = sorted(enr["ano_mes"].unique())
        fm = f2.multiselect("Mês", meses_v, default=[])
        curvas = sorted(enr["curva_valor"].dropna().unique())
        fc = f3.multiselect("Curva (valor)", curvas, default=[])
        v = enr.copy()
        if fl:
            v = v[v["loja"].isin(fl)]
        if fm:
            v = v[v["ano_mes"].isin(fm)]
        if fc:
            v = v[v["curva_valor"].isin(fc)]

        tot_v = v["valor_total"].sum()
        semcad = v.loc[v["sem_cadastro"], "valor_total"].sum()
        susp = v.loc[v["item_suspenso"], "valor_total"].sum()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Valor vencido (filtro)", BRL(tot_v))
        c2.metric("Curva I", PCT(v.loc[v["curva_valor"] == "I", "valor_total"].sum() / tot_v)
                  if tot_v else "—")
        c3.metric("Item já suspenso no cadastro", BRL(susp),
                  delta=f"{susp/tot_v*100:.0f}%" if tot_v else None, delta_color="off")
        c4.metric("Sem vender há +180 dias",
                  PCT(v.loc[v["ult_venda_dias"] > 180, "valor_total"].sum() / tot_v)
                  if tot_v else "—")

        cA, cB = st.columns(2)
        with cA:
            st.subheader("Por curva de valor")
            gc = (v.groupby("curva_valor", as_index=False)["valor_total"].sum()
                  .sort_values("valor_total", ascending=False))
            st.bar_chart(gc.set_index("curva_valor")["valor_total"], height=280)
        with cB:
            st.subheader("Por tempo sem vender")
            ordem = [x[2] for x in core.FAIXAS_GIRO] + ["Sem cadastro"]
            gg = (v.groupby("faixa_giro", as_index=False)["valor_total"].sum())
            gg["faixa_giro"] = pd.Categorical(gg["faixa_giro"], ordem, ordered=True)
            st.bar_chart(gg.sort_values("faixa_giro").set_index("faixa_giro")["valor_total"],
                         height=280)

        st.subheader("Top produtos vencidos")
        top = (v.groupby("produto", as_index=False)
               .agg(valor=("valor_total", "sum"), itens=("itens", "sum"),
                    curva=("curva_valor", "first"),
                    ult_venda=("ult_venda_dias", "max"),
                    lojas=("loja", "nunique"),
                    suspenso=("item_suspenso", "any"),
                    classif=("classif", "first"))
               .sort_values("valor", ascending=False).head(40))
        st.dataframe(
            top.rename(columns={"produto": "Produto", "valor": "Valor",
                                "itens": "Itens", "curva": "Curva",
                                "ult_venda": "Dias s/ vender", "lojas": "Nº lojas",
                                "suspenso": "Suspenso?", "classif": "Classificação"})
               .style.format({"Valor": BRL}),
            use_container_width=True, hide_index=True, height=430)

        st.download_button(
            "⬇️ baixar vencidos cruzados (CSV)",
            v.to_csv(index=False).encode("utf-8-sig"),
            file_name="vencidos_cruzados.csv", mime="text/csv")

# =========================================================================== #
# ABA 5 — DADOS
# =========================================================================== #
with tab_dados:
    st.subheader("Taxa por loja × mês")
    st.dataframe(taxa_lm, use_container_width=True, height=300)
    st.download_button("⬇️ taxa_loja_mes.csv",
                       taxa_lm.to_csv(index=False).encode("utf-8-sig"),
                       "taxa_loja_mes.csv", "text/csv")

    st.subheader("Resumo mensal")
    st.dataframe(mensal, use_container_width=True)

    st.subheader("Perdas (linha a linha, tratado)")
    st.dataframe(perdas.head(2000), use_container_width=True, height=300)
    st.download_button("⬇️ perdas_tratado.csv",
                       perdas.to_csv(index=False).encode("utf-8-sig"),
                       "perdas_tratado.csv", "text/csv")

    st.divider()
    st.subheader("Modelo de faturamento")
    st.caption("Baixe, preencha com os meses fechados (Power BI → Receita por "
               "Und. ID, um mês por vez) e envie na barra lateral.")
    modelo = pd.DataFrame(
        [(l, "2026-01", "") for l in
         sorted(int(x) for x in perdas.loc[~perdas["is_dep"], "loja"].dropna().unique())],
        columns=["loja", "ano_mes", "faturamento"])
    st.download_button("⬇️ faturamento_modelo.csv",
                       modelo.to_csv(index=False).encode("utf-8-sig"),
                       "faturamento_modelo.csv", "text/csv")
