
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


def ui_aba_gerenciar(backlog_df):
    st.header("Gerenciar Item do Backlog")
    if backlog_df.empty:
        st.info("Seu backlog está vazio.")
        return

    titulos = [""] + sorted(backlog_df['Titulo'].tolist())
    item_selecionado_titulo = st.selectbox("Selecione um item para editar ou excluir", titulos, key="gerenciar_select")
    
    if item_selecionado_titulo:
        idx = backlog_df[backlog_df['Titulo'] == item_selecionado_titulo].index[0]
        item_original = backlog_df.loc[idx].copy()

        with st.form("edit_form"):
            st.subheader(f"Editando: {item_original['Titulo']}")
            
            novo_titulo = st.text_input("Título", value=item_original['Titulo'])
            nova_cover_url = st.text_input("URL da Capa", value=item_original.get('Cover_URL', ''))
            
            status_opts = ["No Backlog", "Em Andamento", "Finalizado", "Desejo", "Arquivado"]
            novo_status = st.selectbox("Status", status_opts, index=status_opts.index(item_original['Status']))
            
            novo_hype = st.slider("Meu Hype", 0, 10, int(item_original.get('Meu_Hype', 0)))
            
            nova_minha_nota = item_original.get('Minha_Nota', 0)
            novo_tempo_final = item_original.get('Tempo_Final', 0)

            if novo_status == 'Finalizado':
                st.divider()
                st.write("⭐ **Informações de Finalização**")
                c1, c2 = st.columns(2)
                with c1:
                    nova_minha_nota = st.slider("Minha Nota Pessoal", 1, 10, max(1, int(item_original.get('Minha_Nota', 5))))
                with c2:
                    tempo_final_val = item_original.get('Tempo_Final') or 0
                    duracao_val = item_original.get('Duracao') or 0
                    valor_padrao_tempo = float(tempo_final_val) if float(tempo_final_val) > 0 else float(duracao_val)
                    
                    # --- TOOLTIP ADICIONADO AQUI ---
                    novo_tempo_final = st.number_input(f"Tempo Final de Conclusão ({item_original.get('Unidade_Duracao', 'unidades')})", min_value=0.0, value=valor_padrao_tempo, step=0.5, format="%.1f", help="Informe o tempo real que você levou para finalizar. Este valor será usado para o cálculo de PLs. Se deixado em 0, o sistema usará a duração estimada.")
                st.divider()

            st.write("Detalhes Adicionais")
            nova_plataforma = st.text_input("Plataforma", value=item_original.get('Plataforma', ''))
            novo_autor = st.text_input("Autor / Dev.", value=item_original.get('Autor', ''))
            novo_genero = st.text_input("Gênero", value=item_original.get('Genero', ''))
            
            st.divider()
            eh_serie_default = bool(item_original.get('Nome_Serie'))
            eh_serie = st.checkbox("Faz parte de uma série?", value=eh_serie_default, key="edit_eh_serie")
            
            novo_nome_serie = item_original.get('Nome_Serie', '')
            nova_ordem_serie = int(item_original.get('Ordem_Serie', 1))
            novo_total_serie = int(item_original.get('Total_Serie', 1))
            
            if eh_serie:
                c1, c2, c3 = st.columns(3)
                novo_nome_serie = c1.text_input("Nome da Série", value=novo_nome_serie)
                nova_ordem_serie = c2.number_input("Ordem na Série", min_value=1, value=nova_ordem_serie)
                novo_total_serie = c3.number_input("Total na Série", min_value=1, value=novo_total_serie)
            st.divider()

            st.write("Progresso")
            if item_original['Tipo'] == 'Jogo':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Conquistas Atuais", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Conquistas", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] in ['Série', 'Anime']:
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Episódio Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Episódios", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] == 'Livro':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Página Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Páginas", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] == 'Mangá':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Edição/Capítulo Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Edições/Capítulos", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            else:
                novo_prog_atual = item_original.get('Progresso_Atual', 0)
                novo_prog_total = item_original.get('Progresso_Total', 0)

            st.divider()
            cs, ce = st.columns(2)
            if cs.form_submit_button("Salvar Alterações", type="primary", use_container_width=True):
                dados_atualizados = {
                    'Titulo': novo_titulo, 'Cover_URL': nova_cover_url, 'Status': novo_status,
                    'Meu_Hype': novo_hype, 'Minha_Nota': nova_minha_nota, 'Plataforma': nova_plataforma,
                    'Autor': novo_autor, 'Genero': novo_genero,
                    'Nome_Serie': novo_nome_serie if eh_serie else "",
                    'Ordem_Serie': nova_ordem_serie if eh_serie else 1,
                    'Total_Serie': novo_total_serie if eh_serie else 1,
                    'Progresso_Atual': novo_prog_atual, 'Progresso_Total': novo_prog_total,
                    'Tempo_Final': novo_tempo_final
                }

                if novo_status == 'Finalizado' and item_original['Status'] != 'Finalizado':
                    tempo_usado_para_calculo = float(novo_tempo_final) if float(novo_tempo_final) > 0 else float(item_original.get('Duracao', 0))
                    conversor = st.session_state.config['conversores_pl'].get(item_original['Unidade_Duracao'], 1)
                    pls_ganhos = tempo_usado_para_calculo / conversor if conversor > 0 else 0
                    st.session_state.config['pontos_liberacao'] += pls_ganhos
                    st.toast(f"Item finalizado! Você ganhou {pls_ganhos:.1f} PLs!")
                    dados_atualizados['Data_Finalizacao'] = datetime.now().strftime("%Y-%m-%d")
                    
                    st.session_state.config = verificar_conquistas(st.session_state.backlog_df, st.session_state.config, item_id=item_original['ID'])
                
                for chave, valor in dados_atualizados.items():
                    st.session_state.backlog_df.loc[idx, chave] = valor

                salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                salvar_config(st.session_state.config)
                st.success("Item atualizado!")
                st.rerun()

            if ce.form_submit_button("EXCLUIR PERMANENTEMENTE", use_container_width=True):
                st.session_state.backlog_df = st.session_state.backlog_df.drop(idx).reset_index(drop=True)
                salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                st.warning(f"'{item_selecionado_titulo}' foi excluído.")
                st.rerun()










ui_aba_gerenciar()