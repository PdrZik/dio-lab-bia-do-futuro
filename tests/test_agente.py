"""Testa o orquestrador com um LLM falso: não depende de internet nem de chave de API."""
from agente import AVISO_NAO_VERIFICADO, MENSAGEM_ERRO_LLM, Agente


class LLMFalso:
    nome = "falso"

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def gerar(self, system, mensagens):
        self.chamadas.append(mensagens)
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_bloqueio_de_entrada_nao_chama_o_llm(base, data_ref):
    llm = LLMFalso([])
    r = Agente(base, llm, data_ref).responder("Qual a previsão do tempo?")
    assert r.bloqueado and llm.chamadas == []


def test_resposta_valida_passa_de_primeira(base, data_ref):
    llm = LLMFalso(["Em outubro você gastou R$ 570,00 com alimentação (fonte: transacoes.csv)."])
    r = Agente(base, llm, data_ref).responder("Quanto gastei com alimentação em outubro?")
    assert r.validacao_ok and r.tentativas == 1 and len(llm.chamadas) == 1


def test_alucinacao_dispara_reescrita_e_corrige(base, data_ref):
    llm = LLMFalso([
        "Você gastou R$ 999,00 com alimentação.",                    # inventado
        "Em outubro você gastou R$ 570,00 com alimentação.",         # corrigido
    ])
    r = Agente(base, llm, data_ref).responder("Quanto gastei com alimentação?")
    assert r.validacao_ok and r.tentativas == 2
    assert "570,00" in r.texto and AVISO_NAO_VERIFICADO not in r.texto
    assert "[Verificação automática]" in llm.chamadas[1][-1]["content"]   # feedback foi enviado


def test_alucinacao_persistente_recebe_aviso(base, data_ref):
    llm = LLMFalso(["Você gastou R$ 999,00.", "Você gastou R$ 888,00."])
    r = Agente(base, llm, data_ref).responder("Quanto gastei com alimentação?")
    assert not r.validacao_ok and r.texto.endswith(AVISO_NAO_VERIFICADO.strip()) or AVISO_NAO_VERIFICADO in r.texto


def test_valor_citado_pelo_usuario_e_permitido(base, data_ref):
    llm = LLMFalso(["Guardando R$ 1.234,00 por mês, sua reserva fecha em alguns meses."])
    r = Agente(base, llm, data_ref).responder("E se eu guardar R$ 1.234 por mês?")
    assert r.validacao_ok


def test_erro_do_provedor_nao_derruba_o_app(base, data_ref):
    llm = LLMFalso([RuntimeError("timeout")])
    r = Agente(base, llm, data_ref).responder("Quanto gastei?")
    assert r.texto == MENSAGEM_ERRO_LLM and "timeout" in r.erro


def test_historico_e_limitado_e_enviado(base, data_ref):
    llm = LLMFalso(["Ok, R$ 570,00."])
    hist = [{"role": "user", "content": f"p{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"r{i}"}
            for i in range(40)]
    Agente(base, llm, data_ref).responder("e em outubro?", hist)
    enviadas = llm.chamadas[0]
    assert len(enviadas) <= 13 and enviadas[-1]["content"] == "e em outubro?"


def test_todo_valor_das_respostas_offline_e_rastreavel(base, data_ref):
    agente = Agente(base, data_ref=data_ref, provider="offline")
    perguntas = ["Quanto gastei com alimentação em outubro?", "Minhas metas cabem no orçamento?",
                 "E se eu guardar R$ 1.000 por mês?", "Onde devo investir minha reserva?",
                 "Por que meus gastos com saúde subiram?", "Qual a diferença entre CDB e LCI?"]
    for p in perguntas:
        r = agente.responder(p)
        assert r.validacao_ok, (p, r.problemas)
