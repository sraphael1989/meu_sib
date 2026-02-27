
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


def ui_aba_metas(backlog_df, config):
    st.header("🏁 Metas e Desafios")

    with st.form("add_meta_form"):
        st.subheader("Criar Nova Meta")
        c1, c2, c3 = st.columns(3)
        meta_tipo = c1.selectbox("Tipo de Mídia", ["Qualquer"] + sorted(backlog_df['Tipo'].unique().tolist()))
        meta_genero = c2.selectbox("Gênero Específico", ["Qualquer"] + sorted(backlog_df['Genero'].dropna().unique().tolist()))
        meta_quantidade = c3.number_input("Quantidade a Finalizar", min_value=1, value=10)
        meta_ano = st.number_input("Ano da Meta", min_value=datetime.now().year, value=datetime.now().year)

        if st.form_submit_button("Adicionar Meta", type="primary"):
            nova_meta = {"tipo": meta_tipo, "genero": meta_genero, "quantidade": meta_quantidade, "ano": meta_ano, "id": time.time()}
            st.session_state.config['metas'].append(nova_meta)
            salvar_config(st.session_state.config)
            st.success("Meta adicionada!")
            st.rerun()

    st.divider()
    st.subheader("Acompanhamento de Metas")
    
    if not config.get('metas', []):
        st.info("Nenhuma meta definida. Crie uma acima para começar!")
        return

    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'])

    for i, meta in enumerate(config['metas']):
        df_meta = df_finalizados[df_finalizados['Data_Finalizacao'].dt.year == meta['ano']]
        if meta['tipo'] != 'Qualquer': df_meta = df_meta[df_meta['Tipo'] == meta['tipo']]
        if meta['genero'] != 'Qualquer': df_meta = df_meta[df_meta['Genero'] == meta['genero']]
        
        progresso = len(df_meta)
        objetivo = meta['quantidade']
        percentual = min(progresso / objetivo, 1.0) if objetivo > 0 else 0
        
        st.markdown(f"**Meta {i+1}:** Finalizar {objetivo} itens de **{meta['tipo']}** do gênero **{meta['genero']}** em **{meta['ano']}**")
        st.progress(percentual, text=f"{progresso} / {objetivo}")


ui_aba_metas()