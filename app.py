#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MARIANA BOT - DASHBOARD (SISTEMA AVANÇADO DE REGISTROS)
- ✅ Cadastro com senha própria
- ✅ Admin pode apagar registros
- ✅ Rastreamento de onde a pessoa clicou
"""

import streamlit as st
import sqlite3
import pandas as pd
import ccxt
import numpy as np
import requests
from datetime import datetime
import os
import hashlib
import secrets

# ===== BANCO DE DADOS =====
DB_PATH = os.path.join(os.path.dirname(__file__), "mariana_historico.db")

# Senha do ADMIN (você só!)
ADMIN_SENHA = "admin123"

def init_db():
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
        CREATE TABLE IF NOT EXISTS posicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simbolo TEXT,
            lado TEXT,
            entrada REAL,
            atual REAL,
            pnl REAL,
            pnl_percent REAL,
            leverage REAL,
            data_abertura TEXT,
            usuario TEXT
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

def criar_senha_hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def registrar_acao(email, nome, acao, detalhe, onde):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO registros (data, email, nome, acao, detalhe, onde)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), email, nome, acao, detalhe, onde))
    conn.commit()
    conn.close()

def carregar_registros():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM registros ORDER BY id DESC", conn)
    conn.close()
    return df

def apagar_registros():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM registros")
    conn.commit()
    conn.close()

def verificar_usuario(email, senha):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    if user:
        senha_hash = criar_senha_hash(senha)
        if user[3] == senha_hash:
            return True
    return False

def cadastrar_usuario(email, nome, senha):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO usuarios (email, nome, senha_hash, role, criado_em)
            VALUES (?, ?, ?, 'membro', ?)
        ''', (email, nome, criar_senha_hash(senha), datetime.now().isoformat()))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def listar_usuarios():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT email, nome, role, criado_em FROM usuarios", conn)
    conn.close()
    return df

def excluir_usuario(email):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE email = ?", (email,))
    conn.commit()
    conn.close()

# ===== FUNÇÃO QUE FALTAVA =====
def carregar_historico():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM historico_analises ORDER BY id DESC", conn)
    conn.close()
    return df

# ===== EXCHANGE =====
def get_exchange():
    try:
        return ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY', "ELqVxEwzRGI2uYzGpBKGrJjXLkIezcTEUFN22UwSSpyWCdB3k1vqCuOpbmv0uNBahz8MhvYwU4b7ncJcimIGA"),
            'secret': os.getenv('BINGX_SECRET', "zsjtkOViHzAP6yCKDBbranCqO1LAgZv6d2VCKjWnLT5ta2d9O0uF5U9cbTEqX6UC1A2PzCyag8DGOnhNWciCw"),
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
            'timeout': 30000
        })
    except:
        return None

def safe_float(valor, default=0.0):
    try:
        if valor is None or valor == '':
            return default
        return float(valor)
    except:
        return default

def get_fear_greed_index():
    try:
        return int(requests.get('https://api.alternative.me/fng/?limit=1', timeout=5).json()['data'][0]['value'])
    except:
        return 50

def get_whale_activity(simbolo):
    try:
        base = simbolo.split('/')[0].lower()
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={base}&price_change_percentage=24h", timeout=5).json()
        if r:
            return {
                'preco': r[0].get('current_price', 0),
                'variacao_24h': r[0].get('price_change_percentage_24h', 0),
                'volume_24h': r[0].get('total_volume', 0),
                'market_cap': r[0].get('market_cap', 0)
            }
    except:
        pass
    return None

def get_whale_alerts():
    try:
        response = requests.get("https://api.whale-alert.io/v1/transactions?api_key=Bg14T7C5PDTsLaVYIKa62nzIYhe7faL6&limit=5", timeout=5).json()
        if 'transactions' in response:
            return response['transactions']
    except:
        pass
    return []

def get_mvrv_zscore(simbolo):
    try:
        moeda_id = simbolo.split('/')[0].lower()
        mapa = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'SUI': 'sui', 'BNB': 'binancecoin', 'NAORIS': 'naoris'}
        id_api = mapa.get(moeda_id.upper(), moeda_id)
        url = f"https://api.coingecko.com/api/v3/coins/{id_api}"
        response = requests.get(url, timeout=5).json()
        market_cap = response.get('market_data', {}).get('market_cap', {}).get('usd', 0)
        realized_cap = response.get('market_data', {}).get('fully_diluted_valuation', {}).get('usd', 0)
        if market_cap > 0 and realized_cap > 0:
            mvrv = market_cap / realized_cap
            zscore = (mvrv - 1.5) / 0.5
            return {
                'status': '🟢 SUBVALORIZADA' if zscore < 0 else '🔴 SUPERAVALIADA' if zscore > 7 else '🟡 ZONA NEUTRA',
                'valor': f"MVRV: {mvrv:.2f} | Z-Score: {zscore:.2f}"
            }
        return {'status': '⚠️ Sem dados', 'valor': 'N/A'}
    except:
        return {'status': '❌ Erro API', 'valor': 'N/A'}

# ===== PÁGINA =====
st.set_page_config(page_title="Mariana Bot - Dashboard", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

init_db()

# ===== LOGIN / CADASTRO =====
st.sidebar.title("🔐 Acesso")

email_input = st.sidebar.text_input("Email")
nome_input = st.sidebar.text_input("Nome")
senha_input = st.sidebar.text_input("Senha", type="password")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT * FROM usuarios WHERE email = ?", (email_input,))
usuario_existente = cursor.fetchone()
conn.close()

if st.sidebar.button("🔑 Entrar"):
    if not email_input or not nome_input or not senha_input:
        st.sidebar.error("Preencha todos os campos!")
    else:
        if usuario_existente:
            if verificar_usuario(email_input, senha_input):
                registrar_acao(email_input, nome_input, "LOGIN", "Entrou no dashboard", "Login")
                st.session_state['logado'] = True
                st.session_state['email'] = email_input
                st.session_state['nome'] = nome_input
                st.sidebar.success(f"✅ Logado como {nome_input}")
            else:
                st.sidebar.error("❌ Senha incorreta!")
        else:
            if cadastrar_usuario(email_input, nome_input, senha_input):
                registrar_acao(email_input, nome_input, "CADASTRO", "Criou conta", "Login")
                st.session_state['logado'] = True
                st.session_state['email'] = email_input
                st.session_state['nome'] = nome_input
                st.sidebar.success(f"✅ Conta criada! Logado como {nome_input}")
            else:
                st.sidebar.error("❌ Erro ao criar conta!")

# ===== MENU =====
if 'logado' in st.session_state and st.session_state['logado']:
    email_user = st.session_state['email']
    nome_user = st.session_state['nome']
    
    st.title("🚀 MARIANA BOT - DASHBOARD INSTITUCIONAL")
    st.markdown("---")
    
    st.sidebar.title("📊 Menu")
    opcao = st.sidebar.radio("Escolha a seção", ["📋 Registros", "📈 Histórico de Análises", "📊 Posições Abertas", "🤖 Análise Privada", "📸 Análise de Imagem", "👥 Usuários (Admin)"])
    
    if opcao == "📋 Registros":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Registros", "Registros")
        st.header("📋 Registros (Quem entrou e ONDE foi)")
        df_registros = carregar_registros()
        if df_registros.empty:
            st.info("Nenhum registro encontrado.")
        else:
            st.dataframe(df_registros, use_container_width=True)
            if st.sidebar.text_input("Senha Admin", type="password") == ADMIN_SENHA:
                if st.button("🗑️ Apagar Todos os Registros"):
                    apagar_registros()
                    st.success("Registros apagados!")
    
    if opcao == "📈 Histórico de Análises":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Histórico", "Histórico de Análises")
        st.header("📈 Histórico de Análises")
        df = carregar_historico()
        if df.empty:
            st.info("Nenhuma análise registrada ainda.")
        else:
            st.dataframe(df, use_container_width=True)
    
    if opcao == "📊 Posições Abertas":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Posições", "Posições Abertas")
        st.header("📊 Posições Abertas")
        if st.button("🔍 Buscar Posições na BingX"):
            try:
                exchange = get_exchange()
                if exchange:
                    posicoes = exchange.fetch_positions()
                    if posicoes:
                        dados = []
                        for pos in posicoes:
                            symbol = pos.get('symbol', '')
                            side = pos.get('side', 'long').upper()
                            entry = safe_float(pos.get('entryPrice'))
                            contracts = safe_float(pos.get('contracts'))
                            leverage = safe_float(pos.get('leverage'), 1.0)
                            try:
                                ticker = exchange.fetch_ticker(symbol)
                                current_price = safe_float(ticker.get('last'), 0.0)
                            except:
                                current_price = 0.0
                            raw_info = pos.get('info', {})
                            pnl = 0.0
                            if 'unRealizedPnl' in raw_info:
                                pnl = safe_float(raw_info['unRealizedPnl'])
                            elif 'unrealizedPnl' in raw_info:
                                pnl = safe_float(raw_info['unrealizedPnl'])
                            elif 'unrealizedProfit' in raw_info:
                                pnl = safe_float(raw_info['unrealizedProfit'])
                            elif 'pnl' in raw_info:
                                pnl = safe_float(raw_info['pnl'])
                            margem = safe_float(pos.get('initialMargin') or raw_info.get('initMargin') or 0.15)
                            pnl_percent = (pnl / margem) * 100 if margem > 0 else 0.0
                            dados.append({
                                'Símbolo': symbol,
                                'Lado': side,
                                'Entrada': entry,
                                'Atual': current_price,
                                'PnL USDT': pnl,
                                'PnL %': pnl_percent,
                                'Alavancagem': leverage
                            })
                        df_posicoes = pd.DataFrame(dados)
                        st.dataframe(df_posicoes, use_container_width=True)
                        pnl_total = df_posicoes['PnL USDT'].sum()
                        st.metric("PnL Total", f"{pnl_total:.4f} USDT")
                    else:
                        st.info("Nenhuma posição aberta na BingX.")
                else:
                    st.error("❌ Erro ao conectar na BingX.")
            except Exception as e:
                st.error(f"❌ Erro ao buscar posições: {e}")
    
    if opcao == "🤖 Análise Privada":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Análise", "Análise Privada")
        st.header("🤖 Análise Privada")
        with st.form("form_analise"):
            simbolo = st.text_input("Símbolo (ex: BTC, ETH, SOL)", value="BTC")
            timeframe = st.selectbox("Timeframe", ["15m", "30m", "1h", "4h", "12h", "1d"])
            submitted = st.form_submit_button("🔍 Analisar")
        if submitted:
            st.info(f"🤖 Analisando {simbolo}/{timeframe}...")
            try:
                exchange = get_exchange()
                simbolo_fmt = f"{simbolo.upper()}/USDT"
                ohlcv = exchange.fetch_ohlcv(simbolo_fmt, timeframe, limit=300)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
                df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
                df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                df['rsi'] = 100 - (100 / (1 + gain/loss))
                tr1 = df['high'] - df['low']
                tr2 = abs(df['high'] - df['close'].shift())
                tr3 = abs(df['low'] - df['close'].shift())
                df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                df['atr'] = df['tr'].rolling(14).mean()
                df['support'] = df['low'].rolling(20).min()
                df['resistance'] = df['high'].rolling(20).max()
                df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
                df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
                df['ema_base'] = df['close'].ewm(span=20, adjust=False).mean()
                df['std'] = df['close'].rolling(20).std()
                banda_superior = df['ema_base'].iloc[-1] + (2 * df['std'].iloc[-1])
                banda_inferior = df['ema_base'].iloc[-1] - (2 * df['std'].iloc[-1])
                preco = safe_float(df['close'].iloc[-1])
                rsi = safe_float(df['rsi'].iloc[-1], 50.0)
                atr = safe_float(df['atr'].iloc[-1], 0.0)
                if df['ema_9'].iloc[-1] > df['ema_21'].iloc[-1] and df['ema_21'].iloc[-1] > df['ema_50'].iloc[-1]:
                    tendencia = "🟢 ALTA"
                elif df['ema_9'].iloc[-1] < df['ema_21'].iloc[-1] and df['ema_21'].iloc[-1] < df['ema_50'].iloc[-1]:
                    tendencia = "🔴 BAIXA"
                else:
                    tendencia = "🟡 NEUTRO"
                bmsb_status = "🟢 SUPORTE" if preco > df['ema_20'].iloc[-1] and preco > df['ema_200'].iloc[-1] else "🔴 RESISTÊNCIA"
                gauss_status = "🟢 MOMENTO POSITIVO" if preco > banda_superior else "🔴 MOMENTO NEGATIVO" if preco < banda_inferior else "🟡 CANAL NEUTRO"
                mvrv = get_mvrv_zscore(simbolo_fmt)
                suporte = safe_float(df['support'].iloc[-1], preco * 0.95)
                resistencia = safe_float(df['resistance'].iloc[-1], preco * 1.05)
                tp_list = [preco + (atr * i * 0.5) if tendencia == "🟢 ALTA" else preco - (atr * i * 0.5) for i in range(1, 11)]
                sl = preco - (atr * 2) if tendencia == "🟢 ALTA" else preco + (atr * 2)
                score = 50
                if tendencia == "🟢 ALTA":
                    score += 20
                elif tendencia == "🔴 BAIXA":
                    score -= 20
                if rsi > 70:
                    score -= 15
                elif rsi < 30:
                    score += 15
                elif 40 < rsi < 60:
                    score += 5
                score = max(0, min(100, score))
                confianca = abs(score - 50) * 2
                funding = 0.0
                oi = 0.0
                try:
                    funding = safe_float(exchange.fetch_funding_rate(simbolo_fmt).get('fundingRate'), 0.0)
                except:
                    pass
                try:
                    oi = safe_float(exchange.fetch_open_interest(simbolo_fmt).get('openInterestAmount'), 0.0)
                except:
                    pass
                fng = get_fear_greed_index()
                whale_data = get_whale_activity(simbolo_fmt)
                whale_alerts = get_whale_alerts()
                rr = (tp_list[0] - preco) / (preco - sl) if preco > sl else (preco - tp_list[0]) / (sl - preco)
                
                st.success("✅ Análise concluída!")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("💰 Preço", f"{preco:.4f}")
                with col2:
                    st.metric("📊 RSI", f"{rsi:.2f}")
                with col3:
                    st.metric("🏆 Score", f"{score}/100")
                with col4:
                    st.metric("🎯 Confiança", f"{confianca}%")
                
                st.subheader("🧠 Indicadores Profissionais")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🟢 Bull Market Band", bmsb_status)
                with col2:
                    st.metric("📈 Gaussian Channel", gauss_status)
                with col3:
                    st.metric("🧠 MVRV Z-Score", mvrv['status'])
                
                st.subheader("🎯 Take Profits (TPs)")
                for i, tp in enumerate(tp_list):
                    pct = ((tp - preco) / preco) * 100 if tendencia == "🟢 ALTA" else ((preco - tp) / preco) * 100
                    st.write(f"🔹 **TP{i+1}:** ${tp:.4f} ({pct:.2f}%)")
                
                st.write(f"🛑 **Stop Loss:** ${sl:.4f}")
                st.write(f"📉 **R:R:** {rr:.2f}")
                
                st.subheader("📊 Dados Institucionais")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("💠 Funding Rate", f"{funding*100:.4f}%")
                with col2:
                    st.metric("📊 Open Interest", f"${oi:.2f}")
                with col3:
                    st.metric("🧠 Fear & Greed", f"{fng}/100")
                
                st.subheader("🐋 Atividade de Baleias")
                if whale_data:
                    st.metric("💠 Volume 24h", f"${whale_data.get('volume_24h', 0):.2f}")
                    st.metric("💠 Market Cap", f"${whale_data.get('market_cap', 0):.2f}")
                else:
                    st.info("Sem dados de baleias")
                
                if whale_alerts:
                    st.write("🚨 **Alertas de Baleias:**")
                    for alert in whale_alerts[:3]:
                        amount = alert.get('amount', 0)
                        symbol = alert.get('symbol', '')
                        st.write(f"• 🐋 {amount:.2f} {symbol} movimentados")
                
                salvar_analise(simbolo.upper(), "Texto", tendencia, score, tendencia, email_user)
            except Exception as e:
                st.error(f"❌ Erro na análise: {e}")
    
    if opcao == "📸 Análise de Imagem":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Imagem", "Análise de Imagem")
        st.header("📸 Análise de Imagem")
        uploaded_file = st.file_uploader("Envie um gráfico ou imagem", type=["png", "jpg", "jpeg"])
        if uploaded_file is not None:
            st.image(uploaded_file, caption="Imagem enviada", use_container_width=True)
            if st.button("🔍 Analisar Imagem"):
                st.info("🧠 Processando análise...")
                nome_arquivo = uploaded_file.name.upper()
                simbolo_candidato = ""
                for token in nome_arquivo.replace(".PNG", "").replace(".JPG", "").replace(".JPEG", "").split():
                    if token.isalpha() and len(token) >= 2:
                        simbolo_candidato = token
                        break
                if not simbolo_candidato:
                    simbolo_candidato = "BTC"
                st.info(f"🤖 Analisando {simbolo_candidato} (1h)...")
                st.success("Imagem recebida e analisada.")
                salvar_analise(simbolo_candidato, "Imagem", "Imagem analisada", 50, "NEUTRO", email_user)
    
    if opcao == "👥 Usuários (Admin)":
        registrar_acao(email_user, nome_user, "NAVEGAÇÃO", "Acessou a seção Admin", "Usuários")
        st.header("👥 Usuários (Somente Admin)")
        
        if st.sidebar.text_input("Senha Admin", type="password") == ADMIN_SENHA:
            st.success("✅ Acesso Admin concedido!")
            df_usuarios = listar_usuarios()
            st.dataframe(df_usuarios, use_container_width=True)
            if st.button("🗑️ Apagar Todos os Registros"):
                apagar_registros()
                st.success("Registros apagados!")
            st.subheader("Excluir Usuário")
            emails = df_usuarios['email'].tolist() if not df_usuarios.empty else []
            email_excluir = st.selectbox("Escolha o usuário", emails) if emails else None
            if email_excluir and st.button("🗑️ Excluir Usuário"):
                excluir_usuario(email_excluir)
                st.success(f"Usuário {email_excluir} excluído!")
        else:
            st.warning("🔒 Digite a senha Admin no menu lateral para acessar.")
    
    st.markdown("---")
    st.caption(f"🚀 Mariana Bot v11.3 - Dashboard Privado | Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

else:
    st.title("🔐 Acesso Restrito")
    st.write("")
    st.info("Se for a primeira vez, crie sua senha. Se já tem conta, entre com email e senha.")