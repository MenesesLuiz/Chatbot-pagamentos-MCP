import os
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from ollama import AsyncClient
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession


# CONFIGURAÇÕES
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY não configurada ou vazia. Preencha SECRET_KEY no arquivo .env."
    )
if len(SECRET_KEY.encode("utf-8")) < 32:
    raise RuntimeError("SECRET_KEY precisa ter pelo menos 32 bytes.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 2
DB_PATH = "data/app.db"

app = FastAPI(title="ChatPay Backend API")
security = HTTPBearer()
password_hash = PasswordHash((Argon2Hasher(),))
ollama = AsyncClient()

# Permite que o frontend React converse com a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# MODELOS DE DADOS
class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    message: str


# FUNÇÕES AUXILIARES
SYSTEM_PROMPT = """
Você é o assistente do ChatPay.

Regras obrigatórias:
- Use as ferramentas MCP para consultar o catálogo e executar operações de compra.
- Nunca invente produtos, valores, intenções, transações ou limites.
- Nunca assuma o método de pagamento com base no histórico. Aguarde o usuário confirmar
  explicitamente Pix ou cartão na mensagem atual.
- Depois de registrar uma intenção, pergunte qual método de pagamento o usuário deseja.
- Só diga que uma compra foi aprovada quando realizar_compra retornar status "aprovado".
- Se uma ferramenta retornar uma recusa, explique a recusa e não diga que a compra foi concluída.
""".strip()


def normalizar_texto(texto: str) -> str:
    texto_sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(
        caractere for caractere in texto_sem_acento
        if not unicodedata.combining(caractere)
    )


def detectar_metodo_confirmado(mensagem: str) -> str | None:
    """Retorna um método somente quando há uma única confirmação explícita."""
    texto = normalizar_texto(mensagem)
    metodos = []

    if re.search(r"\bpix\b", texto):
        metodos.append("pix")
    if re.search(r"\bcartao\b", texto):
        metodos.append("cartao")

    return metodos[0] if len(metodos) == 1 else None


def resposta_afirma_aprovacao(texto: str) -> bool:
    """Detecta uma aprovação textual sem tratá-la como prova de pagamento."""
    texto_normalizado = normalizar_texto(texto)
    negacoes = (
        "nao foi",
        "nao e possivel",
        "nao aprovada",
        "nao aprovado",
        "recusad",
        "falha",
        "erro",
    )
    if any(negacao in texto_normalizado for negacao in negacoes):
        return False

    frases_de_aprovacao = (
        "compra realizada",
        "compra aprovada",
        "pagamento realizado",
        "pagamento aprovado",
        "transacao aprovada",
        "venda realizada",
        "purchase completed",
        "purchase approved",
        "payment successful",
    )
    return any(frase in texto_normalizado for frase in frases_de_aprovacao)


def get_db():
    # TIMEOUT ADICIONADO PARA EVITAR "DATABASE IS LOCKED"
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn


def registrar_auditoria(conn, user_id, chat_id, tool_name, argumentos, resultado_texto):
    """Registra todas as chamadas MCP feitas pelo backend."""
    try:
        resultado = json.loads(resultado_texto)
    except json.JSONDecodeError:
        resultado = {"texto": resultado_texto}

    intencao_id = None
    if isinstance(argumentos, dict):
        intencao_id = argumentos.get("intencao_id")
    if not intencao_id and isinstance(resultado, dict):
        intencao_id = resultado.get("intencao_id")

    valor_centavos = None
    if isinstance(resultado, dict):
        valor = resultado.get("valor_total", resultado.get("valor"))
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            valor_centavos = round(valor * 100)

    # Em recusas como limite excedido, o valor pode não voltar no resultado.
    if valor_centavos is None and intencao_id:
        intencao = conn.execute(
            "SELECT valor_total_centavos FROM intencoes WHERE id = ?",
            (intencao_id,)
        ).fetchone()
        if intencao:
            valor_centavos = intencao["valor_total_centavos"]

    auditoria = {
        "argumentos": argumentos,
        "resultado": resultado,
        "valor_centavos": valor_centavos,
    }

    conn.execute(
        """
        INSERT INTO tool_results
        (user_id, chat_id, tool_name, intencao_id, result_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            chat_id,
            tool_name,
            intencao_id,
            json.dumps(auditoria, ensure_ascii=False),
            datetime.now(timezone.utc).isoformat(),
        )
    )

# Middleware de Autenticação JWT
def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=401, detail="Identidade do token inválida")

    conn = get_db()
    try:
        user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    return user_id


# ROTAS DA API
@app.post("/login")
def login(req: LoginRequest):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (req.username,)).fetchone()
    conn.close()

    if not user or not password_hash.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    token = jwt.encode({"sub": user["id"], "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

    return {"access_token": token, "token_type": "bearer", "user_id": user["id"]}


@app.get("/history")
def get_history(user_id: str = Depends(verify_token)):
    conn = get_db()
    chat = conn.execute("SELECT id FROM chats WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    if not chat:
        return {"messages": []}

    mensagens = conn.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? AND role IN ('user', 'assistant') ORDER BY id",
        (chat["id"],)
    ).fetchall()
    conn.close()

    return {"messages": [{"role": m["role"], "content": m["content"]} for m in mensagens if m["content"]]}


@app.post("/chat")
async def chat(req: ChatRequest, user_id: str = Depends(verify_token)):
    conn = get_db()
    agora = datetime.now(timezone.utc).isoformat()
    metodo_confirmado = detectar_metodo_confirmado(req.message)
    compra_aprovada_nesta_requisicao = False
    intencao_criada_nesta_requisicao = False
    resposta_final = ""

    chat = conn.execute("SELECT id FROM chats WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()
    if not chat:
        chat_id = f"chat_{uuid.uuid4().hex[:8]}"
        conn.execute("INSERT INTO chats (id, user_id) VALUES (?, ?)", (chat_id, user_id))
        conn.commit()
    else:
        chat_id = chat["id"]

    conn.execute(
        "INSERT INTO messages (chat_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (chat_id, user_id, "user", req.message, agora)
    )
    conn.commit()

    historico_db = conn.execute(
        "SELECT role, content, tool_calls_json, tool_name FROM messages WHERE chat_id = ? ORDER BY id",
        (chat_id,)
    ).fetchall()

    messages_for_llm = [{"role": "system", "content": SYSTEM_PROMPT}]
    for row in historico_db:
        msg = {"role": row["role"]}
        if row["content"]: msg["content"] = row["content"]
        if row["tool_calls_json"]: msg["tool_calls"] = json.loads(row["tool_calls_json"])
        if row["tool_name"]: msg["name"] = row["tool_name"]
        messages_for_llm.append(msg)

    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server/server.py"],
        env={
            **os.environ,
            "DATABASE_PATH": DB_PATH,
            "USER_ID": user_id,
            "CHAT_ID": chat_id
        }
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()

            mcp_tools = await mcp_client.list_tools()
            ollama_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema
                    }
                } for tool in mcp_tools.tools
            ]

            while True:
                response = await ollama.chat(
                    model="qwen3:1.7b",
                    messages=messages_for_llm,
                    tools=ollama_tools
                )

                assist_msg = response["message"]
                messages_for_llm.append(assist_msg)

                if not assist_msg.get("tool_calls"):
                    resposta = assist_msg.get("content", "")
                    if resposta_afirma_aprovacao(resposta) and not compra_aprovada_nesta_requisicao:
                        if intencao_criada_nesta_requisicao:
                            resposta = (
                                "A intenção de compra foi registrada, mas a compra ainda não foi aprovada. "
                                "Confirme explicitamente se deseja pagar com Pix ou cartão."
                            )
                        else:
                            resposta = (
                                "Não foi possível confirmar uma compra aprovada pelo backend. "
                                "Nenhuma transação foi concluída."
                            )
                    resposta_final = resposta

                    conn.execute(
                        "INSERT INTO messages (chat_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                        (chat_id, user_id, "assistant", resposta, datetime.now(timezone.utc).isoformat())
                    )
                    conn.commit()
                    break

                tool_calls_dict = [t.model_dump() for t in assist_msg["tool_calls"]]

                conn.execute(
                    "INSERT INTO messages (chat_id, user_id, role, tool_calls_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (chat_id, user_id, "assistant", json.dumps(tool_calls_dict), datetime.now(timezone.utc).isoformat())
                )

                # CORREÇÃO DO DEADLOCK - SALVA NO BANCO ANTES DA TOOL DO MCP RODAR
                conn.commit()

                for tool_call in assist_msg["tool_calls"]:
                    t_name = tool_call.function.name
                    t_args = tool_call.function.arguments

                    if t_name == "realizar_compra":
                        metodo_da_tool = t_args.get("metodo_pagamento") if isinstance(t_args, dict) else None

                        if not metodo_confirmado:
                            result_text = json.dumps({
                                "status": "recusado",
                                "erro": "CONFIRMACAO_PAGAMENTO_NECESSARIA",
                                "mensagem": "A mensagem atual precisa confirmar Pix ou cartão antes da compra.",
                            }, ensure_ascii=False)
                        elif metodo_da_tool != metodo_confirmado:
                            result_text = json.dumps({
                                "status": "recusado",
                                "erro": "METODO_NAO_CONFIRMADO",
                                "mensagem": "O método enviado pela ferramenta não corresponde ao método confirmado pelo usuário.",
                            }, ensure_ascii=False)
                        else:
                            try:
                                mcp_result = await mcp_client.call_tool(t_name, t_args)
                                result_text = "".join([item.text for item in mcp_result.content if item.type == "text"])
                            except Exception:
                                # A falha também é registrada para não perder a trilha de auditoria.
                                result_text = json.dumps({
                                    "status": "recusado",
                                    "erro": "ERRO_MCP",
                                    "mensagem": "Não foi possível executar a ferramenta.",
                                }, ensure_ascii=False)
                    else:
                        try:
                            mcp_result = await mcp_client.call_tool(t_name, t_args)
                            result_text = "".join([item.text for item in mcp_result.content if item.type == "text"])
                        except Exception:
                            # A falha também é registrada para não perder a trilha de auditoria.
                            result_text = json.dumps({
                                "status": "recusado",
                                "erro": "ERRO_MCP",
                                "mensagem": "Não foi possível executar a ferramenta.",
                            }, ensure_ascii=False)

                    try:
                        resultado = json.loads(result_text)
                    except json.JSONDecodeError:
                        resultado = {}

                    if t_name == "registrar_intencao" and isinstance(resultado, dict):
                        intencao_criada_nesta_requisicao = intencao_criada_nesta_requisicao or (
                            resultado.get("status") == "pendente"
                            and bool(resultado.get("intencao_id"))
                        )

                    if t_name == "realizar_compra" and isinstance(resultado, dict):
                        compra_aprovada_nesta_requisicao = compra_aprovada_nesta_requisicao or (
                            resultado.get("status") == "aprovado"
                        )

                    registrar_auditoria(
                        conn,
                        user_id,
                        chat_id,
                        t_name,
                        t_args,
                        result_text,
                    )

                    tool_msg = {
                        "role": "tool",
                        "name": t_name,
                        "content": result_text
                    }
                    messages_for_llm.append(tool_msg)

                    conn.execute(
                        "INSERT INTO messages (chat_id, user_id, role, content, tool_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (chat_id, user_id, "tool", result_text, t_name, datetime.now(timezone.utc).isoformat())
                    )
                conn.commit()

    conn.close()
    return {"response": resposta_final}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
