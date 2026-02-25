import streamlit as st
from supabase import create_client, Client
import pandas as pd
import json
from datetime import datetime

# Configurações do Supabase (Secrets do Streamlit)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Erro: Credenciais do Supabase não configuradas nos Secrets.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_config_db(user_id, config_padrao):
    supabase = get_supabase_client()
    try:
        response = supabase.table("user_configs").select("config_data").eq("user_id", user_id).execute()
        
        # AJUSTE AQUI: O Supabase pode retornar os dados de formas diferentes dependendo da versão
        dados = response.data
        if dados and len(dados) > 0:
            # Se for uma lista, pegamos o primeiro item
            if isinstance(dados, list):
                return dados[0].get("config_data", config_padrao)
            # Se for um objeto direto
            return dados.get("config_data", config_padrao)
        else:
            salvar_config_db(user_id, config_padrao)
            return config_padrao
    except Exception as e:
        # Se der qualquer erro, usamos o padrão para o app não travar
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
        dados = response.data
        if dados:
            df = pd.DataFrame(dados)
            
            # Mapeamento para garantir compatibilidade com o app original (Maiúsculas)
            mapeamento = {
                'id': 'ID_BANCO',
                'original_id': 'ID',
                'titulo': 'Titulo',
                'tipo': 'Tipo',
                'plataforma': 'Plataforma',
                'autor': 'Autor',
                'genero': 'Genero',
                'status': 'Status',
                'meu_hype': 'Meu_Hype',
                'nota_externa': 'Nota_Externa',
                'duracao': 'Duracao',
                'unidade_duracao': 'Unidade_Duracao',
                'nome_serie': 'Nome_Serie',
                'ordem_serie': 'Ordem_Serie',
                'total_serie': 'Total_Serie',
                'data_adicao': 'Data_Adicao',
                'progresso_atual': 'Progresso_Atual',
                'progresso_total': 'Progresso_Total',
                'minha_nota': 'Minha_Nota',
                'cover_url': 'Cover_URL',
                'data_finalizacao': 'Data_Finalizacao',
                'tempo_final': 'Tempo_Final',
                'origem': 'Origem'
            }
            df = df.rename(columns=mapeamento)
            
            # Garante que a coluna 'ID' exista
            if 'ID' not in df.columns and 'id' in df.columns:
                df['ID'] = df['id']
                
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()

def salvar_dados_db(user_id, table_name, df):
    supabase = get_supabase_client()
    try:
        if df.empty: return
        
        items = df.to_dict(orient='records')
        for item in items:
            item['user_id'] = user_id
            for k, v in list(item.items()):
                if pd.isna(v): item[k] = None
                elif isinstance(v, (pd.Timestamp, datetime)): item[k] = v.isoformat()
                
                # Converte chaves para minúsculo para o Supabase
                if k != 'user_id':
                    new_key = k.lower()
                    item[new_key] = item.pop(k)
        
        supabase.table(table_name).upsert(items).execute()
    except Exception as e:
        st.error(f"Erro ao salvar dados: {e}")

def deletar_item_db(user_id, table_name, item_id):
    supabase = get_supabase_client()
    try:
        supabase.table(table_name).delete().eq("user_id", user_id).eq("id", item_id).execute()
    except Exception as e:
        st.error(f"Erro ao deletar item: {e}")
