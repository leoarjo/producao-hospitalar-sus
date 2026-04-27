"""
Aplicação Streamlit — Produção Hospitalar SIH/SUS
Dados Detalhados de AIH (SP) | Jan/2024 – Jan/2026 | Brasil/Município

Seções:
  1. Dados Armazenados  — tabela com filtros
  2. Estatísticas Descritivas
  3. Gráficos Interativos
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─── Configuração da página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="Produção Hospitalar SUS",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Estilo extra ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        .metric-card { background:#f0f2f6; border-radius:10px; padding:12px 18px; }
        .stTabs [data-baseweb="tab-list"] { gap: 20px; }
        footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Fonte de dados ───────────────────────────────────────────────────────────
# URL raw do GitHub — preencha após subir o CSV no repositório:
# Exemplo: https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/dados/producao_hospitalar.csv
GITHUB_CSV_URL = ""   # deixe vazio para usar apenas o arquivo local

CSV_LOCAL = Path(__file__).parent.parent / "dados" / "producao_hospitalar.csv"


# ─── Carregamento de dados ────────────────────────────────────────────────────
@st.cache_data(show_spinner="Carregando dados…")
def carregar_dados() -> pd.DataFrame:
    # 1. Tenta arquivo local
    if CSV_LOCAL.exists():
        df = pd.read_csv(CSV_LOCAL, sep=";", decimal=",", encoding="utf-8-sig",
                         dtype={"municipio_codigo": str})
        st.sidebar.caption("Fonte: CSV local")
        return df

    # 2. Tenta GitHub (se URL configurada)
    if GITHUB_CSV_URL:
        try:
            df = pd.read_csv(GITHUB_CSV_URL, sep=";", decimal=",",
                             dtype={"municipio_codigo": str})
            st.sidebar.caption("Fonte: GitHub")
            return df
        except Exception as e:
            st.error(f"Erro ao carregar do GitHub: {e}")

    return pd.DataFrame()


def formatar_br(valor: float, casas: int = 0) -> str:
    """Formata número no padrão brasileiro (1.234.567,89)."""
    formato = f",.{casas}f"
    return f"{valor:{formato}}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_kpi(valor: float) -> str:
    """Abrevia números grandes para bilhões, milhões ou milhares."""
    if valor >= 1_000_000_000:
        return f"{valor / 1_000_000_000:.2f} Bi".replace(".", ",")
    elif valor >= 1_000_000:
        return f"{valor / 1_000_000:.2f} Mi".replace(".", ",")
    elif valor >= 1_000:
        return f"{valor / 1_000:.2f} Mil".replace(".", ",")
    return str(int(valor))

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/4/41/Simple_flower_bud.png",
        width=60,
    )
    st.title("🏥 Produção Hospitalar")
    st.caption("SIH/SUS · Jan/2024 – Jan/2026 · Brasil/Município")
    st.markdown("---")

    df_full = carregar_dados()

    if df_full.empty:
        st.error(
            "Sem dados disponíveis. Execute o robô e depois o carregador primeiro."
        )
        st.stop()

    # Filtros
    st.subheader("Filtros")

    todos_subgrupos = sorted(df_full["subgrupo_proced"].unique())
    subgrupos_sel = st.multiselect(
        "Subgrupo de Procedimento",
        options=todos_subgrupos,
        default=[],
        placeholder="Todos os subgrupos",
    )

    busca_municipio = st.text_input("Buscar município", placeholder="Ex: Brasília")

    metrica = st.radio(
        "Métrica principal nos gráficos",
        options=["quantidade_aprovada", "valor_aprovado"],
        format_func=lambda x: "Qtd. Aprovada" if x == "quantidade_aprovada" else "Valor Aprovado (R$)",
    )

    top_n = st.slider("Top N municípios nos gráficos de ranking", 10, 30, 20)

    st.markdown("---")
    st.caption("Fonte: DATASUS / TabNet — SIH/SUS")


# ─── Aplicação de filtros ─────────────────────────────────────────────────────
df = df_full.copy()
if subgrupos_sel:
    df = df[df["subgrupo_proced"].isin(subgrupos_sel)]
if busca_municipio:
    df = df[df["municipio_nome"].str.contains(busca_municipio, case=False, na=False)]


# ─── Cabeçalho ────────────────────────────────────────────────────────────────
st.title("Produção Hospitalar SIH/SUS — Brasil")
st.markdown(
    "**Dados Detalhados de AIH (SP)** · Abrangência: **Brasil/Município** · "
    "Período: **Jan/2024 a Jan/2026** (25 meses)"
)

# KPIs rápidos
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total de registros", f"{len(df):,}".replace(",", "."))
col2.metric(
    "Municípios com produção",
    f"{df['municipio_nome'].nunique():,}".replace(",", "."),
    help="Municípios com ao menos um procedimento aprovado no período.",
)
col3.metric("Subgrupos", str(df["subgrupo_proced"].nunique()))

col4.metric(
    "Qtd. Aprovada Total",
    formatar_kpi(df_full["quantidade_aprovada"].sum()),
    help=f"Valor exato: {formatar_br(df_full['quantidade_aprovada'].sum())} (Coluna 'Total' excluída para evitar dupla contagem)."
)

col5.metric(
    "Valor Aprovado Total (R$)",
    formatar_kpi(df_full["valor_aprovado"].sum()),
    help=f"Valor exato: R$ {formatar_br(df_full['valor_aprovado'].sum(), 2)} (Coluna 'Total' excluída para evitar dupla contagem)."
)

st.markdown("---")


# ─── Abas ─────────────────────────────────────────────────────────────────────
aba_dados, aba_stats, aba_graficos = st.tabs(
    ["📋 Dados Armazenados", "📊 Estatísticas Descritivas", "📈 Gráficos"]
)

# ══════════════════════════════════════════════════════════════════════════════
# ABA 1 — DADOS ARMAZENADOS
# ══════════════════════════════════════════════════════════════════════════════
with aba_dados:
    st.subheader("Lista de Dados Armazenados")

    st.caption(
        f"Exibindo {len(df):,} registros (de {len(df_full):,} no total)".replace(",", ".")
    )

    # Formata colunas para exibição
    df_exib = df.copy()
    df_exib["quantidade_aprovada"] = df_exib["quantidade_aprovada"].apply(
        lambda x: formatar_br(x, 0)
    )
    df_exib["valor_aprovado"] = df_exib["valor_aprovado"].apply(
        lambda x: formatar_br(x, 2)
    )
    df_exib.columns = [
        "Código IBGE",
        "Município",
        "Subgrupo de Procedimento",
        "Qtd. Aprovada",
        "Valor Aprovado (R$)",
    ]

    st.dataframe(df_exib, use_container_width=True, height=520)

    # Download
    csv_bytes = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8")
    st.download_button(
        label="⬇ Baixar CSV filtrado",
        data=csv_bytes,
        file_name="producao_hospitalar_filtrado.csv",
        mime="text/csv",
    )


# ══════════════════════════════════════════════════════════════════════════════
# ABA 2 — ESTATÍSTICAS DESCRITIVAS
# ══════════════════════════════════════════════════════════════════════════════
with aba_stats:
    st.subheader("Estatísticas Descritivas")

    # ── Resumo geral ──────────────────────────────────────────────────────────
    st.markdown("#### Resumo Geral das Métricas Numéricas (por Município)")
    
    # 1. Primeiro agrupamos e somamos os valores por município
    df_agrupado_mun = df.groupby("municipio_nome")[["quantidade_aprovada", "valor_aprovado"]].sum()
    
    # 2. Depois geramos as estatísticas descritivas em cima desses totais
    desc = df_agrupado_mun.describe()
    
    desc.index.name = "Estatística"
    desc.columns = ["Qtd. Aprovada", "Valor Aprovado (R$)"]
    st.dataframe(desc.style.format("{:,.2f}"), use_container_width=True)

    st.markdown("---")

    col_l, col_r = st.columns(2)

    # ── Por subgrupo ──────────────────────────────────────────────────────────
    with col_l:
        st.markdown("#### Totais por Subgrupo de Procedimento")
        df_sub = (
            df.groupby("subgrupo_proced")[["quantidade_aprovada", "valor_aprovado"]]
            .sum()
            .sort_values("quantidade_aprovada", ascending=False)
            .reset_index()
        )
        df_sub.columns = ["Subgrupo", "Qtd. Aprovada", "Valor Aprovado (R$)"]
        st.dataframe(
            df_sub.style.format({"Qtd. Aprovada": "{:,.0f}", "Valor Aprovado (R$)": "{:,.2f}"}),
            use_container_width=True,
            height=400,
        )

    # ── Top 20 municípios ─────────────────────────────────────────────────────
    with col_r:
        st.markdown(f"#### Top {top_n} Municípios por Qtd. Aprovada")
        df_mun = (
            df.groupby("municipio_nome")[["quantidade_aprovada", "valor_aprovado"]]
            .sum()
            .sort_values("quantidade_aprovada", ascending=False)
            .head(top_n)
            .reset_index()
        )
        df_mun.columns = ["Município", "Qtd. Aprovada", "Valor Aprovado (R$)"]
        st.dataframe(
            df_mun.style.format({"Qtd. Aprovada": "{:,.0f}", "Valor Aprovado (R$)": "{:,.2f}"}),
            use_container_width=True,
            height=400,
        )

    st.markdown("---")

    # ── Concentração por UF ───────────────────────────────────────────────────
    st.markdown("#### Concentração por Estado (UF)")
    st.caption("Extraída do código IBGE do município (2 primeiros dígitos).")

    UF_MAP = {
        "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
        "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
        "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
        "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
        "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
        "52": "GO", "53": "DF",
    }

    df_uf = df.copy()
    df_uf["uf"] = df_uf["municipio_codigo"].str[:2].map(UF_MAP).fillna("??")
    df_uf_agg = (
        df_uf.groupby("uf")[["quantidade_aprovada", "valor_aprovado"]]
        .sum()
        .sort_values("quantidade_aprovada", ascending=False)
        .reset_index()
    )
    df_uf_agg.columns = ["UF", "Qtd. Aprovada", "Valor Aprovado (R$)"]
    df_uf_agg["% Qtd"] = (df_uf_agg["Qtd. Aprovada"] / df_uf_agg["Qtd. Aprovada"].sum() * 100).round(2)
    st.dataframe(
        df_uf_agg.style.format(
            {"Qtd. Aprovada": "{:,.0f}", "Valor Aprovado (R$)": "{:,.2f}", "% Qtd": "{:.2f}%"}
        ),
        use_container_width=True,
        height=400,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ABA 3 — GRÁFICOS
# ══════════════════════════════════════════════════════════════════════════════
with aba_graficos:
    st.subheader("Visualizações Interativas")

    label_metrica = (
        "Qtd. Aprovada" if metrica == "quantidade_aprovada" else "Valor Aprovado (R$)"
    )

    # ── Agrupamentos ──────────────────────────────────────────────────────────
    df_mun_agg = (
        df.groupby("municipio_nome")[["quantidade_aprovada", "valor_aprovado"]]
        .sum()
        .reset_index()
    )
    df_sub_agg = (
        df.groupby("subgrupo_proced")[["quantidade_aprovada", "valor_aprovado"]]
        .sum()
        .reset_index()
    )

    # ── Gráfico 1: Top N Municípios — barras horizontais ─────────────────────
    st.markdown(f"#### Top {top_n} Municípios — {label_metrica}")
    top_mun = df_mun_agg.nlargest(top_n, metrica).sort_values(metrica)
    fig1 = px.bar(
        top_mun,
        x=metrica,
        y="municipio_nome",
        orientation="h",
        labels={metrica: label_metrica, "municipio_nome": "Município"},
        color=metrica,
        color_continuous_scale="Blues",
        height=600,
    )
    fig1.update_layout(showlegend=False, yaxis_title="")
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("---")

    import numpy as np

    # ── Gráfico 2: Top 20 subgrupos — barras HORIZONTAIS ─────────────────────
    st.markdown(f"#### Top 20 Subgrupos de Procedimento — {label_metrica}")
    top20_sub = df_sub_agg.nlargest(20, metrica).sort_values(metrica)
    # Abrevia rótulos longos para melhor leitura
    top20_sub = top20_sub.copy()
    top20_sub["label"] = top20_sub["subgrupo_proced"].str[:60]
    fig2 = px.bar(
        top20_sub,
        x=metrica,
        y="label",
        orientation="h",
        labels={"label": "", metrica: label_metrica},
        color=metrica,
        color_continuous_scale="Blues",
        height=560,
        text=top20_sub[metrica].apply(lambda v: f"{v:,.0f}"),
    )
    fig2.update_traces(textposition="outside", cliponaxis=False)
    fig2.update_layout(showlegend=False, yaxis_title="", coloraxis_showscale=False,
                       margin=dict(l=10, r=80))
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")

    # ── Gráfico 3: Treemap por Subgrupo ──────────────────────────────────────
    st.markdown(f"#### Treemap — Participação dos Subgrupos ({label_metrica})")
    st.caption("Tamanho proporcional ao valor. Passe o mouse para ver detalhes.")
    fig3 = px.treemap(
        df_sub_agg,
        path=["subgrupo_proced"],
        values=metrica,
        color=metrica,
        color_continuous_scale="Blues",
        height=500,
    )
    fig3.update_traces(
        texttemplate="<b>%{label}</b><br>%{percentParent:.1%}",
        hovertemplate="<b>%{label}</b><br>" + label_metrica + ": %{value:,.0f}<extra></extra>",
    )
    fig3.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown("---")

    # ── Gráfico 4: Scatter Qtd × Valor ───────────────────────────────────────
    st.markdown("#### Relação entre Qtd. Aprovada e Valor Aprovado (por Município)")
    st.caption("Escala logarítmica. Passe o mouse para identificar o município.")
    df_scatter = df_mun_agg[
        (df_mun_agg["quantidade_aprovada"] > 0) & (df_mun_agg["valor_aprovado"] > 0)
    ]
    fig4 = px.scatter(
        df_scatter,
        x="quantidade_aprovada",
        y="valor_aprovado",
        hover_name="municipio_nome",
        labels={
            "quantidade_aprovada": "Qtd. Aprovada",
            "valor_aprovado": "Valor Aprovado (R$)",
        },
        color="valor_aprovado",
        color_continuous_scale="Viridis",
        log_x=True,
        log_y=True,
        height=500,
    )
    fig4.update_traces(marker=dict(size=5, opacity=0.65))
    fig4.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig4, use_container_width=True)

    st.markdown("---")

    # ── Gráfico 5: Heatmap Top 10 Municípios × Top 10 Subgrupos ─────────────
    N_MUN_HEAT = 10
    N_SUB_HEAT = 10
    st.markdown(f"#### Heatmap — Top {N_MUN_HEAT} Municípios × Top {N_SUB_HEAT} Subgrupos")
    st.caption("Escala logarítmica (log1p). Apenas as combinações mais relevantes.")

    top_muns_h = df_mun_agg.nlargest(N_MUN_HEAT, metrica)["municipio_nome"].tolist()
    top_subs_h = df_sub_agg.nlargest(N_SUB_HEAT, metrica)["subgrupo_proced"].tolist()

    df_heat = (
        df[df["municipio_nome"].isin(top_muns_h) & df["subgrupo_proced"].isin(top_subs_h)]
        .pivot_table(index="subgrupo_proced", columns="municipio_nome",
                     values=metrica, aggfunc="sum", fill_value=0)
    )

    # Abrevia rótulos das linhas (subgrupos no Y)
    row_labels = [r[:40] + "…" if len(r) > 40 else r for r in df_heat.index.tolist()]
    # Abrevia nomes de município (colunas no X)
    col_labels = [c[:18] for c in df_heat.columns.tolist()]
    z_log = np.log1p(df_heat.values)

    fig5 = go.Figure(
        data=go.Heatmap(
            z=z_log,
            x=col_labels,
            y=row_labels,
            colorscale="YlOrRd",
            hoverongaps=False,
            hovertemplate=(
                "Município: %{x}<br>"
                "Subgrupo: %{y}<br>"
                "log(1 + valor): %{z:.2f}<extra></extra>"
            ),
        )
    )
    fig5.update_layout(
        height=520,
        xaxis_tickangle=-30,
        xaxis_title="",
        yaxis_title="",
        yaxis_autorange="reversed",
        margin=dict(l=20, r=20, t=10, b=80),
    )
    st.plotly_chart(fig5, use_container_width=True)

    st.markdown("---")

    # ── Gráfico 5b: Por UF ────────────────────────────────────────────────────
    st.markdown(f"#### {label_metrica} por Unidade Federativa")
    UF_MAP = {
        "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
        "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
        "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
        "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
        "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
        "52": "GO", "53": "DF",
    }
    df_uf2 = df.copy()
    df_uf2["uf"] = df_uf2["municipio_codigo"].str[:2].map(UF_MAP).fillna("??")
    df_uf2_agg = (
        df_uf2.groupby("uf")[[metrica]]
        .sum()
        .sort_values(metrica, ascending=False)
        .reset_index()
    )
    fig6 = px.bar(
        df_uf2_agg,
        x="uf",
        y=metrica,
        labels={"uf": "UF", metrica: label_metrica},
        color=metrica,
        color_continuous_scale="Teal",
        height=420,
        text=df_uf2_agg[metrica].apply(lambda v: f"{v/1e6:.0f}M"),
    )
    fig6.update_traces(textposition="outside")
    fig6.update_layout(showlegend=False, xaxis_title="", coloraxis_showscale=False)
    st.plotly_chart(fig6, use_container_width=True)

    st.markdown("---")

    # ── Gráfico 6: Box-plot HORIZONTAL — Top 15 subgrupos ────────────────────
    N_SUB_BOX = 15
    st.markdown(f"#### Distribuição de {label_metrica} por Subgrupo — Top {N_SUB_BOX} (Box-plot)")
    st.caption("Ordenado pela mediana. Escala logarítmica. Apenas municípios com valor > 0.")

    top_subs_box = (
        df[df[metrica] > 0]
        .groupby("subgrupo_proced")[metrica]
        .median()
        .nlargest(N_SUB_BOX)
        .index.tolist()
    )
    df_box = df[(df[metrica] > 0) & (df["subgrupo_proced"].isin(top_subs_box))].copy()
    # Abrevia rótulos
    df_box["label"] = df_box["subgrupo_proced"].str[:40]
    # Ordena pela mediana
    ordem = (
        df_box.groupby("label")[metrica].median()
        .sort_values(ascending=True).index.tolist()
    )
    fig7 = px.box(
        df_box,
        y="label",
        x=metrica,
        orientation="h",
        category_orders={"label": ordem},
        labels={"label": "", metrica: label_metrica},
        color="label",
        log_x=True,
        height=620,
        points=False,   # remove pontos outliers (evita labels sobrepostos)
    )
    fig7.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Mín: %{lowerfence:,.0f}<br>"
            "Q1: %{q1:,.0f}<br>"
            "Mediana: %{median:,.0f}<br>"
            "Q3: %{q3:,.0f}<br>"
            "Máx: %{upperfence:,.0f}<extra></extra>"
        )
    )
    fig7.update_layout(
        showlegend=False,
        yaxis_title="",
        margin=dict(l=10, r=30, t=10, b=40),
    )
    st.plotly_chart(fig7, use_container_width=True)

# ── Gráfico Extra 1: Gráfico de Pareto (Curva ABC) ────────────────────────
    st.markdown("#### Curva ABC (Pareto) — Concentração do Valor Aprovado por Subgrupo")
    st.caption("A linha vermelha mostra o percentual acumulado do orçamento. Descubra quais procedimentos somam 80% dos gastos.")
    
    # Prepara os dados: ordena por valor e calcula o % acumulado
    df_pareto = df_sub_agg.sort_values("valor_aprovado", ascending=False).copy()
    df_pareto["perc_acumulado"] = df_pareto["valor_aprovado"].cumsum() / df_pareto["valor_aprovado"].sum() * 100
    
    # Pega apenas os top 20 para o gráfico não ficar esmagado
    df_pareto_top = df_pareto.head(20).copy()
    df_pareto_top["label"] = df_pareto_top["subgrupo_proced"].str[:30] + "..."

    fig_pareto = go.Figure()
    
    # Eixo Y primário (Barras de Valor)
    fig_pareto.add_trace(go.Bar(
        x=df_pareto_top["label"],
        y=df_pareto_top["valor_aprovado"],
        name="Valor Aprovado",
        marker_color="#1f77b4"
    ))
    
    # Eixo Y secundário (Linha de % Acumulado)
    fig_pareto.add_trace(go.Scatter(
        x=df_pareto_top["label"],
        y=df_pareto_top["perc_acumulado"],
        name="% Acumulado",
        mode="lines+markers",
        marker_color="red",
        yaxis="y2"
    ))

    fig_pareto.update_layout(
        height=550,
        xaxis_tickangle=-45,
        yaxis=dict(title="Valor Aprovado (R$)", side="left"),
        yaxis2=dict(title="% Acumulado", side="right", overlaying="y", range=[0, 105]),
        showlegend=False,
        hovermode="x unified",
        margin=dict(b=100)
    )
    st.plotly_chart(fig_pareto, use_container_width=True)
    st.markdown("---")

# ── Gráfico Extra 2: Ticket Médio por Subgrupo ────────────────────────────
    st.markdown("#### Custo Unitário Médio (Ticket Médio) por Subgrupo")
    st.caption("Quais são os procedimentos mais caros por unidade? (Valor Total ÷ Qtd Total)")
    
    # Calcula o ticket médio ignorando divisões por zero
    df_ticket = df_sub_agg[df_sub_agg["quantidade_aprovada"] > 0].copy()
    df_ticket["ticket_medio"] = df_ticket["valor_aprovado"] / df_ticket["quantidade_aprovada"]
    
    # Pega os 15 procedimentos mais caros na média
    top_tickets = df_ticket.nlargest(15, "ticket_medio").sort_values("ticket_medio", ascending=True)
    top_tickets["label"] = top_tickets["subgrupo_proced"].str[:40] + "..."

    fig_ticket = px.bar(
        top_tickets,
        x="ticket_medio",
        y="label",
        orientation="h",
        labels={"ticket_medio": "Custo Médio (R$)", "label": ""},
        color="ticket_medio",
        color_continuous_scale="Reds",
        height=500,
        text=top_tickets["ticket_medio"].apply(lambda v: f"R$ {v:,.2f}")
    )
    fig_ticket.update_traces(textposition="outside", cliponaxis=False)
    fig_ticket.update_layout(showlegend=False, coloraxis_showscale=False)
    
    st.plotly_chart(fig_ticket, use_container_width=True)
    st.markdown("---")

# ── Gráfico Extra 3: Sunburst (Hierarquia de UF para Subgrupo) ────────────
    st.markdown(f"#### Explosão Solar: Participação de UF e Subgrupo ({label_metrica})")
    st.caption("Gráfico interativo! **Clique em uma UF** para ver a distribuição interna dela.")

    # Cria a coluna UF caso não esteja disponível no escopo atual
    df_sun = df.copy()
    df_sun["uf"] = df_sun["municipio_codigo"].str[:2].map(UF_MAP).fillna("Outros")
    
    # Agrupa por UF e Subgrupo
    df_sun_agg = df_sun.groupby(["uf", "subgrupo_proced"])[[metrica]].sum().reset_index()
    
    # Remove zeros e filtra um pouco para o gráfico não travar o navegador
    df_sun_agg = df_sun_agg[df_sun_agg[metrica] > 0]
    
    # Para o Sunburst não ficar ilegível, vamos agrupar procedimentos muito pequenos em "Outros"
    limite = df_sun_agg[metrica].sum() * 0.005 # Corte de 0.5% do total
    df_sun_agg["subgrupo_curto"] = df_sun_agg.apply(
        lambda row: row["subgrupo_proced"][:30] + "..." if row[metrica] > limite else "Outros (menores)", axis=1
    )
    
    # Reagrupa com o nome encurtado
    df_sun_agg = df_sun_agg.groupby(["uf", "subgrupo_curto"])[[metrica]].sum().reset_index()

    fig_sun = px.sunburst(
        df_sun_agg,
        path=["uf", "subgrupo_curto"],
        values=metrica,
        color="uf",
        color_discrete_sequence=px.colors.qualitative.Pastel,
        height=650
    )
    
    fig_sun.update_traces(hovertemplate="<b>%{label}</b><br>Valor: %{value:,.0f}<extra></extra>")
    fig_sun.update_layout(margin=dict(t=10, l=10, r=10, b=10))
    
    st.plotly_chart(fig_sun, use_container_width=True)





