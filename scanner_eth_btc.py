import ccxt
import pandas as pd
import time
import datetime
import requests
import os
import logging
import json
from threading import Thread, Lock, Event
from flask import Flask, request
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

try:
    import pandas_ta as pta
except ImportError:
    raise Exception("Biblioteca pandas_ta não instalada. Execute: pip install pandas_ta")

# ===============================
# === CONFIGURAÇÕES
# ===============================
PARES_ALVOS = ['BTC/USDT', 'ETH/USDT']
timeframe = '4h'
limite_candles = 100
intervalo_em_segundos = 60 * 10  # 10 minutos para monitoramento mais frequente
TEMPO_REENVIO = 60 * 30  # 30 minutos entre alertas do mesmo par

# Configurações do Telegram
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
WEBHOOK_URL = os.getenv("RAILWAY_WEBHOOK_URL") or os.getenv("REPLIT_WEBHOOK_URL")

if not TOKEN or not CHAT_ID:
    print("⚠️ AVISO: Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID para receber alertas")
    print("⚠️ Definindo valores dummy para permitir inicialização...")
    TOKEN = "dummy_token"
    CHAT_ID = "dummy_chat"

# Arquivos de dados
ARQUIVO_SINAIS_MONITORADOS = 'sinais_eth_btc.json'
ARQUIVO_ALERTAS = 'alertas_eth_btc.json'

# Logging
logging.basicConfig(
    filename='scanner_eth_btc.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Controle de threads
lock_alertas = Lock()
scanner_ativo = Event()
alertas_enviados = {}

# ===============================
# === GESTÃO DE SINAIS
# ===============================
def carregar_sinais_monitorados():
    try:
        with open(ARQUIVO_SINAIS_MONITORADOS, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def salvar_sinais_monitorados(sinais):
    with open(ARQUIVO_SINAIS_MONITORADOS, 'w') as f:
        json.dump(sinais, f, indent=2)

def registrar_sinal_monitorado(par, setup_id, preco_entrada, alvo, stop):
    sinais = carregar_sinais_monitorados()
    novo_sinal = {
        "par": par,
        "setup": setup_id,
        "entrada": preco_entrada,
        "alvo": alvo,
        "stop": stop,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "status": "em_aberto"
    }
    sinais.append(novo_sinal)
    salvar_sinais_monitorados(sinais)
    print(f"📝 Sinal registrado: {par} - {setup_id}")

def verificar_sinais_monitorados(exchange):
    sinais = carregar_sinais_monitorados()
    sinais_atualizados = []
    
    for sinal in sinais:
        if sinal['status'] != "em_aberto":
            continue
            
        par = sinal['par']
        try:
            ticker = exchange.fetch_ticker(par)
            preco_atual = ticker['last']
        except Exception as e:
            logging.warning(f"Erro ao buscar preço de {par}: {e}")
            continue
        
        status_anterior = sinal['status']
        
        if preco_atual >= sinal['alvo']:
            sinal['status'] = "🎯 Alvo atingido"
        elif preco_atual <= sinal['stop']:
            sinal['status'] = "🛑 Stop atingido"
        else:
            # Verificar expiração (24 horas)
            dt_alerta = datetime.datetime.fromisoformat(sinal['timestamp'])
            tempo_passado = datetime.datetime.utcnow() - dt_alerta
            if tempo_passado.total_seconds() >= 60 * 60 * 24:
                sinal['status'] = "⏰ Expirado (24h)"
        
        if sinal['status'] != status_anterior:
            sinal['atualizado_em'] = datetime.datetime.utcnow().isoformat()
            sinais_atualizados.append(sinal)
    
    if sinais_atualizados:
        salvar_sinais_monitorados(sinais)
    
    return sinais_atualizados

# ===============================
# === CONTROLE TELEGRAM/FLASK
# ===============================
app = Flask(__name__)

@app.route(f"/{TOKEN}", methods=['POST'])
def receber_mensagem():
    global scanner_ativo
    try:
        msg = request.get_json()
        if 'message' in msg and 'text' in msg['message']:
            texto = msg['message']['text']
            chat_id_msg = msg['message']['chat']['id']
            
            if str(chat_id_msg) != str(CHAT_ID):
                return "Ignorado", 200
            
            if texto == '/start':
                scanner_ativo.set()
                enviar_telegram("✅ *Scanner ETH/BTC ativado!*")
            elif texto == '/stop':
                scanner_ativo.clear()
                enviar_telegram("🛑 *Scanner ETH/BTC pausado!*")
            elif texto == '/status':
                status = "✅ Ativo" if scanner_ativo.is_set() else "⛔ Inativo"
                enviar_telegram(f"📊 *Status Scanner ETH/BTC:* {status}")
            elif texto == '/sinais':
                mostrar_sinais_abertos()
    except Exception as e:
        logging.error(f"Erro no webhook: {e}")
    
    return "OK", 200

def configurar_webhook():
    if TOKEN == "dummy_token" or not WEBHOOK_URL:
        print("⚠️ Webhook não configurado - TOKEN ou WEBHOOK_URL ausentes")
        return
    try:
        endpoint = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
        resposta = requests.post(endpoint, json={"url": f"{WEBHOOK_URL}/{TOKEN}"}, timeout=10)
        if resposta.ok:
            print("✅ Webhook configurado com sucesso!")
            print(f"🔗 Webhook URL: {WEBHOOK_URL}/{TOKEN}")
        else:
            print(f"❌ Erro ao configurar webhook: {resposta.text}")
    except Exception as e:
        print(f"⚠️ Erro ao configurar webhook: {e}")

def iniciar_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def mostrar_sinais_abertos():
    sinais = carregar_sinais_monitorados()
    sinais_abertos = [s for s in sinais if s['status'] == 'em_aberto']
    
    if not sinais_abertos:
        enviar_telegram("📭 *Nenhum sinal em aberto no momento*")
        return
    
    mensagem = f"📊 *{len(sinais_abertos)} sinais em aberto:*\n\n"
    for sinal in sinais_abertos:
        dt = datetime.datetime.fromisoformat(sinal['timestamp'])
        tempo = dt.strftime('%d/%m %H:%M')
        mensagem += (
            f"• *{sinal['par']}* ({sinal['setup']})\n"
            f"  💰 Entrada: {sinal['entrada']}\n"
            f"  🎯 Alvo: {sinal['alvo']} | 🛑 Stop: {sinal['stop']}\n"
            f"  📅 {tempo}\n\n"
        )
    
    enviar_telegram(mensagem)

# ===============================
# === DADOS FUNDAMENTAIS
# ===============================
def obter_dados_fundamentais():
    try:
        # Dados gerais do mercado
        total = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()
        market_data = total.get('data', {})
        
        market_cap = market_data.get('total_market_cap', {}).get('usd')
        market_cap_change = market_data.get('market_cap_change_percentage_24h_usd', 0)
        btc_dominance = market_data.get('market_cap_percentage', {}).get('btc')
        
        if market_cap is None or btc_dominance is None:
            return "*⚠️ Dados fundamentais indisponíveis*"
        
        # Formatação dos valores
        def abreviar_valor(valor):
            if valor >= 1_000_000_000_000:
                return f"${valor/1_000_000_000_000:.2f}T"
            elif valor >= 1_000_000_000:
                return f"${valor/1_000_000_000:.2f}B"
            else:
                return f"${valor/1_000_000:.0f}M"
        
        emoji_cap = "↗️" if market_cap_change >= 0 else "↘️"
        
        # Índice Fear & Greed
        try:
            medo_ganancia = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5).json()
            indice = medo_ganancia['data'][0]
            fear_greed = f"{indice['value']} ({indice['value_classification']})"
        except:
            fear_greed = "Indisponível"
        
        return (
            f"*🌍 MERCADO CRIPTO:*\n"
            f"• Cap. Total: {abreviar_valor(market_cap)} {emoji_cap} ({market_cap_change:+.1f}%)\n"
            f"• Domínio BTC: {btc_dominance:.1f}%\n"
            f"• Fear & Greed: {fear_greed}"
        )
    
    except Exception as e:
        logging.warning(f"Erro ao obter dados fundamentais: {e}")
        return "*⚠️ Dados fundamentais temporariamente indisponíveis*"

# ===============================
# === INDICADORES TÉCNICOS
# ===============================
def calcular_supertrend(df, period=10, multiplier=3):
    try:
        supertrend_data = pta.supertrend(
            high=df['high'], 
            low=df['low'], 
            close=df['close'],
            length=period, 
            multiplier=multiplier
        )
        df['supertrend'] = supertrend_data[f'SUPERT_{period}_{multiplier}'] > 0
    except:
        df['supertrend'] = True  # Fallback
    return df

def detectar_candle_forte(df):
    candle = df.iloc[-1]
    corpo = abs(candle['close'] - candle['open'])
    sombra_sup = candle['high'] - max(candle['close'], candle['open'])
    sombra_inf = min(candle['close'], candle['open']) - candle['low']
    return corpo > (sombra_sup * 2) and corpo > (sombra_inf * 2)

def detectar_engolfo_alta(df):
    if len(df) < 2:
        return False
    c1 = df.iloc[-2]  # Candle anterior
    c2 = df.iloc[-1]  # Candle atual
    return (c2['close'] > c2['open'] and     # Atual é de alta
            c1['close'] < c1['open'] and     # Anterior é de baixa
            c2['open'] < c1['close'] and     # Abertura atual < fechamento anterior
            c2['close'] > c1['open'])        # Fechamento atual > abertura anterior

# ===============================
# === SETUPS DE TRADING
# ===============================
def verificar_setup_conservador(r, df):
    """Setup conservador para BTC/ETH - confluência alta"""
    condicoes = [
        r['rsi'] < 45,                                           # RSI em sobrevenda moderada
        r['ema9'] > r['ema21'],                                 # Tendência de curto prazo positiva
        r['macd'] > r['macd_signal'],                           # MACD positivo
        r['adx'] > 20,                                          # Tendência forte
        df['volume'].iloc[-1] > df['volume'].mean() * 1.2,     # Volume acima da média
        r['close'] > r['ema200'],                               # Preço acima da EMA longa
        df['supertrend'].iloc[-1] == True                       # Supertrend positivo
    ]
    
    if sum(condicoes) >= 5:  # Pelo menos 5 de 7 condições
        return {
            'setup': '🛡️ SETUP CONSERVADOR', 
            'prioridade': '🟢 BAIXO RISCO', 
            'emoji': '🛡️',
            'id': 'conservador'
        }
    return None

def verificar_setup_agressivo(r, df):
    """Setup agressivo para BTC/ETH - entrada rápida"""
    condicoes = [
        r['rsi'] < 50,                                          # RSI não sobrecomprado
        r['ema9'] > r['ema21'],                                 # EMA9 > EMA21
        r['macd'] > r['macd_signal'],                           # MACD > sinal
        df['volume'].iloc[-1] > df['volume'].mean(),            # Volume acima da média
        detectar_candle_forte(df) or detectar_engolfo_alta(df), # Padrão de força
        r['adx'] > 15                                           # ADX mínimo
    ]
    
    if sum(condicoes) >= 4:  # Pelo menos 4 de 6 condições
        return {
            'setup': '⚡ SETUP AGRESSIVO', 
            'prioridade': '🟡 RISCO MODERADO', 
            'emoji': '⚡',
            'id': 'agressivo'
        }
    return None

def verificar_setup_reversao(r, df):
    """Setup de reversão - para entradas em correções"""
    if len(df) < 5:
        return None
    
    # Verificar se houve queda recente
    queda_recente = df['close'].iloc[-3:].min() < df['close'].iloc[-5:].max() * 0.95
    
    condicoes = [
        r['rsi'] < 35,                          # RSI em sobrevenda forte
        queda_recente,                          # Houve correção recente
        detectar_engolfo_alta(df),              # Padrão de reversão
        r['obv'] > df['obv'].iloc[-5:].mean(),  # OBV ainda positivo
        df['volume'].iloc[-1] > df['volume'].mean() * 1.5  # Volume forte
    ]
    
    if sum(condicoes) >= 3:
        return {
            'setup': '🔄 SETUP REVERSÃO', 
            'prioridade': '🟠 OPORTUNIDADE', 
            'emoji': '🔄',
            'id': 'reversao'
        }
    return None

def calcular_score_setup(r, df, setup_id):
    """Calcula score de 0-10 para o setup"""
    score = 0
    total = 0
    criterios = []
    
    def avaliar(condicao, descricao, peso=1):
        nonlocal score, total
        total += peso
        if condicao:
            score += peso
            criterios.append(f"✅ {descricao}")
        else:
            criterios.append(f"❌ {descricao}")
    
    # Critérios básicos (peso 1)
    avaliar(r['rsi'] < 50, "RSI saudável (<50)")
    avaliar(r['ema9'] > r['ema21'], "EMA9 > EMA21")
    avaliar(r['macd'] > r['macd_signal'], "MACD positivo")
    avaliar(df['volume'].iloc[-1] > df['volume'].mean(), "Volume acima da média")
    
    # Critérios importantes (peso 1.5)
    avaliar(r['adx'] > 20, "Tendência forte (ADX>20)", 1.5)
    avaliar(r['close'] > r['ema200'], "Acima EMA200", 1.5)
    avaliar(df['supertrend'].iloc[-1], "Supertrend ativo", 1.5)
    
    # Critérios críticos (peso 2)
    avaliar(detectar_candle_forte(df), "Candle forte", 2)
    avaliar(df['volume'].iloc[-1] > df['volume'].mean() * 1.5, "Volume muito alto", 2)
    
    if total == 0:
        return 0.0, []
    
    score_final = round((score / total) * 10, 1)
    return score_final, criterios

# ===============================
# === ALERTAS E COMUNICAÇÃO
# ===============================
def pode_enviar_alerta(par, setup):
    agora = datetime.datetime.utcnow()
    chave = f"{par}_{setup}"
    
    with lock_alertas:
        if chave in alertas_enviados:
            delta = (agora - alertas_enviados[chave]).total_seconds()
            if delta < TEMPO_REENVIO:
                return False
        
        alertas_enviados[chave] = agora
        return True

def enviar_telegram(mensagem):
    if TOKEN == "dummy_token":
        print(f"[TELEGRAM SIMULADO] {mensagem}")
        return True
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID, 
        "text": mensagem, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.ok:
            return True
        else:
            logging.error(f"Erro Telegram: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Exception Telegram: {e}")
        return False

def enviar_alerta_completo(par, r, setup_info):
    preco = r['close']
    atr = r['atr']
    
    # Cálculo de alvos e stops adaptado para BTC/ETH
    if par == 'BTC/USDT':
        stop = round(preco - (atr * 1.2), 2)   # Stop mais conservador para BTC
        alvo = round(preco + (atr * 2.5), 2)   # Alvo moderado
    else:  # ETH/USDT
        stop = round(preco - (atr * 1.5), 2)   # Stop normal para ETH
        alvo = round(preco + (atr * 3.0), 2)   # Alvo mais agressivo
    
    # Timestamp
    agora_utc = datetime.datetime.utcnow()
    agora_local = agora_utc - datetime.timedelta(hours=3)  # Brasília
    timestamp_br = agora_local.strftime('%d/%m/%Y %H:%M')
    
    # Score do setup
    score, criterios = calcular_score_setup(r, pd.DataFrame({
        'close': [r['close']] * 10,
        'volume': [r['volume']] * 10,
        'ema9': [r['ema9']] * 10,
        'ema21': [r['ema21']] * 10,
        'ema200': [r['ema200']] * 10,
        'supertrend': [True] * 10,
        'high': [r['close'] * 1.01] * 10,
        'low': [r['close'] * 0.99] * 10,
        'open': [r['close'] * 0.999] * 10
    }), setup_info.get('id', 'conservador'))
    
    # Link TradingView
    symbol_clean = par.replace("/", "")
    link_tv = f"https://www.tradingview.com/chart/?symbol=OKX:{symbol_clean}"
    
    # Dados fundamentais
    resumo_mercado = obter_dados_fundamentais()
    
    # Construir mensagem
    mensagem = (
        f"{setup_info['emoji']} *{setup_info['setup']}*\n"
        f"{setup_info['prioridade']}\n\n"
        f"📊 *Par:* `{par}`\n"
        f"💰 *Preço:* `${preco:,.2f}`\n"
        f"🎯 *Alvo:* `${alvo:,.2f}`\n"
        f"🛑 *Stop:* `${stop:,.2f}`\n"
        f"📊 *Score:* {score}/10\n\n"
        f"📈 *Indicadores:*\n"
        f"• RSI: {r['rsi']:.1f} | ADX: {r['adx']:.1f}\n"
        f"• Volume: {r['volume']:,.0f}\n"
        f"• ATR: ${r['atr']:.2f}\n\n"
        f"🕐 {timestamp_br} (BR)\n"
        f"📈 [Ver Gráfico]({link_tv})\n\n"
        f"{resumo_mercado}\n\n"
        f"*📋 Análise Técnica:*\n"
    )
    
    # Adicionar critérios (máximo 5 para não sobrecarregar)
    for criterio in criterios[:5]:
        mensagem += f"{criterio}\n"
    
    if len(criterios) > 5:
        mensagem += f"... e mais {len(criterios)-5} critérios"
    
    # Enviar alerta
    if pode_enviar_alerta(par, setup_info['setup']):
        if enviar_telegram(mensagem):
            logging.info(f"Alerta enviado: {par} - {setup_info['setup']} (score: {score})")
            print(f"✅ {par} - {setup_info['setup']} (score: {score})")
            
            # Registrar sinal para monitoramento
            try:
                registrar_sinal_monitorado(
                    par=par,
                    setup_id=setup_info.get('id', 'desconhecido'),
                    preco_entrada=preco,
                    alvo=alvo,
                    stop=stop
                )
            except Exception as e:
                logging.error(f"Erro ao registrar sinal: {e}")
        else:
            print(f"❌ Falha ao enviar alerta para {par}")
    else:
        print(f"⏳ Alerta recente para {par} - aguardando")

# ===============================
# === ANÁLISE PRINCIPAL
# ===============================
def analisar_par(exchange, par):
    try:
        print(f"🔍 Analisando {par}...")
        
        # Buscar dados OHLCV
        ohlcv = exchange.fetch_ohlcv(par, timeframe, limit=limite_candles)
        if len(ohlcv) < limite_candles:
            print(f"⚠️ Dados insuficientes para {par}")
            return
        
        # Criar DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calcular indicadores
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        df['ema9'] = EMAIndicator(close, 9).ema_indicator()
        df['ema21'] = EMAIndicator(close, 21).ema_indicator()
        df['ema200'] = EMAIndicator(close, 200).ema_indicator()
        df['rsi'] = RSIIndicator(close, 14).rsi()
        df['atr'] = AverageTrueRange(high, low, close, 14).average_true_range()
        
        macd = MACD(close)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        
        df['adx'] = ADXIndicator(high, low, close, 14).adx()
        df['obv'] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        
        df = calcular_supertrend(df)
        
        # Linha atual
        r = df.iloc[-1]
        
        # Verificar setups em ordem de prioridade
        setups = [
            verificar_setup_conservador,
            verificar_setup_agressivo,
            verificar_setup_reversao
        ]
        
        for verificar_setup in setups:
            setup_info = verificar_setup(r, df)
            if setup_info:
                enviar_alerta_completo(par, r, setup_info)
                return par  # Retorna o par se encontrou setup
        
        print(f"   💭 {par}: Nenhum setup detectado")
        return None
        
    except Exception as e:
        logging.error(f"Erro na análise de {par}: {e}")
        print(f"❌ Erro com {par}: {e}"
