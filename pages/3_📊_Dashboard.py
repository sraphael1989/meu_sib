
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


def ui_aba_dashboard(backlog_df):
    st.header("Dashboard de Estatísticas")
    if backlog_df.empty:
        st.warning("Seu backlog está vazio. Adicione itens para ver as estatísticas.")
        return

    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Adicao'] = pd.to_datetime(df_finalizados['Data_Adicao'], errors='coerce')
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
    
    tempo_para_finalizar = (df_finalizados['Data_Finalizacao'] - df_finalizados['Data_Adicao']).dt.days
    tempo_medio_finalizar = tempo_para_finalizar.mean()

    total_itens = len(backlog_df)
    itens_finalizados = len(df_finalizados)
    percentual_finalizado = (itens_finalizados / total_itens) * 100 if total_itens > 0 else 0
    hype_medio = backlog_df[backlog_df['Status'] != 'Finalizado']['Meu_Hype'].mean()

    st.subheader("Visão Geral do seu Backlog")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Itens", f"{total_itens}")
    c2.metric("Itens Finalizados", f"{itens_finalizados} ({percentual_finalizado:.1f}%)")
    c3.metric("Hype Médio (em aberto)", f"{hype_medio:.2f}/10" if pd.notna(hype_medio) else "N/A")
    c4.metric("Tempo Médio na Fila", f"{tempo_medio_finalizar:.0f} dias" if pd.notna(tempo_medio_finalizar) else "N/A", help="Tempo médio entre adicionar e finalizar um item.")

    st.divider()

    tabs = st.tabs(["📊 Geral", "🎮 Jogos", "📚 Livros", "📺 Séries", "🎌 Animes", "🎬 Filmes", "📖 Mangás"])

    with tabs[0]: # Geral
        st.subheader("Análise Geral")
        
        # --- NOVA SEÇÃO DE AFINIDADE DE GÊNERO ---
        st.write("**Seus Gêneros Favoritos (por Afinidade)**", help="Calculado com base nos gêneros que você finaliza e avalia bem (nota >= 7). Mostra o que você realmente mais gosta!")
        afinidades = calcular_afinidade_genero(backlog_df)
        if afinidades:
            # Converte o dicionário para um DataFrame para facilitar a plotagem
            df_afinidade_plot = pd.DataFrame(list(afinidades.items()), columns=['Gênero', 'Pontuação de Afinidade'])
            df_afinidade_plot = df_afinidade_plot.sort_values('Pontuação de Afinidade', ascending=False).head(10)
            st.bar_chart(df_afinidade_plot.set_index('Gênero'))
        else:
            st.info("Finalize e avalie mais itens (com nota 7 ou superior) para descobrirmos seus gêneros favoritos!")
        
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.write("**Itens por Status**")
            st.bar_chart(backlog_df['Status'].value_counts())
        with c2:
            st.write("**Itens por Tipo de Mídia**")
            st.bar_chart(backlog_df['Tipo'].value_counts())

        st.write("**Distribuição das suas Notas (Itens Finalizados)**")
        notas_validas = df_finalizados[df_finalizados['Minha_Nota'] > 0]['Minha_Nota']
        if not notas_validas.empty:
            st.bar_chart(notas_validas.value_counts().sort_index())
        else:
            st.info("Avalie itens finalizados para ver a distribuição das suas notas.")
        ui_componente_hall_of_fame(backlog_df)

    with tabs[1]: # Jogos
        st.subheader("Análise de Jogos")
        df_jogos = backlog_df[backlog_df['Tipo'] == 'Jogo'].copy()
        if not df_jogos.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Desenvolvedoras**")
                st.bar_chart(df_jogos['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Plataformas**")
                st.bar_chart(df_jogos['Plataforma'].value_counts().head(5))
            st.write("**Gêneros de Jogos Mais Comuns (por quantidade)**")
            generos_jogos = df_jogos['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_jogos.value_counts().head(10))
        else:
            st.info("Nenhum jogo no seu backlog para análise.")

    with tabs[2]: # Livros
        st.subheader("Análise de Livros")
        df_livros = backlog_df[backlog_df['Tipo'] == 'Livro'].copy()
        if not df_livros.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Autores**")
                st.bar_chart(df_livros['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Gêneros Literários**")
                generos_livros = df_livros['Genero'].dropna().str.split(',').explode().str.strip()
                st.bar_chart(generos_livros.value_counts().head(5))
        else:
            st.info("Nenhum livro no seu backlog para análise.")

    with tabs[3]: # Séries
        st.subheader("Análise de Séries")
        df_series = backlog_df[backlog_df['Tipo'] == 'Série'].copy()
        if not df_series.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_series = df_series['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_series.value_counts().head(10))
        else:
            st.info("Nenhuma série no seu backlog para análise.")

    with tabs[4]: # Animes
        st.subheader("Análise de Animes")
        df_animes = backlog_df[backlog_df['Tipo'] == 'Anime'].copy()
        if not df_animes.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_animes = df_animes['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_animes.value_counts().head(10))
        else:
            st.info("Nenhum anime no seu backlog para análise.")

    with tabs[5]: # Filmes
        st.subheader("Análise de Filmes")
        df_filmes = backlog_df[backlog_df['Tipo'] == 'Filme'].copy()
        if not df_filmes.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_filmes = df_filmes['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_filmes.value_counts().head(10))
        else:
            st.info("Nenhum filme no seu backlog para análise.")

    with tabs[6]: # Mangás
        st.subheader("Análise de Mangás")
        df_mangas = backlog_df[backlog_df['Tipo'] == 'Mangá'].copy()
        if not df_mangas.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Autores (Mangakás)**")
                st.bar_chart(df_mangas['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Gêneros/Demografias**")
                generos_mangas = df_mangas['Genero'].dropna().str.split(',').explode().str.strip()
                st.bar_chart(generos_mangas.value_counts().head(5))
        else:
            st.info("Nenhum mangá no seu backlog para análise.")







ui_aba_dashboard()