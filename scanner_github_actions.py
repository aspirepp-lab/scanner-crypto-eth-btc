import ccxt
import pandas as pd
import time
import datetime
import requests
import os
import logging
import json
import warnings
from ta.trend import EMAIndicator, MACD, ADXIndicator, SMAIndicator
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator, VolumeSMAIndicator

# Suprimir warnings para logs limpos
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*invalid value encountered.*')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*divide by zero.*')

try:
    import pandas_ta as pta
except ImportError:
    print("⚠️ pandas_ta não disponível, usando cálculo manual")
    pta = def abreviar_valor(valor):
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
        total = requests.get("https://api.coingecko.com/api/v3/global", timeout=5).json()
        market_data = total.get('data', {})
        
        market_cap = market_data.get('total_market_cap', {}).get('usd')
        market_cap_change = market_data.get('market_cap_change_percentage_24h_usd', 0)
        btc_dominance = market_data.get('market_cap_percentage', {}).get('btc')
        
        if market_cap is None or btc_dominance is None:
            return "*Dados fundamentais indisponíveis*"
        
        emoji_cap = "📈" if market_cap_change >= 0 else "📉"
        
        # Contexto de mercado
        contexto = ""
        if market_cap_change < -3:
            contexto = "\n🔴 *Correção em curso*"
        elif market_cap_change > 3:
            contexto = "\n🟢 *Rally em andamento*"
        
        # Fear & Greed Index
        try:
            fg_response = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3).json()
            indice = fg_response['data'][0]
            valor_fg = int(indice['value'])
            
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
                
            fear_greed = f"{valor_fg} {emoji_fg} ({indice['value_classification']})"
        except:
            fear_greed = "Indisponível"
        
        return (
            f"*🌍 CONTEXTO MACRO:*\n"
            f"• Cap. Total: {abreviar_valor(market_cap)} {emoji_cap} ({market_cap_change:+.1f}%)\n"
            f"• Domínio BTC: {btc_dominance:.1f}%\n"
            f"• Fear & Greed: {fear_greed}"
            + contexto
        )
    
    except Exception as e:
        return "*Dados macro indisponíveis*"

def calcular_supertrend(df, period=10, multiplier=3):
    """Supertrend com proteções"""
    try:
        if pta:
            st_data = pta.supertrend(df['high'], df['low'], df['close'], length=period, multiplier=multiplier)
            if st_data is not None and len(st_data.columns) > 1:
                df['supertrend'] = st_data.iloc[:, 1] > 0
            else:
                df['supertrend'] = [True] * len(df)
        else:
            # Cálculo manual
            atr = AverageTrueRange(df['high'], df['low'], df['close'], period).average_true_range()
            atr = atr.fillna(method='bfill').fillna(method='ffill')
            
            hl2 = (df['high'] + df['low']) / 2
            upper_band = hl2 + (multiplier * atr)
            lower_band = hl2 - (multiplier * atr)
            
            df['supertrend'] = df['close'] > lower_band
        
        return df
    except Exception as e:
        df['supertrend'] = [True] * len(df)
        return df

# Funções de detecção de padrões (mantidas da Etapa 1)
def detectar_candle_forte(df):
    if len(df) < 2:
        return False
    try:
        candle = df.iloc[-1]
        if pd.isna([candle['open'], candle['high'], candle['low'], candle['close']]).any():
            return False
        
        corpo = abs(candle['close'] - candle['open'])
        sombra_sup = candle['high'] - max(candle['close'], candle['open'])
        sombra_inf = min(candle['close'], candle['open']) - candle['low']
        
        if corpo == 0:
            return False
        
        return corpo > sombra_sup and corpo > sombra_inf
    except:
        return False

def detectar_engolfo_alta(df):
    if len(df) < 2:
        return False
    try:
        c1, c2 = df.iloc[-2], df.iloc[-1]
        return (c2['close'] > c2['open'] and c1['close'] < c1['open'] and
                c2['open'] < c1['close'] and c2['close'] > c1['open'])
    except:
        return False

def detectar_martelo(df):
    if len(df) < 1:
        return False
    try:
        c = df.iloc[-1]
        corpo = abs(c['close'] - c['open'])
        sombra_inf = min(c['close'], c['open']) - c['low']
        sombra_sup = c['high'] - max(c['close'], c['open'])
        
        return corpo > 0 and sombra_inf > corpo * 2 and sombra_sup < corpo
    except:
        return False

# ===============================
# === SETUPS ORIGINAIS (MANTIDOS)
# ===============================

def verificar_setup_rigoroso(r, df):
    try:
        campos = ['rsi', 'ema9', 'ema21', 'macd', 'macd_signal', 'adx']
        if any(pd.isna(r[campo]) for campo in campos):
            return None
        
        condicoes = [
            r['rsi'] < 40,
            df['ema9'].iloc[-2] < df['ema21'].iloc[-2] and r['ema9'] > r['ema21'],
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
    except:
        pass
    return None

def verificar_setup_alta_confluencia(r, df):
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
        
        if sum(condicoes) >= 6:
            return {
                'setup': '🔥 SETUP ALTA CONFLUÊNCIA',
                'prioridade': '🟥 PRIORIDADE MÁXIMA',
                'emoji': '🔥',
                'id': 'setup_alta_confluencia'
            }
    except:
        pass
    return None

def verificar_setup_rompimento(r, df):
    if len(df) < 10:
        return None
    try:
        resistencia = df['high'].iloc[-10:-1].max()
        if pd.isna(resistencia):
            return None
            
        condicoes = [
            r['close'] > resistencia,
            df['volume'].iloc[-1] > df['volume'].mean(),
            r['rsi'] > 55 and df['rsi'].iloc[-1] > df['rsi'].iloc[-2],
            df['supertrend'].iloc[-1]
        ]
        
        if all(condicoes):
            return {
                'setup': '🚀 SETUP ROMPIMENTO',
                'prioridade': '🟩 ALTA OPORTUNIDADE',
                'emoji': '🚀',
                'id': 'setup_rompimento'
            }
    except:
        pass
    return None

def verificar_setup_reversao_tecnica(r, df):
    if len(df) < 3:
        return None
    try:
        condicoes = [
            r['obv'] > df['obv'].mean(),
            df['close'].iloc[-2] > df['open'].iloc[-2],
            df['close'].iloc[-1] > df['close'].iloc[-2],
            detectar_martelo(df) or detectar_engolfo_alta(df),
            df['rsi'].iloc[-1] > df['rsi'].iloc[-2]
        ]
        
        if all(condicoes):
            return {
                'setup': '🔁 SETUP REVERSÃO TÉCNICA',
                'prioridade': '🟣 OPORTUNIDADE DE REVERSÃO',
                'emoji': '🔁',
                'id': 'setup_reversao_tecnica'
            }
    except:
        pass
    return None

def verificar_setup_intermediario(r, df):
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
    except:
        pass
    return None

def verificar_setup_leve(r, df):
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
    except:
        pass
    return None

# ===============================
# === ANÁLISE AVANÇADA
# ===============================

def calcular_score_avancado(analise_tf, setup_info):
    """Score avançado considerando múltiplos timeframes"""
    try:
        score_base = setup_info.get('score_base', 7.0)
        bonus = 0
        criterios = []
        
        # Bonus por confluência de timeframes
        if len(analise_tf) > 1:
            tendencias = [tf['tendencia'] for tf in analise_tf.values() if tf.get('status') == 'ok']
            if len(set(tendencias)) == 1 and tendencias[0] in ['alta', 'alta_forte']:
                bonus += 1.0
                criterios.append("✅ Confluência entre timeframes")
            else:
                criterios.append("❌ Timeframes divergentes")
        
        # Bonus por força geral
        forcas = [tf['forca'] for tf in analise_tf.values() if tf.get('status') == 'ok']
        if forcas and min(forcas) >= 6:
            bonus += 0.5
            criterios.append("✅ Força consistente")
        
        # Bonus por volatilidade adequada
        volatilidades = [tf['volatilidade'] for tf in analise_tf.values() if tf.get('status') == 'ok']
        if 'normal' in volatilidades or 'alta' in volatilidades:
            bonus += 0.3
            criterios.append("✅ Volatilidade adequada")
        
        score_final = min(score_base + bonus, 10.0)
        return score_final, criterios
        
    except Exception as e:
        return 7.0, [f"Erro no score: {e}"]

def pode_enviar_alerta(par, setup):
    agora = datetime.datetime.utcnow()
    chave = f"{par}_{setup}"
    
    if chave in alertas_enviados:
        delta = (agora - alertas_enviados[chave]).total_seconds()
        if delta < TEMPO_REENVIO:
            return False
    
    alertas_enviados[chave] = agora
    return True

def enviar_telegram(mensagem):
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
        return response.status_code == 200
    except:
        return False

def enviar_alerta_avancado(par, analise_tf, setup_info):
    """Envia alerta com análise de múltiplos timeframes"""
    try:
        # Dados do timeframe principal (1h)
        tf_principal = analise_tf.get('1h', {})
        if tf_principal.get('status') != 'ok':
            return False
        
        preco = tf_principal['preco']
        
        # Score avançado
        score, criterios_bonus = calcular_score_avancado(analise_tf, setup_info)
        score_visual = gerar_score_visual(score)
        risco = categorizar_risco(score)
        
        # Calcular alvos baseados no ATR
        df_1h = tf_principal['df']
        atr = df_1h['atr'].iloc[-1]
        
        if par == 'BTC/USDT':
            stop = round(preco - (atr * 1.2), 2)
            alvo = round(preco + (atr * 2.5), 2)
        else:
            stop = round(preco - (atr * 1.5), 2)
            alvo = round(preco + (atr * 3.0), 2)
        
        # Timestamp
        agora_utc = datetime.datetime.utcnow()
        agora_br = agora_utc - datetime.timedelta(hours=3)
        timestamp = agora_br.strftime('%d/%m %H:%M (BR)')
        
        # Link TradingView
        symbol_tv = par.replace("/", "")
        link_tv = f"https://www.tradingview.com/chart/?symbol=OKX:{symbol_tv}"
        
        # Dados fundamentais
        contexto_macro = obter_dados_fundamentais()
        
        # Construir mensagem avançada
        mensagem = (
            f"{setup_info['emoji']} *{setup_info['setup']}*\n"
            f"{setup_info['prioridade']}\n\n"
            f"📊 Par: `{par}`\n"
            f"💰 Preço: `${preco:,.2f}`\n"
            f"🎯 Alvo: `${alvo:,.2f}`\n"
            f"🛑 Stop: `${stop:,.2f}`\n\n"
            f"📊 *Score:* {score_visual}\n"
            f"🎲 *Risco:* {risco['emoji']} {risco['nivel']}\n\n"
        )
        
        # Análise por timeframe
        mensagem += "*📈 ANÁLISE TIMEFRAMES:*\n"
        for tf, dados in analise_tf.items():
            if dados.get('status') == 'ok':
                tendencia_emoji = {
                    'alta_forte': '🚀',
                    'alta': '📈', 
                    'lateral': '➡️',
                    'baixa': '📉',
                    'baixa_forte': '💥'
                }.get(dados['tendencia'], '❓')
                
                vol_emoji = {
                    'alta': '🔥',
                    'normal': '🟡',
                    'baixa': '😴'
                }.get(dados['volatilidade'], '❓')
                
                mensagem += (
                    f"• {tf}: {tendencia_emoji} {dados['tendencia']} "
                    f"(força: {dados['forca']}/10, vol: {vol_emoji})\n"
                )
        
        # Indicadores atuais
        r = tf_principal['df'].iloc[-1]
        mensagem += (
            f"\n*📊 INDICADORES ATUAIS:*\n"
            f"• RSI: {r['rsi']:.1f} | StochRSI: {r.get('stoch_rsi', 0)*100:.1f}\n"
            f"• ADX: {r['adx']:.1f} | MACD: {r['macd']:.4f}\n"
            f"• Volume: {tf_principal['volume_ratio']:.1f}x média\n"
            f"• ATR: {r['atr']:.4f}\n\n"
        )
        
        # Critérios de bonus
        if criterios_bonus:
            mensagem += "*🎁 BONUS CONFLUÊNCIA:*\n"
            for criterio in criterios_bonus[:3]:
                mensagem += f"{criterio}\n"
            mensagem += "\n"
        
        # Contexto e detalhes específicos do setup
        if 'timeframes' in setup_info:
            mensagem += f"*📋 DETALHES:*\n{setup_info['timeframes']}\n\n"
        
        if 'detalhes' in setup_info:
            mensagem += f"*📋 ESPECÍFICOS:*\n{setup_info['detalhes']}\n\n"
        
        mensagem += f"{contexto_macro}\n\n"
        mensagem += f"🕘 {timestamp}\n"
        mensagem += f"📉 [TradingView]({link_tv})\n\n"
        
        # Explicação baseada no score
        if score >= 8.5:
            explicacao = (
                "*🎯 RECOMENDAÇÃO:*\n"
                "Setup de alta qualidade com múltiplas confirmações. "
                "Confluência entre timeframes detectada."
            )
        elif score >= 7.0:
            explicacao = (
                "*🎯 RECOMENDAÇÃO:*\n"
                "Setup sólido com boa base técnica. "
                "Gestão de risco recomendada."
            )
        else:
            explicacao = (
                "*🎯 RECOMENDAÇÃO:*\n"
                "Setup de qualidade moderada. "
                "Aguardar mais confirmações pode ser prudente."
            )
        
        mensagem += explicacao
        
        # Enviar alerta
        if pode_enviar_alerta(par, setup_info['setup']):
            if enviar_telegram(mensagem):
                print(f"✅ ALERTA AVANÇADO: {par} - {setup_info['setup']} (score: {score})")
                
                # Registrar sinal
                registrar_sinal_monitorado(par, setup_info.get('id', ''), preco, alvo, stop)
                return True
        
        return False
        
    except Exception as e:
        logging.error(f"Erro no relatório status avançado: {e}")

# ===============================
# === FUNÇÕES AUXILIARES FINAIS
# ===============================

def gerar_resumo_estatisticas():
    """Resumo das estatísticas coletadas"""
    try:
        with open(ARQUIVO_ESTATISTICAS, 'r') as f:
            stats = json.load(f)
        
        resumo = stats.get("resumo", {})
        sinais_24h = resumo.get("sinais_24h", 0)
        
        return f"📊 Performance 24h: {sinais_24h} sinais detectados"
    except:
        return "📊 Coletando estatísticas..."

def salvar_estatisticas(par, timeframe, tendencia, forca, sinais_encontrados):
    """Salva estatísticas de performance"""
    try:
        try:
            with open(ARQUIVO_ESTATISTICAS, 'r') as f:
                stats = json.load(f)
        except FileNotFoundError:
            stats = {"analises": [], "resumo": {}}
        
        nova_analise = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "par": par,
            "timeframe": timeframe,
            "tendencia": tendencia,
            "forca": forca,
            "sinais": sinais_encontrados
        }
        
        stats["analises"].append(nova_analise)
        
        # Manter últimas 150 análises
        if len(stats["analises"]) > 150:
            stats["analises"] = stats["analises"][-150:]
        
        # Atualizar resumo das últimas 24h
        agora = datetime.datetime.utcnow()
        sinais_24h = 0
        
        for analise in stats["analises"]:
            dt_analise = datetime.datetime.fromisoformat(analise["timestamp"])
            if (agora - dt_analise).total_seconds() <= 86400 and analise["sinais"] > 0:
                sinais_24h += 1
        
        stats["resumo"] = {
            "ultima_atualizacao": agora.isoformat(),
            "total_analises": len(stats["analises"]),
            "sinais_24h": sinais_24h
        }
        
        with open(ARQUIVO_ESTATISTICAS, 'w') as f:
            json.dump(stats, f, indent=2)
            
    except Exception as e:
        logging.error(f"Erro ao salvar estatísticas: {e}")

# ===============================
# === EXECUÇÃO PRINCIPAL
# ===============================

if __name__ == "__main__":
    print("🎯 SCANNER ETH/BTC AVANÇADO - ETAPA 2")
    print("📋 Múltiplos timeframes + Setups avançados")
    print("🔍 Confluência entre 1h e 4h")
    print("⚡ Análise premium com score visual\n")
    
    sucesso = executar_scanner_avancado()
    
    if sucesso:
        print("🎉 Scanner avançado executado com sucesso!")
        exit(0)
    else:
        print("💥 Scanner avançado falhou!")
        exit(1)Erro ao enviar alerta avançado: {e}")
        return False

# ===============================
# === ANÁLISE PRINCIPAL AVANÇADA
# ===============================

def analisar_par_avancado(exchange, par):
    """Análise principal com múltiplos timeframes"""
    try:
        print(f"🔍 Análise avançada de {par}...")
        
        # Analisar múltiplos timeframes
        analise_tf = analisar_multiplos_timeframes(exchange, par)
        
        # Verificar se temos dados válidos
        dados_validos = any(tf.get('status') == 'ok' for tf in analise_tf.values())
        if not dados_validos:
            print(f"⚠️ Dados insuficientes para {par}")
            return []
        
        sinais_encontrados = []
        
        # Setup especial: Confluência entre timeframes
        setup_confluencia = verificar_confluencia_timeframes(analise_tf, par)
        if setup_confluencia:
            if enviar_alerta_avancado(par, analise_tf, setup_confluencia):
                sinais_encontrados.append(setup_confluencia)
        
        # Analisar setups em cada timeframe
        for tf, dados in analise_tf.items():
            if dados.get('status') != 'ok':
                continue
                
            df = dados['df']
            r = df.iloc[-1]
            
            # Setups avançados específicos do timeframe
            setups_avancados = [
                verificar_breakout_volume_avancado,
                verificar_squeeze_bollinger,
                verificar_divergencia_rsi
            ]
            
            for verificar_setup in setups_avancados:
                try:
                    if verificar_setup == verificar_divergencia_rsi:
                        setup_info = verificar_setup(df)
                    else:
                        setup_info = verificar_setup(r, df)
                        
                    if setup_info:
                        # Criar análise simplificada para este setup
                        analise_single = {tf: dados}
                        if enviar_alerta_avancado(par, analise_single, setup_info):
                            sinais_encontrados.append(setup_info)
                            
                except Exception as e:
                    logging.warning(f"Erro em setup avançado: {e}")
            
            # Setups originais também
            setups_originais = [
                verificar_setup_alta_confluencia,
                verificar_setup_rigoroso,
                verificar_setup_rompimento,
                verificar_setup_reversao_tecnica,
                verificar_setup_intermediario,
                verificar_setup_leve
            ]
            
            for verificar_setup in setups_originais:
                try:
                    setup_info = verificar_setup(r, df)
                    if setup_info:
                        analise_single = {tf: dados}
                        if enviar_alerta_avancado(par, analise_single, setup_info):
                            sinais_encontrados.append(setup_info)
                            break  # Apenas um setup original por timeframe
                except Exception as e:
                    logging.warning(f"Erro em setup original: {e}")
        
        # Salvar estatísticas
        for tf, dados in analise_tf.items():
            if dados.get('status') == 'ok':
                salvar_estatisticas(par, tf, dados['tendencia'], dados['forca'], len(sinais_encontrados))
        
        return sinais_encontrados
        
    except Exception as e:
        logging.error(f"Erro na análise avançada de {par}: {e}")
        return []

# ===============================
# === FUNÇÃO PRINCIPAL AVANÇADA
# ===============================

def executar_scanner_avancado():
    """Scanner principal com funcionalidades avançadas"""
    try:
        print("🚀 SCANNER AVANÇADO ETH/BTC - ETAPA 2")
        print(f"⏰ Executado em: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"📊 Pares: {', '.join(PARES_ALVOS)}")
        print(f"📈 Timeframes: {', '.join(TIMEFRAMES)}")
        
        # Inicializar exchange
        exchange = ccxt.okx({'enableRateLimit': True, 'timeout': 30000})
        
        # Conectar com retry
        for tentativa in range(3):
            try:
                exchange.load_markets()
                break
            except Exception as e:
                if tentativa == 2:
                    raise e
                time.sleep(2)
        
        # Verificar sinais em aberto
        print("🔍 Verificando sinais monitorados...")
        sinais_atualizados = verificar_sinais_monitorados(exchange)
        
        # Analisar cada par
        total_sinais = 0
        relatorio_completo = []
        
        for par in PARES_ALVOS:
            if par not in exchange.markets:
                continue
                
            print(f"\n🎯 Iniciando análise avançada: {par}")
            sinais = analisar_par_avancado(exchange, par)
            total_sinais += len(sinais)
            
            # Coletar dados para relatório
            try:
                ticker = exchange.fetch_ticker(par)
                preco = ticker['last']
                
                # RSI básico para o relatório
                ohlcv = exchange.fetch_ohlcv(par, '1h', limit=20)
                df_temp = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                rsi = RSIIndicator(df_temp['close'], 14).rsi().iloc[-1]
                
                relatorio_completo.append({
                    'par': par,
                    'preco': preco,
                    'rsi': rsi if not pd.isna(rsi) else 0,
                    'sinais': len(sinais)
                })
                
            except Exception as e:
                relatorio_completo.append({
                    'par': par,
                    'preco': 0,
                    'rsi': 0,
                    'sinais': len(sinais)
                })
            
            time.sleep(1)  # Rate limiting
        
        print(f"\n✅ SCANNER AVANÇADO FINALIZADO")
        print(f"📨 Total de sinais enviados: {total_sinais}")
        
        # Enviar relatório de status se não houver sinais
        if total_sinais == 0:
            enviar_relatorio_status_avancado(relatorio_completo)
        
        return True
        
    except Exception as e:
        logging.error(f"Erro crítico no scanner avançado: {e}")
        
        # Alerta de erro
        if TOKEN != "dummy_token":
            mensagem_erro = (
                f"🚨 *ERRO SCANNER AVANÇADO*\n\n"
                f"❌ {str(e)[:80]}...\n"
                f"⏰ {datetime.datetime.utcnow().strftime('%H:%M UTC')}"
            )
            enviar_telegram(mensagem_erro)
        
        return False

def enviar_relatorio_status_avancado(relatorio):
    """Envia relatório de status avançado"""
    try:
        agora = datetime.datetime.utcnow().strftime('%H:%M UTC')
        
        # Sinais monitorados
        sinais = carregar_sinais_monitorados()
        sinais_abertos = len([s for s in sinais if s['status'] == 'em_aberto'])
        
        # Estatísticas
        stats_resumo = gerar_resumo_estatisticas()
        
        mensagem = (
            f"🤖 *Scanner Avançado ETH/BTC*\n"
            f"📊 *RELATÓRIO TIMEFRAMES MÚLTIPLOS*\n\n"
            f"⏰ Executado às {agora}\n"
            f"🔍 Análise: Timeframes 1h + 4h\n"
            f"📈 Resultado: Aguardando oportunidades\n"
            f"📝 Sinais ativos: {sinais_abertos}\n\n"
        )
        
        # Status por par
        mensagem += "*💰 ANÁLISE DETALHADA:*\n"
        for item in relatorio:
            par = item['par']
            preco = item['preco']
            rsi = item['rsi']
            
            # Análise do RSI
            if rsi < 25:
                rsi_status = "🔥 Oversold extremo"
            elif rsi < 35:
                rsi_status = "🟠 Oversold"
            elif rsi > 75:
                rsi_status = "🔴 Overbought"
            elif rsi > 65:
                rsi_status = "🟡 Overbought leve"
            else:
                rsi_status = "🟢 Neutro"
            
            mensagem += f"• {par}: ${preco:,.2f}\n"
            mensagem += f"  RSI: {rsi:.1f} ({rsi_status})\n"
        
        # Setups monitorados
        mensagem += (
            f"\n*🔍 SETUPS MONITORADOS:*\n"
            f"• Confluência Timeframes (1h+4h)\n"
            f"• Bollinger Squeeze (explosão)\n"
            f"• Divergências RSI\n"
            f"• Breakouts com Volume\n"
            f"• + 6 setups originais\n\n"
            f"{stats_resumo}\n\n"
            f"⏰ Próxima análise: 15 minutos\n"
            f"🎯 Scanner Avançado ativo"
        )
        
        if enviar_telegram(mensagem):
            print("✅ Relatório avançado enviado")
        else:
            print("❌ Falha no envio do relatório")
            
    except Exception as e:
        logging.error(f"

# ===============================
# === CONFIGURAÇÕES AVANÇADAS
# ===============================
PARES_ALVOS = ['BTC/USDT', 'ETH/USDT']
TIMEFRAMES = ['1h', '4h']  # Múltiplos timeframes
limite_candles = 200  # Mais dados para análise avançada
TEMPO_REENVIO = 60 * 30

# Configurações do Telegram
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not TOKEN or not CHAT_ID:
    print("⚠️ AVISO: Configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID para receber alertas")
    TOKEN = "dummy_token"
    CHAT_ID = "dummy_chat"

# Arquivos de dados
ARQUIVO_SINAIS_MONITORADOS = 'sinais_monitorados.json'
ARQUIVO_ESTATISTICAS = 'estatisticas_scanner.json'

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Controle de alertas
alertas_enviados = {}

# ===============================
# === SISTEMA DE MÚLTIPLOS TIMEFRAMES
# ===============================

def analisar_multiplos_timeframes(exchange, par):
    """Analisa o mesmo par em múltiplos timeframes"""
    resultados = {}
    
    for tf in TIMEFRAMES:
        try:
            print(f"    📈 Timeframe {tf}...")
            ohlcv = exchange.fetch_ohlcv(par, tf, limit=limite_candles)
            
            if len(ohlcv) < 100:
                resultados[tf] = {'status': 'dados_insuficientes', 'candles': len(ohlcv)}
                continue
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = limpar_dados(df)
            
            if not validar_dados(df, f"{par}_{tf}"):
                resultados[tf] = {'status': 'dados_invalidos'}
                continue
                
            # Calcular indicadores completos
            df = calcular_indicadores_completos(df)
            
            # Análise de tendência
            tendencia = determinar_tendencia(df)
            forca_tendencia = calcular_forca_tendencia(df)
            volatilidade = calcular_volatilidade(df)
            
            r = df.iloc[-1]
            
            resultados[tf] = {
                'status': 'ok',
                'df': df,
                'tendencia': tendencia,
                'forca': forca_tendencia,
                'volatilidade': volatilidade,
                'preco': r['close'],
                'rsi': r['rsi'],
                'adx': r['adx'],
                'macd': r['macd'],
                'macd_signal': r['macd_signal'],
                'volume_ratio': df['volume'].iloc[-1] / df['volume'].mean()
            }
            
        except Exception as e:
            logging.error(f"Erro no timeframe {tf} para {par}: {e}")
            resultados[tf] = {'status': 'erro', 'erro': str(e)}
    
    return resultados

def determinar_tendencia(df):
    """Determina tendência baseada em múltiplos indicadores"""
    try:
        r = df.iloc[-1]
        
        # Critérios de tendência
        ema_score = 0
        if r['ema9'] > r['ema21'] > r['ema50'] > r['ema200']:
            ema_score = 2  # Forte alta
        elif r['ema9'] > r['ema21'] > r['ema50']:
            ema_score = 1  # Alta moderada
        elif r['ema9'] < r['ema21'] < r['ema50'] < r['ema200']:
            ema_score = -2  # Forte baixa
        elif r['ema9'] < r['ema21'] < r['ema50']:
            ema_score = -1  # Baixa moderada
        
        macd_score = 1 if r['macd'] > r['macd_signal'] else -1
        adx_multiplier = 1.5 if r['adx'] > 25 else 1.0 if r['adx'] > 20 else 0.5
        
        score_final = (ema_score + macd_score) * adx_multiplier
        
        if score_final >= 2.5:
            return "alta_forte"
        elif score_final >= 1.0:
            return "alta"
        elif score_final <= -2.5:
            return "baixa_forte"
        elif score_final <= -1.0:
            return "baixa"
        else:
            return "lateral"
            
    except Exception as e:
        logging.warning(f"Erro ao determinar tendência: {e}")
        return "indefinida"

def calcular_forca_tendencia(df):
    """Calcula força da tendência (0-10)"""
    try:
        r = df.iloc[-1]
        pontos = 0
        
        # ADX (0-3 pontos)
        if r['adx'] > 40:
            pontos += 3
        elif r['adx'] > 25:
            pontos += 2
        elif r['adx'] > 20:
            pontos += 1
        
        # Volume (0-2 pontos)
        volume_ratio = df['volume'].iloc[-1] / df['volume'].mean()
        if volume_ratio > 2.0:
            pontos += 2
        elif volume_ratio > 1.3:
            pontos += 1
        
        # Alinhamento EMAs (0-2 pontos)
        if r['ema9'] > r['ema21'] > r['ema50'] > r['ema200']:
            pontos += 2
        elif r['ema9'] > r['ema21'] > r['ema50']:
            pontos += 1
        
        # RSI momentum (0-2 pontos)
        if len(df) >= 5:
            rsi_change = df['rsi'].iloc[-1] - df['rsi'].iloc[-5]
            if abs(rsi_change) > 15:
                pontos += 2
            elif abs(rsi_change) > 8:
                pontos += 1
        
        # MACD momentum (0-1 ponto)
        if r['macd'] > r['macd_signal'] and df['macd'].iloc[-1] > df['macd'].iloc[-2]:
            pontos += 1
        
        return min(pontos, 10)
        
    except Exception as e:
        logging.warning(f"Erro ao calcular força: {e}")
        return 0

def calcular_volatilidade(df):
    """Calcula nível de volatilidade atual"""
    try:
        # ATR normalizado
        atr_atual = df['atr'].iloc[-1]
        atr_medio = df['atr'].mean()
        
        if atr_atual > atr_medio * 1.5:
            return "alta"
        elif atr_atual < atr_medio * 0.7:
            return "baixa"
        else:
            return "normal"
            
    except Exception as e:
        return "indefinida"

# ===============================
# === SETUPS AVANÇADOS (NOVOS)
# ===============================

def verificar_confluencia_timeframes(analise_tf, par):
    """Setup especial: Confluência entre timeframes"""
    try:
        tf_1h = analise_tf.get('1h', {})
        tf_4h = analise_tf.get('4h', {})
        
        if tf_1h.get('status') != 'ok' or tf_4h.get('status') != 'ok':
            return None
        
        # Critérios de confluência
        condicoes = []
        
        # Tendência alinhada
        tendencias_alta = tf_1h['tendencia'] in ['alta', 'alta_forte'] and tf_4h['tendencia'] in ['alta', 'alta_forte']
        condicoes.append(tendencias_alta)
        
        # Força adequada em ambos timeframes
        forca_ok = tf_1h['forca'] >= 6 and tf_4h['forca'] >= 5
        condicoes.append(forca_ok)
        
        # RSI em zona favorável
        rsi_1h_ok = 25 < tf_1h['rsi'] < 65
        rsi_4h_ok = tf_4h['rsi'] < 70
        condicoes.append(rsi_1h_ok and rsi_4h_ok)
        
        # MACD positivo em ambos
        macd_ok = tf_1h['macd'] > tf_1h['macd_signal'] and tf_4h['macd'] > tf_4h['macd_signal']
        condicoes.append(macd_ok)
        
        # Volume forte no 1h
        volume_ok = tf_1h['volume_ratio'] > 1.2
        condicoes.append(volume_ok)
        
        if sum(condicoes) >= 4:  # Pelo menos 4 de 5 critérios
            return {
                'setup': '🌟 CONFLUÊNCIA TIMEFRAMES',
                'prioridade': '🔴 SINAL PREMIUM',
                'emoji': '🌟',
                'id': 'confluencia_timeframes',
                'score_base': 9.0,
                'timeframes': f"1h: {tf_1h['tendencia']} (força {tf_1h['forca']}) | 4h: {tf_4h['tendencia']} (força {tf_4h['forca']})"
            }
            
    except Exception as e:
        logging.error(f"Erro na confluência timeframes: {e}")
    
    return None

def verificar_squeeze_bollinger(r, df):
    """Setup avançado: Bollinger Band Squeeze"""
    try:
        # Calcular Bollinger Bands se não existir
        if 'bb_upper' not in df.columns:
            bollinger = BollingerBands(df['close'], 20, 2)
            df['bb_upper'] = bollinger.bollinger_hband()
            df['bb_lower'] = bollinger.bollinger_lband()
            df['bb_middle'] = bollinger.bollinger_mavg()
        
        # Largura das bandas (volatilidade)
        bb_width = (r['bb_upper'] - r['bb_lower']) / r['bb_middle']
        bb_width_avg = ((df['bb_upper'] - df['bb_lower']) / df['bb_middle']).rolling(20).mean().iloc[-1]
        
        # Squeeze: volatilidade muito baixa
        squeeze_ativo = bb_width < bb_width_avg * 0.6
        
        # Preço próximo a uma das bandas
        dist_upper = abs(r['close'] - r['bb_upper']) / r['close']
        dist_lower = abs(r['close'] - r['bb_lower']) / r['close']
        proximo_banda = min(dist_upper, dist_lower) < 0.015  # 1.5%
        
        # Volume começando a aumentar
        volume_crescente = df['volume'].iloc[-3:].mean() > df['volume'].iloc[-6:-3].mean()
        
        # ADX baixo (sem tendência definida)
        adx_baixo = r['adx'] < 20
        
        if squeeze_ativo and proximo_banda and volume_crescente and adx_baixo:
            return {
                'setup': '🎪 BOLLINGER SQUEEZE',
                'prioridade': '🟣 EXPLOSÃO IMINENTE',
                'emoji': '🎪',
                'id': 'bollinger_squeeze',
                'score_base': 8.5
            }
            
    except Exception as e:
        logging.warning(f"Erro no Bollinger Squeeze: {e}")
    
    return None

def verificar_divergencia_rsi(df):
    """Setup avançado: Divergência RSI"""
    try:
        if len(df) < 30:
            return None
        
        # Últimos 20 candles para análise
        recent = df.tail(20).copy()
        
        # Encontrar máximas de preço e RSI
        recent['price_peak'] = recent['high'].rolling(3, center=True).max() == recent['high']
        recent['rsi_peak'] = recent['rsi'].rolling(3, center=True).max() == recent['rsi']
        
        price_peaks = recent[recent['price_peak']]['high']
        rsi_peaks = recent[recent['rsi_peak']]['rsi']
        
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            # Divergência bearish: preço sobe, RSI desce
            price_trend = price_peaks.iloc[-1] > price_peaks.iloc[-2]
            rsi_trend = rsi_peaks.iloc[-1] < rsi_peaks.iloc[-2]
            rsi_overbought = rsi_peaks.iloc[-1] > 65
            
            if price_trend and rsi_trend and rsi_overbought:
                return {
                    'setup': '📉 DIVERGÊNCIA RSI BEARISH',
                    'prioridade': '🟡 REVERSÃO POTENCIAL',
                    'emoji': '📉',
                    'id': 'divergencia_rsi',
                    'score_base': 7.5
                }
                
        # Divergência bullish: preço desce, RSI sobe
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            price_lows = recent[recent['low'].rolling(3, center=True).min() == recent['low']]['low']
            rsi_lows = recent[recent['rsi'].rolling(3, center=True).min() == recent['rsi']]['rsi']
            
            if len(price_lows) >= 2 and len(rsi_lows) >= 2:
                price_trend_down = price_lows.iloc[-1] < price_lows.iloc[-2]
                rsi_trend_up = rsi_lows.iloc[-1] > rsi_lows.iloc[-2]
                rsi_oversold = rsi_lows.iloc[-1] < 35
                
                if price_trend_down and rsi_trend_up and rsi_oversold:
                    return {
                        'setup': '📈 DIVERGÊNCIA RSI BULLISH',
                        'prioridade': '🟢 REVERSÃO ALTA PROVÁVEL',
                        'emoji': '📈',
                        'id': 'divergencia_rsi_bullish',
                        'score_base': 8.0
                    }
                
    except Exception as e:
        logging.warning(f"Erro na divergência RSI: {e}")
    
    return None

def verificar_breakout_volume_avancado(r, df):
    """Setup avançado: Breakout com confirmação de volume forte"""
    try:
        if len(df) < 20:
            return None
        
        # Resistência dos últimos 15 candles
        resistencia = df['high'].iloc[-15:-1].max()
        
        # Contar quantas vezes testou a resistência
        touches = ((df['high'].iloc[-15:-1] >= resistencia * 0.995) & 
                  (df['high'].iloc[-15:-1] <= resistencia * 1.005)).sum()
        
        # Resistência forte (testada pelo menos 3 vezes)
        resistencia_forte = touches >= 3
        
        # Breakout atual
        breakout = r['close'] > resistencia * 1.002  # 0.2% acima
        
        # Volume explosivo (pelo menos 3x a média)
        volume_explosivo = df['volume'].iloc[-1] > df['volume'].mean() * 3.0
        
        # RSI em zona saudável (não sobrecomprado)
        rsi_saudavel = 40 < r['rsi'] < 75
        
        # MACD confirmando
        macd_confirmando = r['macd'] > r['macd_signal']
        
        if resistencia_forte and breakout and volume_explosivo and rsi_saudavel and macd_confirmando:
            return {
                'setup': '💥 BREAKOUT VOLUME EXTREMO',
                'prioridade': '🔴 ALTA PROBABILIDADE',
                'emoji': '💥',
                'id': 'breakout_extremo',
                'score_base': 9.0,
                'detalhes': f"Resistência ${resistencia:.2f} testada {touches}x"
            }
            
    except Exception as e:
        logging.warning(f"Erro no breakout avançado: {e}")
    
    return None

# ===============================
# === INDICADORES COMPLETOS
# ===============================

def calcular_indicadores_completos(df):
    """Calcula conjunto completo de indicadores para análise avançada"""
    try:
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # Médias móveis múltiplas
        df['ema9'] = EMAIndicator(close, 9).ema_indicator()
        df['ema21'] = EMAIndicator(close, 21).ema_indicator()
        df['ema50'] = EMAIndicator(close, 50).ema_indicator()
        df['ema200'] = EMAIndicator(close, 200).ema_indicator()
        df['sma20'] = SMAIndicator(close, 20).sma_indicator()
        
        # Momentum
        df['rsi'] = RSIIndicator(close, 14).rsi()
        
        # StochRSI para sinais mais sensíveis
        try:
            stoch_rsi = StochRSIIndicator(close, 14, 3, 3)
            df['stoch_rsi'] = stoch_rsi.stochrsi()
        except:
            df['stoch_rsi'] = df['rsi'] / 100  # Fallback
        
        # Tendência
        macd = MACD(close)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_histogram'] = macd.macd_diff()
        
        df['adx'] = ADXIndicator(high, low, close, 14).adx()
        
        # Volatilidade
        df['atr'] = AverageTrueRange(high, low, close, 14).average_true_range()
        
        # Bollinger Bands
        bollinger = BollingerBands(close, 20, 2)
        df['bb_upper'] = bollinger.bollinger_hband()
        df['bb_middle'] = bollinger.bollinger_mavg()
        df['bb_lower'] = bollinger.bollinger_lband()
        
        # Volume
        df['obv'] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()
        df['volume_sma'] = VolumeSMAIndicator(volume, 20).volume_sma()
        
        # Supertrend
        df = calcular_supertrend(df)
        
        # Preencher valores NaN com método seguro
        for col in df.columns:
            if df[col].dtype in ['float64', 'int64'] and df[col].isna().sum() > 0:
                df[col] = df[col].fillna(method='bfill').fillna(method='ffill')
        
        return df
        
    except Exception as e:
        logging.error(f"Erro ao calcular indicadores completos: {e}")
        return df

# ===============================
# === SISTEMA DE SCORE VISUAL
# ===============================

def gerar_score_visual(score):
    """Gera representação visual do score"""
    if score >= 9.0:
        return "🟢🟢🟢🟢🟢 (Excelente)"
    elif score >= 8.0:
        return "🟢🟢🟢🟢🟡 (Muito Bom)"
    elif score >= 7.0:
        return "🟢🟢🟢🟡🟡 (Bom)"
    elif score >= 6.0:
        return "🟢🟢🟡🟡🟡 (Moderado)"
    elif score >= 5.0:
        return "🟢🟡🟡🟡🟡 (Fraco)"
    else:
        return "🟡🟡🟡⚫⚫ (Muito Fraco)"

def categorizar_risco(score):
    """Categoriza nível de risco"""
    if score >= 8.5:
        return {"nivel": "BAIXO", "emoji": "🟢", "cor": "Verde"}
    elif score >= 7.0:
        return {"nivel": "MÉDIO", "emoji": "🟡", "cor": "Amarelo"}
    elif score >= 5.5:
        return {"nivel": "ALTO", "emoji": "🟠", "cor": "Laranja"}
    else:
        return {"nivel": "MUITO ALTO", "emoji": "🔴", "cor": "Vermelho"}

# ===============================
# === ESTATÍSTICAS E HISTÓRICO
# ===============================

def salvar_estatisticas(par, timeframe, tendencia, forca, sinais_encontrados):
    """Salva estatísticas para análise de performance"""
    try:
        try:
            with open(ARQUIVO_ESTATISTICAS, 'r') as f:
                stats = json.load(f)
        except FileNotFoundError:
            stats = {"analises": [], "resumo": {}}
        
        nova_analise = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "par": par,
            "timeframe": timeframe,
            "tendencia": tendencia,
            "forca": forca,
            "sinais": sinais_encontrados
        }
        
        stats["analises"].append(nova_analise)
        
        # Manter apenas últimas 200 análises
        if len(stats["analises"]) > 200:
            stats["analises"] = stats["analises"][-200:]
        
        # Atualizar resumo
        stats["resumo"] = {
            "ultima_atualizacao": datetime.datetime.utcnow().isoformat(),
            "total_analises": len(stats["analises"]),
            "sinais_24h": len([a for a in stats["analises"] 
                              if (datetime.datetime.utcnow() - 
                                  datetime.datetime.fromisoformat(a["timestamp"])).days == 0 
                              and a["sinais"] > 0])
        }
        
        with open(ARQUIVO_ESTATISTICAS, 'w') as f:
            json.dump(stats, f, indent=2)
            
    except Exception as e:
        logging.error(f"Erro ao salvar estatísticas: {e}")

def gerar_resumo_estatisticas():
    """Gera resumo de estatísticas para incluir nas mensagens"""
    try:
        with open(ARQUIVO_ESTATISTICAS, 'r') as f:
            stats = json.load(f)
        
        resumo = stats.get("resumo", {})
        sinais_24h = resumo.get("sinais_24h", 0)
        total_analises = resumo.get("total_analises", 0)
        
        if total_analises > 0:
            return f"📊 Últimas 24h: {sinais_24h} sinais detectados"
        else:
            return "📊 Coletando dados históricos..."
            
    except:
        return "📊 Estatísticas em preparação..."

# ===============================
# === FUNÇÕES ORIGINAIS MANTIDAS
# ===============================

def validar_dados(df, nome_par):
    """Validação melhorada"""
    if df is None or len(df) == 0:
        return False
    if len(df) < 50:
        return False
    
    colunas_essenciais = ['open', 'high', 'low', 'close', 'volume']
    for col in colunas_essenciais:
        if col not in df.columns:
            return False
        if df[col].isna().sum() > len(df) * 0.1:
            return False
        if (df[col] <= 0).sum() > 0:
            return False
    
    return True

def limpar_dados(df):
    """Limpeza de dados"""
    df = df[df['high'] >= df['low']].copy()
    df = df[df['volume'] > 0].copy()
    return df.reset_index(drop=True)

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
    """Verifica sinais em aberto"""
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
            continue
        
        status_anterior = sinal['status']
        
        if preco_atual >= sinal['alvo']:
            sinal['status'] = "🎯 Alvo atingido"
            sinal['preco_final'] = preco_atual
        elif preco_atual <= sinal['stop']:
            sinal['status'] = "🛑 Stop atingido"
            sinal['preco_final'] = preco_atual
        else:
            dt_alerta = datetime.datetime.fromisoformat(sinal['timestamp'])
            tempo_passado = datetime.datetime.utcnow() - dt_alerta
            if tempo_passado.total_seconds() >= 86400:  # 24h
                sinal['status'] = "⏰ Expirado (24h)"
                sinal['preco_final'] = preco_atual
        
        if sinal['status'] != status_anterior:
            sinal['atualizado_em'] = datetime.datetime.utcnow().isoformat()
            sinais_atualizados.append(sinal)
    
    if sinais_atualizados:
        salvar_sinais_monitorados(sinais)
        for sinal in sinais_atualizados:
            enviar_notificacao_fechamento(sinal)
    
    return sinais_atualizados

def enviar_notificacao_fechamento(sinal):
    """Notificação de fechamento de sinal"""
    try:
        dt_inicio = datetime.datetime.fromisoformat(sinal['timestamp'])
        dt_fim = datetime.datetime.fromisoformat(sinal['atualizado_em'])
        duracao = dt_fim - dt_inicio
        horas = int(duracao.total_seconds() // 3600)
        minutos = int((duracao.total_seconds() % 3600) // 60)
        
        resultado = "🎉 SUCESSO" if "Alvo" in sinal['status'] else "⚠️ STOP" if "Stop" in sinal['status'] else "⏰ EXPIRADO"
        
        mensagem = (
            f"📊 *SINAL FINALIZADO*\n\n"
            f"{resultado}\n\n"
            f"📊 Par: `{sinal['par']}`\n"
            f"📋 Setup: {sinal['setup']}\n"
            f"💰 Entrada: `${sinal['entrada']:.2f}`\n"
            f"🏁 Saída: `${sinal.get('preco_final', 0):.2f}`\n"
            f"⏱️ Duração: {horas}h {minutos}min\n"
            f"📍 Status: {sinal['status']}"
        )
        
        enviar_telegram(mensagem)
    except Exception as e:
        logging.error(f"Erro notificação fechamento: {e}")

def abreviar_valor(valor):
    if valor >= 1_000_000_000_000:
        return f"${valor
