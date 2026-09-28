# Base de Conhecimento

## Dados Utilizados

| Arquivo | Formato | Utilização no Agente |
|---------|---------|---------------------|
| `historico_atendimento.csv` | CSV | Dar continuidade ao atendimento: o Fin retoma o último assunto tratado (ex.: dúvida sobre Tesouro Selic em 01/10/2025) |
| `perfil_investidor.json` | JSON | Personalizar tudo: renda, perfil, restrição de risco (`aceita_risco`), reserva atual e as duas metas com valor e prazo |
| `produtos_financeiros.json` | JSON | Catálogo de produtos. É a **única fonte** de taxas e condições que o agente pode citar; alimenta a compatibilidade produto × perfil |
| `transacoes.csv` | CSV | Resumo mensal, gastos por categoria, capacidade média de poupança e variação mês a mês |
| `glossario_financeiro.json` *(novo)* | JSON | Definições revisadas de conceitos (CDI, Selic, liquidez, IR em renda fixa etc.), recuperadas por palavra-chave para o Fin explicar sem inventar |

> [!TIP]
> Este projeto não usou datasets externos: o objetivo era demonstrar confiabilidade sobre os dados mockados do desafio.

---

## Adaptações nos Dados

1. **`transacoes.csv` foi estendido com agosto e setembro/2025** (as 10 linhas originais de outubro foram mantidas **sem alteração**). Com um único mês não é possível detectar tendências; com três meses o Fin calcula média de sobra e variação por categoria e por lançamento (ex.: a alta de Saúde em outubro vem inteiramente da Farmácia, de R$ 62,00 para R$ 89,00).
2. **`glossario_financeiro.json` foi criado** com 15 verbetes. Foi escrito deliberadamente **sem valores voláteis** (nada de "a Selic está em X%"), remetendo à fonte oficial, justamente para o agente não cair em números defasados.
3. **`perfil_investidor.json`, `produtos_financeiros.json` e `historico_atendimento.csv` não foram alterados** (apenas a quebra de linha do CSV foi normalizada para `\n`).
4. **Data de referência fixa (`DATA_REFERENCIA=2025-11-01`):** os dados vão até out/2025, então usar a data real de hoje faria o prazo da reserva (jun/2026) parecer vencido ou distante demais. Fixar a data torna os cálculos reproduzíveis.

### Premissas assumidas (e declaradas ao cliente pelo agente)

- **Patrimônio fora da reserva** (R$ 15.000,00 − R$ 10.000,00 = R$ 5.000,00) é considerado já destinado à meta do apartamento. Sem essa premissa, a meta parecia ter progresso zero.
- **Perfil "moderado" com `aceita_risco: false`:** os dados são ambíguos. Adotamos a leitura mais conservadora: a restrição de risco prevalece e apenas produtos de risco baixo são considerados compatíveis. O Fin conta isso ao cliente em um dos insights.

---

## Estratégia de Integração

### Como os dados são carregados?

Os arquivos são lidos e **validados** (colunas e chaves obrigatórias, erro claro se faltar algo) por `src/base_conhecimento.py` no início da sessão:

```python
from base_conhecimento import carregar

base = carregar()   # perfil, transacoes (DataFrame), historico, produtos, glossario
```

### Como os dados são usados no prompt?

Em vez de despejar os arquivos crus no prompt, o Fin usa uma abordagem em **duas etapas**:

1. **Ferramentas determinísticas** (`src/ferramentas.py`) transformam os dados em *fatos calculados*: resumo mensal, gastos por categoria, variação por lançamento, progresso e aporte mensal necessário por meta, viabilidade conjunta, compatibilidade de produtos e insights.
2. **O montador de contexto** (`src/contexto.py`) escreve esses fatos em texto estruturado e, **a cada mensagem**, acrescenta partes dinâmicas: uma *simulação* (se o cliente propôs um valor mensal) e *verbetes do glossário* (se citou um conceito). Tudo entra no system prompt.

Isso dá duas vantagens: o modelo não precisa fazer contas (menos erro) e o validador consegue conferir cada número da resposta contra o contexto.

---

## Exemplo de Contexto Montado

Gerado pelo próprio código para a mensagem *"O que é CDI? E se eu guardar R$ 2.000 por mês?"* (trecho):

```text
=== CLIENTE (fonte: perfil_investidor.json) ===
- Nome: João Silva, 32 anos, Analista de Sistemas
- Renda mensal: R$ 5.000,00
- Perfil declarado: moderado | Aceita risco: não
- Objetivo principal: Construir reserva de emergência
- Patrimônio total: R$ 15.000,00 | Reserva atual: R$ 10.000,00

=== RESUMO MENSAL (fonte: transacoes.csv) ===
- ago/2025: entradas R$ 5.000,00 | saídas R$ 2.374,90 | saldo R$ 2.625,10 | taxa de poupança 52,5%
- set/2025: entradas R$ 5.000,00 | saídas R$ 2.708,90 | saldo R$ 2.291,10 | taxa de poupança 45,8%
- out/2025: entradas R$ 5.000,00 | saídas R$ 2.488,90 | saldo R$ 2.511,10 | taxa de poupança 50,2%

=== METAS (calculado a partir de perfil_investidor.json) ===
- Completar reserva de emergência: alvo R$ 15.000,00 | atual R$ 10.000,00 | falta R$ 5.000,00 | progresso 66,7% | prazo jun/2026 | 8 meses de aporte | aporte mensal necessário R$ 625,00
- Entrada do apartamento: alvo R$ 50.000,00 | atual R$ 5.000,00 | falta R$ 45.000,00 | progresso 10,0% | prazo dez/2027 | 26 meses de aporte | aporte mensal necessário R$ 1.730,77
  (premissa: considera os R$ 5.000,00 do patrimônio que estão fora da reserva como já destinados a esta meta)
- Viabilidade: aporte exigido no período mais exigente R$ 2.355,77 | capacidade média R$ 2.475,77 | folga mensal R$ 120,00 | as metas cabem no orçamento

COMPATIBILIDADE COM O PERFIL (risco máximo aceito: baixo):
- Compatíveis para reserva/liquidez: Tesouro Selic, CDB Liquidez Diária
- Compatíveis para metas de prazo maior: LCI/LCA
- INCOMPATÍVEL: Fundo Multimercado (risco médio acima do máximo aceito pelo perfil, que é baixo)
- INCOMPATÍVEL: Fundo de Ações (risco alto acima do máximo aceito pelo perfil, que é baixo)

=== SIMULAÇÃO SOLICITADA: guardar R$ 2.000,00 por mês (reserva primeiro, depois as demais metas) ===
- Completar reserva de emergência: concluída em jan/2026 (3 meses), prazo jun/2026 -> DENTRO do prazo
- Entrada do apartamento: concluída em nov/2027 (25 meses), prazo dez/2027 -> DENTRO do prazo

=== GLOSSÁRIO (use estas definições para explicar conceitos) ===
- CDI: Taxa de referência usada nos empréstimos entre bancos, que acompanha de perto a Selic. Quando um investimento rende '102% do CDI', significa que ele paga 102% dessa taxa de referência. O valor do CDI muda com o tempo, então consulte fontes oficiais para o número vigente.
```
