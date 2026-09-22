# 🛒 ChatPay - Chatbot de Pagamentos com MCP (Model Context Protocol)
<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB" alt="React">
  <img src="https://img.shields.io/badge/SQLite-07405E?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Ollama-000000?style=flat-square&logo=ollama&logoColor=white" alt="Ollama">
</p>

ChatPay é um assistente virtual inteligente integrado a um sistema de pagamentos seguro utilizando a arquitetura **MCP (Model Context Protocol)**. O projeto conecta um agente de linguagem natural a ferramentas backend controladas para gerenciar catálogo de produtos, intenções de compra temporárias e efetivação de transações com controle de limite de crédito.

---

## 🚀 Tecnologias Utilizadas

* **Backend:** Python, FastAPI, Uvicorn, SQLite
* **Segurança e Autenticação:** JWT (JSON Web Tokens), Argon2 (`pwdlib`)
* **IA & MCP:** Ollama, Python MCP SDK (`mcp`)
* **Frontend:** React, Vite, CSS Moderno

---

## 🛠️ Arquitetura e Ferramentas (MCP Tools)

O servidor MCP (`mcp_server/server.py`) expõe **3 ferramentas principais** que o LLM aciona de forma autônoma e segura:

1. **`listar_catalogo`**: Consulta os produtos ativos e com estoque disponível no banco de dados.
2. **`registrar_intencao`**: Cria um carrinho temporário (expira em 10 minutos) validando estoque, quantidade e regras de negócio sem movimentar saldo financeiro.
3. **`realizar_compra`**: Valida a intenção gerada na sessão, checa o limite de saldo disponível do usuário, processa o pagamento (Pix ou Cartão) de forma atômica e atualiza o estoque.
4. **`consultar_historico_compras`**: Permite que o usuário consulte as informações das últimas compras realizadas em sua conta. A consulta respeita o isolamento de sessão, garantindo que cada usuário tenha acesso somente ao seu próprio histórico de compras.

---

## 📂 Estrutura do Projeto

```text
chatbot-pagamentos-mcp/
├── backend/
│   └── main.py          # API FastAPI principal (Endpoints de chat, login, JWT e ponte com MCP)
├── data/
│   └── .gitkeep         # Mantém a pasta no versionamento (o app.db é gerado pelo seed)
├── frontend/            # Interface visual em React/Vite
│   ├── src/
│   ├── package.json
│   └── ...
├── mcp_server/
│   └── server.py        # Servidor MCP com as regras de negócio e tools
├── seed.py              # Script de inicialização e carga de dados (Seed)
└── README.md
```

# ⚙️ Como Executar o Projeto Localmente
## 1. Pré-requisitos
* Python 3.10+ instalado

* Node.js e npm instalados

* Servidor Ollama rodando localmente

## 2. Configurar o Ollama

Instale o Ollama pelo [site oficial](https://ollama.com/download). Depois, abra um terminal e baixe o modelo utilizado pelo projeto:

```shell
ollama pull qwen3:1.7b
```

O backend usa exatamente o modelo `qwen3:1.7b`, configurado em `backend/main.py`.

Verifique se o modelo foi instalado:

```shell
ollama list
```

O Ollama normalmente inicia o serviço automaticamente. Se ele não estiver rodando, inicie-o com:

```shell
ollama serve
```

Se aparecer uma mensagem informando que a porta já está em uso, o serviço provavelmente já está rodando; nesse caso, não é necessário iniciar outro processo.

Opcionalmente, teste o modelo diretamente:

```shell
ollama run qwen3:1.7b
```

## 3. Configurar o Backend e o Banco de Dados
No terminal, navegue até a raiz do projeto e configure o ambiente virtual:

```python
# Criar e ativar ambiente virtual (Windows)
python -m venv .venv
.venv\Scripts\activate

# Instalar dependências da API e do MCP
pip install fastapi uvicorn pydantic pyjwt pwdlib argon2-cffi ollama mcp python-dotenv

# Criar a configuração local a partir do exemplo (Linux/macOS)
cp .env.example .env

# No Windows PowerShell, use: Copy-Item .env.example .env

# Gere uma chave aleatória com pelo menos 32 bytes
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"

# Copie a linha exibida acima para o arquivo .env, substituindo SECRET_KEY=

# Executar o seed para criar e popular o banco de dados do zero
python seed.py
```

## 4. Iniciar o Servidor Backend (FastAPI)

```python
uvicorn backend.main:app --reload
```
## 5. Iniciar o Frontend (React)
Abra um novo terminal na pasta do frontend:

```python
cd frontend
npm install
npm run dev
```

# 👥 Usuários de Teste

Para testar os cenários de limite excedido e sucesso, utilize as credenciais padrão geradas pelo seed:

* Usuário Normal (Limite Alto - R$ 2.000,00):

* Username: cliente_normal

* Senha: 123456

* Usuário com Limite Baixo (R$ 100,00):

* Username: cliente_baixo

* Senha: 123456

## 6. Caso dê erro de conexão com o Ollama/MCP

Para verificar quais modelos do Ollama estão instalados na sua máquina, execute:

```shell
ollama list
```

O back-end está configurado para utilizar o modelo `qwen3:1.7b`. Caso você tenha outra versão instalada, altere a configuração do back-end para utilizar exatamente o nome exibido pelo comando `ollama list`.

No meu caso, por exemplo:

```text
qwen3:1.7b
```

---

# 🛒 Consulta do Histórico de Compras

O ChatPay também permite que o usuário consulte o histórico das compras realizadas anteriormente.

Por meio da ferramenta MCP `consultar_historico_compras`, o sistema recupera as informações das últimas transações associadas ao usuário autenticado, permitindo acompanhar suas compras diretamente pelo chat.

A funcionalidade mantém o **isolamento dos dados entre usuários**, garantindo que um usuário não consiga consultar o histórico de compras de outra conta.

Essa funcionalidade complementa o fluxo de pagamentos ao permitir não apenas realizar novas compras, mas também consultar as transações já realizadas.

---


# 📸 Evidências dos Testes (Prints)

## Cenário de Sucesso (Compra Aprovada)
<img width="603"  alt="O Print de Sucesso da Compra" src="./venda-sucesso.png" />

## Cenário de Regra (Limite Excedido)
<img width="603"  alt="O Print de Limite Excedido" src="./limite-nao-aprovado.png" />

## Cenário de Segurança (Pedidos Maliciosos)
<img width="603" alt="O print de teste de pedidos maliciosos" src="./intencao-maligna.png" />

## Cenário de Amostra (Catalogo entregue)
<img width="603"  alt="O Print do CatálogoInterface" src="./catalogo.png" />

## Histórico de Compras (Extra)
<img width="603"  alt="O Print do Histórico de Compras" src="./historico-de-compras.png" />

## Sistema de Chat 
https://github.com/user-attachments/assets/6ae4dccd-7843-4b20-8695-16d0b76b920c


# 🛡️ Principais Validações de Segurança Implementadas
* Prevenção de Deadlock: Uso de timeout configurado no SQLite e commits atômicos para evitar travamentos de concorrência.

* Isolamento de Sessão: Validação estrita de user_id e chat_id em todas as ferramentas MCP.

* Prevenção de Fraudes: O preço real do produto nunca é enviado pelo modelo de IA; ele é buscado diretamente no banco de dados com base no produto_id.

## 🔎 Auditoria das Chamadas MCP

Cada chamada de tool é registrada na tabela `tool_results`, incluindo o usuário, a sessão, a ferramenta, os argumentos, o valor da operação, o resultado e o horário.

Depois de utilizar o chat, consulte os registros com:

```bash
sqlite3 -header -column data/app.db "SELECT u.username AS quem, t.created_at AS quando, t.tool_name AS tool, t.result_json AS resultado FROM tool_results t LEFT JOIN users u ON u.id = t.user_id ORDER BY t.id DESC;"
```

O campo `resultado` contém o status da operação, o valor, os argumentos e eventuais mensagens de erro ou recusa.

## 🚀 Squad 9

*Autor:* [Thiago Klebis](https://www.linkedin.com/in/thiagoklebis/)

*Autor:* [Luiz Meneses](https://www.linkedin.com/in/menesesluizf/)

*Autor:* [Carlos Eduardo Darmada](https://www.linkedin.com/in/cadudarmada/)