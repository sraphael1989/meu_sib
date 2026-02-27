
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


def ui_aba_centro_de_acoes(acoes_pendentes_df, config):
    st.header("🎯 Centro de Ações 2.0")
    st.info("Aqui estão os itens do seu backlog que precisam de atenção, como dados faltantes ou inconsistentes.")

    if acoes_pendentes_df.empty:
        st.success("🎉 Parabéns! Seu backlog está totalmente preenchido e consistente. Nenhuma ação pendente encontrada.")
        return

    st.subheader(f"Itens com Ações Pendentes: {len(acoes_pendentes_df)}")

    for index, item in acoes_pendentes_df.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{item['Titulo']}** ({item['Tipo']})")
                # Exibe o motivo da pendência de forma clara
                st.caption(f"🚨 **Pendência:** {item['motivo']}")

            with c2:
                # --- ALTERAÇÃO AQUI: Botão de busca online para mais tipos ---
                tipos_com_busca = ["Jogo", "Filme", "Série", "Livro", "Anime"]
                if item['Tipo'] in tipos_com_busca and "Falta" in item['motivo']: # Só mostra se faltar dados
                    if st.button("Buscar Online", key=f"buscar_{item['ID']}", use_container_width=True):
                        st.session_state[f"buscando_item_{item['ID']}"] = True
                        st.rerun()

                # Botão para edição/preenchimento manual
                if st.button("Resolver Manualmente", key=f"manual_{item['ID']}", use_container_width=True):
                    # Reutiliza a aba "Gerenciar" para uma experiência de edição completa
                    st.warning(f"Para resolver, vá para a aba 'Gerenciar' e selecione '{item['Titulo']}'.")
                    st.session_state.gerenciar_select = item['Titulo'] # Pré-seleciona o item na outra aba


            # Lógica para exibir o formulário de busca online (agora genérico)
            if st.session_state.get(f"buscando_item_{item['ID']}"):
                st.write("---")
                st.subheader(f"Buscando dados para: {item['Titulo']}")
                
                resultados = buscar_dados_online_geral(item['Titulo'], item['Tipo'], config.get('api_keys', {}))
                
                if resultados:
                    dados = resultados[0]
                    st.success("Dados encontrados!")
                    
                    # Mostra o que foi encontrado
                    st.write(f"**Capa:**")
                    st.image(dados.get('cover_url'), width=150)
                    st.write(f"**Gênero(s):** {', '.join(dados.get('generos', []))}")
                    st.write(f"**Duração:** {dados.get('duracao', 0)}")

                    if st.button("Aplicar Dados Encontrados", key=f"aplicar_{item['ID']}", type="primary"):
                        idx_original = st.session_state.backlog_df[st.session_state.backlog_df['ID'] == item['ID']].index
                        
                        # Atualiza apenas os campos que estavam vazios, para não sobrescrever dados manuais
                        if pd.isnull(item.get('Cover_URL')) or item.get('Cover_URL') == '':
                            st.session_state.backlog_df.loc[idx_original, 'Cover_URL'] = dados.get('cover_url')
                        if pd.isnull(item.get('Genero')) or item.get('Genero') == '':
                            st.session_state.backlog_df.loc[idx_original, 'Genero'] = ", ".join(dados.get('generos', []))
                        if pd.to_numeric(item.get('Duracao'), errors='coerce') == 0:
                            st.session_state.backlog_df.loc[idx_original, 'Duracao'] = float(dados.get('duracao', 0))
                        if pd.to_numeric(item.get('Nota_Externa'), errors='coerce') == 0:
                             st.session_state.backlog_df.loc[idx_original, 'Nota_Externa'] = int(dados.get('nota_externa', 0))
                        
                        salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                        st.toast("Item atualizado com sucesso!")
                        del st.session_state[f"buscando_item_{item['ID']}"]
                        st.rerun()
                else:
                    st.error("Nenhum dado encontrado para este título.")











ui_aba_centro_de_acoes()