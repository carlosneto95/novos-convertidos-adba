# Colocar o sistema no ar — PythonAnywhere

> Guia passo a passo. Siga na ordem; cada passo depende do anterior.
> Reserve **40 minutos** na primeira vez.

---

## ⚠️ LEIA ISTO ANTES DE QUALQUER COISA

**O endereço `carlosneto.pythonanywhere.com` não é só deste sistema.** Ele já
servia dois outros, que estão no ar e em uso:

| Endereço | Sistema |
|---|---|
| `/demandas/` | Controle de Demandas |
| `/fechamento/` | Fechamento Contas a Pagar |
| `/adba/` | **este sistema** |

No PythonAnywhere, **uma conta tem um web app por domínio**. Os três rodam no
mesmo processo Python, montados por prefixo de caminho pelo arquivo WSGI.

Disso saem três regras que **não** são opcionais:

1. **Nunca apague nem reescreva o arquivo WSGI.** Ele contém as senhas dos
   outros dois sistemas e monta os três. Reescrevê-lo derruba tudo e troca
   segredos que estão em uso. Use o `anexar-wsgi.sh`, que **só acrescenta** no
   fim do arquivo (Passo 7).
2. **Nunca troque o Virtualenv por outro** sem antes conferir que os três
   sistemas têm suas bibliotecas nele. Um só virtualenv serve aos três.
3. **Nunca mapeie estáticos na URL `/static/`.** Use `/adba/static/`. A URL
   genérica pegaria requisição dos outros sistemas.

---

## Antes de começar

| O que você precisa | Onde conseguir |
|---|---|
| Conta no PythonAnywhere | [pythonanywhere.com](https://www.pythonanywhere.com) — o plano grátis funciona |
| O projeto num repositório Git | GitHub, GitLab — ou envie os arquivos pelo painel |

> ⚠️ **O plano grátis não permite tarefas agendadas com frequência nem domínio próprio.** Para o backup automático diário e um endereço como `sistema.suaigreja.com.br`, é preciso o plano pago (US$ 5/mês).

---

## PASSO 0 — Antes de subir: as três travas de produção

Estas três coisas **precisam** ser feitas. Sem elas o sistema sobe inseguro.

### 0.1 — Gerar segredos NOVOS

Os segredos do seu computador **não podem** ir para o servidor. Se um dia vazarem do seu PC, o sistema no ar cai junto.

No **console do PythonAnywhere** (depois do Passo 2), gere novos:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('CADASTRO_TOKEN=' + secrets.token_urlsafe(24))"
```

Guarde os dois — vão para o `.env` do servidor no Passo 4.

### 0.2 — Ligar de volta a troca de senha obrigatória

Durante os testes eu **desliguei** a exigência de trocar a senha no primeiro acesso. No servidor ela precisa estar ligada — a senha inicial de cada responsável vai passar por WhatsApp até chegar na pessoa.

Depois de criar o admin no servidor (Passo 6), rode:

```bash
flask criar-admin --redefinir-senha
```

Isso sorteia a senha do `.env` e **liga a exigência de troca** de novo.

### 0.3 — Conferir que o `.env` não subiu

```bash
git check-ignore -v .env
```

Precisa responder algo. Se não responder nada, **pare** — o arquivo de segredos está indo para o Git.

> Este erro existiu de verdade neste projeto: um comentário à direita da linha fazia o `.gitignore` não valer. Já está corrigido, mas confira.

---

## PASSO 1 — O app web

**O web app já existe** — é o que serve `/demandas` e `/fechamento`.
**Não clique em "Add a new web app".** No PythonAnywhere, um web app novo
exigiria um domínio próprio; e o que precisamos é entrar no que já está ali.

Confira apenas, na aba **Web**:

| Campo | Valor esperado |
|---|---|
| Python version | 3.13 |
| Virtualenv | `/home/carlosneto/novos-convertidos/venv` |
| Force HTTPS | Enabled |

> Se for uma conta **nova**, sem nada no ar: aí sim use **Add a new web app**
> → **Manual configuration** → **Python 3.13** *(não escolha "Flask": o
> instalador dele conflita com a nossa estrutura)*. Nesse caso o sistema pode
> morar na raiz, e você deixa `URL_PREFIXO` vazio no `.env`.

---

## PASSO 2 — Enviar o código

Abra um **Bash console** (aba *Consoles*) e rode:

```bash
cd ~
git clone https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git novos-convertidos
cd novos-convertidos
```

> Sem Git? Use a aba **Files** para enviar um `.zip` e depois `unzip arquivo.zip`.

---

## PASSO 3 — Criar o ambiente e instalar

```bash
cd ~/novos-convertidos
python3.13 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Demora uns 3 minutos. Confira no fim:

```bash
python -c "import flask, sqlalchemy, openpyxl; print('tudo instalado')"
```

---

## PASSO 4 — Criar o arquivo de segredos

```bash
cd ~/novos-convertidos
cp .env.example .env
nano .env
```

Preencha assim (use os valores gerados no Passo 0.1):

```
APP_ENV=production

SECRET_KEY=<cole o valor gerado>
CADASTRO_TOKEN=<cole o valor gerado>

DATABASE_URL=

ADMIN_NOME=Seu Nome Completo
ADMIN_LOGIN=seulogin
ADMIN_SENHA_INICIAL=<uma senha temporária de 12+ caracteres>

LIMITE_CADASTRO_PUBLICO=
LIMITE_LOGIN=

URL_PREFIXO=/adba
```

Para salvar no `nano`: `Ctrl+O`, `Enter`, `Ctrl+X`.

> **`URL_PREFIXO` precisa ser idêntico ao prefixo do arquivo WSGI** (`/adba`).
> Ele define o *path* do cookie de sessão. Errado, o login falha **em
> silêncio**: o navegador guarda o cookie e simplesmente nunca o devolve — a
> tela de login reaparece sem mensagem de erro nenhuma. O `anexar-wsgi.sh`
> (Passo 7.1) grava este valor sozinho; a linha aqui é só para você saber o que
> ela faz. Sistema na raiz do domínio → deixe vazio.

> **`APP_ENV=production` é o interruptor mais importante deste arquivo.** Ele desliga o modo de depuração (que mostraria o código na tela em caso de erro) e exige HTTPS no cookie de sessão.

Proteja o arquivo:

```bash
chmod 600 .env
```

---

## PASSO 5 — Criar o banco

```bash
cd ~/novos-convertidos
source venv/bin/activate
export FLASK_APP=run.py
flask db upgrade
```

Deve aparecer `Running upgrade ... -> ...`. O arquivo nasce em `instance/adba.db`.

---

## PASSO 6 — Criar o administrador e a agenda

```bash
flask criar-admin
flask seed-eventos
```

Anote o login. **Você vai trocar a senha no primeiro acesso** — é obrigatório.

---

## PASSO 7 — Ligar o sistema no servidor web

> ⚠️ **Este é o passo onde dá para derrubar os outros dois sistemas.** Leia até
> o fim antes de fazer.

### 7.1 — Deixar o virtualenv servir os três sistemas

Um web app tem **um** virtualenv — e aqui ele serve três sistemas. Então esse
virtualenv precisa ter as bibliotecas dos três.

```bash
bash ~/novos-convertidos/preparar-venv.sh
```

> ⚠️ **O Reload é que revela esse problema, e aí já é tarde.** O PythonAnywhere
> só passa a usar o virtualenv configurado quando o app é recarregado. Até lá o
> processo no ar continua com o ambiente antigo e tudo parece bem — mesmo que o
> virtualenv novo não tenha as bibliotecas dos outros sistemas. Foi exatamente o
> caso aqui: o Fechamento usa `requests`, que o venv deste projeto não tinha.

O script carrega o arquivo WSGI de verdade, com o Python do venv. Se faltar
alguma coisa, liga o `include-system-site-packages` (o venv passa a enxergar os
pacotes do sistema, **sem** perder prioridade para as nossas versões) e testa de
novo. Se ainda assim faltar, **desfaz a mudança**, diz qual biblioteca falta e
avisa para não recarregar.

Só siga para o 7.2 depois de ver **PODE RECARREGAR**.

### 7.2 — Anexar o nosso bloco ao arquivo WSGI

O arquivo WSGI da conta monta os três sistemas e **guarda as senhas dos outros
dois dentro dele**. Então não mexemos nele à mão: um script cuida disso.

```bash
bash ~/novos-convertidos/anexar-wsgi.sh
```

O que ele faz, nesta ordem:

1. copia o arquivo atual para `*.backup-DATA` — sempre dá para voltar
2. **acrescenta** o nosso bloco no fim (nenhuma linha existente é tocada)
3. confere que o arquivo montado ainda compila
4. **se a sintaxe quebrar, restaura a cópia e para** — nada vai para o ar
5. grava `URL_PREFIXO=/adba` no `.env`

Pode rodar de novo quantas vezes quiser: se o bloco já estiver lá, ele avisa e
sai sem duplicar.

> **Por que anexar funciona:** o Python usa a **última** atribuição de
> `application`. Nosso bloco lê os apps que o arquivo original já criou,
> acrescenta o nosso e remonta os três. E o nosso `create_app()` está dentro de
> um `try/except`: se este sistema não subir, os outros dois **continuam no ar**.

### 7.3 — Arquivos estáticos

Na seção **Static files**, adicione:

| URL | Directory |
|---|---|
| `/adba/static/` | `/home/carlosneto/novos-convertidos/app/static/` |

> ⚠️ **A URL precisa ser `/adba/static/`, não `/static/`.** O mapeamento acontece
> no servidor, **antes** do Python — uma URL genérica interceptaria requisição
> dos outros dois sistemas. Eles servem os próprios arquivos em
> `/demandas/static_web/` e `/fechamento/static_web/`; com o prefixo, ninguém
> pisa no pé de ninguém.

### 7.4 — Force HTTPS

Ainda na aba **Web**, confira que **Force HTTPS** está **Enabled**.

> Sem isso, alguém na mesma rede Wi-Fi poderia ler a senha digitada no login.
> Com `APP_ENV=production`, o cookie de sessão **só** viaja em HTTPS — então sem
> esta opção o login simplesmente não funcionaria.

### 7.5 — Recarregar

Botão verde **Reload**.

### 7.6 — Se algo der errado: como voltar atrás

Os outros dois sistemas estão em uso. Se depois do Reload algum deles falhar:

```bash
ls -la /var/www/*.backup-*
cp /var/www/carlosneto_pythonanywhere_com_wsgi.py.backup-DATA    /var/www/carlosneto_pythonanywhere_com_wsgi.py
```

Depois **Reload** de novo. Isso devolve o arquivo ao estado anterior e os dois
sistemas voltam. O motivo da falha fica no **Error log** da aba Web.

---

## PASSO 8 — Conferir que subiu certo

### Primeiro: os outros dois sistemas continuam de pé?

**Confira isto antes do nosso.** Se algum quebrou, volte atrás pelo Passo 7.6.

- [ ] `https://carlosneto.pythonanywhere.com/demandas/` abre a tela de entrar
- [ ] `https://carlosneto.pythonanywhere.com/fechamento/` abre a tela de entrar
- [ ] `https://carlosneto.pythonanywhere.com/` lista os **três** sistemas

### Depois: o nosso

Abra `https://carlosneto.pythonanywhere.com/adba/`

- [ ] A tela de login aparece, com o logotipo da ADBA
- [ ] O cadeado do HTTPS aparece na barra do navegador
- [ ] Você entra com o login criado no Passo 6
- [ ] O sistema **exige** que você crie uma senha nova
- [ ] O painel abre
- [ ] O formulário público abre em `/adba/cadastro/SEU-TOKEN`
- [ ] Um token errado devolve "Página não encontrada"

### E, já logado, o teste que pega o cookie errado

- [ ] Depois de logar, **recarregue** a página (F5). Se cair de volta na tela de
      login, o `URL_PREFIXO` está diferente do prefixo do WSGI — veja o Passo 4
- [ ] Abra `/demandas/` numa aba e `/adba/` em outra, logado nos dois. Nenhum
      dos dois deve derrubar o outro

**Teste que o modo de produção está mesmo ligado:** abra um endereço inventado,
tipo `/adba/xyz123`. Deve aparecer **a nossa página 404 desenhada**. Se aparecer
uma tela de erro técnica com código Python, o `APP_ENV=production` não pegou —
confira o Passo 4.

> Cuidado ao ler o resultado: um endereço inventado **sem** o `/adba`, como
> `/xyz123`, cai no roteador da conta e devolve a lista de sistemas em texto
> puro. Isso é o esperado — não é erro nosso.

---

## PASSO 9 — Backup automático (plano pago)

Aba **Tasks** → **Create a new scheduled task**:

```
cd /home/SEU-USUARIO/novos-convertidos && /home/SEU-USUARIO/novos-convertidos/venv/bin/python -m flask backup --limpar 30
```

Horário sugerido: **04:00** (madrugada, sistema parado).

O `--limpar 30` guarda as 30 cópias mais recentes e apaga as antigas — senão o disco enche em alguns meses.

### ⚠️ Cópia FORA do servidor

O backup automático protege contra erro humano (apagar algo sem querer). **Não protege contra a conta ser perdida ou o serviço sair do ar.**

Uma vez por mês, baixe uma cópia:

1. Aba **Files** → pasta `backups/`
2. Baixe o arquivo mais recente
3. Guarde em outro lugar (Google Drive, pen drive)

> São dados de pessoas reais. Incêndio e roubo levam as duas cópias juntas se estiverem no mesmo lugar.

---

## PASSO 10 — Divulgar o link do formulário

O endereço público é:

```
https://carlosneto.pythonanywhere.com/adba/cadastro/SEU-TOKEN
```

> Não esqueça o `/adba` — sem ele o link cai no roteador da conta.

**Como divulgar:** gere um QR Code desse link (há sites grátis), imprima e deixe na recepção da igreja. Quem cadastra aponta a câmera e o formulário abre.

**Se o link vazar ou começar a receber spam:** troque o `CADASTRO_TOKEN` no `.env`, dê **Reload** na aba Web, e gere um QR novo. O link antigo morre na hora — sem mexer em uma linha de código.

---

## Quando você mudar alguma coisa

```bash
cd ~/novos-convertidos
source venv/bin/activate
export FLASK_APP=run.py

flask backup              # SEMPRE antes de mexer no banco
git pull
pip install -r requirements.txt
flask db upgrade
```

Depois: aba **Web** → **Reload**.

---

## Se der errado

| Sintoma | O que olhar |
|---|---|
| **Os TRÊS sistemas cairam de uma vez** | Sintaxe do arquivo WSGI. Restaure a cópia — Passo 7.5 |
| **`/demandas` ou `/fechamento` quebrou** | Restaure a cópia (7.5). Depois: o Virtualenv tem as bibliotecas deles? |
| `/adba/` dá "not found", os outros funcionam | O `anexar-wsgi.sh` não rodou, ou rodou e o `create_app()` falhou. O motivo está no **Error log** |
| A raiz `/` não lista `/adba/` | O `create_app()` falhou. Nosso bloco só anuncia o que subiu. Veja o **Error log** |
| "Something went wrong :-(" | Aba **Web** → **Error log**. A última linha diz o motivo |
| Tela sem cor nenhuma | O mapeamento dos **Static files** (7.2). A URL é `/adba/static/`, com o prefixo |
| **Login entra e o F5 joga de volta na tela de login** | `URL_PREFIXO` diferente do prefixo do WSGI. O cookie sai com um *path* que o navegador nunca devolve |
| Login não entra, sem mensagem | O **Force HTTPS** (7.4) está desligado e o cookie não viaja |
| Logar aqui derruba a sessão do Demandas | Nome do cookie. O nosso é `adba_sessao`; se virar `session`, atropela os outros |
| "Configuração inválida para produção" | Falta `SECRET_KEY` ou `CADASTRO_TOKEN` no `.env` |
| Erro técnico na tela em vez da página 404 | `APP_ENV` não está como `production` |

---

## Lembretes de LGPD

Este sistema guarda **dados pessoais de pessoas reais**: nome, telefone, endereço, data de nascimento — e, no caso de menores, os dados do responsável legal.

1. **Só a equipe pastoral** deve ter acesso. Cada pessoa com seu próprio login, nunca um login compartilhado.
2. **Desative** o acesso de quem sair da equipe (tela de Responsáveis). Nunca apague a pessoa — o histórico dela precisa continuar fazendo sentido.
3. **A planilha exportada é a base inteira num arquivo só.** Não mande por WhatsApp nem deixe em pasta compartilhada.
4. **Quem pedir exclusão dos dados** tem direito pela lei. O telefone de contato está no rodapé do formulário público.
5. **A tela de Auditoria** mostra quem leu o quê. Se a igreja for questionada, é ali que está a resposta.
