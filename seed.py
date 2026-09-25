import sqlite3
import os
import sys
from pathlib import Path
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Configura o gerador de hash de senhas
password_hash = PasswordHash((Argon2Hasher(),))

PROJECT_ROOT = Path(__file__).resolve().parent
configured_db_path = Path(os.getenv("DATABASE_PATH", "data/app.db"))
DB_PATH = configured_db_path if configured_db_path.is_absolute() else PROJECT_ROOT / configured_db_path

def seed(reset=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        if not reset:
            raise RuntimeError(
                f"O banco já existe em {DB_PATH}. Use 'python seed.py --reset' para recriá-lo."
            )
        os.remove(DB_PATH)

    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()

    # 1. Tabela de Usuários
    c.execute('''CREATE TABLE users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        limite_centavos INTEGER NOT NULL,
        gasto_centavos INTEGER NOT NULL DEFAULT 0
    )''')

    # 2. Tabela de Produtos
    c.execute('''CREATE TABLE produtos (
        id TEXT PRIMARY KEY,
        nome TEXT NOT NULL,
        categoria TEXT NOT NULL,
        preco_centavos INTEGER NOT NULL,
        moeda TEXT NOT NULL DEFAULT 'BRL',
        estoque INTEGER NOT NULL
    )''')

    # 3. Tabela de Chats
    c.execute('''CREATE TABLE chats (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL
    )''')

    # 4. Tabela de Mensagens do Histórico
    c.execute('''CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT,
        tool_name TEXT,
        tool_calls_json TEXT,
        created_at TEXT NOT NULL
    )''')

    # 5. Tabela de Intenções de Compra (Carrinho temporário)
    c.execute('''CREATE TABLE intencoes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        produto_id TEXT NOT NULL,
        quantidade INTEGER NOT NULL,
        valor_total_centavos INTEGER NOT NULL,
        moeda TEXT NOT NULL,
        status TEXT NOT NULL,
        expira_em TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 6. Tabela de resultados das tools (auditoria de todas as chamadas MCP)
    c.execute('''CREATE TABLE tool_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        intencao_id TEXT,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 7. Tabela de Transações (Compras Efetivadas)
    c.execute('''CREATE TABLE transacoes (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        intencao_id TEXT NOT NULL UNIQUE,
        valor_centavos INTEGER NOT NULL,
        metodo_pagamento TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # ==========================================
    # INSERINDO DADOS DE TESTE
    # ==========================================

    # Produtos
    produtos = [
        ("prod_001", "Mouse Gamer", "perifericos", 12990, 15),
        ("prod_002", "Teclado Mecânico", "perifericos", 34990, 8),
        ("prod_003", "Fone Bluetooth", "audio", 24990, 12),
        ("prod_004", "Notebook", "computadores", 459990, 3)
    ]
    c.executemany(
        "INSERT INTO produtos (id, nome, categoria, preco_centavos, estoque) VALUES (?, ?, ?, ?, ?)",
        produtos
    )

    # Usuários
    senha_padrao = password_hash.hash("123456")
    usuarios = [
        ("user_normal", "cliente_normal", senha_padrao, 200000), # Limite R$ 2.000,00
        ("user_baixo", "cliente_baixo", senha_padrao, 10000)     # Limite R$ 100,00
    ]
    c.executemany(
        "INSERT INTO users (id, username, password_hash, limite_centavos) VALUES (?, ?, ?, ?)",
        usuarios
    )

    conn.commit()
    conn.close()
    print("✅ Banco de dados 'app.db' criado com sucesso na pasta 'data'!")
    print("✅ Produtos e usuários de teste inseridos.")

if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
