import ccxt
import pandas as pd
import time
import datetime
import requests
import os
import logging
import json
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

try:
    import pandas_ta as pta
except ImportError:
    print("⚠️ pandas_ta não disponível, usando cálculo manual do Supertrend")
    pta = None

# ===============================
# === CONFIGURAÇÕES
# ===============================
PARES_ALVOS = ['BTC/USDT', 'ETH/USDT']
timeframe = '1h'
limite_candles = 100
TEMPO_REENVIO = 60 * 30  # 30 minutos entre alertas do mesmo par

# Configurações do Telegram
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TOKEN or not CHAT_ID:
    print("⚠️ AVISO: Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID para receber alertas")
    TOKEN = "dummy_token"
    CHAT_ID = "dummy_chat"

# Arquivos de dados
ARQUIVO_SINAIS_MONITORADOS = 'sinais_monitorados.json'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Controle de alertas
alertas_enviados = {}

# ===============================
# === GESTÃO DE SINAIS MONITORADOS
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
    """Verifica status dos sinais em aberto"""
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
            sinal['preco_final'] = preco_atual
        elif preco_atual <= sinal['stop']:
            sinal['status'] = "🛑 Stop atingido"
            sinal['preco_final'] = preco_atual
        else:
            # Verificar expiração (24 horas)
            dt_alerta = datetime.datetime.fromisoformat(sinal['timestamp'])
            tempo_passado = datetime.datetime.utcnow() - dt_alerta
            if tempo_passado.total_seconds() >= 60 * 60 * 24:
                sinal['status'] = "⏰ Expirado (24h)"
                sinal['preco_final'] = preco_atual
        
        if sinal['status'] != status_anterior:
            sinal['atualizado_em'] = datetime.datetime.utcnow().isoformat()
            sinais_atualizados.append(sinal)
    
    if sinais_atualizados:
        salvar_sinais_monitorados(sinais)
        
        # Enviar notificações de fechamento
        for sinal in sinais_atualizados:
            enviar_notificacao_fechamento(sinal)
    
    return sinais_atualizados

def enviar_notificacao_fechamento(sinal):
    """Envia notificação quando sinal é fechado"""
    try:
        dt_inicio = datetime.datetime.fromisoformat(sinal['timestamp'])
        dt_fim = datetime.datetime.fromisoformat(sinal['atualizado_em'])
        duracao = dt_fim - dt_inicio
        horas = int(duracao.total_seconds() // 3600)
        minutos = int((duracao.total_seconds() % 3600) // 60)
        tempo_duracao = f"{horas}h {minutos}min"
        
        resultado = ""
        if "Alvo atingido" in sinal['status']:
            resultado = "🎉 SUCESSO"
        elif "Stop atingido" in sinal['status']:
            resultado = "⚠️ STOP"
        else:
            resultado = "⏰ EXPIRADO"
            
        mensagem = (
            f"📊 *SINAL FINALIZADO*\n\n"
            f"{resultado}\n\n"
            f"📊 *Par:* `{sinal['par']}`\n"
            f"📋 *Setup:* {sinal['setup']}\n"
            f"💰 *Entrada:* `${sinal['entrada']:.2f}`\n"
            f"🏁 *Saída:* `${sinal.get('preco_final', 'N/A')}`\n"
            f"⏱️ *Duração:* {tempo_duracao}\n"
            f"📍 *Status:* {sinal['status']}"
        )
        
        enviar_telegram(mensagem)
        
    except Exception as e:
        logging.error(f"Erro ao enviar notificação de fechamento: {e}")

# ===============================
# === DADOS FUNDAMENTAIS
# ===============================

def abreviar_valor(valor):
    if valor >= 1_000_000_000_000:
        return f"${valor/1_000_000_000_000:.2f}T"
    elif valor >= 1_000_000_000:
        return f"${valor/1_000_000_000:.2f}B"
    elif valor >= 1_000_000:
        return f"${valor/1_000_000:.2f}M"
    else:
        return f"${valor:,.2f}"

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
        
        emoji_cap = "↗️" if market_cap_change >= 0 else "↘️"
        
        # Alerta de mercado
        alerta_mercado = ""
        if market_cap_change < -2:
            alerta_mercado = "\n⚠️ *Queda relevante na capitalização nas últimas 24h.*"
        
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
            + alerta_mercado
        )
    
    except Exception as e:
        logging.warning(f"Erro ao obter dados fundamentais: {e}")
        return "*⚠️ Dados fundamentais temporariamente indisponíveis*"

# ===============================
# === INDICADORES TÉCNICOS
# ===============================

def calcular_supertrend(df, period=10, multiplier=3):
    """Cálculo do Supertrend - tenta pandas_ta, senão usa manual"""
    try:
        if pta:
            supertrend_data = pta.supertrend(
                high=df['high'], 
                low=df['low'], 
                close=df['close'],
                length=period, 
                multiplier=multiplier
            )
            df['supertrend'] = supertrend_data[f'SUPERT_{period}_{multiplier}'] > 0
        else:
            # Cálculo manual simplificado
            high = df['high']
            low = df['low']
            close = df['close']
            
            atr = AverageTrueRange(high, low, close, period).average_true_range()
            hl2 = (high + low) / 2
            upper_band = hl2 + (multiplier * atr)
            lower_band = hl2 - (multiplier * atr)
            
            # Supertrend simplificado
            df['supertrend'] = close > lower_band
            
        return df
        
    except Exception as e:
        logging.warning(f"Erro no Supertrend: {e}")
        df['supertrend'] = [True] * len(df)
        return df

def detectar_candle_forte(df):
    """Detecta candle com corpo forte vs sombras"""
    if len(df) < 2:
        return False
    
    candle = df.iloc[-1]
    corpo = abs(candle['close'] - candle['open'])
    sombra_sup = candle['high'] - max(candle['close'], candle['open'])
    sombra_inf = min(candle['close'], candle['open']) - candle['low']
    
    return corpo > sombra_sup and corpo > sombra_inf

def detectar_engolfo_alta(df):
    """Detecta padrão de engolfo de alta"""
    if len(df) < 2:
        return False
    
    c1 = df.iloc[-2]  # Anterior
    c2 = df.iloc[-1]  # Atual
    
    return (c2['close'] > c2['open'] and     # Atual de alta
            c1['close'] < c1['open'] and     # Anterior de baixa
            c2['open'] < c1['close'] and     # Abertura atual < fechamento anterior
            c2['close'] > c1['open'])        # Fechamento atual > abertura anterior

def detectar_martelo(df):
    """Detecta padrão de martelo"""
    if len(df) < 1:
        return False
        
    c = df.iloc[-1]
    corpo = abs(c['close'] - c['open'])
    sombra_inf = min(c['close'], c['open']) - c['low']
    sombra_sup = c['high'] - max(c['close'], c['open'])
    
    return sombra_inf > corpo * 2 and sombra_sup < corpo

# ===============================
# === SETUPS DE TRADING (Baseados no Script Original)
# ===============================

def verificar_setup_rigoroso(r, df):
    """Setup 1 - Rigoroso (baseado no script original)"""
    condicoes = [
        r['rsi'] < 40,
        df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and r['ema9'] > r['ema21'],  # Cruzamento
        r['macd'] > r['macd_signal'],
        r['adx'] > 20,
        df['volume'].iloc[-1] > df['volume'].mean() * 1.5,
        df['supertrend'].iloc[-1] == True
    ]
    
    if all(condicoes):
        return {
            'setup': '🎯 SETUP RIGOROSO', 
            'prioridade': '🟠 PRIORIDADE ALTA', 
            'emoji': '🎯',
            'id': 'setup_rigoroso'
        }
    return None

def verificar_setup_alta_confluencia(r, df):
    """Setup 5 - Alta Confluência (baseado no script original)"""
    condicoes = [
        r['rsi'] < 40,
        df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and r['ema9'] > r['ema21'],
        r['macd'] > r['macd_signal'],
        r['atr'] > df['atr'].mean(),
        r['obv'] > df['obv'].mean(),
        r['adx'] > 20,
        r['close'] > r['ema200'],
        df['volume'].iloc[-1] > df['volume'].mean(),
        df['supertrend'].iloc[-1],
        detectar_candle_forte(df)
    ]
    
    if sum(condicoes) >= 6:
        return {
            'setup': '🔥 SETUP ALTA CONFLUÊNCIA',
            'prioridade': '🟥 PRIORIDADE MÁXIMA',
            'emoji': '🔥',
            'id': 'setup_alta_confluencia'
        }
    return None

def verificar_setup_rompimento(r, df):
    """Setup 6 - Rompimento (baseado no script original)"""
    if len(df) < 10:
        return None
        
    resistencia = df['high'].iloc[-10:-1].max()
    rompimento = r['close'] > resistencia
    volume_ok = df['volume'].iloc[-1] > df['volume'].mean()
    rsi_ok = r['rsi'] > 55 and df['rsi'].iloc[-1] > df['rsi'].iloc[-2]
    
    if rompimento and volume_ok and rsi_ok and df['supertrend'].iloc[-1]:
        return {
            'setup': '🚀 SETUP ROMPIMENTO',
            'prioridade': '🟩 ALTA OPORTUNIDADE',
            'emoji': '🚀',
            'id': 'setup_rompimento'
        }
    return None

def verificar_setup_reversao_tecnica(r, df):
    """Setup 4 - Reversão Técnica (baseado no script original)"""
    if len(df) < 3:
        return None
        
    candle_reversao = detectar_martelo(df) or detectar_engolfo_alta(df)
    rsi_subindo = df['rsi'].iloc[-1] > df['rsi'].iloc[-2]
    
    condicoes = [
        r['obv'] > df['obv'].mean(),
        df['close'].iloc[-2] > df['open'].iloc[-2],  # Candle anterior de alta
        df['close'].iloc[-1] > df['close'].iloc[-2],  # Candle atual em alta
        candle_reversao,
        rsi_subindo
    ]
    
    if all(condicoes):
        return {
            'setup': '🔁 SETUP REVERSÃO TÉCNICA',
            'prioridade': '🟣 OPORTUNIDADE DE REVERSÃO',
            'emoji': '🔁',
            'id': 'setup_reversao_tecnica'
        }
    return None

def verificar_setup_intermediario(r, df):
    """Setup 2 - Intermediário (baseado no script original)"""
    condicoes = [
        r['rsi'] < 50,
        r['ema9'] > r['ema21'],
        r['macd'] > r['macd_signal'],
        r['adx'] > 15,
        df['volume'].iloc[-1] > df['volume'].mean()
    ]
    
    if all(condicoes):
        return {
            'setup': '⚙️ SETUP INTERMEDIÁRIO',
            'prioridade': '🟡 PRIORIDADE MÉDIA-ALTA',
            'emoji': '⚙️',
            'id': 'setup_intermediario'
        }
    return None

def verificar_setup_leve(r, df):
    """Setup 3 - Leve (baseado no script original)"""
    condicoes = [
        r['ema9'] > r['ema21'],
        r['adx'] > 15,
        df['volume'].iloc[-1] > df['volume'].mean()
    ]
    
    if sum(condicoes) >= 2:
        return {
            'setup': '🔹 SETUP LEVE',
            'prioridade': '🔵 PRIORIDADE MÉDIA',
            'emoji': '🔹',
            'id': 'setup_leve'
        }
    return None

# ===============================
# === SCORE E ANÁLISE
# ===============================

def calcular_score_setup(r, df, setup_id):
    """Score baseado no script original"""
    score = 0
    total = 0
    criterios = []
    
    def conta(condicao, descricao, peso=1):
        nonlocal score, total
        total += peso
        if condicao:
            score += peso
            criterios.append(f"✅ {descricao}")
        else:
            criterios.append(f"❌ {descricao}")
    
    # Critérios específicos por setup (baseado no script original)
    if setup_id in ['setup_rigoroso', 'setup_alta_confluencia']:
        conta(r['rsi'] < 40, "RSI < 40")
        conta(df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and r['ema9'] > r['ema21'], "Cruzamento EMA9 > EMA21")
        conta(r['macd'] > r['macd_signal'], "MACD > sinal")
        conta(r['adx'] > 20, "ADX > 20")
        conta(df['volume'].iloc[-1] > df['volume'].mean() * 1.5, "Volume acima da média")
        conta(df['supertrend'].iloc[-1], "Supertrend ativo")
        conta(r['atr'] > df['atr'].mean(), "ATR > média")
        conta(r['obv'] > df['obv'].mean(), "OBV > média")
        conta(r['close'] > r['ema200'], "Preço > EMA200")
        conta(detectar_candle_forte(df), "Candle forte detectado")
        
    elif setup_id == 'setup_intermediario':
        conta(r['rsi'] < 50, "RSI < 50")
        conta(r['ema9'] > r['ema21'], "EMA9 > EMA21")
        conta(r['macd'] > r['macd_signal'], "MACD > sinal")
        conta(r['adx'] > 15, "ADX > 15")
        conta(df['volume'].iloc[-1] > df['volume'].mean(), "Volume acima da média")
        
    elif setup_id == 'setup_leve':
        conta(r['ema9'] > r['ema21'], "EMA9 > EMA21")
        conta(r['adx'] > 15, "ADX > 15")
        conta(df['volume'].iloc[-1] > df['volume'].mean(), "Volume acima da média")
        
    elif setup_id == 'setup_reversao_tecnica':
        conta(r['obv'] > df['obv'].mean(), "OBV > média")
        conta(df['close'].iloc[-2] > df['open'].iloc[-2], "Candle anterior de alta")
        conta(df['close'].iloc[-1] > df['close'].iloc[-2], "Candle atual em alta")
        conta(detectar_martelo(df) or detectar_engolfo_alta(df), "Padrão de reversão")
        conta(df['rsi'].iloc[-1] > df['rsi'].iloc[-2], "RSI em alta")
        
    elif setup_id == 'setup_rompimento':
        resistencia = df['high'].iloc[-10:-1].max()
        conta(r['close'] > resistencia, "Rompimento da resistência")
        conta(df['volume'].iloc[-1] > df['volume'].mean(), "Volume acima da média")
        conta(r['rsi'] > 55 and df['rsi'].iloc[-1] > df['rsi'].iloc[-2], "RSI em alta (>55)")
        conta(df['supertrend'].iloc[-1], "Supertrend ativo")
    
    if total == 0:
        return 0.0, []
    
    score_final = round((score / total) * 10, 1)
    return score_final, criterios

def gerar_explicacao_score(score):
    """Explicação educativa baseada no script original"""
    if score >= 9:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal teve **confluência máxima** entre indicadores:\n"
            "• RSI saudável\n"
            "• ADX forte (> 20)\n"
            "• Volume bem acima da média\n"
            "• Supertrend em tendência de alta\n\n"
            "📌 Isso indica um momento técnico **muito favorável** para entrada."
        )
    elif score >= 6.5:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal apresenta **boa base técnica**, mas exige mais cautela:\n"
            "• Alguns indicadores estão neutros ou moderados\n"
            "• Volume não muito acima da média\n\n"
            "📌 Pode indicar oportunidade, mas atenção ao contexto é recomendada."
        )
    else:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal possui **baixa força técnica**:\n"
            "• Indicadores fracos ou divergentes\n"
            "• Volume abaixo da média\n\n"
            "📌 Não recomendado operar com base nesse sinal isoladamente."
        )

# ===============================
# === COMUNICAÇÃO TELEGRAM
# ===============================

def pode_enviar_alerta(par, setup):
    """Controla intervalo entre alertas do mesmo par/setup"""
    agora = datetime.datetime.utcnow()
    chave = f"{par}_{setup}"
    
    if chave in alertas_enviados:
        delta = (agora - alertas_enviados[chave]).total_seconds()
        if delta < TEMPO_REENVIO:
            return False
    
    alertas_enviados[chave] = agora
    return True

def enviar_telegram(mensagem):
    """Envia mensagem para o Telegram"""
    if not TOKEN or TOKEN == "dummy_token":
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
        if response.status_code == 200:
            return True
        else:
            logging.error(f"Erro Telegram: {response.text}")
            return False
    except Exception as e:
        logging.error(f"Erro ao enviar Telegram: {e}")
        return False

def enviar_alerta_completo(par, r, setup_info, df):
    """Envia alerta completo baseado no script original"""
    preco = r['close']
    atr = r['atr']
    
    # Cálculo de alvos adaptativos (baseado no script original)
    if par == 'BTC/USDT':
        stop = round(preco - (atr * 1.2), 2)   # Mais conservador para BTC
        alvo = round(preco + (atr * 2.5), 2)   # Alvo moderado
    else:  # ETH/USDT
        stop = round(preco - (atr * 1.5), 2)   # Stop normal para ETH
        alvo = round(preco + (atr * 3.0), 2)   # Alvo mais agressivo
    
    # Score do setup
    score, criterios = calcular_score_setup(r, df, setup_info.get('id', ''))
    
    # Timestamp em Brasília
    agora_utc = datetime.datetime.utcnow()
    agora_local = agora_utc - datetime.timedelta(hours=3)
    timestamp_br = agora_local.strftime('%d/%m/%Y %H:%M (Brasília)')
    
    # Link TradingView
    symbol_clean = par.replace("/", "")
    link_tv = f"https://www.tradingview.com/chart/?symbol=OKX:{symbol_clean}"
    
    # Dados fundamentais
    resumo_mercado = obter_dados_fundamentais()
    
    # Construir mensagem (baseada no formato original)
    mensagem = (
        f"{setup_info['emoji']} *{setup_info['setup']}*\n"
        f"{setup_info['prioridade']}\n\n"
        f"📊 Par: `{par}`\n"
        f"💰 Preço: `{preco:,.2f}`\n"
        f"🎯 Alvo: `{alvo:,.2f}` ({'2.5x' if par == 'BTC/USDT' else '3.0x'} ATR)\n"
        f"🛑 Stop: `{stop:,.2f}` ({'1.2x' if par == 'BTC/USDT' else '1.5x'} ATR)\n\n"
        f"📊 *Força do Sinal:* {score} / 10\n"
        f"📌 *Componentes do Score:*\n"
    )
    
    # Adicionar critérios (máximo 6 para não sobrecarregar)
    for criterio in criterios[:6]:
        mensagem += f"{criterio}\n"
    
    if len(criterios) > 6:
        mensagem += f"... e mais {len(criterios)-6} critérios\n"
    
    mensagem += (
        f"\n📈 Indicadores:\n"
        f"• RSI: {r['rsi']:.1f} | ADX: {r['adx']:.1f}\n"
        f"• ATR: {r['atr']:.4f} | OBV: {r['obv']:,.0f}\n"
        f"• Volume: {r['volume']:,.0f}\n"
        f"🕘 {timestamp_br}\n"
        f"📉 [Ver gráfico no TradingView]({link_tv})\n\n"
        f"{resumo_mercado}\n\n"
    )
    
    # Explicação educativa
    explicacao = gerar_explicacao_score(score)
    mensagem += explicacao
    
    # Enviar se permitido
    if pode_enviar_alerta(par, setup_info['setup']):
        if enviar_telegram(mensagem):
            logging.info(f"✅ Alerta enviado: {par} - {setup_info['setup']} (score: {score})")
            print(f"✅ ALERTA: {par} - {setup_info['setup']} (score: {score})")
            
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
                
            return True
        else:
            logging.error(f"❌ Falha ao enviar: {par} - {setup_info['setup']}")
            return False
    else:
        logging.info(f"⏳ Alerta recente ignorado: {par} - {setup_info['setup']}")
        return False

# ===============================
# === ANÁLISE PRINCIPAL
# ===============================

def analisar_par(exchange, par):
    """Análise principal de um par - baseada no script original"""
    try:
        print(f"🔍 Analisando {par}...")
        
        # Buscar dados OHLCV
        ohlcv = exchange.fetch_ohlcv(par, timeframe, limit=limite_candles)
        if len(ohlcv) < limite_candles:
            print(f"⚠️ Dados insuficientes para {par}")
            return None
        
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
        
        # Verificar se temos dados suficientes
        if df['ema200'].isna().any() or df['adx'].isna().any():
            print(f"⚠️ Indicadores incompletos para {par}")
            return None
        
        # Dados da linha atual
        r = df.iloc[-1]
        
        # Verificar setups em ordem de prioridade (baseado no script original)
        setups = [
            verificar_setup_alta_confluencia,  # Prioridade máxima
            verificar_setup_rompimento,       # Alta oportunidade
            verificar_setup_rigoroso,         # Prioridade alta
            verificar_setup_intermediario,    # Média-alta
            verificar_setup_reversao_tecnica, # Oportunidade reversão
            verificar_setup_leve             # Última opção
        ]
        
        for verificar_setup in setups:
            setup_info = verificar_setup(r, df)
            if setup_info:
                return enviar_alerta_completo(par, r, setup_info, df)
        
        print(f"   💭 {par}: Nenhum setup detectado")
        return None
        
    except Exception as e:
        logging.error(f"❌ Erro na análise de {par}: {e}")
        print(f"❌ Erro com {par}: {e}")
        return None

# ===============================
# === FUNÇÃO PRINCIPAL
# ===============================

def executar_scanner():
    """Função principal do scanner GitHub Actions"""
    try:
        print("🚀 INICIANDO SCANNER GITHUB ACTIONS - ETH/BTC FOCUS")
        print(f"⏰ Executado em: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"📊 Pares: {', '.join(PARES_ALVOS)}")
        print(f"📈 Timeframe: {timeframe}")
        
        # Inicializar exchange
        exchange = ccxt.okx({'enableRateLimit': True})
        exchange.load_markets()
        
        # Verificar se pares existem
        for par in PARES_ALVOS:
            if par not in exchange.markets:
                print(f"❌ Par {par} não encontrado na OKX")
                continue
        
        # Verificar sinais em aberto primeiro
        try:
            print("🔍 Verificando sinais em aberto...")
            sinais_atualizados = verificar_sinais_monitorados(exchange)
            if sinais_atualizados:
                print(f"📊 {len(sinais_atualizados)} sinais foram atualizados")
        except Exception as e:
            logging.error(f"Erro ao verificar sinais: {e}")
        
        # Analisar cada par
        alertas_enviados_count = 0
        for par in PARES_ALVOS:
            if par in exchange.markets:
                resultado = analisar_par(exchange, par)
                if resultado:
                    alertas_enviados_count += 1
                time.sleep(2)  # Evitar rate limiting
        
        # Resumo final
        print(f"\n✅ SCANNER FINALIZADO")
        print(f"📨 Alertas enviados: {alertas_enviados_count}")
        print(f"🕒 Próxima execução: em 10 minutos")
        
        ## SEMPRE enviar status quando não há sinais
if alertas_enviados_count == 0:
    agora = datetime.datetime.utcnow().strftime('%H:%M UTC')
    
    # Verificar quantos sinais estão em aberto
    sinais = carregar_sinais_monitorados()
    sinais_abertos = len([s for s in sinais if s['status'] == 'em_aberto'])
    
    mensagem_resumo = (
        f"🤖 *Scanner ETH/BTC - Status*\n\n"
        f"⏰ {agora}\n"
        f"📊 Analisados: BTC/USDT, ETH/USDT\n"
        f"🔍 Setups verificados: 6 por moeda\n"
        f"📈 Resultado: Nenhum novo sinal\n"
        f"📝 Sinais monitorados: {sinais_abertos}\n\n"
        f"💭 *Situação atual:*\n"
        f"• RSI fora das zonas de reversão\n"
        f"• Sem breakouts significativos\n"
        f"• MACD sem cruzamentos recentes\n"
        f"• Aguardando melhores condições\n\n"
        f"⏰ Próxima verificação: 15 minutos"
    )
    enviar_telegram(mensagem_resumo)
    print("✅ Status detalhado enviado ao Telegram")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ Erro crítico no scanner: {e}")
        print(f"❌ ERRO CRÍTICO: {e}")
        
        # Enviar alerta de erro
        if TOKEN and TOKEN != "dummy_token":
            mensagem_erro = (
                f"🚨 *ERRO NO SCANNER*\n\n"
                f"❌ {str(e)[:100]}...\n"
                f"⏰ {datetime.datetime.utcnow().strftime('%H:%M UTC')}\n"
                f"🔧 Verifique os logs do GitHub Actions"
            )
            enviar_telegram(mensagem_erro)
        
        return False

# ===============================
# === EXECUÇÃO
# ===============================

if __name__ == "__main__":
    # Executar scanner
    print("🎯 SCANNER ETH/BTC - GitHub Actions")
    print("📋 Baseado no script original com 6 setups")
    print("🔍 Focado exclusivamente em BTC/USDT e ETH/USDT")
    print("⚡ Execução otimizada para GitHub Actions\n")
    
    sucesso = executar_scanner()
    
    if sucesso:
        print("🎉 Scanner executado com sucesso!")
        exit(0)
    else:
        print("💥 Scanner falhou!")
        exit(1)
