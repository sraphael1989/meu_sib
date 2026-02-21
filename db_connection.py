import streamlit as st
from supabase import create_client, Client
import pandas as pd
import json

# Configurações do Supabase (Secrets do Streamlit)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Credenciais do Supabase não configuradas nos Secrets do Streamlit.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_config_db(user_id, config_padrao):
    supabase = get_supabase_client()
    try:
        response = supabase.table("user_configs").select("config_data").eq("user_id", user_id).execute()
        if response.data:
            return response.data[0]["config_data"]
        else:
            salvar_config_db(user_id, config_padrao)
            return config_padrao
    except Exception as e:
        return config_padrao

def salvar_config_db(user_id, config):
    supabase = get_supabase_client()
    try:
        data = {"user_id": user_id, "config_data": config}
        supabase.table("user_configs").upsert(data, on_conflict="user_id").execute()
    except Exception as e:
        st.error(f"Erro ao salvar configurações: {e}")

def carregar_dados_db(user_id, table_name):
    supabase = get_supabase_client()
    try:
        response = supabase.table(table_name).select("*").eq("user_id", user_id).execute()
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def salvar_dados_db(user_id, table_name, df):
    supabase = get_supabase_client()
    try:
        if df.empty:
            return
        
        items = df.to_dict(orient='records')
        for item in items:
            item['user_id'] = user_id
            # Limpeza de NaT/NaN para JSON
            for k, v in item.items():
                if pd.isna(v):
                    item[k] = None
                elif isinstance(v, (pd.Timestamp, datetime)):
                    item[k] = v.isoformat()
        
        # Upsert baseado em user_id e ID (chave composta ou ID único do item)
        # Importante: No Supabase, você deve garantir que a tabela tenha uma constraint de unicidade para (user_id, ID)
        supabase.table(table_name).upsert(items).execute()
            
    except Exception as e:
        st.error(f"Erro ao salvar dados em {table_name}: {e}")

def deletar_item_db(user_id, table_name, item_id):
    supabase = get_supabase_client()
    try:
        supabase.table(table_name).delete().eq("user_id", user_id).eq("ID", item_id).execute()
    except Exception as e:
        st.error(f"Erro ao deletar item: {e}")
