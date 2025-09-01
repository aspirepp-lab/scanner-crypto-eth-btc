import ccxt
import pandas as pd
import time
import datetime
import requests
import os
import logging
import json
import warnings
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import OnBalanceVolumeIndicator

# Suprimir warnings específicos para logs mais limpos
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*invalid value encountered.*')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*divide by zero.*')

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

# Logging melhorado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Controle de alertas
alertas_enviados = {}

# ===============================
# === VALIDAÇÃO DE DADOS (NOVO)
# ===============================

def validar_dados(df, nome_par):
    """Valida qualidade dos dados antes de calcular indicadores"""
    if df is None or len(df) == 0:
        logging.warning(f"DataFrame vazio para {nome_par}")
        return False
        
    if len(df) < 50:
        logging.warning(f"Dados insuficientes para {nome_par}: {len(df)} candles")
        return False
    
    # Verificar se há valores NaN ou inválidos nas colunas essenciais
    colunas_essenciais = ['open', 'high', 'low', 'close', 'volume']
    for col in colunas_essenciais:
        if df[col].isna().sum() > 0:
            logging.warning(f"Valores NaN encontrados em {col} para {nome_par}")
            # Tentar corrigir interpolando
            df[col] = df[col].interpolate(method='linear')
        
        if (df[col] <= 0).sum() > 0:
            logging.warning(f"Valores inválidos (<=0) em {col} para {nome_par}")
            return False
    
    return True

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
# === DADOS FUNDAMENTAIS (MELHORADOS)
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
        # Dados gerais do mercado com timeout reduzido
        total = requests.get("https://api.coingecko.com/api/v3/global", timeout=5).json()
        market_data = total.get('data', {})
        
        market_cap = market_data.get('total_market_cap', {}).get('usd')
        market_cap_change = market_data.get('market_cap_change_percentage_24h_usd', 0)
        btc_dominance = market_data.get('market_cap_percentage', {}).get('btc')
        
        if market_cap is None or btc_dominance is None:
            return "*⚠️ Dados fundamentais indisponíveis*"
        
        emoji_cap = "📈" if market_cap_change >= 0 else "📉"
        
        # Alerta de mercado melhorado
        alerta_mercado = ""
        if market_cap_change < -3:
            alerta_mercado = "\n🔴 *Mercado em correção significativa*"
        elif market_cap_change > 3:
            alerta_mercado = "\n🟢 *Mercado em alta forte*"
        
        # Índice Fear & Greed melhorado
        try:
            medo_ganancia = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3).json()
            indice = medo_ganancia['data'][0]
            valor_fg = int(indice['value'])
            classificacao = indice['value_classification']
            
            # Emoji baseado no valor
            if valor_fg >= 75:
                emoji_fg = "🔥"
            elif valor_fg >= 55:
                emoji_fg = "😊"
            elif valor_fg >= 45:
                emoji_fg = "😐"
            elif valor_fg >= 25:
                emoji_fg = "😰"
            else:
                emoji_fg = "🥶"
                
            fear_greed = f"{valor_fg} {emoji_fg} ({classificacao})"
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
# === INDICADORES TÉCNICOS (MELHORADOS)
# ===============================

def calcular_supertrend(df, period=10, multiplier=3):
    """Cálculo do Supertrend com validação melhorada"""
    try:
        if not validar_dados(df, "Supertrend"):
            df['supertrend'] = [True] * len(df)
            return df
            
        if pta:
            supertrend_data = pta.supertrend(
                high=df['high'], 
                low=df['low'], 
                close=df['close'],
                length=period, 
                multiplier=multiplier
            )
            if supertrend_data is not None and len(supertrend_data.columns) > 1:
                df['supertrend'] = supertrend_data.iloc[:, 1] > 0
            else:
                raise Exception("pandas_ta retornou dados inválidos")
        else:
            # Cálculo manual melhorado
            high = df['high']
            low = df['low']
            close = df['close']
            
            atr = AverageTrueRange(high, low, close, period).average_true_range()
            
            # Validar ATR antes de usar
            if atr.isna().sum() > 0:
                atr = atr.fillna(method='bfill').fillna(method='ffill')
            
            hl2 = (high + low) / 2
            upper_band = hl2 + (multiplier * atr)
            lower_band = hl2 - (multiplier * atr)
            
            # Supertrend com proteção contra divisão por zero
            df['supertrend'] = close > lower_band
            
        return df
        
    except Exception as e:
        logging.warning(f"Erro no Supertrend: {e}")
        df['supertrend'] = [True] * len(df)
        return df

def detectar_candle_forte(df):
    """Detecta candle com corpo forte vs sombras - versão protegida"""
    if len(df) < 2:
        return False
    
    try:
        candle = df.iloc[-1]
        
        # Validar dados do candle
        if pd.isna([candle['open'], candle['high'], candle['low'], candle['close']]).any():
            return False
        
        corpo = abs(candle['close'] - candle['open'])
        sombra_sup = candle['high'] - max(candle['close'], candle['open'])
        sombra_inf = min(candle['close'], candle['open']) - candle['low']
        
        # Proteger contra divisão por zero
        if corpo == 0:
            return False
        
        return corpo > sombra_sup and corpo > sombra_inf
        
    except Exception as e:
        logging.warning(f"Erro ao detectar candle forte: {e}")
        return False

def detectar_engolfo_alta(df):
    """Detecta padrão de engolfo de alta - versão protegida"""
    if len(df) < 2:
        return False
    
    try:
        c1 = df.iloc[-2]  # Anterior
        c2 = df.iloc[-1]  # Atual
        
        # Validar dados
        colunas = ['open', 'high', 'low', 'close']
        if pd.isna([c1[col] for col in colunas] + [c2[col] for col in colunas]).any():
            return False
        
        return (c2['close'] > c2['open'] and     # Atual de alta
                c1['close'] < c1['open'] and     # Anterior de baixa
                c2['open'] < c1['close'] and     # Abertura atual < fechamento anterior
                c2['close'] > c1['open'])        # Fechamento atual > abertura anterior
                
    except Exception as e:
        logging.warning(f"Erro ao detectar engolfo: {e}")
        return False

def detectar_martelo(df):
    """Detecta padrão de martelo - versão protegida"""
    if len(df) < 1:
        return False
        
    try:
        c = df.iloc[-1]
        
        # Validar dados
        if pd.isna([c['open'], c['high'], c['low'], c['close']]).any():
            return False
        
        corpo = abs(c['close'] - c['open'])
        sombra_inf = min(c['close'], c['open']) - c['low']
        sombra_sup = c['high'] - max(c['close'], c['open'])
        
        # Proteger contra casos extremos
        if corpo == 0 or sombra_inf == 0:
            return False
        
        return sombra_inf > corpo * 2 and sombra_sup < corpo
        
    except Exception as e:
        logging.warning(f"Erro ao detectar martelo: {e}")
        return False

# ===============================
# === SETUPS DE TRADING (ORIGINAIS COM PROTEÇÕES)
# ===============================

def verificar_setup_rigoroso(r, df):
    """Setup 1 - Rigoroso com validações melhoradas"""
    try:
        # Validar dados essenciais
        campos_necessarios = ['rsi', 'ema9', 'ema21', 'macd', 'macd_signal', 'adx']
        for campo in campos_necessarios:
            if pd.isna(r[campo]):
                return None
        
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
    except Exception as e:
        logging.warning(f"Erro no setup rigoroso: {e}")
        
    return None

def verificar_setup_alta_confluencia(r, df):
    """Setup 5 - Alta Confluência com validações"""
    try:
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
        
        # Verificar se pelo menos 6 condições são atendidas
        condicoes_validas = [c for c in condicoes if not pd.isna(c)]
        if sum(condicoes_validas) >= 6:
            return {
                'setup': '🔥 SETUP ALTA CONFLUÊNCIA',
                'prioridade': '🟥 PRIORIDADE MÁXIMA',
                'emoji': '🔥',
                'id': 'setup_alta_confluencia'
            }
    except Exception as e:
        logging.warning(f"Erro no setup alta confluência: {e}")
        
    return None

def verificar_setup_rompimento(r, df):
    """Setup 6 - Rompimento com proteções"""
    if len(df) < 10:
        return None
        
    try:
        resistencia = df['high'].iloc[-10:-1].max()
        if pd.isna(resistencia):
            return None
            
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
    except Exception as e:
        logging.warning(f"Erro no setup rompimento: {e}")
        
    return None

def verificar_setup_reversao_tecnica(r, df):
    """Setup 4 - Reversão Técnica com proteções"""
    if len(df) < 3:
        return None
        
    try:
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
    except Exception as e:
        logging.warning(f"Erro no setup reversão: {e}")
        
    return None

def verificar_setup_intermediario(r, df):
    """Setup 2 - Intermediário com proteções"""
    try:
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
    except Exception as e:
        logging.warning(f"Erro no setup intermediário: {e}")
        
    return None

def verificar_setup_leve(r, df):
    """Setup 3 - Leve com proteções"""
    try:
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
    except Exception as e:
        logging.warning(f"Erro no setup leve: {e}")
        
    return None

# ===============================
# === SCORE E ANÁLISE (MELHORADOS)
# ===============================

def calcular_score_setup(r, df, setup_id):
    """Score com validações e informações detalhadas"""
    score = 0
    total = 0
    criterios = []
    
    def conta(condicao, descricao, peso=1):
        nonlocal score, total
        total += peso
        try:
            if condicao:
                score += peso
                criterios.append(f"✅ {descricao}")
            else:
                criterios.append(f"❌ {descricao}")
        except Exception as e:
            criterios.append(f"⚠️ {descricao} (erro: {e})")
    
    # Critérios específicos por setup com valores detalhados
    try:
        if setup_id in ['setup_rigoroso', 'setup_alta_confluencia']:
            conta(r['rsi'] < 40, f"RSI < 40 (atual: {r['rsi']:.1f})")
            conta(df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and r['ema9'] > r['ema21'], 
                  f"Cruzamento EMA9 > EMA21 ({r['ema9']:.2f} vs {r['ema21']:.2f})")
            conta(r['macd'] > r['macd_signal'], 
                  f"MACD > Signal ({r['macd']:.4f} vs {r['macd_signal']:.4f})")
            conta(r['adx'] > 20, f"ADX > 20 (atual: {r['adx']:.1f})")
            
            volume_ratio = df['volume'].iloc[-1] / df['volume'].mean()
            conta(volume_ratio > 1.5, f"Volume 1.5x média (atual: {volume_ratio:.1f}x)")
            conta(df['supertrend'].iloc[-1], "Supertrend ativo")
            
            if setup_id == 'setup_alta_confluencia':
                atr_ratio = r['atr'] / df['atr'].mean()
                obv_ratio = r['obv'] / df['obv'].mean()
                conta(atr_ratio > 1.0, f"ATR > média ({atr_ratio:.1f}x)")
                conta(obv_ratio > 1.0, f"OBV > média ({obv_ratio:.1f}x)")
                conta(r['close'] > r['ema200'], 
                      f"Preço > EMA200 (${r['close']:.2f} vs ${r['ema200']:.2f})")
                conta(detectar_candle_forte(df), "Candle forte detectado")
                
        elif setup_id == 'setup_intermediario':
            conta(r['rsi'] < 50, f"RSI < 50 (atual: {r['rsi']:.1f})")
            conta(r['ema9'] > r['ema21'], f"EMA9 > EMA21 ({r['ema9']:.2f} vs {r['ema21']:.2f})")
            conta(r['macd'] > r['macd_signal'], "MACD > Signal")
            conta(r['adx'] > 15, f"ADX > 15 (atual: {r['adx']:.1f})")
            volume_ratio = df['volume'].iloc[-1] / df['volume'].mean()
            conta(volume_ratio > 1.0, f"Volume > média ({volume_ratio:.1f}x)")
            
        elif setup_id == 'setup_leve':
            conta(r['ema9'] > r['ema21'], f"EMA9 > EMA21")
            conta(r['adx'] > 15, f"ADX > 15 (atual: {r['adx']:.1f})")
            volume_ratio = df['volume'].iloc[-1] / df['volume'].mean()
            conta(volume_ratio > 1.0, f"Volume > média ({volume_ratio:.1f}x)")
            
        elif setup_id == 'setup_reversao_tecnica':
            obv_ratio = r['obv'] / df['obv'].mean()
            conta(obv_ratio > 1.0, f"OBV > média ({obv_ratio:.1f}x)")
            conta(df['close'].iloc[-2] > df['open'].iloc[-2], "Candle anterior de alta")
            conta(df['close'].iloc[-1] > df['close'].iloc[-2], "Candle atual em alta")
            conta(detectar_martelo(df) or detectar_engolfo_alta(df), "Padrão de reversão")
            conta(df['rsi'].iloc[-1] > df['rsi'].iloc[-2], "RSI em alta")
            
        elif setup_id == 'setup_rompimento':
            resistencia = df['high'].iloc[-10:-1].max()
            conta(r['close'] > resistencia, f"Rompimento resistência (${resistencia:.2f})")
            volume_ratio = df['volume'].iloc[-1] / df['volume'].mean()
            conta(volume_ratio > 1.0, f"Volume > média ({volume_ratio:.1f}x)")
            rsi_momentum = df['rsi'].iloc[-1] > df['rsi'].iloc[-2]
            conta(r['rsi'] > 55 and rsi_momentum, f"RSI forte e subindo ({r['rsi']:.1f})")
            conta(df['supertrend'].iloc[-1], "Supertrend ativo")
    
    except Exception as e:
        logging.error(f"Erro ao calcular score: {e}")
        return 0.0, [f"❌ Erro no cálculo: {str(e)[:50]}"]
    
    if total == 0:
        return 0.0, []
    
    score_final = round((score / total) * 10, 1)
    return score_final, criterios

def gerar_explicacao_score(score):
    """Explicação educativa melhorada"""
    if score >= 9:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal tem **confluência máxima** - múltiplos indicadores concordam. "
            "RSI em zona ideal, tendência clara, volume confirmando. "
            "Momento tecnicamente muito favorável para entrada."
        )
    elif score >= 7:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal tem **boa base técnica** - maioria dos indicadores alinhados. "
            "Alguns critérios neutros, mas oportunidade válida com gestão de risco."
        )
    elif score >= 5:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal tem **força moderada** - indicadores mistos. "
            "Algumas confirmações, mas faltam outras. Requer cautela extra."
        )
    else:
        return (
            "🔎 *Para Iniciantes:*\n"
            "Este sinal tem **baixa qualidade técnica** - indicadores divergentes. "
            "Não recomendado operar baseado apenas neste sinal."
        )

# ===============================
# === COMUNICAÇÃO TELEGRAM (MELHORADA)
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
    """Envia mensagem para o Telegram com melhor tratamento de erros"""
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
            logging.info("✅ Mensagem enviada ao Telegram com sucesso")
            return True
        else:
            logging.error(f"Erro Telegram ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        logging.error(f"Erro ao conectar com Telegram: {e}")
        return False

def enviar_alerta_completo(par, r, setup_info, df):
    """Envia alerta completo com informações detalhadas"""
    try:
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
        
        # Construir mensagem melhorada
        mensagem = (
            f"{setup_info['emoji']} *{setup_info['setup']}*\n"
            f"{setup_info['prioridade']}\n\n"
            f"📊 Par: `{par}`\n"
            f"💰 Preço: `{preco:,.2f}`\n"
            f"🎯 Alvo: `{alvo:,.2f}` ({'2.5x' if par == 'BTC/USDT' else '3.0x'} ATR)\n"
            f"🛑 Stop: `{stop:,.2f}` ({'1.2x' if par == 'BTC/USDT' else '1.5x'} ATR)\n\n"
            f"📊 *Força do Sinal:* {score:.1f} / 10\n"
            f"📌 *Análise Detalhada:*\n"
        )
        
        # Adicionar critérios (máximo 6 para não sobrecarregar)
        for criterio in criterios[:6]:
            mensagem += f"{criterio}\n"
        
        if len(criterios) > 6:
            mensagem += f"... e mais {len(criterios)-6} critérios\n"
        
        # Indicadores atuais com valores
        mensagem += (
            f"\n📈 *Indicadores Atuais:*\n"
            f"• RSI: {r['rsi']:.1f} | ADX: {r['adx']:.1f}\n"
            f"• ATR: {r['atr']:.4f} | Volume: {r['volume']:,.0f}\n"
            f"• EMA9: ${r['ema9']:.2f} | EMA21: ${r['ema21']:.2f}\n"
            f"• MACD: {r['macd']:.4f} | Signal: {r['macd_signal']:.4f}\n"
            f"🕘 {timestamp_br}\n"
            f"📉 [Ver gráfico]({link_tv})\n\n"
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
            
    except Exception as e:
        logging.error(f"Erro ao enviar alerta completo: {e}")
        return False

# ===============================
# === ANÁLISE PRINCIPAL (MELHORADA)
# ===============================

def analisar_par(exchange, par):
    """Análise principal de um par com melhorias de qualidade"""
    try:
        print(f"🔍 Analisando {par}...")
        
        # Buscar dados OHLCV
        ohlcv = exchange.fetch_ohlcv(par, timeframe, limit=limite_candles)
        if len(ohlcv) < limite_candles:
            print(f"⚠️ Dados insuficientes para {par}")
            return None
        
        # Criar DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Validar dados antes de prosseguir
        if not validar_dados(df, par):
            print(f"❌ Dados inválidos para {par}")
            return None
        
        # Calcular indicadores com proteção
        try:
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
            
        except Exception as e:
            logging.error(f"Erro ao calcular indicadores para {par}: {e}")
            return None
        
        # Verificar se indicadores foram calculados corretamente
        indicadores_principais = ['ema9', 'ema21', 'rsi', 'macd', 'adx']
        for ind in indicadores_principais:
            if df[ind].isna().iloc[-1]:
                print(f"⚠️ Indicador {ind} inválido para {par}")
                return None
        
        # Dados da linha atual
        r = df.iloc[-1]
        
        # Verificar setups em ordem de prioridade
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
# === FUNÇÃO PRINCIPAL (MELHORADA)
# ===============================

def executar_scanner():
    """Função principal do scanner com melhorias de qualidade"""
    try:
        print("🚀 INICIANDO SCANNER GITHUB ACTIONS - ETH/BTC FOCUS")
        print(f"⏰ Executado em: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"📊 Pares: {', '.join(PARES_ALVOS)}")
        print(f"📈 Timeframe: {timeframe}")
        
        # Inicializar exchange com configurações otimizadas
        exchange = ccxt.okx({
            'enableRateLimit': True,
            'timeout': 30000,  # 30 segundos timeout
            'rateLimit': 100   # Limite de requisições
        })
        
        # Carregar mercados com retry
        for tentativa in range(3):
            try:
                exchange.load_markets()
                break
            except Exception as e:
                if tentativa == 2:
                    raise e
                print(f"Tentativa {tentativa + 1} de conectar à exchange...")
                time.sleep(2)
        
        # Verificar se pares existem
        pares_validos = []
        for par in PARES_ALVOS:
            if par in exchange.markets:
                pares_validos.append(par)
            else:
                print(f"❌ Par {par} não encontrado na OKX")
        
        if not pares_validos:
            raise Exception("Nenhum par válido encontrado")
        
        # Verificar sinais em aberto primeiro
        try:
            print("🔍 Verificando sinais em aberto...")
            sinais_atualizados = verificar_sinais_monitorados(exchange)
            if sinais_atualizados:
                print(f"📊 {len(sinais_atualizados)} sinais foram atualizados")
        except Exception as e:
            logging.error(f"Erro ao verificar sinais: {e}")
        
        # Analisar cada par válido
        alertas_enviados_count = 0
        analises_realizadas = []
        
        for par in pares_validos:
            try:
                print(f"\n--- Iniciando análise de {par} ---")
                resultado = analisar_par(exchange, par)
                
                if resultado:
                    alertas_enviados_count += 1
                    analises_realizadas.append(f"✅ {par}: Sinal encontrado")
                else:
                    analises_realizadas.append(f"📊 {par}: Análise completa, sem sinais")
                
                # Pequena pausa entre análises
                time.sleep(2)
                
            except Exception as e:
                logging.error(f"Erro ao analisar {par}: {e}")
                analises_realizadas.append(f"❌ {par}: Erro na análise")
        
        # Resumo final melhorado
        print(f"\n✅ SCANNER FINALIZADO")
        print(f"📨 Alertas enviados: {alertas_enviados_count}")
        print(f"📊 Análises realizadas: {len(analises_realizadas)}")
        for analise in analises_realizadas:
            print(f"   {analise}")
        print(f"🕒 Próxima execução: em 15 minutos")
        
        # SEMPRE enviar status quando não há sinais (ETAPA 1 - MELHORIA PRINCIPAL)
        if alertas_enviados_count == 0:
            agora = datetime.datetime.utcnow().strftime('%H:%M UTC')
            
            # Verificar quantos sinais estão em aberto
            sinais = carregar_sinais_monitorados()
            sinais_abertos = len([s for s in sinais if s['status'] == 'em_aberto'])
            
            # Coletar dados atuais para status detalhado
            status_pares = []
            for par in pares_validos:
                try:
                    ticker = exchange.fetch_ticker(par)
                    preco_atual = ticker['last']
                    
                    # Buscar dados básicos para RSI atual
                    ohlcv_basico = exchange.fetch_ohlcv(par, timeframe, limit=20)
                    if len(ohlcv_basico) >= 15:
                        df_temp = pd.DataFrame(ohlcv_basico, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        rsi_atual = RSIIndicator(df_temp['close'], 14).rsi().iloc[-1]
                        
                        if not pd.isna(rsi_atual):
                            status_pares.append(f"• {par}: ${preco_atual:,.2f} | RSI: {rsi_atual:.1f}")
                        else:
                            status_pares.append(f"• {par}: ${preco_atual:,.2f} | RSI: calculando...")
                    else:
                        status_pares.append(f"• {par}: ${preco_atual:,.2f}")
                        
                except Exception as e:
                    status_pares.append(f"• {par}: Erro ao obter dados")
            
            # Mensagem de status detalhada
            mensagem_status = (
                f"🤖 *Scanner ETH/BTC - Relatório*\n\n"
                f"⏰ Executado às {agora}\n"
                f"🔍 Análise: 6 setups por moeda\n"
                f"📈 Resultado: Nenhum novo sinal\n"
                f"📝 Sinais monitorados: {sinais_abertos}\n\n"
                f"💰 *Preços Atuais:*\n"
                + "\n".join(status_pares) +
                f"\n\n💭 *Setups Verificados:*\n"
                f"• RSI Oversold + MACD Bullish\n"
                f"• Alta Confluência de Indicadores\n"
                f"• Rompimentos de Resistência\n"
                f"• Reversões Técnicas\n"
                f"• Cruzamentos de Médias\n"
                f"• Padrões de Candlestick\n\n"
                f"📊 *Situação:* Aguardando condições técnicas favoráveis\n"
                f"⏰ Próxima verificação: 15 minutos\n"
                f"🎯 Sistema ativo e operacional"
            )
            
            # Enviar status detalhado
            if enviar_telegram(mensagem_status):
                print("✅ Status detalhado enviado ao Telegram")
            else:
                print("❌ Falha ao enviar status ao Telegram")
        
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
    print("🎯 SCANNER ETH/BTC - GitHub Actions (Etapa 1 - Melhorias de Qualidade)")
    print("📋 Baseado no script original com 6 setups")
    print("🔍 Focado exclusivamente em BTC/USDT e ETH/USDT")
    print("⚡ Execução otimizada com validações e logs melhorados\n")
    
    sucesso = executar_scanner()
    
    if sucesso:
        print("🎉 Scanner executado com sucesso!")
        exit(0)
    else:
        print("💥 Scanner falhou!")
        exit(1)
