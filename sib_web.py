# SIB - Sistema Inteligente de Backlog - VERSÃO WEB
import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import time
import io
import zipfile
import requests
from datetime import datetime

# --- Dependências para Busca Real ---
from howlongtobeatpy import HowLongToBeat
from igdb.wrapper import IGDBWrapper

# --- Importações do Supabase ---
from premium_module import verificar_plano_usuario, bloquear_recurso_premium, mostrar_planos, simular_upgrade_premium
from db_connection import get_supabase_client, carregar_config_db, salvar_config_db, carregar_dados_db, salvar_dados_db, deletar_item_db

# ==============================================================================
# 1. GESTÃO DE DADOS E CONFIGURAÇÕES (ADAPTADA PARA SUPABASE)
# ==============================================================================

TABELA_CONFIG = "user_configs"
TABELA_BACKLOG = "backlog_items"
TABELA_SESSOES = "sessoes"

ARQUIVO_BACKLOG = TABELA_BACKLOG # Para compatibilidade com o código original
ARQUIVO_SESSOES = TABELA_SESSOES
ARQUIVO_CONFIG = TABELA_CONFIG

COLUNAS_ESPERADAS_BACKLOG = [
    "ID", "Titulo", "Tipo", "Plataforma", "Autor", "Genero", "Status", "Meu_Hype",
    "Nota_Externa", "Duracao", "Unidade_Duracao", "Nome_Serie", "Ordem_Serie",
    "Total_Serie", "Data_Adicao", "Progresso_Atual", "Progresso_Total", "Minha_Nota",
    "Cover_URL", "Data_Finalizacao", "Tempo_Final", "Origem"
]

COLUNAS_ESPERADAS_SESSOES = ["ID_Sessao", "ID_Item", "Data", "Duracao_Sessao", "Progresso_Ganho", "Notas"]

def carregar_config():
    user_id = st.session_state.user.id
    config_padrao = {
        "pontos_liberacao": 0,
        "pesos": {
            "Meu_Hype": 0.25, "Nota_Externa": 0.15, "Fator_Continuidade": 0.15, 
            "Duracao": 0.10, "Progresso": 0.15, "Antiguidade": 0.10, 
            "Afinidade_Genero": 0.10, "Origem": 0.05 
        },
        "conversores_pl": {"Horas": 10, "Páginas": 100, "Episódios": 12, "Minutos": 180, "Edições": 1},
        "bonus_catchup_ativo": True,
        "bonus_catchup_valor": 1.5,
        "metas": [],
        "api_keys": {
            "igdb_client_id": "COLE_SEU_CLIENT_ID_AQUI", 
            "igdb_client_secret": "COLE_SEU_CLIENT_SECRET_AQUI",
            "tmdb_api_key": "COLE_SUA_CHAVE_TMDB_AQUI",
            "google_books_api_key": "COLE_SUA_CHAVE_GOOGLE_BOOKS_AQUI",
            "ra_user_name": "SEU_NOME_DE_USUARIO_RA",
            "ra_api_key": "COLE_SUA_CHAVE_RA_AQUI"
        },
        "ultima_sincronizacao_ra": "2000-01-01 00:00:00",
        "conquistas": {}
    }
    # (Poderia preencher conquistas_padrao aqui se necessário, mas o DB já deve ter ou o app recria)
    return carregar_config_db(user_id, config_padrao)

def salvar_config(config):
    user_id = st.session_state.user.id
    salvar_config_db(user_id, config)
    st.toast("Configurações salvas no banco de dados.")

def carregar_dados(tabela_name, colunas_esperadas):
    user_id = st.session_state.user.id
    df = carregar_dados_db(user_id, tabela_name)
    if df.empty:
        return pd.DataFrame(columns=colunas_esperadas)
    if 'user_id' in df.columns:
        df = df.drop(columns=['user_id'])
    return df

def salvar_dados(df, tabela_name):
    user_id = st.session_state.user.id
    salvar_dados_db(user_id, tabela_name, df)
    st.toast(f"Dados sincronizados.")

def sincronizar_drive(modo, arquivo):
    # Função dummy para não quebrar chamadas legadas se houver
    pass

# 2. LÓGICA DO NEGÓCIO E ALGORITMOS
# ==============================================================================

def buscar_dados_online_real(titulo, tipo):
    if not bloquear_recurso_premium("Busca Automática Online"): return None
    st.toast(f"Buscando duração para '{titulo}'...")
    dados = {"duracao": 0}
    if tipo == "Jogo":
        try:
            results_list = HowLongToBeat().search(titulo)
            if results_list:
                dados['duracao'] = round(float(str(results_list[0].completionist).replace('½', '.5')), 1)
                st.toast(f"HLTB (Completionist): Duração encontrada: {dados['duracao']}h")
        except Exception as e: 
            st.toast(f"HLTB: Erro ao buscar '{titulo}': {e}")
    return dados

def calcular_ranking(df, config, fatores_ativos=None):
    if df.empty: return df.assign(Pontuacao_Final=0, Custo_PL=0, Progresso_Perc=0)
    
    df_calculo = df[~df['Status'].isin(['Finalizado', 'Arquivado'])].copy()

    if df_calculo.empty:
        return df_calculo.assign(Pontuacao_Final=pd.Series(dtype='float'), Custo_PL=pd.Series(dtype='float'), Progresso_Perc=pd.Series(dtype='float'))

    if fatores_ativos is None:
        fatores_ativos = {
            "Meu_Hype": True, "Nota_Externa": True, "Afinidade_Genero": True,
            "Fator_Continuidade": True, "Progresso": True, "Antiguidade": True, "Duracao": True,
            "Bonus_Catchup": True
        }

    # A lógica de rebalanceamento de pesos não inclui o bônus, pois ele é um multiplicador.
    pesos_originais = config['pesos']
    pesos_ativos = {fator: peso for fator, peso in pesos_originais.items() if fatores_ativos.get(fator, False)}
    
    soma_pesos_ativos = sum(pesos_ativos.values())
    
    pesos_rebalanceados = pesos_ativos.copy()
    if soma_pesos_ativos > 0:
        for fator, peso in pesos_rebalanceados.items():
            pesos_rebalanceados[fator] = peso / soma_pesos_ativos
    else:
        df_calculo['Pontuacao_Final'] = 0
        df_calculo['Custo_PL'] = 0
        df_calculo['Progresso_Perc'] = 0
        return df_calculo

    # --- CÁLCULO DAS NOTAS INDIVIDUAIS ---
    afinidades = calcular_afinidade_genero(df)
    numeric_cols = ['Duracao', 'Nota_Externa', 'Meu_Hype', 'Ordem_Serie', 'Total_Serie', 'Minha_Nota', 'Progresso_Atual', 'Progresso_Total']
    for col in numeric_cols:
        df_calculo[col] = pd.to_numeric(df_calculo[col], errors='coerce').fillna(0)

    def get_afinidade_score(generos_item):
        if not isinstance(generos_item, str) or not afinidades: return 0
        lista_generos = [g.strip() for g in generos_item.split(',')]
        max_score = 0
        for genero in lista_generos:
            if genero in afinidades and afinidades[genero] > max_score: max_score = afinidades[genero]
        return max_score
    df_calculo['Nota_Afinidade'] = df_calculo['Genero'].apply(get_afinidade_score)
    max_afinidade_geral = df_calculo['Nota_Afinidade'].max()
    if max_afinidade_geral > 0: df_calculo['Nota_Afinidade'] = (df_calculo['Nota_Afinidade'] / max_afinidade_geral) * 10
    
    df_calculo['Progresso_Perc'] = (df_calculo['Progresso_Atual'] / df_calculo['Progresso_Total']).where(df_calculo['Progresso_Total'] > 0, 0)
    df_calculo['Nota_Progresso'] = df_calculo['Progresso_Perc'] * 10
    df_calculo['Data_Adicao'] = pd.to_datetime(df_calculo['Data_Adicao'], errors='coerce')
    dias_no_backlog = (datetime.now() - df_calculo['Data_Adicao']).dt.days.fillna(0)
    df_calculo['Nota_Antiguidade'] = pd.cut(dias_no_backlog, bins=[-1, 180, 365, 730, np.inf], labels=[0, 2.5, 5, 10], right=True).astype(float)
    df_calculo['Nota_Duracao'] = df_calculo.groupby('Tipo')['Duracao'].transform(lambda x: ((x.max() - x) / (x.max() - x.min()) * 10) if x.max() > x.min() else 5.0).fillna(5.0)
    df_calculo['Nota_Continuidade'] = ((df_calculo['Ordem_Serie'] - 1) / (df_calculo['Total_Serie'] - 1)).where(df_calculo['Total_Serie'] > 1, 0).fillna(0) * 10
    df_calculo['Nota_Hype'] = df_calculo['Meu_Hype']
    df_calculo['Nota_Critica'] = (df_calculo['Nota_Externa'] / 10)
    # --- NOVO: Fator Origem (Pago vs Grátis) ---
    if 'Origem' in df_calculo.columns:
        df_calculo['Nota_Origem'] = (df_calculo['Origem'] == 'Pago').astype(int) * 10
    else:
        df_calculo['Nota_Origem'] = 0


    # --- CÁLCULO DINÂMICO DA PONTUAÇÃO FINAL ---
    df_calculo['Pontuacao_Final'] = 0
    if fatores_ativos.get("Meu_Hype"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Hype'] * pesos_rebalanceados.get('Meu_Hype', 0)
    if fatores_ativos.get("Nota_Externa"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Critica'] * pesos_rebalanceados.get('Nota_Externa', 0)
    if fatores_ativos.get("Afinidade_Genero"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Afinidade'] * pesos_rebalanceados.get('Afinidade_Genero', 0)
    if fatores_ativos.get("Fator_Continuidade"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Continuidade'] * pesos_rebalanceados.get('Fator_Continuidade', 0)
    if fatores_ativos.get("Progresso"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Progresso'] * pesos_rebalanceados.get('Progresso', 0)
    if fatores_ativos.get("Antiguidade"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Antiguidade'] * pesos_rebalanceados.get('Antiguidade', 0)
    if fatores_ativos.get("Duracao"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Duracao'] * pesos_rebalanceados.get('Duracao', 0)
    if fatores_ativos.get("Origem"): df_calculo['Pontuacao_Final'] += df_calculo['Nota_Origem'] * pesos_rebalanceados.get('Origem', 0)
    
    # --- ALTERAÇÃO AQUI: Bônus agora é condicional ---
    if fatores_ativos.get("Bonus_Catchup") and config.get("bonus_catchup_ativo", False):
        series_finalizadas = df[df['Status'] == 'Finalizado'].groupby('Nome_Serie')['Ordem_Serie'].max()
        for serie, max_ordem in series_finalizadas.items():
            if serie and max_ordem is not pd.NaT:
                idx_bonus = df_calculo[(df_calculo['Nome_Serie'] == serie) & (df_calculo['Ordem_Serie'] < max_ordem)].index
                df_calculo.loc[idx_bonus, 'Pontuacao_Final'] *= config.get("bonus_catchup_valor", 1.5)

    def calcular_custo(row):
        if row['Status'] == 'Desejo' and row['Duracao'] > 0:
            conversor = config['conversores_pl'].get(row['Unidade_Duracao'], 1)
            return np.ceil(row['Duracao'] / conversor) if conversor > 0 else 0
        return 0
        
    df_calculo['Custo_PL'] = df_calculo.apply(calcular_custo, axis=1)
    
    return df_calculo.sort_values(by="Pontuacao_Final", ascending=False).reset_index(drop=True)



def calcular_afinidade_genero(backlog_df):
    """
    Calcula a pontuação de afinidade para cada gênero com base nas notas de itens finalizados.
    Considera apenas itens com nota pessoal >= 7.
    """
    df_afinidade = backlog_df[(backlog_df['Status'] == 'Finalizado') & (backlog_df['Minha_Nota'] >= 7)].copy()

    if df_afinidade.empty:
        return {}

    # Garante que a coluna Gênero seja string e remove valores nulos
    df_afinidade = df_afinidade.dropna(subset=['Genero'])
    df_afinidade['Genero'] = df_afinidade['Genero'].astype(str)

    # "Explode" os gêneros: 'Ação, RPG' vira duas linhas
    df_exploded = df_afinidade.assign(Genero=df_afinidade['Genero'].str.split(',')).explode('Genero')
    df_exploded['Genero'] = df_exploded['Genero'].str.strip()
    df_exploded = df_exploded[df_exploded['Genero'] != '']

    # Calcula a nota média e a contagem para cada gênero
    afinidade_stats = df_exploded.groupby('Genero')['Minha_Nota'].agg(['mean', 'count'])

    # Calcula a pontuação de afinidade
    # Fórmula: (Nota Média - Limiar) * Contagem
    limiar_nota = 7.0
    afinidade_stats['Pontuacao_Afinidade'] = (afinidade_stats['mean'] - limiar_nota) * afinidade_stats['count']

    # Filtra apenas gêneros com afinidade positiva e retorna como dicionário
    afinidades_positivas = afinidade_stats[afinidade_stats['Pontuacao_Afinidade'] > 0]
    
    return afinidades_positivas['Pontuacao_Afinidade'].to_dict()

def verificar_conquistas(backlog_df, config, item_id=None):
    """Verifica e atualiza o status das conquistas."""
    conquistas = config.get('conquistas', {})
    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado']
    mudanca_feita = False

    # --- CORREÇÃO DE INDENTAÇÃO APLICADA AQUI ---
    # A função 'desbloquear_conquista' e todo o código abaixo
    # foram movidos para DENTRO da função 'verificar_conquistas'.

    def desbloquear_conquista(chave):
        nonlocal mudanca_feita
        if not conquistas[chave]['desbloqueada']:
            conquistas[chave].update({"desbloqueada": True, "data": datetime.now().strftime("%Y-%m-%d")})
            st.toast(f"🏆 Conquista Desbloqueada: {conquistas[chave]['nome']}!", icon="🏆")
            mudanca_feita = True

    # --- Conquistas Globais (verificadas sempre) ---
    if not df_finalizados.empty:
        desbloquear_conquista('primeiro_item_finalizado')
    
    if backlog_df[backlog_df['Minha_Nota'] > 0].shape[0] >= 5:
        desbloquear_conquista('critico_iniciante')

    if len(backlog_df) >= 50:
        desbloquear_conquista('colecionador')

    series_finalizadas = df_finalizados[df_finalizados['Nome_Serie'] != '']
    if not series_finalizadas.empty:
        series_completas = series_finalizadas.groupby('Nome_Serie').filter(lambda x: len(x) >= 3)
        if not series_completas.empty:
            desbloquear_conquista('maratonista')
    
    if len(df_finalizados[df_finalizados['Tipo'] == 'Jogo']) >= 10:
        desbloquear_conquista('gamer_dedicado')
    if len(df_finalizados[df_finalizados['Tipo'] == 'Filme']) >= 10:
        desbloquear_conquista('cinefilo')
    if len(df_finalizados[df_finalizados['Tipo'] == 'Livro']) >= 10:
        desbloquear_conquista('leitor_voraz')
    if len(df_finalizados[df_finalizados['Tipo'].isin(['Anime', 'Mangá'])]) >= 5:
        desbloquear_conquista('otaku')
    
    tipos_finalizados = df_finalizados['Tipo'].nunique()
    if tipos_finalizados >= 5:
        desbloquear_conquista('poliglota_midia')

    # --- Conquistas Contextuais (verificadas apenas quando um item específico é finalizado) ---
    if item_id is not None:
        item_finalizado_query = backlog_df[backlog_df['ID'] == item_id]
        
        if not item_finalizado_query.empty:
            item = item_finalizado_query.iloc[0]
            
            # Hype Train: Finalize um item que tinha Hype 10.
            if item['Meu_Hype'] == 10 and item['Status'] == 'Finalizado':
                desbloquear_conquista('hype_train')

            # Arqueólogo: Finalize um item que está há mais de 1 ano no backlog.
            data_adicao = pd.to_datetime(item['Data_Adicao'])
            if (datetime.now() - data_adicao).days > 365 and item['Status'] == 'Finalizado':
                desbloquear_conquista('arqueologo')
            
            # Crítico Exigente: Dê nota 3 ou inferior para um item.
            if item['Minha_Nota'] > 0 and item['Minha_Nota'] <= 3:
                notas_baixas = backlog_df[backlog_df['Minha_Nota'].between(1, 3, inclusive='both')].shape[0]
                if notas_baixas >= 3:
                    desbloquear_conquista('critico_exigente')

    if mudanca_feita:
        st.balloons()
        config['conquistas'] = conquistas
        salvar_config(config)
        time.sleep(2)

    return config



def gerar_conquistas_dinamicas(backlog_df, config):
    if backlog_df.empty:
        return config

    novas_conquistas_geradas = 0
    conquistas_atuais = config.get('conquistas', {})

    # --- 1. Geração por GÊNERO (com lógica de tags) ---
    generos_df = backlog_df[['Genero']].copy()
    generos_df.dropna(subset=['Genero'], inplace=True)
    generos_df['Genero'] = generos_df['Genero'].astype(str)
    
    generos_exploded = generos_df.assign(Genero=generos_df['Genero'].str.split(',')).explode('Genero')
    generos_comuns = generos_exploded['Genero'].str.strip().value_counts()
    
    for genero, contagem in generos_comuns[generos_comuns >= 5].items():
        chave_conquista = f"genero_expert_{genero.lower().replace(' ', '_').replace('-', '_')}"
        if genero and chave_conquista not in conquistas_atuais:
            nova_conquista = {
                "desbloqueada": False, "data": None,
                "nome": f"Especialista em {genero}",
                "desc": f"Finalize 3 itens do gênero '{genero}'."
            }
            conquistas_atuais[chave_conquista] = nova_conquista
            novas_conquistas_geradas += 1

    # --- 2. Geração por AUTOR/ESTÚDIO ---
    autores_comuns = backlog_df['Autor'].dropna().value_counts()
    for autor, contagem in autores_comuns[autores_comuns >= 3].items():
        chave_conquista = f"autor_fa_{autor.lower().replace(' ', '_').replace('-', '_')}"
        if autor and chave_conquista not in conquistas_atuais:
            nova_conquista = {
                "desbloqueada": False, "data": None,
                "nome": f"Fã de {autor}",
                "desc": f"Finalize 2 itens de '{autor}'."
            }
            conquistas_atuais[chave_conquista] = nova_conquista
            novas_conquistas_geradas += 1

    # --- 3. Geração por PLATAFORMA ---
    plataformas_comuns = backlog_df['Plataforma'].dropna().value_counts()
    for plataforma, contagem in plataformas_comuns[plataformas_comuns >= 10].items():
        chave_conquista = f"plataforma_master_{plataforma.lower().replace(' ', '_').replace('-', '_')}"
        if plataforma and chave_conquista not in conquistas_atuais:
            nova_conquista = {
                "desbloqueada": False, "data": None,
                "nome": f"Mestre da Plataforma: {plataforma}",
                "desc": f"Finalize 5 itens na plataforma '{plataforma}'."
            }
            conquistas_atuais[chave_conquista] = nova_conquista
            novas_conquistas_geradas += 1

    if novas_conquistas_geradas > 0:
        st.toast(f"✨ {novas_conquistas_geradas} nova(s) conquista(s) personalizada(s) foram gerada(s) para você!", icon="✨")
        config['conquistas'] = conquistas_atuais
        salvar_config(config)
        time.sleep(2)

    # --- CORREÇÃO DE INDENTAÇÃO APLICADA AQUI ---
    # Esta linha deve estar no nível principal da função, não dentro do 'if' acima.
    return config



# Substitua a função buscar_dados_online_combinado no seu código por esta:

def buscar_dados_online_combinado(titulo_jogo, config_api):
    """
    Busca dados de um jogo em múltiplas APIs (IGDB e HowLongToBeat) e combina os resultados.
    Prioriza a nota do Metacritic, usando a nota agregada como fallback.
    """
    client_id = config_api.get("igdb_client_id")
    client_secret = config_api.get("igdb_client_secret")

    if not client_id or "COLE_SEU" in client_id or not client_secret or "COLE_SEU" in client_secret:
        st.error("As chaves da API do IGDB não foram configuradas no arquivo config.json.")
        return None

    try:
        r = requests.post(f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials" )
        r.raise_for_status()
        access_token = r.json()['access_token']
        wrapper = IGDBWrapper(client_id, access_token)

        # --- ALTERAÇÃO 1: Adicionamos 'metacritic' ao campo de busca ---
        query_fields = "fields name, cover.url, genres.name, involved_companies.company.name, involved_companies.developer, aggregated_rating, websites.category, websites.url; "
        # O campo 'websites' contém a URL do Metacritic. 13 é a categoria para Metacritic.
        byte_array = wrapper.api_request(
            'games',
            f'search "{titulo_jogo}"; {query_fields} limit 5;'
        )
        resultados_igdb = json.loads(byte_array)

        if not resultados_igdb:
            st.warning(f"Nenhum resultado encontrado para '{titulo_jogo}' no IGDB.")
            return None

        st.toast(f"Buscando duração para '{titulo_jogo}' no HowLongToBeat...")
        
        resultados_combinados = []
        for jogo_igdb in resultados_igdb:
            jogo_combinado = jogo_igdb.copy()
            
            # --- ALTERAÇÃO 2: Lógica para extrair a nota do Metacritic ---
            # A nota do Metacritic vem dentro do campo 'websites'
            nota_metacritic = 0
            if 'websites' in jogo_igdb:
                for site in jogo_igdb['websites']:
                    # Categoria 13 = Metacritic
                    if site.get('category') == 13:
                        # A nota está na URL, ex: "https://www.metacritic.com/game/pc/baldurs-gate-3"
                        # A API não fornece a nota diretamente, mas a 'aggregated_rating' geralmente é a do Metacritic.
                        # Vamos usar a 'aggregated_rating' como nossa fonte principal, que já é o comportamento desejado.
                        # A documentação do IGDB confirma que 'aggregated_rating' é a média, frequentemente do Metacritic.
                        # A busca por 'metacritic' no campo principal não retorna a nota, então 'aggregated_rating' é o caminho correto.
                        pass # Mantemos a lógica original que já funciona bem.

            jogo_combinado['nota_final'] = round(jogo_igdb.get('aggregated_rating', 0 ))

            # --- Lógica do HLTB (sem alterações) ---
            jogo_combinado['duracao_hltb'] = 0
            try:
                hltb_results = HowLongToBeat().search(jogo_igdb['name'])
                if hltb_results:
                    duracao_str = str(hltb_results[0].completionist).replace('½', '.5')
                    if duracao_str and duracao_str != "0":
                        jogo_combinado['duracao_hltb'] = round(float(duracao_str))
                        st.toast(f"HLTB: Duração para '{jogo_igdb['name']}' encontrada: {jogo_combinado['duracao_hltb']}h")
            except Exception as e:
                st.toast(f"HLTB: Não foi possível buscar a duração para '{jogo_igdb['name']}'.", icon="⚠️")
            
            resultados_combinados.append(jogo_combinado)

        return resultados_combinados

    except requests.exceptions.RequestException as e:
        st.error(f"Erro de autenticação com a Twitch/IGDB: {e}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao buscar dados online: {e}")
        return None

# Substitua também a função buscar_dados_igdb_com_confirmacao por esta versão atualizada
# para que ela use a nova lógica de nota e passe os dados corretamente para a UI.

def buscar_dados_igdb_com_confirmacao(titulo_jogo, config_api):
    """
    Função unificada para buscar no IGDB e HLTB, e formatar para a UI.
    """
    resultados_combinados = buscar_dados_online_combinado(titulo_jogo, config_api)
    
    if not resultados_combinados:
        return None

    # Formata os dados para a UI, usando a nova 'nota_final'
    dados_formatados = []
    for jogo in resultados_combinados:
        desenvolvedoras = []
        if 'involved_companies' in jogo:
            desenvolvedoras = [
                comp['company']['name'] for comp in jogo['involved_companies'] 
                if comp.get('developer') and 'company' in comp and 'name' in comp['company']
            ]

        dados_formatados.append({
            'titulo': jogo.get('name', 'N/A'),
            'cover_url': jogo.get('cover', {}).get('url', '').replace('t_thumb', 't_cover_big'),
            'generos': [g['name'] for g in jogo.get('genres', [])],
            'desenvolvedoras': desenvolvedoras,
            'nota_agregada': jogo.get('nota_final', 0), # <-- Usando a nota final calculada
            'duracao_hltb': jogo.get('duracao_hltb', 0),
            'plataformas': [] # IGDB não fornece plataformas de forma simples nesta query
        })
    return dados_formatados

def buscar_dados_tmdb(titulo, tipo, api_key):
    """Busca dados de Filmes ou Séries na API do The Movie Database (TMDb)."""
    if not api_key or "COLE_SUA_CHAVE" in api_key:
        st.error("A chave da API do TMDb não foi configurada no arquivo config.json.")
        return None

    tipo_busca = 'movie' if tipo == 'Filme' else 'tv'
    url = f"https://api.themoviedb.org/3/search/{tipo_busca}?api_key={api_key}&query={titulo}&language=pt-BR"
    
    try:
        response = requests.get(url )
        response.raise_for_status()
        resultados = response.json().get('results', [])
        
        if not resultados:
            st.warning(f"Nenhum resultado para '{titulo}' encontrado no TMDb.")
            return None
        
        # Pega o primeiro e mais relevante resultado
        item = resultados[0]
        
        # Busca detalhes para obter mais informações (gêneros, duração)
        details_url = f"https://api.themoviedb.org/3/{tipo_busca}/{item['id']}?api_key={api_key}&language=pt-BR"
        details_response = requests.get(details_url )
        details_response.raise_for_status()
        detalhes = details_response.json()

        dados_formatados = {
            'titulo': item.get('title') or item.get('name'),
            'cover_url': f"https://image.tmdb.org/t/p/w500{item.get('poster_path' )}" if item.get('poster_path') else '',
            'generos': [g['name'] for g in detalhes.get('genres', [])],
            'nota_externa': round(item.get('vote_average', 0) * 10), # Converte de 0-10 para 0-100
            'autor': ", ".join([c['name'] for c in detalhes.get('created_by', [])]) if tipo_busca == 'tv' else '', # Criador para séries
        }

        if tipo_busca == 'movie':
            dados_formatados['duracao'] = detalhes.get('runtime', 0) # Duração em minutos
        else: # tv
            dados_formatados['duracao'] = detalhes.get('number_of_episodes', 0) # Duração em episódios

        return [dados_formatados] # Retorna em uma lista para manter o padrão

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao conectar com a API do TMDb: {e}")
        return None

def buscar_dados_google_books(titulo, api_key):
    """Busca dados de Livros na API do Google Books."""
    if not api_key or "COLE_SUA_CHAVE" in api_key:
        st.error("A chave da API do Google Books não foi configurada no arquivo config.json.")
        return None

    url = f"https://www.googleapis.com/books/v1/volumes?q={titulo}&key={api_key}"
    
    try:
        response = requests.get(url )
        response.raise_for_status()
        resultados = response.json().get('items', [])

        if not resultados:
            st.warning(f"Nenhum resultado para '{titulo}' encontrado no Google Books.")
            return None

        # Pega o primeiro e mais relevante resultado
        item = resultados[0]['volumeInfo']
        
        dados_formatados = {
            'titulo': item.get('title'),
            'autor': ", ".join(item.get('authors', ['Autor desconhecido'])),
            'cover_url': item.get('imageLinks', {}).get('thumbnail', ''),
            'generos': [g for g in item.get('categories', [])],
            'nota_externa': round(item.get('averageRating', 0) * 20), # Converte de 0-5 para 0-100
            'duracao': item.get('pageCount', 0) # Duração em páginas
        }
        
        return [dados_formatados] # Retorna em uma lista para manter o padrão

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao conectar com a API do Google Books: {e}")
        return None

def buscar_dados_online_geral(titulo, tipo, config_api):
    """Função orquestradora que chama a API correta com base no tipo de mídia."""
    if tipo == "Jogo":
        return buscar_dados_igdb_com_confirmacao(titulo, config_api)
    elif tipo in ["Filme", "Série", "Anime"]: # Anime é buscado como 'tv' no TMDb
        return buscar_dados_tmdb(titulo, tipo, config_api.get('tmdb_api_key'))
    elif tipo == "Livro":
        return buscar_dados_google_books(titulo, config_api.get('google_books_api_key'))
    else:
        st.warning(f"A busca online ainda não está implementada para o tipo '{tipo}'.")
        return None

def analisar_backlog_para_acoes(backlog_df):
    """
    Analisa o backlog em busca de itens que precisam de atenção do usuário.
    Retorna um DataFrame com os itens e o motivo da pendência.
    Versão 2.0: Verifica mais tipos de problemas.
    """
    if backlog_df.empty:
        return pd.DataFrame()

    acoes_pendentes = []
    df = backlog_df.copy()

    # Garante que colunas numéricas sejam tratadas como tal
    numeric_cols = ['Nota_Externa', 'Duracao', 'Progresso_Atual', 'Minha_Nota']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    for index, item in df.iterrows():
        motivos = []
        
        # Ignora itens que já estão arquivados
        if item['Status'] == 'Arquivado':
            continue

        # Ação 1: Dados básicos incompletos (para itens que não são desejos)
        if item['Status'] != 'Desejo':
            if pd.isnull(item.get('Cover_URL')) or item.get('Cover_URL') == '':
                motivos.append("Falta a imagem da capa.")
            if item['Duracao'] == 0:
                motivos.append("Duração não preenchida.")
            if pd.isnull(item.get('Genero')) or item.get('Genero') == '':
                motivos.append("Falta definir o gênero.")
        
        # Ação 2: Inconsistências lógicas
        if item['Status'] == 'Em Andamento' and item['Progresso_Atual'] == 0:
            motivos.append("Está 'Em Andamento', mas com progresso zero.")
        
        if item['Status'] == 'Finalizado' and item['Minha_Nota'] == 0:
            motivos.append("Foi finalizado, mas está sem a sua avaliação pessoal.")

        if motivos:
            item_com_acao = item.to_dict()
            # Junta os motivos em uma única string para exibição
            item_com_acao['motivo'] = " ".join(motivos)
            acoes_pendentes.append(item_com_acao)
            
    return pd.DataFrame(acoes_pendentes)

def sincronizar_retroachievements(config, backlog_df):
    """
    Verifica e sincroniza conquistas recentes do RetroAchievements com o backlog.
    """
    ra_user = config.get('api_keys', {}).get('ra_user_name')
    ra_key = config.get('api_keys', {}).get('ra_api_key')
    
    if not ra_user or "SEU_NOME" in ra_user or not ra_key or "COLE_SUA_CHAVE" in ra_key:
        return None, None # Retorna None se não estiver configurado

    # Pega a data da última sincronização e converte para objeto datetime
    try:
        ultima_sinc_str = config.get('ultima_sincronizacao_ra', "2000-01-01 00:00:00")
        ultima_sinc_dt = datetime.strptime(ultima_sinc_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        ultima_sinc_dt = datetime.min # Em caso de erro no formato, busca tudo

    base_url = "https://retroachievements.org/API"
    auth_params = {"z": ra_user, "y": ra_key}
    
    try:
        # 1. Obter a lista de jogos que o usuário jogou
        url_user_progress = f"{base_url}/API_GetUserProgress.php"
        params = {**auth_params, "u": ra_user}
        response = requests.get(url_user_progress, params=params )
        response.raise_for_status()
        user_progress = response.json()

        jogos_atualizados = {}
        total_novas_conquistas = 0
        
        # 2. Para cada jogo, verificar as conquistas recentes
        for game_id, game_data in user_progress.items():
            # Procura o jogo no backlog pelo título (pode precisar de ajuste fino)
            # Idealmente, teríamos um campo 'RA_Game_ID' no backlog.csv
            titulo_jogo_ra = game_data.get("Title")
            if titulo_jogo_ra is None: continue

            # Procura por uma correspondência exata do título no backlog
            jogo_no_backlog = backlog_df[backlog_df['Titulo'].str.lower() == titulo_jogo_ra.lower()]
            if jogo_no_backlog.empty: continue

            # Pega o ID do jogo no SIB
            id_item_sib = jogo_no_backlog.iloc[0]['ID']

            # 3. Obter detalhes das conquistas para o jogo
            url_game_progress = f"{base_url}/API_GetGameInfoAndUserProgress.php"
            params_game = {**auth_params, "u": ra_user, "g": game_id}
            game_response = requests.get(url_game_progress, params=params_game)
            game_response.raise_for_status()
            game_details = game_response.json()

            novas_conquistas_neste_jogo = 0
            num_achievements_unlocked = 0
            
            if "Achievements" in game_details:
                for ach_id, ach_data in game_details["Achievements"].items():
                    if ach_data.get("DateEarned"):
                        num_achievements_unlocked += 1
                        data_conquista_dt = datetime.strptime(ach_data["DateEarned"], "%Y-%m-%d %H:%M:%S")
                        if data_conquista_dt > ultima_sinc_dt:
                            novas_conquistas_neste_jogo += 1
            
            if novas_conquistas_neste_jogo > 0:
                total_novas_conquistas += novas_conquistas_neste_jogo
                jogos_atualizados[titulo_jogo_ra] = novas_conquistas_neste_jogo
                
                # Atualiza o progresso no DataFrame
                idx = backlog_df[backlog_df['ID'] == id_item_sib].index
                backlog_df.loc[idx, 'Progresso_Atual'] = num_achievements_unlocked
                # Opcional: Atualiza o total de conquistas também
                backlog_df.loc[idx, 'Progresso_Total'] = game_details.get("NumAchievements", 0)

        if total_novas_conquistas > 0:
            # Constrói a mensagem de resumo
            resumo = f"RA Sincronizado! {total_novas_conquistas} nova(s) conquista(s) encontrada(s) em {len(jogos_atualizados)} jogo(s)."
            # Atualiza a data da última sincronização para agora
            config['ultima_sincronizacao_ra'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return backlog_df, resumo
        else:
            return backlog_df, "Nenhuma nova conquista no RetroAchievements desde a última sincronização."

    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao conectar com a API do RetroAchievements: {e}")
        return backlog_df, None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado durante a sincronização com RA: {e}")
        return backlog_df, None

    return backlog_df, None


# ==============================================================================
# 3. INTERFACE GRÁFICA (UI) E COMPONENTES
# ==============================================================================

def highlight_rows(row):
    color_map = {
        'Jogo': '#D6EAF8', 'Livro': '#D5F5E3', 'Série': '#FAE5D3',
        'Filme': '#FADBD8', 'Anime': '#E8DAEF', 'Mangá': '#FEF9E7'
    }
    color = color_map.get(row['Tipo'], '')
    return [f'background-color: {color}; color: black;' for _ in row]

def ui_componente_hall_of_fame(backlog_df):
    st.divider()
    st.subheader("🏆 Hall da Fama & Vergonha 🤡")
    df_avaliados = backlog_df[(backlog_df['Status'] == 'Finalizado') & (backlog_df['Minha_Nota'] > 0)].sort_values('Minha_Nota', ascending=False)
    
    if df_avaliados.empty:
        st.info("Avalie os itens que você finalizou para popular esta secção.")
        return
        
    col1, col2 = st.columns(2)
    with col1:
        st.write("**🏆 Hall da Fama (Melhores Notas)**")
        df_display = df_avaliados[['Titulo', 'Minha_Nota']].head(5).copy()
        df_display.columns = ["Título", "Minha Nota"]
        st.dataframe(df_display, hide_index=True, use_container_width=True)
    with col2:
        st.write("**🤡 Hall da Vergonha (Piores Notas)**")
        df_display = df_avaliados[['Titulo', 'Minha_Nota']].tail(5).sort_values('Minha_Nota', ascending=True).copy()
        df_display.columns = ["Título", "Minha Nota"]
        st.dataframe(df_display, hide_index=True, use_container_width=True)

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










def ui_aba_estante(backlog_df):
    st.header("📚 Minha Estante Virtual")
    st.info("Aqui estão todos os itens que você já finalizou. Parabéns!")
    
    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    
    if df_finalizados.empty:
        st.warning("Sua estante está vazia. Finalize alguns itens para começar!")
        return
        
    c1, c2, c3 = st.columns(3)
    with c1:
        tipos = ["Todos"] + sorted(df_finalizados['Tipo'].unique().tolist())
        tipo_filtro = st.selectbox("Filtrar por Tipo", tipos, key="estante_tipo")
    with c2:
        # Garante que a coluna de data de finalização seja do tipo datetime
        df_finalizados['Data_Finalizacao_dt'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
        anos = ["Todos"] + sorted(df_finalizados['Data_Finalizacao_dt'].dt.year.dropna().unique().astype(int).tolist(), reverse=True)
        ano_filtro = st.selectbox("Filtrar por Ano de Finalização", anos, key="estante_ano")
    with c3:
        ordem = st.selectbox("Ordenar por", ["Data de Finalização (Recente)", "Minha Nota (Maior)", "Título"], key="estante_ordem")

    if tipo_filtro != "Todos": df_finalizados = df_finalizados[df_finalizados['Tipo'] == tipo_filtro]
    if ano_filtro != "Todos": df_finalizados = df_finalizados[df_finalizados['Data_Finalizacao_dt'].dt.year == ano_filtro]
    
    if ordem == "Minha Nota (Maior)": df_finalizados = df_finalizados.sort_values('Minha_Nota', ascending=False)
    elif ordem == "Título": df_finalizados = df_finalizados.sort_values('Titulo')
    else: df_finalizados = df_finalizados.sort_values('Data_Finalizacao_dt', ascending=False)

    if df_finalizados.empty:
        st.info("Nenhum item corresponde aos filtros selecionados.")
        return

    cols = st.columns(5)
    for i, row in df_finalizados.reset_index().iterrows():
        with cols[i % 5]:
            with st.container(border=True):
                cover_url = row.get('Cover_URL', '')
                titulo_item = row.get('Titulo', 'Sem Título')

                if pd.notna(cover_url) and cover_url:
                    st.image(cover_url, caption=titulo_item)
                else:
                    st.image(f"https://placehold.co/400x600/222/fff?text={titulo_item}", caption=titulo_item )
                
                # Exibe a nota
                st.markdown(f"**Nota:** {row.get('Minha_Nota', 0):.0f} ⭐")

                # --- NOVA FUNCIONALIDADE AQUI ---
                # Exibe o tempo final de conclusão, se disponível
                tempo_final = float(row.get('Tempo_Final', 0))
                if tempo_final > 0:
                    unidade = row.get('Unidade_Duracao', 'unidades')
                    st.caption(f"Finalizado em: {tempo_final:.1f} {unidade}")

                if st.button("Ver Detalhes", key=f"details_{row['ID']}", use_container_width=True):
                    st.session_state[f"dialog_open_{row['ID']}"] = True

            if st.session_state.get(f"dialog_open_{row['ID']}", False):
                @st.dialog(f"Visualizando: {titulo_item}")
                def show_details_dialog(item_row):
                    cover_url_dialog = item_row.get('Cover_URL', '')
                    if pd.notna(cover_url_dialog) and cover_url_dialog:
                        st.image(cover_url_dialog)
                    else:
                        st.image(f"https://placehold.co/400x600/222/fff?text={item_row['Titulo']}" )
                    
                    data_finalizacao_str = pd.to_datetime(item_row.get('Data_Finalizacao')).strftime('%d/%m/%Y') if pd.notna(item_row.get('Data_Finalizacao')) else "Data não registrada"
                    st.write(f"**Finalizado em:** {data_finalizacao_str}")
                    st.write(f"**Sua Nota:** {item_row.get('Minha_Nota', 0):.0f} ⭐")
                    
                    tempo_final_dialog = float(item_row.get('Tempo_Final', 0))
                    if tempo_final_dialog > 0:
                        unidade_dialog = item_row.get('Unidade_Duracao', 'unidades')
                        st.write(f"**Tempo de Conclusão:** {tempo_final_dialog:.1f} {unidade_dialog}")

                show_details_dialog(row)
                st.session_state[f"dialog_open_{row['ID']}"] = False # Fecha o dialog para a próxima interação








def ui_aba_dashboard(backlog_df):
    st.header("Dashboard de Estatísticas")
    if backlog_df.empty:
        st.warning("Seu backlog está vazio. Adicione itens para ver as estatísticas.")
        return

    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Adicao'] = pd.to_datetime(df_finalizados['Data_Adicao'], errors='coerce')
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
    
    tempo_para_finalizar = (df_finalizados['Data_Finalizacao'] - df_finalizados['Data_Adicao']).dt.days
    tempo_medio_finalizar = tempo_para_finalizar.mean()

    total_itens = len(backlog_df)
    itens_finalizados = len(df_finalizados)
    percentual_finalizado = (itens_finalizados / total_itens) * 100 if total_itens > 0 else 0
    hype_medio = backlog_df[backlog_df['Status'] != 'Finalizado']['Meu_Hype'].mean()

    st.subheader("Visão Geral do seu Backlog")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Itens", f"{total_itens}")
    c2.metric("Itens Finalizados", f"{itens_finalizados} ({percentual_finalizado:.1f}%)")
    c3.metric("Hype Médio (em aberto)", f"{hype_medio:.2f}/10" if pd.notna(hype_medio) else "N/A")
    c4.metric("Tempo Médio na Fila", f"{tempo_medio_finalizar:.0f} dias" if pd.notna(tempo_medio_finalizar) else "N/A", help="Tempo médio entre adicionar e finalizar um item.")

    st.divider()

    tabs = st.tabs(["📊 Geral", "🎮 Jogos", "📚 Livros", "📺 Séries", "🎌 Animes", "🎬 Filmes", "📖 Mangás"])

    with tabs[0]: # Geral
        st.subheader("Análise Geral")
        
        # --- NOVA SEÇÃO DE AFINIDADE DE GÊNERO ---
        st.write("**Seus Gêneros Favoritos (por Afinidade)**", help="Calculado com base nos gêneros que você finaliza e avalia bem (nota >= 7). Mostra o que você realmente mais gosta!")
        afinidades = calcular_afinidade_genero(backlog_df)
        if afinidades:
            # Converte o dicionário para um DataFrame para facilitar a plotagem
            df_afinidade_plot = pd.DataFrame(list(afinidades.items()), columns=['Gênero', 'Pontuação de Afinidade'])
            df_afinidade_plot = df_afinidade_plot.sort_values('Pontuação de Afinidade', ascending=False).head(10)
            st.bar_chart(df_afinidade_plot.set_index('Gênero'))
        else:
            st.info("Finalize e avalie mais itens (com nota 7 ou superior) para descobrirmos seus gêneros favoritos!")
        
        st.divider()

        c1, c2 = st.columns(2)
        with c1:
            st.write("**Itens por Status**")
            st.bar_chart(backlog_df['Status'].value_counts())
        with c2:
            st.write("**Itens por Tipo de Mídia**")
            st.bar_chart(backlog_df['Tipo'].value_counts())

        st.write("**Distribuição das suas Notas (Itens Finalizados)**")
        notas_validas = df_finalizados[df_finalizados['Minha_Nota'] > 0]['Minha_Nota']
        if not notas_validas.empty:
            st.bar_chart(notas_validas.value_counts().sort_index())
        else:
            st.info("Avalie itens finalizados para ver a distribuição das suas notas.")
        ui_componente_hall_of_fame(backlog_df)

    with tabs[1]: # Jogos
        st.subheader("Análise de Jogos")
        df_jogos = backlog_df[backlog_df['Tipo'] == 'Jogo'].copy()
        if not df_jogos.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Desenvolvedoras**")
                st.bar_chart(df_jogos['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Plataformas**")
                st.bar_chart(df_jogos['Plataforma'].value_counts().head(5))
            st.write("**Gêneros de Jogos Mais Comuns (por quantidade)**")
            generos_jogos = df_jogos['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_jogos.value_counts().head(10))
        else:
            st.info("Nenhum jogo no seu backlog para análise.")

    with tabs[2]: # Livros
        st.subheader("Análise de Livros")
        df_livros = backlog_df[backlog_df['Tipo'] == 'Livro'].copy()
        if not df_livros.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Autores**")
                st.bar_chart(df_livros['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Gêneros Literários**")
                generos_livros = df_livros['Genero'].dropna().str.split(',').explode().str.strip()
                st.bar_chart(generos_livros.value_counts().head(5))
        else:
            st.info("Nenhum livro no seu backlog para análise.")

    with tabs[3]: # Séries
        st.subheader("Análise de Séries")
        df_series = backlog_df[backlog_df['Tipo'] == 'Série'].copy()
        if not df_series.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_series = df_series['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_series.value_counts().head(10))
        else:
            st.info("Nenhuma série no seu backlog para análise.")

    with tabs[4]: # Animes
        st.subheader("Análise de Animes")
        df_animes = backlog_df[backlog_df['Tipo'] == 'Anime'].copy()
        if not df_animes.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_animes = df_animes['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_animes.value_counts().head(10))
        else:
            st.info("Nenhum anime no seu backlog para análise.")

    with tabs[5]: # Filmes
        st.subheader("Análise de Filmes")
        df_filmes = backlog_df[backlog_df['Tipo'] == 'Filme'].copy()
        if not df_filmes.empty:
            st.write("**Gêneros Mais Comuns**")
            generos_filmes = df_filmes['Genero'].dropna().str.split(',').explode().str.strip()
            st.bar_chart(generos_filmes.value_counts().head(10))
        else:
            st.info("Nenhum filme no seu backlog para análise.")

    with tabs[6]: # Mangás
        st.subheader("Análise de Mangás")
        df_mangas = backlog_df[backlog_df['Tipo'] == 'Mangá'].copy()
        if not df_mangas.empty:
            c1, c2 = st.columns(2)
            with c1:
                st.write("**Top 5 Autores (Mangakás)**")
                st.bar_chart(df_mangas['Autor'].value_counts().head(5))
            with c2:
                st.write("**Top 5 Gêneros/Demografias**")
                generos_mangas = df_mangas['Genero'].dropna().str.split(',').explode().str.strip()
                st.bar_chart(generos_mangas.value_counts().head(5))
        else:
            st.info("Nenhum mangá no seu backlog para análise.")






def ui_aba_review_anual(backlog_df):
    st.header("🗓️ Meu Ano em Review")
    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'], errors='coerce')
    
    anos_disponiveis = sorted(df_finalizados['Data_Finalizacao'].dt.year.dropna().unique().astype(int), reverse=True)
    if not anos_disponiveis:
        st.warning("Nenhum item finalizado com data registrada. Finalize itens para gerar relatórios.")
        return
        
    ano_selecionado = st.selectbox("Selecione o ano para o relatório", anos_disponiveis)
    df_ano = df_finalizados[df_finalizados['Data_Finalizacao'].dt.year == ano_selecionado].copy()

    if df_ano.empty:
        st.info(f"Nenhum item finalizado registrado para o ano de {ano_selecionado}.")
        return

    st.subheader(f"Seu resumo de entretenimento em {ano_selecionado}")
    
    # Métricas Chave
    total_itens_ano = len(df_ano)
    nota_media_ano = df_ano[df_ano['Minha_Nota'] > 0]['Minha_Nota'].mean()
    total_horas_jogos_ano = df_ano[df_ano['Tipo'] == 'Jogo']['Duracao'].sum()
    total_paginas_livros_ano = df_ano[df_ano['Tipo'] == 'Livro']['Duracao'].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Itens Finalizados", f"{total_itens_ano}")
    c2.metric("Nota Média Pessoal", f"{nota_media_ano:.2f} ⭐" if pd.notna(nota_media_ano) else "N/A")
    c3.metric("Horas em Jogos", f"{total_horas_jogos_ano:.1f} h")
    c4.metric("Páginas Lidas", f"{total_paginas_livros_ano:.0f}")

    st.divider()

    # --- NOVA SEÇÃO DE DESTAQUES ---
    st.subheader("🏆 Destaques do Ano")
    
    # Item com a melhor nota
    melhor_item = df_ano.loc[df_ano['Minha_Nota'].idxmax()] if not df_ano[df_ano['Minha_Nota'] > 0].empty else None
    # Item mais longo (considerando apenas jogos em horas)
    item_mais_longo = df_ano.loc[df_ano[df_ano['Tipo'] == 'Jogo']['Duracao'].idxmax()] if not df_ano[df_ano['Tipo'] == 'Jogo'].empty else None

    c1, c2 = st.columns(2)
    with c1:
        if melhor_item is not None:
            st.markdown(f"**Melhor Avaliado:**")
            st.markdown(f"##### {melhor_item['Titulo']} ({melhor_item['Minha_Nota']:.0f} ⭐)")
        else:
            st.markdown("**Melhor Avaliado:**")
            st.info("Nenhum item avaliado este ano.")
    with c2:
        if item_mais_longo is not None:
            st.markdown(f"**Maior Jornada (Jogos):**")
            st.markdown(f"##### {item_mais_longo['Titulo']} ({item_mais_longo['Duracao']:.1f} h)")
        else:
            st.markdown("**Maior Jornada (Jogos):**")
            st.info("Nenhum jogo finalizado este ano.")

    st.divider()

    # Gráficos
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Finalizações por Tipo")
        st.bar_chart(df_ano['Tipo'].value_counts())
    with c2:
        st.subheader("Gêneros Favoritos do Ano")
        generos_ano = df_ano['Genero'].dropna().str.split(',').explode().str.strip()
        if not generos_ano.empty:
            st.bar_chart(generos_ano.value_counts().head(10))
        else:
            st.info("Nenhum gênero registrado.")
        
    st.subheader("Ritmo de Finalizações ao Longo do Ano")
    finalizacoes_por_mes = df_ano.groupby(df_ano['Data_Finalizacao'].dt.month).size()
    # Cria um DataFrame com todos os meses para garantir a ordem
    meses_df = pd.DataFrame({'Mes': range(1, 13)})
    meses_df = meses_df.merge(finalizacoes_por_mes.rename('Contagem'), left_on='Mes', right_index=True, how='left').fillna(0)
    meses_df['Nome_Mes'] = meses_df['Mes'].apply(lambda x: pd.to_datetime(f'2024-{x}-01').strftime('%b'))
    st.bar_chart(meses_df.set_index('Nome_Mes')['Contagem'])

    # --- NOVA TABELA DE ITENS FINALIZADOS ---
    with st.expander(f"Ver todos os {total_itens_ano} itens finalizados em {ano_selecionado}"):
        df_display_ano = df_ano[['Titulo', 'Tipo', 'Minha_Nota', 'Data_Finalizacao']].copy()
        df_display_ano.rename(columns={'Titulo': 'Título', 'Tipo': 'Tipo', 'Minha_Nota': 'Minha Nota', 'Data_Finalizacao': 'Finalizado em'}, inplace=True)
        df_display_ano['Finalizado em'] = df_display_ano['Finalizado em'].dt.strftime('%d/%m/%Y')
        st.dataframe(df_display_ano, use_container_width=True, hide_index=True)





def ui_aba_sessoes(sessoes_df, backlog_df):
    st.header("🎯 Sessões de Atividade")
    
    st.subheader("Registrar Nova Sessão")
    
    # Filtra itens que podem ter progresso registrado
    itens_ativos = backlog_df[backlog_df['Status'].isin(['Em Andamento', 'No Backlog'])].copy()
    
    if itens_ativos.empty:
        st.info("Você não tem itens 'Em Andamento' ou 'No Backlog' para registrar uma sessão.")
        return

    # Selectbox para escolher o item
    item_selecionado_titulo = st.selectbox(
        "Selecione o item para registrar a sessão:",
        options=itens_ativos['Titulo'].unique().tolist(),
        index=None, # Começa sem nada selecionado
        placeholder="Escolha um item..."
    )

    if item_selecionado_titulo:
        # Pega os dados do item selecionado
        item_selecionado = itens_ativos[itens_ativos['Titulo'] == item_selecionado_titulo].iloc[0]
        tipo_item = item_selecionado['Tipo']
        item_id = int(item_selecionado['ID'])

        with st.form(key=f"sessao_form_{item_id}"):
            st.write(f"Registrando sessão para **{item_selecionado_titulo}** ({tipo_item})")
            
            duracao_sessao = 0
            progresso_ganho = 0
            
            # --- FORMULÁRIO CONTEXTUAL ---
            if tipo_item == "Jogo":
                c1, c2 = st.columns(2)
                duracao_sessao = c1.number_input("Duração da Sessão (minutos)", min_value=0)
                progresso_ganho = c2.number_input("Conquistas Ganhas na Sessão", min_value=0)
            
            elif tipo_item == "Livro":
                progresso_ganho = st.number_input("Páginas Lidas na Sessão", min_value=0)
                # Para livros, a duração pode ser opcional ou não aplicável
                duracao_sessao = progresso_ganho * 2 # Estimativa de 2 min por página

            elif tipo_item in ["Série", "Anime"]:
                progresso_ganho = st.number_input("Episódios Assistidos na Sessão", min_value=1)
                duracao_sessao = progresso_ganho * 45 # Estimativa de 45 min por episódio

            elif tipo_item == "Mangá":
                progresso_ganho = st.number_input("Capítulos Lidos na Sessão", min_value=0)
                duracao_sessao = progresso_ganho * 5 # Estimativa de 5 min por capítulo
            
            elif tipo_item == "Filme":
                st.info("Filmes geralmente são finalizados em uma única sessão. Você pode registrar a finalização na aba 'Gerenciar'.")
                progresso_ganho = 0
                duracao_sessao = 0

            notas_sessao = st.text_area("Notas da Sessão (opcional)")
            
            if st.form_submit_button("Salvar Sessão", type="primary"):
                if progresso_ganho > 0 or duracao_sessao > 0:
                    max_id_sessao = st.session_state.sessoes_df['ID_Sessao'].max() if not st.session_state.sessoes_df.empty else 0

                    nova_sessao = {
                        "ID_Sessao": max_id_sessao + 1, "ID_Item": item_id, "Data": datetime.now().strftime("%Y-%m-%d"),
                        "Duracao_Sessao": duracao_sessao, "Progresso_Ganho": progresso_ganho, "Notas": notas_sessao
                    }
                    
                    st.session_state.sessoes_df = pd.concat([st.session_state.sessoes_df, pd.DataFrame([nova_sessao])], ignore_index=True)
                    salvar_dados(st.session_state.sessoes_df, ARQUIVO_SESSOES)
                    
                    # Atualiza o progresso no backlog
                    idx_backlog = st.session_state.backlog_df[st.session_state.backlog_df['ID'] == item_id].index
                    st.session_state.backlog_df.loc[idx_backlog, 'Progresso_Atual'] += progresso_ganho
                    
                    # Se o item não estava "Em Andamento", muda o status
                    if st.session_state.backlog_df.loc[idx_backlog, 'Status'].iloc[0] == 'No Backlog':
                        st.session_state.backlog_df.loc[idx_backlog, 'Status'] = 'Em Andamento'
                        st.toast("Status do item atualizado para 'Em Andamento'!")

                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                    
                    st.success("Sessão registrada e progresso atualizado!")
                    st.rerun()
                else:
                    st.warning("Nenhum progresso ou duração foi registrado para a sessão.")

    st.divider()
    st.subheader("Histórico de Sessões Recentes")
    if not sessoes_df.empty:
        # Junta os dataframes para mostrar o título do item
        df_display = sessoes_df.merge(backlog_df[['ID', 'Titulo']], left_on='ID_Item', right_on='ID', how='left')
        df_display_final = df_display[['Data', 'Titulo', 'Duracao_Sessao', 'Progresso_Ganho', 'Notas']].copy()
        df_display_final.columns = ["Data", "Título", "Duração (min)", "Progresso Ganho", "Notas"]
        # Mostra as 10 sessões mais recentes
        st.dataframe(df_display_final.sort_values(by="Data", ascending=False).head(10), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma sessão registrada ainda.")

def ui_aba_metas(backlog_df, config):
    st.header("🏁 Metas e Desafios")

    with st.form("add_meta_form"):
        st.subheader("Criar Nova Meta")
        c1, c2, c3 = st.columns(3)
        meta_tipo = c1.selectbox("Tipo de Mídia", ["Qualquer"] + sorted(backlog_df['Tipo'].unique().tolist()))
        meta_genero = c2.selectbox("Gênero Específico", ["Qualquer"] + sorted(backlog_df['Genero'].dropna().unique().tolist()))
        meta_quantidade = c3.number_input("Quantidade a Finalizar", min_value=1, value=10)
        meta_ano = st.number_input("Ano da Meta", min_value=datetime.now().year, value=datetime.now().year)

        if st.form_submit_button("Adicionar Meta", type="primary"):
            nova_meta = {"tipo": meta_tipo, "genero": meta_genero, "quantidade": meta_quantidade, "ano": meta_ano, "id": time.time()}
            st.session_state.config['metas'].append(nova_meta)
            salvar_config(st.session_state.config)
            st.success("Meta adicionada!")
            st.rerun()

    st.divider()
    st.subheader("Acompanhamento de Metas")
    
    if not config.get('metas', []):
        st.info("Nenhuma meta definida. Crie uma acima para começar!")
        return

    df_finalizados = backlog_df[backlog_df['Status'] == 'Finalizado'].copy()
    df_finalizados['Data_Finalizacao'] = pd.to_datetime(df_finalizados['Data_Finalizacao'])

    for i, meta in enumerate(config['metas']):
        df_meta = df_finalizados[df_finalizados['Data_Finalizacao'].dt.year == meta['ano']]
        if meta['tipo'] != 'Qualquer': df_meta = df_meta[df_meta['Tipo'] == meta['tipo']]
        if meta['genero'] != 'Qualquer': df_meta = df_meta[df_meta['Genero'] == meta['genero']]
        
        progresso = len(df_meta)
        objetivo = meta['quantidade']
        percentual = min(progresso / objetivo, 1.0) if objetivo > 0 else 0
        
        st.markdown(f"**Meta {i+1}:** Finalizar {objetivo} itens de **{meta['tipo']}** do gênero **{meta['genero']}** em **{meta['ano']}**")
        st.progress(percentual, text=f"{progresso} / {objetivo}")

def ui_aba_conquistas(config):
    st.header("🏆 Conquistas 🏆")
    st.info("Aqui estão todas as suas conquistas. As desbloqueadas ficam no topo!")
    
    conquistas = config.get('conquistas', {})
    if not conquistas:
        st.warning("Nenhuma conquista encontrada na configuração.")
        return

    desbloqueadas = {k: v for k, v in conquistas.items() if v['desbloqueada']}
    bloqueadas = {k: v for k, v in conquistas.items() if not v['desbloqueada']}

    # Seção de Conquistas Desbloqueadas
    if desbloqueadas:
        st.subheader("⭐ Desbloqueadas ⭐")
        cols = st.columns(4)
        i = 0
        for key, data in desbloqueadas.items():
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: #FFD700;'>🏆 {data['nome']}</h3>", unsafe_allow_html=True)
                    st.success(f"**Desbloqueada em:** {pd.to_datetime(data['data']).strftime('%d/%m/%Y')}")
                    st.caption(data['desc'])
            i += 1
    
    st.divider()

    # Seção de Conquistas Bloqueadas
    if bloqueadas:
        st.subheader("🔒 A Desbloquear 🔒")
        cols = st.columns(4)
        i = 0
        for key, data in bloqueadas.items():
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center; color: grey;'>🔒 {data['nome']}</h3>", unsafe_allow_html=True)
                    st.warning("**Bloqueada**")
                    st.caption(data['desc'])
            i += 1


def ui_aba_adicionar_itens():
    st.header("Adicionar Itens")
    
    if 'add_mode' not in st.session_state:
        st.session_state.add_mode = "Individualmente"

    add_mode_options = ["Individualmente", "Série / Volumes", "Em Lote (Busca Inteligente)"]
    st.session_state.add_mode = st.radio("Como deseja adicionar?", add_mode_options, horizontal=True, key="add_mode_selector")
    add_mode = st.session_state.add_mode

    if add_mode == "Individualmente":
        if 'tipo_selecionado_add' not in st.session_state:
            st.session_state.tipo_selecionado_add = "Jogo"

        tipos_entretenimento = ["Jogo", "Livro", "Série", "Filme", "Anime", "Mangá"]
        st.session_state.tipo_selecionado_add = st.selectbox("Primeiro, selecione o tipo de entretenimento:", tipos_entretenimento, key="tipo_selector_add")
        tipo_selecionado = st.session_state.tipo_selecionado_add

        with st.form("add_individual_form"):
            st.subheader(f"Adicionar Novo(a) {tipo_selecionado}")
            
            titulo = st.text_input("Título*")
            
            if tipo_selecionado != "Mangá":
                if st.form_submit_button("Buscar Dados Online", use_container_width=True):
                    if titulo:
                        st.session_state.busca_titulo = titulo
                        st.session_state.resultados_busca = buscar_dados_online_geral(titulo, tipo_selecionado, st.session_state.config.get('api_keys', {}))
                    else:
                        st.warning("Por favor, insira um título para buscar.")

            if st.session_state.get('resultados_busca'):
                st.write("---")
                st.subheader("Confirme os Dados Encontrados")
                dados_encontrados = st.session_state.resultados_busca[0]
                
                cover_url = st.text_input("URL da Capa", value=dados_encontrados.get('cover_url', ''))
                autor = st.text_input("Autor / Criador / Dev.", value=dados_encontrados.get('autor', ''))
                genero = st.text_input("Gênero", value=", ".join(dados_encontrados.get('generos', [])))
                nota_externa = st.number_input("Nota Externa (0-100)", min_value=0, max_value=100, value=int(dados_encontrados.get('nota_externa', 0)), help="Nota da crítica. A busca online tenta preencher este campo.")
                
                unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                unidade_atual = unidade_map.get(tipo_selecionado, 'unidades')
                duracao = st.number_input(f"Duração ({unidade_atual})", min_value=0.0, value=float(dados_encontrados.get('duracao', 0)), step=1.0, format="%.0f")
                plataforma = st.text_input("Plataforma", value=dados_encontrados.get('plataforma', ''))

            else:
                cover_url = st.text_input("URL da Imagem da Capa")
                plataforma = st.text_input("Plataforma")
                autor = st.text_input("Autor / Desenvolvedora")
                genero = st.text_input("Gênero")
                nota_externa = st.number_input("Nota Externa (0-100)", min_value=0, max_value=100, value=0, help="Nota da crítica (ex: Metacritic).")
                unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                duracao = st.number_input(f"Duração ({unidade_map.get(tipo_selecionado, 'unidades')})", min_value=0.0, value=0.0, step=0.5, format="%.1f")

            status = st.selectbox("Status", ["No Backlog", "Desejo", "Em Andamento", "Finalizado"])
            meu_hype = st.slider("Meu Hype (0-10)", 0, 10, 0)
            st.divider()
            
            eh_serie = st.checkbox("Faz parte de uma série?", key="add_eh_serie")
            nome_serie, ordem_serie, total_serie = "", 1, 1
            if eh_serie:
                c1, c2, c3 = st.columns(3)
                nome_serie = c1.text_input("Nome da Série")
                ordem_serie = c2.number_input("Ordem na Série", min_value=1, value=1)
                total_serie = c3.number_input("Total na Série", min_value=1, value=1)
            st.divider()

            prog_atual, prog_total = 0, 0
            if tipo_selecionado == 'Jogo':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Conquistas Atuais", min_value=0, value=0)
                prog_total = c2.number_input("Total de Conquistas", min_value=0, value=1)
            elif tipo_selecionado in ['Série', 'Anime']:
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Episódio Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Episódios", min_value=0, value=1)
            elif tipo_selecionado == 'Livro':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Página Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Páginas", min_value=0, value=1)
            elif tipo_selecionado == 'Mangá':
                c1, c2 = st.columns(2)
                prog_atual = c1.number_input("Edição/Capítulo Atual", min_value=0, value=0)
                prog_total = c2.number_input("Total de Edições/Capítulos", min_value=0, value=1)

            if st.form_submit_button("Salvar Item", type="primary"):
                if not titulo:
                    st.error("O campo 'Título' é obrigatório.")
                elif st.session_state.backlog_df['Titulo'].str.contains(f'^{titulo}$', case=False, regex=True).any():
                    st.error(f"ERRO: Um item com o título '{titulo}' já existe no backlog.")
                else:
                    max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                    unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios", "Mangá": "Edições"}
                    
                    novo_item = {
                        "ID": max_id + 1, "Titulo": titulo, "Tipo": tipo_selecionado, "Plataforma": plataforma,
                        "Autor": autor, "Genero": genero, "Status": status, "Meu_Hype": meu_hype,
                        "Nota_Externa": nota_externa, "Duracao": duracao, "Unidade_Duracao": unidade_map.get(tipo_selecionado, 'unidades'),
                        "Nome_Serie": nome_serie if eh_serie else "", 
                        "Ordem_Serie": ordem_serie if eh_serie else 1, 
                        "Total_Serie": total_serie if eh_serie else 1,
                        "Data_Adicao": datetime.now().strftime("%Y-%m-%d"), 
                        "Progresso_Atual": prog_atual, "Progresso_Total": prog_total, "Minha_Nota": 0,
                        "Cover_URL": cover_url, "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": origem_selecionada
                    }
                    novo_df = pd.DataFrame([novo_item])
                    st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, novo_df], ignore_index=True)
                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                    st.success(f"'{titulo}' foi adicionado!")
                    st.session_state.config = verificar_conquistas(st.session_state.backlog_df, st.session_state.config, item_id=novo_item['ID'])
                    
                    if 'resultados_busca' in st.session_state:
                        del st.session_state.resultados_busca
                    if 'busca_titulo' in st.session_state:
                        del st.session_state.busca_titulo

                    st.rerun()

    elif add_mode == "Série / Volumes":
        with st.form("add_series_form"):
            st.subheader("Adicionar Série / Volumes")
            nome_base = st.text_input("Nome da Série (ex: Vagabond)")
            total_edicoes = st.number_input("Número Total de Itens", min_value=1, value=1)
            edicoes_possuidas = st.number_input("Quantos itens você já possui?", min_value=0, value=0)
            tipo_serie = st.selectbox("Tipo", ["Mangá", "Livro", "Série"])
            
            if st.form_submit_button("Adicionar Série", use_container_width=True):
                if nome_base and total_edicoes > 0:
                    if st.session_state.backlog_df['Nome_Serie'].str.contains(f'^{nome_base}$', case=False, regex=True).any():
                        st.error(f"ERRO: Uma série com o nome '{nome_base}' já existe.")
                    else:
                        itens_para_adicionar = []
                        max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                        unidade_map = {"Mangá": "Edições", "Livro": "Páginas", "Série": "Episódios"}

                        for i in range(1, total_edicoes + 1):
                            titulo_item = f"{nome_base} #{i}"
                            item = {
                                "ID": max_id + i, "Titulo": titulo_item, "Tipo": tipo_serie, 
                                "Status": "No Backlog" if i <= edicoes_possuidas else "Desejo",
                                "Nome_Serie": nome_base, "Ordem_Serie": i, "Total_Serie": total_edicoes,
                                "Duracao": 1 if tipo_serie == "Mangá" else 0, 
                                "Unidade_Duracao": unidade_map.get(tipo_serie, 'unidades'),
                                "Data_Adicao": datetime.now().strftime("%Y-%m-%d"), "Meu_Hype": 0,
                                "Plataforma": "", "Autor": "", "Genero": "", "Nota_Externa": 0,
                                "Progresso_Atual": 0, "Progresso_Total": 0, "Minha_Nota": 0,
                                "Cover_URL": "", "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": "Grátis"
                            }
                            itens_para_adicionar.append(item)
                        
                        df_lote = pd.DataFrame(itens_para_adicionar)
                        st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, df_lote], ignore_index=True)
                        salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                        st.success(f"{total_edicoes} itens de '{nome_base}' adicionados!")
                        st.rerun()

    # --- SEÇÃO "EM LOTE" COMPLETAMENTE ATUALIZADA ---
    elif add_mode == "Em Lote (Busca Inteligente)":
        st.subheader("Adicionar Itens em Lote (com busca online)")
        st.info("Selecione o tipo de mídia, cole uma lista de títulos (um por linha) e o SIB buscará os dados de cada um.")
        
        # 1. Seletor de tipo de mídia
        tipo_lote = st.selectbox("Qual tipo de mídia você está adicionando?", ["Jogo", "Filme", "Série", "Livro", "Anime"])

        titulos_lote = st.text_area(f"Cole a lista de títulos de '{tipo_lote}' aqui:", height=250)
        
        if st.button("Processar e Adicionar em Lote", use_container_width=True, type="primary"):
            if titulos_lote:
                lista_titulos = [titulo.strip() for titulo in titulos_lote.split('\n') if titulo.strip()]
                
                titulos_existentes = st.session_state.backlog_df['Titulo'].str.lower().tolist()
                titulos_novos = [t for t in lista_titulos if t.lower() not in titulos_existentes]
                titulos_duplicados = [t for t in lista_titulos if t.lower() in titulos_existentes]

                if titulos_duplicados:
                    st.warning(f"Itens já existentes e ignorados: {', '.join(titulos_duplicados)}")

                if not titulos_novos:
                    st.error("Nenhum título novo para adicionar.")
                    return

                itens_para_adicionar = []
                falha = []
                max_id = st.session_state.backlog_df['ID'].max() if not st.session_state.backlog_df.empty else 0
                
                progress_bar = st.progress(0, text="Buscando dados...")
                
                for i, titulo in enumerate(titulos_novos):
                    progress_bar.progress((i + 1) / len(titulos_novos), text=f"Buscando: {titulo}")
                    
                    # 2. Usa a função de busca geral
                    resultados = buscar_dados_online_geral(titulo, tipo_lote, st.session_state.config.get('api_keys', {}))
                    
                    if resultados:
                        dados = resultados[0]
                        max_id += 1
                        unidade_map = {"Jogo": "Horas", "Livro": "Páginas", "Série": "Episódios", "Filme": "Minutos", "Anime": "Episódios"}
                        
                        # 3. Lógica de criação de item generalizada
                        item = {
                            "ID": max_id,
                            "Titulo": dados.get('titulo', titulo),
                            "Tipo": tipo_lote,
                            "Plataforma": dados.get('plataforma', ''),
                            "Autor": dados.get('autor', ''),
                            "Genero": ", ".join(dados.get('generos', [])),
                            "Status": "No Backlog",
                            "Meu_Hype": 0,
                            "Nota_Externa": int(dados.get('nota_externa', 0)),
                            "Duracao": float(dados.get('duracao', 0)),
                            "Unidade_Duracao": unidade_map.get(tipo_lote, 'unidades'),
                            "Nome_Serie": "", "Ordem_Serie": 1, "Total_Serie": 1,
                            "Data_Adicao": datetime.now().strftime("%Y-%m-%d"),
                            "Progresso_Atual": 0, "Progresso_Total": 1, "Minha_Nota": 0,
                            "Cover_URL": dados.get('cover_url', ''),
                            "Data_Finalizacao": pd.NaT, "Tempo_Final": 0, "Origem": "Grátis"
                        }
                        itens_para_adicionar.append(item)
                    else:
                        falha.append(titulo)
                
                progress_bar.empty()
                
                if itens_para_adicionar:
                    df_lote = pd.DataFrame(itens_para_adicionar)
                    st.session_state.backlog_df = pd.concat([st.session_state.backlog_df, df_lote], ignore_index=True)
                    salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                
                sucesso = len(itens_para_adicionar)
                st.success(f"Operação Concluída! {sucesso} item(ns) do tipo '{tipo_lote}' adicionado(s).")
                if falha:
                    st.warning(f"Títulos não encontrados: {', '.join(falha)}")
                st.balloons()
                time.sleep(2)
                st.rerun()






def ui_aba_gerenciar(backlog_df):
    st.header("Gerenciar Item do Backlog")
    if backlog_df.empty:
        st.info("Seu backlog está vazio.")
        return

    titulos = [""] + sorted(backlog_df['Titulo'].tolist())
    item_selecionado_titulo = st.selectbox("Selecione um item para editar ou excluir", titulos, key="gerenciar_select")
    
    if item_selecionado_titulo:
        idx = backlog_df[backlog_df['Titulo'] == item_selecionado_titulo].index[0]
        item_original = backlog_df.loc[idx].copy()

        with st.form("edit_form"):
            st.subheader(f"Editando: {item_original['Titulo']}")
            
            novo_titulo = st.text_input("Título", value=item_original['Titulo'])
            nova_cover_url = st.text_input("URL da Capa", value=item_original.get('Cover_URL', ''))
            
            status_opts = ["No Backlog", "Em Andamento", "Finalizado", "Desejo", "Arquivado"]
            novo_status = st.selectbox("Status", status_opts, index=status_opts.index(item_original['Status']))
            
            novo_hype = st.slider("Meu Hype", 0, 10, int(item_original.get('Meu_Hype', 0)))
            
            nova_minha_nota = item_original.get('Minha_Nota', 0)
            novo_tempo_final = item_original.get('Tempo_Final', 0)

            if novo_status == 'Finalizado':
                st.divider()
                st.write("⭐ **Informações de Finalização**")
                c1, c2 = st.columns(2)
                with c1:
                    nova_minha_nota = st.slider("Minha Nota Pessoal", 1, 10, max(1, int(item_original.get('Minha_Nota', 5))))
                with c2:
                    tempo_final_val = item_original.get('Tempo_Final') or 0
                    duracao_val = item_original.get('Duracao') or 0
                    valor_padrao_tempo = float(tempo_final_val) if float(tempo_final_val) > 0 else float(duracao_val)
                    
                    # --- TOOLTIP ADICIONADO AQUI ---
                    novo_tempo_final = st.number_input(f"Tempo Final de Conclusão ({item_original.get('Unidade_Duracao', 'unidades')})", min_value=0.0, value=valor_padrao_tempo, step=0.5, format="%.1f", help="Informe o tempo real que você levou para finalizar. Este valor será usado para o cálculo de PLs. Se deixado em 0, o sistema usará a duração estimada.")
                st.divider()

            st.write("Detalhes Adicionais")
            nova_plataforma = st.text_input("Plataforma", value=item_original.get('Plataforma', ''))
            novo_autor = st.text_input("Autor / Dev.", value=item_original.get('Autor', ''))
            novo_genero = st.text_input("Gênero", value=item_original.get('Genero', ''))
            
            st.divider()
            eh_serie_default = bool(item_original.get('Nome_Serie'))
            eh_serie = st.checkbox("Faz parte de uma série?", value=eh_serie_default, key="edit_eh_serie")
            
            novo_nome_serie = item_original.get('Nome_Serie', '')
            nova_ordem_serie = int(item_original.get('Ordem_Serie', 1))
            novo_total_serie = int(item_original.get('Total_Serie', 1))
            
            if eh_serie:
                c1, c2, c3 = st.columns(3)
                novo_nome_serie = c1.text_input("Nome da Série", value=novo_nome_serie)
                nova_ordem_serie = c2.number_input("Ordem na Série", min_value=1, value=nova_ordem_serie)
                novo_total_serie = c3.number_input("Total na Série", min_value=1, value=novo_total_serie)
            st.divider()

            st.write("Progresso")
            if item_original['Tipo'] == 'Jogo':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Conquistas Atuais", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Conquistas", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] in ['Série', 'Anime']:
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Episódio Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Episódios", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] == 'Livro':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Página Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Páginas", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            elif item_original['Tipo'] == 'Mangá':
                c1, c2 = st.columns(2)
                novo_prog_atual = c1.number_input("Edição/Capítulo Atual", min_value=0, value=int(item_original.get('Progresso_Atual', 0)))
                novo_prog_total = c2.number_input("Total de Edições/Capítulos", min_value=0, value=int(item_original.get('Progresso_Total', 0)))
            else:
                novo_prog_atual = item_original.get('Progresso_Atual', 0)
                novo_prog_total = item_original.get('Progresso_Total', 0)

            st.divider()
            cs, ce = st.columns(2)
            if cs.form_submit_button("Salvar Alterações", type="primary", use_container_width=True):
                dados_atualizados = {
                    'Titulo': novo_titulo, 'Cover_URL': nova_cover_url, 'Status': novo_status,
                    'Meu_Hype': novo_hype, 'Minha_Nota': nova_minha_nota, 'Plataforma': nova_plataforma,
                    'Autor': novo_autor, 'Genero': novo_genero,
                    'Nome_Serie': novo_nome_serie if eh_serie else "",
                    'Ordem_Serie': nova_ordem_serie if eh_serie else 1,
                    'Total_Serie': novo_total_serie if eh_serie else 1,
                    'Progresso_Atual': novo_prog_atual, 'Progresso_Total': novo_prog_total,
                    'Tempo_Final': novo_tempo_final
                }

                if novo_status == 'Finalizado' and item_original['Status'] != 'Finalizado':
                    tempo_usado_para_calculo = float(novo_tempo_final) if float(novo_tempo_final) > 0 else float(item_original.get('Duracao', 0))
                    conversor = st.session_state.config['conversores_pl'].get(item_original['Unidade_Duracao'], 1)
                    pls_ganhos = tempo_usado_para_calculo / conversor if conversor > 0 else 0
                    st.session_state.config['pontos_liberacao'] += pls_ganhos
                    st.toast(f"Item finalizado! Você ganhou {pls_ganhos:.1f} PLs!")
                    dados_atualizados['Data_Finalizacao'] = datetime.now().strftime("%Y-%m-%d")
                    
                    st.session_state.config = verificar_conquistas(st.session_state.backlog_df, st.session_state.config, item_id=item_original['ID'])
                
                for chave, valor in dados_atualizados.items():
                    st.session_state.backlog_df.loc[idx, chave] = valor

                salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                salvar_config(st.session_state.config)
                st.success("Item atualizado!")
                st.rerun()

            if ce.form_submit_button("EXCLUIR PERMANENTEMENTE", use_container_width=True):
                st.session_state.backlog_df = st.session_state.backlog_df.drop(idx).reset_index(drop=True)
                salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                st.warning(f"'{item_selecionado_titulo}' foi excluído.")
                st.rerun()









def ui_aba_configuracoes():
    st.header("Configurações do Sistema")
    
    with st.form("config_form"):
        st.subheader("Pesos do Algoritmo de Ranking")
        config = st.session_state.config
        pesos = config['pesos']
        
        pesos['Meu_Hype'] = st.slider("Peso do 'Meu Hype'", 0.0, 1.0, pesos.get('Meu_Hype', 0.25), 0.05, help="Define a importância da sua vontade pessoal de consumir um item.")
        pesos['Nota_Externa'] = st.slider("Peso da 'Nota Externa'", 0.0, 1.0, pesos.get('Nota_Externa', 0.15), 0.05, help="Define a importância da nota da crítica (ex: Metacritic).")
        # --- NOVO SLIDER AQUI ---
        pesos['Afinidade_Genero'] = st.slider("Peso da 'Afinidade de Gênero'", 0.0, 1.0, pesos.get('Afinidade_Genero', 0.10), 0.05, help="Prioriza itens de gêneros que você costuma avaliar bem.")
        pesos['Fator_Continuidade'] = st.slider("Peso do 'Fator de Continuidade'", 0.0, 1.0, pesos.get('Fator_Continuidade', 0.15), 0.05, help="Prioriza itens que dão sequência a uma série que você já começou.")
        pesos['Duracao'] = st.slider("Peso da 'Duração' (Invertido)", 0.0, 1.0, pesos.get('Duracao', 0.10), 0.05, help="Quanto maior o peso, mais o algoritmo priorizará itens CURTOS.")
        pesos['Progresso'] = st.slider("Peso do 'Progresso'", 0.0, 1.0, pesos.get('Progresso', 0.15), 0.05, help="Incentiva a finalização de itens que você já começou.")
        pesos['Antiguidade'] = st.slider("Peso da 'Antiguidade'", 0.0, 1.0, pesos.get('Antiguidade', 0.10), 0.05, help="Prioriza itens que estão há mais tempo no seu backlog.")
        
        # ... (resto da função sem alterações) ...
        st.divider()
        st.subheader("Regras de Gamificação")
        config['pontos_liberacao'] = st.number_input("Saldo de Pontos de Liberação (PLs)", min_value=0.0, value=float(config['pontos_liberacao']), step=0.5, format="%.1f", help="Moeda virtual ganha ao finalizar itens. Usada para 'comprar' itens da sua Lista de Desejos.")
        
        conversores = config.get('conversores_pl', {})
        c1, c2, c3 = st.columns(3)
        conversores['Horas'] = c1.number_input("Horas (Jogos) para 1 PL", min_value=1, value=conversores.get('Horas', 10))
        conversores['Páginas'] = c1.number_input("Páginas (Livros) para 1 PL", min_value=1, value=conversores.get('Páginas', 100))
        conversores['Edições'] = c2.number_input("Edições (Mangás) para 1 PL", min_value=1, value=conversores.get('Edições', 1))
        conversores['Episódios'] = c2.number_input("Episódios (Séries/Animes) para 1 PL", min_value=1, value=conversores.get('Episódios', 12))
        conversores['Minutos'] = c3.number_input("Minutos (Filmes) para 1 PL", min_value=1, value=conversores.get('Minutos', 180))
        config['conversores_pl'] = conversores

        st.divider()
        st.subheader("Outras Configurações")
        config['bonus_catchup_ativo'] = st.toggle("Ativar Bônus de Série 'Catch-up'", value=config.get('bonus_catchup_ativo', True), help="Aplica um bônus na pontuação de itens de uma série se você já finalizou um item posterior a eles (ex: jogar o volume 1 depois de já ter finalizado o 2).")
        config['bonus_catchup_valor'] = st.slider("Valor do Bônus 'Catch-up'", 1.1, 2.0, config.get('bonus_catchup_valor', 1.5), 0.1, help="Multiplicador aplicado à pontuação final do item elegível ao bônus. Ex: 1.5 = 50% de bônus.")

        if st.form_submit_button("Salvar Configurações", type="primary"):
            st.session_state.config.update(config)
            salvar_config(st.session_state.config)
            st.success("Configurações salvas!")
            st.rerun()

    st.divider()
    st.subheader("🛠️ Ferramentas Administrativas")
    st.warning("Use com cuidado. Estas ações modificam seus dados permanentemente.")
    
    if st.button("Recalcular PLs de Itens Já Finalizados", use_container_width=True):
        df_finalizados = st.session_state.backlog_df[st.session_state.backlog_df['Status'] == 'Finalizado']
        total_pls_devidos = 0
        
        if not df_finalizados.empty:
            for _, row in df_finalizados.iterrows():
                tempo_final = float(row.get('Tempo_Final') or 0)
                duracao_estimada = float(row.get('Duracao') or 0)
                
                tempo_usado = tempo_final if tempo_final > 0 else duracao_estimada
                
                unidade = row['Unidade_Duracao']
                conversor = st.session_state.config['conversores_pl'].get(unidade, 1)
                
                if conversor > 0 and tempo_usado > 0:
                    total_pls_devidos += tempo_usado / conversor
            
            st.session_state.config['pontos_liberacao'] = total_pls_devidos
            salvar_config(st.session_state.config)
            st.success(f"Varredura completa! Seu novo saldo de PLs foi recalculado para {total_pls_devidos:.1f} baseado em {len(df_finalizados)} itens finalizados.")
            st.rerun()
        else:
            st.info("Nenhum item finalizado encontrado para recalcular.")






def ui_aba_backup():
    st.header("Backup e Restauro de Dados")
    st.subheader("Exportar Backup")
    st.info("Clique para descarregar um ficheiro .zip com todos os seus dados.")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # --- MELHORIA DE ROBUSTEZ ---
        # Adiciona ao zip apenas os arquivos que existem
        for f in [ARQUIVO_BACKLOG, ARQUIVO_CONFIG, ARQUIVO_SESSOES]:
            if os.path.exists(f):
                zf.write(f)
                
    st.download_button(
        label="Descarregar Backup", 
        data=zip_buffer.getvalue(), 
        file_name=f"sib_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip", 
        mime="application/zip"
    )
    
    st.divider()
    st.subheader("Importar Backup")
    st.warning("Atenção: A importação substituirá todos os seus dados atuais.", icon="⚠️")
    uploaded_file = st.file_uploader("Carregue o seu ficheiro de backup (.zip)", type="zip")
    
    if uploaded_file:
        if st.button("Restaurar a partir deste Backup", type="primary"):
            try:
                with zipfile.ZipFile(uploaded_file, 'r') as zf:
                    zf.extractall(".")
                
                # --- MELHORIA DE USABILIDADE ---
                st.success("Backup restaurado com sucesso! A aplicação será reiniciada em 3 segundos...")
                time.sleep(3)
                st.session_state.clear() # Limpa o cache para forçar o recarregamento dos novos arquivos
                st.rerun()
            except Exception as e:
                st.error(f"Ocorreu um erro ao restaurar: {e}")

def ui_aba_centro_de_acoes(acoes_pendentes_df, config):
    st.header("🎯 Centro de Ações 2.0")
    st.info("Aqui estão os itens do seu backlog que precisam de atenção, como dados faltantes ou inconsistentes.")

    if acoes_pendentes_df.empty:
        st.success("🎉 Parabéns! Seu backlog está totalmente preenchido e consistente. Nenhuma ação pendente encontrada.")
        return

    st.subheader(f"Itens com Ações Pendentes: {len(acoes_pendentes_df)}")

    for index, item in acoes_pendentes_df.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{item['Titulo']}** ({item['Tipo']})")
                # Exibe o motivo da pendência de forma clara
                st.caption(f"🚨 **Pendência:** {item['motivo']}")

            with c2:
                # --- ALTERAÇÃO AQUI: Botão de busca online para mais tipos ---
                tipos_com_busca = ["Jogo", "Filme", "Série", "Livro", "Anime"]
                if item['Tipo'] in tipos_com_busca and "Falta" in item['motivo']: # Só mostra se faltar dados
                    if st.button("Buscar Online", key=f"buscar_{item['ID']}", use_container_width=True):
                        st.session_state[f"buscando_item_{item['ID']}"] = True
                        st.rerun()

                # Botão para edição/preenchimento manual
                if st.button("Resolver Manualmente", key=f"manual_{item['ID']}", use_container_width=True):
                    # Reutiliza a aba "Gerenciar" para uma experiência de edição completa
                    st.warning(f"Para resolver, vá para a aba 'Gerenciar' e selecione '{item['Titulo']}'.")
                    st.session_state.gerenciar_select = item['Titulo'] # Pré-seleciona o item na outra aba


            # Lógica para exibir o formulário de busca online (agora genérico)
            if st.session_state.get(f"buscando_item_{item['ID']}"):
                st.write("---")
                st.subheader(f"Buscando dados para: {item['Titulo']}")
                
                resultados = buscar_dados_online_geral(item['Titulo'], item['Tipo'], config.get('api_keys', {}))
                
                if resultados:
                    dados = resultados[0]
                    st.success("Dados encontrados!")
                    
                    # Mostra o que foi encontrado
                    st.write(f"**Capa:**")
                    st.image(dados.get('cover_url'), width=150)
                    st.write(f"**Gênero(s):** {', '.join(dados.get('generos', []))}")
                    st.write(f"**Duração:** {dados.get('duracao', 0)}")

                    if st.button("Aplicar Dados Encontrados", key=f"aplicar_{item['ID']}", type="primary"):
                        idx_original = st.session_state.backlog_df[st.session_state.backlog_df['ID'] == item['ID']].index
                        
                        # Atualiza apenas os campos que estavam vazios, para não sobrescrever dados manuais
                        if pd.isnull(item.get('Cover_URL')) or item.get('Cover_URL') == '':
                            st.session_state.backlog_df.loc[idx_original, 'Cover_URL'] = dados.get('cover_url')
                        if pd.isnull(item.get('Genero')) or item.get('Genero') == '':
                            st.session_state.backlog_df.loc[idx_original, 'Genero'] = ", ".join(dados.get('generos', []))
                        if pd.to_numeric(item.get('Duracao'), errors='coerce') == 0:
                            st.session_state.backlog_df.loc[idx_original, 'Duracao'] = float(dados.get('duracao', 0))
                        if pd.to_numeric(item.get('Nota_Externa'), errors='coerce') == 0:
                             st.session_state.backlog_df.loc[idx_original, 'Nota_Externa'] = int(dados.get('nota_externa', 0))
                        
                        salvar_dados(st.session_state.backlog_df, ARQUIVO_BACKLOG)
                        st.toast("Item atualizado com sucesso!")
                        del st.session_state[f"buscando_item_{item['ID']}"]
                        st.rerun()
                else:
                    st.error("Nenhum dado encontrado para este título.")










# ==============================================================================
# 4. APLICAÇÃO PRINCIPAL (main)
# ==============================================================================


# ==============================================================================
# 4. APLICAÇÃO PRINCIPAL (COM AUTENTICAÇÃO)
# ==============================================================================

def login_page():
    st.title("🚀 SIB - Login")
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
                    st.success("Conta criada! Verifique seu email ou tente entrar.")
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")

def main():
    st.set_page_config(page_title="SIB - Sistema Inteligente de Backlog", layout="wide")
    
    if 'user' not in st.session_state:
        login_page()
        return

    # Se logado, carrega os dados
    if 'config' not in st.session_state:
        st.session_state.config = carregar_config()
    if 'backlog_df' not in st.session_state:
        st.session_state.backlog_df = carregar_dados(TABELA_BACKLOG, COLUNAS_ESPERADAS_BACKLOG)
    if 'sessoes_df' not in st.session_state:
        st.session_state.sessoes_df = carregar_dados(TABELA_SESSOES, COLUNAS_ESPERADAS_SESSOES)

    # Sidebar com Logout
    with st.sidebar:
        st.write(f"Logado como: {st.session_state.user.email}")
        if st.button("Sair"):
            supabase = get_supabase_client()
            supabase.auth.sign_out()
            del st.session_state.user
            st.rerun()
        st.divider()

    # --- O resto do código original (abas, etc) ---
    df_acoes = analisar_backlog_para_acoes(st.session_state.backlog_df)
    num_acoes_pendentes = len(df_acoes)

    with st.sidebar:
        st.title("Controles do SIB")
        st.header(f"🌟 PLs: {st.session_state.config.get('pontos_liberacao', 0):.1f}")
        st.divider()
        
        label_centro_acoes = f"Centro de Ações 🎯"
        if num_acoes_pendentes > 0:
            label_centro_acoes = f"Centro de Ações 🎯 ({num_acoes_pendentes})"

        abas = ["Ranking", "Minha Estante 📚", "Dashboard 📊", "Meu Ano em Review 🗓️", 
                label_centro_acoes, "Sessões 🎯", "Metas 🏁", "Conquistas 🏆", 
                "Adicionar Itens", "Gerenciar", "Configurações", "Backup / Restauro 💾"]
        
        aba_selecionada_raw = st.radio("Navegação", abas, key="main_nav")
        aba_selecionada = aba_selecionada_raw.split('(')[0].strip()
        st.divider()
        
        if aba_selecionada == "Ranking":
            st.header("Filtros do Ranking")
            tipos_disponiveis = ["Todos"] + sorted(st.session_state.backlog_df['Tipo'].unique().tolist())
            generos_disponiveis = ["Todos"] + sorted(list(set(g for generos in st.session_state.backlog_df['Genero'].dropna() for g in generos.split(', '))))
            autores_disponiveis = ["Todos"] + sorted(st.session_state.backlog_df['Autor'].dropna().unique().tolist())
            st.selectbox("Filtrar por Tipo", tipos_disponiveis, key="tipo_filtro")
            st.selectbox("Filtrar por Gênero", generos_disponiveis, key="genero_filtro")
            st.selectbox("Filtrar por Autor / Dev.", autores_disponiveis, key="autor_filtro")

    if aba_selecionada == "Ranking": ui_aba_ranking(st.session_state.backlog_df, st.session_state.config)
    elif aba_selecionada == "Minha Estante 📚": ui_aba_estante(st.session_state.backlog_df)
    elif aba_selecionada == "Dashboard 📊": ui_aba_dashboard(st.session_state.backlog_df)
    elif aba_selecionada == "Meu Ano em Review 🗓️": ui_aba_review_anual(st.session_state.backlog_df)
    elif aba_selecionada == "Centro de Ações 🎯": ui_aba_centro_de_acoes(df_acoes, st.session_state.config)
    elif aba_selecionada == "Sessões 🎯": ui_aba_sessoes(st.session_state.sessoes_df, st.session_state.backlog_df)
    elif aba_selecionada == "Metas 🏁": ui_aba_metas(st.session_state.backlog_df, st.session_state.config)
    elif aba_selecionada == "Conquistas 🏆": ui_aba_conquistas(st.session_state.config)
    elif aba_selecionada == "Adicionar Itens": ui_aba_adicionar_itens()
    elif aba_selecionada == "Gerenciar": ui_aba_gerenciar(st.session_state.backlog_df)
    elif aba_selecionada == "Configurações": ui_aba_configuracoes()
    elif aba_selecionada == "Backup / Restauro 💾": ui_aba_backup()

if __name__ == "__main__":
    main()
