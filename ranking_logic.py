import pandas as pd
import numpy as np
from datetime import datetime

def calcular_ranking(backlog_df, config, fatores_ativos):
    """
    Algoritmo principal do SIB. Calcula a pontuação de cada item.
    """
    if backlog_df.empty:
        return backlog_df

    df = backlog_df.copy()
    pesos = config.get('pesos', {})
    
    # Normalização e cálculos de base
    df['Data_Adicao'] = pd.to_datetime(df['Data_Adicao'], errors='coerce')
    hoje = datetime.now()
    
    # 1. Antiguidade (Normalizada 0-10)
    df['Dias_Fila'] = (hoje - df['Data_Adicao']).dt.days.fillna(0)
    max_dias = df['Dias_Fila'].max() if df['Dias_Fila'].max() > 0 else 1
    df['Score_Antiguidade'] = (df['Dias_Fila'] / max_dias) * 10
    
    # 2. Progresso (Normalizado 0-10)
    df['Progresso_Total'] = pd.to_numeric(df['Progresso_Total'], errors='coerce').fillna(1)
    df['Progresso_Atual'] = pd.to_numeric(df['Progresso_Atual'], errors='coerce').fillna(0)
    df['Progresso_Perc'] = (df['Progresso_Atual'] / df['Progresso_Total']).clip(0, 1)
    df['Score_Progresso'] = df['Progresso_Perc'] * 10
    
    # 3. Duração (Inverso: mais curto = maior pontuação, normalizado 0-10)
    df['Duracao'] = pd.to_numeric(df['Duracao'], errors='coerce').fillna(0)
    max_duracao = df['Duracao'].max() if df['Duracao'].max() > 0 else 1
    df['Score_Duracao'] = (1 - (df['Duracao'] / max_duracao)) * 10
    
    # Cálculo da Pontuação Final Ponderada
    df['Pontuacao_Final'] = 0.0
    
    if fatores_ativos.get("Meu_Hype", True):
        df['Pontuacao_Final'] += df['Meu_Hype'].fillna(0) * pesos.get('Meu_Hype', 0.25)
    
    if fatores_ativos.get("Nota_Externa", True):
        # Nota externa costuma ser 0-100, normalizamos para 0-10
        df['Pontuacao_Final'] += (df['Nota_Externa'].fillna(0) / 10) * pesos.get('Nota_Externa', 0.15)
        
    if fatores_ativos.get("Antiguidade", True):
        df['Pontuacao_Final'] += df['Score_Antiguidade'] * pesos.get('Antiguidade', 0.10)
        
    if fatores_ativos.get("Progresso", True):
        df['Pontuacao_Final'] += df['Score_Progresso'] * pesos.get('Progresso', 0.15)
        
    if fatores_ativos.get("Duracao", True):
        df['Pontuacao_Final'] += df['Score_Duracao'] * pesos.get('Duracao', 0.10)

    # Ordenar pelo Ranking
    return df.sort_values(by='Pontuacao_Final', ascending=False)
