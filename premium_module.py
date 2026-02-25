import streamlit as st
from db_connection import get_supabase_client
import pandas as pd

def verificar_plano_usuario(user_id):
    """
    Verifica qual plano o usuário tem (Gratuito ou Premium).
    Retorna: 'Gratuito' ou 'Premium'
    """
    supabase = get_supabase_client()
    try:
        response = supabase.table("user_profiles").select("plano").eq("user_id", user_id).execute()
        if response.data:
            return response.data[0].get("plano", "Gratuito")
        else:
            # Se não existe, cria o perfil com plano Gratuito
            criar_perfil_usuario(user_id)
            return "Gratuito"
    except Exception as e:
        return "Gratuito"

def criar_perfil_usuario(user_id):
    """
    Cria um novo perfil de usuário com plano Gratuito padrão.
    """
    supabase = get_supabase_client()
    try:
        data = {
            "user_id": user_id,
            "plano": "Gratuito",
            "data_criacao": pd.Timestamp.now().isoformat(),
            "data_upgrade": None
        }
        supabase.table("user_profiles").upsert(data).execute()
    except Exception as e:
        pass

def bloquear_recurso_premium(recurso_nome):
    """
    Exibe um aviso se o usuário não tem acesso a um recurso Premium.
    Retorna True se o usuário pode acessar, False caso contrário.
    """
    user_id = st.session_state.user.id
    plano = verificar_plano_usuario(user_id)
    
    if plano == "Premium":
        return True
    else:
        st.warning(
            f"🔒 **{recurso_nome}** é um recurso exclusivo do plano Premium!\n\n"
            f"Assine o plano Premium para desbloquear essa funcionalidade e aproveitar ao máximo o SIB.",
            icon="⭐"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Assinar Premium", type="primary", use_container_width=True):
                st.info("🚀 Funcionalidade de pagamento em desenvolvimento! Em breve você poderá assinar Premium.")
        with col2:
            if st.button("Saber Mais", use_container_width=True):
                mostrar_planos()
        
        return False

def mostrar_planos():
    """
    Exibe uma comparação entre os planos Gratuito e Premium.
    """
    st.subheader("📊 Comparação de Planos")
    
    planos_data = {
        "Recurso": [
            "Adicionar Itens",
            "Ranking Inteligente",
            "Dashboard",
            "Busca Automática (IGDB/HLTB)",
            "Conquistas",
            "Metas e Desafios",
            "Backup & Restauro",
            "Suporte Prioritário"
        ],
        "Gratuito": [
            "✅",
            "✅",
            "✅",
            "❌",
            "✅",
            "✅",
            "✅",
            "❌"
        ],
        "Premium": [
            "✅",
            "✅",
            "✅",
            "✅",
            "✅",
            "✅",
            "✅",
            "✅"
        ]
    }
    
    df_planos = pd.DataFrame(planos_data)
    st.dataframe(df_planos, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    st.markdown("**Premium:** R$ 9,90/mês ou R$ 99,90/ano (economize 16%!)")

def simular_upgrade_premium():
    """
    Função para TESTE: Simula um upgrade para Premium.
    Isso é apenas para você testar a funcionalidade.
    """
    user_id = st.session_state.user.id
    supabase = get_supabase_client()
    try:
        data = {
            "user_id": user_id,
            "plano": "Premium",
            "data_upgrade": pd.Timestamp.now().isoformat()
        }
        supabase.table("user_profiles").upsert(data).execute()
        st.success("✅ Você foi promovido para Premium (TESTE)!")
        st.rerun()
    except Exception as e:
        st.error(f"Erro ao fazer upgrade: {e}")
