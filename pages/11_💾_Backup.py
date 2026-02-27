
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


def ui_aba_backup():
    st.header("Backup e Restauro de Dados")
    st.subheader("Exportar Backup")
    st.info("Clique para descarregar um ficheiro .zip com todos os seus dados.")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # --- MELHORIA DE ROBUSTEZ ---
        # Adiciona ao zip apenas os arquivos que existem
        for f in [ARQUIVO_BACKLOG, ARQUIVO_CONFIG, ARQUIVO_SESSOES]:
            if os.path.exists(f):
                zf.write(f)
                
    st.download_button(
        label="Descarregar Backup", 
        data=zip_buffer.getvalue(), 
        file_name=f"sib_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip", 
        mime="application/zip"
    )
    
    st.divider()
    st.subheader("Importar Backup")
    st.warning("Atenção: A importação substituirá todos os seus dados atuais.", icon="⚠️")
    uploaded_file = st.file_uploader("Carregue o seu ficheiro de backup (.zip)", type="zip")
    
    if uploaded_file:
        if st.button("Restaurar a partir deste Backup", type="primary"):
            try:
                with zipfile.ZipFile(uploaded_file, 'r') as zf:
                    zf.extractall(".")
                
                # --- MELHORIA DE USABILIDADE ---
                st.success("Backup restaurado com sucesso! A aplicação será reiniciada em 3 segundos...")
                time.sleep(3)
                st.session_state.clear() # Limpa o cache para forçar o recarregamento dos novos arquivos
                st.rerun()
            except Exception as e:
                st.error(f"Ocorreu um erro ao restaurar: {e}")


ui_aba_backup()