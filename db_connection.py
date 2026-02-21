import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Estas chaves devem ser configuradas no Streamlit Secrets ou variáveis de ambiente
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

def get_supabase_client() -> Client:
    """Retorna o cliente do Supabase inicializado."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Credenciais do Supabase não configuradas. Verifique os Secrets.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_dados_db(user_id, table_name):
    """Carrega dados de uma tabela específica para um usuário."""
    supabase = get_supabase_client()
    try:
        response = supabase.table(table_name).select("*").eq("user_id", user_id).execute()
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame()
    except Exception as e:
        st.warning(f"Aviso ao carregar {table_name}: {e}")
        return pd.DataFrame()

def salvar_item_db(table_name, item_data):
    """Insere ou atualiza um item no banco de dados."""
    supabase = get_supabase_client()
    try:
        # Se o item já tem um ID, tentamos um 'upsert' (atualizar ou inserir)
        response = supabase.table(table_name).upsert(item_data).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao salvar item em {table_name}: {e}")
        return None

def deletar_item_db(table_name, item_id, user_id):
    """Remove um item do banco de dados."""
    supabase = get_supabase_client()
    try:
        response = supabase.table(table_name).delete().eq("id", item_id).eq("user_id", user_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao deletar item de {table_name}: {e}")
        return None

def atualizar_item_db(table_name, item_id, user_id, dados_atualizacao):
    """Atualiza campos específicos de um item."""
    supabase = get_supabase_client()
    try:
        response = supabase.table(table_name).update(dados_atualizacao).eq("id", item_id).eq("user_id", user_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao atualizar item em {table_name}: {e}")
        return None
