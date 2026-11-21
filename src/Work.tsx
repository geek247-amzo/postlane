import { useEffect, useState, FormEvent } from "react";
import {
  MessageSquare,
  Plug,
  Plus,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  Check,
  X,
  ExternalLink,
  Mail,
  ClipboardList,
} from "lucide-react";
import { api, post, patch, Mailbox } from "./api";
import { Modal } from "./App";
import "./work.css";

type Connection = {
  id: string;
  name: string;
  provider: string;
  kind: string;
  enabled: boolean;
  credential_saved: boolean;
  settings: Record<string, string>;
};
type Chat = {
  id: string;
  title: string;
  provider_id: string;
  connection_ids: string[];
};
type Detail = Chat & {
  entries: { id: string; role: string; content: string }[];
  actions: {
    id: string;
    connection_id: string;
    operation: string;
    arguments: Record<string, string>;
    status: string;
    result: string;
  }[];
};
const names: Record<string, string> = {
  openai: "OpenAI API",
  gemini: "Google Gemini",
  claude: "Anthropic Claude",
  deepseek: "DeepSeek",
  codex: "Codex account",
  hermes: "Hermes webhook assistant",
  clickup: "ClickUp",
  notion: "Notion",
  drive: "Google Drive",
  mail: "Gmail & connected mail",
  linkedin: "LinkedIn",
  facebook: "Facebook Pages",
  instagram: "Instagram Business",
};
const targets: Record<string, string> = {
  clickup: "list_id",
  notion: "page_id",
  mail: "mailbox_id",
  linkedin: "author",
  facebook: "page_id",
  instagram: "account_id",
};
const hints: Record<string, string> = {
  hermes:
    "Connect your approved Hermes HTTPS webhook. In Work chat Jeff is a reply-only assistant: he receives no integrations, cannot propose actions, and cannot send email. Store its bearer/signing secret here, never in chat. A workspace administrator must explicitly approve its HTTPS origin.",
  clickup:
    "Connect one ClickUp list. Use a personal API token with access to that list.",
  notion:
    "Share the parent page with your Notion integration. Search covers pages shared with that integration.",
  drive:
    "Authorize Google after saving. Allows read-only access to your Drive and creation of new documents. The agent can read Google Docs and plain-text files on selected connections.",
  mail: "Uses an existing mailbox and its permissions. External AI must be enabled for the mailbox. Work can search and prepare drafts, but cannot send email.",
  linkedin:
    "Use an authorized access token and author URN, such as urn:li:organization:123. Posting requires LinkedIn permissions.",
  facebook:
    "Use a Page access token with pages_read_engagement and pages_manage_posts. Actions publish as this Page.",
  instagram:
    "Connect an Instagram professional account linked to a Facebook Page. Use a token with instagram_basic and instagram_content_publish. This release publishes single public JPEG images with captions.",
  codex:
    "Sign in through the separate Codex account panel. Requires the operator-enabled Codex bridge; no API key is used.",
};

function unwrapJeffReply(content: string) {
  try {
    const parsed = JSON.parse(content);
    if (
      parsed &&
      typeof parsed.reply === "string" &&
      Array.isArray(parsed.actions) &&
      parsed.actions.length === 0
    )
      return parsed.reply;
  } catch {
    // Older Jeff turns may already be plain text.
  }
  return content;
}

export default function Work({
  boxes,
  demo,
  notify,
  isAdmin = false,
}: {
  isAdmin?: boolean;
  boxes: Mailbox[];
  demo: boolean;
  notify: (s: string) => void;
}) {
  const [page, setPage] = useState("chat"),
    [connections, setConnections] = useState<Connection[]>([]),
    [chats, setChats] = useState<Chat[]>([]),
    [detail, setDetail] = useState<Detail | null>(null),
    [catalog, setCatalog] = useState<any>(null);
  const [hermesOrigins, setHermesOrigins] = useState<
    { origin: string; active: boolean }[]
  >([]);
  const [modal, setModal] = useState(""),
    [provider, setProvider] = useState("openai"),
    [chatProviderId, setChatProviderId] = useState(""),
    [busy, setBusy] = useState(false),
    [input, setInput] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [codex, setCodex] = useState<any>(null);
  const [connectionError, setConnectionError] = useState("");
  const [providerToken, setProviderToken] = useState("");
  const [providerModels, setProviderModels] = useState<
    { id: string; name: string }[]
  >([]);
  const [chosenModel, setChosenModel] = useState("");
  const keyProvider = ["openai", "gemini", "claude", "deepseek"].includes(
    provider,
  );
  useEffect(() => {
    setConnectionError("");
    setProviderToken("");
    setProviderModels([]);
    setChosenModel("");
  }, [provider, modal]);
  async function discoverModels() {
    await perform(async () => {
      const result = await post<{ models: { id: string; name: string }[] }>(
        "/work/provider-models",
        { provider, token: providerToken },
      );
      setProviderModels(result.models);
      setChosenModel(result.models[0]?.id || "");
      notify("Key verified. Choose a model, then save the connection.");
    });
  }
  useEffect(() => {
    if (page === "hermes")
      api<{ origin: string; active: boolean }[]>("/work/hermes-origins")
        .then(setHermesOrigins)
        .catch((e) => notify(e.message));
  }, [page, connections]);
  const error = (e: unknown) => notify((e as Error).message);
  const gmailBoxes = boxes.filter((b) => b.provider === "gmail");
  const workReadyGmail = gmailBoxes.filter(
    (b) => b.status === "connected" && b.ai_enabled,
  );
  const clickupSaved = connections.some(
    (c) => c.provider === "clickup" && c.enabled && c.credential_saved,
  );
  async function load() {
    const [c, h, k] = await Promise.all([
      api<Connection[]>("/work/connections"),
      api<Chat[]>("/work/chats"),
      api("/work/catalog"),
    ]);
    setConnections(c);
    setChats(h);
    setCatalog(k);
  }
  useEffect(() => {
    void load().catch(error);
  }, []);
  async function openChat(id: string) {
    setDetail(await api<Detail>("/work/chats/" + id));
    setPage("chat");
  }
  async function perform(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    if (modal === "connection") setConnectionError("");
    try {
      await fn();
    } catch (e) {
      if (modal === "connection") setConnectionError((e as Error).message);
      error(e);
    } finally {
      setBusy(false);
    }
  }
  async function saveConnection(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    await perform(async () => {
      if (
        keyProvider &&
        (!providerModels.length ||
          !providerModels.some((m) => m.id === chosenModel))
      )
        throw new Error(
          "Test the API key and choose an available model before saving.",
        );
      const settings: Record<string, string> = {};
      if (provider === "hermes") settings.url = String(data.url).trim();
      else if (catalog.ai.includes(provider))
        settings.model = keyProvider ? chosenModel : String(data.model);
      else if (targets[provider])
        settings[targets[provider]] = String(data.target);
      await post("/work/connections", {
        provider,
        name: data.name,
        token: keyProvider ? providerToken : data.token || "",
        settings,
        approve_origin: provider === "hermes" && data.approve_origin === "on",
      });
      setModal("");
      await load();
      notify(
        "Connection saved. Credentials are encrypted; verify provider access before relying on it.",
      );
    });
  }
  async function createChat(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget));
    await perform(async () => {
      const c = await post("/work/chats", {
        title: data.title,
        provider_id: data.provider_id,
        connection_ids: selected,
        consent: data.consent === "on",
      });
      setModal("");
      await load();
      await openChat(c.id);
    });
  }
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!detail || !input.trim()) return;
    await perform(async () => {
      const next = await post<Detail>(`/work/chats/${detail.id}/messages`, {
        content: input,
      });
      setDetail(next);
      setInput("");
    });
  }
  const active = connections.filter((c) => c.enabled);
  const selectedChatProvider = active.find((c) => c.id === chatProviderId);
  const chatUsesJeff = selectedChatProvider?.provider === "hermes";
  const detailProvider = connections.find((c) => c.id === detail?.provider_id);
  const detailUsesJeff = detailProvider?.provider === "hermes";
  return (
    <div className="work-page">
      <div className="work-heading">
        <div>
          <span className="eyebrow">CLOUDMONKEY WORK</span>
          <h1>Your business, connected.</h1>
          <p>Think, plan and take action across the tools you use every day.</p>
        </div>
        <div className="work-tabs">
          <button
            className={page === "chat" ? "selected" : ""}
            onClick={() => setPage("chat")}
          >
            <MessageSquare size={16} /> Agent chat
          </button>
          <button
            className={page === "connections" ? "selected" : ""}
            onClick={() => setPage("connections")}
          >
            <Plug size={16} /> Connections
          </button>
          <button
            className={page === "hermes" ? "selected" : ""}
            onClick={() => setPage("hermes")}
          >
            <Plug size={16} />
            Hermes settings
          </button>
        </div>
      </div>
      {demo && (
        <div className="work-notice">
          Explore the workspace. Live connections, AI calls and account sign-in
          are disabled in sample mode.
        </div>
      )}
      {page === "connections" || page === "hermes" ? (
        <>
          <div className="work-section-title">
            <div>
              <h2>
                {page === "hermes"
                  ? "Hermes assistant settings"
                  : "Your connections"}
              </h2>
              <p>
                Private to your account. Choose which connections each
                conversation can use.
              </p>
            </div>
            <button
              className="primary"
              disabled={demo || busy || !catalog}
              onClick={() => {
                setProvider(page === "hermes" ? "hermes" : "openai");
                setModal("connection");
              }}
            >
              <Plus size={16} />{" "}
              {page === "hermes" ? "Connect Hermes webhook" : "Add connection"}
            </button>
          </div>
          {page !== "hermes" && (
            <section className="integration-setup">
              <div className="setup-card">
                <Mail size={20} />
                <div>
                  <h3>Gmail for Work agents</h3>
                  <p>
                    Add a Gmail mailbox in Admin, authorize Google, sync it,
                    then enable external AI on that mailbox. Work can search the
                    local synchronized mail and prepare drafts for review.
                  </p>
                  <dl>
                    <div>
                      <dt>Google OAuth</dt>
                      <dd>
                        {catalog?.gmail_oauth_configured
                          ? "Configured; verify live"
                          : "Needs server credentials"}
                      </dd>
                    </div>
                    <div>
                      <dt>Mailbox callback</dt>
                      <dd>{catalog?.mail_oauth_callback || "Loading..."}</dd>
                    </div>
                    <div>
                      <dt>Gmail mailboxes</dt>
                      <dd>
                        {gmailBoxes.length} added; {workReadyGmail.length} ready
                        for Work
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
              <div className="setup-card">
                <ClipboardList size={20} />
                <div>
                  <h3>ClickUp task actions</h3>
                  <p>
                    Create a ClickUp personal token with access to one list and
                    save that list ID here. Reads run automatically; task
                    creation appears as an approval card before it is sent to
                    ClickUp.
                  </p>
                  <dl>
                    <div>
                      <dt>Saved connection</dt>
                      <dd>
                        {clickupSaved ? "Ready to test" : "Not added yet"}
                      </dd>
                    </div>
                    <div>
                      <dt>Allowed actions</dt>
                      <dd>List open tasks and create approved tasks</dd>
                    </div>
                  </dl>
                </div>
              </div>
              <div className="setup-card">
                <ExternalLink size={20} />
                <div>
                  <h3>Google Drive and apps</h3>
                  <p>
                    Drive uses a second Google redirect so the agent can read
                    docs and create new documents without expanding Gmail
                    mailbox scopes.
                  </p>
                  <dl>
                    <div>
                      <dt>Drive callback</dt>
                      <dd>{catalog?.work_oauth_callback || "Loading..."}</dd>
                    </div>
                    <div>
                      <dt>Approval policy</dt>
                      <dd>Reads automatic; changes and posts need approval</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </section>
          )}
          {page === "hermes" && (
            <section className="panel">
              <h3>Approved Hermes destinations</h3>
              <p className="help">
                Administrators can approve an exact HTTPS origin while
                connecting Hermes. Browser input cannot enable private-network
                access: private destinations still require server policy and
                trusted TLS.
              </p>
              {hermesOrigins.length ? (
                hermesOrigins.map((o) => (
                  <div className="integration-row" key={o.origin}>
                    <code>{o.origin}</code>
                    {isAdmin && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          perform(async () => {
                            await post("/work/hermes-origins/revoke", {
                              origin: o.origin,
                            });
                            setHermesOrigins(await api("/work/hermes-origins"));
                            notify(
                              "Hermes origin revoked. Future requests will be rejected.",
                            );
                          })
                        }
                      >
                        Revoke origin
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p className="help">
                  No workspace-approved Hermes origins yet.
                </p>
              )}
            </section>
          )}
          <div className="connection-grid">
            {Object.entries(names)
              .filter(([key]) => page !== "hermes" || key === "hermes")
              .map(([key, label]) => {
                const saved = connections.filter((c) => c.provider === key);
                return (
                  <section className="connection-card" key={key}>
                    <div className={"integration-mark mark-" + key}>
                      {label.slice(0, 2).toUpperCase()}
                    </div>
                    <h3>{label}</h3>
                    <p>
                      {hints[key] ||
                        "Bring your own API key and choose a model available to your account. Usage is billed by the provider."}
                    </p>
                    {saved.map((c) => (
                      <div className="saved-connection" key={c.id}>
                        <strong>{c.name}</strong>
                        <small>
                          {c.enabled
                            ? c.credential_saved
                              ? "Credential saved; verify live"
                              : key === "codex"
                                ? "Uses Codex account"
                                : key === "mail"
                                  ? "Uses mailbox access"
                                  : "Authorization needed"
                            : "Disabled"}
                        </small>
                        <div className="work-inline-actions">
                          {key === "hermes" && c.enabled && (
                            <button
                              disabled={busy}
                              onClick={() =>
                                perform(async () => {
                                  await post(`/work/connections/${c.id}/test`);
                                  notify(
                                    "Hermes connection verified. No Postlane actions executed.",
                                  );
                                })
                              }
                            >
                              Test webhook
                            </button>
                          )}
                          <button
                            disabled={busy}
                            onClick={() =>
                              perform(async () => {
                                await patch("/work/connections/" + c.id, {
                                  enabled: !c.enabled,
                                });
                                await load();
                              })
                            }
                          >
                            {c.enabled ? "Disable" : "Enable"}
                          </button>
                          {key === "drive" && c.enabled && (
                            <button
                              disabled={busy || demo}
                              onClick={() =>
                                perform(async () => {
                                  const r = await post(
                                    `/work/connections/${c.id}/google`,
                                  );
                                  window.location.assign(r.url);
                                })
                              }
                            >
                              Authorize Google <ExternalLink size={12} />
                            </button>
                          )}
                          <button
                            disabled={busy}
                            onClick={() => {
                              if (
                                window.confirm(
                                  "Disconnect and erase this saved credential? Existing chats stay in your history.",
                                )
                              )
                                void perform(async () => {
                                  await api("/work/connections/" + c.id, {
                                    method: "DELETE",
                                  });
                                  await load();
                                });
                            }}
                          >
                            Disconnect
                          </button>
                        </div>
                      </div>
                    ))}
                    <button
                      className="secondary"
                      disabled={demo || busy || !catalog}
                      onClick={() => {
                        setProvider(key);
                        setModal("connection");
                      }}
                    >
                      <Plus size={14} /> Add {label}
                    </button>
                  </section>
                );
              })}
          </div>
          <section className="codex-panel">
            <div>
              <h3>Sign in with your Codex / ChatGPT account</h3>
              <p>
                Uses the official Codex app-server device sign-in flow. Account
                eligibility and usage limits apply separately from OpenAI API
                billing.
              </p>
              {!catalog?.codex_available && (
                <p className="help">
                  The server operator must enable the isolated Codex bridge
                  before sign-in is available.
                </p>
              )}
            </div>
            <div className="work-inline-actions">
              {["login", "status", "logout"].map((op) => (
                <button
                  className="secondary"
                  key={op}
                  disabled={demo || busy || !catalog?.codex_available}
                  onClick={() =>
                    perform(async () => {
                      setCodex(await post("/work/codex/" + op));
                    })
                  }
                >
                  {op === "login"
                    ? "Sign in"
                    : op === "status"
                      ? "Check account"
                      : "Sign out"}
                </button>
              ))}
            </div>
            {codex?.userCode && (
              <div className="work-notice">
                Open{" "}
                <a
                  href="https://auth.openai.com/codex/device"
                  target="_blank"
                  rel="noreferrer"
                >
                  OpenAI device sign-in
                </a>{" "}
                and enter <strong>{codex.userCode}</strong>. Then choose Check
                account. Never share this code.
              </div>
            )}
            {codex && !codex.userCode && (
              <pre className="work-result">
                {JSON.stringify(codex, null, 2)}
              </pre>
            )}
          </section>
        </>
      ) : (
        <div className="work-chat-layout">
          <aside className="chat-list">
            <button
              className="primary"
              disabled={demo || busy || !active.some((c) => c.kind === "ai")}
              onClick={() => {
                setSelected([]);
                setChatProviderId(
                  active.find((c) => c.kind === "ai")?.id || "",
                );
                setModal("chat");
              }}
            >
              <Plus size={16} /> New conversation
            </button>
            {chats.map((c) => (
              <button
                className={
                  "chat-link " + (detail?.id === c.id ? "selected" : "")
                }
                key={c.id}
                disabled={busy}
                onClick={() => perform(() => openChat(c.id))}
              >
                <MessageSquare size={15} />
                <span>{c.title}</span>
              </button>
            ))}
            {!chats.length && <p>Your conversations will appear here.</p>}
            <div className="work-private">
              <ShieldCheck size={20} />
              <strong>You stay in control</strong>
              <p>
                Reads run automatically on selected connections. Task creation,
                changes and public posts need your approval. Email drafts still
                require review in Mail.
              </p>
            </div>
          </aside>
          <section className="chat-main">
            {!detail ? (
              <div className="work-welcome">
                <div className="work-orb">
                  <Sparkles size={32} />
                </div>
                <h2>A place to get work done.</h2>
                <p>
                  Connect a model and your business tools, then start a private
                  conversation with your agent.
                </p>
                <div className="prompt-examples">
                  <span>Turn this brief into ClickUp tasks</span>
                  <span>Prepare a Notion project update</span>
                  <span>Draft a LinkedIn announcement</span>
                  <span>Find the latest client email</span>
                </div>
                <button
                  className="secondary"
                  onClick={() => setPage("connections")}
                >
                  <Plug size={16} /> Set up connections
                </button>
              </div>
            ) : (
              <>
                <div className="chat-heading">
                  <div>
                    <h3>{detail.title}</h3>
                    <small>
                      {detailUsesJeff
                        ? "Jeff · reply-only assistant · no integrations or actions"
                        : `${detailProvider?.name || "Work agent"} · ${detail.connection_ids.length} selected integrations · reads automatic · changes need approval`}
                    </small>
                  </div>
                  <button
                    className="icon-button"
                    title="Delete conversation"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Delete this conversation and its action history? Provider actions already performed cannot be undone.",
                        )
                      )
                        void perform(async () => {
                          await api("/work/chats/" + detail.id, {
                            method: "DELETE",
                          });
                          setDetail(null);
                          await load();
                        });
                    }}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="chat-transcript" aria-live="polite">
                  {!detail.entries.length && (
                    <p className="chat-empty">
                      {detailUsesJeff
                        ? "What would you like to ask Jeff? He can help with replies, but has no integrations or actions in this chat."
                        : "What would you like to work on? Your selected integrations are available for proposed actions."}
                    </p>
                  )}
                  {detail.entries.map((e) => (
                    <article
                      className={"chat-message role-" + e.role}
                      key={e.id}
                    >
                      <strong>
                        {e.role === "user"
                          ? "You"
                          : e.role === "assistant"
                            ? detailUsesJeff
                              ? "Jeff"
                              : "Work agent"
                            : "Action result"}
                      </strong>
                      <div>
                        {detailUsesJeff && e.role === "assistant"
                          ? unwrapJeffReply(e.content)
                          : e.content}
                      </div>
                    </article>
                  ))}
                  {detail.actions.length > 0 && (
                    <div className="action-list">
                      <h3>Actions & approvals</h3>
                      {detail.actions.map((a) => (
                        <article className="action-card" key={a.id}>
                          <div className="action-heading">
                            <strong>{a.operation.replaceAll("_", " ")}</strong>
                            <span
                              className={"action-status status-" + a.status}
                            >
                              {a.status}
                            </span>
                          </div>
                          <p>
                            {
                              connections.find((c) => c.id === a.connection_id)
                                ?.name
                            }
                            {a.operation.startsWith("publish_")
                              ? " · Publishes publicly"
                              : ""}
                          </p>
                          <dl>
                            {Object.entries(a.arguments).map(([k, v]) => (
                              <div key={k}>
                                <dt>{k}</dt>
                                <dd>{v}</dd>
                              </div>
                            ))}
                          </dl>
                          {a.status === "pending" && (
                            <div className="work-inline-actions">
                              <button
                                className="primary"
                                disabled={busy}
                                onClick={() =>
                                  perform(async () => {
                                    const r = await post(
                                      `/work/actions/${a.id}/approve`,
                                    );
                                    notify(
                                      r.status === "completed"
                                        ? "Action completed."
                                        : r.result,
                                    );
                                    await openChat(detail.id);
                                  })
                                }
                              >
                                <Check size={15} /> Approve & run
                              </button>
                              <button
                                className="secondary"
                                disabled={busy}
                                onClick={() =>
                                  perform(async () => {
                                    await post(`/work/actions/${a.id}/reject`);
                                    await openChat(detail.id);
                                  })
                                }
                              >
                                <X size={15} /> Reject
                              </button>
                            </div>
                          )}
                          {a.result && (
                            <details>
                              <summary>View result</summary>
                              <pre className="work-result">{a.result}</pre>
                            </details>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                  {busy && (
                    <div
                      className="work-thinking"
                      role="status"
                      aria-live="polite"
                      aria-label={
                        detailUsesJeff
                          ? "Jeff is thinking"
                          : "Work agent is thinking"
                      }
                    >
                      <Sparkles size={16} className="thinking-sparkle" />
                      <span>
                        {detailUsesJeff
                          ? "Jeff is thinking"
                          : "Your agent is thinking"}
                      </span>
                      <span className="thinking-dots" aria-hidden="true">
                        <i />
                        <i />
                        <i />
                      </span>
                    </div>
                  )}
                </div>
                <form className="chat-composer" onSubmit={send}>
                  <textarea
                    aria-label={
                      detailUsesJeff
                        ? "Message Jeff"
                        : "Message your Work agent"
                    }
                    placeholder={
                      detailUsesJeff
                        ? "Ask Jeff to help with a response…"
                        : "Ask your agent to plan, research or prepare an action…"
                    }
                    value={input}
                    maxLength={12000}
                    onChange={(e) => setInput(e.target.value)}
                    disabled={busy}
                  />
                  <div>
                    <small>
                      {detailUsesJeff
                        ? "Your message goes to Jeff through the approved reply-only webhook. He has no integrations and cannot send email."
                        : "Chat and connected data go to your selected AI provider. Never paste passwords or API keys here."}
                    </small>
                    <button
                      className="primary"
                      disabled={busy || !input.trim() || demo}
                    >
                      <Send size={16} /> Send
                    </button>
                  </div>
                </form>
              </>
            )}
          </section>
        </div>
      )}
      {modal === "connection" && (
        <Modal
          title={"Connect " + names[provider]}
          close={() => !busy && setModal("")}
        >
          <form className="stack-form" onSubmit={saveConnection}>
            {connectionError && (
              <p role="alert" className="help">
                {connectionError}
              </p>
            )}
            <label>
              Connection name
              <input
                name="name"
                required
                maxLength={100}
                placeholder="My business account"
              />
            </label>
            {!["mail", "drive", "codex"].includes(provider) && (
              <label>
                {provider === "hermes"
                  ? "Hermes bearer / signing secret"
                  : "API key / access token"}
                <input
                  name="token"
                  value={keyProvider ? providerToken : undefined}
                  onChange={
                    keyProvider
                      ? (e) => {
                          setProviderToken(e.target.value);
                          setProviderModels([]);
                          setChosenModel("");
                        }
                      : undefined
                  }
                  type="password"
                  required
                  autoComplete="new-password"
                  maxLength={16000}
                  minLength={provider === "hermes" ? 16 : undefined}
                  disabled={busy}
                />
              </label>
            )}
            {keyProvider && (
              <>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || !providerToken.trim()}
                  onClick={() => void discoverModels()}
                >
                  Test key & load models
                </button>
                <label>
                  Available model
                  <select
                    name="model"
                    required
                    disabled={busy || !providerModels.length}
                    value={chosenModel}
                    onChange={(e) => setChosenModel(e.target.value)}
                  >
                    <option value="">Test your key to load models</option>
                    {providerModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.id})
                      </option>
                    ))}
                  </select>
                </label>
                <p className="help">
                  Testing checks model-list access without generating text.
                  Provider billing and model-generation permissions still apply.
                </p>
              </>
            )}
            {catalog.ai.includes(provider) &&
              !keyProvider &&
              provider !== "hermes" && (
                <label>
                  Model ID
                  <input
                    name="model"
                    required
                    maxLength={120}
                    placeholder="Exact model ID from your provider"
                    pattern="[A-Za-z0-9._:\-]+"
                  />
                </label>
              )}
            {provider === "hermes" && (
              <label>
                Hermes HTTPS webhook URL
                <input
                  name="url"
                  type="url"
                  required
                  placeholder="https://hermes.example.com/postlane"
                  maxLength={2000}
                />
              </label>
            )}
            {provider === "hermes" && isAdmin && (
              <label className="check-label">
                <input type="checkbox" name="approve_origin" />
                Approve outbound requests to this exact HTTPS origin for this
                workspace
              </label>
            )}
            {targets[provider] &&
              (provider === "mail" ? (
                <label>
                  Mailbox
                  <select name="target" required>
                    {boxes.map((b) => (
                      <option value={b.id} key={b.id}>
                        {b.email}
                        {b.ai_enabled ? "" : " — AI disabled"}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label>
                  {targets[provider].replaceAll("_", " ")}
                  <input
                    name="target"
                    required
                    placeholder={
                      provider === "linkedin"
                        ? "urn:li:organization:123"
                        : "Target ID from your connected service"
                    }
                  />
                </label>
              ))}
            <p className="help">
              {hints[provider] ||
                "Your key is encrypted on the server and is never sent to the model as conversation text."}
            </p>
            <button
              className="primary"
              disabled={busy || (keyProvider && !chosenModel)}
            >
              Save connection
            </button>
          </form>
        </Modal>
      )}
      {modal === "chat" && (
        <Modal
          title="Start a Work conversation"
          close={() => !busy && setModal("")}
        >
          <form className="stack-form" onSubmit={createChat}>
            <label>
              Conversation name
              <input
                name="title"
                required
                maxLength={120}
                placeholder="Plan the product launch"
              />
            </label>
            <label>
              AI provider
              <select
                name="provider_id"
                required
                value={chatProviderId}
                onChange={(e) => {
                  const nextId = e.target.value;
                  setChatProviderId(nextId);
                  if (
                    connections.find((c) => c.id === nextId)?.provider ===
                    "hermes"
                  )
                    setSelected([]);
                }}
              >
                {active
                  .filter((c) => c.kind === "ai")
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} · {names[c.provider]}
                      {c.provider === "hermes"
                        ? " · Jeff reply-only"
                        : c.settings.model
                          ? ` · ${c.settings.model}`
                          : ""}
                    </option>
                  ))}
              </select>
            </label>
            {chatUsesJeff ? (
              <p className="work-notice">
                Jeff is a reply-only assistant. This conversation won’t share
                Work integrations, and Jeff can’t perform actions or send email.
              </p>
            ) : (
              <fieldset>
                <legend>
                  Allow this conversation to propose actions using
                </legend>
                {active
                  .filter((c) => c.kind === "integration")
                  .map((c) => (
                    <label className="check-label" key={c.id}>
                      <input
                        type="checkbox"
                        checked={selected.includes(c.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, c.id]
                              : selected.filter((id) => id !== c.id),
                          )
                        }
                      />
                      {c.name} · {names[c.provider]}
                    </label>
                  ))}
              </fieldset>
            )}
            <label className="check-label">
              <input type="checkbox" name="consent" required />I agree to send
              {chatUsesJeff
                ? " this conversation to Jeff through my approved webhook."
                : " this conversation and integration results to the selected AI provider. Reads run automatically on my selected connections; changes and public posts require my approval."}
            </label>
            <button className="primary" disabled={busy}>
              Start conversation
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
