# Scanner Crypto ETH/BTC - GitHub Actions

Scanner automático de Bitcoin e Ethereum executado a cada 15 minutos via GitHub Actions.

## Características

- Execução automatizada 24/7
- Monitora BTC/USDT e ETH/USDT
- Análise técnica com múltiplos indicadores
- Alertas via Telegram
- Completamente gratuito
- Não requer servidor

## Configuração Necessária

1. Configure os GitHub Secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

2. Ative GitHub Actions no repositório

## Funcionamento

O scanner analisa os mercados a cada 15 minutos usando:
- EMAs (9, 21, 200)
- RSI
- MACD
- ADX
- Volume
- Supertrend

Detecta três tipos de setups:
- Setup Conservador (alta qualidade)
- Setup Momentum (oportunidades rápidas)
- Setup Reversão (contra-tendência)

## Próximos Passos

Após criar todos os arquivos, configure o bot do Telegram e os Secrets do GitHub para ativar os alertas.
