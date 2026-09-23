# Sistema de Acompanhamento de Novos Convertidos — ADBA

> Documento de referência do projeto. Fonte da verdade para todas as etapas.

## REGRAS DE TRABALHO
1. Comentar o código linha a linha — o dono do projeto é leigo em programação.
2. Mostrar a estrutura antes de escrever código e aguardar OK.
3. Construir em etapas. Ao fim de cada etapa: parar, explicar como testar, aguardar OK.
4. Segurança não é opcional (seção 7). Avisar sobre qualquer brecha nova identificada.
5. Nunca colocar informação confidencial no front-end.

---

## 1. VISÃO GERAL

Sistema web para a igreja ADBA cadastrar e acompanhar pastoralmente pessoas que
aceitaram Jesus ("novos convertidos" ou "almas").

**Fluxo:**
1. Qualquer membro acessa um link público e cadastra a alma que aceitou Jesus.
2. A alma entra com status **"Aguardando responsável"**.
3. O **Admin** designa um **Responsável** (equipe de evangelismo).
4. O Responsável faz contatos (telefone, WhatsApp, presencial), registra cada um
   e marca presenças nos cultos.
5. Um painel colorido mostra em ONE PAGE quem está em dia e quem está abandonado.

**Papéis:**

| Papel | Acesso |
|---|---|
| **Público** (sem login) | Apenas o formulário de cadastro. Depois de enviar, vê só "Cadastro realizado!" |
| **Responsável** (login) | Painel e ficha **somente** das almas designadas a ele. Registra contatos e presenças. |
| **Admin** (login) | Tudo: designa responsáveis, cria usuários, cadastra eventos, vê relatórios, exporta Excel, mescla duplicados. |

---

## 2. STACK TÉCNICA

- **Backend:** Python 3.11+ / Flask
- **Templates:** Jinja2 (autoescape ligado)
- **ORM:** SQLAlchemy + Flask-Migrate (Alembic)
- **Banco:** SQLite (arquivo único). Conexão em variável de ambiente.
- **Auth:** Flask-Login + **bcrypt** (decidido)
- **Formulários:** Flask-WTF (CSRF em todos, inclusive no público)
- **Rate limit:** Flask-Limiter
- **Excel:** openpyxl
- **Front-end:** Tailwind CSS (CDN) + Alpine.js (CDN) + Chart.js (CDN). **Sem build, sem Node, sem npm.**
- **Deploy alvo:** PythonAnywhere (WSGI, sem processos em background permanentes)

> ⚠️ Python local é 3.14, mas o PythonAnywhere vai até 3.13. Manter o código
> compatível com 3.11+ e não usar recursos exclusivos do 3.14.

---

## 3. MODELO DE DADOS

### `usuario`
```
id                UUID (PK)
nome              String, obrigatório
login             String, único, obrigatório
senha_hash        String (bcrypt)
telefone          String
papel             Enum: 'admin' | 'responsavel'
ativo             Boolean, default True
criado_em         DateTime
```

### `novo_convertido`
```
id                      UUID (PK)  -> usado em TODAS as URLs
codigo                  Integer, autoincrement, único -> só exibição (#001, #002)

-- Dados pessoais
nome_completo           String, obrigatório
telefone                String, obrigatório
sexo                    Enum: 'M' | 'F'
data_nascimento         Date, obrigatório

-- Endereço (via ViaCEP)
cep, logradouro, numero, complemento, bairro, cidade, uf

-- Conversão
trabalho                Enum: 'culto_dominical' | 'culto_ensino' | 'culto_ceia' |
                              'encontro_tribo' | 'evangelismo_rua' |
                              'trabalho_preciosas' | 'outro'
trabalho_outro          String (obrigatório se trabalho == 'outro')
data_conversao          Date, default hoje
departamento            Enum: 'geracao_life' | 'preciosas' | 'irmaos' (obrigatório)

-- Questionário
como_chegou             Text
tem_conhecido           Boolean
conhecido_nome          String
ja_frequentou_igreja    Boolean
qual_igreja             String

-- Quem cadastrou
cadastrante_nome        String, obrigatório
cadastrante_telefone    String, obrigatório

-- LGPD
consentimento_em        DateTime, obrigatório
consentimento_ip        String
responsavel_legal_nome      String (obrigatório se menor de 18)
responsavel_legal_telefone  String (obrigatório se menor de 18)

-- Gestão
status_ciclo            Enum: 'aguardando_responsavel' | 'em_acompanhamento' |
                              'integrado' | 'frequenta_outra_igreja' |
                              'nao_deseja_contato' | 'perdido_contato' | 'mudou_cidade'
                        default 'aguardando_responsavel'
status_justificativa    Text (obrigatório ao sair de 'em_acompanhamento')
status_alterado_em      DateTime
responsavel_atual_id    FK usuario (nullable)
designado_em            DateTime (nullable)
mesclado_em_id          FK novo_convertido (nullable) -> se preenchido, é duplicata inativa
observacao_sensivel     Text -> visibilidade controlada (seção 7, item 11)
criado_em               DateTime
```

### `atribuicao` — histórico de responsáveis, **nunca apagar linha**
```
id, convertido_id (FK), responsavel_id (FK), inicio DateTime,
fim DateTime (nullable = atual), motivo Text, atribuido_por_id (FK usuario)
```

### `contato`
```
id, convertido_id (FK), responsavel_id (FK)
tipo        Enum: 'telefone' | 'whatsapp' | 'presencial'
data_hora   DateTime, obrigatório
resultado   Enum: 'efetivo' | 'sem_resposta' | 'recusou_contato'
relato      Text, obrigatório
criado_em   DateTime
```

### `evento`
```
id, nome String, tipo Enum: 'culto_dominical' | 'culto_ensino' | 'culto_ceia' |
                            'encontro_tribo' | 'trabalho_preciosas' | 'outro'
data Date, recorrente Boolean, criado_por_id FK, ativo Boolean
```
**Seed automático:** "Culto Dominical" todo domingo e "Culto de Ensino" toda
terça, 90 dias à frente. Comando `flask seed-eventos` estende a agenda e pode
ser rodado manualmente. Eventos pontuais: só Admin cadastra.

### `presenca`
```
id, convertido_id (FK), evento_id (FK), presente Boolean,
registrado_por_id (FK usuario), registrado_em DateTime
UNIQUE(convertido_id, evento_id)
```

### `log_auditoria`
```
id, usuario_id (FK, nullable), acao String, entidade String, entidade_id String,
detalhe Text, ip String, criado_em DateTime
```
Registrar obrigatoriamente: login/logout, designação, transferência, mudança de
status, mesclagem, exportação Excel, leitura de observação sensível,
criação/desativação de usuário.

---

## 4. REGRA DO SEMÁFORO (coração do sistema)

**Dois relógios independentes por alma:**
- `dias_desde_ultima_tentativa` — qualquer contato, com qualquer resultado. **Mede o Responsável.**
- `dias_desde_contato_efetivo` — só `resultado = 'efetivo'`. **Mede a alma.**

**Prazos:**
- Alma designada e **sem nenhum contato** → prazo de **48 horas**.
- Alma com pelo menos um contato → prazo de **7 dias**.
- **Na transferência de responsável, o relógio volta a 48h**, mas o histórico
  permanece intacto e visível.

**Cor do card = o PIOR dos dois relógios:**

| Dias | Cor |
|---|---|
| 0–7 | 🟢 Verde |
| 8–14 | 🟡 Amarelo |
| 15–21 | 🟠 Laranja |
| 22+ | 🔴 Vermelho |

**Ícone no card indica qual relógio estourou:**
- 📵 = o responsável não tentou contato (falha do responsável)
- 🚫 = há tentativas, mas nenhuma efetiva (a alma não responde)

**Exceções:**
- `status_ciclo = 'aguardando_responsavel'` → 🟣 **ROXO**, só no painel do Admin,
  relógio próprio (meta: 24h para designar).
- Qualquer `status_ciclo` diferente de `em_acompanhamento` **sai do semáforo** e
  some do painel principal (acessível por filtro).

Todo o cálculo de cor e de dias é feito **no backend**. O front apenas exibe.

---

## 5. TELAS

Barra de navegação horizontal fixa no topo.
- **Admin vê:** Painel · Novo Convertido · Responsáveis · Eventos · Relatórios
- **Responsável vê:** Painel · Eventos

### 5.1 `/cadastro/<token>` — PÚBLICO, sem login
Mobile-first. Formulário em 4 blocos com barra de progresso:

1. **Quem está cadastrando** — nome e telefone (obrigatórios)
2. **Dados da alma** — nome, telefone, sexo, data de nascimento, endereço com
   busca automática por CEP (`https://viacep.com.br/ws/{cep}/json/`)
3. **A conversão** — trabalho (campo livre se "outro"), departamento
   (sugerido por sexo + idade, mas **sempre confirmado manualmente**)
   - Sugestão: menor de 25 → *Geração Life*; mulher 25+ → *Preciosas*; homem 25+ → *Irmãos*
4. **Questionário** — como chegou, tem conhecido na igreja (+ nome), já
   frequentou igreja evangélica (+ qual)

**Bloco LGPD no rodapé — checkbox obrigatório, NÃO pré-marcado:**
> ☐ Autorizo a `{IGREJA_NOME_LEGAL}` a registrar e utilizar meus dados pessoais
> exclusivamente para acompanhamento pastoral e comunicação da igreja. Meus dados
> não serão compartilhados com terceiros. Posso solicitar acesso, correção ou
> exclusão a qualquer momento pelo telefone (16) 99280-5852.

**Se menor de 18**, o formulário revela automaticamente dois campos obrigatórios
(nome e telefone do responsável legal) e um segundo checkbox de autorização.
Sem esses campos, o envio é bloqueado.

Ao enviar: grava `consentimento_em` e `consentimento_ip`, redireciona para
**"Cadastro realizado! 🙌"** sem exibir dado nenhum e sem link para o resto do sistema.

### 5.2 `/painel` — ONE PAGE
- **Faixa roxa no topo (só Admin):** *"⚠️ 3 almas aguardando responsável — a mais antiga há 4 dias"*, clicável
- **Cartões de KPI:** total em acompanhamento · em dia · em atenção (amarelo+laranja) · críticas · integradas no mês
- **Grade de cards:** inicial do nome em círculo colorido, nome, `#código`,
  departamento, responsável, "X dias sem contato", ícone do relógio estourado,
  barra lateral colorida
- **Filtros:** status, responsável, departamento, cor, trabalho de conversão, período
- **Busca** por nome, telefone ou código
- Responsável vê **apenas** suas almas (filtrado no `query` do backend, nunca no JavaScript)

### 5.3 Drawer lateral (abre ao clicar num card)
Abas: **Dados · Contatos · Presenças · Histórico**
- Dados completos + botão "Editar" (Admin)
- Timeline de contatos (mais recente primeiro), ícone por tipo e cor por resultado
- Presenças: eventos dos últimos 60 dias com ✅/❌
- Histórico: todas as atribuições com datas e motivo
- Botões: **Registrar contato** · **Marcar presença** · **Alterar status** ·
  **Transferir responsável** (Admin) · **Copiar relatório WhatsApp**

**Formato do "Copiar relatório WhatsApp":**
```
🙌 *Acompanhamento — Maria Silva (#012)*
📅 Convertida em 07/09 · Culto Dominical
🏠 Departamento: Preciosas
👤 Responsável: João Pereira
📞 Último contato: 18/09 (efetivo)
⛪ Presenças: 3 de 5 cultos
🟢 Em dia
```

### 5.4 `/responsaveis` — só Admin
Criar usuário (login + senha gerada), ativar/desativar, redefinir senha.
Tabela de carga: quantas almas cada um tem, % no verde, dias médios entre
contatos, almas críticas.

### 5.5 `/eventos`
Lista dos próximos e passados. Admin cadastra eventos pontuais. Responsável só visualiza.

### 5.6 `/relatorios` — só Admin
Gráficos Chart.js:
- Conversões por mês (linha)
- Conversões por trabalho (barra)
- Distribuição por departamento (rosca)
- Funil de status do ciclo de vida
- Taxa de retenção: % com presença nos últimos 30 dias
- Ranking de responsáveis

**Botão "Exportar Excel"** (openpyxl): abas *Novos Convertidos*, *Contatos*,
*Presenças*, *Responsáveis*. Cabeçalho formatado, colunas ajustadas, filtros
ativados. Registrar a exportação no log de auditoria.

### 5.7 Mesclagem de duplicados — só Admin
Lista possíveis duplicatas (telefone igual ou nome parecido). Ao mesclar: mantém
o registro mais antigo, transfere contatos e presenças, marca o duplicado com
`mesclado_em_id` e o remove do painel. **Nunca apagar do banco.**

---

## 6. IDENTIDADE VISUAL

Estilo CRM moderno (Pipedrive / HubSpot). Limpo, muito espaço em branco, cantos
arredondados, sombras suaves, tipografia Inter (Google Fonts).

- **Paleta tirada do logotipo da ADBA** (`logotipo ADBA/`):
  - Chama: `#C13B34` (vermelho) — usada só em **acentos**
  - Letras: `#858488` (cinza) — escurecido para `#3E3D42` como cor principal da interface
  - Motivo de não usar o vermelho da marca nos botões: no semáforo o vermelho significa **alma crítica**. Dois vermelhos parecidos na mesma tela esvaziariam o alerta.
- Semáforo: verde `#16a34a` · amarelo `#eab308` · laranja `#f97316` · vermelho `#dc2626` · roxo `#9333ea`
- Transições suaves nos cards e no drawer
- **100% responsivo** — o formulário público será preenchido majoritariamente no celular
- Estados vazios desenhados (ilustração + texto), nunca uma tela em branco

---

## 7. SEGURANÇA — verificar item a item

1. **Senhas:** bcrypt. Nunca MD5/SHA simples, nunca texto puro.
2. **IDOR:** todas as rotas usam UUID, nunca o código sequencial. **Além disso**,
   toda rota valida no backend se a alma pertence ao responsável logado.
   Um responsável que digite o UUID de outra alma deve receber 403.
3. **Filtro no backend:** a consulta ao banco já traz apenas os dados permitidos.
   Nunca trazer tudo e esconder no JavaScript.
4. **CSRF:** Flask-WTF em todos os formulários, inclusive no público.
5. **XSS:** autoescape do Jinja ligado. **Proibido usar `|safe`** em qualquer
   campo preenchido por usuário — especialmente `relato`, `observacao_sensivel`
   e `como_chegou`.
6. **Validação de entrada:** todos os campos validados no servidor (tamanho,
   formato, tipo). Validação no navegador é conveniência, não segurança.
7. **Formulário público:** honeypot, rate limit por IP (5 envios/hora), token na
   URL armazenado em configuração e revogável sem alterar código.
8. **Segredos:** `SECRET_KEY`, token do formulário e credenciais em `.env`,
   carregado com `python-dotenv`. `.env.example` versionado, `.env` no `.gitignore`.
9. **Sessão:** cookie `HttpOnly`, `Secure`, `SameSite=Lax`, expiração de 8 horas.
10. **Login:** rate limit (5 tentativas por 15 minutos por IP).
11. **Observação sensível:** visível apenas ao responsável atual e ao Admin.
    Na transferência, **não** é repassada automaticamente — o Admin decide.
    Controlado por `OBSERVACAO_SENSIVEL_RESTRITA = True`. Toda leitura auditada.
12. **Exportação Excel:** exclusiva do Admin, registrada em auditoria.
13. **Auditoria:** tabela append-only, sem rota de edição ou exclusão.
14. **Backup:** comando `flask backup` que copia o `.db` com data no nome.

---

## 8. CONFIGURAÇÃO (`config.py`)

```python
IGREJA_NOME = "ADBA"
IGREJA_NOME_LEGAL = "Assembleia de Deus Ministerio Belem"
IGREJA_CNPJ = "45.275.005/0001-65"
IGREJA_TELEFONE = "(16) 99280-5852"

PRAZO_PRIMEIRO_CONTATO_HORAS = 48
PRAZO_CONTATO_DIAS = 7
PRAZO_DESIGNACAO_HORAS = 24
FAIXAS_SEMAFORO = {"verde": 7, "amarelo": 14, "laranja": 21}

OBSERVACAO_SENSIVEL_RESTRITA = True
IDADE_MAIORIDADE = 18
```

---

## 9. ETAPAS DE CONSTRUÇÃO

Parar ao fim de cada etapa e aguardar OK.

- [x] **Etapa 1** — Estrutura de pastas, `requirements.txt`, `config.py`, `.env.example`, app Flask com "Olá mundo"
- [x] **Etapa 2** — Modelos SQLAlchemy + migrações + seed (admin inicial + eventos recorrentes)
- [x] **Etapa 3** — Formulário público completo (ViaCEP, LGPD, menor de idade, honeypot, rate limit) + tela de sucesso
- [x] **Etapa 4** — Autenticação (login, logout, papéis, proteção de rotas)
- [x] **Etapa 5** — Painel com cards, semáforo, filtros e faixa de pendentes
- [x] **Etapa 6** — Drawer lateral: registrar contato, marcar presença, alterar status, transferir responsável, copiar WhatsApp
- [x] **Etapa 7** — Telas de Responsáveis e Eventos
- [x] **Etapa 8** — Relatórios, gráficos e exportação Excel
- [x] **Etapa 9** — Mesclagem de duplicados + log de auditoria + comando de backup
- [x] **Etapa 10** — Revisão de segurança item a item da seção 7 + deploy no PythonAnywhere

---

## DECISÕES JÁ TOMADAS

| Assunto | Decisão |
|---|---|
| Hash de senha | bcrypt (`Flask-Bcrypt`) |
| Razão social | Assembleia de Deus Ministério Belém |
| CNPJ | 45.275.005/0001-65 |
| Admin inicial | login `admin`, senha inicial no `.env`, **troca obrigatória no 1º login** (Etapa 4) |
| Ambiente virtual | `venv/` na raiz do projeto |

## DESVIOS DA ESPECIFICAÇÃO (decididos durante a construção)

| O quê | Por quê |
|---|---|
| Campo extra `usuario.deve_trocar_senha` | Obriga a troca da senha inicial no 1º login (combinado na Etapa 1). |
| Tabela extra `contador` (8ª tabela) | O `codigo` sequencial não pode usar o autoincremento do SQLite (a PK é UUID). Calcular `MAX(codigo)+1` gera códigos duplicados quando duas almas são gravadas juntas — bug comprovado em teste. O contador resolve de forma atômica. |
| Paleta extraída do logotipo | As cores foram lidas do arquivo do logo pixel a pixel. O cinza puro (`#858488`) tem contraste 3.71 com texto branco — abaixo do mínimo de 4.5 — então foi escurecido para `#3E3D42` (contraste 10.76). |
| Lista em linhas, não grade de cards | Pedido do usuário. Cabem 14 linhas onde cabiam 8 cards, e as colunas alinhadas deixam varrer "quem está pior" de relance. Montada com `grid` (não `flex`), senão a coluna de ação desalinha as linhas que não a têm. |
| Ficha lateral carregada sob demanda | A rota `/alma/<id>/ficha` devolve só um pedaço de HTML, buscado ao clicar no nome. Trazer os contatos das 300 almas no painel carregaria milhares de registros que ninguém olharia. |
| Prazo estourado nunca fica verde | A seção 4 se contradiz: uma alma designada há 3 dias **sem nenhum contato** estoura o prazo de 48h, mas cairia em "0–7 dias = VERDE". O card diria "em dia" sobre alguém abandonado desde o primeiro dia. Decisão: verde significa "dentro do prazo"; prazo estourado vira no mínimo **amarelo**. Reversível apagando 3 linhas em `app/semaforo.py`. |
| Designação de responsável entrou na Etapa 5 | A faixa roxa sem o botão de designar seria um aviso sem saída — nada sairia de "aguardando responsável" e o semáforo nunca começaria a contar. A **transferência** continua na Etapa 6. |
| Comando `flask dados-exemplo` | Cria 13 almas fictícias, uma para cada cor do semáforo, para dar para conferir o painel de verdade. Todas marcadas com cadastrante "EXEMPLO" e telefone 16900…, removíveis com `--apagar`. |
| Ícones em SVG, não emoji | Emoji muda de desenho em cada sistema, não acompanha a cor do texto e não permite ajuste fino de tamanho. Os ícones do sistema ficam em `app/templates/_icones.html`. |
| Sem `x-transition` do Alpine no formulário | As transições do Alpine dependem de `requestAnimationFrame`. Quando o navegador economiza recursos (aba em segundo plano, bateria fraca), esse relógio para e o bloco fica **congelado semitransparente** — bug reproduzido em teste. Trocado por animação CSS (`custom.css`), que não pode travar. |
| Bolinha dos cartões de escolha no `custom.css` | O `peer-checked:` do Tailwind vira o seletor `~`, que só alcança irmãos. A bolinha fica dentro do rótulo. Resolvido com seletor descendente. |
| Datas gravadas em UTC | O servidor do PythonAnywhere roda em UTC e o Brasil em UTC-3. Gravar em UTC e exibir em `America/Sao_Paulo` (`app/tempo.py`) evita o relógio do semáforo pular um dia. Exige o pacote `tzdata` no Windows. |

### O sistema não tem o domínio só para ele

**A especificação supõe que o sistema mora na raiz do endereço.** No servidor
não é o caso: `carlosneto.pythonanywhere.com` já servia dois sistemas em uso,
e no PythonAnywhere uma conta tem **um web app por domínio**. Os três rodam
no mesmo processo, montados por prefixo:

| Prefixo | Sistema |
|---|---|
| `/demandas` | Controle de Demandas (já existia) |
| `/fechamento` | Fechamento Contas a Pagar (já existia) |
| `/adba` | este sistema |

**O que isso obrigou a mudar:**

1. **`URL_PREFIXO` no `.env`** → define `SESSION_COOKIE_PATH` e
   `REMEMBER_COOKIE_PATH`. Sem isso o cookie vale `/` e viaja junto de toda
   requisição aos outros dois sistemas, sem necessidade.
2. **`deploy/bloco_wsgi_adba.py`** → o bloco que monta este sistema. É
   **anexado** ao arquivo WSGI da conta, nunca substitui: aquele arquivo
   guarda as senhas dos outros dois e reescrevê-lo derrubaria ambos.
   O `create_app()` fica num `try/except` — um erro nosso não pode levar
   sistemas de terceiros junto.
3. **`anexar-wsgi.sh`** → faz cópia de segurança, anexa, valida a sintaxe e
   restaura sozinho se quebrar.
4. **Estáticos em `/adba/static/`**, não `/static/`. O mapeamento acontece no
   servidor, antes do Python; a URL genérica interceptaria requisição dos
   outros sistemas.
5. **`testes/teste_multiapp.py`** → 34 verificações que montam dois sistemas
   falsos com a mesma armadilha de nomes de módulo (`web_app`, `dados`,
   `core`) e provam que ninguém atropela ninguém, inclusive que os outros dois
   **continuam no ar se este falhar**.

O `SESSION_COOKIE_NAME` já era `adba_sessao`, e não o padrão `session` do
Flask — por sorte, não por previsão. Com o nome padrão, logar aqui teria
derrubado a sessão de quem estivesse nos outros dois sistemas.
