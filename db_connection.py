import streamlit as st
from supabase import create_client, Client
import pandas as pd
import json
from datetime import datetime

# ==============================================================================
# OTIMIZAÇÃO 1: CACHE NA CONEXÃO DO SUPABASE
# ==============================================================================
# Com @st.cache_resource, a conexão é criada apenas uma vez por sessão.
# Isso evita dezenas de conexões desnecessárias e melhora a performance.

@st.cache_resource
def get_supabase_client() -> Client:
    """
    Cria e cacheia uma única instância do cliente Supabase por sessão.
    O cache garante que a conexão seja reutilizada, economizando recursos.
    """
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("❌ Erro: Credenciais do Supabase não configuradas nos Secrets.")
        st.stop()
    
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================================================================
# OTIMIZAÇÃO 2: CACHE PARA CONSULTAS DE CONFIGURAÇÃO
# ==============================================================================
# Evita refazer a mesma consulta ao banco de dados múltiplas vezes.

@st.cache_data(ttl=300)  # Cache por 5 minutos
def _carregar_config_db_cached(user_id: str, config_padrao: dict):
    """
    Versão cacheada de carregar_config_db.
    O ttl=300 significa que o cache é renovado a cada 5 minutos.
    """
    supabase = get_supabase_client()
    try:
        response = supabase.table("user_configs").select("config_data").eq("user_id", user_id).execute()
        
        dados = response.data
        if dados and len(dados) > 0:
            if isinstance(dados, list):
                return dados[0].get("config_data", config_padrao)
            return dados.get("config_data", config_padrao)
        else:
            return config_padrao
    except Exception as e:
        st.warning(f"⚠️ Não conseguimos carregar as configurações. Usando padrões.")
        return config_padrao

def carregar_config_db(user_id, config_padrao):
    """
    Wrapper que chama a versão cacheada.
    """
    return _carregar_config_db_cached(user_id, config_padrao)

def salvar_config_db(user_id, config):
    """
    Salva configurações no Supabase.
    Limpa o cache para que a próxima leitura pegue os dados novos.
    """
    supabase = get_supabase_client()
    try:
        data = {"user_id": user_id, "config_data": config}
        supabase.table("user_configs").upsert(data, on_conflict="user_id").execute()
        
        # Limpa o cache para forçar a próxima leitura a buscar os dados atualizados
        st.cache_data.clear()
        st.success("✅ Configurações salvas com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao salvar configurações: {str(e)}")

# ==============================================================================
# OTIMIZAÇÃO 3: CACHE PARA CONSULTAS DE DADOS (Backlog, Sessões)
# ==============================================================================

@st.cache_data(ttl=60)  # Cache por 1 minuto
def _carregar_dados_db_cached(user_id: str, table_name: str):
    """
    Versão cacheada de carregar_dados_db.
    O ttl=60 significa que o cache é renovado a cada 1 minuto.
    """
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
        st.warning(f"⚠️ Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

def carregar_dados_db(user_id, table_name):
    """
    Wrapper que chama a versão cacheada.
    """
    return _carregar_dados_db_cached(user_id, table_name)

def salvar_dados_db(user_id, table_name, df):
    """
    Salva dados no Supabase com tratamento robusto de erros.
    Limpa o cache para que a próxima leitura pegue os dados novos.
    """
    supabase = get_supabase_client()
    try:
        if df.empty:
            st.info("ℹ️ Nenhum dado para salvar.")
            return
        
        items = df.to_dict(orient='records')
        for item in items:
            item['user_id'] = user_id
            for k, v in list(item.items()):
                # Trata valores nulos e timestamps
                if pd.isna(v):
                    item[k] = None
                elif isinstance(v, (pd.Timestamp, datetime)):
                    item[k] = v.isoformat()
                
                # Converte chaves para minúsculo para o Supabase
                if k != 'user_id':
                    new_key = k.lower()
                    item[new_key] = item.pop(k)
        
        supabase.table(table_name).upsert(items).execute()
        
        # Limpa o cache para forçar a próxima leitura a buscar os dados atualizados
        st.cache_data.clear()
        st.success(f"✅ {len(items)} item(ns) sincronizado(s) com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao salvar dados: {str(e)}")

def deletar_item_db(user_id, table_name, item_id):
    """
    Deleta um item do banco de dados.
    A segurança é garantida pelo RLS (Row Level Security) no Supabase.
    """
    supabase = get_supabase_client()
    try:
        supabase.table(table_name).delete().eq("user_id", user_id).eq("id", item_id).execute()
        
        # Limpa o cache
        st.cache_data.clear()
        st.success("✅ Item deletado com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao deletar item: {str(e)}")

# ==============================================================================
# FUNÇÃO AUXILIAR: Verificar Conexão com o Supabase
# ==============================================================================

def verificar_conexao_supabase():
    """
    Testa a conexão com o Supabase.
    Útil para diagnosticar problemas de conectividade.
    """
    try:
        supabase = get_supabase_client()
        # Tenta fazer uma consulta simples
        response = supabase.table("user_profiles").select("user_id").limit(1).execute()
        return True, "✅ Conexão com Supabase OK"
    except Exception as e:
        return False, f"❌ Erro de conexão: {str(e)}"
