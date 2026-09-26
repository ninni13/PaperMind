import { useEffect, useRef, useState } from 'react';
import type { SVGProps } from 'react';
import './App.css';
import PaperOverview from './PaperOverview';

export type Overview = {
  research_question: string | null;
  method: string | null;
  datasets: string[];
  key_results: string[];
  limitations: string[];
};

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
type Paper = { id: number; filename: string; created_at: string };
type Source = { chunk_index: number; page_number: number; similarity: number };
type SourceDetail = { chunk_index: number; page_number: number; content: string };
type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[] };
type IconName = 'book' | 'plus' | 'search' | 'file' | 'arrow' | 'close' | 'menu' | 'trash' | 'quote' | 'check';
function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    book: <><path d="M12 5v15M3 4c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    file: <><path d="M14 3H5v18h14V8Z M14 3v6h5M8 13h8M8 17h5" /></>,
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    trash: <><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7" /></>,
    quote: <><path d="M10 6H4v7h5c0 3-2 4-4 5M20 6h-6v7h5c0 3-2 4-4 5" /></>,
    check: <path d="m5 12 4 4L19 6" />,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
const prompts = [
  { title: 'Summarize this paper', question: 'What is the main contribution of this paper?' },
  { title: 'Explain the methodology', question: 'What methodology and datasets were used in this study?' },
  { title: 'Identify the limitations', question: 'What are the limitations of this study?' },
];
const paperDate = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};
const paperTitle = (name: string) => name.replace(/\.pdf$/i, '').replace(/_/g, ' ');
function App() {
  const [models, setModels] = useState<{ provider: string; ask_paper: string; overview: string } | null>(null);
  const [papers, setPapers] = useState<Paper[]>([]);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);
  const [conversations, setConversations] = useState<Record<number, Message[]>>({});
  const [question, setQuestion] = useState('');
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'ask'>('overview');
  const [uploading, setUploading] = useState(false);
  const [askingPaper, setAskingPaper] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sourceDetail, setSourceDetail] = useState<SourceDetail | null>(null);
  const [loadingSource, setLoadingSource] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const sourceRequest = useRef(0);
  const messages = selectedPaper ? conversations[selectedPaper.id] ?? [] : [];
  const asking = askingPaper === selectedPaper?.id;
  const filteredPapers = papers.filter(p => p.filename.toLowerCase().includes(search.toLowerCase()));

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/models`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Model configuration unavailable');
        return response.json();
      })
      .then(data => {
        if (!controller.signal.aborted && typeof data.provider === 'string' && typeof data.ask_paper === 'string' && typeof data.overview === 'string') setModels(data);
      })
      .catch(() => { /* Keep the model unspecified if the backend is unavailable. */ });
    return () => controller.abort();
  }, []);

  const fetchPapers = async () => {
    const response = await fetch(`${API_URL}/papers`);
    if (!response.ok) throw new Error('Could not load your library. Check that the backend is running and try again.');
    setPapers(await response.json());
    setConnected(true);
  };
  const loadLibrary = async () => {
    setLoading(true);
    setError('');
    try { await fetchPapers(); }
    catch { setConnected(false); setError('Could not load your library. Check that the backend is running and try again.'); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/papers`, { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Library unavailable');
        return response.json();
      })
      .then(data => { setPapers(data); setConnected(true); })
      .catch(() => {
        if (!controller.signal.aborted) {
          setConnected(false);
          setError('Could not load your library. Check that the backend is running and try again.');
        }
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [messages.length, asking, selectedPaper?.id, activeTab]);
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [question]);
  useEffect(() => {
    if (!mobileOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [mobileOpen]);

  const selectPaper = (paper: Paper | null) => {
    setSelectedPaper(paper); setQuestion(''); setMobileOpen(false); setActiveTab('overview');
    sourceRequest.current += 1; dialogRef.current?.close();
  };
  const handleDelete = async (paper: Paper) => {
    if (!window.confirm(`Delete “${paper.filename}”? This permanently removes the paper and its indexed content.`)) return;
    try {
      const response = await fetch(`${API_URL}/papers/${paper.id}`, { method: 'DELETE' });
      if (!response.ok) throw new Error();
      setPapers(current => current.filter(p => p.id !== paper.id));
      if (selectedPaper?.id === paper.id) selectPaper(null);
      setConversations(current => { const next = { ...current }; delete next[paper.id]; return next; });
    } catch { setError('Could not delete this paper. Please try again.'); }
  };
  const handleUpload = async (file?: File) => {
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) { setError('Please choose a PDF file.'); return; }
    setUploading(true); setError('');
    const body = new FormData(); body.append('file', file);
    try {
      const response = await fetch(`${API_URL}/papers/upload`, { method: 'POST', body });
      if (!response.ok) throw new Error();
      const data = await response.json();
      const paper = { id: data.paper_id, filename: data.filename, created_at: new Date().toISOString() };
      setPapers(current => current.some(p => p.id === paper.id) ? current : [paper, ...current]);
      setConnected(true); selectPaper(paper);
    } catch { setError('Upload failed. Check your connection and try uploading the PDF again.'); }
    finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = ''; }
  };
  const handleAsk = async () => {
    const text = question.trim();
    if (!text || !selectedPaper || askingPaper !== null) return;
    const id = selectedPaper.id;
    const append = (message: Message) => setConversations(current => ({ ...current, [id]: [...(current[id] ?? []), message] }));
    append({ role: 'user', content: text }); setQuestion(''); setAskingPaper(id);
    try {
      const response = await fetch(`${API_URL}/papers/ask`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paper_id: id, question: text }),
      });
      if (!response.ok) throw new Error();
      const data = await response.json();
      append({ role: 'assistant', content: data.answer, sources: data.sources });
    } catch { append({ role: 'assistant', content: 'I couldn’t retrieve an answer. Please check your connection and try asking again.' }); }
    finally { setAskingPaper(null); }
  };
  const handleSource = async (chunkIndex: number) => {
    if (!selectedPaper) return;
    const request = ++sourceRequest.current;
    setSourceDetail(null); setSourceError(''); setLoadingSource(true); dialogRef.current?.showModal();
    try {
      const response = await fetch(`${API_URL}/papers/${selectedPaper.id}/chunks/${chunkIndex}`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (sourceRequest.current === request) setSourceDetail(data);
    } catch { if (sourceRequest.current === request) setSourceError('This source could not be loaded. Close this panel and try again.'); }
    finally { if (sourceRequest.current === request) setLoadingSource(false); }
  };

  return (
    <div className="app">
      {mobileOpen && <button className="sidebar-scrim" aria-label="Close library" onClick={() => setMobileOpen(false)} />}
      <aside id="library-sidebar" className={`sidebar ${mobileOpen ? 'is-open' : ''}`}>
        <button className="brand" onClick={() => selectPaper(null)} aria-label="PaperMind home">
          <span className="brand-mark"><Icon name="book" /></span><strong>PaperMind</strong>
        </button>
        <button className="upload-button" onClick={() => fileInputRef.current?.click()} disabled={uploading}><Icon name="plus" />{uploading ? 'Indexing your paper…' : 'Upload PDF'}<span className="button-end">PDF</span></button>
        <input ref={fileInputRef} type="file" accept="application/pdf,.pdf" onChange={event => void handleUpload(event.target.files?.[0])} hidden />
        <div className="library-heading"><span className="section-label">Library</span><span className="count">{papers.length}</span></div>
        <label className="library-search"><Icon name="search" width="16" /><input aria-label="Search papers" placeholder="Find a paper…" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <nav className="paper-list" aria-label="Paper library" aria-busy={loading}>
          {loading ? <div className="library-placeholder">Loading your library…</div> : filteredPapers.length ? filteredPapers.map(paper => (
            <div className={`paper-item ${selectedPaper?.id === paper.id ? 'selected' : ''}`} key={paper.id}>
              <button className="paper-select" onClick={() => selectPaper(paper)} aria-current={selectedPaper?.id === paper.id ? 'page' : undefined} title={paper.filename}>
                <span className="document-icon"><Icon name="file" /></span><span className="paper-info"><span className="paper-name">{paperTitle(paper.filename)}</span><small>PDF document</small></span>
              </button>
              <button className="paper-delete" aria-label={`Delete ${paper.filename}`} onClick={() => void handleDelete(paper)} disabled={askingPaper === paper.id}><Icon name="trash" width="15" /></button>
            </div>
          )) : <div className="library-placeholder">{search ? 'No papers match your search.' : 'No papers yet. Upload a PDF to get started.'}</div>}
        </nav>
        <div className="sidebar-footer"><span className={`status-dot ${connected ? '' : 'offline'}`} />{loading ? 'Connecting…' : connected ? 'Connected to your library' : 'Library unavailable'}<span className="version">v0.1</span></div>
      </aside>
      <main className="workspace">
        <header className="workspace-header"><div className="breadcrumb"><button className="mobile-toggle icon-button" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Toggle library" aria-expanded={mobileOpen} aria-controls="library-sidebar"><Icon name="menu" /></button><Icon name="book" width="17" /><button onClick={() => selectPaper(null)}>Workspace</button><span>/</span><span>{selectedPaper ? (activeTab === 'overview' ? 'Overview' : 'Ask Paper') : 'Library'}</span></div>
          {selectedPaper && <span className="model-label" title="Current model used for new requests. Previously saved overviews may have used a different model.">
            <span>Current model</span><strong>{models ? `${models.provider} · ${activeTab === 'overview' ? models.overview : models.ask_paper}` : 'Unavailable'}</strong>
          </span>}
        </header>
        {error && <div className="error-banner" role="alert"><span>{error}</span>{!connected && <button onClick={() => void loadLibrary()} disabled={loading}>Retry</button>}<button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><Icon name="close" width="16" /></button></div>}
        {uploading && <div className="upload-progress" role="status"><span className="spinner" />Reading and indexing your PDF. This may take a moment.</div>}
        {selectedPaper ? <>
          <div className="paper-header"><span className="paper-header-icon"><Icon name="file" /></span><div><h1 title={selectedPaper.filename}>{selectedPaper.filename}</h1><p className="section-label">Research paper</p></div><span className="indexed-badge"><Icon name="check" width="13" />Indexed</span></div>
          <nav className="paper-tabs" aria-label="Paper views">
            <button aria-pressed={activeTab === 'overview'} aria-controls="overview-panel" onClick={() => setActiveTab('overview')}>Overview</button>
            <button aria-pressed={activeTab === 'ask'} aria-controls="ask-panel" onClick={() => setActiveTab('ask')}>Ask Paper</button>
          </nav>
          <div id="overview-panel" className="overview-panel" hidden={activeTab !== 'overview'}>
            <PaperOverview key={selectedPaper.id} paperId={selectedPaper.id} apiUrl={API_URL} />
          </div>
          <div id="ask-panel" className="ask-panel" hidden={activeTab !== 'ask'}>
          <section className="chat" aria-label="Paper conversation">
            {messages.length === 0 ? (
              <div className="welcome">
                <h2>Ask about this paper</h2>
                <p>Answers include references to the original text.</p>
                <div className="suggestions">
                  {prompts.map(prompt => (
                    <button key={prompt.title} onClick={() => { setQuestion(prompt.question); textareaRef.current?.focus(); }}>
                      <span>{prompt.title}</span><Icon name="arrow" width="16" />
                    </button>
                  ))}
                </div>
              </div>
            ) : <div className="messages" role="log" aria-label="Messages">{messages.map((message, index) => <article key={index} className={`message ${message.role}`}><div className="message-role">{message.role === 'assistant' && <span className="assistant-avatar"><Icon name="book" width="15" /></span>}{message.role === 'user' ? 'You' : 'PaperMind'}</div><div className="message-content">{message.content}</div>{!!message.sources?.length && <div className="sources"><span className="source-title"><Icon name="quote" width="14" />Sources</span>{Array.from(new Map(message.sources.map(source => [source.page_number, source])).values()).map(source => <button className="source-chip" key={source.page_number} onClick={() => void handleSource(source.chunk_index)}><Icon name="file" width="13" />Page {source.page_number}<Icon name="arrow" width="12" /></button>)}</div>}</article>)}{asking && <div className="thinking" role="status"><span className="spinner" />Reading the paper and finding relevant sources…</div>}</div>}
            <div ref={endRef} />
          </section>
          <div className="composer-wrapper"><form className="composer" onSubmit={event => { event.preventDefault(); void handleAsk(); }}><label className="sr-only" htmlFor="question">Question about this paper</label><textarea id="question" ref={textareaRef} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void handleAsk(); } }} placeholder="Ask a question about this paper…" rows={1} /><div className="composer-bottom"><span><Icon name="file" width="13" /> Grounded in this paper</span><button className="send-button" type="submit" disabled={!question.trim() || askingPaper !== null} aria-label="Send question"><Icon name="arrow" /></button></div></form><p className="composer-hint">AI can make mistakes. Check the sources. <span>Enter to send · Shift + Enter for a new line</span></p></div>
          </div>
        </> : (
          <section className="home">
            <div className="home-heading">
              <div><h1>Papers</h1><p>Your research library. Select a paper to start a conversation.</p></div>
              <button className="primary-button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                <Icon name="plus" width="16" />{uploading ? 'Indexing…' : 'Upload PDF'}
              </button>
            </div>
            <div className="library-toolbar">
              <span>All papers <span className="count">{papers.length}</span></span>
              <label className="table-search"><Icon name="search" width="16" /><input aria-label="Filter library" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name…" /></label>
            </div>
            {loading ? <div className="library-empty" role="status"><span className="spinner" /><p>Loading papers…</p></div> : papers.length > 0 ? (
              <div className="paper-table">
                <div className="table-heading"><span>Name</span><span>Added</span><span className="sr-only">Open</span></div>
                {filteredPapers.map(paper => (
                  <button className="table-row" key={paper.id} onClick={() => selectPaper(paper)}>
                    <span className="table-paper"><Icon name="file" width="19" /><span><strong>{paperTitle(paper.filename)}</strong><small>PDF</small></span></span>
                    <time dateTime={paper.created_at}>{paperDate(paper.created_at)}</time>
                    <Icon name="arrow" width="16" />
                  </button>
                ))}
                {filteredPapers.length === 0 && <p className="no-results">No papers match “{search}”.</p>}
              </div>
            ) : (
              <div className="library-empty">
                <Icon name="file" width="28" height="28" />
                <h2>{connected ? 'No papers yet' : 'Library unavailable'}</h2>
                <p>{connected ? 'Upload a PDF to read, ask questions, and check sources.' : 'Connect to the backend to load your papers.'}</p>
                {connected && <button className="text-button" onClick={() => fileInputRef.current?.click()} disabled={uploading}>Choose a PDF <Icon name="arrow" width="15" /></button>}
              </div>
            )}
          </section>
        )}

      </main>
      <dialog ref={dialogRef} className="source-dialog" aria-label="Source text" onClick={event => { if (event.target === event.currentTarget) dialogRef.current?.close(); }}><aside className="source-panel"><div className="source-header"><div><p className="section-label">Source</p><h2>{loadingSource ? 'Finding your source…' : sourceDetail ? `Page ${sourceDetail.page_number}` : 'Source unavailable'}</h2></div><button autoFocus className="icon-button" aria-label="Close source" onClick={() => dialogRef.current?.close()}><Icon name="close" /></button></div><p className="source-paper-name">{selectedPaper?.filename}</p>{loadingSource ? <div className="thinking" role="status"><span className="spinner" />Loading source…</div> : sourceError ? <p role="alert">{sourceError}</p> : <div className="source-content">{sourceDetail?.content}</div>}</aside></dialog>
    </div>
  );
}
export default App;
