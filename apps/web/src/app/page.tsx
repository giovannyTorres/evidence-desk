"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  consumeEvents,
  type Citation,
  type Config,
  type Conversation,
  type Document,
  type Message,
  type Scenario,
  type User,
} from "@/lib/api";

type IconName =
  | "book"
  | "spark"
  | "arrow"
  | "plus"
  | "upload"
  | "file"
  | "link"
  | "close"
  | "check"
  | "search"
  | "logout"
  | "chat"
  | "shield"
  | "refresh"
  | "trash";
function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    book: (
      <>
        <path d="M4 4h7a3 3 0 0 1 3 3v14a4 4 0 0 0-3-2H4z" />
        <path d="M14 7a3 3 0 0 1 3-3h3v15h-3a4 4 0 0 0-3 2" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4z" />
        <path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5z" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14M13 6l6 6-6 6" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    upload: (
      <>
        <path d="M12 15V3m-5 5 5-5 5 5M4 15v5h16v-5" />
      </>
    ),
    file: (
      <>
        <path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h5" />
      </>
    ),
    link: (
      <>
        <path d="m9 15 6-6M8 16l-1 1a3.5 3.5 0 0 1-5-5l5-5a3.5 3.5 0 0 1 5 0m0 10a3.5 3.5 0 0 0 5 0l5-5a3.5 3.5 0 0 0-5-5l-1 1" />
      </>
    ),
    close: <path d="m6 6 12 12M18 6 6 18" />,
    check: <path d="m5 12 4 4L19 6" />,
    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="m15 15 5 5" />
      </>
    ),
    logout: (
      <>
        <path d="M9 4H4v16h5m0-8h12m-5-5 5 5-5 5" />
      </>
    ),
    chat: <path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5" />,
    shield: (
      <>
        <path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 10a8 8 0 1 0-2 8M20 4v6h-6" />
      </>
    ),
    trash: (
      <>
        <path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "brand-small" : ""}`}>
      <span className="brand-mark">
        <Icon name="book" size={small ? 20 : 25} />
      </span>
      <span>
        evidence<span className="brand-light">desk</span>
        <span className="brand-dot">.</span>
      </span>
    </div>
  );
}
function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

export default function Home() {
  const [config, setConfig] = useState<Config | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [source, setSource] = useState<Citation | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [question, setQuestion] = useState("");
  const [tab, setTab] = useState<"workspace" | "library">("workspace");
  const [query, setQuery] = useState("");
  const [uploadBusy, setUploadBusy] = useState(false);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [libraryBusy, setLibraryBusy] = useState(false);
  const [conversationBusy, setConversationBusy] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const messageSequence = useRef(0);

  const refreshData = useCallback(async () => {
    const [docs, presets, chats] = await Promise.all([
      api<Document[]>("/documents"),
      api<Scenario[]>("/scenarios"),
      api<Conversation[]>("/conversations"),
    ]);
    setDocuments(docs);
    setScenarios(presets);
    setConversations(chats);
  }, []);
  useEffect(() => {
    let mounted = true;
    async function init() {
      try {
        const current = await api<Config>("/config");
        if (mounted) {
          setConfig(current);
          setEmail(current.mode === "DEMO" ? "analyst@aurora.example" : "");
          setPassword(current.mode === "DEMO" ? "demo-evidence" : "");
        }
      } catch (e) {
        if (mounted) {
          setError(errorText(e));
          setInitializing(false);
        }
        return;
      }
      try {
        const current = await api<User>("/me");
        if (mounted) {
          setUser(current);
          await refreshData();
        }
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 401) && mounted)
          setError(errorText(e));
      } finally {
        if (mounted) setInitializing(false);
      }
    }
    void init();
    return () => {
      mounted = false;
      abortRef.current?.abort();
    };
  }, [refreshData]);
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(() => {
      void api<Document[]>("/documents")
        .then(setDocuments)
        .catch(() => {});
    }, 4000);
    return () => clearInterval(interval);
  }, [user]);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  async function login(event: FormEvent) {
    event.preventDefault();
    if (!config) {
      setError("Reconnect before signing in so the active mode can be verified.");
      return;
    }
    setLoginBusy(true);
    setError("");
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUser(await api<User>("/me"));
      await refreshData();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoginBusy(false);
    }
  }
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      abortRef.current?.abort();
      setUser(null);
      setMessages([]);
      setConversationId(null);
      setSource(null);
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function openConversation(id: string) {
    if (streaming) return;
    setConversationBusy(true);
    setError("");
    try {
      const chat = await api<Conversation>(`/conversations/${id}`);
      setConversationId(id);
      setMessages(chat.messages ?? []);
      setSource(null);
      setTab("workspace");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setConversationBusy(false);
    }
  }
  function newConversation() {
    if (streaming) return;
    setConversationId(null);
    setMessages([]);
    setSource(null);
    setTab("workspace");
    setError("");
  }
  async function send(scenario?: Scenario) {
    const text = scenario?.question ?? question.trim();
    if (!text || streaming) return;
    if (config?.mode === "DEMO" && !scenario) {
      setNotice(
        "Free-form answers require LIVE mode. Choose a suggested question to explore a labeled example with real sources.",
      );
      return;
    }
    setError("");
    setNotice("");
    setStreaming(true);
    setQuestion("");
    setTab("workspace");
    const controller = new AbortController();
    abortRef.current = controller;
    let id = conversationId;
    try {
      if (!id) {
        const created = await api<Conversation>("/conversations", {
          method: "POST",
          body: JSON.stringify({ title: text.slice(0, 80) }),
        });
        id = created.id;
        setConversationId(id);
      }
      const localId = `stream-${++messageSequence.current}`;
      setMessages((previous) => [
        ...previous,
        { id: `question-${localId}`, role: "user", content: text },
        { id: localId, role: "assistant", content: "", citations: [] },
      ]);
      const response = await fetch(`/api/conversations/${id}/messages`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          scenario && config?.mode === "DEMO"
            ? { scenario_id: scenario.id }
            : { question: text },
        ),
        signal: controller.signal,
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : "The answer could not be generated. Please retry.",
        );
      }
      if (!response.body)
        throw new Error("Streaming is unavailable. Please retry.");
      let terminalReceived = false;
      await consumeEvents(response.body, (event, payload) => {
        if (event === "done" || event === "cancelled") terminalReceived = true;
        const data = payload as {
          text?: string;
          citations?: Citation[];
          message?: string;
          message_id?: string;
        };
        if (event === "token")
          setMessages((previous) =>
            previous.map((message) =>
              message.id === localId
                ? { ...message, content: message.content + (data.text ?? "") }
                : message,
            ),
          );
        if (event === "citations")
          setMessages((previous) =>
            previous.map((message) =>
              message.id === localId
                ? { ...message, citations: data.citations ?? [] }
                : message,
            ),
          );
        if (event === "cancelled")
          setNotice("Generation stopped. Your conversation is saved.");
        if (event === "error")
          throw new Error(
            data.message ??
              "The provider could not complete this answer. Try again.",
          );
      });
      if (!terminalReceived) throw new Error("The answer stream ended early. Reopen the conversation or retry.");
      const persisted = await api<Conversation>(`/conversations/${id}`);
      setMessages(persisted.messages ?? []);
      setConversations(await api<Conversation[]>("/conversations"));
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError")
        setNotice("Generation stopped. Your conversation is saved.");
      else setError(errorText(e));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }
  async function cancel() {
    abortRef.current?.abort();
    if (conversationId) {
      try {
        await api(`/conversations/${conversationId}/cancel`, {
          method: "POST",
        });
      } catch (e) {
        setError(errorText(e));
      }
    }
  }
  async function viewSource(citation: Citation) {
    setSourceLoading(true);
    setError("");
    try {
      setSource(await api<Citation>(`/sources/${citation.chunk_id}`));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSourceLoading(false);
    }
  }
  async function upload(file: File | undefined) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("Choose a file smaller than 5 MB.");
      return;
    }
    setUploadBusy(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    if (versionId) form.append("document_id", versionId);
    try {
      await api<Document>("/documents", { method: "POST", body: form });
      await refreshData();
      setNotice(
        versionId
          ? "New version uploaded. Processing status will update here."
          : "Document uploaded. Processing status will update here.",
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setUploadBusy(false);
      setVersionId(null);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }
  async function removeDocument(document: Document) {
    if (
      !window.confirm(
        `Delete “${document.title}” and all indexed versions? This cannot be undone.`,
      )
    )
      return;
    setLibraryBusy(true);
    setError("");
    try {
      await api(`/documents/${document.id}`, { method: "DELETE" });
      await refreshData();
      setSource(null);
      setNotice("Document and its index were deleted.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLibraryBusy(false);
    }
  }
  async function retryDocument(id: string) {
    setLibraryBusy(true);
    try {
      await api(`/documents/${id}/retry`, { method: "POST" });
      await refreshData();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLibraryBusy(false);
    }
  }
  const organization = user?.org === "aurora" ? "Aurora Cooperative" : user?.org === "meridian" ? "Meridian Studio" : (user?.org ?? "Organization");
  const filtered = documents.filter((document) =>
    `${document.title} ${document.filename}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  if (initializing)
    return (
      <main className="boot">
        <Brand />
        <span className="spinner" />
        <p>Opening your workspace…</p>
      </main>
    );
  if (!user)
    return (
      <main className="login-page">
        <div className="login-story">
          <Brand />
          <div className="login-main">
            <h1>
              Good answers
              <br />
              leave a trail<span>.</span>
            </h1>
            <p>
              Your manuals. A focused conversation. Every answer connected to
              the evidence behind it.
            </p>
            <div className="sample-note">
              <div className="sample-note-top">
                <Icon name="file" />
                <span>Travel & expenses</span>
                <span className="small-badge">v1</span>
              </div>
              <p>“Submit your reimbursement within 30 calendar days.”</p>
              <div className="sample-note-foot">
                <Icon name="link" size={14} /> Original synthetic manual ·
                Example citation
              </div>
            </div>
          </div>
          <div className="login-bottom">
            <span>Original synthetic manuals for two fictional organizations.</span>
          </div>
        </div>
        <div className="login-panel">
          <div className="mode-pill">
            <span className="mode-dot" />
            {config?.mode ?? "MODE UNKNOWN"}
            {config?.mode === "DEMO"
              ? " · Synthetic workspace"
              : config?.mode === "LIVE" ? " · API workspace" : " · Reconnect to verify mode"}
          </div>
          <div className="login-form-wrap">
            <h2>Welcome to your desk.</h2>
            <p className="muted">
              Sign in to explore documents and follow the evidence.
            </p>
            <form onSubmit={login} className="login-form">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
              />
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
              {error && (
                <div className="alert alert-error" role="alert">
                  {error}
                </div>
              )}
              <button
                className="button button-primary login-submit"
                disabled={loginBusy || !config}
              >
                {loginBusy ? "Signing in…" : "Open workspace"}
                <Icon name="arrow" />
              </button>
            </form>
            {!config && <button className="text-link" onClick={() => window.location.reload()}>Retry connection</button>}
            {config?.mode === "DEMO" && (
              <div className="demo-access">
                <Icon name="shield" size={19} />
                <div>
                  <strong>Two independent demo organizations</strong>
                  <p>
                    Use the prefilled account or switch to{" "}
                    <button
                      className="text-link"
                      onClick={() =>
                        setEmail(
                          email.includes("aurora")
                            ? "analyst@meridian.example"
                            : "analyst@aurora.example",
                        )
                      }
                    >
                      {email.includes("aurora")
                        ? "Meridian Studio"
                        : "Aurora Cooperative"}
                    </button>
                    . Password: <code>demo-evidence</code>.
                  </p>
                </div>
              </div>
            )}
          </div>
          <p className="login-disclaimer">
            Original synthetic data. No connection to a real financial
            institution.
          </p>
        </div>
      </main>
    );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <Brand small />
        <div className="organization">
          <span className="org-avatar">{String(organization).charAt(0)}</span>
          <div>
            <strong>{organization}</strong>
            <span>Research workspace</span>
          </div>
        </div>
        <div className="nav-label">Workspace</div>
        <nav aria-label="Main navigation">
          <button
            className={`nav-item ${tab === "workspace" ? "active" : ""}`}
            onClick={() => setTab("workspace")}
          >
            <Icon name="search" size={18} />
            Ask your documents
          </button>
          <button
            className={`nav-item ${tab === "library" ? "active" : ""}`}
            onClick={() => setTab("library")}
          >
            <Icon name="book" size={18} />
            Document library<span className="count">{documents.length}</span>
          </button>
        </nav>
        <label className="mobile-history">
          <span>Conversation history</span>
          <select
            aria-label="Conversation history"
            value={conversationId ?? ""}
            disabled={streaming}
            onChange={(event) =>
              event.target.value
                ? void openConversation(event.target.value)
                : newConversation()
            }
          >
            <option value="">New conversation</option>
            {conversations.map((chat) => (
              <option key={chat.id} value={chat.id}>
                {chat.title}
              </option>
            ))}
          </select>
        </label>
        <div className="history-heading">
          <span className="nav-label">Conversations</span>
          <button
            className="icon-button"
            aria-label="New conversation"
            onClick={newConversation}
            disabled={streaming}
          >
            <Icon name="plus" size={17} />
          </button>
        </div>
        <div className="history-list">
          {conversations.length === 0 ? (
            <p className="sidebar-empty">No conversations yet.</p>
          ) : (
            conversations.map((chat) => (
              <button
                key={chat.id}
                className={`history-item ${chat.id === conversationId ? "selected" : ""}`}
                onClick={() => void openConversation(chat.id)}
                disabled={streaming}
              >
                <Icon name="chat" size={15} />
                <span>{chat.title}</span>
              </button>
            ))
          )}
        </div>
        <div className="sidebar-foot">
          <div className="trust-note">
            <Icon name="shield" size={17} />
            <p>
              Private to your organization.
              <br />
              <span>Sources stay within your workspace.</span>
            </p>
          </div>
          <div className="user-card">
            <div className="user-avatar">AN</div>
            <div>
              <strong>Research analyst</strong>
              <span>{user.email}</span>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={() => void logout()}
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <strong>
              {tab === "library" ? "Document library" : "Ask your documents"}
            </strong>
          </div>
          <div className="topbar-right">
            <span
              className={`mode-pill ${config?.mode === "LIVE" ? "live" : ""}`}
            >
              <span className="mode-dot" />
              {config?.mode ?? "MODE UNKNOWN"}
            </span>
            <button
              className="icon-button mobile-logout"
              aria-label="Sign out"
              onClick={() => void logout()}
            >
              <Icon name="logout" size={16} />
            </button>
            <span className="mode-caption">
              {config?.mode === "DEMO"
                ? "Example answers · real sources"
                : config?.ready
                  ? `${config.provider} · ${config.model}`
                  : "Configuration required"}
            </span>
          </div>
        </header>
        <main
          id="main-content"
          className={`workspace ${source ? "with-source" : ""}`}
        >
          <div className="workspace-body">
            {error && (
              <div role="alert" className="alert alert-error">
                <span>{error}</span>
                <button
                  aria-label="Dismiss error"
                  className="icon-button"
                  onClick={() => setError("")}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            )}
            {notice && (
              <div role="status" className="alert alert-info">
                <span>{notice}</span>
                <button
                  aria-label="Dismiss notice"
                  className="icon-button"
                  onClick={() => setNotice("")}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            )}
            {config?.mode === "LIVE" && !config.ready && (
              <div role="alert" className="alert alert-error">
                LIVE configuration is incomplete: {config.missing.join(", ")}.
                Ask your operator to configure the provider. Demo responses will
                not be substituted.
              </div>
            )}
            <input
              ref={uploadRef}
              type="file"
              accept=".pdf,.txt,.md,.markdown"
              className="visually-hidden"
              aria-label="Upload document file"
              onChange={(event) => void upload(event.target.files?.[0])}
            />
            {tab === "library" ? (
              <section className="library">
                <div className="section-top">
                  <div>
                    <h1>
                      Document library<span>.</span>
                    </h1>
                    <p className="muted">
                      The source of every supported answer.
                    </p>
                  </div>
                  <button
                    className="button button-primary"
                    onClick={() => {
                      setVersionId(null);
                      uploadRef.current?.click();
                    }}
                    disabled={uploadBusy}
                  >
                    {uploadBusy ? (
                      <span className="spinner small" />
                    ) : (
                      <Icon name="upload" size={17} />
                    )}{" "}
                    {uploadBusy ? "Uploading…" : "Upload document"}
                  </button>
                </div>
                <div className="library-summary">
                  <div>
                    <strong>
                      {documents.length}
                    </strong>
                    <span>
                      {documents.length === 1 ? "document" : "documents"} in
                      your workspace
                    </span>
                  </div>
                  <p>
                    <Icon name="shield" size={17} />
                    {config?.mode === "DEMO"
                      ? "Text extraction works without an API key. DEMO uses textual retrieval."
                      : "API embeddings power permission-scoped hybrid retrieval."}
                  </p>
                </div>
                <label className="search-box">
                  <Icon name="search" size={18} />
                  <span className="visually-hidden">Search library</span>
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Find a document…"
                  />
                </label>
                <div className="document-list">
                  {filtered.length === 0 ? (
                    <div className="empty-state">
                      <Icon name="book" size={34} />
                      <h3>
                        {query
                          ? "No documents match"
                          : "Your library starts here"}
                      </h3>
                      <p>
                        {query
                          ? "Try a different search."
                          : "Upload a PDF with selectable text, a TXT file, or Markdown."}
                      </p>
                    </div>
                  ) : (
                    filtered.map((document) => (
                      <article className="document-row" key={document.id}>
                        <div className="doc-icon">
                          <Icon name="file" size={22} />
                        </div>
                        <div className="document-info">
                          <h3>{document.title}</h3>
                          <p>
                            {document.filename} <span>·</span> Version{" "}
                            {document.version}
                          </p>
                          {document.error && (
                            <p className="doc-error">
                              Processing failed. Retry this document or upload a
                              new version.
                            </p>
                          )}
                        </div>
                        <span
                          className={`status-chip ${["ready", "indexed", "completed"].includes(document.status) ? "ready" : ["failed", "error"].includes(document.status) ? "failed" : "pending"}`}
                        >
                          {["ready", "indexed", "completed"].includes(
                            document.status,
                          ) && <Icon name="check" size={12} />}{" "}
                          {document.status}
                        </span>
                        <div className="doc-actions">
                          {["failed", "error"].includes(document.status) && (
                            <button
                              className="icon-button"
                              aria-label={`Retry ${document.title}`}
                              disabled={libraryBusy}
                              onClick={() => void retryDocument(document.id)}
                            >
                              <Icon name="refresh" size={17} />
                            </button>
                          )}
                          <button
                            className="icon-button"
                            aria-label={`Upload new version of ${document.title}`}
                            disabled={uploadBusy}
                            onClick={() => {
                              setVersionId(document.id);
                              uploadRef.current?.click();
                            }}
                          >
                            <Icon name="upload" size={17} />
                          </button>
                          <button
                            className="icon-button danger"
                            aria-label={`Delete ${document.title}`}
                            disabled={libraryBusy}
                            onClick={() => void removeDocument(document)}
                          >
                            <Icon name="trash" size={17} />
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
                <p className="library-footnote">
                  PDF with text, TXT, or Markdown · up to 5 MB · each upload is
                  versioned
                  <br />
                  Scanned documents need text extraction before upload.
                </p>
              </section>
            ) : (
              <section
                className="chat-workspace"
                aria-label="Document conversation"
              >
                <div className="chat-toolbar">
                  <span>
                    <span className="online-dot" />
                    {(() => {
                      const ready = documents.filter((d) =>
                        ["ready", "indexed", "completed"].includes(d.status),
                      ).length;
                      return `${ready} ${ready === 1 ? "document" : "documents"} ready to explore`;
                    })()}
                  </span>
                  <button
                    className="subtle-button"
                    onClick={newConversation}
                    disabled={streaming}
                  >
                    <Icon name="plus" size={16} />
                    New conversation
                  </button>
                </div>
                <div className="chat-content" aria-busy={conversationBusy}>
                  {messages.length === 0 ? (
                    <div className="welcome">
                      <h1>Ask your documents</h1>
                      <p className="welcome-lede">
                        Every answer links to the exact passage, version and
                        section it relies on. When the authorized documents do
                        not cover a question, the desk says so.
                      </p>
                      <div className="suggestions-label">
                        <span>
                          {config?.mode === "DEMO"
                            ? "Example questions"
                            : "Suggested questions"}
                        </span>
                        {config?.mode === "DEMO" && (
                          <span>Answers are labelled examples; sources are real</span>
                        )}
                      </div>
                      <div className="suggestions">
                        {scenarios.slice(0, 4).map((scenario) => (
                          <button
                            key={scenario.id}
                            className="suggestion"
                            onClick={() => void send(scenario)}
                            disabled={streaming || config?.ready === false}
                          >
                            <span>{scenario.question}</span>
                            <Icon name="arrow" size={16} />
                          </button>
                        ))}
                      </div>
                      {scenarios.length > 4 && (
                        <details className="more-scenarios">
                          <summary>
                            Explore {scenarios.length - 4} more example
                            questions
                          </summary>
                          <div className="suggestions">
                            {scenarios.slice(4).map((scenario) => (
                              <button
                                key={scenario.id}
                                className="suggestion"
                                onClick={() => void send(scenario)}
                                disabled={streaming || config?.ready === false}
                              >
                                <span>{scenario.question}</span>
                                <Icon name="arrow" size={16} />
                              </button>
                            ))}
                          </div>
                        </details>
                      )}
                      {scenarios.length === 0 && (
                        <p className="muted">
                          No example scenarios are available yet. Add documents
                          to get started.
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="messages">
                      {messages.map((message) => (
                        <article
                          className={`message ${message.role}`}
                          key={message.id}
                        >
                          <div className="message-body">
                            <div className="message-heading">
                              <strong>
                                {message.role === "assistant"
                                  ? "Evidence Desk"
                                  : message.role === "system"
                                    ? "Workspace"
                                    : "You"}
                              </strong>
                              {message.role === "assistant" &&
                                config?.mode === "DEMO" && (
                                  <span className="sample-badge">
                                    Example response
                                  </span>
                                )}
                            </div>
                            <div className="message-content">
                              {message.content ||
                                (streaming ? (
                                  <span className="typing">
                                    <i />
                                    <i />
                                    <i />
                                    <span className="visually-hidden">
                                      Preparing answer
                                    </span>
                                  </span>
                                ) : (
                                  "No answer was saved. Please retry."
                                ))}
                            </div>
                            {message.citations &&
                              message.citations.length > 0 && (
                                <div className="citation-list">
                                  <div className="citation-heading">
                                    Sources
                                  </div>
                                  {message.citations.map((citation, index) => (
                                    <button
                                      className="citation-card"
                                      key={`${citation.chunk_id}-${index}`}
                                      onClick={() => void viewSource(citation)}
                                      disabled={sourceLoading}
                                    >
                                      <span className="citation-index">
                                        {index + 1}
                                      </span>
                                      <div>
                                        <strong>{citation.title}</strong>
                                        <span>
                                          Version {citation.version} ·{" "}
                                          {citation.location}
                                        </span>
                                      </div>
                                      <span className="citation-open">
                                        Open passage
                                        <Icon name="arrow" size={14} />
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              )}
                          </div>
                        </article>
                      ))}
                      <div ref={endRef} />
                    </div>
                  )}
                </div>
                <div className="composer-wrap">
                  <form
                    className="composer"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void send();
                    }}
                  >
                    <label className="visually-hidden" htmlFor="question">
                      Ask a question about your documents
                    </label>
                    <textarea
                      id="question"
                      placeholder={
                        config?.mode === "DEMO"
                          ? "Choose a question above to explore the demo…"
                          : "Ask a question about your documents…"
                      }
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      rows={2}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          void send();
                        }
                      }}
                    />
                    <div className="composer-bottom">
                      <span>
                        <Icon name="book" size={15} />
                        {config?.mode === "DEMO"
                          ? "Curated examples"
                          : "Your authorized sources"}
                      </span>
                      {streaming ? (
                        <button
                          type="button"
                          className="stop-button"
                          onClick={() => void cancel()}
                        >
                          Stop generation
                        </button>
                      ) : (
                        <button
                          className="send-button"
                          aria-label="Send question"
                          disabled={!question.trim() || config?.ready === false}
                        >
                          <Icon name="arrow" size={21} />
                        </button>
                      )}
                    </div>
                  </form>
                  <p className="composer-note">
                    {config?.mode === "DEMO"
                      ? "DEMO: labeled example answers. Free-form questions require LIVE. No model metrics are simulated."
                      : "Check the cited sources before making a decision. Unsupported questions should receive an abstention."}
                  </p>
                </div>
              </section>
            )}
          </div>
          {source && (
            <aside className="source-panel" aria-label="Source evidence">
              <div className="source-top">
                <span className="eyebrow">Source</span>
                <button
                  className="icon-button"
                  aria-label="Close source"
                  onClick={() => setSource(null)}
                >
                  <Icon name="close" size={18} />
                </button>
              </div>
              <div className="source-document">
                <h2>{source.title}</h2>
                <span className="source-version">
                  Version {source.version} <span>·</span> {source.location}
                </span>
                <a
                  className="source-download"
                  href={`/api/documents/${encodeURIComponent(source.document_id)}/file?version=${source.version}`}
                >
                  Download version {source.version}
                  <Icon name="arrow" size={14} />
                </a>
              </div>
              <div className="source-rule" />
              <div className="source-excerpt">
                <div className="eyebrow">Original passage</div>
                <blockquote>{source.excerpt}</blockquote>
              </div>
              <div className="source-trust">
                <Icon name="check" size={17} />
                <p>
                  Retrieved from your authorized document.
                  <span>
                    Document content is evidence, never an instruction to the
                    assistant.
                  </span>
                </p>
              </div>
              <div className="source-id">
                Passage ID <code>{source.chunk_id.slice(0, 12)}</code>
              </div>
            </aside>
          )}
        </main>
      </div>
    </div>
  );
}
