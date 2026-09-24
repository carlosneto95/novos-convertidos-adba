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
  // VALIDACAO NA TELA - o espelho das regras do servidor
  //
  // O BUG QUE ISTO CONSERTA:
  // Antes, a tela so conferia se os campos obrigatorios estavam PREENCHIDOS.
  // Um "Maria" sem sobrenome ou um telefone "1699" passavam pelos blocos 1,
  // 2 e 3 sem reclamacao. So no fim, ao clicar em "Concluir", o servidor
  // recusava - e a pessoa era jogada de volta a um bloco anterior sem
  // entender por que.
  //
  // Agora cada bloco confere as MESMAS regras do app/forms.py e do
  // app/validacao.py ANTES de deixar avancar. O erro aparece na hora, no
  // campo certo, na tela em que a pessoa esta.
  //
  // O servidor continua conferindo tudo de novo (regra de ouro, no topo
  // deste arquivo). Se um dia as regras la mudarem, mude aqui tambem - senao
  // o bug de "voltar para tras" reaparece.
  // ========================================================================

  /** "  maria   silva " -> "maria silva" (igual ao normalizar_nome do Python) */
  function normalizarNome(texto) {
    return (texto || "").split(/\s+/).filter(Boolean).join(" ");
  }

  /** Mesma regra do NomeValido: minimo de letras, pelo menos uma letra, sobrenome. */
  function erroDeNome(valor, minimo, exigirSobrenome) {
    var nome = normalizarNome(valor);
    if (!nome) return "Este campo é obrigatório.";
    if (nome.length < minimo) return "Digite pelo menos " + minimo + " caracteres.";
    if (!/[A-Za-zÀ-ÖØ-öø-ÿ]/.test(nome)) return "Digite um nome válido.";
    if (exigirSobrenome && nome.split(" ").length < 2) {
      return "Digite o nome completo (nome e sobrenome).";
    }
    return "";
  }

  /** Mesma regra do TelefoneValido: 10 ou 11 digitos, DDD real, celular com 9. */
  function erroDeTelefone(valor) {
    var d = (valor || "").replace(/\D/g, "");
    var padrao = "Telefone inválido. Digite com DDD, ex: (16) 99280-5852.";
    if (!d) return "Informe o telefone.";
    if (d.length !== 10 && d.length !== 11) return padrao;
    if (/^(\d)\1+$/.test(d)) return "Este telefone não parece real.";   // todos os digitos iguais
    if (d[0] === "0") return padrao;
    if (d.length === 11 && d[2] !== "9") {
      return "Celular com 11 dígitos deve começar com 9 depois do DDD.";
    }
    return "";
  }

  /** Hoje, no formato AAAA-MM-DD (o mesmo do campo de data), no fuso do celular. */
  function hojeISO() {
    var h = new Date();
    var mes = String(h.getMonth() + 1).padStart(2, "0");
    var dia = String(h.getDate()).padStart(2, "0");
    return h.getFullYear() + "-" + mes + "-" + dia;
  }

  /** Mesma regra do DataNascimentoValida: nao no futuro, nao mais de 120 anos. */
  function erroDeNascimento(valor) {
    if (!valor) return "Informe a data de nascimento.";
    if (valor > hojeISO()) return "A data de nascimento não pode estar no futuro.";
    var anos = new Date().getFullYear() - parseInt(valor.slice(0, 4), 10);
    if (anos > 120) return "Data muito antiga. Confira o ano digitado.";
    return "";
  }

  /** Mesma regra do DataConversaoValida: nao no futuro, no maximo 10 anos atras. */
  function erroDeConversao(valor) {
    if (!valor) return "Informe a data.";
    if (valor > hojeISO()) return "A data da conversão não pode estar no futuro.";
    var dias = (new Date(hojeISO()) - new Date(valor)) / 86400000;
    if (dias > 3650) return "Data muito antiga. Confira o ano digitado.";
    return "";
  }

  /**
   * AS REGRAS, campo por campo (o nome e o "name" do campo no HTML).
   * Cada regra recebe o valor e devolve a mensagem de erro, ou "" se estiver ok.
   * Campo que nao aparece aqui e opcional e nao e conferido.
   *
   * Os campos condicionais ("Qual?", responsavel legal...) so sao conferidos
   * quando estao VISIVEIS - ver validarBloco().
   */
  var REGRAS = {
    cadastrante_nome:            function (v) { return erroDeNome(v, 3, false); },
    cadastrante_telefone:        erroDeTelefone,
    nome_completo:               function (v) { return erroDeNome(v, 3, true); },
    telefone:                    erroDeTelefone,
    sexo:                        function (v) { return v ? "" : "Selecione o sexo."; },
    data_nascimento:             erroDeNascimento,
    cep: function (v) {
      var d = (v || "").replace(/\D/g, "");
      return d && d.length !== 8 ? "CEP inválido. Deve ter 8 dígitos, ex: 14015-000." : "";
    },
    trabalho:                    function (v) { return v ? "" : "Selecione o trabalho."; },
    trabalho_outro:              function (v) { return (v || "").trim() ? "" : "Descreva qual foi o trabalho."; },
    data_conversao:              erroDeConversao,
    departamento:                function (v) { return v ? "" : "Confirme o departamento."; },
    conhecido_nome:              function (v) { return (v || "").trim() ? "" : "Informe quem ela conhece."; },
    qual_igreja:                 function (v) { return (v || "").trim() ? "" : "Informe qual igreja."; },
    consentimento:               function (v) { return v ? "" : "É preciso autorizar o uso dos dados para concluir."; },
    responsavel_legal_nome:      function (v) { return (v || "").trim() ? "" : "Obrigatório para menores de idade."; },
    responsavel_legal_telefone:  erroDeTelefone,
    consentimento_responsavel:   function (v) { return v ? "" : "O responsável legal precisa autorizar."; },
  };

  /** O valor de um campo: texto, opcao marcada (radio) ou marcado/desmarcado. */
  function valorDoCampo(formulario, campo) {
    if (campo.type === "radio") {
      var marcado = formulario.querySelector('input[name="' + campo.name + '"]:checked');
      return marcado ? marcado.value : "";
    }
    if (campo.type === "checkbox") return campo.checked;
    return campo.value;
  }

  /**
   * Um campo esta visivel? Campo dentro de algo escondido (display:none) nao
   * ocupa espaco na tela - getClientRects() volta vazio. E assim que sabemos
   * que "Qual igreja?" esta escondido porque a resposta foi "Nao".
   */
  function estaVisivel(campo) {
    return campo.getClientRects().length > 0;
  }

  /**
   * A "caixa" do campo: onde a mensagem de erro vai aparecer.
   *   - opcoes (radio)   -> o grupo inteiro (fieldset)
   *   - caixa de marcar  -> o quadro em volta do texto da autorizacao
   *   - demais campos    -> o bloco rotulo + campo
   */
  function caixaDoCampo(campo) {
    if (campo.type === "radio") return campo.closest("fieldset");
    if (campo.type === "checkbox") return campo.closest("label").parentElement;
    return campo.parentElement;
  }

  /** Mostra a mensagem vermelha embaixo do campo e pinta a borda. */
  function mostrarErro(campo, mensagem) {
    var caixa = caixaDoCampo(campo);
    if (!caixa) return;
    tirarErro(campo);
    caixa.classList.add("campo-com-erro");

    var p = document.createElement("p");
    p.className = "erro-cliente";
    p.setAttribute("role", "alert");          // leitor de tela anuncia o erro
    var icone = document.createElement("span");
    icone.textContent = "⚠";
    var texto = document.createElement("span");
    texto.textContent = mensagem;             // textContent: nunca vira HTML
    p.appendChild(icone);
    p.appendChild(texto);
    caixa.appendChild(p);
  }

  /** Apaga a mensagem (a nossa e a que veio do servidor) e a borda vermelha. */
  function tirarErro(campo) {
    var caixa = caixaDoCampo(campo);
    if (!caixa) return;
    caixa.classList.remove("campo-com-erro");
    caixa.querySelectorAll(".erro-cliente, [data-erro-servidor]").forEach(function (p) {
      p.remove();
    });
    // A borda vermelha que o SERVIDOR desenhou fica nas classes do proprio
    // campo. Marcamos como "corrigido" e o CSS devolve a borda normal.
    caixa.querySelectorAll("input, select, textarea").forEach(function (c) {
      c.classList.add("erro-corrigido");
    });
  }

  // ========================================================================
  // O COMPONENTE DO FORMULARIO PUBLICO
  //
  // O Alpine.js chama esta funcao quando encontra
  //     x-data='formularioCadastro(18, {...})'
  // no HTML. O objeto devolvido vira o "estado" daquele trecho da pagina.
  //
  // "inicial" traz o que a pessoa ja tinha digitado, quando o servidor
  // devolve a pagina com algum erro (ver o topo do cadastro.html).
  // ========================================================================
  window.formularioCadastro = function (maioridade, inicial) {
    inicial = inicial || {};

    return {
      // ------------------------------------------------------------------
      // NAVEGACAO: passo 0 = boas-vindas, passos 1 a 4 = os blocos
      // ------------------------------------------------------------------
      // Se o servidor devolveu a pagina com erro, ou se a pessoa veio do
      // "Cadastrar outra pessoa", ela ja passou pela tela de boas-vindas:
      // comecamos direto no formulario.
      passo: inicial.comErro || inicial.direto ? 1 : 0,
      enviando: false,
      titulos: ["Você", "Dados", "Conversão", "Perguntas"],

      /** Botao "Iniciar cadastro" da tela de boas-vindas. */
      iniciar: function () {
        this.irPara(1, true);
      },

      proximo: function () {
        // Confere os campos do bloco atual antes de avancar.
        // De novo: isto e conveniencia. Quem valida de verdade e o servidor.
        if (!this.validarBloco(this.passo)) return;
        if (this.passo < 4) this.irPara(this.passo + 1, true);
      },

      /**
       * Botao "Voltar" da tela.
       * Se o bloco atual foi aberto pelo "Continuar", existe uma entrada no
       * historico do navegador para ele: voltamos por la, e o "popstate"
       * (la no init) faz o resto. Assim o botao da tela e o botao/gesto de
       * voltar do celular fazem EXATAMENTE a mesma coisa.
       */
      voltar: function () {
        var estado = window.history.state;
        if (estado && estado.adbaPasso === this.passo && estado.adbaPasso > this.passoDeEntrada) {
          window.history.back();
        } else if (this.passo > 0) {
          this.irPara(this.passo - 1, false);
        }
      },

      /**
       * Troca de bloco. "empurrar" = criar uma entrada no historico do
       * navegador, para que o botao voltar do celular volte UM BLOCO.
       *
       * O BUG QUE ISTO CONSERTA: no celular, o gesto de voltar saia do
       * formulario inteiro (os blocos nao eram paginas de verdade) e tudo
       * que a pessoa tinha digitado se perdia.
       */
      irPara: function (novoPasso, empurrar) {
        this.passo = novoPasso;
        try {
          if (empurrar) {
            window.history.pushState({ adbaPasso: novoPasso }, "");
          } else {
            window.history.replaceState({ adbaPasso: novoPasso }, "");
          }
        } catch (e) { /* navegador sem historico: segue sem ele */ }
        this.rolarParaTopo();
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
       * Aqui o evento "submit" ja disparou quando esta funcao roda. Ou o
       * cancelamos de proposito (preventDefault), ou ele segue.
       */
      aoEnviar: function (evento) {
        // Envio duplo (dedo nervoso, clique duas vezes): o segundo e ignorado.
        if (this.enviando) {
          evento.preventDefault();
          return;
        }

        // Ultima conferencia antes de enviar: o bloco 4 E os anteriores.
        // Os anteriores ja foram conferidos ao avancar, mas a pessoa pode
        // ter voltado e apagado algo. Se achar problema, leva a pessoa ao
        // bloco certo AGORA - em vez de o servidor fazer isso depois.
        for (var bloco = 1; bloco <= 4; bloco++) {
          if (!this.validarBloco(bloco)) {
            evento.preventDefault();
            if (bloco !== this.passo) {
              this.irPara(bloco, false);
              var self = this;
              // O bloco precisa estar visivel para conferir de novo e
              // posicionar o cursor no campo com problema.
              this.$nextTick(function () { self.validarBloco(bloco); });
            }
            return;
          }
        }

        this.enviando = true;
      },

      /**
       * Confere os campos de UM bloco. Mostra a mensagem embaixo de cada
       * campo com problema e poe o cursor no primeiro deles.
       * Devolve true se esta tudo certo.
       *
       * Campo ESCONDIDO nao e conferido: "Qual igreja?" so e obrigatorio se
       * a resposta foi "Sim", e so fica visivel nesse caso. Por isso um bloco
       * que nao esta na tela e mostrado por um instante durante a conferencia.
       */
      validarBloco: function (numero) {
        var formulario = this.$refs.formulario;
        var secao = formulario.querySelectorAll("section")[numero - 1];
        if (!secao) return true;

        // Um bloco escondido (display:none) esconde tambem os campos que
        // DEVERIAM estar visiveis. Mostramos o bloco um instante, conferimos
        // e escondemos de novo - rapido demais para aparecer na tela.
        var estavaEscondido = secao.style.display === "none";
        if (estavaEscondido) secao.style.display = "";

        var primeiroComErro = null;
        var jaVistos = {};                  // radios: confere o grupo uma vez so

        secao.querySelectorAll("input, select, textarea").forEach(function (campo) {
          var regra = REGRAS[campo.name];
          if (!regra || jaVistos[campo.name]) return;
          jaVistos[campo.name] = true;

          // Radio fica "invisivel" (sr-only) de proposito; quem mostra se o
          // grupo esta na tela e o rotulo ao lado dele.
          var referencia = campo.type === "radio" ? caixaDoCampo(campo) : campo;
          if (!estaVisivel(referencia)) {
            tirarErro(campo);
            return;
          }

          var mensagem = regra(valorDoCampo(formulario, campo));
          if (mensagem) {
            mostrarErro(campo, mensagem);
            if (!primeiroComErro) primeiroComErro = campo;
          } else {
            tirarErro(campo);
          }
        });

        if (estavaEscondido) secao.style.display = "none";

        if (primeiroComErro && !estavaEscondido) {
          // Leva a pessoa ate o primeiro problema. preventScroll + scroll
          // manual: assim o campo nao fica escondido atras do cabecalho fixo.
          var caixa = caixaDoCampo(primeiroComErro);
          primeiroComErro.focus({ preventScroll: true });
          var y = caixa.getBoundingClientRect().top + window.scrollY - 140;
          window.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
        }
        return !primeiroComErro;
      },

      /**
       * Quando a pessoa mexe num campo que estava com erro, a mensagem some
       * na hora - sinal de que ela esta no caminho certo. A conferencia
       * completa volta a acontecer no "Continuar".
       */
      limparErroDoCampo: function (campo) {
        if (!campo || !campo.name) return;
        var caixa = caixaDoCampo(campo);
        if (caixa && caixa.classList.contains("campo-com-erro")) tirarErro(campo);
        else if (caixa && caixa.querySelector("[data-erro-servidor]")) tirarErro(campo);
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
      cadastranteNome: inicial.cadastranteNome || "",
      cadastranteTelefone: inicial.cadastranteTelefone || "",

      // ------------------------------------------------------------------
      // BLOCO 2 - IDADE E MENOR DE IDADE
      // ------------------------------------------------------------------
      sexo: inicial.sexo || "",
      dataNascimento: inicial.dataNascimento || "",

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
      cep: inicial.cep || "",
      logradouro: inicial.logradouro || "",
      bairro: inicial.bairro || "",
      cidade: inicial.cidade || "",
      uf: inicial.uf || "",
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
      trabalho: inicial.trabalho || "",

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
          geracao_life: "Geração Life",
          preciosas: "Preciosas",
          irmaos: "Irmãos",
        };
        return nomes[this.departamentoSugerido] || "";
      },

      // ------------------------------------------------------------------
      // BLOCO 4 - PERGUNTAS COM CAMPO CONDICIONAL
      // ------------------------------------------------------------------
      temConhecido: inicial.temConhecido || "",
      jaFrequentou: inicial.jaFrequentou || "",

      // ------------------------------------------------------------------
      // INICIALIZACAO
      // ------------------------------------------------------------------
      init: function () {
        var self = this;

        // Se o servidor devolveu a pagina com erros, levamos a pessoa direto
        // ao primeiro bloco que tem problema - em vez de deixa-la caçando.
        var primeiroErro = this.$refs.formulario.querySelector("[data-erro-servidor]");
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

        // O passo em que a pagina ABRIU. O "Voltar" usa o historico do
        // navegador so para os passos que vieram DEPOIS deste.
        this.passoDeEntrada = this.passo;
        try {
          window.history.replaceState({ adbaPasso: this.passo }, "");
        } catch (e) { /* sem historico: segue sem ele */ }

        // O botao/gesto de voltar do celular: em vez de sair da pagina,
        // volta para o bloco anterior (o endereco nao muda, so o bloco).
        window.addEventListener("popstate", function (evento) {
          var estado = evento.state;
          if (estado && typeof estado.adbaPasso === "number") {
            self.passo = estado.adbaPasso;
            self.rolarParaTopo();
          }
        });
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
