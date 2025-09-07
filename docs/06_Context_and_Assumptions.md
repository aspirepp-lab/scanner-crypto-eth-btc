# 06. Context and Assumptions

Este documento reúne todas as premissas técnicas, fontes de dados, definições de regime de mercado e restrições operacionais do projeto Scanner Crypto ETH/BTC.

---

## Fontes de Dados

- **Binance (via CCXT)**: dados de mercado em tempo real e históricos para pares spot e futuros.  
- **Trading Economics API**: indicadores macroeconômicos como inflação, juros, PIB, desemprego.  
- **alternative.me**: índice de sentimento Fear & Greed para o mercado cripto.  
- **Twitter/X API**: análise de sentimento por palavras-chave e volume de menções.

---

## Modelos de Dados

- **Logs**: armazenados em SQLite ou arquivos JSON, com timestamp, par, setup, score e status.  
- **Backtest**: estrutura em pandas DataFrame, com métricas como win rate, lucro médio, drawdown.  
- **Score**: valor numérico entre 0 e 100, calculado com base em confluência de setups, volume, volatilidade e contexto externo.  
- **Alertas**: enviados via Telegram, com ícones, legenda, explicação e link para gráfico.

---

## Limites e Restrições

- **Rate limits** das APIs externas devem ser respeitados para evitar bloqueios.  
- **Lookback padrão** para indicadores: 50 candles.  
- **Janela de correlação móvel**: 30 dias para análise entre BTC e índices globais.  
- **Sessões de mercado** definidas por horário UTC: Ásia, Europa, EUA.  
- **Execução**: o sistema não realiza ordens reais, apenas sinaliza oportunidades.

---

## Definições de Regime de Mercado

- **Tendencial forte**: ADX > 25 e direção clara (ex: média móvel inclinada).  
- **Lateralidade**: ADX < 20 e ausência de direção predominante.  
- **Alto risco**:  
  - VIX acima do percentil 80 histórico  
  - Fear & Greed acima de 80 (euforia) ou abaixo de 20 (pânico)  
  - Correlação BTC ↔ S&P > 0.8 (risco sistêmico)

Esses regimes são usados para ajustar filtros, score e comportamento dos alertas.

---

## Premissas Técnicas

- O projeto é modular e pode ser expandido com novos indicadores, fontes e interfaces.  
- O código é compatível com Python 3.11+ e segue boas práticas de logging, versionamento e testes.  
- A estrutura permite uso pessoal, validação estatística e escalonamento futuro.  
- A documentação deve ser atualizada conforme novas ideias forem implementadas.

---

## Observações

Este documento serve como referência para retomada do projeto em qualquer momento.  
Ele deve ser revisado sempre que houver mudanças nas fontes de dados, lógica de score ou estrutura de execução.
