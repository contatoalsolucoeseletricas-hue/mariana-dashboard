#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================
MARIANA BOT - PAINEL INSTITUCIONAL DE TRADING (VERSÃO CORRIGIDA)
====================================================================
- ✅ 100% em Português do Brasil (Interface, Mensagens e Análises)
- ✅ Autenticação Segura (Login e Cadastro isolados, sem sobrescrita)
- ✅ Banco de Dados Resiliente (SQLite nativo com suporte a Supabase)
- ✅ Gráficos Interativos Profissionais com Plotly (Candlestick + Indicadores)
- ✅ Correção Crítica dos Indicadores (EMA 20, EMA 200, BMSB, etc.)
- ✅ Análise de Imagem Real via IA Multimodal (Google Gemini)
- ✅ Assistente de Chat Especializado em Mercado Cripto
- ✅ Monitoramento de Posições na BingX com PnL em tempo real
- ✅ Segurança: Chaves e Segredos protegidos via arquivo .env
====================================================================
"""

import os
import sqlite3
import hashlib
from datetime import datetime
import requests
import numpy as np
import pandas as pd
import streamlit as st
import ccxt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv
from PIL import Image

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# ===== CONFIGURAÇÃO DA PÁGINA STREAMLIT =====
st.set_page_config(
    page_title="Mariana Bot - Painel Institucional",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== ESTILOS CUSTOMIZADOS (ADAPTADO PARA DESKTOP E CELULAR) =====
st.markdown("""
<style>
    @media (max-width: 768px) {
        .css-1d391kg {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        .stMetric {
            margin-bottom: 8px;
        }
        .stButton button {
            width: 100%;
        }
    }
    .metric-card {
        background-color: #1e222d;
        border-radius: 8px;
        padding: 12px;
        border: 1px solid #2a2e39;
    }
    .status-alta {
        color: #26a69a;
        font-weight: bold;
    }
    .status-baixa {
        color: #ef5350;
        font-weight: bold;
    }
    .status-neutro {
        color: #fbc02d;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ===== BANCO DE DADOS LOCAL (SQLITE) E SUPABASE =====
DB_PATH = "mariana_historico.db"
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')
SUPABASE_HABILITADO = False

supabase_cliente = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_cliente = create_client(SUPABASE_URL, SUPABASE_KEY)
        SUPABASE_HABILITADO = True
    except Exception:
        SUPABASE_HABILITADO = False

def init_banco_local():
    """Garante que as tabelas necessárias existam no SQLite local."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            nome TEXT,
            senha_hash TEXT,
            role TEXT DEFAULT 'membro',
            criado_em TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            email TEXT,
            nome TEXT,
            acao TEXT,
            detalhe TEXT,
            onde TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_analises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            simbolo TEXT,
            tipo TEXT,
            resultado TEXT,
            confianca INTEGER,
            tendencia TEXT,
            usuario TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

# Inicializa o banco local ao iniciar a aplicação
init_banco_local()

# ===== SEGURANÇA E HASH DE SENHA =====
ADMIN_SENHA = os.getenv("ADMIN_SENHA", "admin123")

def criar_senha_hash(senha: str) -> str:
    """Gera hash SHA-256 com um salt de aplicação."""
    salt = "mariana_bot_salt_seguro_"
    return hashlib.sha256((salt + senha).encode('utf-8')).hexdigest()

def autenticar_usuario_banco(email: str, senha: str):
    """
    Verifica credenciais.
    Retorna (sucesso: bool, nome: str, role: str, mensagem: str)
    """
    email_limpo = email.strip().lower()
    senha_hash = criar_senha_hash(senha)
    
    # Tentativa via Supabase (se configurado)
    if SUPABASE_HABILITADO and supabase_cliente:
        try:
            resposta = supabase_cliente.table('usuarios').select('*').eq('email', email_limpo).execute()
            if resposta.data:
                u = resposta.data[0]
                # Aceita tanto hash com salt quanto hash legado
                if u.get('senha_hash') == senha_hash or u.get('senha_hash') == hashlib.sha256(senha.encode()).hexdigest():
                    return True, u.get('nome', 'Usuário'), u.get('role', 'membro'), "Login realizado com sucesso."
                return False, "", "", "Senha incorreta."
        except Exception:
            pass
            
    # Consulta no SQLite Local
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT nome, senha_hash, role FROM usuarios WHERE lower(email) = ?', (email_limpo,))
    linha = cursor.fetchone()
    conn.close()
    
    if linha:
        nome_db, hash_db, role_db = linha
        # Compatibilidade com hash com salt e legado
        if hash_db == senha_hash or hash_db == hashlib.sha256(senha.encode()).hexdigest():
            return True, nome_db, role_db or 'membro', "Login realizado com sucesso."
        return False, "", "", "Senha incorreta."
        
    return False, "", "", "E-mail não cadastrado no sistema."

def cadastrar_usuario_banco(email: str, nome: str, senha: str):
    """
    Cadastra novo usuário de forma segura, sem sobrescrever contas existentes.
    Retorna (sucesso: bool, mensagem: str)
    """
    email_limpo = email.strip().lower()
    if not email_limpo or not nome.strip() or not senha:
        return False, "Por favor, preencha todos os campos obrigatórios."
        
    senha_hash = criar_senha_hash(senha)
    data_agora = datetime.now().isoformat()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM usuarios WHERE lower(email) = ?', (email_limpo,))
    if cursor.fetchone():
        conn.close()
        return False, "Este e-mail já está cadastrado. Por favor, acerte a senha ou use o login."
        
    try:
        cursor.execute('''
            INSERT INTO usuarios (email, nome, senha_hash, role, criado_em)
            VALUES (?, ?, ?, 'membro', ?)
        ''', (email_limpo, nome.strip(), senha_hash, data_agora))
        conn.commit()
        conn.close()
        
        # Sincroniza com Supabase se disponível
        if SUPABASE_HABILITADO and supabase_cliente:
            try:
                supabase_cliente.table('usuarios').insert({
                    'email': email_limpo,
                    'nome': nome.strip(),
                    'senha_hash': senha_hash,
                    'role': 'membro',
                    'criado_em': data_agora
                }).execute()
            except Exception:
                pass
                
        return True, "Cadastro realizado com sucesso! Agora você já pode entrar."
    except Exception as e:
        conn.close()
        return False, f"Erro ao registrar usuário: {e}"

def registrar_acao(email: str, nome: str, acao: str, detalhe: str, onde: str):
    """Grava o registro de auditoria no SQLite e Supabase."""
    data_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO registros (data, email, nome, acao, detalhe, onde)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data_agora, email, nome, acao, detalhe, onde))
        conn.commit()
        conn.close()
    except Exception:
        pass
        
    if SUPABASE_HABILITADO and supabase_cliente:
        try:
            supabase_cliente.table('registros').insert({
                'data': data_agora,
                'email': email,
                'nome': nome,
                'acao': acao,
                'detalhe': detalhe,
                'onde': onde
            }).execute()
        except Exception:
            pass

def carregar_registros():
    """Retorna registros de auditoria em DataFrame."""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, data as Data, email as 'E-mail', nome as Nome, acao as 'Ação', detalhe as Detalhe, onde as 'Seção' FROM registros ORDER BY id DESC LIMIT 500", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def apagar_todos_registros():
    """Apaga os registros de auditoria."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM registros")
        conn.commit()
        conn.close()
    except Exception:
        pass
    if SUPABASE_HABILITADO and supabase_cliente:
        try:
            supabase_cliente.table('registros').delete().gte('id', 0).execute()
        except Exception:
            pass

def listar_usuarios():
    """Retorna tabela de usuários."""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, email as 'E-mail', nome as Nome, role as 'Perfil', criado_em as 'Cadastrado Em' FROM usuarios ORDER BY id DESC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

def excluir_usuario(email: str):
    """Exclui usuário pelo e-mail."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM usuarios WHERE email = ?", (email,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    if SUPABASE_HABILITADO and supabase_cliente:
        try:
            supabase_cliente.table('usuarios').delete().eq('email', email).execute()
        except Exception:
            pass

def salvar_analise(simbolo, tipo, resultado, confianca, tendencia, usuario):
    """Salva a análise no histórico."""
    data_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO historico_analises (data, simbolo, tipo, resultado, confianca, tendencia, usuario)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data_agora, simbolo, tipo, resultado, confianca, tendencia, usuario))
        conn.commit()
        conn.close()
    except Exception:
        pass

def carregar_historico():
    """Retorna o histórico de análises em DataFrame."""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, data as Data, simbolo as 'Ativo', tipo as 'Tipo', resultado as 'Resultado', confianca as 'Confiança (%)', tendencia as 'Tendência', usuario as 'Usuário' FROM historico_analises ORDER BY id DESC LIMIT 200", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

# ===== INTEGRAÇÃO COM TELEGRAM (HTTP) =====
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '') or os.getenv('GRUPO_MESTRE_ID', '')

def enviar_telegram(mensagem: str):
    """Envia notificação formatada para o Telegram."""
    try:
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.getenv('TELEGRAM_CHAT_ID', '') or os.getenv('GRUPO_MESTRE_ID', '')
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception:
        return False

# ===== CONEXÃO COM A CORRETORA BINGX (CCXT) =====
@st.cache_resource
def get_exchange():
    """Inicializa a conexão segura com a corretora BingX."""
    api_key = os.getenv('BINGX_API_KEY', '').strip()
    secret = os.getenv('BINGX_SECRET', '').strip()
    
    if not api_key or not secret:
        return None
        
    try:
        return ccxt.bingx({
            'apiKey': api_key,
            'secret': secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'timeout': 30000
        })
    except Exception:
        return None

@st.cache_data(ttl=120)
def fetch_ohlcv(symbol, timeframe, limit=300):
    """Baixa histórico de velas (OHLCV) com cache de 2 minutos."""
    try:
        exchange = get_exchange()
        if not exchange:
            # Fallback público sem chaves se necessário
            exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception:
        return None

@st.cache_data(ttl=30)
def fetch_ticker(symbol):
    """Obtém cotação em tempo real com cache de 30 segundos."""
    try:
        exchange = get_exchange()
        if not exchange:
            exchange = ccxt.bingx({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})
        return exchange.fetch_ticker(symbol)
    except Exception:
        return None

def safe_float(valor, default=0.0):
    """Converte valores com segurança evitando quebras."""
    try:
        if valor is None or valor == '':
            return default
        return float(valor)
    except Exception:
        return default

# ===== DADOS DE MERCADO EXTERNO =====
def get_fear_greed_index():
    """Busca o índice de Medo e Ganância do mercado de criptomoedas."""
    try:
        req = requests.get('https://api.alternative.me/fng/?limit=1', timeout=5).json()
        return int(req['data'][0]['value'])
    except Exception:
        return 50

def get_whale_activity(simbolo):
    """Consulta dados de volume e capitalização de mercado."""
    try:
        moeda = simbolo.split('/')[0].lower()
        mapa_ids = {
            'btc': 'bitcoin', 'eth': 'ethereum', 'sol': 'solana',
            'bnb': 'binancecoin', 'xrp': 'ripple', 'ada': 'cardano',
            'doge': 'dogecoin', 'sui': 'sui', 'avax': 'avalanche-2'
        }
        coin_id = mapa_ids.get(moeda, moeda)
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_id}&price_change_percentage=24h"
        r = requests.get(url, timeout=5).json()
        if r and isinstance(r, list) and len(r) > 0:
            return {
                'preco': r[0].get('current_price', 0),
                'variacao_24h': r[0].get('price_change_percentage_24h', 0),
                'volume_24h': r[0].get('total_volume', 0),
                'market_cap': r[0].get('market_cap', 0)
            }
    except Exception:
        pass
    return None

def get_whale_alerts():
    """Consulta alertas recentes de movimentações de grandes carteiras."""
    api_key = os.getenv("WHALE_ALERT_API_KEY", "")
    if not api_key:
        return []
    try:
        url = f"https://api.whale-alert.io/v1/transactions?api_key={api_key}&limit=5"
        resp = requests.get(url, timeout=5).json()
        if 'transactions' in resp:
            return resp['transactions']
    except Exception:
        pass
    return []

# ===== CÁLCULO DE INDICADORES TÉCNICOS AVANÇADOS =====
def calcular_todos_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula dezenas de indicadores técnicos garantindo integridade matemática.
    Corrige o bug de colunas faltantes e divisões por zero.
    """
    try:
        # Médias Móveis Exponenciais (EMAs) Essenciais
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Índice de Força Relativa (RSI 14)
        delta = df['close'].diff()
        ganho = (delta.where(delta > 0, 0.0)).rolling(14).mean()
        perda = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        perda = perda.replace(0, 0.00001)
        rs = ganho / perda
        df['rsi'] = 100 - (100 / (1 + rs))

        # True Range e ATR (Average True Range)
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['close'].shift(1))
        tr3 = abs(df['low'] - df['close'].shift(1))
        df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = df['tr'].rolling(14).mean()

        # Suporte e Resistência de 20 períodos
        df['support'] = df['low'].rolling(20).min()
        df['resistance'] = df['high'].rolling(20).max()

        # MACD (12, 26, 9)
        df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['signal']

        # Bandas de Bollinger (20, 2)
        df['bb_middle'] = df['close'].rolling(20).mean()
        df['bb_std'] = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (2 * df['bb_std'])
        df['bb_lower'] = df['bb_middle'] - (2 * df['bb_std'])

        # On-Balance Volume (OBV)
        obv = [0]
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i-1]:
                obv.append(obv[-1] + df['volume'].iloc[i])
            elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                obv.append(obv[-1] - df['volume'].iloc[i])
            else:
                obv.append(obv[-1])
        df['obv'] = obv

        # Stochastic RSI
        rsi_min = df['rsi'].rolling(14).min()
        rsi_max = df['rsi'].rolling(14).max()
        den = (rsi_max - rsi_min).replace(0, 0.00001)
        df['stoch_k'] = ((df['rsi'] - rsi_min) / den) * 100
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()

        # VWAP (Preço Médio Ponderado por Volume)
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3
        df['vol_tp'] = df['tp'] * df['volume']
        cum_vol_tp = df['vol_tp'].cumsum()
        cum_vol = df['volume'].cumsum().replace(0, 0.00001)
        df['vwap'] = cum_vol_tp / cum_vol

        # SuperTendência (SuperTrend simplificado)
        atr_st = df['atr'].fillna(df['high'] - df['low'])
        hl2 = (df['high'] + df['low']) / 2
        df['upperband'] = hl2 + (2 * atr_st)
        df['lowerband'] = hl2 - (2 * atr_st)
        trend = [1]
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['upperband'].iloc[i-1]:
                trend.append(1)
            elif df['close'].iloc[i] < df['lowerband'].iloc[i-1]:
                trend.append(-1)
            else:
                trend.append(trend[-1])
        df['trend'] = trend

        # Canais de Donchian (20)
        df['dc_upper'] = df['high'].rolling(20).max()
        df['dc_lower'] = df['low'].rolling(20).min()
        df['dc_middle'] = (df['dc_upper'] + df['dc_lower']) / 2

        # Canais de Keltner
        df['kc_middle'] = df['ema_20']
        df['kc_upper'] = df['kc_middle'] + (2 * atr_st)
        df['kc_lower'] = df['kc_middle'] - (2 * atr_st)

        # Awesome Oscillator (AO)
        df['ao'] = ((df['high'].rolling(5).mean() + df['low'].rolling(5).mean()) / 2) - \
                   ((df['high'].rolling(34).mean() + df['low'].rolling(34).mean()) / 2)

        # CCI (Commodity Channel Index)
        tp_mean = df['tp'].rolling(20).mean()
        tp_std = df['tp'].rolling(20).std().replace(0, 0.00001)
        df['cci'] = (df['tp'] - tp_mean) / (0.015 * tp_std)

        # Chaikin Money Flow (CMF)
        hl_diff = (df['high'] - df['low']).replace(0, 0.00001)
        df['mf_mult'] = ((df['close'] - df['low']) - (df['high'] - df['close'])) / hl_diff
        df['mf_vol'] = df['mf_mult'] * df['volume']
        vol_sum = df['volume'].rolling(20).sum().replace(0, 0.00001)
        df['cmf'] = df['mf_vol'].rolling(20).sum() / vol_sum

        return df
    except Exception as e:
        st.error(f"Aviso ao calcular indicadores: {e}")
        return df

# ===== GRÁFICO INTERATIVO COM PLOTLY =====
def criar_grafico_interativo(df: pd.DataFrame, simbolo: str, timeframe: str, tp_list=None, sl=None):
    """
    Gera um gráfico Candlestick profissional e interativo com Plotly:
    - Velas japonesas (verde para alta, vermelho para baixa)
    - EMAs 9, 21, 50, 200
    - Bandas de Bollinger
    - Linhas de Alvos de Lucro (TP1, TP2) e Limite de Perda (Stop Loss)
    - Painel inferior de Volume
    """
    # Formata timestamps para datas legíveis
    if 'timestamp' in df.columns:
        datas = pd.to_datetime(df['timestamp'], unit='ms')
    else:
        datas = df.index

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.75, 0.25],
        subplot_titles=(f"📈 Cotação {simbolo} ({timeframe}) - Velas e Médias", "📊 Volume Negociado")
    )

    # 1. Velas Candlestick
    fig.add_trace(
        go.Candlestick(
            x=datas,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="Preço",
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ),
        row=1, col=1
    )

    # 2. Médias Móveis
    if 'ema_9' in df.columns:
        fig.add_trace(go.Scatter(x=datas, y=df['ema_9'], line=dict(color='#2196f3', width=1.5), name="EMA 9 (Curto Prazo)"), row=1, col=1)
    if 'ema_21' in df.columns:
        fig.add_trace(go.Scatter(x=datas, y=df['ema_21'], line=dict(color='#ff9800', width=1.5), name="EMA 21 (Médio Prazo)"), row=1, col=1)
    if 'ema_50' in df.columns:
        fig.add_trace(go.Scatter(x=datas, y=df['ema_50'], line=dict(color='#9c27b0', width=1.5), name="EMA 50"), row=1, col=1)
    if 'ema_200' in df.columns:
        fig.add_trace(go.Scatter(x=datas, y=df['ema_200'], line=dict(color='#e91e63', width=2), name="EMA 200 (Tendência Macro)"), row=1, col=1)

    # 3. Bandas de Bollinger
    if 'bb_upper' in df.columns and 'bb_lower' in df.columns:
        fig.add_trace(go.Scatter(x=datas, y=df['bb_upper'], line=dict(color='rgba(150, 150, 150, 0.3)', dash='dash'), name="Bollinger Superior", showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=datas, y=df['bb_lower'], line=dict(color='rgba(150, 150, 150, 0.3)', dash='dash'), fill='tonexty', fillcolor='rgba(100, 100, 100, 0.05)', name="Bandas de Bollinger"), row=1, col=1)

    # 4. Linhas de Alvos (TP) e Stop Loss
    if tp_list and len(tp_list) >= 2:
        fig.add_hline(y=tp_list[0], line_dash="dash", line_color="#26a69a", annotation_text="🎯 Alvo 1 (TP1)", annotation_position="top right", row=1, col=1)
        fig.add_hline(y=tp_list[1], line_dash="dot", line_color="#00e676", annotation_text="🎯 Alvo 2 (TP2)", annotation_position="top right", row=1, col=1)
    if sl:
        fig.add_hline(y=sl, line_dash="dash", line_color="#ef5350", annotation_text="🛑 Limite de Perda (Stop Loss)", annotation_position="bottom right", row=1, col=1)

    # 5. Barras de Volume
    cores_volume = ['#26a69a' if c >= o else '#ef5350' for c, o in zip(df['close'], df['open'])]
    fig.add_trace(
        go.Bar(
            x=datas,
            y=df['volume'],
            marker_color=cores_volume,
            name="Volume"
        ),
        row=2, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        height=650,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig

# ===== INTELIGÊNCIA ARTIFICIAL (GEMINI E HUGGING FACE) =====
def consultar_ia_chat(prompt: str) -> str:
    """
    Envia pergunta para IA com fallback inteligente:
    1º Tenta Google Gemini (mais avançado e rápido)
    2º Caso falhe ou não tenha chave, tenta os 7 modelos do Hugging Face
    """
    # 1. Tentativa via Google Gemini
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            prompt_contexto = (
                "Você é a Mariana, uma assistente profissional de trading institucional e gestão de risco em criptomoedas. "
                "Responda sempre em Português do Brasil de forma clara, técnica, objetiva e amigável.\n\n"
                f"Pergunta do usuário: {prompt}"
            )
            # Tenta com o modelo atual
            for modelo_gemini in ['gemini-3.6-flash', 'gemini-2.5-flash']:
                try:
                    res = client.models.generate_content(model=modelo_gemini, contents=prompt_contexto)
                    if res and res.text:
                        return res.text
                except Exception:
                    continue
        except Exception:
            pass

    # 2. Fallback via Hugging Face Router
    hf_token = os.getenv('HF_TOKEN', '').strip()
    modelos_hf = [
        "Qwen/Qwen2.5-7B-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.2",
        "google/gemma-2-9b-it",
        "HuggingFaceH4/zephyr-7b-beta",
        "Qwen/Qwen2.5-Coder-7B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct"
    ]
    
    for modelo in modelos_hf:
        try:
            headers = {"Authorization": f"Bearer {hf_token}", "Content-Type": "application/json"}
            payload = {
                "model": modelo,
                "messages": [
                    {"role": "system", "content": "Você é a assistente Mariana de trading de criptomoedas. Responda em Português do Brasil com foco em análise técnica e risco."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 400
            }
            req = requests.post("https://router.huggingface.co/v1/chat/completions", headers=headers, json=payload, timeout=20)
            resultado = req.json()
            if 'choices' in resultado and resultado['choices']:
                return resultado['choices'][0]['message']['content']
        except Exception:
            continue

    return "⚠️ Desculpe, não consegui conectar aos provedores de inteligência artificial no momento. Verifique a chave GEMINI_API_KEY ou HF_TOKEN no arquivo .env."

def analisar_imagem_grafico(imagem_pil: Image.Image) -> str:
    """
    Analisa um print de gráfico financeiro usando visão computacional do Google Gemini.
    """
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not gemini_key:
        return "⚠️ Chave GEMINI_API_KEY não encontrada no arquivo .env. Por favor, adicione sua chave para ativar a análise visual com inteligência artificial."

    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
        prompt_instrucao = (
            "Você é a Mariana, analista técnica sênior de criptoativos. Analise a imagem deste gráfico e forneça um relatório institucional em Português do Brasil estruturado em:\n"
            "1. 🔍 **Identificação:** Ativo, tempo gráfico e contexto macro aparente.\n"
            "2. 📊 **Price Action e Tendência:** Tendência atual (alta/baixa/lateral), topos e fundos.\n"
            "3. 🧱 **Zonas Chave:** Níveis de Suporte e Resistência relevantes identificados.\n"
            "4. 📐 **Padrões Técnicos:** Figuras gráficas (ex: OCO, triângulos, bandeiras, rejeições de velas).\n"
            "5. 🎯 **Estratégia Recomendada:** Cenário provável, ponto de entrada sugerido, alvo de lucro (TP) e proteção (Stop Loss).\n"
            "Seja direto, profissional e priorize a gestão de risco."
        )
        
        for modelo_gemini in ['gemini-3.6-flash', 'gemini-2.5-flash']:
            try:
                res = client.models.generate_content(
                    model=modelo_gemini,
                    contents=[imagem_pil, prompt_instrucao]
                )
                if res and res.text:
                    return res.text
            except Exception:
                continue
                
        return "❌ Não foi possível obter resposta dos modelos de visão. Tente novamente em instantes."
    except Exception as e:
        return f"❌ Erro ao processar análise da imagem: {e}"

# ===== INTERFACE: AUTENTICAÇÃO LATERAL =====
st.sidebar.title("🔐 Acesso ao Painel")

if 'logado' not in st.session_state:
    st.session_state['logado'] = False
    st.session_state['email'] = ""
    st.session_state['nome'] = ""
    st.session_state['role'] = "membro"

if not st.session_state['logado']:
    modo_acesso = st.sidebar.radio("Escolha a opção:", ["🔑 Entrar", "📝 Criar Nova Conta"])
    
    if modo_acesso == "🔑 Entrar":
        email_login = st.sidebar.text_input("E-mail para Login")
        senha_login = st.sidebar.text_input("Senha", type="password")
        
        if st.sidebar.button("🚀 Entrar no Sistema"):
            if not email_login or not senha_login:
                st.sidebar.error("Preencha e-mail e senha.")
            else:
                ok, nome_usuario, perfil, msg = autenticar_usuario_banco(email_login, senha_login)
                if ok:
                    st.session_state['logado'] = True
                    st.session_state['email'] = email_login
                    st.session_state['nome'] = nome_usuario
                    st.session_state['role'] = perfil
                    registrar_acao(email_login, nome_usuario, "LOGIN", "Entrou no painel institucional", "Acesso")
                    st.sidebar.success(f"✅ Bem-vindo(a), {nome_usuario}!")
                    st.rerun()
                else:
                    st.sidebar.error(f"❌ {msg}")
                    
    elif modo_acesso == "📝 Criar Nova Conta":
        nome_novo = st.sidebar.text_input("Seu Nome Completo")
        email_novo = st.sidebar.text_input("Seu E-mail")
        senha_nova = st.sidebar.text_input("Crie uma Senha Segura", type="password")
        senha_confirma = st.sidebar.text_input("Confirme a Senha", type="password")
        
        if st.sidebar.button("✨ Cadastrar Conta"):
            if senha_nova != senha_confirma:
                st.sidebar.error("❌ As senhas não conferem.")
            elif len(senha_nova) < 6:
                st.sidebar.warning("A senha deve conter pelo menos 6 caracteres.")
            else:
                ok, msg = cadastrar_usuario_banco(email_novo, nome_novo, senha_nova)
                if ok:
                    st.sidebar.success(f"✅ {msg}")
                    registrar_acao(email_novo, nome_novo, "CADASTRO", "Criou conta no sistema", "Cadastro")
                else:
                    st.sidebar.error(f"❌ {msg}")

else:
    st.sidebar.success(f"👤 Conectado: **{st.session_state['nome']}**")
    st.sidebar.caption(f"Perfil: `{st.session_state['role'].upper()}` | {st.session_state['email']}")
    if st.sidebar.button("🚪 Sair da Conta"):
        registrar_acao(st.session_state['email'], st.session_state['nome'], "LOGOUT", "Encerrou a sessão", "Menu")
        st.session_state['logado'] = False
        st.session_state['email'] = ""
        st.session_state['nome'] = ""
        st.rerun()

# ===== ÁREA PRINCIPAL DO DASHBOARD =====
if st.session_state['logado']:
    email_atual = st.session_state['email']
    nome_atual = st.session_state['nome']
    
    st.title("🚀 MARIANA BOT - PAINEL INSTITUCIONAL")
    st.caption("Sistema Avançado de Análise Técnica, Monitoramento e Gestão de Risco para Criptoativos")
    st.markdown("---")
    
    # Navegação por Menu
    st.sidebar.markdown("---")
    st.sidebar.title("📊 Navegação")
    menu_selecionado = st.sidebar.radio(
        "Selecione uma seção:",
        [
            "🤖 Análise Técnica Privada",
            "📊 Posições Abertas (BingX)",
            "📸 Análise de Imagem (IA)",
            "💬 Assistente com IA",
            "📈 Histórico de Análises",
            "📋 Registros de Auditoria",
            "👥 Gestão de Usuários (Admin)"
        ]
    )

    # -------------------------------------------------------------
    # SEÇÃO 1: ANÁLISE TÉCNICA PRIVADA
    # -------------------------------------------------------------
    if menu_selecionado == "🤖 Análise Técnica Privada":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Análise Técnica Privada", "Análise")
        st.header("🤖 Análise Técnica Automatizada com Indicadores")
        st.write("Digite o par desejado e escolha o tempo gráfico para receber uma leitura institucional completa com gráfico interativo e projeções de alvo.")

        with st.form("form_analise_tecnica"):
            col_par, col_tf, col_botao = st.columns([3, 2, 2])
            with col_par:
                simbolo_input = st.text_input("Par de Negociação (ex: BTC, ETH, SOL, SUI)", value="BTC").upper().strip()
            with col_tf:
                timeframe_selecionado = st.selectbox(
                    "Tempo Gráfico",
                    ["15m", "30m", "1h", "4h", "12h", "1d"],
                    index=2
                )
            with col_botao:
                st.write("")
                st.write("")
                executar_analise = st.form_submit_button("🔍 Executar Análise Completa")

        if executar_analise:
            simbolo_formatado = f"{simbolo_input}/USDT"
            with st.spinner(f"Processando cotações e calculando dezenas de indicadores para {simbolo_formatado}..."):
                ohlcv = fetch_ohlcv(simbolo_formatado, timeframe_selecionado, limit=300)
                
                if not ohlcv or len(ohlcv) < 50:
                    st.error(f"❌ Não foi possível carregar os dados para o par **{simbolo_formatado}**. Verifique se o ativo está listado na corretora.")
                else:
                    # Constrói o DataFrame e calcula indicadores
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df = calcular_todos_indicadores(df)

                    ticker = fetch_ticker(simbolo_formatado)
                    preco_atual = safe_float(ticker.get('last'), safe_float(df['close'].iloc[-1]))
                    rsi_atual = safe_float(df['rsi'].iloc[-1], 50.0)
                    atr_atual = safe_float(df['atr'].iloc[-1], preco_atual * 0.01)

                    # Tendência baseada no alinhamento das médias móveis
                    ema_9 = df['ema_9'].iloc[-1]
                    ema_21 = df['ema_21'].iloc[-1]
                    ema_50 = df['ema_50'].iloc[-1]
                    ema_20 = df['ema_20'].iloc[-1]
                    ema_200 = df['ema_200'].iloc[-1]

                    if ema_9 > ema_21 and ema_21 > ema_50:
                        tendencia = "🟢 TENDÊNCIA DE ALTA"
                        cor_tendencia = "status-alta"
                    elif ema_9 < ema_21 and ema_21 < ema_50:
                        tendencia = "🔴 TENDÊNCIA DE BAIXA"
                        cor_tendencia = "status-baixa"
                    else:
                        tendencia = "🟡 ZONA LATERAL / NEUTRA"
                        cor_tendencia = "status-neutro"

                    # Status da Faixa de Suporte do Mercado de Alta (BMSB)
                    if preco_atual > ema_20 and preco_atual > ema_200:
                        bmsb_status = "🟢 SUPORTE CONFIRMADO (Acima das Médias 20 e 200)"
                    elif preco_atual < ema_20 and preco_atual < ema_200:
                        bmsb_status = "🔴 RESISTÊNCIA FORTE (Abaixo das Médias 20 e 200)"
                    else:
                        bmsb_status = "🟡 ZONA DE TRANSIÇÃO (Entre Médias 20 e 200)"

                    # Canal Gaussiano / Bollinger
                    bb_sup = safe_float(df['bb_upper'].iloc[-1])
                    bb_inf = safe_float(df['bb_lower'].iloc[-1])
                    if preco_atual > bb_sup:
                        momento_status = "🟢 FORÇA COMPRADORA (Rompendo Banda Superior)"
                    elif preco_atual < bb_inf:
                        momento_status = "🔴 FORÇA VENDEDORA (Abaixo da Banda Inferior)"
                    else:
                        momento_status = "🟡 CANAL DENTRO DA NORMALIDADE"

                    # Cálculo de Alvos de Lucro (TP 1 a 10) e Limite de Perda (Stop Loss)
                    if "ALTA" in tendencia:
                        tp_list = [preco_atual + (atr_atual * i * 0.6) for i in range(1, 11)]
                        stop_loss = preco_atual - (atr_atual * 2.0)
                        risco = preco_atual - stop_loss
                        ganho_tp1 = tp_list[0] - preco_atual
                        rr = (ganho_tp1 / risco) if risco > 0 else 1.0
                    else:
                        tp_list = [preco_atual - (atr_atual * i * 0.6) for i in range(1, 11)]
                        stop_loss = preco_atual + (atr_atual * 2.0)
                        risco = stop_loss - preco_atual
                        ganho_tp1 = preco_atual - tp_list[0]
                        rr = (ganho_tp1 / risco) if risco > 0 else 1.0

                    # Pontuação Institucional (Score 0 a 100)
                    pontuacao = 50
                    if "ALTA" in tendencia:
                        pontuacao += 20
                    elif "BAIXA" in tendencia:
                        pontuacao -= 20
                    if rsi_atual > 70:
                        pontuacao -= 15  # Sobrecompra
                    elif rsi_atual < 30:
                        pontuacao += 15  # Sobrevenda
                    elif 45 <= rsi_atual <= 60:
                        pontuacao += 5

                    if preco_atual > ema_200:
                        pontuacao += 10
                    else:
                        pontuacao -= 10

                    pontuacao = max(0, min(100, int(pontuacao)))
                    confianca = int(abs(pontuacao - 50) * 2)

                    # Dados de Derivativos e Sentimento
                    taxa_financiamento = 0.0
                    contratos_abertos = 0.0
                    try:
                        ex = get_exchange()
                        if ex:
                            fr = ex.fetch_funding_rate(simbolo_formatado)
                            taxa_financiamento = safe_float(fr.get('fundingRate'), 0.0)
                            oi = ex.fetch_open_interest(simbolo_formatado)
                            contratos_abertos = safe_float(oi.get('openInterestAmount'), 0.0)
                    except Exception:
                        pass

                    indice_fng = get_fear_greed_index()
                    dados_baleia = get_whale_activity(simbolo_formatado)

                    st.success(f"✅ Análise concluída com sucesso para **{simbolo_formatado}**!")

                    # Exibição das Principais Métricas
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.metric("💰 Preço Atual", f"${preco_atual:,.4f}".replace(",", "v").replace(".", ",").replace("v", "."))
                    with c2:
                        st.metric("📊 Força Relativa (RSI)", f"{rsi_atual:.1f}")
                    with c3:
                        st.metric("🏆 Pontuação Institucional", f"{pontuacao} / 100")
                    with c4:
                        st.metric("🎯 Nível de Confiança", f"{confianca}%")

                    st.markdown(f"### Direção Principal: <span class='{cor_tendencia}'>{tendencia}</span>", unsafe_allow_html=True)
                    st.write(f"**Estrutura de Médias:** {bmsb_status}")
                    st.write(f"**Dinâmica de Bandas:** {momento_status}")

                    # GRÁFICO INTERATIVO COM CANDLESTICKS E MÉDIAS
                    st.subheader("📈 Gráfico Interativo com Velas e Alvos")
                    figura = criar_grafico_interativo(df, simbolo_formatado, timeframe_selecionado, tp_list, stop_loss)
                    st.plotly_chart(figura, use_container_width=True)

                    # ALVOS DE LUCRO E GERENCIAMENTO DE RISCO
                    st.subheader("🎯 Plano de Operação e Alvos de Lucro")
                    col_alvos, col_risco = st.columns([3, 2])
                    
                    with col_alvos:
                        st.write("Projeções de Saída Parcial:")
                        dados_tp = []
                        for i, tp in enumerate(tp_list, start=1):
                            pct = ((tp - preco_atual) / preco_atual) * 100 if "ALTA" in tendencia else ((preco_atual - tp) / preco_atual) * 100
                            dados_tp.append({
                                "Nível de Alvo": f"Alvo {i} (TP{i})",
                                "Preço Alvo ($)": f"${tp:.4f}",
                                "Ganho Estimado (%)": f"{pct:+.2f}%"
                            })
                        st.dataframe(pd.DataFrame(dados_tp), use_container_width=True, hide_index=True)

                    with col_risco:
                        st.markdown("#### 🛡️ Gerenciamento de Risco")
                        st.write(f"🛑 **Limite de Perda (Stop Loss):** `${stop_loss:.4f}`")
                        st.write(f"⚖️ **Relação Risco x Retorno (R:R):** `{rr:.2f}x`")
                        st.write(f"📏 **Volatilidade Média (ATR 14):** `${atr_atual:.4f}`")
                        st.info("💡 **Recomendação Institucional:** Nunca arrisque mais do que 1% a 2% do seu capital total em uma única operação.")

                    # PAINEL DE INDICADORES AVANÇADOS
                    st.subheader("📊 Indicadores Avançados e Derivativos")
                    c_ind1, c_ind2, c_ind3 = st.columns(3)
                    with c_ind1:
                        st.metric("MACD (Histograma)", f"{safe_float(df['macd_hist'].iloc[-1]):.4f}")
                        st.metric("Volume Ponderado (VWAP)", f"${safe_float(df['vwap'].iloc[-1]):.2f}")
                        st.metric("Canal de Donchian Superior", f"${safe_float(df['dc_upper'].iloc[-1]):.2f}")
                    with c_ind2:
                        st.metric("SuperTendência", "🟢 COMPRA" if df['trend'].iloc[-1] == 1 else "🔴 VENDA")
                        st.metric("Estocástico K / D", f"{safe_float(df['stoch_k'].iloc[-1]):.1f} / {safe_float(df['stoch_d'].iloc[-1]):.1f}")
                        st.metric("Canal de Donchian Inferior", f"${safe_float(df['dc_lower'].iloc[-1]):.2f}")
                    with c_ind3:
                        st.metric("Taxa de Financiamento (Funding)", f"{taxa_financiamento * 100:.4f}%")
                        st.metric("Contratos em Aberto (OI)", f"{contratos_abertos:,.0f}")
                        st.metric("Índice Medo e Ganância", f"{indice_fng} / 100")

                    # Atividade de Grandes Carteiras
                    if dados_baleia:
                        st.subheader("🐋 Movimentação de Grandes Carteiras (Baleias)")
                        c_w1, c_w2 = st.columns(2)
                        with c_w1:
                            st.metric("Volume Global em 24h", f"${dados_baleia.get('volume_24h', 0):,.2f}")
                        with c_w2:
                            st.metric("Variação de Preço em 24h", f"{dados_baleia.get('variacao_24h', 0):+.2f}%")

                    # Salva no histórico de análises
                    salvar_analise(simbolo_formatado, "Técnica", f"Score: {pontuacao}/100 | Preço: ${preco_atual:.4f}", confianca, tendencia, email_atual)

                    # Disparo opcional para Telegram
                    if st.button("📢 Enviar Resumo da Análise para o Telegram"):
                        msg_telegram = (
                            f"🚀 <b>MARIANA BOT - SINAL INSTITUCIONAL</b>\n\n"
                            f"📌 <b>Ativo:</b> {simbolo_formatado} ({timeframe_selecionado})\n"
                            f"💰 <b>Preço:</b> ${preco_atual:.4f}\n"
                            f"🧭 <b>Tendência:</b> {tendencia}\n"
                            f"🏆 <b>Pontuação:</b> {pontuacao}/100 (Confiança: {confianca}%)\n\n"
                            f"🎯 <b>Alvo 1:</b> ${tp_list[0]:.4f}\n"
                            f"🎯 <b>Alvo 2:</b> ${tp_list[1]:.4f}\n"
                            f"🛑 <b>Stop Loss:</b> ${stop_loss:.4f}\n"
                            f"⚖️ <b>R:R:</b> {rr:.2f}x\n"
                        )
                        if enviar_telegram(msg_telegram):
                            st.success("✅ Sinal enviado com sucesso para o Telegram!")
                        else:
                            st.warning("⚠️ Não foi possível enviar para o Telegram. Verifique as credenciais no .env.")

    # -------------------------------------------------------------
    # SEÇÃO 2: POSIÇÕES ABERTAS NA BINGX
    # -------------------------------------------------------------
    elif menu_selecionado == "📊 Posições Abertas (BingX)":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Posições Abertas", "Posições")
        st.header("📊 Posições Abertas em Contratos Futuros (BingX)")
        st.write("Consulte as operações ativas na sua conta de swap, com cálculo em tempo real de lucro e prejuízo.")

        if st.button("🔄 Atualizar Posições Agora"):
            exchange = get_exchange()
            if not exchange:
                st.error("❌ Credenciais da BingX não configuradas no arquivo .env. Por favor, adicione BINGX_API_KEY e BINGX_SECRET.")
            else:
                try:
                    with st.spinner("Consultando carteira de contratos perpétuos..."):
                        posicoes = exchange.fetch_positions()
                        if not posicoes:
                            st.info("Nenhuma posição aberta encontrada na corretora no momento.")
                        else:
                            linhas_posicoes = []
                            pnl_acumulado = 0.0
                            
                            for pos in posicoes:
                                contratos = safe_float(pos.get('contracts', 0.0))
                                if contratos <= 0:
                                    continue
                                    
                                simbolo = pos.get('symbol', '')
                                lado = pos.get('side', 'long').upper()
                                entrada = safe_float(pos.get('entryPrice', 0.0))
                                alavancagem = safe_float(pos.get('leverage', 1.0))
                                
                                ticker_pos = fetch_ticker(simbolo)
                                preco_mercado = safe_float(ticker_pos.get('last'), entrada) if ticker_pos else entrada
                                
                                raw = pos.get('info', {})
                                pnl = safe_float(raw.get('unRealizedPnl') or raw.get('unrealizedPnl') or raw.get('unrealizedProfit') or pos.get('unrealizedPnl') or 0.0)
                                margem = safe_float(pos.get('initialMargin') or raw.get('initMargin') or 0.0)
                                pnl_pct = (pnl / margem * 100) if margem > 0 else 0.0
                                
                                pnl_acumulado += pnl
                                
                                linhas_posicoes.append({
                                    "Ativo": simbolo,
                                    "Direção": "🟢 COMPRA (LONG)" if lado == "LONG" else "🔴 VENDA (SHORT)",
                                    "Preço de Entrada": f"${entrada:,.4f}",
                                    "Preço de Mercado": f"${preco_mercado:,.4f}",
                                    "Contratos": f"{contratos}",
                                    "Alavancagem": f"{alavancagem:.0f}x",
                                    "Lucro / Prejuízo (USDT)": f"{pnl:+,.2f} USDT",
                                    "Retorno (%)": f"{pnl_pct:+.2f}%"
                                })

                            if linhas_posicoes:
                                df_pos = pd.DataFrame(linhas_posicoes)
                                st.dataframe(df_pos, use_container_width=True, hide_index=True)
                                
                                c_pnl1, c_pnl2 = st.columns(2)
                                with c_pnl1:
                                    cor_pnl = "normal" if pnl_acumulado >= 0 else "inverse"
                                    st.metric("💰 Resultado Total Não Realizado", f"{pnl_acumulado:+,.2f} USDT")
                                with c_pnl2:
                                    st.metric("📋 Total de Operações Ativas", len(linhas_posicoes))
                            else:
                                st.info("Nenhuma posição ativa com contratos em aberto no momento.")
                except Exception as e:
                    st.error(f"❌ Erro ao buscar posições na BingX: {e}")

    # -------------------------------------------------------------
    # SEÇÃO 3: ANÁLISE DE IMAGEM REAL COM IA (GEMINI)
    # -------------------------------------------------------------
    elif menu_selecionado == "📸 Análise de Imagem (IA)":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Análise de Imagem", "Imagem")
        st.header("📸 Leitura e Análise de Gráficos por Inteligência Artificial")
        st.write("Envie uma captura de tela do seu gráfico (TradingView, BingX, Binance, etc.) e nossa inteligência artificial analisará o price action, figuras gráficas e zonas de suporte.")

        arquivo_imagem = st.file_uploader("Envie a imagem do gráfico (formatos PNG, JPG ou JPEG):", type=["png", "jpg", "jpeg"])
        
        if arquivo_imagem is not None:
            imagem_pil = Image.open(arquivo_imagem)
            st.image(imagem_pil, caption="Gráfico Carregado", use_container_width=True)
            
            if st.button("🧠 Realizar Leitura Técnica da Imagem"):
                with st.spinner("Analisando padrões visuais, suporte, resistência e momento com inteligência artificial..."):
                    resposta_visao = analisar_imagem_grafico(imagem_pil)
                    st.markdown("### 📋 Parecer Técnico Institucional:")
                    st.markdown(resposta_visao)
                    salvar_analise("GRÁFICO VISUAL", "Imagem", resposta_visao[:150] + "...", 70, "Visual", email_atual)

    # -------------------------------------------------------------
    # SEÇÃO 4: CHAT ESPECIALIZADO COM IA
    # -------------------------------------------------------------
    elif menu_selecionado == "💬 Assistente com IA":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Assistente com IA", "Chat")
        st.header("💬 Assistente Especializado em Mercado Financeiro")
        st.write("Tire dúvidas sobre indicadores, gestão de risco, estratégias de trading e correlações de mercado.")

        if 'historico_chat' not in st.session_state:
            st.session_state['historico_chat'] = [
                {"role": "assistant", "content": "Olá! Eu sou a Mariana, sua analista de inteligência artificial. Como posso ajudar nas suas operações hoje?"}
            ]

        # Exibe mensagens anteriores
        for msg in st.session_state['historico_chat']:
            with st.chat_message(msg['role']):
                st.write(msg['content'])

        pergunta_usuario = st.chat_input("Ex: Qual o melhor momento para entrar a favor da tendência?")
        if pergunta_usuario:
            st.session_state['historico_chat'].append({"role": "user", "content": pergunta_usuario})
            with st.chat_message("user"):
                st.write(pergunta_usuario)

            with st.chat_message("assistant"):
                with st.spinner("Consultando modelos de inteligência artificial..."):
                    resposta_ia = consultar_ia_chat(pergunta_usuario)
                    st.write(resposta_ia)
                    st.session_state['historico_chat'].append({"role": "assistant", "content": resposta_ia})
                    registrar_acao(email_atual, nome_atual, "CHAT IA", pergunta_usuario[:60], "Assistente")

    # -------------------------------------------------------------
    # SEÇÃO 5: HISTÓRICO DE ANÁLISES
    # -------------------------------------------------------------
    elif menu_selecionado == "📈 Histórico de Análises":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Histórico de Análises", "Histórico")
        st.header("📈 Histórico de Análises Realizadas")
        st.write("Veja todas as avaliações e sinais gerados recentemente pela plataforma.")
        df_hist = carregar_historico()
        if df_hist.empty:
            st.info("Nenhuma análise salva no histórico até o momento.")
        else:
            st.dataframe(df_hist, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------
    # SEÇÃO 6: REGISTROS DE AUDITORIA
    # -------------------------------------------------------------
    elif menu_selecionado == "📋 Registros de Auditoria":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Registros de Auditoria", "Auditoria")
        st.header("📋 Registros de Atividades e Auditoria")
        st.write("Relatório de ações executadas pelos usuários dentro da plataforma.")
        
        df_reg = carregar_registros()
        if df_reg.empty:
            st.info("Nenhum registro de atividade encontrado.")
        else:
            st.dataframe(df_reg, use_container_width=True, hide_index=True)
            
            # Opção para o Administrador limpar logs
            st.markdown("---")
            senha_limpeza = st.text_input("Digite a Senha de Administrador para apagar os registros:", type="password", key="senha_limpar_logs")
            if st.button("🗑️ Limpar Todos os Registros de Auditoria"):
                if senha_limpeza == ADMIN_SENHA:
                    apagar_todos_registros()
                    st.success("✅ Todos os registros de auditoria foram excluídos com sucesso.")
                    st.rerun()
                else:
                    st.error("❌ Senha de Administrador incorreta.")

    # -------------------------------------------------------------
    # SEÇÃO 7: GESTÃO DE USUÁRIOS (ADMINISTRADOR)
    # -------------------------------------------------------------
    elif menu_selecionado == "👥 Gestão de Usuários (Admin)":
        registrar_acao(email_atual, nome_atual, "NAVEGAÇÃO", "Acessou Área Administrativa", "Admin")
        st.header("👥 Painel de Gestão de Usuários")
        
        senha_admin_digitada = st.text_input("Digite a Senha de Administrador para desbloquear o gerenciamento:", type="password")
        
        if senha_admin_digitada == ADMIN_SENHA:
            st.success("🔓 Modo Administrador ativado com sucesso.")
            df_usuarios = listar_usuarios()
            if df_usuarios.empty:
                st.info("Nenhum usuário cadastrado.")
            else:
                st.dataframe(df_usuarios, use_container_width=True, hide_index=True)
                
                st.subheader("Excluir Conta de Usuário")
                lista_emails = df_usuarios['E-mail'].tolist()
                email_para_remover = st.selectbox("Selecione o e-mail do usuário:", lista_emails)
                
                if st.button("⚠️ Confirmar Exclusão de Usuário"):
                    if email_para_remover == email_atual:
                        st.warning("Você não pode excluir sua própria conta enquanto estiver conectado nela.")
                    else:
                        excluir_usuario(email_para_remover)
                        registrar_acao(email_atual, nome_atual, "ADMIN", f"Excluiu usuário {email_para_remover}", "Admin")
                        st.success(f"✅ Usuário {email_para_remover} removido com sucesso!")
                        st.rerun()
        elif senha_admin_digitada:
            st.error("❌ Senha de Administrador incorreta.")

    st.markdown("---")
    st.caption(f"🚀 Mariana Bot v12.0 - Painel Institucional | Horário do Sistema: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

else:
    # Tela quando não logado
    st.title("🔐 Mariana Bot - Painel Institucional")
    st.write("Bem-vindo(a) à plataforma de análise e monitoramento de mercado financeiro.")
    st.info("👉 Por favor, utilize o menu lateral esquerdo para **Entrar** ou **Criar sua Nova Conta**.")

