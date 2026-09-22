import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from mcp.server import MCPServer

mcp = MCPServer("Pagamentos MCP")

# Variáveis de ambiente que o nosso backend (FastAPI) vai injetar
DB_PATH = os.environ.get("DATABASE_PATH", "data/app.db")
USER_ID = os.environ.get("USER_ID", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

def conectar():
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    return conn

def recusado(erro: str, mensagem: str):
    return {
        "status": "recusado",
        "erro": erro,
        "mensagem": mensagem
    }

@mcp.tool()
def listar_catalogo(categoria: str | None = None) -> dict:
    """Lista os produtos disponíveis no catálogo."""
    try:
        conn = conectar()
        if categoria:
            produtos = conn.execute(
                "SELECT * FROM produtos WHERE categoria = ? AND estoque > 0",
                (categoria,)
            ).fetchall()
        else:
            produtos = conn.execute(
                "SELECT * FROM produtos WHERE estoque > 0"
            ).fetchall()

        return {
            "produtos": [
                {
                    "id": p["id"],
                    "nome": p["nome"],
                    "preco": p["preco_centavos"] / 100,
                    "moeda": p["moeda"],
                    "estoque": p["estoque"],
                }
                for p in produtos
            ]
        }
    except Exception as e:
        return recusado("ERRO_CATALOGO", str(e))
    finally:
        if 'conn' in locals():
            conn.close()

@mcp.tool()
def registrar_intencao(produto_id: str, quantidade: int) -> dict:
    """Registra uma intenção de compra sem movimentar dinheiro."""
    # Força a conversão para garantir que o LLM não quebre a validação com strings
    try:
        quantidade = int(quantidade)
    except ValueError:
        return recusado("QUANTIDADE_INVALIDA", "A quantidade fornecida não é um número válido.")

    if quantidade <= 0:
        return recusado("QUANTIDADE_INVALIDA", "Quantidade deve ser maior que zero.")

    try:
        conn = conectar()
        produto = conn.execute("SELECT * FROM produtos WHERE id = ?", (produto_id,)).fetchone()

        if not produto:
            return recusado("PRODUTO_INVALIDO", "Produto não encontrado.")

        if quantidade > produto["estoque"]:
            return recusado("ESTOQUE_INSUFICIENTE", "Estoque insuficiente para a quantidade.")

        # O preço real SEMPRE vem do banco, não do modelo
        valor = produto["preco_centavos"] * quantidade
        intencao_id = f"int_{uuid.uuid4().hex[:8]}"
        agora = datetime.now(timezone.utc)
        expira = agora + timedelta(minutes=10)

        conn.execute(
            """
            INSERT INTO intencoes
            (id, user_id, chat_id, produto_id, quantidade, valor_total_centavos, moeda, status, expira_em, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (intencao_id, USER_ID, CHAT_ID, produto_id, quantidade, valor, produto["moeda"], "pendente", expira.isoformat(), agora.isoformat())
        )

        conn.commit()

        return {
            "intencao_id": intencao_id,
            "produto_id": produto_id,
            "quantidade": quantidade,
            "valor_total": valor / 100,
            "moeda": produto["moeda"],
            "status": "pendente",
            "expira_em": expira.isoformat()
        }
    except Exception as e:
        return recusado("ERRO_INTERNO", f"Falha no servidor ao registrar intenção: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

@mcp.tool()
def realizar_compra(intencao_id: str, metodo_pagamento: Literal["cartao", "pix"]) -> dict:
    """Realiza uma compra usando uma intenção previamente registrada e confirmada."""
    try:
        conn = conectar()
        conn.execute("BEGIN IMMEDIATE")

        intencao = conn.execute("SELECT * FROM intencoes WHERE id = ?", (intencao_id,)).fetchone()

        if not intencao or intencao["user_id"] != USER_ID or intencao["chat_id"] != CHAT_ID:
            return recusado("INTENCAO_INVALIDA", "A intenção informada não é válida para este usuário/sessão.")

        emitida = conn.execute(
            """
            SELECT 1 FROM tool_results
            WHERE user_id = ? AND chat_id = ? AND tool_name = 'registrar_intencao' AND intencao_id = ?
            LIMIT 1
            """,
            (USER_ID, CHAT_ID, intencao_id)
        ).fetchone()

        if not emitida:
            return recusado("INTENCAO_NAO_AUTORIZADA", "A intenção não foi registrada nesta conversa.")

        if intencao["status"] == "paga":
            return recusado("INTENCAO_JA_PAGA", "Essa intenção já foi utilizada.")

        agora = datetime.now(timezone.utc)
        expira = datetime.fromisoformat(intencao["expira_em"])
        if agora > expira:
            return recusado("INTENCAO_EXPIRADA", "Essa intenção de compra expirou.")

        usuario = conn.execute("SELECT limite_centavos, gasto_centavos FROM users WHERE id = ?", (USER_ID,)).fetchone()
        disponivel = usuario["limite_centavos"] - usuario["gasto_centavos"]
        valor = intencao["valor_total_centavos"]

        if valor > disponivel:
            return recusado("LIMITE_EXCEDIDO", "A compra ultrapassa o limite disponível.")

        transacao_id = f"tx_{uuid.uuid4().hex[:8]}"

        conn.execute(
            """
            INSERT INTO transacoes
            (id, user_id, intencao_id, valor_centavos, metodo_pagamento, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (transacao_id, USER_ID, intencao_id, valor, metodo_pagamento, agora.isoformat())
        )

        conn.execute("UPDATE intencoes SET status = 'paga' WHERE id = ?", (intencao_id,))
        conn.execute("UPDATE users SET gasto_centavos = gasto_centavos + ? WHERE id = ?", (valor, USER_ID))
        conn.execute("UPDATE produtos SET estoque = estoque - ? WHERE id = ?", (intencao["quantidade"], intencao["produto_id"]))
        conn.commit()

        return {
            "status": "aprovado",
            "transacao_id": transacao_id,
            "intencao_id": intencao_id,
            "valor": valor / 100,
            "metodo_pagamento": metodo_pagamento,
            "limite_restante": (disponivel - valor) / 100,
            "data": agora.isoformat()
        }
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return recusado("ERRO_INTERNO", f"Falha no servidor ao processar pagamento: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

@mcp.tool()
def consultar_historico_compras(limite: int = 3) -> dict:
    """Consulta o histórico de compras concluidas do usuário autenticado."""
    try:
        if limite is None:
            limite = 3
        limite = int(limite)
    except (TypeError, ValueError):
        return recusado("LIMITE_INVALIDO", "O limite informado não é um número válido.")

    if limite <= 0:
        limite = 3

    limite = min(limite, 10)

    try:
        conn = conectar()
        compras = conn.execute(
            """
            SELECT
                transacoes.id,
                transacoes.user_id,
                transacoes.valor_centavos,
                transacoes.metodo_pagamento,
                transacoes.created_at,
                intencoes.quantidade,
                produtos.nome,
                produtos.id AS produto_id,
                intencoes.moeda
            FROM transacoes
            INNER JOIN intencoes ON intencoes.id = transacoes.intencao_id
            INNER JOIN produtos ON produtos.id = intencoes.produto_id
            WHERE transacoes.user_id = ?
            ORDER BY datetime(transacoes.created_at) DESC
            LIMIT ?
            """,
            (USER_ID, limite)
        ).fetchall()

        return {
            "compras": [
                {
                    "id": c["id"],
                    "produto": c["nome"],
                    "produto_id": c["produto_id"],
                    "quantidade": c["quantidade"],
                    "valor": c["valor_centavos"] / 100,
                    "moeda": c["moeda"],
                    "metodo_pagamento": c["metodo_pagamento"],
                    "data": c["created_at"],
                }
                for c in compras
            ]
        }
    except Exception as e:
        return recusado("ERRO_HISTORICO_COMPRAS", f"Falha no servidor ao consultar histórico: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    mcp.run()
