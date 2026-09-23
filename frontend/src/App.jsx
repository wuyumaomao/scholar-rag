import { useState, useEffect, useRef, useCallback } from 'react';
import { Upload, Settings, ChevronLeft } from 'lucide-react';
import Sidebar from './components/Sidebar';
import ChatMessages from './components/ChatMessages';
import ChatInput from './components/ChatInput';
import FileUpload from './components/FileUpload';
import SettingsPanel from './components/SettingsPanel';
import { fetchSessions, fetchHistory, deleteSession, fetchFiles, streamChat } from './api';

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [files, setFiles] = useState([]);
  const [paperId, setPaperId] = useState('');
  const [currentId, setCurrentId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [panel, setPanel] = useState(null);
  const cancelRef = useRef(null);
  const bottomRef = useRef(null);

  const loadSessions = useCallback(() => {
    fetchSessions().then(setSessions).catch(() => {});
  }, []);

  const loadFiles = useCallback(() => {
    fetchFiles().then((items) => {
      setFiles(items);
      setPaperId((current) => {
        if (current && !items.some((file) => file.paper_id === current)) return '';
        return current || (items.length === 1 ? items[0].paper_id : '');
      });
    }).catch(() => {});
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);
  useEffect(() => { loadFiles(); }, [loadFiles]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const selectSession = async (id) => {
    setCurrentId(id);
    setPanel(null);
    try {
      const data = await fetchHistory(id);
      setMessages((data.messages || []).map((m) => ({
        ...m,
        citations: m.citations || [],
        finalized: true,
      })));
    } catch {
      setMessages([]);
    }
  };

  const newChat = () => {
    setCurrentId(null);
    setMessages([]);
    setPanel(null);
  };

  const handleDelete = async (id) => {
    await deleteSession(id);
    if (currentId === id) newChat();
    loadSessions();
  };

  const handleSend = (query) => {
    if (cancelRef.current) cancelRef.current();

    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setLoading(true);

    let sessionId = currentId;
    let answer = '';
    let citations = [];

    const cancel = streamChat(query, sessionId, paperId, (evt) => {
      switch (evt.type) {
        case 'session_id':
          sessionId = evt.data;
          setCurrentId(evt.data);
          break;
        case 'answer':
          answer = evt.data;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === 'assistant' && !last.finalized) {
              return prev.slice(0, -1).concat({ ...last, content: answer });
            }
            return [...prev, { role: 'assistant', content: answer, citations: [], finalized: false }];
          });
          break;
        case 'citations':
          citations = evt.data;
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === 'assistant'
                ? { ...m, citations, finalized: true }
                : m
            )
          );
          break;
        case 'done':
          setLoading(false);
          loadSessions();
          break;
        case 'error':
          setMessages((prev) => [
            ...prev,
            { role: 'assistant', content: `Error: ${evt.data}`, citations: [] },
          ]);
          setLoading(false);
          break;
      }
    });

    cancelRef.current = cancel;
  };

  const togglePanel = (name) => setPanel((prev) => (prev === name ? null : name));
  const handleFilesChanged = () => {
    loadFiles();
    loadSessions();
  };

  return (
    <div className="flex h-screen bg-white">
      <Sidebar
        sessions={sessions}
        currentId={currentId}
        onSelect={selectSession}
        onNew={newChat}
        onDelete={handleDelete}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-white">
          <h1 className="text-sm font-medium text-gray-700">Scholar RAG</h1>
          <div className="flex items-center gap-2">
            <label htmlFor="paper-scope" className="sr-only">Search scope</label>
            <select
              id="paper-scope"
              value={paperId}
              onChange={(e) => setPaperId(e.target.value)}
              className="max-w-44 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 outline-none focus:border-gray-400"
              title="Limit answers to one uploaded paper"
            >
              <option value="">All papers</option>
              {files.map((file) => (
                <option key={file.file_id} value={file.paper_id}>{file.filename}</option>
              ))}
            </select>
            <button
              onClick={() => togglePanel('upload')}
              className={`p-2 rounded-lg transition-colors ${panel === 'upload' ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
            >
              <Upload size={16} className="text-gray-500" />
            </button>
            <button
              onClick={() => togglePanel('settings')}
              className={`p-2 rounded-lg transition-colors ${panel === 'settings' ? 'bg-gray-100' : 'hover:bg-gray-50'}`}
            >
              <Settings size={16} className="text-gray-500" />
            </button>
          </div>
        </header>

        <div className="flex flex-1 min-h-0">
          <div className="flex-1 flex flex-col min-w-0">
            <ChatMessages messages={messages} loading={loading} />
            <div ref={bottomRef} />
            <ChatInput onSend={handleSend} disabled={loading} />
          </div>

          {panel && (
            <div className="w-72 border-l border-gray-200 bg-white overflow-y-auto">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  {panel === 'upload' ? 'Upload Files' : 'Settings'}
                </span>
                <button onClick={() => setPanel(null)} className="p-1 rounded hover:bg-gray-100">
                  <ChevronLeft size={14} className="text-gray-400" />
                </button>
              </div>
              {panel === 'upload' && <FileUpload onUploaded={handleFilesChanged} />}
              {panel === 'settings' && <SettingsPanel onFilesChanged={handleFilesChanged} />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
