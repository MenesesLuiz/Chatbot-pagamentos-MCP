import { useState, useEffect, useRef } from 'react';
import { login, getHistory, sendMessage } from './api';
import './App.css';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    if (token) {
      getHistory(token).then(data => setMessages(data.messages || []));
    }
  }, [token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const data = await login(username, password);
      setToken(data.access_token);
      localStorage.setItem('token', data.access_token);
    } catch (error) {
      alert('Login falhou. Tente cliente_normal com senha 123456');
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setLoading(true);

    try {
      const data = await sendMessage(userMsg, token);
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
    } catch (error) {
      alert('Erro ao comunicar com o backend MCP.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken('');
    localStorage.removeItem('token');
    setMessages([]);
  };

  // Função para converter **texto** em negrito no React
  const formatMessage = (text) => {
    if (!text) return "";
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={index}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  if (!token) {
    return (
      <main className="login-page">
        <section className="login-container">
          <div className="brand-mark" aria-hidden="true">🛒</div>
          <p className="eyebrow">CHATPAY · PAGAMENTOS COM MCP</p>
          <h1>Seu assistente de compras</h1>
          <p className="login-copy">
            Consulte o catálogo e acompanhe suas compras com segurança.
          </p>

        <form onSubmit={handleLogin}>
          <label className="field">
            <span>Usuário</span>
            <input
              placeholder="Digite seu usuário"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="field">
            <span>Senha</span>
            <input
              type="password"
              placeholder="Digite sua senha"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button className="primary-button" type="submit">
            <span>Entrar no ChatPay</span>
            <span aria-hidden="true">→</span>
          </button>
        </form>

          <div className="demo-card">
            <span className="demo-card-title">Acesso para demonstração</span>
            <p><code>cliente_normal</code> · limite alto</p>
            <p><code>cliente_baixo</code> · limite baixo</p>
            <small>Senha para ambos: <code>123456</code></small>
          </div>
          <p className="local-note">Ambiente local de demonstração</p>
        </section>
      </main>
    );
  }

  return (
    <main className="chat-page">
      <div className="chat-container">
        <header className="header">
          <div className="brand-lockup">
            <div className="brand-mark brand-mark-small" aria-hidden="true">🛒</div>
            <div>
              <h2>ChatPay</h2>
              <span className="status-label"><i /> Assistente online</span>
            </div>
          </div>
          <div className="header-actions">
            <span className="session-label">Sessão protegida</span>
            <button className="logout-button" onClick={handleLogout}>Sair</button>
          </div>
        </header>

        <div className="messages">
          {messages.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon" aria-hidden="true">✦</div>
              <h3>Como posso ajudar?</h3>
              <p>Peça o catálogo, escolha um produto ou acompanhe uma compra.</p>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`message ${m.role}`}>
              <strong>{m.role === 'user' ? 'Você' : 'Agente'}</strong>
              <p>{formatMessage(m.content)}</p>
            </div>
          ))}

        {loading && (
          <div className="message assistant">
            <span className="loading-indicator"><i /><i /><i /></span>
            <em>Processando ferramentas MCP...</em>
          </div>
        )}
          <div ref={chatEndRef} />
        </div>

        <form className="input-area" onSubmit={handleSend}>
          <div className="compose-box">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="Escreva uma mensagem..."
              aria-label="Mensagem para o assistente"
              disabled={loading}
            />
            <button className="send-button" type="submit" disabled={loading} aria-label="Enviar mensagem">
              <span aria-hidden="true">↑</span>
            </button>
          </div>
          <span className="input-note">As compras são simuladas neste ambiente local.</span>
        </form>
      </div>
    </main>
  );
}

export default App;
