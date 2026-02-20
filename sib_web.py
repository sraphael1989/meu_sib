import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import uuid
from datetime import datetime
from db_connection import get_supabase_client, carregar_dados_db, salvar_item_db
from ranking_logic import calcular_ranking

# Configuração da página
st.set_page_config(page_title="SIB - Sistema Inteligente de Backlog", layout="wide")

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 5px; height: 3em; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE APOIO ---

def get_user_config(user_id):
    return {
        "pesos": {
            "Meu_Hype": 0.25, "Nota_Externa": 0.15, "Fator_Continuidade": 0.15, 
            "Duracao": 0.10, "Progresso": 0.15, "Antiguidade": 0.10, 
            "Afinidade_Genero": 0.10 
        }
    }

# --- SISTEMA DE AUTENTICAÇÃO ---

def auth_page():
    st.title("🚀 SIB")
    st.subheader("Sistema Inteligente de Backlog")
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
    supabase = get_supabase_client()
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")
            if submit:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao entrar: {e}")
                    
    with tab2:
        with st.form("signup_form"):
            new_email = st.text_input("Seu melhor email")
            new_password = st.text_input("Escolha uma senha forte", type="password")
            signup_submit = st.form_submit_button("Criar minha conta gratuita")
            if signup_submit:
                try:
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    st.success("Conta criada! Verifique seu email para confirmar.")
                except Exception as e:
                    st.error(f"Erro ao criar conta: {e}")

# --- APLICAÇÃO PRINCIPAL ---

def main_app():
    user = st.session_state.user
    config = get_user_config(user.id)
    backlog_df = carregar_dados_db(user.id, "backlog_items")
    
    with st.sidebar:
        st.title("🎮 SIB Menu")
        st.write(f"Olá, **{user.email.split('@')[0]}**")
        st.metric("Meus PLs", 0)
        if st.button("Sair"):
            get_supabase_client().auth.sign_out()
            del st.session_state.user
            st.rerun()
            
    tabs = st.tabs(["📊 Dashboard", "📋 Meu Backlog", "🏆 Ranking", "⚙️ Configurações"])
    
    with tabs[0]:
        st.header("Seu Progresso")
        col1, col2, col3 = st.columns(3)
        total = len(backlog_df)
        finalizados = len(backlog_df[backlog_df['Status'] == 'Finalizado']) if not backlog_df.empty else 0
        taxa = (finalizados / total * 100) if total > 0 else 0
        col1.metric("Total no Backlog", total)
        col2.metric("Itens Finalizados", finalizados)
        col3.metric("Taxa de Conclusão", f"{taxa:.1f}%")

    with tabs[1]:
        st.header("Gerenciar Backlog")
        
        with st.expander("➕ Adicionar Novo Item", expanded=False):
            with st.form("add_item_manual"):
                col1, col2 = st.columns(2)
                titulo = col1.text_input("Título do Item")
                tipo = col2.selectbox("Tipo", ["Jogo", "Filme", "Série", "Livro", "Anime", "Mangá"])
                
                col3, col4, col5 = st.columns(3)
                plataforma = col3.text_input("Plataforma / Onde consumir")
                hype = col4.slider("Seu Hype (0-10)", 0, 10, 5)
                status = col5.selectbox("Status Inicial", ["No Backlog", "Em Andamento", "Desejo"])
                
                if st.form_submit_button("Salvar no Backlog"):
                    if titulo:
                        novo_item = {
                            "id": str(uuid.uuid4()),
                            "user_id": user.id,
                            "Titulo": titulo,
                            "Tipo": tipo,
                            "Plataforma": plataforma,
                            "Status": status,
                            "Meu_Hype": hype,
                            "Data_Adicao": datetime.now().strftime("%Y-%m-%d"),
                            "Progresso_Atual": 0,
                            "Progresso_Total": 100, # Valor padrão
                            "Nota_Externa": 0
                        }
                        salvar_item_db("backlog_items", novo_item)
                        st.success(f"'{titulo}' adicionado com sucesso!")
                        st.rerun()
                    else:
                        st.error("O título é obrigatório.")
        
        if not backlog_df.empty:
            st.dataframe(
                backlog_df[['Titulo', 'Tipo', 'Plataforma', 'Status', 'Meu_Hype']]
                .sort_values(by='Titulo'),
                use_container_width=True
            )
        else:
            st.info("Seu backlog está vazio. Adicione itens para começar!")

    with tabs[2]:
        st.header("Ranking Inteligente")
        if not backlog_df.empty:
            fatores = {
                "Meu_Hype": st.checkbox("Hype", value=True),
                "Nota_Externa": st.checkbox("Nota Crítica", value=True),
                "Progresso": st.checkbox("Progresso Atual", value=True),
                "Antiguidade": st.checkbox("Tempo de Espera", value=True),
                "Duracao": st.checkbox("Duração", value=True)
            }
            df_aberto = backlog_df[backlog_df['Status'] != 'Finalizado']
            if not df_aberto.empty:
                df_ranqueado = calcular_ranking(df_aberto, config, fatores)
                st.dataframe(
                    df_ranqueado[['Titulo', 'Tipo', 'Plataforma', 'Pontuacao_Final']]
                    .rename(columns={'Pontuacao_Final': 'Pontuação'}),
                    use_container_width=True
                )
            else:
                st.success("Tudo finalizado! Adicione novos itens para ver o ranking.")
        else:
            st.info("Adicione itens ao seu backlog para ver o ranking inteligente.")

    with tabs[3]:
        st.header("Configurações")
        st.write("Em breve: ajuste de pesos e chaves de API.")

# --- INICIALIZAÇÃO ---

if 'user' not in st.session_state:
    auth_page()
else:
    main_app()
