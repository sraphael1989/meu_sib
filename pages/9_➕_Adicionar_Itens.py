
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


def ui_aba_adicionar_itens():
    st.header("Adicionar Itens")
    
    if 'add_mode' not in st.session_state:
        st.session_state.add_mode = "Individualmente"

    add_mode_options = ["Individualmente", "Série / Volumes", "Em Lote (Busca Inteligente)"]
    st.session_state.add_mode = st.radio("Como deseja adicionar?", add_mode_options, horizontal=True, key="add_mode_selector")
    add_mode = st.session_state.add_mode

    if add_mode == "Individualmente":
        if 'tipo_selecionado_add' not in st.session_state:
            st.session_state.tipo_selecionado_add = "Jogo"

        tipos_entretenimento = ["Jogo", "Livro", "Série", "Filme", "Anime", "Mangá"]
        st.session_state.tipo_selecionado_add = st.selectbox("Primeiro, selecione o tipo de entretenimento:", tipos_entretenimento, key="tipo_selector_add")
        tipo_selecionado = st.session_state.tipo_selecionado_add

        with st.form("add_individual_form"):
            st.subheader(f"Adicionar Novo(a) {tipo_selecionado}")
            
            titulo = st.text_input("Título*")
            
            if tipo_selecionado != "Mangá":
                if st.form_submit_button("Buscar Dados Online", use_container_width=True):
                    if titulo:
                        st.session_state.busca_titulo = titulo
                        st.session_state.resultados_busca = buscar_dados_online_geral(titulo, tipo_selecionado, st.session_state.config.get('api_keys', {}))
                    else:
                        st.warning("Por favor, insira um título para buscar.")

            if st.session_state.get('resultados_busca'):
                st.write("---")
                st.subheader("Confirme os Dados Encontrados")
                dados_encontrados = st.session_state.resultados_busca[0]
                
                cover_url = st.text_input("URL da Capa", value=dados_encontrados.get('cover_url', ''))
                autor = st.text_input("Autor / Criador / Dev.", value=dados_encontrados.get('autor', ''))
                genero = st.text_input("Gênero", value=", ".join(dados_encontrados.get('generos', [])))
                nota_externa = st.number_input("Nota Externa (0-100)", min_value=0, max_value=100, value=int(dados_encontrados.get('nota_externa', 0)), help="Nota da crítica. A busca online tenta preencher este campo.")
                
                unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                unidade_atual = unidade_map.get(tipo_selecionado, 'unidades')
                duracao = st.number_input(f"Duração ({unidade_atual})", min_value=0.0, value=float(dados_encontrados.get('duracao', 0)), step=1.0, format="%.0f")
                plataforma = st.text_input("Plataforma", value=dados_encontrados.get('plataforma', ''))

            else:
                cover_url = st.text_input("URL da Imagem da Capa")
                plataforma = st.text_input("Plataforma")
                autor = st.text_input("Autor / Desenvolvedora")
                genero = st.text_input("Gênero")
                nota_externa = st.number_input("Nota Externa (0-100)", min_value=0, max_value=100, value=0, help="Nota da crítica (ex: Metacritic).")
                unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                duracao = st.number_input(f"Duração ({unidade_map.get(tipo_selecionado, 'unidades')})", min_value=0.0, value=0.0, step=0.5, format="%.1f")

            status = st.selectbox("Status", ["No Backlog", "Desejo", "Em Andamento", "Finalizado"])
            meu_hype = st.slider("Meu Hype (0-10)", 0, 10, 0)
            st.divider()
            
            eh_serie = st.checkbox("Faz parte de uma série?", key="add_eh_serie")
            nome_serie, ordem_serie, total_serie = "", 1, 1
            if eh_serie:
                c1, c2, c3 = st.columns(3)
                nome_serie = c1.text_input("Nome da Série")
                ordem_serie = c2.number_input("Ordem na Série", min_value=1, value=1)
                total_serie = c3.number_input("Total na Série", min_value=1, value=1)
            st.divider()

            prog_atual, prog_total = 0, 0
            if tipo_selecionado == 'Jogo':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Conquistas Atuais", min_value=0, value=0)
                prog_total = c2.number_input("Total de Conquistas", min_value=0, value=1)
            elif tipo_selecionado in ['Série', 'Anime']:
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Episódio Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Episódios", min_value=0, value=1)
            elif tipo_selecionado == 'Livro':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Página Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Páginas", min_value=0, value=1)
            elif tipo_selecionado == 'Mangá':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Edição/Capítulo Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Edições/Capítulos", min_value=0, value=1)

            if st.form_submit_button("Salvar Item", type="primary"):
                if not titulo:
                    st.error("O campo 'Título' é obrigatório.")
                elif st.session_state.backlog_df['Titulo'].str.contains(f'^{titulo}$', case=False, regex=True).any():
                    st.error(f"ERRO: Um item com o título '{titulo}' já existe no backlog.")
                else:
                    max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                    unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                    
                    novo_item = {
                        "ID": max_id + 1, "Titulo": titulo, "Tipo": tipo_selecionado, "Plataforma": plataforma,
                        "Autor": autor, "Genero": genero, "Status": status, "Meu_Hype": meu_hype,
                        "Nota_Externa": nota_externa, "Duracao": duracao, "Unidade_Duracao": unidade_map.get(tipo_selecionado, 'unidades'),
                        "Nome_Serie": nome_serie if eh_serie else "", 
                        "Ordem_Serie": ordem_serie if eh_serie else 1, 
                        "Total_Serie": total_serie if eh_serie else 1,
                        "Data_Adicao": datetime.now().strftime("%Y-%m-%d"), 
                        "Progresso_Atual": prog_atual, "Progresso_Total": prog_total, "Minha_Nota": 0,
                        "Cover_URL": cover_url, "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": origem_selecionada
                    }
                    novo_df = pd.DataFrame([novo_item])
                    st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, novo_df], ignore_index=True)
                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                    st.success(f"'{titulo}' foi adicionado!")
                    st.session_state.config = verificar_conquistas(st.session_state.backlog_df, st.session_state.config, item_id=novo_item['ID'])
                    
                    if 'resultados_busca' in st.session_state:
                        del st.session_state.resultados_busca
                    if 'busca_titulo' in st.session_state:
                        del st.session_state.busca_titulo

                    st.rerun()

    elif add_mode == "Série / Volumes":
        with st.form("add_series_form"):
            st.subheader("Adicionar Série / Volumes")
            nome_base = st.text_input("Nome da Série (ex: Vagabond)")
            total_edicoes = st.number_input("Número Total de Itens", min_value=1, value=1)
            edicoes_possuidas = st.number_input("Quantos itens você já possui?", min_value=0, value=0)
            tipo_serie = st.selectbox("Tipo", ["Mangá", "Livro", "Série"])
            
            if st.form_submit_button("Adicionar Série", use_container_width=True):
                if nome_base and total_edicoes > 0:
                    if st.session_state.backlog_df['Nome_Serie'].str.contains(f'^{nome_base}$', case=False, regex=True).any():
                        st.error(f"ERRO: Uma série com o nome '{nome_base}' já existe.")
                    else:
                        itens_para_adicionar = []
                        max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                        unidade_map = {"Mangá": "Edições", "Livro": "Páginas", "Série": "Episódios"}

                        for i in range(1, total_edicoes + 1):
                            titulo_item = f"{nome_base} #{i}"
                            item = {
                                "ID": max_id + i, "Titulo": titulo_item, "Tipo": tipo_serie, 
                                "Status": "No Backlog" if i <= edicoes_possuidas else "Desejo",
                                "Nome_Serie": nome_base, "Ordem_Serie": i, "Total_Serie": total_edicoes,
                                "Duracao": 1 if tipo_serie == "Mangá" else 0, 
                                "Unidade_Duracao": unidade_map.get(tipo_serie, 'unidades'),
                                "Data_Adicao": datetime.now().strftime("%Y-%m-%d"), "Meu_Hype": 0,
                                "Plataforma": "", "Autor": "", "Genero": "", "Nota_Externa": 0,
                                "Progresso_Atual": 0, "Progresso_Total": 0, "Minha_Nota": 0,
                                "Cover_URL": "", "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": "Grátis"
                            }
                            itens_para_adicionar.append(item)
                        
                        df_lote = pd.DataFrame(itens_para_adicionar)
                        st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, df_lote], ignore_index=True)
                        salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                        st.success(f"{total_edicoes} itens de '{nome_base}' adicionados!")
                        st.rerun()

    # --- SEÇÃO "EM LOTE" COMPLETAMENTE ATUALIZADA ---
    elif add_mode == "Em Lote (Busca Inteligente)":
        st.subheader("Adicionar Itens em Lote (com busca online)")
        st.info("Selecione o tipo de mídia, cole uma lista de títulos (um por linha) e o SIB buscará os dados de cada um.")
        
        # 1. Seletor de tipo de mídia
        tipo_lote = st.selectbox("Qual tipo de mídia você está adicionando?", ["Jogo", "Filme", "Série", "Livro", "Anime"])

        titulos_lote = st.text_area(f"Cole a lista de títulos de '{tipo_lote}' aqui:", height=250)
        
        if st.button("Processar e Adicionar em Lote", use_container_width=True, type="primary"):
            if titulos_lote:
                lista_titulos = [titulo.strip() for titulo in titulos_lote.split('\n') if titulo.strip()]
                
                titulos_existentes = st.session_state.backlog_df['Titulo'].str.lower().tolist()
                titulos_novos = [t for t in lista_titulos if t.lower() not in titulos_existentes]
                titulos_duplicados = [t for t in lista_titulos if t.lower() in titulos_existentes]

                if titulos_duplicados:
                    st.warning(f"Itens já existentes e ignorados: {', '.join(titulos_duplicados)}")

                if not titulos_novos:
                    st.error("Nenhum título novo para adicionar.")
                    return

                itens_para_adicionar = []
                falha = []
                max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                
                progress_bar = st.progress(0, text="Buscando dados...")
                
                for i, titulo in enumerate(titulos_novos):
                    progress_bar.progress((i + 1) / len(titulos_novos), text=f"Buscando: {titulo}")
                    
                    # 2. Usa a função de busca geral
                    resultados = buscar_dados_online_geral(titulo, tipo_lote, st.session_state.config.get('api_keys', {}))
                    
                    if resultados:
                        dados = resultados[0]
                        max_id += 1
                        unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios"}
                        
                        # 3. Lógica de criação de item generalizada
                        item = {
                            "ID": max_id,
                            "Titulo": dados.get('titulo', titulo),
                            "Tipo": tipo_lote,
                            "Plataforma": dados.get('plataforma', ''),
                            "Autor": dados.get('autor', ''),
                            "Genero": ", ".join(dados.get('generos', [])),
                            "Status": "No Backlog",
                            "Meu_Hype": 0,
                            "Nota_Externa": int(dados.get('nota_externa', 0)),
                            "Duracao": float(dados.get('duracao', 0)),
                            "Unidade_Duracao": unidade_map.get(tipo_lote, 'unidades'),
                            "Nome_Serie": "", "Ordem_Serie": 1, "Total_Serie": 1,
                            "Data_Adicao": datetime.now().strftime("%Y-%m-%d"),
                            "Progresso_Atual": 0, "Progresso_Total": 1, "Minha_Nota": 0,
                            "Cover_URL": dados.get('cover_url', ''),
                            "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": "Grátis"
                        }
                        itens_para_adicionar.append(item)
                    else:
                        falha.append(titulo)
                
                progress_bar.empty()
                
                if itens_para_adicionar:
                    df_lote = pd.DataFrame(itens_para_adicionar)
                    st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, df_lote], ignore_index=True)
                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                
                sucesso = len(itens_para_adicionar)
                st.success(f"Operação Concluída! {sucesso} item(ns) do tipo '{tipo_lote}' adicionado(s).")
                if falha:
                    st.warning(f"Títulos não encontrados: {', '.join(falha)}")
                st.balloons()
                time.sleep(2)
                st.rerun()







ui_aba_adicionar_itens()