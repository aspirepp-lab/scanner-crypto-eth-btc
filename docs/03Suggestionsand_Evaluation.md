# 03. Suggestions and Evaluation

| #  | Sugestão                                        | IR    | CD    | CM    | AN    | Fase        |
|----|-------------------------------------------------|-------|-------|-------|-------|-------------|
| 1  | Interface Streamlit/Dash                        | Alto  | Médio | Médio | Médio | 6           |
| 2  | Backtesting (backtrader/vectorbt)               | Alto  | Alto  | Médio | Alto  | 3           |
| 3  | Machine Learning leve (scikit-learn)            | Médio | Médio | Médio | Médio | 2–3¹        |
| 4  | Expansão de ativos/timeframes                   | Médio | Baixo | Baixo | Alto  | 4           |
| 5  | Logs e monitoramento (Grafana/Kibana)           | Alto  | Médio | Médio | Alto  | 2           |
| 6  | Gráficos com matplotlib ou Plotly               | Médio | Baixo | Baixo | Médio | Imediato¹   |
| 7  | Agendamento local (schedule/apscheduler)        | Baixo | Baixo | Baixo | Médio | Opcional    |
| 8  | Alertas avançados (python-telegram-bot)         | Médio | Médio | Médio | Alto  | 1           |
| 9  | Logs persistentes (Loki/arquivos .log)          | Alto  | Médio | Médio | Alto  | 2           |
| 10 | Notificações de erro no Telegram                | Médio | Baixo | Baixo | Alto  | 2           |
| 11 | Jobs paralelos por ativo/timeframe              | Médio | Médio | Médio | Médio | 2           |
| 12 | Testes automatizados (pytest)                   | Alto  | Médio | Médio | Alto  | 2           |
| 13 | `runtime.txt` para versão do Python             | Baixo | Baixo | Baixo | Médio | 1           |
| 14 | `requirements.txt` pronto para produção         | Baixo | Baixo | Baixo | Alto  | 1           |
| 15 | Logging estruturado vs `print`                  | Alto  | Baixo | Baixo | Alto  | 1           |
| 16 | Keep-alive (`while True`)                       | Baixo | Baixo | Baixo | Baixo | **Não**²    |
| 17 | Modularização de código                         | Alto  | Médio | Baixo | Alto  | 1           |
| 18 | Avaliação de resultados e confiabilidade        | Alto  | Médio | Baixo | Alto  | 2           |
| 19 | Separação lógica/API/Multiusuário (FastAPI)     | Alto  | Alto  | Alto  | Médio | 6           |
| 20 | Segurança e boas práticas (secrets, validação)  | Alto  | Baixo | Baixo | Alto  | 1           |
| 21 | Classificação visual de setups (cores, ícones)  | Alto  | Baixo | Baixo | Alto  | 1           |
| 22 | Explicações embutidas de setups                 | Alto  | Baixo | Baixo | Alto  | 1           |
| 23 | Comando no Telegram para explicação de setups   | Alto  | Baixo | Baixo | Alto  | 1           |
| 24 | Painel de performance (win rate, lucro médio)   | Alto  | Médio | Médio | Alto  | 2           |
| 25 | Filtro de volume mínimo (≥0.5× média)           | Alto  | Baixo | Baixo | Alto  | 1           |
| 26 | Tabela de legendas de setups (ícones, cores)    | Médio | Baixo | Baixo | Alto  | 1           |
| 27 | Pontuação dinâmica (confluência, volume, macro) | Alto  | Médio | Médio | Alto  | 2           |
| 28 | Performance por setup/par/horário e condição    | Médio | Médio | Médio | Alto  | 2           |
| 29 | Estrutura modular de pastas                     | Alto  | Médio | Baixo | Alto  | 1           |
| 30 | Pipeline completo de backtest                   | Alto  | Alto  | Médio | Alto  | 3           |
| 31 | Fibonacci (retração/extensão)                   | Alto  | Baixo | Baixo | Alto  | 4           |
| 32 | VWAP intradiário                                 | Médio | Baixo | Baixo | Médio | 4           |
| 33 | Padrões gráficos (bandeira, cunha)              | Alto  | Médio | Médio | Alto  | 4           |
| 34 | Price action (ABC, 1-2-3, pivôs)                 | Alto  | Baixo | Baixo | Alto  | 4           |
| 35 | Padrão cuia de alta/baixa                       | Baixo | Médio | Médio | Baixo | **Não**³    |
| 36 | Ondas de Elliott simplificadas (3/5)            | Médio | Alto  | Médio | Médio | 5 (opt)     |
| 37 | Eventos macroeconômicos (FOMC, CPI, Payroll…)    | Alto  | Médio | Médio | Alto  | 5           |
| 38 | Sentimento investidor (AAII Survey)             | Médio | Médio | Médio | Médio | 5           |
| 39 | Crypto Fear & Greed Index                       | Médio | Baixo | Baixo | Alto  | 5           |
| 40 | Notícias tokenizadas (Binance News…)            | Médio | Médio | Médio | Médio | 5           |
| 41 | Sentimento Twitter/X por palavra-chave          | Médio | Alto  | Alto  | Médio | 5 (cond)    |
| 42 | API REST multiusuário (FastAPI)                 | Médio | Alto  | Alto  | Médio | 6           |
| 43 | Autenticação por API Key                        | Médio | Médio | Médio | Médio | 6           |
| 44 | Documentação & guia no README                   | Alto  | Baixo | Baixo | Alto  | 1           |
| 45 | Gestão avançada de sinais (expiração/stop)      | Alto  | Baixo | Baixo | Alto  | 1           |
| 46 | Integração TradingView (webhook)                | Médio | Médio | Médio | Médio | 6           |
| 47 | Regime Detector (ADX, VIX, Fear & Greed)        | Alto  | Médio | Médio | Alto  | 5           |
| 48 | Fator de Risco Global (PCA em índices)          | Alto  | Alto  | Médio | Alto  | 5           |
| 49 | Estados de Volatilidade (VIX)                   | Alto  | Baixo | Baixo | Alto  | 5           |
| 50 | Correlação Dinâmica (BTC↔índices)               | Alto  | Médio | Médio | Alto  | 5           |
| 51 | Peso por Sessão (horário UTC)                   | Médio | Baixo | Baixo | Médio | 5           |
| 52 | Backtest Walk-Forward                           | Alto  | Alto  | Médio | Alto  | 3           |
| 53 | Monitoramento Dinâmico (throttle alerts)        | Alto  | Médio | Médio | Alto  | 5           |
| 54 | Dados On-Chain (fluxos, endereços, hash rate)   | Alto  | Médio | Médio | Alto  | 7           |
| 55 | Orquestração de Modelos ML (AutoML)             | Médio | Alto  | Médio | Médio | 7 (opt)     |
| 56 | Execução Automatizada de Ordens (APIs broker)   | Alto  | Alto  | Médio | Alto  | 7           |
| 57 | Governança & Compliance (auditoria, anomalias)  | Médio | Médio | Médio | Alto  | 7           |
| 58 | High-Availability (multi-zona, failover)        | Alto  | Alto  | Alto  | Alto  | 7           |

> **Legenda**  
> IR = Impacto no Resultado | CD = Complexidade de Desenvolvimento  
> CM = Custo de Manutenção | AN = Aderência ao Modelo de Negócio  
> ¹ Fases 1–3 priorizadas  
> ² Evitar loop infinito; usar agendador  
> ³ Subjetivo; priorizar cunha/bandeira
