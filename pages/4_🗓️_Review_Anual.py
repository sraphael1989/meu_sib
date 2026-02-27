
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import io
import zipfile
import os
from db_connection import carregar_dados_db, salvar_dados_db, carregar_config_db, salvar_config_db, deletar_item_db
from ranking_logic import calcular_ranking
from premium_module import verificar_plano_usuario, bloquear_recurso_premium

# Configurações de Tabelas
TABELA_BACKLOG = "backlog_items"
TABELA_SESSOES = "sessoes"

# Garantir que o usuário está logado
if 'user' not in st.session_state:
    st.warning("Por favor, faça login na página inicial.")
    st.stop()


def ui_aba_review_anual(backlog_df):
    st.header("🗓️ Meu Ano em Review")
    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
    
    anos_disponiveis = sorted(df_finalizados['Data_Finalizacao'].dt.year.dropna().unique().astype(int), reverse=True)
    if not anos_disponiveis:
        st.warning("Nenhum item finalizado com data registrada. Finalize itens para gerar relatórios.")
        return
        
    ano_selecionado = st.selectbox("Selecione o ano para o relatório", anos_disponiveis)
    df_ano = df_finalizados[df_finalizados['Data_Finalizacao'].dt.year == ano_selecionado].copy()

    if df_ano.empty:
        st.info(f"Nenhum item finalizado registrado para o ano de {ano_selecionado}.")
        return

    st.subheader(f"Seu resumo de entretenimento em {ano_selecionado}")
    
    # Métricas Chave
    total_itens_ano = len(df_ano)
    nota_media_ano = df_ano[df_ano['Minha_Nota'] > 0]['Minha_Nota'].mean()
    total_horas_jogos_ano = df_ano[df_ano['Tipo'] == 'Jogo']['Duracao'].sum()
    total_paginas_livros_ano = df_ano[df_ano['Tipo'] == 'Livro']['Duracao'].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Itens Finalizados", f"{total_itens_ano}")
    c2.metric("Nota Média Pessoal", f"{nota_media_ano:.2f} ⭐" if pd.notna(nota_media_ano) else "N/A")
    c3.metric("Horas em Jogos", f"{total_horas_jogos_ano:.1f} h")
    c4.metric("Páginas Lidas", f"{total_paginas_livros_ano:.0f}")

    st.divider()

    # --- NOVA SEÇÃO DE DESTAQUES ---
    st.subheader("🏆 Destaques do Ano")
    
    # Item com a melhor nota
    melhor_item = df_ano.loc[df_ano['Minha_Nota'].idxmax()] if not df_ano[df_ano['Minha_Nota'] > 0].empty else None
    # Item mais longo (considerando apenas jogos em horas)
    item_mais_longo = df_ano.loc[df_ano[df_ano['Tipo'] == 'Jogo']['Duracao'].idxmax()] if not df_ano[df_ano['Tipo'] == 'Jogo'].empty else None

    c1, c2 = st.columns(2)
    with c1:
        if melhor_item is not None:
            st.markdown(f"**Melhor Avaliado:**")
            st.markdown(f"##### {melhor_item['Titulo']} ({melhor_item['Minha_Nota']:.0f} ⭐)")
        else:
            st.markdown("**Melhor Avaliado:**")
            st.info("Nenhum item avaliado este ano.")
    with c2:
        if item_mais_longo is not None:
            st.markdown(f"**Maior Jornada (Jogos):**")
            st.markdown(f"##### {item_mais_longo['Titulo']} ({item_mais_longo['Duracao']:.1f} h)")
        else:
            st.markdown("**Maior Jornada (Jogos):**")
            st.info("Nenhum jogo finalizado este ano.")

    st.divider()

    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Finalizações por Tipo")
        st.bar_chart(df_ano['Tipo'].value_counts())
    with c2:
        st.subheader("Gêneros Favoritos do Ano")
        generos_ano = df_ano['Genero'].dropna().str.split(',').explode().str.strip()
        if not generos_ano.empty:
            st.bar_chart(generos_ano.value_counts().head(10))
        else:
            st.info("Nenhum gênero registrado.")
        
    st.subheader("Ritmo de Finalizações ao Longo do Ano")
    finalizacoes_por_mes = df_ano.groupby(df_ano['Data_Finalizacao'].dt.month).size()
    # Cria um DataFrame com todos os meses para garantir a ordem
    meses_df = pd.DataFrame({'Mes': range(1, 13)})
    meses_df = meses_df.merge(finalizacoes_por_mes.rename('Contagem'), left_on='Mes', right_index=True, how='left').fillna(0)
    meses_df['Nome_Mes'] = meses_df['Mes'].apply(lambda x: pd.to_datetime(f'2024-{x}-01').strftime('%b'))
    st.bar_chart(meses_df.set_index('Nome_Mes')['Contagem'])

    # --- NOVA TABELA DE ITENS FINALIZADOS ---
    with st.expander(f"Ver todos os {total_itens_ano} itens finalizados em {ano_selecionado}"):
        df_display_ano = df_ano[['Titulo', 'Tipo', 'Minha_Nota', 'Data_Finalizacao']].copy()
        df_display_ano.rename(columns={'Titulo': 'Título', 'Tipo': 'Tipo', 'Minha_Nota': 'Minha Nota', 'Data_Finalizacao': 'Finalizado em'}, inplace=True)
        df_display_ano['Finalizado em'] = df_display_ano['Finalizado em'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_display_ano, use_container_width=True, hide_index=True)






ui_aba_review_anual()