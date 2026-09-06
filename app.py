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
