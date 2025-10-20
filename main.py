# === Importações base
import os, json, time, datetime, logging, warnings
import requests
import numpy as np
import pandas as pd
import ccxt
from pathlib import Path
import csv

# === TA (indicadores técnicos)
# Precisamos do módulo inteiro para usar ta.momentum/ta.volatility nas funções gpt_
try:
    import ta  # módulo completo
except Exception:
    ta = None

# Você já usa algumas classes diretamente — ok manter:
from ta.trend import EMAIndicator, MACD, ADXIndicator, SMAIndicator
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import OnBalanceVolumeIndicator

# === pandas-ta (opcional; fallback para cálculo manual)
try:
    import pandas_ta as pta
except Exception:
    print("⚠️ pandas_ta não disponível, usando cálculo manual")
    pta = None

# === Ajustes de compatibilidade e limpeza de avisos
pd.options.mode.chained_assignment = None
np.seterr(all='ignore')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*invalid value encountered.*')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*divide by zero.*')

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
ARQUIVO_LEDGER = 'data/ledger_sinais.csv'
ARQUIVO_THROTTLE = 'data/throttle.json'

# Logging
#logging.basicConfig(
#    level=logging.INFO,
#    format='%(asctime)s #[%(levelname)s] %(message)s',
#   datefmt='%Y-%m-%d %H:%M:%S'
#)

# Controle de alertas
alertas_enviados = {}
# ===============================
# === ITEM 1.1: LOGS ESTRUTURADOS PT-BR
# ===============================

def configurar_logs_estruturados():
    """Configura sistema de logs estruturados em português"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    data_hoje = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"scanner_{data_hoje}.log"
    
    formato = '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
    formato_data = '%Y-%m-%d %H:%M:%S'
    
    logging.basicConfig(
        level=logging.INFO,
        format=formato,
        datefmt=formato_data,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger('scanner')
    logger.info("=" * 60)
    logger.info("🚀 SCANNER INICIADO")
    logger.info(f"📅 Data/Hora: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    logger.info(f"📂 Log: {log_file}")
    logger.info("=" * 60)
    
    return logger
    # ===============================
# === ITEM 1.2: VALIDAÇÃO ANTES DE ENVIAR
# ===============================

def validar_antes_enviar(par, setup, score, preco_entrada, stop, alvo):
    """Valida sinal antes de enviar ao Telegram"""
    logger = logging.getLogger('scanner')
    
    if not par or par.strip() == "":
        logger.warning("❌ Validação falhou: Par vazio")
        return False
    
    if not setup or setup.strip() == "":
        logger.warning(f"❌ Validação falhou [{par}]: Setup não identificado")
        return False
    
    if score < 6.0:
        logger.info(f"⚠️ Score baixo [{par}]: {score:.1f} < 6.0 (não enviado)")
        return False
    
    if preco_entrada <= 0 or stop <= 0 or alvo <= 0:
        logger.error(f"❌ Validação falhou [{par}]: Preços inválidos")
        return False
    
    if not (stop < preco_entrada < alvo):
        logger.error(f"❌ Validação falhou [{par}]: Ordem incorreta")
        return False
    
    risco = preco_entrada - stop
    recompensa = alvo - preco_entrada
    rr_ratio = recompensa / risco if risco > 0 else 0
    
    if rr_ratio < 1.5:
        logger.warning(f"⚠️ R:R baixo [{par}]: {rr_ratio:.2f} < 1.5")
        return False
    
    logger.info(f"✅ Validações OK [{par}]: Score={score:.1f}, R:R={rr_ratio:.2f}")
    return True
    
#===============================
# === ITEM 1.3: PAPER MODE OBRIGATÓRIO
# ===============================

def obter_modo_operacao():
    """Obtém modo de operação (PAPER ou LIVE)"""
    logger = logging.getLogger('scanner')
    modo = os.getenv('PAPER_MODE', 'true').lower()
    
    if modo == 'false':
        logger.critical("=" * 60)
        logger.critical("⚠️  ATENÇÃO: LIVE MODE DETECTADO")
        logger.critical("⚠️  Este modo executa ordens REAIS")
        logger.critical("⚠️  Certifique-se de ter cumprido os critérios GO")
        logger.critical("=" * 60)
        
        import time
        for i in range(10, 0, -1):
            print(f"⏳ Iniciando LIVE MODE em {i}s... (Ctrl+C para cancelar)")
            time.sleep(1)
        
        logger.warning("🔴 LIVE MODE ATIVADO")
        return "LIVE"
    else:
        logger.info("📝 PAPER MODE ATIVO - Apenas registro e análise")
        return "PAPER"   
  #===============================
# === ITEM 1.4: LEDGER COMPLETO CSV
# ===============================

class LedgerSinais:
    """Gerencia ledger completo de sinais em CSV"""
    
    def __init__(self, arquivo="data/ledger_sinais.csv"):
        self.arquivo = Path(arquivo)
        self.logger = logging.getLogger('scanner')
        self.arquivo.parent.mkdir(exist_ok=True)
        
        if not self.arquivo.exists():
            self._criar_arquivo()
    
    def _criar_arquivo(self):
        """Cria arquivo CSV com cabeçalho"""
        cabecalho = [
            'id', 'data_criacao', 'par', 'setup', 'score',
            'preco_entrada', 'stop', 'alvo', 'rr_ratio',
            'status', 'data_encerramento', 'preco_final',
            'resultado', 'roi_pct', 'duracao_horas', 'observacoes'
        ]
        
        with open(self.arquivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(cabecalho)
        
        self.logger.info(f"📄 Ledger criado: {self.arquivo}")
    
    def registrar_sinal(self, par, setup, score, preco_entrada, stop, alvo, observacoes=""):
        """Registra novo sinal no ledger"""
        sinal_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        risco = preco_entrada - stop
        recompensa = alvo - preco_entrada
        rr_ratio = recompensa / risco if risco > 0 else 0
        
        linha = [
            sinal_id,
            datetime.datetime.now().isoformat(),
            par, setup, f"{score:.2f}",
            f"{preco_entrada:.8f}", f"{stop:.8f}", f"{alvo:.8f}",
            f"{rr_ratio:.2f}",
            "aberto", "", "", "", "", "", observacoes
        ]
        
        with open(self.arquivo, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(linha)
        
        self.logger.info(f"📝 Sinal no ledger: {sinal_id} - {par}")
        return sinal_id
    
    def atualizar_sinal(self, sinal_id, preco_final, resultado, observacoes=""):
        """Atualiza sinal quando encerrado"""
        linhas = []
        
        with open(self.arquivo, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['id'] == sinal_id:
                    preco_entrada = float(row['preco_entrada'])
                    roi_pct = ((preco_final - preco_entrada) / preco_entrada) * 100
                    
                    data_criacao = datetime.datetime.fromisoformat(row['data_criacao'])
                    data_encerramento = datetime.datetime.now()
                    duracao = (data_encerramento - data_criacao).total_seconds() / 3600
                    
                    row['status'] = 'fechado'
                    row['data_encerramento'] = data_encerramento.isoformat()
                    row['preco_final'] = f"{preco_final:.8f}"
                    row['resultado'] = resultado
                    row['roi_pct'] = f"{roi_pct:+.2f}"
                    row['duracao_horas'] = f"{duracao:.1f}"
                    row['observacoes'] = observacoes
                    
                    self.logger.info(f"✅ Sinal atualizado: {sinal_id} - {resultado} - ROI: {roi_pct:+.2f}%")
                
                linhas.append(row)
        
        with open(self.arquivo, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=linhas[0].keys())
            writer.writeheader()
            writer.writerows(linhas)      
            
#===============================
# === ITEM 1.5: LOG DE THROTTLE
# ===============================

def verificar_throttle(par, tempo_reenvio_min=30):
    """Verifica se pode enviar alerta (controle de throttle)"""
    logger = logging.getLogger('scanner')
    throttle_file = Path("data/throttle.json")
    throttle_file.parent.mkdir(exist_ok=True)
    
    if throttle_file.exists():
        with open(throttle_file, 'r') as f:
            throttle_data = json.load(f)
    else:
        throttle_data = {}
    
    agora = datetime.datetime.now()
    
    if par in throttle_data:
        ultimo_envio = datetime.datetime.fromisoformat(throttle_data[par])
        tempo_passado = (agora - ultimo_envio).total_seconds() / 60
        
        if tempo_passado < tempo_reenvio_min:
            proximo_permitido = ultimo_envio + datetime.timedelta(minutes=tempo_reenvio_min)
            falta = (proximo_permitido - agora).total_seconds() / 60
            
            logger.info(f"⏸️  Throttle ativo [{par}]:")
            logger.info(f"   ├─ Último alerta há {tempo_passado:.1f} minutos")
            logger.info(f"   ├─ Tempo mínimo: {tempo_reenvio_min} minutos")
            logger.info(f"   └─ Próximo permitido em: {falta:.1f} minutos")
            
            return False
    
    throttle_data[par] = agora.isoformat()
    
    with open(throttle_file, 'w') as f:
        json.dump(throttle_data, f, indent=2)
    
    logger.info(f"✅ Throttle OK [{par}]: Pode enviar")
    return True
           
# ===============================
# === VALIDAÇÃO E LIMPEZA DE DADOS
# ===============================

def validar_dados(df, nome_par):
    """Validação de dados"""
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
    """Limpeza de dados com proteção contra erros de versão"""
    try:
        # Criar uma cópia para evitar problemas de referência
        df_clean = df.copy()
        
        # Filtros de validação
        mask_valid = (
            (df_clean['high'] >= df_clean['low']) & 
            (df_clean['volume'] > 0)
        )
        
        df_clean = df_clean[mask_valid].copy()
        return df_clean.reset_index(drop=True)
        
    except Exception as e:
        logging.warning(f"Erro na limpeza de dados: {e}")
        # Fallback simples
        return df.reset_index(drop=True)

# ===============================
# === SISTEMA DE MÚLTIPLOS TIMEFRAMES
# ===============================

def analisar_multiplos_timeframes(exchange, par):
    """Analisa o mesmo par em múltiplos timeframes e retorna DF + métricas por TF."""
    resultados = {}
    for tf in TIMEFRAMES:
        try:
            print(f"    📈 Timeframe {tf}...")
            ohlcv = exchange.fetch_ohlcv(par, tf, limit=limite_candles)

            # Verificação inicial
            if not ohlcv or len(ohlcv) < 100:
                resultados[tf] = {"status": "dados_insuficientes", "candles": (len(ohlcv) if ohlcv else 0)}
                continue

            # DataFrame base + limpeza
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df = limpar_dados(df)

            # Sanitização extra
            cols = ["open", "high", "low", "close", "volume"]
            df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
            df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=cols).reset_index(drop=True)

            # Amostra mínima
            if len(df) < 100:
                resultados[tf] = {"status": "dados_insuficientes", "candles": len(df)}
                continue

            # Indicadores
            try:
                df = calcular_indicadores_completos(df)
            except Exception as e:
                # Ainda retorna DF mínimo em caso de falha
                logging.warning(f"Indicadores falharam em {par} {tf}: {e}")

            if not validar_dados(df, f"{par}_{tf}"):
                resultados[tf] = {"status": "dados_invalidos"}
                continue

            # ----- Métricas necessárias para os setups/alerta -----
            preco = float(df["close"].iloc[-1])
            tendencia = determinar_tendencia(df)
            forca = calcular_forca_tendencia(df)
            volatilidade = calcular_volatilidade(df)

            # Alguns campos usados por mensagens/setups:
            rsi_val = float(df["rsi"].iloc[-1]) if "rsi" in df.columns else float("nan")
            macd_val = float(df["macd"].iloc[-1]) if "macd" in df.columns else float("nan")
            macd_sig = float(df["macd_signal"].iloc[-1]) if "macd_signal" in df.columns else float("nan")
            vol_ma = df["volume"].rolling(20, min_periods=1).mean().iloc[-1]
            volume_ratio = float(df["volume"].iloc[-1] / vol_ma) if vol_ma else 0.0

            resultados[tf] = {
                "status": "ok",
                "df": df,
                "preco": preco,
                "tendencia": tendencia,
                "forca": forca,
                "volatilidade": volatilidade,
                "rsi": rsi_val,
                "macd": macd_val,
                "macd_signal": macd_sig,
                "volume_ratio": volume_ratio,
            }

        except Exception as e:
            logging.error(f"Falha ao preparar dados ({par}, {tf}): {e}")
            resultados[tf] = {"status": "erro", "mensagem": str(e)}
            continue

    return resultados
def calcular_indicadores_completos(df):
    """
    Calcula o conjunto completo de indicadores.
    Inclusões (E): VWAP e BB Width/Squeeze sob controle por variáveis de ambiente.
    """
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

        # StochRSI
        try:
            stoch_rsi = StochRSIIndicator(close, 14, 3, 3)
            df['stoch_rsi'] = stoch_rsi.stochrsi()
        except Exception:
            df['stoch_rsi'] = df['rsi'] / 100.0

        # Tendência
        macd = MACD(close)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_histogram'] = macd.macd_diff()

        df['adx'] = ADXIndicator(high, low, close, 14).adx()

        # Volatilidade (ATR)
        df['atr'] = AverageTrueRange(high, low, close, 14).average_true_range()

        # Bandas de Bollinger
        bollinger = BollingerBands(close, 20, 2)
        df['bb_upper'] = bollinger.bollinger_hband()
        df['bb_middle'] = bollinger.bollinger_mavg()
        df['bb_lower'] = bollinger.bollinger_lband()

        # ===== (E) BB Width + Squeeze (opcional) =====
        if os.getenv("ATIVAR_BBWIDTH", "false").lower() == "true":
            try:
                base = df['bb_middle'].replace(0, np.nan)
                df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / base
                if len(df) >= 50:
                    limiar = df['bb_width'].rolling(50).quantile(0.2).iloc[-1]
                else:
                    limiar = df['bb_width'].median()
                df['bb_squeeze'] = df['bb_width'] < limiar
            except Exception as e:
                logging.warning(f"BB Width falhou (seguindo sem): {e}")
                df['bb_width'] = np.nan
                df['bb_squeeze'] = False
        else:
            if 'bb_width' not in df.columns:
                df['bb_width'] = np.nan
            if 'bb_squeeze' not in df.columns:
                df['bb_squeeze'] = False

        # Volume (média de volume 20)
        try:
            df['volume_sma'] = df['volume'].rolling(20, min_periods=1).mean() if 'volume_sma' not in df.columns else df['volume_sma']
        except Exception:
            df['volume_sma'] = df['volume'].rolling(20, min_periods=1).mean()

        df['obv'] = OnBalanceVolumeIndicator(close, volume).on_balance_volume()

        # Supertrend
        df = calcular_supertrend(df)

        # ===== (E) VWAP (opcional) =====
        if os.getenv("ATIVAR_VWAP", "false").lower() == "true":
            try:
                pv = (df['close'] * df['volume']).cumsum()
                vv = df['volume'].cumsum().replace(0, np.nan)
                df['vwap'] = pv / vv
                df['vwap_ok'] = (df['close'] > df['vwap']) & ((df['close'] - df['vwap']) / df['vwap'] < 0.005)
            except Exception as e:
                logging.warning(f"VWAP falhou (seguindo sem): {e}")
                df['vwap'] = np.nan
                df['vwap_ok'] = False
        else:
            if 'vwap' not in df.columns:
                df['vwap'] = np.nan
            if 'vwap_ok' not in df.columns:
                df['vwap_ok'] = False

        # Preencher NaN
        for col in df.columns:
            try:
                if df[col].dtype in ['float64', 'int64'] and df[col].isna().sum() > 0:
                    df[col] = df[col].fillna(method='bfill').fillna(method='ffill')
            except Exception:
                pass

        return df

    except Exception as e:
        logging.error(f"Erro ao calcular indicadores: {e}")
        return df

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
            atr = AverageTrueRange(df['high'], df['low'], df['close'], period).average_true_range()
            atr = atr.fillna(method='bfill').fillna(method='ffill')
            
            hl2 = (df['high'] + df['low']) / 2
            lower_band = hl2 - (multiplier * atr)
            df['supertrend'] = df['close'] > lower_band
        
        return df
    except Exception as e:
        df['supertrend'] = [True] * len(df)
        return df

# ===============================
# === DETECÇÃO DE PADRÕES
# ===============================

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
# === SETUPS AVANÇADOS
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
        
        # Força adequada
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
        
        if sum(condicoes) >= 4:
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
    """Setup: Bollinger Band Squeeze"""
    try:
        if 'bb_upper' not in df.columns:
            bollinger = BollingerBands(df['close'], 20, 2)
            df['bb_upper'] = bollinger.bollinger_hband()
            df['bb_lower'] = bollinger.bollinger_lband()
            df['bb_middle'] = bollinger.bollinger_mavg()
        
        # Largura das bandas
        bb_width = (r['bb_upper'] - r['bb_lower']) / r['bb_middle']
        bb_width_avg = ((df['bb_upper'] - df['bb_lower']) / df['bb_middle']).rolling(20).mean().iloc[-1]
        
        # Squeeze ativo
        squeeze_ativo = bb_width < bb_width_avg * 0.6
        
        # Preço próximo a banda
        dist_upper = abs(r['close'] - r['bb_upper']) / r['close']
        dist_lower = abs(r['close'] - r['bb_lower']) / r['close']
        proximo_banda = min(dist_upper, dist_lower) < 0.015
        
        # Volume crescente
        volume_crescente = df['volume'].iloc[-3:].mean() > df['volume'].iloc[-6:-3].mean()
        
        # ADX baixo
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
    """Setup: Divergência RSI"""
    try:
        if len(df) < 30:
            return None
        
        recent = df.tail(20).copy()
        
        # Encontrar picos
        recent['price_peak'] = recent['high'].rolling(3, center=True).max() == recent['high']
        recent['rsi_peak'] = recent['rsi'].rolling(3, center=True).max() == recent['rsi']
        
        price_peaks = recent[recent['price_peak']]['high']
        rsi_peaks = recent[recent['rsi_peak']]['rsi']
        
        if len(price_peaks) >= 2 and len(rsi_peaks) >= 2:
            # Divergência bearish
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
        
        # Divergência bullish
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
    """Setup: Breakout com volume extremo"""
    try:
        if len(df) < 20:
            return None
        
        # Resistência dos últimos 15 candles
        resistencia = df['high'].iloc[-15:-1].max()
        
        # Contar toques na resistência
        touches = ((df['high'].iloc[-15:-1] >= resistencia * 0.995) & 
                  (df['high'].iloc[-15:-1] <= resistencia * 1.005)).sum()
        
        # Critérios
        resistencia_forte = touches >= 3
        breakout = r['close'] > resistencia * 1.002
        volume_explosivo = df['volume'].iloc[-1] > df['volume'].mean() * 3.0
        rsi_saudavel = 40 < r['rsi'] < 75
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
# === SETUPS ORIGINAIS
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
# === SISTEMA DE SCORE VISUAL
# ===============================

def gerar_score_visual(score):
    """Representação visual do score"""
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
    """Categorização de risco"""
    if score >= 8.5:
        return {"nivel": "BAIXO", "emoji": "🟢", "cor": "Verde"}
    elif score >= 7.0:
        return {"nivel": "MÉDIO", "emoji": "🟡", "cor": "Amarelo"}
    elif score >= 5.5:
        return {"nivel": "ALTO", "emoji": "🟠", "cor": "Laranja"}
    else:
        return {"nivel": "MUITO ALTO", "emoji": "🔴", "cor": "Vermelho"}

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

def registrar_sinal_monitorado(par, setup_id, preco_entrada, alvo, stop, score_100=None):
    """
    Registra um sinal em dados/sinais_monitorados.json.
    Compatível com a versão anterior; o campo score_100 é OPCIONAL.
    """
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
    if score_100 is not None:
        try:
            novo_sinal["score_100"] = float(score_100)
        except Exception:
            novo_sinal["score_100"] = score_100

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
            if tempo_passado.total_seconds() >= 86400:
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
    """Notificação de fechamento"""
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

# ===============================
# === COMUNICAÇÃO TELEGRAM
# ===============================

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
    """Alerta com análise de múltiplos timeframes + (B) bloco de componentes 0–100 opcional."""
    try:
        # Dados do timeframe principal (1h)
        tf_principal = analise_tf.get('1h', {})
        if tf_principal.get('status') != 'ok':
            return False

        preco = tf_principal['preco']

        # Score avançado (0–10) que você já usa
        score, criterios_bonus = calcular_score_avancado(analise_tf, setup_info)
        score_visual = gerar_score_visual(score)
        risco = categorizar_risco(score)

        # Calcular alvos (sua lógica atual baseada em ATR de 1h)
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

        # Dados fundamentais (A: ocultar dentro do alerta se macro único estiver ativo)
        contexto_macro = obter_dados_fundamentais()
        macro_unico_ativo = os.getenv("ATIVAR_MACRO_UNICO", "false").lower() == "true"

        # Montagem da mensagem (mantive seu estilo)
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

        # Indicadores atuais no 1h
        r = df_1h.iloc[-1]
        stoch_str = ""
        try:
            stoch_val = float(r.get('stoch_rsi', 0)*100.0)
            stoch_str = f"{stoch_val:.1f}"
        except Exception:
            stoch_str = "—"
        mensagem += (
            f"\n*📊 INDICADORES ATUAIS:*\n"
            f"• RSI: {r['rsi']:.1f} | StochRSI: {stoch_str}\n"
            f"• ADX: {r['adx']:.1f} | MACD: {r['macd']:.4f}\n"
            f"• Volume: {analise_tf['1h']['volume_ratio']:.1f}x média\n"
            f"• ATR: {r['atr']:.4f}\n\n"
        )

        # Critérios bônus
        if criterios_bonus:
            mensagem += "*🎁 BONUS CONFLUÊNCIA:*\n"
            for criterio in criterios_bonus[:3]:
                mensagem += f"{criterio}\n"
            mensagem += "\n"

        # Detalhes
        if 'timeframes' in setup_info:
            mensagem += f"*📋 DETALHES:*\n{setup_info['timeframes']}\n\n"
        if 'detalhes' in setup_info:
            mensagem += f"*📋 ESPECÍFICOS:*\n{setup_info['detalhes']}\n\n"

        # (B) Bloco de Pontuação 0–100 com componentes (opcional)
        score_100 = None
        if os.getenv("ATIVAR_SCORE_COMPONENTES", "false").lower() == "true":
            try:
                score_100, comp, confs_txt = gpt_obter_score_100(df_1h)
                linha = gpt_formatar_linha_componentes(comp)
                mensagem += (
                    f"🧮 Pontuação: {score_100}/100\n"
                    f"📎 Componentes: {linha}\n"
                    f"🔎 Confluências: {confs_txt}\n\n"
                )
            except Exception as e:
                logging.warning(f"Bloco de componentes falhou: {e}")

        # (A) Macro dentro do alerta só quando o macro único NÃO estiver ativo
        if not macro_unico_ativo:
            mensagem += f"{contexto_macro}\n\n"

        mensagem += f"🕘 {timestamp}\n"
        mensagem += f"📉 [TradingView]({link_tv})\n\n"

        # Recomendação baseada no score (mantido)
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

# === SEMANA 1: VALIDAÇÕES E REGISTRO ===
    logger = logging.getLogger('scanner')
    
    # Extrair dados para validação
    setup_nome = setup_info.get('setup', 'Desconhecido')
    
    # Item 1.2: Validar antes de enviar
    if not validar_antes_enviar(par, setup_nome, score, preco, stop, alvo):
        logger.warning(f"❌ Sinal reprovado nas validações: {par}")
        return False
    
    # Item 1.5: Verificar throttle
    if not verificar_throttle(par, tempo_reenvio_min=TEMPO_REENVIO):
        return False
    
    # Item 1.3: Adicionar modo na mensagem
    modo = os.getenv('PAPER_MODE', 'true').lower()
    if modo == 'true':
        mensagem = f"[📝 PAPER MODE]\n\n{mensagem}"
    
    # Enviar alerta
    if pode_enviar_alerta(par, setup_nome):
        if enviar_telegram(mensagem):
            # Item 1.4: Registrar no ledger
            ledger = LedgerSinais()
            sinal_id = ledger.registrar_sinal(
                par=par,
                setup=setup_nome,
                score=score,
                preco_entrada=preco,
                stop=stop,
                alvo=alvo,
                observacoes=f"TF: 1h | Confluência detectada"
            )
            
            print(f"✅ ALERTA AVANÇADO: {par} - {setup_nome} (score: {score})")
            registrar_sinal_monitorado(par, setup_info.get('id', ''), preco, alvo, stop, score_100=score_100)
            logger.info(f"📨 Alerta enviado | ID Ledger: {sinal_id}")
            return True

        return False

    except Exception as e:
        logging.error(f"Erro ao enviar alerta avançado: {e}")
        return False

# ===============================
# === ESTATÍSTICAS
# ===============================

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
        
        # Resumo 24h
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

def gerar_resumo_estatisticas():
    """Resumo das estatísticas"""
    try:
        with open(ARQUIVO_ESTATISTICAS, 'r') as f:
            stats = json.load(f)
        
        resumo = stats.get("resumo", {})
        sinais_24h = resumo.get("sinais_24h", 0)
        
        return f"📊 Performance 24h: {sinais_24h} sinais detectados"
    except:
        return "📊 Coletando estatísticas..."

# ===============================
# === ANÁLISE PRINCIPAL AVANÇADA
# ===============================

def analisar_par_avancado(exchange, par):
    """Análise avançada com múltiplos timeframes"""
    try:
        print(f"🔍 Análise avançada de {par}...")
        
        # Analisar múltiplos timeframes
        analise_tf = analisar_multiplos_timeframes(exchange, par)
        
        # Verificar dados válidos
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
            
            # Setups avançados
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
                        analise_single = {tf: dados}
                        if enviar_alerta_avancado(par, analise_single, setup_info):
                            sinais_encontrados.append(setup_info)
                            
                except Exception as e:
                    logging.warning(f"Erro em setup avançado: {e}")
            
            # Setups originais
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
                            break
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

def enviar_relatorio_status_avancado(relatorio):
    """Relatório de status avançado"""
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
        logging.error(f"Erro no relatório avançado: {e}")

# ===============================
# === FUNÇÃO PRINCIPAL AVANÇADA
# ===============================

def executar_scanner_avancado():
    """
    Scanner principal com funcionalidades avançadas.
    Inclusões:
      (A) Macro único no início do ciclo (opcional por variável)
      (D) Filtro de liquidez (volume médio diário 30d) antes do loop (opcional)
    """
    try:
  # === SEMANA 1: INICIALIZAÇÃO ===
        logger = configurar_logs_estruturados()
        modo = obter_modo_operacao()
        ledger = LedgerSinais()
        
        print("🚀 SCANNER AVANÇADO ETH/BTC - ETAPA 2")  
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

        # (A) Macro único no início do ciclo (se ativado)
        if os.getenv("ATIVAR_MACRO_UNICO", "false").lower() == "true":
            try:
                dados_macro = gpt_macro_coletar_dados()
                gpt_macro_enviar_uma_vez(dados_macro)
            except Exception as e:
                logging.warning(f"Macro único falhou (seguindo): {e}")

        # Verificar sinais em aberto
        print("🔍 Verificando sinais monitorados...")
        sinais_atualizados = verificar_sinais_monitorados(exchange)

        # (D) Filtro de liquidez por volume médio 30d (se ativado)
        pares_exec = list(PARES_ALVOS)
        if os.getenv("ATIVAR_FILTRO_LIQUIDEZ", "false").lower() == "true":
            minimo = float(os.getenv("LIQ_MINIMO_30D", "1000000"))
            try:
                pares_exec = gpt_liq_filtrar_por_media_30d(exchange, pares_exec, minimo)
            except Exception as e:
                logging.warning(f"Filtro de liquidez falhou (seguindo com pares originais): {e}")

        # Analisar cada par
        total_sinais = 0
        relatorio_completo = []

        for par in pares_exec:
            if par not in exchange.markets:
                continue

            print(f"\n🎯 Iniciando análise avançada: {par}")
            sinais = analisar_par_avancado(exchange, par)
            total_sinais += len(sinais)

            # Coletar dados para relatório (mantido)
            try:
                ticker = exchange.fetch_ticker(par)
                preco = ticker['last']

                # RSI básico
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

            time.sleep(1)

        print(f"\n✅ SCANNER AVANÇADO FINALIZADO")
        print(f"📨 Total de sinais enviados: {total_sinais}")

        # Enviar relatório se não houver sinais
        if total_sinais == 0:
            enviar_relatorio_status_avancado(relatorio_completo)

        return True

    except Exception as e:
        logging.error(f"Erro crítico no scanner avançado: {e}")

        # Alerta de erro (mantido)
        if TOKEN != "dummy_token":
            mensagem_erro = (
                f"🚨 *ERRO SCANNER AVANÇADO*\n\n"
                f"❌ {str(e)[:80]}...\n"
                f"⏰ {datetime.datetime.utcnow().strftime('%H:%M UTC')}"
            )
            enviar_telegram(mensagem_erro)

        return False
# ============================== [GPT] SUPORTES ==============================
# (B) Pontuação 0–100 com componentes + resumo de “confluências”
def gpt_comp_calcular(df):
    """
    Calcula componentes normalizados (0–1):
      • tend: tendência (EMAs e posição do preço)
      • mom:  momentum (RSI)
      • vol:  volume relativo (vs. média 20)
      • volat:volatilidade (largura BB/σ)
      • conf: confiabilidade (tamanho da amostra)
    Retorna: dict com chaves {'tend','mom','vol','volat','conf'} em [0,1].
    """
    if df is None or len(df) == 0:
        return {"tend": 0.0, "mom": 0.0, "vol": 0.0, "volat": 0.0, "conf": 0.0}

    d = df.copy()

    # Garante colunas numéricas básicas
    for col in ("open", "high", "low", "close", "volume"):
        if col not in d:
            d[col] = np.nan
        d[col] = pd.to_numeric(d[col], errors="coerce")

    # EMAs (se não existirem)
    if "ema9" not in d:
        d["ema9"] = d["close"].ewm(span=9, adjust=False).mean()
    if "ema21" not in d:
        d["ema21"] = d["close"].ewm(span=21, adjust=False).mean()
    if "ema50" not in d:
        d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()

    # RSI (se possível)
    if "rsi" not in d:
        try:
            if ta is not None:
                d["rsi"] = ta.momentum.RSIIndicator(d["close"], window=14).rsi()
            else:
                # fallback simples (diferenças positivas/negativas)
                delta = d["close"].diff()
                up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
                down = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
                rs = up / (down + 1e-9)
                d["rsi"] = 100 - (100 / (1 + rs))
        except Exception:
            d["rsi"] = np.nan

    # Volume médio 20 (se não existir)
    if "volume_sma20" not in d:
        d["volume_sma20"] = d["volume"].rolling(20, min_periods=1).mean()

    # Largura de bandas (se não existir)
    if "bb_width" not in d:
        try:
            if ta is not None:
                bb = ta.volatility.BollingerBands(d["close"], window=20, window_dev=2)
                high = bb.bollinger_hband()
                low = bb.bollinger_lband()
                d["bb_width"] = (high - low) / d["close"]
            else:
                std = d["close"].rolling(20, min_periods=1).std()
                d["bb_width"] = (4 * std) / d["close"]  # ~2σ p/ cada lado
        except Exception:
            d["bb_width"] = np.nan

    r = d.iloc[-1]

    # ---- Componentes normalizados 0–1
    # Tendência: EMAs em ordem e preço acima de EMA50
    conds = [
        float(r.get("ema9", np.nan) > r.get("ema21", np.nan)),
        float(r.get("ema21", np.nan) > r.get("ema50", np.nan)),
        float(r.get("close", np.nan) > r.get("ema50", np.nan)),
    ]
    tend = np.nanmean(conds)
    if np.isnan(tend):
        tend = 0.0

    # Momentum: RSI centralizado (30–70)
    rsi = float(r.get("rsi", np.nan))
    mom = 0.0 if np.isnan(rsi) else np.clip((rsi - 30.0) / 40.0, 0.0, 1.0)

    # Volume relativo vs. média (satura em 2x)
    v = float(r.get("volume", np.nan))
    vma = float(r.get("volume_sma20", np.nan))
    vol = 0.0 if (np.isnan(v) or np.isnan(vma) or vma <= 0) else np.clip(v / vma, 0.0, 2.0) / 2.0

    # Volatilidade (BB width) – 0.08 ~ “alto”
    bb = float(r.get("bb_width", np.nan))
    volat = 0.0 if np.isnan(bb) else np.clip(bb / 0.08, 0.0, 1.0)

    # Confiabilidade: tamanho da amostra (>=200 candles => 1.0)
    conf = np.clip(len(d) / 200.0, 0.0, 1.0)

    return {"tend": float(tend), "mom": float(mom), "vol": float(vol), "volat": float(volat), "conf": float(conf)}
    
# --- compat: manter chamadas antigas funcionando ---
def gpt_obter_score_100(comp):
    # reaproveita a função nova
    return gpt_comp_score_100(comp)
    
def gpt_comp_score_100(comp, pesos=None):
    """
    Converte os componentes em uma pontuação 0–100 com pesos.
    Se 'pesos' não for informado, busca em variáveis de ambiente
    (PESO_TEND, PESO_MOM, PESO_VOL, PESO_VOLAT, PESO_CONF) ou usa 1.0.
    """
    if pesos is None:
        try:
            pesos = {
                "tend": float(os.getenv("PESO_TEND", "1")),
                "mom": float(os.getenv("PESO_MOM", "1")),
                "vol": float(os.getenv("PESO_VOL", "1")),
                "volat": float(os.getenv("PESO_VOLAT", "1")),
                "conf": float(os.getenv("PESO_CONF", "1")),
            }
        except Exception:
            pesos = {"tend": 1.0, "mom": 1.0, "vol": 1.0, "volat": 1.0, "conf": 1.0}

    num = 0.0
    den = 0.0
    for k, w in pesos.items():
        v = float(comp.get(k, 0.0))
        num += w * v
        den += abs(w)
    base = 0.0 if den == 0 else num / den  # 0–1
    return int(round(100 * np.clip(base, 0.0, 1.0)))

def gpt_comp_resumir(df):
    """
    Retorna (score_100, componentes_dict, texto_confluencias).
    Confluências checadas:
      • vwap_ok (último candle acima da VWAP)
      • bb_squeeze (compressão de Bandas de Bollinger)
    """
    comp = gpt_comp_calcular(df)
    score_100 = gpt_comp_score_100(comp)

    confs = []
    try:
        v_ok = df.get("vwap_ok", pd.Series([False])).iloc[-1]
        if bool(v_ok):
            confs.append("acima da VWAP")
    except Exception:
        pass

    try:
        bb_sq = df.get("bb_squeeze", pd.Series([False])).iloc[-1]
        if bool(bb_sq):
            confs.append("Bandas comprimidas")
    except Exception:
        pass

    confs_txt = "; ".join(confs) if confs else "—"
    return score_100, comp, confs_txt

# (A) Macro único por ciclo — enviar 1x no começo
_GPT_MACRO_ENVIADO = False

def gpt_macro_coletar_dados():
    """
    Coleta contexto macro (cap total, domínio BTC e Fear&Greed).
    Retorna dict com chaves: total_cap, btc_dom, fng, agenda.
    Obs.: 'agenda' fica como '-' aqui (placeholder), pois depende
    de fontes específicas caso deseje adicionar no futuro.
    """
    dados = {"total_cap": "-", "btc_dom": "-", "fng": "-", "agenda": "-"}
    try:
        cg = requests.get("https://api.coingecko.com/api/v3/global", timeout=8).json()
        total_cap = cg["data"]["total_market_cap"].get("usd")
        btc_dom = cg["data"]["market_cap_percentage"].get("btc")
        if total_cap:
            dados["total_cap"] = f"${total_cap:,.0f}"
        if btc_dom is not None:
            dados["btc_dom"] = f"{btc_dom:.1f}%"
    except Exception as e:
        logging.warning(f"Falha CoinGecko (macro): {e}")

    try:
        fng = requests.get("https://api.alternative.me/fng/?limit=1", timeout=6).json()
        item = fng["data"][0]
        dados["fng"] = f"{item['value']} ({item['value_classification']})"
    except Exception as e:
        logging.warning(f"Falha Fear&Greed (macro): {e}")

    return dados

def gpt_macro_enviar_uma_vez(dados_macro: dict):
    """
    Envia o bloco macro apenas uma vez por execução (controle global).
    Exige a função enviar_telegram(texto).
    """
    global _GPT_MACRO_ENVIADO
    if _GPT_MACRO_ENVIADO:
        return

    texto = (
        "🌍 CONTEXTO MACRO\n"
        f"• Cap. Total: {dados_macro.get('total_cap','-')}\n"
        f"• Domínio BTC: {dados_macro.get('btc_dom','-')}\n"
        f"• Fear & Greed: {dados_macro.get('fng','-')}\n"
        f"• Agenda: {dados_macro.get('agenda','-')}\n"
    )
    try:
        enviar_telegram(texto)
    except Exception:
        print(texto)

    _GPT_MACRO_ENVIADO = True

# (D) Filtro de liquidez — média de volume 30d com dados diários (fail-open)
def gpt_liq_filtrar_por_media_30d(exchange, pares: list, minimo: float) -> list:
    """
    Para cada par em 'pares', consulta OHLCV diário (1d), calcula a
    média de 'volume' dos últimos 30 dias e mantém somente aqueles
    com média >= 'minimo'. Em caso de erro, mantém o par (fail-open).
    """
    aprovados, reprovados = [], []
    for par in pares:
        try:
            ohlcv = exchange.fetch_ohlcv(par, '1d', limit=60)
            d = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            d["volume"] = pd.to_numeric(d["volume"], errors="coerce")
            media30 = float(d["volume"].tail(30).mean())
            (aprovados if media30 >= minimo else reprovados).append(par)
        except Exception as e:
            logging.warning(f"Liquidez: não avaliei {par} ({e}). Mantendo (fail-open).")
            aprovados.append(par)

    logging.info(
        "Liquidez: aprovados=%d | reprovados=%d | mínimo=%.0f",
        len(aprovados), len(reprovados), minimo
    )
    return aprovados
# ============================== [GPT] FIM SUPORTES ==============================
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
        exit(1)
        # ============================== [GPT] SUPORTES — ADICIONAR NO FINAL ==============================
