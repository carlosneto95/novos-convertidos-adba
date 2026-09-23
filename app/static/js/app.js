// ==========================================================================
// app.js - JavaScript proprio do sistema.
//
// REGRA DE OURO (secao 7, item 3): o JavaScript NUNCA decide quem pode ver o
// que, e NUNCA e a validacao que vale. Tudo aqui e CONVENIENCIA para quem
// digita. Um robo pode enviar dados direto, pulando esta tela inteira - por
// isso a validacao de verdade esta em app/forms.py, no servidor.
// ==========================================================================

(function () {
  "use strict"; // modo estrito: o navegador reclama de erros silenciosos

  // ========================================================================
  // ENDERECOS - NUNCA escreva um caminho a mao neste arquivo
  // ========================================================================

  /**
   * Monta um endereco do sistema, respeitando onde ele mora no dominio.
   *
   * POR QUE ISTO EXISTE:
   * No servidor da igreja este sistema divide o endereco com outros dois e
   * vive sob /adba. No HTML isso se resolve sozinho, porque todo link passa
   * por url_for(). Mas este arquivo e ESTATICO: nao passa pelo Jinja e nao
   * tem como adivinhar o prefixo.
   *
   * Um fetch("/alma/123/ficha") escrito a mao sai SEM o /adba. No servidor
   * esse endereco cai no roteador da conta, que responde 200 com uma lista de
   * sistemas em texto puro - entao nem da erro: a tela simplesmente nao faz
   * nada. Foi exatamente esse o bug da ficha lateral.
   *
   * O prefixo vem do base.html, de request.script_root - o valor que o
   * servidor esta REALMENTE usando. Sem ele (pagina fora do base.html, ou
   * sistema na raiz do dominio), o caminho vale como esta.
   */
  function enderecoDoSistema(caminho) {
    return (window.ADBA_BASE || "") + caminho;
  }

  // ========================================================================
  // MASCARAS - vao formatando o texto enquanto a pessoa digita
  // ========================================================================

  /**
   * "16992805852" -> "(16) 99280-5852"
   * Monta o telefone por partes, conforme a quantidade de digitos ja digitada.
   */
  function formatarTelefone(valor) {
    var d = (valor || "").replace(/\D/g, "").slice(0, 11); // so numeros, no maximo 11
    if (d.length === 0) return "";
    if (d.length <= 2) return "(" + d;
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }

  /** "14015000" -> "14015-000" */
  function formatarCep(valor) {
    var d = (valor || "").replace(/\D/g, "").slice(0, 8);
    if (d.length <= 5) return d;
    return d.slice(0, 5) + "-" + d.slice(5);
  }

  // ========================================================================
  // O COMPONENTE DO FORMULARIO PUBLICO
  //
  // O Alpine.js chama esta funcao quando encontra x-data="formularioCadastro(18)"
  // no HTML. O objeto devolvido vira o "estado" daquele trecho da pagina.
  // ========================================================================
  window.formularioCadastro = function (maioridade) {
    return {
      // ------------------------------------------------------------------
      // NAVEGACAO ENTRE OS 4 BLOCOS
      // ------------------------------------------------------------------
      passo: 1,
      enviando: false,
      titulos: ["Quem cadastra", "Dados", "Conversão", "Questionário"],

      /** Largura da barra de progresso: passo 1 = 25%, passo 4 = 100%. */
      get progresso() {
        return (this.passo / 4) * 100;
      },

      proximo: function () {
        // Confere os campos do bloco atual antes de avancar.
        // De novo: isto e conveniencia. Quem valida de verdade e o servidor.
        if (!this.blocoAtualEstaOk()) return;
        if (this.passo < 4) {
          this.passo++;
          this.rolarParaTopo();
        }
      },

      voltar: function () {
        if (this.passo > 1) {
          this.passo--;
          this.rolarParaTopo();
        }
      },

      rolarParaTopo: function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
      },

      /**
       * Roda quando a pessoa aperta ENTER em qualquer campo do formulario.
       *
       * O PROBLEMA QUE ISSO CONSERTA:
       * O HTML tem uma regra antiga chamada "envio implicito": apertar Enter
       * em QUALQUER campo de uma linha envia o formulario inteiro. Num
       * formulario comum isso ajuda. No nosso, que tem 4 blocos, era um
       * desastre: a pessoa digitava o CEP no bloco 2, apertava Enter por
       * reflexo, e o cadastro inteiro era enviado pela metade.
       *
       * Agora o Enter faz o que a pessoa ESPERA em cada situacao:
       *   - caixa de texto grande  -> pula linha (comportamento normal)
       *   - campo do CEP           -> busca o endereco
       *   - blocos 1, 2 e 3        -> avanca, igual ao botao "Continuar"
       *   - bloco 4                -> ai sim, envia o cadastro
       */
      aoApertarEnter: function (evento) {
        var alvo = evento.target;

        // Numa caixa de texto grande, Enter e quebra de linha. Nao mexemos.
        if (alvo.tagName === "TEXTAREA") return;

        // Se o foco esta num botao, o Enter e um clique nele. Deixamos passar.
        if (alvo.tagName === "BUTTON") return;

        // No ultimo bloco, Enter enviar o cadastro e o esperado.
        if (this.passo === 4) return;

        // Em todo o resto, o envio implicito e BLOQUEADO aqui.
        evento.preventDefault();

        // No CEP, o Enter serve para buscar o endereco - e o gesto natural.
        if (alvo.id === "cep") {
          this.buscarCep();
          return;
        }

        // Nos demais campos, Enter avanca de bloco, como o botao "Continuar".
        this.proximo();
      },

      /**
       * Roda quando o formulario e ENVIADO (evento submit), nao quando o
       * botao e clicado.
       *
       * POR QUE ISSO IMPORTA - O BUG QUE ESTA FUNCAO CONSERTA:
       * A versao anterior fazia "enviando = true" no @click do botao, e o
       * botao tinha :disabled="enviando". So que um botao de envio que se
       * DESABILITA durante o proprio clique CANCELA o envio: o navegador
       * simplesmente ignora a acao de um botao desabilitado.
       * A tela ficava presa em "Enviando..." para sempre e o cadastro nunca
       * chegava ao servidor.
       *
       * Aqui o evento "submit" ja disparou quando esta funcao roda - o envio
       * esta a caminho e nada mais o cancela. Trocamos so o texto do botao.
       *
       * O envio duplo (dedo nervoso, clique duas vezes) e barrado pelo
       * preventDefault abaixo: a partir do segundo clique, o navegador
       * descarta a tentativa.
       */
      aoEnviar: function (evento) {
        if (this.enviando) {
          evento.preventDefault();   // ja esta indo; ignora o segundo clique
          return;
        }
        this.enviando = true;
      },

      /**
       * Procura campos obrigatorios vazios dentro do bloco visivel.
       * Se achar, destaca o primeiro e impede o avanco.
       */
      blocoAtualEstaOk: function () {
        var secao = this.$refs.formulario.querySelectorAll("section")[this.passo - 1];
        if (!secao) return true;

        var campos = secao.querySelectorAll("input, select, textarea");
        for (var i = 0; i < campos.length; i++) {
          var campo = campos[i];
          if (campo.type === "hidden" || campo.disabled) continue;
          // offsetParent nulo = campo escondido (ex: "qual igreja?" quando a
          // resposta foi "nao"). Campo escondido nao bloqueia o avanco.
          if (campo.offsetParent === null && campo.type !== "radio") continue;

          if (!campo.checkValidity()) {
            campo.reportValidity();   // mostra o balaozinho do navegador
            campo.focus();
            return false;
          }
        }
        return true;
      },

      // ------------------------------------------------------------------
      // MASCARAS LIGADAS AOS CAMPOS
      // ------------------------------------------------------------------
      mascaraTelefone: function (evento) {
        evento.target.value = formatarTelefone(evento.target.value);
      },

      mascaraCep: function (evento) {
        evento.target.value = formatarCep(evento.target.value);
        this.cep = evento.target.value;
      },

      // ------------------------------------------------------------------
      // BLOCO 1
      // ------------------------------------------------------------------
      cadastranteNome: "",
      cadastranteTelefone: "",

      // ------------------------------------------------------------------
      // BLOCO 2 - IDADE E MENOR DE IDADE
      // ------------------------------------------------------------------
      sexo: "",
      dataNascimento: "",

      /**
       * Idade em anos completos. Devolve null enquanto a data nao estiver
       * preenchida - e esse null que mantem o selo de idade escondido.
       */
      get idade() {
        if (!this.dataNascimento) return null;
        var nasc = new Date(this.dataNascimento + "T00:00:00");
        if (isNaN(nasc.getTime())) return null;

        var hoje = new Date();
        var anos = hoje.getFullYear() - nasc.getFullYear();

        // Mesma sutileza do app/tempo.py: se o aniversario deste ano ainda nao
        // chegou, desconta um ano.
        var mesDia = hoje.getMonth() * 100 + hoje.getDate();
        var mesDiaNasc = nasc.getMonth() * 100 + nasc.getDate();
        if (mesDia < mesDiaNasc) anos--;

        if (anos < 0 || anos > 130) return null;  // data digitada errada
        return anos;
      },

      get menorDeIdade() {
        return this.idade !== null && this.idade < maioridade;
      },

      // ------------------------------------------------------------------
      // BLOCO 2 - BUSCA DE ENDERECO PELO CEP (API ViaCEP)
      // ------------------------------------------------------------------
      cep: "",
      logradouro: "",
      bairro: "",
      cidade: "",
      uf: "",
      cepEstado: "",   // "" | "buscando" | "ok" | "nao_encontrado" | "erro"

      buscarCep: function () {
        var self = this;
        var digitos = (this.cep || "").replace(/\D/g, "");

        if (digitos.length !== 8) {
          this.cepEstado = "";
          return;
        }

        this.cepEstado = "buscando";

        // fetch pede o endereco a API publica dos Correios (ViaCEP).
        // Nenhum dado pessoal e enviado: so o CEP.
        fetch("https://viacep.com.br/ws/" + digitos + "/json/")
          .then(function (resposta) {
            if (!resposta.ok) throw new Error("falha na rede");
            return resposta.json();
          })
          .then(function (dados) {
            // O ViaCEP devolve {"erro": true} quando o CEP nao existe.
            if (dados.erro) {
              self.cepEstado = "nao_encontrado";
              return;
            }
            // Preenche os campos. A pessoa ainda pode corrigir tudo a mao.
            self.logradouro = dados.logradouro || "";
            self.bairro = dados.bairro || "";
            self.cidade = dados.localidade || "";
            self.uf = dados.uf || "";
            self.cepEstado = "ok";

            // Leva o cursor direto para o numero: e o unico que falta.
            self.$nextTick(function () {
              var numero = document.getElementById("numero");
              if (numero && !numero.value) numero.focus();
            });
          })
          .catch(function () {
            // Sem internet ou API fora do ar: a pessoa preenche a mao.
            self.cepEstado = "erro";
          });
      },

      // ------------------------------------------------------------------
      // BLOCO 3 - CONVERSAO E SUGESTAO DE DEPARTAMENTO
      // ------------------------------------------------------------------
      trabalho: "",

      /**
       * Sugere o departamento pela regra da secao 5.1:
       *   menor de 25   -> Geracao Life
       *   mulher 25+    -> Preciosas
       *   homem 25+     -> Irmaos
       *
       * ATENCAO: isto so DESTACA a opcao com um selo "sugerido".
       * NAO marca nada sozinho - a especificacao exige confirmacao manual.
       */
      get departamentoSugerido() {
        if (this.idade === null || !this.sexo) return "";
        if (this.idade < 25) return "geracao_life";
        if (this.sexo === "F") return "preciosas";
        if (this.sexo === "M") return "irmaos";
        return "";
      },

      get nomeDepartamentoSugerido() {
        var nomes = {
          geracao_life: "Geracao Life",
          preciosas: "Preciosas",
          irmaos: "Irmaos",
        };
        return nomes[this.departamentoSugerido] || "";
      },

      // ------------------------------------------------------------------
      // BLOCO 4 - PERGUNTAS COM CAMPO CONDICIONAL
      // ------------------------------------------------------------------
      temConhecido: "",
      jaFrequentou: "",

      // ------------------------------------------------------------------
      // INICIALIZACAO
      // ------------------------------------------------------------------
      init: function () {
        // Se o servidor devolveu a pagina com erros, levamos a pessoa direto
        // ao primeiro bloco que tem problema - em vez de deixa-la caçando.
        var primeiroErro = this.$refs.formulario.querySelector(".border-red-400, .border-red-300");
        if (primeiroErro) {
          var secoes = Array.prototype.slice.call(
            this.$refs.formulario.querySelectorAll("section")
          );
          for (var i = 0; i < secoes.length; i++) {
            if (secoes[i].contains(primeiroErro)) {
              this.passo = i + 1;
              break;
            }
          }
        }

        // Recupera os valores que o servidor devolveu, para que a idade, a
        // sugestao de departamento e os campos condicionais reapareçam certos.
        var pegar = function (id) {
          var el = document.getElementById(id);
          return el ? el.value : "";
        };
        var marcado = function (nome) {
          var el = document.querySelector('input[name="' + nome + '"]:checked');
          return el ? el.value : "";
        };

        this.dataNascimento = pegar("data_nascimento");
        this.cep = pegar("cep");
        this.sexo = marcado("sexo");
        this.trabalho = marcado("trabalho");
        this.temConhecido = marcado("tem_conhecido");
        this.jaFrequentou = marcado("ja_frequentou_igreja");
      },
    };
  };


  // ========================================================================
  // O PAINEL DE ALMAS - abre a ficha lateral ao clicar num nome
  // ========================================================================
  window.painelDeAlmas = function (fichaParaAbrir) {
    return {
      fichaAberta: false,
      carregando: false,
      erro: "",
      conteudo: "",
      almaAtual: null,

      /**
       * Busca a ficha no servidor e abre o painel lateral.
       *
       * POR QUE BUSCAR EM VEZ DE JA TER TUDO NA PAGINA?
       * Com 300 almas, trazer os contatos de todas encheria a pagina de
       * milhares de registros que ninguem vai olhar. Aqui buscamos so o que
       * foi pedido, na hora em que foi pedido.
       */
      abrirFicha: function (almaId) {
        var self = this;

        self.almaAtual = almaId;
        self.fichaAberta = true;
        self.carregando = true;
        self.erro = "";
        self.conteudo = "";

        // Trava a rolagem do fundo enquanto a ficha esta aberta, senao a
        // pagina de tras rola junto e a pessoa se perde.
        document.body.style.overflow = "hidden";

        fetch(enderecoDoSistema("/alma/" + almaId + "/ficha"), {
          // same-origin: o navegador manda o cookie de sessao junto.
          // Sem isso o servidor nos trataria como visitante deslogado.
          credentials: "same-origin",
          headers: { "X-Requested-With": "fetch" },
        })
          .then(function (resposta) {
            // O servidor responde 403 quando a alma NAO pertence a quem
            // pediu. E a trava de seguranca funcionando (secao 7, item 2).
            if (resposta.status === 403) {
              throw new Error("Voce nao tem permissao para ver esta ficha.");
            }
            if (resposta.status === 404) {
              throw new Error("Ficha nao encontrada.");
            }
            if (!resposta.ok) {
              throw new Error("Nao foi possivel carregar a ficha.");
            }
            return resposta.text();
          })
          .then(function (html) {
            self.conteudo = html;
            self.carregando = false;
          })
          .catch(function (e) {
            self.erro = e.message || "Nao foi possivel carregar a ficha.";
            self.carregando = false;
          });
      },

      fechar: function () {
        this.fichaAberta = false;
        this.conteudo = "";
        this.almaAtual = null;
        document.body.style.overflow = "";   // devolve a rolagem da pagina

        // Tira o "?ficha=..." do endereco. Sem isso, apertar F5 reabriria a
        // ficha que a pessoa acabou de fechar.
        if (window.location.search.indexOf("ficha=") !== -1) {
          var url = new URL(window.location.href);
          url.searchParams.delete("ficha");
          window.history.replaceState({}, "", url.toString());
        }
      },

      /**
       * Roda quando a pagina termina de montar.
       *
       * Depois de registrar um contato (ou qualquer outra acao), o servidor
       * manda de volta para /painel?ficha=<id>. E aqui que lemos esse
       * endereco e reabrimos a ficha - para a pessoa continuar de onde
       * parou, em vez de ter que procurar a alma de novo na lista.
       */
      init: function () {
        if (fichaParaAbrir) {
          this.abrirFicha(fichaParaAbrir);
        }
      },
    };
  };

  // ========================================================================
  // O COMPONENTE DA FICHA - abas e copia do relatorio do WhatsApp
  // ========================================================================
  window.fichaDaAlma = function () {
    return {
      aba: "dados",
      textoCopiado: false,

      /**
       * Copia o relatorio para a area de transferencia.
       *
       * Duas tentativas, nesta ordem:
       *   1. navigator.clipboard - o jeito moderno. So funciona em HTTPS ou
       *      em localhost; num endereco http comum o navegador bloqueia.
       *   2. document.execCommand - o jeito antigo. Esta marcado como
       *      obsoleto, mas funciona em qualquer lugar. E a nossa rede de
       *      seguranca para quando o item 1 nao estiver disponivel.
       *
       * Se os dois falharem, o texto continua visivel na caixa: a pessoa
       * seleciona e copia com Ctrl+C. Nunca fica sem saida.
       */
      copiarTexto: function (elemento) {
        var self = this;
        var texto = elemento.value;

        function avisarCopiado() {
          self.textoCopiado = true;
          setTimeout(function () { self.textoCopiado = false; }, 2500);
        }

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(texto).then(avisarCopiado).catch(function () {
            self.copiarPeloMetodoAntigo(elemento, avisarCopiado);
          });
        } else {
          self.copiarPeloMetodoAntigo(elemento, avisarCopiado);
        }
      },

      copiarPeloMetodoAntigo: function (elemento, aoCopiar) {
        try {
          elemento.removeAttribute("readonly");   // iPhone exige isto
          elemento.select();
          elemento.setSelectionRange(0, 99999);   // celular: seleciona tudo
          document.execCommand("copy");
          elemento.setAttribute("readonly", "readonly");
          aoCopiar();
        } catch (e) {
          // Sem jeito: a pessoa copia a mao. O texto esta na tela.
        }
      },
    };
  };

  // ========================================================================
  // CONFIRMACAO DE CARREGAMENTO
  // ========================================================================
  document.addEventListener("DOMContentLoaded", function () {
    console.log("[ADBA] app.js carregado - Etapa 5");
  });
})();
