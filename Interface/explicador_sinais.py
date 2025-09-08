# interface/explicador_sinais.py
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

class ExplicadorSinais:
    """
    Sistema de Explicações Educativas para Sinais de Trading
    Transforma análise técnica em conhecimento educativo
    """
    
    def __init__(self):
        self.templates_explicacao = {
            'base_tecnica': "📊 ANÁLISE TÉCNICA:\n{indicadores}",
            'contexto_vwap': "🏦 CONTEXTO VWAP:\n{analise_vwap}",
            'contexto_macro': "🌍 CONTEXTO MACRO:\n{analise_macro}",
            'gestao_risco': "💰 GESTÃO DE RISCO:\n{detalhes_posicao}",
            'confluencia': "🎯 CONFLUÊNCIA:\n{analise_confluencia}",
            'educativo': "🎓 CONCEITOS:\n{conteudo_educativo}"
        }
        
        # Biblioteca educativa expandida
        self.biblioteca_educativa = {
            'explicacao_vwap': {
                'basico': """VWAP (Volume Weighted Average Price):
• Preço médio ponderado pelo volume
• Referência institucional padrão
• Efeito "ímã" - preço tende a retornar""",
                
                'detalhado': """VWAP - Ferramenta Institucional:
• Cálculo: Σ(Preço × Volume) / Σ(Volume)
• Usado por fundos e bancos como benchmark
• Abaixo VWAP = Zona de compra institucional
• Acima VWAP = Possível resistência/distribuição
• Desvios >3% frequentemente revertem
• Reset: Diário (00:00 UTC), Semanal (Dom 21h)""",
                
                'profissional': """VWAP - Análise Institucional Avançada:
• Método Maria Silveira: VWAP ancorada em eventos
• Timeframes múltiplos revelam estrutura institucional
• Confluência VWAP D+S+M = zonas de alta probabilidade
• Volume Profile + VWAP = mapeamento institucional
• Desvios extremos (>4%) = oportunidades contrarian
• Bias institucional: Compra Forte (<-3%), Venda Forte (>+3%)"""
            },
            
            'explicacao_analise_macro': {
                'basico': """Contexto Macro:
• Eventos econômicos afetam crypto
• FOMC = reunião do Fed americano
• Fear & Greed = sentimento do mercado""",
                
                'detalhado': """Análise Macro Crypto:
• FOMC: Decisões de juros impactam crypto
• Fear & Greed Index: 0-100 (medo-ganância)
• Volatilidade aumenta em eventos macro
• Position sizing deve ajustar por risco
• Efeito weekend: menor liquidez""",
                
                'profissional': """Contexto Macro - Visão Institucional:
• Proximidade FOMC: Volatilidade 2-5x normal
• Correlação Risk-on/Risk-off com tradicional
• Força DXY = fraqueza crypto (geralmente)
• Avaliação impacto calendário regulatório
• Análise integrada flow institucional
• Monitoramento correlação cross-asset"""
            },
            
            'explicacao_indicadores_tecnicos': {
                'rsi': """RSI (Relative Strength Index):
• Mede força do movimento (0-100)
• <30 = Oversold (possível alta)
• >70 = Overbought (possível queda)
• Divergências indicam reversão""",
                
                'macd': """MACD (Moving Average Convergence Divergence):
• Cruzamento de médias móveis
• Linha > Sinal = Momentum bullish
• Histograma crescente = força aumentando
• Divergências antecipam reversões""",
                
                'volume': """Análise de Volume:
• Volume confirma movimento de preço
• Alto volume = interesse institucional
• Breakout + volume = validação
• Volume decrescente = perda interesse""",
                
                'confluencia': """Confluência de Indicadores:
• Múltiplos sinais na mesma direção
• Reduz falsos positivos significativamente
• RSI + MACD + Volume + VWAP = alta confiança
• Mínimo 3 confluências para sinal forte"""
            }
        }
        
        # Templates de explicação por tipo de sinal
        self.explicacoes_tipo_sinal = {
            'breakout': """PADRÃO BREAKOUT:
• Preço rompe resistência com volume
• Volume alto confirma interesse comprador
• Target: Altura do padrão projetada
• Stop: Abaixo da resistência rompida""",
            
            'reversao': """PADRÃO REVERSÃO:
• Sinais de mudança de tendência
• RSI divergente + Volume anômalo
• VWAP como suporte/resistência dinâmica
• Confluência múltipla aumenta probabilidade""",
            
            'continuacao': """PADRÃO CONTINUAÇÃO:
• Tendência principal mantida
• Correção técnica normal
• Volume mantém interesse
• VWAP alinhada com direção principal""",
            
            'institucional': """ATIVIDADE INSTITUCIONAL:
• VWAP como referência principal
• Volume Profile mostra interesse
• Detecção smart money ativa
• Timing institucional identificado"""
        }
    
    def explicar_sinal_completo(self, dados_sinal: Dict) -> str:
        """
        Gera explicação completa e educativa do sinal
        Args:
            dados_sinal: Dict com todos dados do sinal
        Returns:
            String formatada com explicação completa
        """
        try:
            partes_explicacao = []
            
            # 1. Resumo executivo
            resumo = self._gerar_resumo_executivo(dados_sinal)
            partes_explicacao.append(resumo)
            
            # 2. Análise técnica base
            explicacao_tecnica = self._explicar_base_tecnica(dados_sinal)
            partes_explicacao.append(explicacao_tecnica)
            
            # 3. Contexto VWAP (se disponível)
            if 'analise_vwap' in dados_sinal:
                explicacao_vwap = self._explicar_contexto_vwap(dados_sinal['analise_vwap'])
                partes_explicacao.append(explicacao_vwap)
            
            # 4. Contexto macro
            if 'analise_macro' in dados_sinal:
                explicacao_macro = self._explicar_contexto_macro(dados_sinal['analise_macro'])
                partes_explicacao.append(explicacao_macro)
            
            # 5. Confluência e probabilidade
            explicacao_confluencia = self._explicar_confluencia(dados_sinal)
            partes_explicacao.append(explicacao_confluencia)
            
            # 6. Gestão de risco
            explicacao_risco = self._explicar_gestao_risco(dados_sinal)
            partes_explicacao.append(explicacao_risco)
            
            # 7. Conceitos educativos
            conteudo_educativo = self._adicionar_contexto_educativo(dados_sinal)
            partes_explicacao.append(conteudo_educativo)
            
            return "\n\n".join(partes_explicacao)
            
        except Exception as e:
            return f"Erro ao gerar explicação: {e}"
    
    def _gerar_resumo_executivo(self, dados_sinal: Dict) -> str:
        """Gera resumo executivo do sinal"""
        try:
            simbolo = dados_sinal.get('simbolo', 'CRYPTO')
            score = dados_sinal.get('score_aprimorado', dados_sinal.get('score', 0))
            tipo_sinal = dados_sinal.get('tipo_sinal', 'TECNICO')
            
            confianca = self._determinar_nivel_confianca(score)
            recomendacao = self._determinar_recomendacao(score, dados_sinal)
            
            resumo = f"""🎯 RESUMO EXECUTIVO - {simbolo}
            
Score: {score:.0f}/100 ({confianca})
Tipo: {tipo_sinal}
Recomendação: {recomendacao}"""
            
            return resumo
            
        except Exception as e:
            return f"Erro no resumo: {e}"
    
    def _explicar_base_tecnica(self, dados_sinal: Dict) -> str:
        """Explica base técnica detalhadamente"""
        try:
            indicadores = []
            
            # Análise RSI
            if 'rsi' in dados_sinal:
                rsi = dados_sinal['rsi']
                explicacao_rsi = self._explicar_rsi(rsi)
                indicadores.append(f"• RSI: {rsi:.1f} - {explicacao_rsi}")
            
            # Análise MACD
            if 'macd' in dados_sinal and 'sinal_macd' in dados_sinal:
                macd = dados_sinal['macd']
                sinal_macd = dados_sinal['sinal_macd']
                explicacao_macd = self._explicar_macd(macd, sinal_macd)
                indicadores.append(f"• MACD: {explicacao_macd}")
            
            # Análise Volume
            if 'ratio_volume' in dados_sinal:
                ratio_volume = dados_sinal['ratio_volume']
                explicacao_volume = self._explicar_volume(ratio_volume)
                indicadores.append(f"• Volume: {ratio_volume:.1f}x - {explicacao_volume}")
            
            # Análise OBV
            if 'tendencia_obv' in dados_sinal:
                tendencia_obv = dados_sinal['tendencia_obv']
                explicacao_obv = "Compradores dominando" if tendencia_obv > 0 else "Vendedores dominando"
                indicadores.append(f"• OBV: {explicacao_obv}")
            
            base_tecnica = self.templates_explicacao['base_tecnica'].format(
                indicadores="\n".join(indicadores) if indicadores else "Análise técnica básica"
            )
            
            return base_tecnica
            
        except Exception as e:
            return f"Erro análise técnica: {e}"
    
    def _explicar_rsi(self, rsi: float) -> str:
        """Explica RSI contextualmente"""
        if rsi < 20:
            return "Oversold extremo - pressão vendedora excessiva, reversão provável"
        elif rsi < 30:
            return "Oversold - zona de possível compra, aguardar confirmação"
        elif rsi < 40:
            return "Fraqueza moderada - tendência baixista ainda ativa"
        elif rsi > 80:
            return "Overbought extremo - correção iminente, cautela"
        elif rsi > 70:
            return "Overbought - zona de possível venda, monitorar divergências"
        elif rsi > 60:
            return "Força moderada - tendência altista saudável"
        else:
            return "Zona neutra - aguardar definição direcional"
    
    def _explicar_macd(self, macd: float, sinal_macd: float) -> str:
        """Explica MACD contextualmente"""
        if macd > sinal_macd:
            momentum = "crescente" if macd > 0 else "recuperando"
            return f"Bullish ({momentum}) - momentum favor compradores"
        else:
            momentum = "decrescente" if macd < 0 else "enfraquecendo"
            return f"Bearish ({momentum}) - momentum favor vendedores"
    
    def _explicar_volume(self, ratio_volume: float) -> str:
        """Explica volume contextualmente"""
        if ratio_volume > 3.0:
            return "Volume extremo - interesse institucional forte"
        elif ratio_volume > 2.0:
            return "Volume alto - validação do movimento"
        elif ratio_volume > 1.5:
            return "Volume acima média - interesse crescente"
        elif ratio_volume > 0.8:
            return "Volume normal - sem sinais especiais"
        else:
            return "Volume baixo - cautela, movimento não validado"
    
    def _explicar_contexto_vwap(self, analise_vwap: Dict) -> str:
        """Explica contexto VWAP detalhadamente"""
        try:
            dist_diaria = analise_vwap.get('distancia_diaria_pct', 0)
            dist_semanal = analise_vwap.get('distancia_semanal_pct', 0)
            bias_institucional = analise_vwap.get('bias_institucional', 'NEUTRO')
            contexto_educativo = analise_vwap.get('contexto_educativo', '')
            
            explicacao_vwap = f"""🏦 CONTEXTO VWAP:
• Diária: {dist_diaria:+.1f}% ({analise_vwap.get('posicao_diaria', 'N/A')})
• Semanal: {dist_semanal:+.1f}% ({analise_vwap.get('posicao_semanal', 'N/A')})
• Bias Institucional: {bias_institucional}

📚 EXPLICAÇÃO:
{contexto_educativo}

🎯 NÍVEIS CHAVE:
• VWAP Diária: ${analise_vwap.get('vwap_diario', 0):,.2f}
• VWAP Semanal: ${analise_vwap.get('vwap_semanal', 0):,.2f}"""
            
            # Adicionar alertas se existirem
            if 'alertas_desvio' in analise_vwap:
                alertas = analise_vwap['alertas_desvio']
                if alertas:
                    textos_alerta = [f"⚠️ {alerta['mensagem']}" for alerta in alertas]
                    explicacao_vwap += f"\n\n🚨 ALERTAS:\n" + "\n".join(textos_alerta)
            
            return explicacao_vwap
            
        except Exception as e:
            return f"Erro explicação VWAP: {e}"
    
    def _explicar_contexto_macro(self, analise_macro: Dict) -> str:
        """Explica contexto macro detalhadamente"""
        try:
            score_risco = analise_macro.get('score_risco_total', 0)
            nivel_risco = analise_macro.get('nivel_risco', 'DESCONHECIDO')
            ajuste_pos = analise_macro.get('ajuste_posicao', 1.0)
            explicacao = analise_macro.get('explicacao', '')
            recomendacao = analise_macro.get('recomendacao', '')
            
            explicacao_macro = f"""🌍 CONTEXTO MACRO:
• Score Risco: {score_risco:.1f}/10 ({nivel_risco})
• Ajuste Posição: {ajuste_pos:.1f}x
• Situação: {explicacao}

📋 BREAKDOWN RISCOS:"""
            
            # Adicionar breakdown se disponível
            if 'breakdown_risco' in analise_macro:
                breakdown = analise_macro['breakdown_risco']
                for tipo_risco, valor in breakdown.items():
                    if valor > 0:
                        nome_risco = tipo_risco.replace('_', ' ').title()
                        explicacao_macro += f"\n• {nome_risco}: {valor:.1f}"
            
            explicacao_macro += f"\n\n💡 RECOMENDAÇÃO:\n{recomendacao}"
            
            # Próximo evento de risco
            if 'proximo_evento_risco' in analise_macro:
                proximo_evento = analise_macro['proximo_evento_risco']
                if proximo_evento.get('evento') and proximo_evento.get('evento') != 'Nenhum evento major identificado':
                    explicacao_macro += f"\n\n📅 PRÓXIMO EVENTO:\n{proximo_evento['evento']}"
                    if proximo_evento.get('dias_restantes'):
                        explicacao_macro += f" (em {proximo_evento['dias_restantes']} dias)"
            
            return explicacao_macro
            
        except Exception as e:
            return f"Erro explicação macro: {e}"
    
    def _explicar_confluencia(self, dados_sinal: Dict) -> str:
        """Explica confluência de fatores"""
        try:
            confluencias = []
            score_total = dados_sinal.get('score_aprimorado', dados_sinal.get('score', 0))
            
            # Identificar confluências ativas
            if dados_sinal.get('rsi', 0) < 35:
                confluencias.append("RSI Oversold")
            
            if dados_sinal.get('ratio_volume', 0) > 1.5:
                confluencias.append("Volume Elevado")
            
            if 'analise_vwap' in dados_sinal:
                bias_vwap = dados_sinal['analise_vwap'].get('bias_institucional', '')
                if 'COMPRA' in bias_vwap:
                    confluencias.append("VWAP Bullish")
            
            if 'analise_macro' in dados_sinal:
                risco_macro = dados_sinal['analise_macro'].get('score_risco_total', 5)
                if risco_macro < 3:
                    confluencias.append("Macro Favorável")
            
            count_confluencia = len(confluencias)
            nivel_confianca = self._calcular_confianca_confluencia(count_confluencia)
            
            explicacao_confluencia = f"""🎯 ANÁLISE DE CONFLUÊNCIA:
            
Fatores Confirmando: {count_confluencia}
• {' + '.join(confluencias) if confluencias else 'Análise individual'}

Confiança: {nivel_confianca}
Score Final: {score_total:.0f}/100

📊 INTERPRETAÇÃO:
{self._interpretar_nivel_confluencia(count_confluencia)}"""
            
            return explicacao_confluencia
            
        except Exception as e:
            return f"Erro análise confluência: {e}"
    
    def _explicar_gestao_risco(self, dados_sinal: Dict) -> str:
        """Explica gestão de risco detalhadamente"""
        try:
            entrada = dados_sinal.get('preco_entrada', 0)
            stop = dados_sinal.get('stop_loss', 0)
            target = dados_sinal.get('target', 0)
            tamanho_posicao = dados_sinal.get('tamanho_posicao', 0)
            
            # Calcular risk/reward
            if entrada > 0 and stop > 0 and target > 0:
                valor_risco = entrada - stop
                valor_recompensa = target - entrada
                ratio_rr = valor_recompensa / valor_risco if valor_risco > 0 else 0
            else:
                ratio_rr = 0
            
            explicacao_risco = f"""💰 GESTÃO DE RISCO:
            
Entrada: R$ {entrada:,.2f}
Stop Loss: R$ {stop:,.2f}
Target: R$ {target:,.2f}
Risk/Reward: 1:{ratio_rr:.1f}

Posição Recomendada: R$ {tamanho_posicao:,.0f}
Perda Máxima: R$ {tamanho_posicao * (valor_risco/entrada if entrada > 0 else 0.02):,.0f}

🛡️ PROTEÇÕES ATIVAS:"""
            
            # Explicar ajustes macro
            if 'analise_macro' in dados_sinal:
                adj = dados_sinal['analise_macro'].get('ajuste_posicao', 1.0)
                if adj < 1.0:
                    reducao_pct = (1 - adj) * 100
                    explicacao_risco += f"\n• Posição reduzida {reducao_pct:.0f}% por risco macro"
            
            # Explicar tipo de stop
            explicacao_risco += f"\n• Stop dinâmico baseado em ATR"
            
            if 'analise_vwap' in dados_sinal:
                explicacao_risco += f"\n• Stop ajustado por níveis VWAP"
            
            return explicacao_risco
            
        except Exception as e:
            return f"Erro explicação risco: {e}"
    
    def _adicionar_contexto_educativo(self, dados_sinal: Dict) -> str:
        """Adiciona contexto educativo baseado no sinal"""
        try:
            conceitos = []
            
            # Conceito VWAP se presente
            if 'analise_vwap' in dados_sinal:
                conceitos.append("📚 VWAP INSTITUCIONAL:")
                conceitos.append(self.biblioteca_educativa['explicacao_vwap']['detalhado'])
            
            # Conceito Macro se relevante
            if 'analise_macro' in dados_sinal:
                risco_macro = dados_sinal['analise_macro'].get('score_risco_total', 0)
                if risco_macro > 3:
                    conceitos.append("\n📚 RISCO MACRO:")
                    conceitos.append(self.biblioteca_educativa['explicacao_analise_macro']['detalhado'])
            
            # Conceito confluência
            confluencias = self._contar_confluencias(dados_sinal)
            if confluencias >= 3:
                conceitos.append("\n📚 CONFLUÊNCIA:")
                conceitos.append(self.biblioteca_educativa['explicacao_indicadores_tecnicos']['confluencia'])
            
            conteudo_educativo = "\n".join(conceitos) if conceitos else "🎓 Use /aprenda_vwap para tutoriais detalhados"
            
            return f"🎓 CONCEITOS EDUCATIVOS:\n{conteudo_educativo}"
            
        except Exception as e:
            return f"Erro contexto educativo: {e}"
    
    def _determinar_nivel_confianca(self, score: float) -> str:
        """Determina nível de confiança baseado no score"""
        if score >= 85:
            return "MUITO ALTA"
        elif score >= 75:
            return "ALTA"
        elif score >= 65:
            return "MÉDIA-ALTA"
        elif score >= 55:
            return "MÉDIA"
        else:
            return "BAIXA"
    
    def _determinar_recomendacao(self, score: float, dados_sinal: Dict) -> str:
        """Determina recomendação baseada no score e contexto"""
        # Ajustar por risco macro
        risco_macro = 0
        if 'analise_macro' in dados_sinal:
            risco_macro = dados_sinal['analise_macro'].get('score_risco_total', 0)
        
        score_ajustado = score - (risco_macro * 2)  # Penaliza por risco macro
        
        if score_ajustado >= 85:
            return "EXECUTAR - Alta probabilidade"
        elif score_ajustado >= 75:
            return "CONSIDERAR - Boa oportunidade"
        elif score_ajustado >= 65:
            return "MONITORAR - Aguardar confirmação"
        else:
            return "AGUARDAR - Sinais insuficientes"
    
    def _calcular_confianca_confluencia(self, count_confluencia: int) -> str:
        """Calcula confiança baseada no número de confluências"""
        if count_confluencia >= 4:
            return "MUITO ALTA (4+ fatores)"
        elif count_confluencia >= 3:
            return "ALTA (3 fatores)"
        elif count_confluencia >= 2:
            return "MÉDIA (2 fatores)"
        elif count_confluencia >= 1:
            return "BAIXA (1 fator)"
        else:
            return "MUITO BAIXA (sem confluência)"
    
    def _interpretar_nivel_confluencia(self, count_confluencia: int) -> str:
        """Interpreta o nível de confluência"""
        if count_confluencia >= 4:
            return "Confluência excepcional - múltiplos fatores confirmam direção. Alta probabilidade de sucesso."
        elif count_confluencia >= 3:
            return "Boa confluência - vários fatores alinhados. Sinal confiável para execução."
        elif count_confluencia >= 2:
            return "Confluência moderada - alguns fatores confirmam. Considerar com gestão de risco adequada."
        elif count_confluencia >= 1:
            return "Confluência baixa - poucos fatores confirmam. Aguardar mais sinais antes de executar."
        else:
            return "Sem confluência - fatores não alinhados. Evitar execução até melhor definição."
    
    def _contar_confluencias(self, dados_sinal: Dict) -> int:
        """Conta número de confluências ativas"""
        count = 0
        
        if dados_sinal.get('rsi', 50) < 35 or dados_sinal.get('rsi', 50) > 65:
            count += 1
        
        if dados_sinal.get('ratio_volume', 1) > 1.5:
            count += 1
        
        if 'analise_vwap' in dados_sinal:
            bias = dados_sinal['analise_vwap'].get('bias_institucional', 'NEUTRO')
            if bias in ['COMPRA', 'COMPRA_FORTE', 'VENDA', 'VENDA_FORTE']:
                count += 1
        
        if 'analise_macro' in dados_sinal:
            risco = dados_sinal['analise_macro'].get('score_risco_total', 5)
            if risco < 3:  # Baixo risco = confluência positiva
                count += 1
        
        return count
    
    def gerar_explicacao_telegram(self, dados_sinal: Dict) -> str:
        """Gera explicação formatada para Telegram"""
        explicacao = self.explicar_sinal_completo(dados_sinal)
        
        # Adicionar comandos educativos
        comandos_educativos = [
            "",
            "🎓 APRENDER MAIS:",
            "/aprenda_vwap - Tutorial VWAP completo",
            "/contexto_macro - Situação macro atual",
            "/explica_risco - Por que posição foi ajustada",
            "/aprenda_confluencia - Como funciona confluência"
        ]
        
        return explicacao + "\n" + "\n".join(comandos_educativos)
    
    def explicar_conceito_especifico(self, conceito: str, nivel: str = 'detalhado') -> str:
        """Explica conceito específico em nível escolhido"""
        conceito_lower = conceito.lower()
        
        if 'vwap' in conceito_lower:
            return self.biblioteca_educativa['explicacao_vwap'].get(nivel, 'Conceito não encontrado')
        elif 'macro' in conceito_lower:
            return self.biblioteca_educativa['explicacao_analise_macro'].get(nivel, 'Conceito não encontrado')
        elif 'rsi' in conceito_lower:
            return self.biblioteca_educativa['explicacao_indicadores_tecnicos']['rsi']
        elif 'macd' in conceito_lower:
            return self.biblioteca_educativa['explicacao_indicadores_tecnicos']['macd']
        elif 'volume' in conceito_lower:
            return self.biblioteca_educativa['explicacao_indicadores_tecnicos']['volume']
        elif 'confluencia' in conceito_lower:
            return self.biblioteca_educativa['explicacao_indicadores_tecnicos']['confluencia']
        else:
            return "Conceito não encontrado. Conceitos disponíveis: VWAP, Macro, RSI, MACD, Volume, Confluência"
