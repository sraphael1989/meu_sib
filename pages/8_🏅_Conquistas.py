
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


def ui_aba_conquistas(config):
    st.header("🏆 Conquistas 🏆")
    st.info("Aqui estão todas as suas conquistas. As desbloqueadas ficam no topo!")
    
    conquistas = config.get('conquistas', {})
    if not conquistas:
        st.warning("Nenhuma conquista encontrada na configuração.")
        return

    desbloqueadas = {k: v for k, v in conquistas.items() if v['desbloqueada']}
    bloqueadas = {k: v for k, v in conquistas.items() if not v['desbloqueada']}

    # Seção de Conquistas Desbloqueadas
    if desbloqueadas:
        st.subheader("⭐ Desbloqueadas ⭐")
        cols = st.columns(4)
        i = 0
        for key, data in desbloqueadas.items():
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: #FFD700;'>🏆 {data['nome']}</h3>", unsafe_allow_html=True)
                    st.success(f"**Desbloqueada em:** {pd.to_datetime(data['data']).strftime('%d/%m/%Y')}")
                    st.caption(data['desc'])
            i += 1
    
    st.divider()

    # Seção de Conquistas Bloqueadas
    if bloqueadas:
        st.subheader("🔒 A Desbloquear 🔒")
        cols = st.columns(4)
        i = 0
        for key, data in bloqueadas.items():
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: grey;'>🔒 {data['nome']}</h3>", unsafe_allow_html=True)
                    st.warning("**Bloqueada**")
                    st.caption(data['desc'])
            i += 1



ui_aba_conquistas()