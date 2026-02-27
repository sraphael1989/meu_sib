
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


def ui_aba_estante(backlog_df):
    st.header("📚 Minha Estante Virtual")
    st.info("Aqui estão todos os itens que você já finalizou. Parabéns!")
    
    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    
    if df_finalizados.empty:
        st.warning("Sua estante está vazia. Finalize alguns itens para começar!")
        return
        
    c1, c2, c3 = st.columns(3)
    with c1:
        tipos = ["Todos"] + sorted(df_finalizados['Tipo'].unique().tolist())
        tipo_filtro = st.selectbox("Filtrar por Tipo", tipos, key="estante_tipo")
    with c2:
        # Garante que a coluna de data de finalização seja do tipo datetime
        df_finalizados['Data_Finalizacao_dt'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
        anos = ["Todos"] + sorted(df_finalizados['Data_Finalizacao_dt'].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
        ano_filtro = st.selectbox("Filtrar por Ano de Finalização", anos, key="estante_ano")
    with c3:
        ordem = st.selectbox("Ordenar por", ["Data de Finalização (Recente)", "Minha Nota (Maior)", "Título"], key="estante_ordem")

    if tipo_filtro != "Todos": df_finalizados = df_finalizados[df_finalizados['Tipo'] == tipo_filtro]
    if ano_filtro != "Todos": df_finalizados = df_finalizados[df_finalizados['Data_Finalizacao_dt'].dt.year == ano_filtro]
    
    if ordem == "Minha Nota (Maior)": df_finalizados = df_finalizados.sort_values('Minha_Nota', ascending=False)
    elif ordem == "Título": df_finalizados = df_finalizados.sort_values('Titulo')
    else: df_finalizados = df_finalizados.sort_values('Data_Finalizacao_dt', ascending=False)

    if df_finalizados.empty:
        st.info("Nenhum item corresponde aos filtros selecionados.")
        return

    cols = st.columns(5)
    for i, row in df_finalizados.reset_index().iterrows():
        with cols[i % 5]:
            with st.container(border=True):
                cover_url = row.get('Cover_URL', '')
                titulo_item = row.get('Titulo', 'Sem Título')

                if pd.notna(cover_url) and cover_url:
                    st.image(cover_url, caption=titulo_item)
                else:
                    st.image(f"https://placehold.co/400x600/222/fff?text={titulo_item}", caption=titulo_item )
                
                # Exibe a nota
                st.markdown(f"**Nota:** {row.get('Minha_Nota', 0):.0f} ⭐")

                # --- NOVA FUNCIONALIDADE AQUI ---
                # Exibe o tempo final de conclusão, se disponível
                tempo_final = float(row.get('Tempo_Final', 0))
                if tempo_final > 0:
                    unidade = row.get('Unidade_Duracao', 'unidades')
                    st.caption(f"Finalizado em: {tempo_final:.1f} {unidade}")

                if st.button("Ver Detalhes", key=f"details_{row['ID']}", use_container_width=True):
                    st.session_state[f"dialog_open_{row['ID']}"] = True

            if st.session_state.get(f"dialog_open_{row['ID']}", False):
                @st.dialog(f"Visualizando: {titulo_item}")
                def show_details_dialog(item_row):
                    cover_url_dialog = item_row.get('Cover_URL', '')
                    if pd.notna(cover_url_dialog) and cover_url_dialog:
                        st.image(cover_url_dialog)
                    else:
                        st.image(f"https://placehold.co/400x600/222/fff?text={item_row['Titulo']}" )
                    
                    data_finalizacao_str = pd.to_datetime(item_row.get('Data_Finalizacao')).strftime('%d/%m/%Y') if pd.notna(item_row.get('Data_Finalizacao')) else "Data não registrada"
                    st.write(f"**Finalizado em:** {data_finalizacao_str}")
                    st.write(f"**Sua Nota:** {item_row.get('Minha_Nota', 0):.0f} ⭐")
                    
                    tempo_final_dialog = float(item_row.get('Tempo_Final', 0))
                    if tempo_final_dialog > 0:
                        unidade_dialog = item_row.get('Unidade_Duracao', 'unidades')
                        st.write(f"**Tempo de Conclusão:** {tempo_final_dialog:.1f} {unidade_dialog}")

                show_details_dialog(row)
                st.session_state[f"dialog_open_{row['ID']}"] = False # Fecha o dialog para a próxima interação









ui_aba_estante()