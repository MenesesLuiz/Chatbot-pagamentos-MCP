# Escopo do Projeto

## 1. Objetivo

O projeto deverá:

- substituir a IA local Ollama pela API Gemini;
- aplicar os conceitos e requisitos de segurança do Agent Payments Protocol (AP2);
- permanecer como um projeto pessoal e local, sem utilização pública;
- manter os pagamentos como simulação, sem movimentação financeira real.

---

## 2. Análise Atual do Projeto

### 2.1 Fluxo atual

```text
React → FastAPI/JWT → Ollama → MCP via stdio → SQLite
```

### 2.2 Principais problemas encontrados

- Ollama está fixo em `backend/main.py`.
- Não existe `requirements.txt`; a instalação depende de comandos manuais do README.
- O diretório `data/` não existe, mas `seed.py` tenta criar `data/app.db`; o seed pode falhar.
- CORS está aberto para qualquer origem.
- O modelo pode solicitar `realizar_compra`; a validação atual depende parcialmente de texto do usuário.
- Não existem Checkout Mandates, Payment Mandates, assinaturas digitais ou receipts.
- JWT usa HS256, adequado apenas para autenticação local; não substitui as assinaturas exigidas pelo AP2.
- O pagamento atual é apenas uma simulação de limite e estoque.
- O frontend guarda o JWT em `localStorage`.
- O README afirma haver três ferramentas MCP, mas documenta quatro.
- Há imagens referenciadas no README que não estão presentes no projeto.

---

## 3. Premissa sobre o AP2

O AP2 não é um gateway de pagamentos nem depende do Gemini. Ele define papéis, mandatos assinados, verificações e recibos para dar prova verificável da autorização do usuário.

A especificação atual é a v0.2:

- [Especificação AP2](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)

---

## 4. Fases de Implementação

## Fase 1 — Trocar Ollama pela API Gemini

### Arquivos envolvidos

- `backend/main.py`
- `.env.example`
- `README.md`
- Novo `requirements.txt`

### 1. Criar a credencial Gemini

1. Criar um projeto no Google AI Studio.
2. Criar uma chave Gemini restrita à API Gemini.
3. Nunca colocar a chave no React ou no Git.
4. Armazenar somente no `.env`.

A documentação atual recomenda manter a chave exclusivamente no backend e aplicar restrições de API.

- [Segurança das chaves Gemini](https://ai.google.dev/gemini-api/docs/api-key)

### 2. Atualizar o `.env.example`

Adicionar:

```env
SECRET_KEY=
GEMINI_API_KEY=
GEMINI_MODEL=
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_PATH=data/app.db
```

O modelo deve ficar configurável, sem ser fixado no código.

### 3. Criar `requirements.txt`

Incluir as dependências atuais do backend e substituir:

```text
ollama
```

por:

```text
google-genai
```

A SDK oficial atual é `google-genai`.

- [SDK oficial Python](https://github.com/googleapis/python-genai)

### 4. Substituir o cliente Ollama

Em `backend/main.py`:

- remover `AsyncClient` do Ollama;
- inicializar `genai.Client` com `GEMINI_API_KEY`;
- usar o cliente assíncrono (`client.aio`) porque a rota `/chat` é assíncrona;
- manter o MCP como camada de ferramentas.

A API Gemini possui suporte oficial a function calling.

- [Documentação de function calling](https://ai.google.dev/gemini-api/docs/generate-content/function-calling)

### 5. Adaptar as ferramentas MCP para o formato Gemini

O fluxo será:

1. Buscar as ferramentas no MCP.
2. Converter `name`, `description` e `input_schema` para declarações de função Gemini.
3. Enviar as funções ao modelo.
4. Quando Gemini solicitar uma função:
   - validar o nome;
   - validar os argumentos;
   - executar a ferramenta MCP;
   - devolver o resultado ao Gemini.
5. Repetir até obter uma resposta final.

Usar function calling manual, não automático, porque `realizar_compra` precisará passar por verificações determinísticas antes de ser executada.

### 6. Usar histórico compatível com Gemini

O formato de mensagens do Ollama não deve ser reaproveitado diretamente.

Recomendação mínima:

- adicionar `gemini_interaction_id` à tabela `chats`;
- usar a Interactions API com `previous_interaction_id`;
- manter SQLite apenas para o histórico visual e auditoria local;
- não reconstruir manualmente pensamentos ou chamadas internas do Gemini.

A API atual recomenda conversas estatais usando `previous_interaction_id`.

- [Guia Gemini](https://ai.google.dev/gemini-api/docs/get-started)

### 7. Adicionar limites de segurança

Na migração:

- limite máximo de chamadas Gemini por mensagem;
- timeout para Gemini e MCP;
- tratamento genérico de erro;
- não retornar exceções internas ao usuário;
- não enviar chaves, tokens ou mandatos privados para o modelo;
- impedir que texto do modelo seja considerado prova de pagamento.

### 8. Validar a migração

Testar:

1. login;
2. consulta de catálogo;
3. registro de intenção;
4. histórico;
5. chamada de ferramenta;
6. recusa de compra;
7. compra simulada;
8. falha de API Gemini;
9. ausência de `GEMINI_API_KEY`;
10. tentativa de prompt injection.

Resultado esperado: o projeto funciona exatamente como antes, mas usando Gemini.

---

## Fase 2 — Corrigir a Base de Segurança

### Backend

- Restringir CORS para `FRONTEND_ORIGIN`.
- Validar tamanho máximo de `ChatRequest.message`.
- Criar rate limit simples para login e chat.
- Manter MCP apenas via stdio local.
- Remover mensagens de exceção internas das respostas.
- Ativar `PRAGMA foreign_keys = ON`.
- Adicionar constraints e índices SQLite.
- Revalidar estoque dentro da transação de compra.
- Garantir idempotência por `intencao_id`.
- Usar caminho absoluto/configurável para o banco.
- Separar chave JWT da chave de assinatura AP2.

### Frontend

- Não exibir credenciais demo fora do modo local.
- Substituir `localStorage` por cookie `HttpOnly` quando o objetivo for maior segurança.
- Tratar token expirado automaticamente.
- Exibir confirmação visual antes de qualquer compra.
- Nunca permitir que a IA controle diretamente o botão de aprovação.

---

## Fase 3 — Modelar os Papéis do AP2

O projeto pode representar vários papéis no mesmo processo, desde que as responsabilidades sejam separadas:

| Papel AP2 | Implementação no projeto |
|---|---|
| Shopping Agent | Gemini + orquestrador FastAPI |
| Trusted Surface | Tela React de confirmação |
| Merchant | Catálogo, checkout e preços |
| Credential Provider | Simulador de credencial |
| Merchant Payment Processor | Simulador de processamento |
| Network | Fora do escopo inicial |

O Trusted Surface deve ser determinístico e nunca controlado pelo LLM.

- [Papéis AP2](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md#roles)

---

## Fase 4 — Implementar Primeiro o Fluxo Human Present

Não começar pelo modo autônomo.

### 1. Criar o Checkout

Quando o usuário escolher um produto:

1. Buscar produto e preço diretamente no banco.
2. Criar um checkout imutável.
3. Fixar:
   - produto;
   - quantidade;
   - preço;
   - moeda;
   - merchant;
   - expiração;
   - método de pagamento;
   - identificador do checkout.

O Gemini nunca deve enviar preço como fonte de verdade.

### 2. Assinar o Checkout

Criar um Checkout JWT assinado pelo Merchant.

Usar assinatura assimétrica, preferencialmente ES256. O AP2 exige que o checkout assinado seja vinculado por hash ao mandato.

- [Checkout Mandate](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/checkout_mandate.md)

### 3. Criar o Trusted Surface

A interface React deve mostrar:

- produto;
- quantidade;
- preço unitário;
- preço total;
- moeda;
- método;
- validade;
- merchant;
- aviso de simulação.

O usuário deve clicar explicitamente em “Aprovar compra”.

Uma frase como “pode pagar com Pix” não deve ser considerada autorização AP2.

### 4. Criar o Checkout Mandate

Implementar os tipos corretos:

```text
mandate.checkout.open.1
mandate.checkout.1
```

O mandato fechado deve conter o hash do checkout assinado.

### 5. Criar o Payment Mandate

Implementar:

```text
mandate.payment.open.1
mandate.payment.1
```

O mandato deve estar vinculado ao checkout e conter:

- valor;
- moeda;
- merchant;
- método de pagamento;
- identificador da transação;
- validade;
- instrumento permitido.

O AP2 define constraints como valor máximo, merchant permitido, instrumento permitido, orçamento e janela de execução.

- [Payment Mandate](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/payment_mandate.md)

### 6. Validar antes do pagamento

O backend deve verificar deterministicamente:

- assinatura;
- `vct`;
- expiração;
- emissor;
- destinatário;
- hash do checkout;
- valor;
- moeda;
- produto;
- quantidade;
- merchant;
- método;
- nonce;
- replay;
- usuário autenticado.

Se qualquer validação falhar, a compra não ocorre.

### 7. Gerar os receipts

Após a execução:

- gerar Checkout Receipt;
- gerar Payment Receipt;
- vincular os receipts aos respectivos mandatos;
- armazenar os artefatos de auditoria;
- somente depois atualizar estoque e limite.

O AP2 utiliza esses mandatos e receipts como evidência verificável de autorização e processamento.

---

## Fase 5 — Simular o Processamento de Pagamento

Como o projeto é pessoal:

- manter Pix e cartão como instrumentos simulados;
- não armazenar dados reais de cartão;
- não usar credenciais reais;
- deixar explícito no README que não há liquidação financeira;
- separar o simulador de pagamento do agente Gemini.

A transação só deve ser marcada como `aprovada` após a validação do Payment Mandate e a geração do Payment Receipt.

---

## Fase 6 — Adicionar o Modo Autônomo

Somente depois do fluxo Human Present funcionando.

Implementar:

1. Open Checkout Mandate.
2. Open Payment Mandate.
3. Limite máximo de valor.
4. Merchant permitido.
5. Métodos permitidos.
6. Janela de validade.
7. Orçamento acumulado.
8. Chave pública do agente em `cnf`.
9. Mandato fechado assinado pelo agente.
10. Proteção contra reutilização.
11. Rejeição explícita antes de apresentar novo mandato.

No modo autônomo, o agente pode assinar o mandato fechado, mas apenas dentro das restrições assinadas pelo usuário.

- [Fluxo autônomo AP2](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md#autonomous-human-not-present)

---

## Fase 7 — Testes Obrigatórios

Criar testes mínimos para:

- preço enviado pelo modelo ser ignorado;
- produto inexistente;
- quantidade negativa;
- estoque insuficiente;
- limite excedido;
- usuário acessando intenção de outro usuário;
- mandato expirado;
- assinatura inválida;
- checkout alterado;
- valor do pagamento diferente do checkout;
- replay do mesmo mandato;
- pagamento duplicado;
- método não autorizado;
- prompt injection tentando forçar compra;
- Gemini indisponível;
- MCP indisponível;
- tentativa de acessar histórico de outro usuário.

---

## 5. Ordem Prática de Execução

1. Corrigir setup (`data/`, dependências e README).
2. Migrar Ollama para Gemini.
3. Validar Gemini com as ferramentas MCP existentes.
4. Corrigir CORS, erros, estoque e idempotência.
5. Implementar Checkout assinado.
6. Implementar Trusted Surface no React.
7. Implementar Checkout Mandate e Receipt.
8. Implementar Payment Mandate e Receipt.
9. Integrar o fluxo Human Present.
10. Criar testes de segurança.
11. Somente então implementar o modo autônomo.

---

## 6. Escopo Deliberadamente Adiado

Ficam fora da primeira versão:

- pagamento real;
- Pix real;
- cartão real;
- A2A;
- UCP;
- infraestrutura pública.

Adicionar apenas quando o fluxo local Human Present estiver validado.
