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
        st.error("Erro: Credenciais do Supabase não configuradas.")
        st.stop()
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def carregar_dados_db(user_id, table_name):
    supabase = get_supabase_client()
    try:
        response = supabase.table(table_name).select("*").eq("user_id", user_id).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            
            # --- TRADUÇÃO DE COLUNAS (A MÁGICA AQUI) ---
            # Se o banco retornar 'id', 'titulo', etc (minúsculo), 
            # nós renomeamos para 'ID', 'Titulo', etc (como o seu app espera)
            mapeamento = {
                'id': 'ID_BANCO', # Reservamos o id do banco
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
            # Se a coluna 'ID' (maiúscula) não existir, mas 'id' existir, renomeamos.
            # Isso resolve o erro KeyError: 'ID'
            df = df.rename(columns=mapeamento)
            
            # Garante que a coluna 'ID' exista para o app não travar
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
            # Limpeza de NaT/NaN para JSON
            for k, v in list(item.items()):
                if pd.isna(v): item[k] = None
                elif isinstance(v, (pd.Timestamp, datetime)): item[k] = v.isoformat()
                
                # Para o Supabase aceitar o salvamento, enviamos em minúsculo
                # (O Supabase prefere assim e evita erros de aspas)
                item[k.lower()] = item.pop(k)
        
        supabase.table(table_name).upsert(items).execute()
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

# ... (Mantenha as outras funções carregar_config_db e salvar_config_db como estão)
