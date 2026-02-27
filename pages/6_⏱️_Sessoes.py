
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


def ui_aba_sessoes(sessoes_df, backlog_df):
    st.header("🎯 Sessões de Atividade")
    
    st.subheader("Registrar Nova Sessão")
    
    # Filtra itens que podem ter progresso registrado
    itens_ativos = backlog_df[backlog_df['Status'].isin(['Em Andamento', 'No Backlog'])].copy()
    
    if itens_ativos.empty:
        st.info("Você não tem itens 'Em Andamento' ou 'No Backlog' para registrar uma sessão.")
        return

    # Selectbox para escolher o item
    item_selecionado_titulo = st.selectbox(
        "Selecione o item para registrar a sessão:",
        options=itens_ativos['Titulo'].unique().tolist(),
        index=None, # Começa sem nada selecionado
        placeholder="Escolha um item..."
    )

    if item_selecionado_titulo:
        # Pega os dados do item selecionado
        item_selecionado = itens_ativos[itens_ativos['Titulo'] == item_selecionado_titulo].iloc[0]
        tipo_item = item_selecionado['Tipo']
        item_id = int(item_selecionado['ID'])

        with st.form(key=f"sessao_form_{item_id}"):
            st.write(f"Registrando sessão para **{item_selecionado_titulo}** ({tipo_item})")
            
            duracao_sessao = 0
            progresso_ganho = 0
            
            # --- FORMULÁRIO CONTEXTUAL ---
            if tipo_item == "Jogo":
                c1, c2 = st.columns(2)
                duracao_sessao = c1.number_input("Duração da Sessão (minutos)", min_value=0)
                progresso_ganho = c2.number_input("Conquistas Ganhas na Sessão", min_value=0)
            
            elif tipo_item == "Livro":
                progresso_ganho = st.number_input("Páginas Lidas na Sessão", min_value=0)
                # Para livros, a duração pode ser opcional ou não aplicável
                duracao_sessao = progresso_ganho * 2 # Estimativa de 2 min por página

            elif tipo_item in ["Série", "Anime"]:
                progresso_ganho = st.number_input("Episódios Assistidos na Sessão", min_value=1)
                duracao_sessao = progresso_ganho * 45 # Estimativa de 45 min por episódio

            elif tipo_item == "Mangá":
                progresso_ganho = st.number_input("Capítulos Lidos na Sessão", min_value=0)
                duracao_sessao = progresso_ganho * 5 # Estimativa de 5 min por capítulo
            
            elif tipo_item == "Filme":
                st.info("Filmes geralmente são finalizados em uma única sessão. Você pode registrar a finalização na aba 'Gerenciar'.")
                progresso_ganho = 0
                duracao_sessao = 0

            notas_sessao = st.text_area("Notas da Sessão (opcional)")
            
            if st.form_submit_button("Salvar Sessão", type="primary"):
                if progresso_ganho > 0 or duracao_sessao > 0:
                    max_id_sessao = st.session_state.sessoes_df['ID_Sessao'].max() if not st.session_state.sessoes_df.empty else 0

                    nova_sessao = {
                        "ID_Sessao": max_id_sessao + 1, "ID_Item": item_id, "Data": datetime.now().strftime("%Y-%m-%d"),
                        "Duracao_Sessao": duracao_sessao, "Progresso_Ganho": progresso_ganho, "Notas": notas_sessao
                    }
                    
                    st.session_state.sessoes_df = pd.concat([st.session_state.sessoes_df, pd.DataFrame([nova_sessao])], ignore_index=True)
                    salvar_dados(st.session_state.sessoes_df, ARQUIVO_SESSOES)
                    
                    # Atualiza o progresso no backlog
                    idx_backlog = st.session_state.backlog_df[st.session_state.backlog_df['ID'] == item_id].index
                    st.session_state.backlog_df.loc[idx_backlog, 'Progresso_Atual'] += progresso_ganho
                    
                    # Se o item não estava "Em Andamento", muda o status
                    if st.session_state.backlog_df.loc[idx_backlog, 'Status'].iloc[0] == 'No Backlog':
                        st.session_state.backlog_df.loc[idx_backlog, 'Status'] = 'Em Andamento'
                        st.toast("Status do item atualizado para 'Em Andamento'!")

                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                    
                    st.success("Sessão registrada e progresso atualizado!")
                    st.rerun()
                else:
                    st.warning("Nenhum progresso ou duração foi registrado para a sessão.")

    st.divider()
    st.subheader("Histórico de Sessões Recentes")
    if not sessoes_df.empty:
        # Junta os dataframes para mostrar o título do item
        df_display = sessoes_df.merge(backlog_df[['ID', 'Titulo']], left_on='ID_Item', right_on='ID', how='left')
        df_display_final = df_display[['Data', 'Titulo', 'Duracao_Sessao', 'Progresso_Ganho', 'Notas']].copy()
        df_display_final.columns = ["Data", "Título", "Duração (min)", "Progresso Ganho", "Notas"]
        # Mostra as 10 sessões mais recentes
        st.dataframe(df_display_final.sort_values(by="Data", ascending=False).head(10), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma sessão registrada ainda.")


ui_aba_sessoes()