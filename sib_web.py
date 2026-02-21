import streamlit as st
import pandas as pd
import numpy as np
import json
import uuid
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

from db_connection import get_supabase_client, carregar_dados_db, salvar_item_db, deletar_item_db
from ranking_logic import calcular_ranking

# Configuração da página
st.set_page_config(page_title="SIB - Sistema Inteligente de Backlog", layout="wide")

# --- ESTILIZAÇÃO ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE APOIO ---

def get_user_config(user_id):
    return {
        "pesos": {
            "Meu_Hype": 0.25, "Nota_Externa": 0.15, "Fator_Continuidade": 0.15, 
            "Duracao": 0.10, "Progresso": 0.15, "Antiguidade": 0.10, 
            "Afinidade_Genero": 0.10 
        },
        "pontos_liberacao": 0,
        "conversores_pl": {"Horas": 10, "Páginas": 100, "Episódios": 12, "Minutos": 180, "Edições": 1}
    }

def desbloquear_conquista(user_id, chave_conquista, conquistas_db):
    """Marca uma conquista como desbloqueada."""
    try:
        supabase = get_supabase_client()
        data_agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conquista_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "chave": chave_conquista,
            "desbloqueada": True,
            "data_desbloqueio": data_agora
        }
        
        salvar_item_db("conquistas", conquista_data)
        st.toast(f"🏆 Conquista desbloqueada: {chave_conquista}!")
        return True
    except Exception as e:
        st.warning(f"Erro ao desbloquear conquista: {e}")
        return False

def verificar_conquistas(user_id, backlog_df, sessoes_df):
    """Verifica e desbloqueia conquistas baseado no progresso."""
    conquistas_db = carregar_dados_db(user_id, "conquistas")
    
    if backlog_df.empty:
        return
    
    # Conquista: Primeiro Item Finalizado
    finalizados = backlog_df[backlog_df['Status'] == 'Finalizado']
    if len(finalizados) > 0 and not any(conquistas_db.get('chave') == 'primeiro_item_finalizado'):
        desbloquear_conquista(user_id, "primeiro_item_finalizado", conquistas_db)
    
    # Conquista: Colecionador (50 itens)
    if len(backlog_df) >= 50 and not any(conquistas_db.get('chave') == 'colecionador'):
        desbloquear_conquista(user_id, "colecionador", conquistas_db)
    
    # Conquista: Maratonista (3 itens da mesma série)
    if not backlog_df.empty:
        series_counts = backlog_df[backlog_df['Nome_Serie'].notna()]['Nome_Serie'].value_counts()
        if (series_counts >= 3).any() and not any(conquistas_db.get('chave') == 'maratonista'):
            desbloquear_conquista(user_id, "maratonista", conquistas_db)

# --- SISTEMA DE AUTENTICAÇÃO ---

def auth_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🚀 SIB")
        st.subheader("Sistema Inteligente de Backlog")
        st.divider()
    
    tab1, tab2 = st.tabs(["Entrar", "Criar Conta"])
    supabase = get_supabase_client()
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar", use_container_width=True)
            if submit:
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.success("Login realizado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao entrar: Verifique email e senha.")
                    
    with tab2:
        st.info("O SIB é gratuito. Crie sua conta para começar a organizar seu backlog.")
        with st.form("signup_form"):
            new_email = st.text_input("Seu melhor email")
            new_password = st.text_input("Escolha uma senha forte", type="password")
            confirm_password = st.text_input("Confirme a senha", type="password")
            signup_submit = st.form_submit_button("Criar minha conta gratuita", use_container_width=True)
            if signup_submit:
                if new_password != confirm_password:
                    st.error("As senhas não coincidem.")
                elif len(new_password) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                else:
                    try:
                        res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                        st.success("Conta criada! Verifique seu email para confirmar.")
                    except Exception as e:
                        st.error(f"Erro ao criar conta: {e}")

# --- APLICAÇÃO PRINCIPAL ---

def main_app():
    user = st.session_state.user
    config = get_user_config(user.id)
    
    # Carregar dados
    backlog_df = carregar_dados_db(user.id, "backlog_items")
    sessoes_df = carregar_dados_db(user.id, "sessoes")
    
    # Sidebar
    with st.sidebar:
        st.title("🎮 SIB Menu")
        st.write(f"Olá, **{user.email.split('@')[0]}**")
        st.metric("Meus PLs", config["pontos_liberacao"])
        
        if st.button("Sair", use_container_width=True):
            get_supabase_client().auth.sign_out()
            del st.session_state.user
            st.rerun()
    
    # Abas principais
    tabs = st.tabs(["📊 Dashboard", "📋 Meu Backlog", "🏆 Ranking", "🎯 Sessões", "🏆 Conquistas", "🗓️ Review Anual", "⚙️ Configurações"])
    
    # --- ABA 1: DASHBOARD ---
    with tabs[0]:
        st.header("📊 Seu Progresso")
        
        if backlog_df.empty:
            st.info("Seu backlog está vazio. Adicione itens para ver as estatísticas.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            total = len(backlog_df)
            finalizados = len(backlog_df[backlog_df['Status'] == 'Finalizado'])
            em_andamento = len(backlog_df[backlog_df['Status'] == 'Em Andamento'])
            taxa = (finalizados / total * 100) if total > 0 else 0
            
            col1.metric("Total no Backlog", total)
            col2.metric("Itens Finalizados", finalizados)
            col3.metric("Em Andamento", em_andamento)
            col4.metric("Taxa de Conclusão", f"{taxa:.1f}%")
            
            st.divider()
            
            # Gráficos
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Distribuição por Tipo")
                tipo_counts = backlog_df['Tipo'].value_counts()
                fig = px.pie(values=tipo_counts.values, names=tipo_counts.index, title="Itens por Tipo")
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Status dos Itens")
                status_counts = backlog_df['Status'].value_counts()
                fig = px.bar(x=status_counts.index, y=status_counts.values, title="Status")
                st.plotly_chart(fig, use_container_width=True)
            
            # Gêneros mais comuns
            st.subheader("Gêneros Favoritos")
            generos_list = []
            for generos_str in backlog_df['Genero'].dropna():
                generos_list.extend([g.strip() for g in str(generos_str).split(',')])
            
            if generos_list:
                generos_df = pd.Series(generos_list).value_counts().head(10)
                fig = px.bar(x=generos_df.index, y=generos_df.values, title="Top 10 Gêneros")
                st.plotly_chart(fig, use_container_width=True)
    
    # --- ABA 2: MEU BACKLOG ---
    with tabs[1]:
        st.header("📋 Gerenciar Backlog")
        
        with st.expander("➕ Adicionar Novo Item", expanded=False):
            with st.form("add_item_form"):
                col1, col2 = st.columns(2)
                titulo = col1.text_input("Título do Item *")
                tipo = col2.selectbox("Tipo *", ["Jogo", "Filme", "Série", "Livro", "Anime", "Mangá"])
                
                col3, col4, col5 = st.columns(3)
                plataforma = col3.text_input("Plataforma / Onde consumir")
                hype = col4.slider("Seu Hype (0-10)", 0, 10, 5)
                status = col5.selectbox("Status Inicial", ["No Backlog", "Em Andamento", "Desejo"])
                
                col6, col7 = st.columns(2)
                duracao = col6.number_input("Duração Estimada", min_value=0, value=0)
                nota_externa = col7.number_input("Nota Externa (0-100)", min_value=0, max_value=100, value=0)
                
                autor = st.text_input("Autor / Desenvolvedora")
                genero = st.text_input("Gênero(s) (separados por vírgula)")
                
                if st.form_submit_button("Salvar no Backlog", use_container_width=True):
                    if titulo:
                        novo_item = {
                            "id": str(uuid.uuid4()),
                            "user_id": user.id,
                            "Titulo": titulo,
                            "Tipo": tipo,
                            "Plataforma": plataforma,
                            "Autor": autor,
                            "Genero": genero,
                            "Status": status,
                            "Meu_Hype": hype,
                            "Nota_Externa": nota_externa,
                            "Duracao": duracao,
                            "Data_Adicao": datetime.now().strftime("%Y-%m-%d"),
                            "Progresso_Atual": 0,
                            "Progresso_Total": 100,
                            "Minha_Nota": 0,
                            "Data_Finalizacao": None,
                            "Nome_Serie": "",
                            "Ordem_Serie": 0,
                            "Total_Serie": 0
                        }
                        salvar_item_db("backlog_items", novo_item)
                        st.success(f"'{titulo}' adicionado com sucesso!")
                        st.rerun()
                    else:
                        st.error("O título é obrigatório.")
        
        st.divider()
        
        if not backlog_df.empty:
            # Filtros
            col1, col2, col3 = st.columns(3)
            tipo_filtro = col1.selectbox("Filtrar por Tipo", ["Todos"] + sorted(backlog_df['Tipo'].unique().tolist()))
            status_filtro = col2.selectbox("Filtrar por Status", ["Todos"] + sorted(backlog_df['Status'].unique().tolist()))
            busca = col3.text_input("🔍 Pesquisar por Título")
            
            df_filtrado = backlog_df.copy()
            if tipo_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado['Tipo'] == tipo_filtro]
            if status_filtro != "Todos":
                df_filtrado = df_filtrado[df_filtrado['Status'] == status_filtro]
            if busca:
                df_filtrado = df_filtrado[df_filtrado['Titulo'].str.contains(busca, case=False, na=False)]
            
            if not df_filtrado.empty:
                st.dataframe(
                    df_filtrado[['Titulo', 'Tipo', 'Plataforma', 'Status', 'Meu_Hype', 'Minha_Nota']]
                    .sort_values(by='Titulo'),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Nenhum item corresponde aos filtros.")
        else:
            st.info("Seu backlog está vazio. Adicione itens para começar!")
    
    # --- ABA 3: RANKING ---
    with tabs[2]:
        st.header("🏆 Ranking Inteligente")
        
        if backlog_df.empty:
            st.info("Adicione itens ao seu backlog para ver o ranking inteligente.")
        else:
            st.subheader("Ative os fatores que deseja considerar:")
            cols = st.columns(5)
            fatores = {}
            fatores["Meu_Hype"] = cols[0].checkbox("Hype", value=True)
            fatores["Nota_Externa"] = cols[1].checkbox("Nota Crítica", value=True)
            fatores["Progresso"] = cols[2].checkbox("Progresso", value=True)
            fatores["Antiguidade"] = cols[3].checkbox("Tempo de Espera", value=True)
            fatores["Duracao"] = cols[4].checkbox("Duração", value=True)
            
            df_aberto = backlog_df[backlog_df['Status'] != 'Finalizado'].copy()
            
            if not df_aberto.empty:
                df_ranqueado = calcular_ranking(df_aberto, config, fatores)
                
                st.dataframe(
                    df_ranqueado[['Titulo', 'Tipo', 'Plataforma', 'Meu_Hype', 'Pontuacao_Final']]
                    .rename(columns={'Pontuacao_Final': 'Pontuação', 'Meu_Hype': 'Hype'})
                    .head(20),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("🎉 Tudo finalizado! Adicione novos itens para ver o ranking.")
    
    # --- ABA 4: SESSÕES ---
    with tabs[3]:
        st.header("🎯 Sessões de Atividade")
        
        st.subheader("Registrar Nova Sessão")
        
        itens_ativos = backlog_df[backlog_df['Status'].isin(['Em Andamento', 'No Backlog'])].copy()
        
        if itens_ativos.empty:
            st.info("Você não tem itens 'Em Andamento' ou 'No Backlog' para registrar uma sessão.")
        else:
            with st.form("sessao_form"):
                item_titulo = st.selectbox("Selecione o item", options=itens_ativos['Titulo'].unique().tolist())
                
                item_selecionado = itens_ativos[itens_ativos['Titulo'] == item_titulo].iloc[0]
                tipo_item = item_selecionado['Tipo']
                
                duracao_sessao = 0
                progresso_ganho = 0
                
                if tipo_item == "Jogo":
                    col1, col2 = st.columns(2)
                    duracao_sessao = col1.number_input("Duração (minutos)", min_value=0)
                    progresso_ganho = col2.number_input("Progresso (horas)", min_value=0)
                
                elif tipo_item == "Livro":
                    progresso_ganho = st.number_input("Páginas Lidas", min_value=0)
                    duracao_sessao = progresso_ganho * 2
                
                elif tipo_item in ["Série", "Anime"]:
                    progresso_ganho = st.number_input("Episódios Assistidos", min_value=0)
                    duracao_sessao = progresso_ganho * 45
                
                elif tipo_item == "Mangá":
                    progresso_ganho = st.number_input("Capítulos Lidos", min_value=0)
                    duracao_sessao = progresso_ganho * 5
                
                notas = st.text_area("Notas da Sessão (opcional)")
                
                if st.form_submit_button("Salvar Sessão", use_container_width=True):
                    if progresso_ganho > 0 or duracao_sessao > 0:
                        nova_sessao = {
                            "id": str(uuid.uuid4()),
                            "user_id": user.id,
                            "item_id": item_selecionado['id'],
                            "data": datetime.now().strftime("%Y-%m-%d"),
                            "duracao_sessao": duracao_sessao,
                            "progresso_ganho": progresso_ganho,
                            "notas": notas
                        }
                        
                        salvar_item_db("sessoes", nova_sessao)
                        
                        # Atualizar progresso do item
                        item_atualizado = item_selecionado.copy()
                        item_atualizado['Progresso_Atual'] = float(item_atualizado.get('Progresso_Atual', 0)) + progresso_ganho
                        if item_atualizado['Status'] == 'No Backlog':
                            item_atualizado['Status'] = 'Em Andamento'
                        
                        salvar_item_db("backlog_items", item_atualizado.to_dict())
                        
                        st.success("Sessão registrada e progresso atualizado!")
                        st.rerun()
                    else:
                        st.warning("Registre algum progresso ou duração.")
        
        st.divider()
        st.subheader("Histórico de Sessões Recentes")
        
        if not sessoes_df.empty:
            sessoes_df['data'] = pd.to_datetime(sessoes_df.get('data', []), errors='coerce')
            sessoes_recentes = sessoes_df.sort_values(by='data', ascending=False).head(10)
            st.dataframe(sessoes_recentes[['data', 'duracao_sessao', 'progresso_ganho', 'notas']], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma sessão registrada ainda.")
    
    # --- ABA 5: CONQUISTAS ---
    with tabs[4]:
        st.header("🏆 Suas Conquistas")
        
        verificar_conquistas(user.id, backlog_df, sessoes_df)
        
        conquistas_db = carregar_dados_db(user.id, "conquistas")
        
        if conquistas_db.empty:
            st.info("Você ainda não desbloqueou nenhuma conquista. Continue progredindo!")
        else:
            col1, col2, col3 = st.columns(3)
            
            for idx, conquista in conquistas_db.iterrows():
                with col1 if idx % 3 == 0 else (col2 if idx % 3 == 1 else col3):
                    with st.container(border=True):
                        st.write(f"🏆 **{conquista.get('chave', 'Conquista')}**")
                        st.caption(f"Desbloqueada em: {conquista.get('data_desbloqueio', 'Data não registrada')}")
    
    # --- ABA 6: REVIEW ANUAL ---
    with tabs[5]:
        st.header("🗓️ Meu Ano em Review")
        
        df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
        
        if df_finalizados.empty:
            st.info("Nenhum item finalizado com data registrada. Finalize itens para gerar relatórios.")
        else:
            df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados.get('Data_Finalizacao', []), errors='coerce')
            anos = sorted(df_finalizados['Data_Finalizacao'].dt.year.dropna().unique().astype(int), reverse=True)
            
            ano_selecionado = st.selectbox("Selecione o ano", anos)
            df_ano = df_finalizados[df_finalizados['Data_Finalizacao'].dt.year == ano_selecionado].copy()
            
            if not df_ano.empty:
                st.subheader(f"Seu resumo de entretenimento em {ano_selecionado}")
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Itens Finalizados", len(df_ano))
                col2.metric("Nota Média", f"{df_ano['Minha_Nota'].mean():.2f}" if df_ano['Minha_Nota'].mean() > 0 else "N/A")
                col3.metric("Tipo Favorito", df_ano['Tipo'].mode()[0] if not df_ano['Tipo'].mode().empty else "N/A")
                col4.metric("Gênero Favorito", "Vários" if not df_ano.empty else "N/A")
                
                st.divider()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Finalizações por Tipo")
                    tipo_counts = df_ano['Tipo'].value_counts()
                    fig = px.bar(x=tipo_counts.index, y=tipo_counts.values)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.subheader("Finalizações por Mês")
                    df_ano['mes'] = df_ano['Data_Finalizacao'].dt.month
                    mes_counts = df_ano['mes'].value_counts().sort_index()
                    fig = px.bar(x=mes_counts.index, y=mes_counts.values)
                    st.plotly_chart(fig, use_container_width=True)
    
    # --- ABA 7: CONFIGURAÇÕES ---
    with tabs[6]:
        st.header("⚙️ Configurações")
        
        st.subheader("Ajustar Pesos do Ranking")
        st.info("Aqui você pode ajustar a importância de cada fator no seu ranking inteligente.")
        
        col1, col2, col3 = st.columns(3)
        col1.slider("Hype", 0.0, 1.0, config["pesos"]["Meu_Hype"])
        col2.slider("Nota Crítica", 0.0, 1.0, config["pesos"]["Nota_Externa"])
        col3.slider("Duração", 0.0, 1.0, config["pesos"]["Duracao"])
        
        st.divider()
        st.subheader("Sobre o SIB")
        st.write("**SIB v1.0** - Sistema Inteligente de Backlog")
        st.write("Transforme seu backlog em uma ferramenta inteligente de decisão.")

# --- INICIALIZAÇÃO ---

if 'user' not in st.session_state:
    auth_page()
else:
    main_app()
