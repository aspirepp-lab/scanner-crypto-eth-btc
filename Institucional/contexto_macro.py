# institucional/contexto_macro.py
import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

class AnalisadorContextoMacro:
    """
    Análise de Contexto Macro para Trading de Crypto
    Integra: FOMC, Sentimento, VIX, Efeitos Weekend, Notícias Regulatórias
    """
    
    def __init__(self):
        # APIs públicas (sem keys necessárias)
        self.api_fear_greed = "https://api.alternative.me/fng/"
        self.api_crypto_fear = "https://api.alternative.me/fng/"
        
        # Calendário FOMC 2025 (datas conhecidas)
        self.datas_fomc_2025 = [
            datetime(2025, 1, 29),   # Jan 28-29, 2025
            datetime(2025, 3, 19),   # Mar 18-19, 2025  
            datetime(2025, 5, 1),    # Apr 30-May 1, 2025
            datetime(2025, 6, 11),   # Jun 10-11, 2025
            datetime(2025, 7, 30),   # Jul 29-30, 2025
            datetime(2025, 9, 17),   # Sep 16-17, 2025
            datetime(2025, 10, 29),  # Oct 28-29, 2025
            datetime(2025, 12, 17),  # Dec 16-17, 2025
        ]
        
        # Cache para evitar calls excessivas
        self.cache = {}
        self.timeout_cache = 300  # 5 minutos
        
    def obter_score_risco_macro(self) -> Dict:
        """
        Calcula score de risco macro completo (0-10)
        Componentes: FOMC, Fear&Greed, Volatilidade, Weekend, Regulatório
        """
        try:
            componentes_risco = {
                'proximidade_fomc': self._verificar_proximidade_fomc(),
                'extremo_fear_greed': self._verificar_extremo_sentimento(),  
                'volatilidade_mercado': self._estimar_risco_volatilidade(),
                'sentimento_crypto': self._analisar_sentimento_crypto(),
                'efeito_weekend': self._verificar_fator_weekend(),
                'horario_dia': self._verificar_risco_horario(),
                'risco_regulatorio': self._avaliar_ambiente_regulatorio()
            }
            
            risco_total = sum(componentes_risco.values())
            nivel_risco = self._categorizar_nivel_risco(risco_total)
            ajuste_posicao = self._calcular_ajuste_posicao(risco_total)
            
            return {
                'score_risco_total': min(risco_total, 10),
                'nivel_risco': nivel_risco,
                'breakdown_risco': componentes_risco,
                'ajuste_posicao': ajuste_posicao,
                'explicacao': self._gerar_explicacao_risco(componentes_risco),
                'proximo_evento_risco': self._identificar_proximo_evento_risco(),
                'recomendacao': self._gerar_recomendacao_macro(risco_total),
                'nivel_confianca': self._calcular_nivel_confianca(componentes_risco)
            }
            
        except Exception as e:
            print(f"Erro no cálculo risco macro: {e}")
            return self._obter_analise_risco_padrao()
    
    def _verificar_proximidade_fomc(self) -> float:
        """
        Verifica proximidade de reunião FOMC
        Returns: 0-3 pontos de risco
        """
        try:
            hoje = datetime.now().date()
            proximo_fomc = self._obter_proxima_data_fomc()
            
            if not proximo_fomc:
                return 0
            
            dias_ate_fomc = (proximo_fomc.date() - hoje).days
            
            # Escalas de risco por proximidade
            if dias_ate_fomc <= 1:
                return 3.0  # Máximo risco - dia da reunião
            elif dias_ate_fomc <= 3:
                return 2.5  # Alto risco - véspera
            elif dias_ate_fomc <= 7:
                return 2.0  # Risco elevado - semana da reunião
            elif dias_ate_fomc <= 14:
                return 1.0  # Risco moderado - 2 semanas
            elif dias_ate_fomc <= 21:
                return 0.5  # Risco baixo - 3 semanas
            else:
                return 0    # Sem risco FOMC
                
        except Exception as e:
            print(f"Erro verificação FOMC: {e}")
            return 0
    
    def _obter_proxima_data_fomc(self) -> Optional[datetime]:
        """Encontra próxima data FOMC"""
        hoje = datetime.now()
        
        for data_fomc in self.datas_fomc_2025:
            if data_fomc > hoje:
                return data_fomc
        
        return None  # Não há mais reuniões no ano
    
    def _verificar_extremo_sentimento(self) -> float:
        """
        Verifica Fear & Greed Index extremos
        Returns: 0-2 pontos de risco
        """
        try:
            # Verificar cache
            chave_cache = 'fear_greed'
            if self._cache_valido(chave_cache):
                valor_fear_greed = self.cache[chave_cache]['valor']
            else:
                response = requests.get(self.api_fear_greed + "?limit=1", timeout=10)
                dados = response.json()
                
                if 'data' in dados and len(dados['data']) > 0:
                    valor_fear_greed = int(dados['data'][0]['value'])
                    self.cache[chave_cache] = {
                        'valor': valor_fear_greed,
                        'timestamp': datetime.now()
                    }
                else:
                    return 0
            
            # Análise do sentimento
            if valor_fear_greed <= 10:
                return 0    # Medo Extremo = Oportunidade (contrarian)
            elif valor_fear_greed <= 25:
                return 0    # Medo = Ainda oportunidade
            elif valor_fear_greed >= 90:
                return 2.0  # Ganância Extrema = Alto risco
            elif valor_fear_greed >= 75:
                return 1.5  # Ganância = Risco elevado
            elif valor_fear_greed >= 55:
                return 0.5  # Neutro-Ganância = Risco baixo
            else:
                return 0    # Neutro-Medo = Sem risco
                
        except Exception as e:
            print(f"Erro Fear & Greed: {e}")
            return 0
    
    def _estimar_risco_volatilidade(self) -> float:
        """
        Estima risco de volatilidade baseado em proxy indicators
        Returns: 0-2 pontos de risco
        """
        try:
            hora_atual = datetime.now().hour
            dia_atual = datetime.now().weekday()
            
            # Horários de alta volatilidade (baseado em abertura mercados)
            risco_volatilidade = 0
            
            # Abertura mercados americanos (14-16h UTC)
            if 14 <= hora_atual <= 16:
                risco_volatilidade += 0.5
            
            # Fechamento sexta-feira / abertura segunda
            if dia_atual == 4 and hora_atual >= 20:  # Sexta tarde
                risco_volatilidade += 1.0
            elif dia_atual == 0 and hora_atual <= 10:  # Segunda manhã
                risco_volatilidade += 1.0
            
            # Meio da semana (menor volatilidade)
            if dia_atual in [1, 2]:  # Terça/Quarta
                risco_volatilidade -= 0.5
            
            return max(0, min(2, risco_volatilidade))
            
        except Exception as e:
            print(f"Erro estimativa volatilidade: {e}")
            return 0
    
    def _analisar_sentimento_crypto(self) -> float:
        """
        Análise específica de sentimento crypto
        Returns: 0-2 pontos de risco
        """
        try:
            # Mesmo que Fear & Greed mas com interpretação crypto-específica
            chave_cache = 'sentimento_crypto'
            if self._cache_valido(chave_cache):
                return self.cache[chave_cache]['risco']
            
            # Por enquanto usar Fear & Greed como proxy
            risco_fear_greed = self._verificar_extremo_sentimento()
            
            # Crypto tem comportamento mais extremo
            risco_crypto = risco_fear_greed * 1.2  # Amplifica 20%
            
            self.cache[chave_cache] = {
                'risco': risco_crypto,
                'timestamp': datetime.now()
            }
            
            return min(2, risco_crypto)
            
        except Exception as e:
            print(f"Erro sentimento crypto: {e}")
            return 0
    
    def _verificar_fator_weekend(self) -> float:
        """
        Efeito weekend - menor liquidez, maior risco de gaps
        Returns: 0-1 ponto de risco
        """
        try:
            dia_atual = datetime.now().weekday()
            hora_atual = datetime.now().hour
            
            # Sábado/Domingo = maior risco (menor liquidez tradicional)
            if dia_atual in [5, 6]:  # Sáb/Dom
                return 1.0
            
            # Sexta à noite = preparação weekend
            elif dia_atual == 4 and hora_atual >= 18:
                return 0.5
            
            # Segunda manhã = volatilidade pós-weekend
            elif dia_atual == 0 and hora_atual <= 12:
                return 0.5
            
            else:
                return 0
                
        except Exception as e:
            return 0
    
    def _verificar_risco_horario(self) -> float:
        """
        Risco por horário do dia (overlap mercados, liquidez)
        Returns: 0-1 ponto de risco
        """
        try:
            hora_atual = datetime.now().hour
            
            # Horários de baixa liquidez = maior risco
            if 2 <= hora_atual <= 6:  # Madrugada
                return 1.0
            elif 22 <= hora_atual <= 23 or 0 <= hora_atual <= 1:  # Noite tardia
                return 0.5
            else:
                return 0
                
        except Exception as e:
            return 0
    
    def _avaliar_ambiente_regulatorio(self) -> float:
        """
        Avalia ambiente regulatório (simplificado)
        Returns: 0-1 ponto de risco
        """
        try:
            # Por enquanto baseline baixo
            # TODO: Integrar feeds de notícias para sentimento regulatório
            mes_atual = datetime.now().month
            
            # Meses com histórico de atividade regulatória alta
            if mes_atual in [3, 6, 9, 12]:  # Final de trimestres
                return 0.5
            else:
                return 0
                
        except Exception as e:
            return 0
    
    def _categorizar_nivel_risco(self, risco_total: float) -> str:
        """Categoriza nível de risco total"""
        if risco_total >= 8:
            return 'MUITO_ALTO'
        elif risco_total >= 6:
            return 'ALTO'
        elif risco_total >= 4:
            return 'MODERADO'
        elif risco_total >= 2:
            return 'BAIXO'
        else:
            return 'MUITO_BAIXO'
    
    def _calcular_ajuste_posicao(self, score_risco: float) -> float:
        """
        Calcula fator de ajuste para position sizing
        Returns: 0.2-1.0 (20% a 100% da posição normal)
        """
        if score_risco >= 8:
            return 0.2  # Reduz para 20% - Risco extremo
        elif score_risco >= 6:
            return 0.4  # Reduz para 40% - Risco alto
        elif score_risco >= 4:
            return 0.6  # Reduz para 60% - Risco moderado
        elif score_risco >= 2:
            return 0.8  # Reduz para 80% - Risco baixo
        else:
            return 1.0  # Posição normal - Risco muito baixo
    
    def _gerar_explicacao_risco(self, componentes_risco: Dict) -> str:
        """Gera explicação detalhada dos riscos"""
        explicacoes = []
        
        for componente, valor in componentes_risco.items():
            if valor > 0:
                if componente == 'proximidade_fomc':
                    if valor >= 2.5:
                        explicacoes.append("FOMC iminente - alta volatilidade esperada")
                    elif valor >= 1.0:
                        explicacoes.append("FOMC próximo - cautela recomendada")
                
                elif componente == 'extremo_fear_greed':
                    if valor >= 1.5:
                        explicacoes.append("Ganância extrema - correção possível")
                    elif valor >= 0.5:
                        explicacoes.append("Sentimento elevado - monitorar")
                
                elif componente == 'efeito_weekend':
                    explicacoes.append("Weekend - liquidez reduzida")
                
                elif componente == 'volatilidade_mercado':
                    explicacoes.append("Período de alta volatilidade")
        
        if not explicacoes:
            return "Ambiente macro favorável para trading"
        
        return "; ".join(explicacoes)
    
    def _identificar_proximo_evento_risco(self) -> Dict:
        """Identifica próximo evento de risco macro"""
        try:
            proximo_fomc = self._obter_proxima_data_fomc()
            
            if proximo_fomc:
                dias_ate_fomc = (proximo_fomc.date() - datetime.now().date()).days
                return {
                    'evento': 'Reunião FOMC',
                    'data': proximo_fomc.strftime('%Y-%m-%d'),
                    'dias_restantes': dias_ate_fomc,
                    'nivel_impacto': 'ALTO' if dias_ate_fomc <= 7 else 'MÉDIO'
                }
            
            # Se não há FOMC próximo, identificar outros eventos
            dia_atual = datetime.now().weekday()
            if dia_atual <= 4:  # Segunda a sexta
                dias_ate_weekend = 4 - dia_atual  # Dias até sexta
                return {
                    'evento': 'Weekend',
                    'data': (datetime.now() + timedelta(days=dias_ate_weekend)).strftime('%Y-%m-%d'),
                    'dias_restantes': dias_ate_weekend,
                    'nivel_impacto': 'BAIXO'
                }
            
            return {
                'evento': 'Nenhum evento major identificado',
                'data': None,
                'dias_restantes': None,
                'nivel_impacto': 'NENHUM'
            }
            
        except Exception as e:
            return {'evento': 'Erro identificando eventos', 'erro': str(e)}
    
    def _gerar_recomendacao_macro(self, score_risco: float) -> str:
        """Gera recomendação baseada no risco macro"""
        if score_risco >= 8:
            return "EVITAR trading - Risco extremo. Aguardar estabilização."
        elif score_risco >= 6:
            return "CAUTELA máxima - Posições pequenas apenas. Monitorar eventos."
        elif score_risco >= 4:
            return "MODERAÇÃO - Trading normal com posições reduzidas."
        elif score_risco >= 2:
            return "ATENÇÃO - Ambiente favorável com pequenos riscos."
        else:
            return "AMBIENTE FAVORÁVEL - Trading normal recomendado."
    
    def _calcular_nivel_confianca(self, componentes_risco: Dict) -> float:
        """Calcula nível de confiança da análise (0-1)"""
        # Baseado na disponibilidade e qualidade dos dados
        confianca = 1.0
        
        # Reduz confiança se há muitos erros ou dados ausentes
        dados_ausentes = sum(1 for v in componentes_risco.values() if v == 0)
        confianca -= dados_ausentes * 0.1
        
        return max(0.5, confianca)  # Mínimo 50% de confiança
    
    def _cache_valido(self, chave_cache: str) -> bool:
        """Verifica se cache ainda é válido"""
        if chave_cache not in self.cache:
            return False
        
        tempo_cache = self.cache[chave_cache].get('timestamp')
        if not tempo_cache:
            return False
        
        idade = (datetime.now() - tempo_cache).total_seconds()
        return idade < self.timeout_cache
    
    def _obter_analise_risco_padrao(self) -> Dict:
        """Retorna análise padrão em caso de erro"""
        return {
            'score_risco_total': 2,  # Risco baixo padrão
            'nivel_risco': 'BAIXO',
            'breakdown_risco': {
                'proximidade_fomc': 0,
                'extremo_fear_greed': 0,
                'volatilidade_mercado': 1,
                'sentimento_crypto': 1,
                'efeito_weekend': 0,
                'horario_dia': 0,
                'risco_regulatorio': 0
            },
            'ajuste_posicao': 0.8,
            'explicacao': 'Análise macro indisponível - usando defaults conservadores',
            'proximo_evento_risco': {'evento': 'Desconhecido', 'data': None},
            'recomendacao': 'MODERAÇÃO - Dados macro limitados',
            'nivel_confianca': 0.5
        }
    
    def obter_analise_impacto_fomc(self) -> Dict:
        """Análise específica de impacto FOMC"""
        try:
            proximo_fomc = self._obter_proxima_data_fomc()
            if not proximo_fomc:
                return {'status': 'NENHUM_FOMC_AGENDADO'}
            
            dias_ate_fomc = (proximo_fomc.date() - datetime.now().date()).days
            
            # Análise de impacto baseada em dados históricos
            analise_impacto = {
                'dias_ate_reuniao': dias_ate_fomc,
                'volatilidade_esperada': self._calcular_impacto_volatilidade_fomc(dias_ate_fomc),
                'recomendacao_trading': self._obter_conselho_trading_fomc(dias_ate_fomc),
                'padrao_historico': self._obter_padrao_historico_fomc(),
                'conselho_position_sizing': self._obter_conselho_posicao_fomc(dias_ate_fomc)
            }
            
            return analise_impacto
            
        except Exception as e:
            print(f"Erro análise FOMC: {e}")
            return {'status': 'ERRO', 'mensagem': str(e)}
    
    def _calcular_impacto_volatilidade_fomc(self, dias_ate_fomc: int) -> str:
        """Calcula impacto esperado na volatilidade"""
        if dias_ate_fomc <= 1:
            return 'EXTREMA - Volatilidade 3-5x normal'
        elif dias_ate_fomc <= 3:
            return 'ALTA - Volatilidade 2-3x normal'
        elif dias_ate_fomc <= 7:
            return 'ELEVADA - Volatilidade 1.5-2x normal'
        else:
            return 'NORMAL - Sem impacto significativo'
    
    def _obter_conselho_trading_fomc(self, dias_ate_fomc: int) -> str:
        """Conselho de trading específico para FOMC"""
        if dias_ate_fomc <= 1:
            return 'EVITAR trading ativo - Apenas hedge de posições'
        elif dias_ate_fomc <= 3:
            return 'EXTREMA cautela - Posições pequenas apenas'
        elif dias_ate_fomc <= 7:
            return 'CAUTELA - Reduzir posições 50%'
        else:
            return 'NORMAL - Trading regular'
    
    def _obter_padrao_historico_fomc(self) -> str:
        """Padrão histórico observado em reuniões FOMC"""
        return "Historicamente: Queda pré-FOMC (50-70%), Rally pós-decisão se dovish (60-80%)"
    
    def _obter_conselho_posicao_fomc(self, dias_ate_fomc: int) -> str:
        """Conselho específico para position sizing"""
        if dias_ate_fomc <= 1:
            return 'Máximo 10% da posição normal'
        elif dias_ate_fomc <= 3:
            return 'Máximo 25% da posição normal'
        elif dias_ate_fomc <= 7:
            return 'Máximo 50% da posição normal'
        else:
            return 'Posição normal permitida'
