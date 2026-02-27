import streamlit as st
from db_connection import get_supabase_client, carregar_config_db, carregar_dados_db, verificar_conexao_supabase
from premium_module import verificar_plano_usuario
import pandas as pd

# Configurações da Página
st.set_page_config(
    page_title="SIB - Smart Backlog System",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilo CSS Customizado para deixar o app mais "bonito" (Diretriz NotebookLM)
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stButton>button {
        border-radius: 8px;
    }
    .stTextInput>div>div>input {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# Tabela e Colunas
TABELA_BACKLOG = "backlog_items"
TABELA_SESSOES = "sessoes"
COLUNAS_ESPERADAS_BACKLOG = ["ID", "Titulo", "Tipo", "Plataforma", "Status", "Meu_Hype", "Nota_Externa", "Duracao", "Origem"]

def main():
    st.title("🚀 SIB - Smart Backlog System")
    st.subheader("Bem-vindo ao seu Centro de Comando de Entretenimento")

    # Inicialização de Estado
    if 'user' not in st.session_state:
        # Usando o formulário de login manual por enquanto, mas preparado para st-login-form
        # O st-login-form exige instalação via pip que faremos no requirements.txt
        st.info("Por favor, faça login ou crie uma conta para acessar seu backlog.")
        
        tab1, tab2 = st.tabs(["Entrar", "Cadastrar"])
        
        with tab1:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary"):
                    supabase = get_supabase_client()
                    try:
                        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                        st.session_state.user = res.user
                        st.success("Login realizado com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao entrar: {e}")
        
        with tab2:
            with st.form("signup_form"):
                email = st.text_input("Email")
                password = st.text_input("Senha", type="password")
                if st.form_submit_button("Criar Conta"):
                    supabase = get_supabase_client()
                    try:
                        res = supabase.auth.sign_up({"email": email, "password": password})
                        st.success("Conta criada! Verifique seu email para confirmar.")
                    except Exception as e:
                        st.error(f"Erro ao cadastrar: {e}")
        
        st.divider()
        st.markdown("### Por que usar o SIB?")
        c1, c2, c3 = st.columns(3)
        c1.metric("Organização", "100%", "Foco total")
        c2.metric("Ranking", "Smart", "Algoritmo único")
        c3.metric("Progresso", "Gamificado", "Conquistas")
        
    else:
        # Usuário Logado
        st.sidebar.success(f"Logado como: {st.session_state.user.email}")
        
        # Carregar Dados Globais no Session State
        if 'config' not in st.session_state:
            st.session_state.config = carregar_config_db(st.session_state.user.id, {})
        if 'backlog_df' not in st.session_state:
            st.session_state.backlog_df = carregar_dados_db(st.session_state.user.id, TABELA_BACKLOG)
        if 'plano' not in st.session_state:
            st.session_state.plano = verificar_plano_usuario(st.session_state.user.id)

        # Dashboard Inicial Rápido
        st.write(f"Olá! Você é um usuário **{st.session_state.plano}**.")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            total_itens = len(st.session_state.backlog_df) if not st.session_state.backlog_df.empty else 0
            st.metric("Total no Backlog", total_itens)
        with col2:
            st.metric("Plano Atual", st.session_state.plano)
        with col3:
            if st.button("Sair"):
                supabase = get_supabase_client()
                supabase.auth.sign_out()
                st.session_state.clear()
                st.rerun()

        st.divider()
        st.info("👈 Use o menu lateral para navegar entre as páginas do sistema.")
        
        # Dica do Dia
        st.markdown("""
        ### 💡 Dica do Dia
        Use o **Ranking Inteligente** para decidir o que jogar ou ler a seguir. 
        O algoritmo prioriza o que você realmente quer baseado no seu Hype e Investimento!
        """)

if __name__ == "__main__":
    main()
