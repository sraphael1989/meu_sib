
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


def ui_aba_ranking(backlog_df, config):
    st.header("Seu Próximo Entretenimento Será...")

    st.subheader("Fatores do Ranking")
    
    # --- LÓGICA DE INICIALIZAÇÃO CORRIGIDA E ROBUSTA ---
    # Define o dicionário padrão com todas as chaves esperadas
    fatores_padrao = {
        "Meu_Hype": True, "Nota_Externa": True, "Afinidade_Genero": True,
        "Fator_Continuidade": True, "Progresso": True, "Antiguidade": True, "Duracao": True,
        "Bonus_Catchup": True
    }

    # Se o dicionário não existir na sessão, cria-o
    if 'fatores_ranking' not in st.session_state:
        st.session_state.fatores_ranking = fatores_padrao
    else:
        # Se o dicionário já existe, verifica se falta alguma chave (como a nova 'Bonus_Catchup')
        for chave, valor_padrao in fatores_padrao.items():
            if chave not in st.session_state.fatores_ranking:
                st.session_state.fatores_ranking[chave] = valor_padrao

    fatores = st.session_state.fatores_ranking
    
    cols = st.columns(8)
    fatores["Meu_Hype"] = cols[0].toggle("Hype", value=fatores["Meu_Hype"], help="Sua vontade de jogar/ler/assistir.")
    fatores["Nota_Externa"] = cols[1].toggle("Crítica", value=fatores["Nota_Externa"], help="Nota de sites como Metacritic.")
    fatores["Afinidade_Genero"] = cols[2].toggle("Afinidade", value=fatores["Afinidade_Genero"], help="Gêneros que você costuma avaliar bem.")
    fatores["Fator_Continuidade"] = cols[3].toggle("Séries", value=fatores["Fator_Continuidade"], help="Prioriza a continuação de séries já iniciadas.")
    fatores["Progresso"] = cols[4].toggle("Progresso", value=fatores["Progresso"], help="Incentiva a terminar itens já começados.")
    fatores["Antiguidade"] = cols[5].toggle("Antiguidade", value=fatores["Antiguidade"], help="Prioriza itens mais antigos no backlog.")
    fatores["Duracao"] = cols[6].toggle("Duração", value=fatores["Duracao"], help="Prioriza itens mais curtos.")
    fatores["Bonus_Catchup"] = cols[7].toggle("Catch-up", value=fatores["Bonus_Catchup"], help="Bônus para itens de uma série que você 'pulou'.")
    
    st.divider()

    df_ranqueado = calcular_ranking(backlog_df, config, st.session_state.fatores_ranking)
    
    df_filtrado = df_ranqueado.copy()
    
    if 'tipo_filtro' in st.session_state and st.session_state.tipo_filtro != "Todos": 
        df_filtrado = df_filtrado[df_filtrado['Tipo'] == st.session_state.tipo_filtro]
    if 'status_filtro' in st.session_state and st.session_state.status_filtro != "Todos": 
        df_filtrado = df_filtrado[df_filtrado['Status'] == st.session_state.status_filtro]
    
    if 'genero_filtro' in st.session_state and st.session_state.genero_filtro != "Todos":
        genero_selecionado = st.session_state.genero_filtro
        mascara_genero = df_filtrado['Genero'].str.split(',').apply(
            lambda lista_generos: genero_selecionado in [g.strip() for g in lista_generos] if isinstance(lista_generos, list) else False
        )
        df_filtrado = df_filtrado[mascara_genero]

    if 'autor_filtro' in st.session_state and st.session_state.autor_filtro != "Todos": 
        df_filtrado = df_filtrado[df_filtrado['Autor'] == st.session_state.autor_filtro]

    termo_busca = st.text_input("🔍 Pesquisar por Título", key="search_ranking")
    if termo_busca:
        df_filtrado = df_filtrado[df_filtrado['Titulo'].str.contains(termo_busca, case=False, na=False)]

    if not df_filtrado.empty:
        df_display = df_filtrado.copy()
        df_display.insert(0, 'Posição', range(1, len(df_display) + 1))

        nomes_colunas = {
            "Posição": "Pos.", "Titulo": "Título", "Tipo": "Tipo", "Plataforma": "Plataforma", 
            "Autor": "Autor / Dev.", "Genero": "Gênero(s)", "Status": "Status",
            "Pontuacao_Final": "Pontuação", "Progresso_Perc": "Progresso"
        }
        colunas_visiveis = list(nomes_colunas.keys())
        df_display = df_display[colunas_visiveis]
        
        df_display.rename(columns=nomes_colunas, inplace=True)
        
        st.dataframe(
            df_display.style
            .apply(highlight_rows, axis=1)
            .bar(subset=['Progresso'], color='#5B8D5A', vmin=0, vmax=1)
            .background_gradient(cmap='Greens', subset=['Pontuação'], vmin=0, vmax=10)
            .format({'Pontuação': '{:.2f}', 'Progresso': '{:.0%}'})
            .set_properties(**{'text-align': 'left'})
            .set_properties(subset=['Pos.', 'Pontuação'], **{'text-align': 'right'}),
            use_container_width=True, 
            hide_index=True
        )
    else:
        st.info("Nenhum item corresponde aos filtros ou à pesquisa.")

    st.divider()
    st.header("Ações Rápidas")
    top_10_desejo = df_ranqueado[(df_ranqueado['Status'] == 'Desejo') & (df_ranqueado.index < 10)]
    if not top_10_desejo.empty:
        st.subheader("Liberar Compra de Item Desejado (Top 10)")
        item_para_liberar = st.selectbox("Selecione o item", top_10_desejo['Titulo'])
        item_selecionado = top_10_desejo[top_10_desejo['Titulo'] == item_para_liberar].iloc[0]
        custo, pls_atuais = item_selecionado['Custo_PL'], st.session_state.config['pontos_liberacao']
        if custo == 0:
            st.info("Este item não tem custo em PLs (duração desconhecida).")
        elif pls_atuais >= custo:
            if st.button(f"Liberar '{item_selecionado['Titulo']}' (Custo: {custo} PLs)", type="primary"):
                st.session_state.config['pontos_liberacao'] -= custo
                idx = st.session_state.backlog_df[st.session_state.backlog_df['ID'] == item_selecionado['ID']].index
                st.session_state.backlog_df.loc[idx, 'Status'] = 'No Backlog'
                salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                salvar_config(st.session_state.config)
                st.success(f"'{item_selecionado['Titulo']}' liberado!")
                st.rerun()
        else: st.warning(f"PLs insuficientes. Você precisa de {custo}, mas tem {pls_atuais:.1f}.")
    else:
        st.info("Nenhum item da sua lista de desejos está no Top 10 do ranking.")











ui_aba_ranking()