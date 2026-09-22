# Colocar o sistema no ar — PythonAnywhere

> Guia passo a passo. Siga na ordem; cada passo depende do anterior.
> Reserve **40 minutos** na primeira vez.

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

## PASSO 1 — Criar a conta e o app web

1. Entre no PythonAnywhere
2. Aba **Web** → **Add a new web app**
3. Escolha **Manual configuration** *(não escolha "Flask" — o instalador dele conflita com a nossa estrutura)*
4. Escolha **Python 3.13** *(ou a mais nova disponível; o sistema exige 3.11+)*

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
```

Para salvar no `nano`: `Ctrl+O`, `Enter`, `Ctrl+X`.

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

## PASSO 7 — Configurar o servidor web

Volte à aba **Web**.

### 7.1 — Virtualenv

No campo **Virtualenv**, digite:

```
/home/SEU-USUARIO/novos-convertidos/venv
```

### 7.2 — Arquivo WSGI

Clique no link do **WSGI configuration file**. **Apague tudo** e coloque:

```python
import sys

# A pasta do projeto precisa estar na lista de busca do Python,
# senão ele não acha o pacote "app" nem o "config".
CAMINHO = "/home/SEU-USUARIO/novos-convertidos"
if CAMINHO not in sys.path:
    sys.path.insert(0, CAMINHO)

# Carrega o .env ANTES de criar o app: é dele que vêm a SECRET_KEY,
# o token do formulário e o APP_ENV=production.
from dotenv import load_dotenv
load_dotenv(CAMINHO + "/.env")

from app import create_app

# O nome "application" é obrigatório: é exatamente ele que o servidor procura.
application = create_app()
```

Troque `SEU-USUARIO` pelo seu nome de usuário. Salve.

### 7.3 — Arquivos estáticos

Na seção **Static files**, adicione:

| URL | Directory |
|---|---|
| `/static/` | `/home/SEU-USUARIO/novos-convertidos/app/static/` |

Isso faz o PythonAnywhere entregar o logo, o CSS e o JavaScript direto — mais rápido e sem gastar processamento do app.

### 7.4 — Forçar HTTPS

Ainda na aba **Web**, ligue **Force HTTPS**.

> Sem isso, alguém na mesma rede Wi-Fi poderia ler a senha digitada no login. Com `APP_ENV=production`, o cookie de sessão **só** viaja em HTTPS — então sem esta opção o login simplesmente não funcionaria.

### 7.5 — Recarregar

Botão verde **Reload**.

---

## PASSO 8 — Conferir que subiu certo

Abra `https://SEU-USUARIO.pythonanywhere.com`

**Checklist:**

- [ ] A tela de login aparece, com o logotipo da ADBA
- [ ] O cadeado do HTTPS aparece na barra do navegador
- [ ] Você entra com o login criado no Passo 6
- [ ] O sistema **exige** que você crie uma senha nova
- [ ] O painel abre
- [ ] O formulário público abre em `.../cadastro/SEU-TOKEN`
- [ ] Um token errado devolve "Página não encontrada"

**Teste que o modo de produção está mesmo ligado:** abra um endereço inventado, tipo `.../xyz123`. Deve aparecer **a nossa página 404 desenhada**. Se aparecer uma tela de erro técnica com código Python, o `APP_ENV=production` não pegou — confira o Passo 4.

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
https://SEU-USUARIO.pythonanywhere.com/cadastro/SEU-TOKEN
```

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
| "Something went wrong :-(" | Aba **Web** → **Error log**. A última linha diz o motivo. |
| Tela sem cor nenhuma | O caminho dos **Static files** (Passo 7.3) está errado |
| Login não entra, sem mensagem | O **Force HTTPS** (7.4) está desligado e o cookie não viaja |
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
