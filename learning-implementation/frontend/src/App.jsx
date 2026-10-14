import { useEffect, useRef, useState } from "react";
import SourceMessage from "./SourceMessage.jsx";

import {
  deleteSession,
  getFiles,
  getHistory,
  getSessions,
  streamChat,
  uploadFile,
} from "./api.js";

function Message({ message }) {
  const isUser = message.role === "user";

  return (
    <article className={`message-row ${isUser ? "message-row-user" : ""}`}>
      {!isUser && <div className="assistant-avatar" aria-hidden="true">S</div>}
      <div className={`message-bubble ${isUser ? "message-user" : "message-assistant"}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <SourceMessage message={message} />
        )}
      </div>
    </article>
  );
}

export default function App() {
  const [files, setFiles] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedFileId, setSelectedFileId] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileInputRef = useRef(null);
  const bottomRef = useRef(null);
  const conversationVersionRef = useRef(0);

  async function refreshFiles() {
    const items = await getFiles();
    setFiles(items);
    setSelectedFileId((current) => {
      if (current && items.some((file) => file.file_id === current)) return current;
      return items[0]?.file_id ?? "";
    });
  }

  async function refreshSessions() {
    setSessions(await getSessions());
  }

  useEffect(() => {
    Promise.all([refreshFiles(), refreshSessions()]).catch((requestError) => {
      setError(requestError.message);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setError("");
    setNotice("");
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件。");
      return;
    }

    setUploading(true);
    try {
      const uploaded = await uploadFile(file);
      await refreshFiles();
      setSelectedFileId(uploaded.file_id);
      setNotice(`已上传并建立索引：${uploaded.filename}`);
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleSend(event) {
    event.preventDefault();
    const question = query.trim();
    if (!question || !selectedFileId || loading || historyLoading) return;

    setError("");
    setNotice("");
    setQuery("");
    const requestConversationVersion = conversationVersionRef.current;
    const assistantMessageId = `streaming-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setMessages((current) => [
      ...current,
      { role: "user", content: question },
      { id: assistantMessageId, role: "assistant", content: "", sources: [] },
    ]);
    setLoading(true);

    try {
      const response = await streamChat({
        file_id: selectedFileId,
        query: question,
        session_id: sessionId,
        onSources: (sources) => {
          setMessages((current) => current.map((message) => (
            message.id === assistantMessageId ? { ...message, sources } : message
          )));
        },
        onToken: (text) => {
          setMessages((current) => current.map((message) => (
            message.id === assistantMessageId
              ? { ...message, content: message.content + text }
              : message
          )));
        },
      });
      if (conversationVersionRef.current === requestConversationVersion) {
        setSessionId(response.session_id);
      }
      await refreshSessions();
    } catch (chatError) {
      if (conversationVersionRef.current === requestConversationVersion) {
        setError(chatError.message);
        setMessages((current) => current.filter((message) => (
          message.id !== assistantMessageId || message.content
        )));
      }
    } finally {
      setLoading(false);
    }
  }

  async function selectSession(id) {
    const conversationVersion = ++conversationVersionRef.current;
    setError("");
    setHistoryLoading(true);
    setSessionId(null);
    setMessages([]);
    try {
      const history = await getHistory(id);
      if (conversationVersionRef.current !== conversationVersion) return;
      setSessionId(id);
      setMessages(history);
    } catch (historyError) {
      if (conversationVersionRef.current === conversationVersion) {
        setError(historyError.message);
      }
    } finally {
      if (conversationVersionRef.current === conversationVersion) {
        setHistoryLoading(false);
      }
    }
  }

  function startNewChat() {
    conversationVersionRef.current += 1;
    setHistoryLoading(false);
    setSessionId(null);
    setMessages([]);
    setError("");
    setNotice("");
  }

  async function removeSession(event, id) {
    event.stopPropagation();
    setError("");
    try {
      await deleteSession(id);
      if (sessionId === id) startNewChat();
      await refreshSessions();
    } catch (deleteError) {
      setError(deleteError.message);
    }
  }

  const activeFile = files.find((file) => file.file_id === selectedFileId);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark">S</div>
          <div>
            <strong>Scholar RAG</strong>
            <span>学习版</span>
          </div>
        </div>

        <button className="new-chat-button" onClick={startNewChat}>
          <span aria-hidden="true">＋</span> 新建对话
        </button>

        <div className="sidebar-heading">最近对话</div>
        <nav className="session-list" aria-label="最近对话">
          {sessions.length === 0 ? (
            <p className="sidebar-empty">还没有对话</p>
          ) : sessions.map((session) => (
            <div
              className={`session-item ${sessionId === session.session_id ? "session-item-active" : ""}`}
              key={session.session_id}
            >
              <button onClick={() => selectSession(session.session_id)}>
                {session.title || "新对话"}
              </button>
              <button
                className="session-delete"
                aria-label={`删除对话 ${session.title || "新对话"}`}
                title="删除对话"
                onClick={(event) => removeSession(event, session.session_id)}
              >
                ×
              </button>
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" /> 后端 API · 8100
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <div>
            <h1>论文问答</h1>
            <p>上传论文，然后用自然语言提问</p>
          </div>
          <div className="file-controls">
            <label className="file-select-label" htmlFor="paper-select">当前论文</label>
            <select
              id="paper-select"
              value={selectedFileId}
              onChange={(event) => setSelectedFileId(event.target.value)}
              disabled={files.length === 0}
            >
              {files.length === 0 ? (
                <option value="">尚未上传论文</option>
              ) : files.map((file) => (
                <option key={file.file_id} value={file.file_id}>{file.filename}</option>
              ))}
            </select>
            <input
              ref={fileInputRef}
              className="visually-hidden"
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleUpload}
            />
            <button
              className="upload-button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? "解析并索引中…" : "上传 PDF"}
            </button>
          </div>
        </header>

        {error && <div className="feedback feedback-error" role="alert">{error}</div>}
        {notice && <div className="feedback feedback-notice" role="status">{notice}</div>}

        <section className="conversation" aria-label="聊天记录">
          {messages.length === 0 && !loading ? (
            <div className="welcome-card">
              <div className="welcome-icon">✦</div>
              <h2>从论文中寻找答案</h2>
              <p>
                {activeFile
                  ? `当前选择：${activeFile.filename}`
                  : "先上传一篇 PDF 论文，后端会解析并建立检索索引。"}
              </p>
              {!activeFile && (
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                  选择 PDF 文件
                </button>
              )}
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message, index) => (
                <Message key={message.id || `${message.role}-${index}`} message={message} />
              ))}
              {loading && (
                <div className="thinking-indicator" role="status">
                  <span /><span /><span /> 正在检索论文并生成回答…
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </section>

        <footer className="composer-area">
          <form className="composer" onSubmit={handleSend}>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form.requestSubmit();
                }
              }}
              placeholder={activeFile ? "向这篇论文提问…（Enter 发送，Shift+Enter 换行）" : "请先上传并选择一篇论文"}
              rows={2}
              disabled={!activeFile || loading || historyLoading}
            />
            <button type="submit" disabled={!activeFile || !query.trim() || loading || historyLoading}>
              {loading ? "生成中" : historyLoading ? "加载会话中" : "发送"}
            </button>
          </form>
          <p className="composer-hint">
            回答由检索到的论文内容生成；请检查回答中的页码和来源引用。
          </p>
        </footer>
      </section>
    </main>
  );
}
