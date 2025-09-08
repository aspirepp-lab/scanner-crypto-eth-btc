# institucional/analisador_vwap.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

class AnalisadorVWAPInstitucional:
    """
    Analisador VWAP Institucional - Método Maria Silveira
    Implementação para mercado crypto 24/7
    """
    
    def __init__(self):
        self.periodos = ['1D', '1S', '1M']  # Diário, Semanal, Mensal
        self.inicio_semana_crypto = 21  # 21h domingo (horário crypto)
        self.limite_desvio = 2.0  # 2% desvio para alertas críticos
        self.desvio_extremo = 3.0   # 3% desvio para alertas extremos
        
    def calcular_vwap_periodo(self, df, periodo='1D'):
        """
        Calcula VWAP para período específico
        Args:
            df: DataFrame com dados OHLCV
            periodo: '1D', '1S', '1M'
        Returns:
            pandas.Series com valores VWAP
        """
        try:
            if len(df) < 2:
                return pd.Series([np.nan] * len(df), index=df.index)
            
            # Preço típico (HLC/3)
            preco_tipico = (df['high'] + df['low'] + df['close']) / 3
            
            if periodo == '1D':
                return self._calcular_vwap_diario(df, preco_tipico)
            elif periodo == '1S':
                return self._calcular_vwap_semanal(df, preco_tipico)
            elif periodo == '1M':
                return self._calcular_vwap_mensal(df, preco_tipico)
            else:
                raise ValueError(f"Período não suportado: {periodo}")
                
        except Exception as e:
            print(f"Erro no cálculo VWAP {periodo}: {e}")
            return pd.Series([np.nan] * len(df), index=df.index)
    
    def _calcular_vwap_diario(self, df, preco_tipico):
        """VWAP diária - reset a cada 00:00 UTC"""
        df_copia = df.copy()
        df_copia['data'] = df_copia.index.date
        
        valores_vwap = []
        data_atual = None
        soma_preco_volume = 0
        soma_volume = 0
        
        for idx, linha in df_copia.iterrows():
            if linha['data'] != data_atual:
                # Novo dia - resetar acumuladores
                data_atual = linha['data']
                soma_preco_volume = 0
                soma_volume = 0
            
            # Acumular volume e preço*volume
            preco = (linha['high'] + linha['low'] + linha['close']) / 3
            soma_preco_volume += preco * linha['volume']
            soma_volume += linha['volume']
            
            # Calcular VWAP atual
            if soma_volume > 0:
                vwap = soma_preco_volume / soma_volume
            else:
                vwap = preco
                
            valores_vwap.append(vwap)
        
        return pd.Series(valores_vwap, index=df.index)
    
    def _calcular_vwap_semanal(self, df, preco_tipico):
        """VWAP semanal - reset domingo 21h (padrão crypto)"""
        df_copia = df.copy()
        df_copia['semana_crypto'] = self._obter_numero_semana_crypto(df_copia.index)
        
        valores_vwap = []
        semana_atual = None
        soma_preco_volume = 0
        soma_volume = 0
        
        for idx, linha in df_copia.iterrows():
            if linha['semana_crypto'] != semana_atual:
                # Nova semana - resetar acumuladores
                semana_atual = linha['semana_crypto']
                soma_preco_volume = 0
                soma_volume = 0
            
            # Acumular
            preco = (linha['high'] + linha['low'] + linha['close']) / 3
            soma_preco_volume += preco * linha['volume']
            soma_volume += linha['volume']
            
            # Calcular VWAP
            if soma_volume > 0:
                vwap = soma_preco_volume / soma_volume
            else:
                vwap = preco
                
            valores_vwap.append(vwap)
        
        return pd.Series(valores_vwap, index=df.index)
    
    def _calcular_vwap_mensal(self, df, preco_tipico):
        """VWAP mensal - reset primeiro dia do mês"""
        df_copia = df.copy()
        df_copia['mes'] = df_copia.index.to_period('M')
        
        valores_vwap = []
        mes_atual = None
        soma_preco_volume = 0
        soma_volume = 0
        
        for idx, linha in df_copia.iterrows():
            if linha['mes'] != mes_atual:
                mes_atual = linha['mes']
                soma_preco_volume = 0
                soma_volume = 0
            
            preco = (linha['high'] + linha['low'] + linha['close']) / 3
            soma_preco_volume += preco * linha['volume']
            soma_volume += linha['volume']
            
            if soma_volume > 0:
                vwap = soma_preco_volume / soma_volume
            else:
                vwap = preco
                
            valores_vwap.append(vwap)
        
        return pd.Series(valores_vwap, index=df.index)
    
    def _obter_numero_semana_crypto(self, indice_datetime):
        """Calcula número da semana crypto (inicia domingo 21h)"""
        semanas = []
        for dt in indice_datetime:
            # Ajustar para semana crypto
            if dt.hour < 21 and dt.weekday() == 6:  # Domingo antes das 21h
                # Ainda é semana anterior
                inicio_semana = dt - timedelta(days=7)
            else:
                # Encontrar domingo 21h mais próximo no passado
                dias_desde_domingo = (dt.weekday() + 1) % 7
                inicio_semana = dt - timedelta(days=dias_desde_domingo)
                if dt.weekday() != 6 or dt.hour < 21:
                    inicio_semana = inicio_semana - timedelta(days=7)
            
            # Usar ano e semana como identificador
            id_semana = f"{inicio_semana.year}-{inicio_semana.isocalendar()[1]}"
            semanas.append(id_semana)
        
        return semanas
    
    def analisar_posicao_vwap(self, preco_atual, vwap_diario, vwap_semanal, vwap_mensal=None):
        """
        Analisa posição do preço atual vs VWAPs
        Retorna análise institucional completa
        """
        try:
            # Distâncias percentuais
            distancia_diaria = ((preco_atual - vwap_diario) / vwap_diario) * 100
            distancia_semanal = ((preco_atual - vwap_semanal) / vwap_semanal) * 100
            
            # Posições básicas
            posicao_diaria = 'ACIMA' if distancia_diaria > 0 else 'ABAIXO'
            posicao_semanal = 'ACIMA' if distancia_semanal > 0 else 'ABAIXO'
            
            # Bias institucional
            bias_institucional = self._determinar_bias_institucional(distancia_diaria, distancia_semanal)
            
            # Níveis de suporte/resistência
            niveis_sr = self._identificar_niveis_sr(preco_atual, vwap_diario, vwap_semanal)
            
            # Alertas por desvio extremo
            alertas = self._gerar_alertas_desvio(distancia_diaria, distancia_semanal)
            
            # Expectativa de movimento
            expectativa_preco = self._calcular_expectativa_preco(distancia_diaria, distancia_semanal)
            
            return {
                'preco_atual': preco_atual,
                'vwap_diario': vwap_diario,
                'vwap_semanal': vwap_semanal,
                'distancia_diaria_pct': round(distancia_diaria, 2),
                'distancia_semanal_pct': round(distancia_semanal, 2),
                'posicao_diaria': posicao_diaria,
                'posicao_semanal': posicao_semanal,
                'bias_institucional': bias_institucional,
                'niveis_suporte_resistencia': niveis_sr,
                'alertas_desvio': alertas,
                'expectativa_preco': expectativa_preco,
                'score_confluencia': self._calcular_score_confluencia(distancia_diaria, distancia_semanal),
                'contexto_educativo': self._gerar_contexto_educativo(bias_institucional, distancia_diaria)
            }
            
        except Exception as e:
            print(f"Erro na análise posição VWAP: {e}")
            return None
    
    def _determinar_bias_institucional(self, dist_diaria, dist_semanal):
        """
        Determina bias institucional baseado nas distâncias VWAP
        Baseado em comportamento observado de traders institucionais
        """
        # Zonas de compra institucional (abaixo VWAP)
        if dist_diaria <= -3.0 and dist_semanal <= -2.0:
            return 'COMPRA_FORTE'  # Zona de compra agressiva
        elif dist_diaria <= -1.5 and dist_semanal <= -1.0:
            return 'COMPRA'  # Zona de acumulação
        elif -1.5 <= dist_diaria <= 1.5 and -1.0 <= dist_semanal <= 1.0:
            return 'NEUTRO'  # Zona de equilíbrio
        elif dist_diaria >= 1.5 and dist_semanal >= 1.0:
            return 'VENDA'  # Zona de distribuição
        elif dist_diaria >= 3.0 and dist_semanal >= 2.0:
            return 'VENDA_FORTE'  # Zona de venda agressiva
        else:
            return 'MISTO'  # Sinais conflitantes
    
    def _identificar_niveis_sr(self, preco_atual, vwap_diario, vwap_semanal):
        """Identifica níveis de suporte e resistência dinâmicos"""
        niveis = {
            'vwap_diario': {
                'preco': vwap_diario,
                'tipo': 'SUPORTE' if preco_atual > vwap_diario else 'RESISTENCIA',
                'forca': 'ALTA',
                'distancia_pct': abs((preco_atual - vwap_diario) / preco_atual * 100)
            },
            'vwap_semanal': {
                'preco': vwap_semanal,
                'tipo': 'SUPORTE' if preco_atual > vwap_semanal else 'RESISTENCIA',
                'forca': 'MUITO_ALTA',
                'distancia_pct': abs((preco_atual - vwap_semanal) / preco_atual * 100)
            }
        }
        
        # Identificar qual VWAP é mais relevante
        dist_diaria = abs(preco_atual - vwap_diario)
        dist_semanal = abs(preco_atual - vwap_semanal)
        
        niveis['nivel_primario'] = 'vwap_diario' if dist_diaria < dist_semanal else 'vwap_semanal'
        
        return niveis
    
    def _gerar_alertas_desvio(self, dist_diaria, dist_semanal):
        """Gera alertas para desvios extremos"""
        alertas = []
        
        # Alertas desvio diário
        if abs(dist_diaria) >= self.desvio_extremo:
            direcao = "acima" if dist_diaria > 0 else "abaixo"
            alertas.append({
                'tipo': 'DESVIO_EXTREMO_DIARIO',
                'mensagem': f"Preço {abs(dist_diaria):.1f}% {direcao} VWAP diária",
                'severidade': 'ALTA',
                'acao_sugerida': 'REVERSAO_ESPERADA' if abs(dist_diaria) > 4 else 'MONITORAR'
            })
        elif abs(dist_diaria) >= self.limite_desvio:
            direcao = "acima" if dist_diaria > 0 else "abaixo"
            alertas.append({
                'tipo': 'DESVIO_DIARIO',
                'mensagem': f"Preço {abs(dist_diaria):.1f}% {direcao} VWAP diária",
                'severidade': 'MEDIA',
                'acao_sugerida': 'MONITORAR'
            })
        
        # Alertas desvio semanal
        if abs(dist_semanal) >= self.desvio_extremo:
            direcao = "acima" if dist_semanal > 0 else "abaixo"
            alertas.append({
                'tipo': 'DESVIO_EXTREMO_SEMANAL',
                'mensagem': f"Preço {abs(dist_semanal):.1f}% {direcao} VWAP semanal",
                'severidade': 'ALTA',
                'acao_sugerida': 'REVERSAO_FORTE_ESPERADA'
            })
        
        return alertas
    
    def _calcular_expectativa_preco(self, dist_diaria, dist_semanal):
        """Calcula expectativa de movimento do preço (efeito ímã VWAP)"""
        # VWAP age como "ímã" - preços tendem a retornar
        puxao_diario = -dist_diaria * 0.3  # 30% da distância diária
        puxao_semanal = -dist_semanal * 0.2  # 20% da distância semanal
        
        movimento_esperado_total = puxao_diario + puxao_semanal
        
        return {
            'movimento_esperado_pct': round(movimento_esperado_total, 2),
            'direcao': 'ALTA' if movimento_esperado_total > 0 else 'BAIXA' if movimento_esperado_total < 0 else 'NEUTRO',
            'forca': 'FORTE' if abs(movimento_esperado_total) > 2 else 'MODERADA' if abs(movimento_esperado_total) > 0.5 else 'FRACA',
            'explicacao': 'Efeito ímã VWAP - preço tende a retornar à média ponderada'
        }
    
    def _calcular_score_confluencia(self, dist_diaria, dist_semanal):
        """Calcula score de confluência VWAP (0-10)"""
        score = 5  # Base neutra
        
        # Mesmo lado (ambos acima ou abaixo)
        if (dist_diaria > 0 and dist_semanal > 0) or (dist_diaria < 0 and dist_semanal < 0):
            score += 2  # Confluência direcional
        
        # Distâncias moderadas (não extremas)
        if 0.5 <= abs(dist_diaria) <= 2.0:
            score += 1  # Distância diária ideal
        if 0.5 <= abs(dist_semanal) <= 2.0:
            score += 1  # Distância semanal ideal
        
        # Proximidade do VWAP (oportunidade)
        if abs(dist_diaria) < 0.5:
            score += 1  # Muito próximo do VWAP diário
        
        return min(10, max(0, score))
    
    def _gerar_contexto_educativo(self, bias, distancia_diaria):
        """Gera contexto educativo para o usuário"""
        contextos = {
            'COMPRA_FORTE': "Zona de forte interesse institucional de compra. Preço muito abaixo da VWAP indica possível oportunidade.",
            'COMPRA': "Zona de acumulação institucional. Preço abaixo da VWAP pode atrair compradores.",
            'NEUTRO': "Preço próximo do equilíbrio VWAP. Aguardar direção antes de posicionar.",
            'VENDA': "Zona de distribuição institucional. Preço acima da VWAP pode encontrar resistência.",
            'VENDA_FORTE': "Zona de forte pressão vendedora. Preço muito acima da VWAP indica possível correção.",
            'MISTO': "Sinais conflitantes entre timeframes. Aguardar melhor definição."
        }
        
        contexto_base = contextos.get(bias, "Análise VWAP inconclusiva.")
        
        # Adicionar informação sobre o efeito ímã
        if abs(distancia_diaria) > 2:
            contexto_base += f" EFEITO ÍMÃ: Desvio {abs(distancia_diaria):.1f}% pode gerar retorno à VWAP."
        
        return contexto_base
    
    def calcular_contribuicao_score_vwap(self, analise_vwap):
        """
        Calcula contribuição do VWAP para o score geral do sistema
        Retorna: 0-12 pontos para integração com score atual
        """
        if not analise_vwap:
            return 0
        
        bias = analise_vwap.get('bias_institucional', 'NEUTRO')
        confluencia = analise_vwap.get('score_confluencia', 5)
        alertas = analise_vwap.get('alertas_desvio', [])
        
        # Score base por bias
        scores_bias = {
            'COMPRA_FORTE': 12,
            'COMPRA': 8,
            'NEUTRO': 4,
            'VENDA': 2,
            'VENDA_FORTE': 1,
            'MISTO': 3
        }
        
        score_base = scores_bias.get(bias, 4)
        
        # Ajuste por confluência
        multiplicador_confluencia = confluencia / 10  # 0.0 a 1.0
        
        # Bonus por alertas de extremos (oportunidade contrarian)
        bonus_extremo = 0
        for alerta in alertas:
            if alerta.get('severidade') == 'ALTA':
                bonus_extremo += 2
        
        score_final = (score_base * multiplicador_confluencia) + bonus_extremo
        return min(12, max(0, round(score_final)))
    
    def validar_contexto_vwap(self, analise_vwap, outros_indicadores):
        """
        CRÍTICO: VWAP nunca usado isoladamente
        Valida contexto com outros indicadores antes de confirmar sinal
        """
        if not analise_vwap or not outros_indicadores:
            return False
        
        bias_vwap = analise_vwap.get('bias_institucional', 'NEUTRO')
        
        # Requer confirmação de pelo menos 2 outros indicadores
        confirmacoes = 0
        
        # Confirmação RSI
        if 'rsi' in outros_indicadores:
            rsi = outros_indicadores['rsi']
            if bias_vwap in ['COMPRA_FORTE', 'COMPRA'] and rsi < 40:
                confirmacoes += 1
            elif bias_vwap in ['VENDA_FORTE', 'VENDA'] and rsi > 60:
                confirmacoes += 1
        
        # Confirmação Volume
        if 'ratio_volume' in outros_indicadores:
            ratio_volume = outros_indicadores['ratio_volume']
            if ratio_volume > 1.3:  # Volume acima da média
                confirmacoes += 1
        
        # Confirmação MACD
        if 'sinal_macd' in outros_indicadores:
            macd_bullish = outros_indicadores.get('macd', 0) > outros_indicadores.get('sinal_macd', 0)
            if bias_vwap in ['COMPRA_FORTE', 'COMPRA'] and macd_bullish:
                confirmacoes += 1
            elif bias_vwap in ['VENDA_FORTE', 'VENDA'] and not macd_bullish:
                confirmacoes += 1
        
        # Retorna True apenas se houver pelo menos 2 confirmações
        return confirmacoes >= 2
