import { useEffect, useState, FormEvent } from "react";
import {
  Globe,
  Users,
  Mail,
  Plus,
  ArrowUpRight,
  Check,
  ShieldCheck,
  Workflow,
  KeyRound,
  Copy,
  RefreshCw,
  ExternalLink,
  Lock,
  LogOut,
  ChevronRight,
  Trash2,
  Shield,
  Server,
  Settings,
  Activity,
  Ban,
  Sparkles,
  ArrowDown,
  ArrowUp,
  Bell,
} from "lucide-react";
import { api, post, patch, Mailbox, User, Message } from "./api";
import { Modal, Empty } from "./App";
import { Installation, PasswordSettings } from "./Installation";

type Props = {
  tab: string;
  setTab: (s: string) => void;
  boxes: Mailbox[];
  user: User;
  demo: boolean;
  notify: (s: string) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  theme: "light" | "liquid" | "midnight";
  setTheme: (theme: "light" | "liquid" | "midnight") => void;
  notificationsEnabled: boolean;
  enableNotifications: () => Promise<void>;
  disableNotifications: () => Promise<void>;
};
function SpamRules({
  boxes,
  notify,
}: {
  boxes: Mailbox[];
  notify: (s: string) => void;
}) {
  const [rules, setRules] = useState<
    {
      id: string;
      mailbox_id: string;
      sender: string;
      action: "spam" | "trusted";
      created_at: number;
    }[]
  >([]);
  const load = async () => {
    try {
      setRules(await api("/spam-rules"));
    } catch (e) {
      notify((e as Error).message);
    }
  };
  useEffect(() => {
    void load();
  }, []);
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h3>Spam senders</h3>
          <p>Future messages from these addresses go straight to Spam.</p>
        </div>
        <Ban size={20} />
      </div>
      {rules.length ? (
        rules.map((rule) => (
          <div className="integration-row" key={rule.id}>
            {rule.action === "trusted" ? (
              <Check size={17} />
            ) : (
              <Ban size={17} />
            )}
            <div>
              <strong>{rule.sender}</strong>
              <small>
                {rule.action === "trusted"
                  ? "Learned as safe · "
                  : "Blocked sender · "}
                {boxes.find((box) => box.id === rule.mailbox_id)?.email ||
                  "Mailbox"}
              </small>
            </div>
            <button
              className="icon-button"
              title="Remove spam rule"
              onClick={async () => {
                try {
                  await api(`/spam-rules/${rule.id}`, { method: "DELETE" });
                  await load();
                  notify("Spam rule removed.");
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))
      ) : (
        <div className="small-empty">
          No sender addresses have been blocked.
        </div>
      )}
    </section>
  );
}
function SpamManager({
  boxes,
  notify,
}: {
  boxes: Mailbox[];
  notify: (s: string) => void;
}) {
  const [items, setItems] = useState<Message[]>([]);
  const [mailbox, setMailbox] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      setItems(
        await api<Message[]>(
          `/spam/review${mailbox ? `?mailbox_id=${mailbox}` : ""}`,
        ),
      );
    } catch (e) {
      notify((e as Error).message);
    }
  };
  useEffect(() => {
    void load();
  }, [mailbox]);
  const feedback = async (id: string, verdict: "spam" | "not_spam") => {
    setBusy(true);
    try {
      await post(`/messages/${id}/spam-feedback`, { verdict });
      setItems((current) => current.filter((item) => item.id !== id));
      notify(
        verdict === "spam"
          ? "Marked spam and learned this sender."
          : "Marked safe and learned this sender.",
      );
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel spam-manager">
      <div className="panel-heading">
        <div>
          <h3>Spam Manager</h3>
          <p>
            Review suspicious mail and teach the filter what belongs in Spam.
          </p>
        </div>
        <Ban size={20} />
      </div>
      <div className="settings-body spam-manager-controls">
        <select value={mailbox} onChange={(e) => setMailbox(e.target.value)}>
          <option value="">All mailboxes</option>
          {boxes.map((box) => (
            <option value={box.id} key={box.id}>
              {box.email}
            </option>
          ))}
        </select>
        <button
          className="secondary"
          onClick={() => void load()}
          disabled={busy}
        >
          <RefreshCw size={14} /> Refresh queue
        </button>
      </div>
      {items.length ? (
        items.map((item) => (
          <div className="spam-review-row" key={item.id}>
            <div className="spam-review-main">
              <div className="spam-review-topline">
                <strong>{item.sender}</strong>
                <span className={`spam-score ${item.spam_verdict}`}>
                  {item.spam_score}% risk
                </span>
              </div>
              <b>{item.subject || "(No subject)"}</b>
              <small>
                {boxes.find((box) => box.id === item.mailbox_id)?.email ||
                  "Mailbox"}
              </small>
              {!!item.spam_reasons?.length && (
                <p>{item.spam_reasons.join(" ")}</p>
              )}
            </div>
            <div className="spam-review-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void feedback(item.id, "not_spam")}
              >
                <Check size={14} /> Not spam
              </button>
              <button
                className="danger-button"
                disabled={busy}
                onClick={() => void feedback(item.id, "spam")}
              >
                <Ban size={14} /> Spam
              </button>
            </div>
          </div>
        ))
      ) : (
        <div className="small-empty">No suspicious messages need review.</div>
      )}
    </section>
  );
}
function AliasEditor({
  box,
  notify,
}: {
  box: Mailbox;
  notify: (s: string) => void;
}) {
  const [aliases, setAliases] = useState<
      { id: string; email: string; enabled: boolean }[]
    >([]),
    [loaded, setLoaded] = useState(false),
    [address, setAddress] = useState(""),
    [busy, setBusy] = useState(false);
  const load = async () => {
    try {
      setAliases(await api(`/mailboxes/${box.id}/aliases`));
      setLoaded(true);
    } catch (e) {
      notify((e as Error).message);
    }
  };
  return (
    <details>
      <summary
        onClick={() => {
          if (!loaded) void load();
        }}
      >
        Receiving aliases
      </summary>
      <p className="help">
        Aliases deliver to this hosted mailbox. This does not grant send-as
        access. Requires the Stalwart management connection.
      </p>
      {aliases.map((a) => (
        <div className="integration-row" key={a.id}>
          <span>{a.email}</span>
          <button
            className="icon-button"
            title="Remove alias routing"
            onClick={async () => {
              try {
                await api(`/mailboxes/${box.id}/aliases/${a.id}`, {
                  method: "DELETE",
                });
                await load();
              } catch (e) {
                notify((e as Error).message);
              }
            }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post(`/mailboxes/${box.id}/aliases`, { email: address });
            setAddress("");
            await load();
            notify("Alias added to the mail server.");
          } catch (ex) {
            notify((ex as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Alias address
          <input
            type="email"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            required
            placeholder="sales@yourbusiness.com"
          />
        </label>
        <button className="secondary" disabled={busy}>
          Add receiving alias
        </button>
      </form>
    </details>
  );
}

function DnsRecordRow({
  type,
  host,
  value,
  current,
  ok,
  checked = false,
  notify,
}: {
  type: string;
  host: string;
  value: string;
  current: string;
  ok: boolean;
  checked?: boolean;
  onCheck: () => void;
  notify: (s: string) => void;
}) {
  const status = checked
    ? ok
      ? "Functional"
      : "Not functional"
    : "Not checked";
  const copy = (label: string, text: string) =>
    navigator.clipboard
      .writeText(text)
      .then(() => notify(label + " copied."))
      .catch(() => notify("Copy failed."));
  return (
    <div className="dns-guidance-row dns-record-row">
      <div className="dns-record-health">
        <input
          className="dns-status-checkbox"
          type="checkbox"
          checked={checked && ok}
          disabled
          aria-label={`${type} record: ${status}`}
        />
        <span
          className={
            checked ? (ok ? "functional" : "not-functional") : "unchecked"
          }
        >
          {status}
        </span>
      </div>
      <strong className="dns-record-type">{type}</strong>
      <div className="dns-record-fields">
        <div className="dns-record-field">
          <span>Name / prefix</span>
          <code>{host}</code>
          <button
            className="dns-copy-button"
            onClick={() => void copy("Record name", host)}
          >
            <Copy size={13} />
            Copy name
          </button>
        </div>
        <div className="dns-record-field">
          <span>Value</span>
          <code title={value}>{value}</code>
          <button
            className="dns-copy-button"
            onClick={() => void copy("Record value", value)}
          >
            <Copy size={13} />
            Copy value
          </button>
        </div>
        <small className="dns-record-current">
          Live DNS: {current || "No record found"}
        </small>
      </div>
    </div>
  );
}

function CatchallEditor({
  domain,
  boxes,
  notify,
}: {
  domain: { id: string; name: string };
  boxes: Mailbox[];
  notify: (s: string) => void;
}) {
  const [destination, setDestination] = useState("");
  const [active, setActive] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const targets = boxes.filter(
    (box) =>
      box.provider === "hosted" &&
      box.email.toLowerCase().endsWith("@" + domain.name.toLowerCase()),
  );
  const load = async () => {
    try {
      const current = await api(`/domains/${domain.id}/catchall`);
      setDestination(current.destination || "");
      setActive(Boolean(current.active && current.destination));
      setLoaded(true);
    } catch (e) {
      notify((e as Error).message);
    }
  };
  useEffect(() => {
    if (!loaded) void load();
  }, [domain.id]);
  const enable = async () => {
    if (!destination) return;
    setBusy(true);
    try {
      await api(`/domains/${domain.id}/catchall`, {
        method: "PUT",
        body: JSON.stringify({ destination }),
      });
      setActive(true);
      notify(`Catch-all enabled for ${domain.name}.`);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const disable = async () => {
    setBusy(true);
    try {
      await api(`/domains/${domain.id}/catchall`, { method: "DELETE" });
      setActive(false);
      notify(`Catch-all disabled for ${domain.name}.`);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="panel domain-card" style={{ marginTop: 16 }}>
      <div className="panel-heading">
        <div>
          <h3>* Catch-all mailbox</h3>
          <p className="help">
            Route any address sent to @{domain.name} into one hosted mailbox.
          </p>
        </div>
        <span className={"status-pill " + (active ? "good" : "")}>
          {active ? "Enabled" : "Disabled"}
        </span>
      </div>
      {targets.length ? (
        <div className="integration-row">
          <label style={{ flex: 1 }}>
            Deliver unmatched mail to
            <select
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              disabled={busy}
            >
              <option value="">Select a mailbox</option>
              {targets.map((box) => (
                <option key={box.id} value={box.email}>
                  {box.email}
                </option>
              ))}
            </select>
          </label>
          {active ? (
            <button className="secondary" onClick={disable} disabled={busy}>
              Disable catch-all
            </button>
          ) : (
            <button
              className="primary"
              onClick={enable}
              disabled={busy || !destination}
            >
              Enable catch-all
            </button>
          )}
        </div>
      ) : (
        <p className="help">
          Create a hosted mailbox for this domain first. Catch-all delivery
          stays disabled until a destination mailbox exists.
        </p>
      )}
    </div>
  );
}

export default function Admin({
  tab,
  setTab,
  boxes,
  user,
  demo,
  notify,
  refresh,
  logout,
  theme,
  setTheme,
  notificationsEnabled,
  enableNotifications,
  disableNotifications,
}: Props) {
  const [section, setSection] = useState("overview"),
    [modal, setModal] = useState(""),
    [selected, setSelected] = useState<Mailbox | null>(null),
    [records, setRecords] = useState<any[]>([]),
    [expandedDomain, setExpandedDomain] = useState<string | null>(null),
    [keys, setKeys] = useState<any[]>([]),
    [hooks, setHooks] = useState<any[]>([]),
    [deliveries, setDeliveries] = useState<any[]>([]),
    [grants, setGrants] = useState<any[]>([]),
    [adminBoxes, setAdminBoxes] = useState<{ id: string; email: string }[]>([]),
    [secret, setSecret] = useState(""),
    [mfa, setMfa] = useState(""),
    [working, setWorking] = useState(false),
    [editingGrant, setEditingGrant] = useState<any>(null),
    [defaultMailbox, setDefaultMailbox] = useState(
      user.default_mailbox_id || "",
    );
  useEffect(
    () => setDefaultMailbox(user.default_mailbox_id || ""),
    [user.default_mailbox_id],
  );
  const error = (e: unknown) => notify((e as Error).message);
  const load = async () => {
    try {
      if (tab === "automations") {
        const [k, h, d] = await Promise.all([
          api("/keys"),
          api("/webhooks"),
          api("/deliveries"),
        ]);
        setKeys(k);
        setHooks(h);
        setDeliveries(d);
      }
      if (tab === "domains") {
        const domains = await api("/domains");
        setRecords(domains);
        setExpandedDomain((current) =>
          current && domains.some((d: any) => d.id === current)
            ? current
            : domains[0]?.id || null,
        );
      }
      if (tab === "team") {
        setRecords(await api("/users"));
        setGrants(await api("/grants"));
        setAdminBoxes(await api("/admin/mailboxes"));
      }
      if (tab === "settings" && section === "audit")
        setRecords(await api("/audit"));
    } catch (e) {
      error(e);
    }
  };
  useEffect(() => {
    setRecords([]);
    setExpandedDomain(null);
    void load();
  }, [tab, section]);
  const submit = async (
    e: FormEvent<HTMLFormElement>,
    fn: (data: any) => Promise<unknown>,
  ) => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.currentTarget));
    setWorking(true);
    try {
      await fn(values);
      setModal("");
      await refresh();
      await load();
    } catch (ex) {
      error(ex);
    } finally {
      setWorking(false);
    }
  };
  const title =
    tab === "mailboxes"
      ? "Your mailboxes"
      : tab === "domains"
        ? "Domains"
        : tab === "team"
          ? "Your team"
          : tab === "automations"
            ? "Make mail work for you"
            : "Workspace settings";
  const desc =
    tab === "mailboxes"
      ? "Different businesses. One place to stay on top of them."
      : tab === "domains"
        ? "Verify ownership and keep an eye on your mail DNS."
        : tab === "team"
          ? "The right people, with exactly the access they need."
          : tab === "automations"
            ? "Connect your workflows with a private, permission-based API."
            : "A workspace that works the way you do.";
  return (
    <div className="admin-page">
      <div className="admin-heading">
        <div>
          <div className="heading-kicker">YOUR WORKSPACE, YOUR WAY</div>
          <h1>{title}</h1>
          <p>{desc}</p>
        </div>
        {user.role === "admin" &&
          ["mailboxes", "domains", "team"].includes(tab) && (
            <button
              className="primary"
              onClick={() =>
                setModal(
                  tab === "mailboxes"
                    ? "mailbox"
                    : tab === "domains"
                      ? "domain"
                      : "user",
                )
              }
            >
              <Plus size={17} /> Add{" "}
              {tab === "mailboxes"
                ? "mailbox"
                : tab === "domains"
                  ? "domain"
                  : "person"}
            </button>
          )}
      </div>
      <div className="admin-tabs">
        {[
          ["mailboxes", "Mailboxes", Mail],
          ["domains", "Domains", Globe],
          ["team", "Team", Users],
          ["automations", "Integrations", Workflow],
          ["settings", "Security & settings", Shield],
        ]
          .filter(
            ([id]) =>
              user.role === "admin" ||
              !["domains", "team"].includes(id as string),
          )
          .map(([id, name, Icon]: any) => (
            <button
              className={tab === id ? "active" : ""}
              key={id}
              onClick={() => setTab(id)}
            >
              <Icon size={16} />
              {name}
            </button>
          ))}
      </div>
      {tab === "mailboxes" && (
        <>
          <div className="info-callout">
            <Server size={21} />
            <div>
              <strong>
                {demo
                  ? "A look at your future workspace"
                  : "Connect once. Keep everything together."}
              </strong>
              <p>
                {demo
                  ? "These 10 fictional mailboxes show how three domains fit together. Live connections are disabled in sample mode."
                  : "Create hosted domains and mailboxes here. Postlane provisions them in Mailcow and connects them automatically."}
              </p>
            </div>
          </div>
          <div className="mailbox-grid">
            {boxes.map((b, i) => (
              <section className="account-card" key={b.id}>
                <header>
                  <span
                    className="account-icon"
                    style={{ color: b.color, background: b.color + "18" }}
                  >
                    <Mail size={22} />
                  </span>
                  <span
                    className={
                      "status-pill " + (b.status === "connected" ? "good" : "")
                    }
                  >
                    {b.status.replaceAll("_", " ")}
                  </span>
                </header>
                <h3>{b.name}</h3>
                <p>{b.email}</p>
                <span
                  className={
                    "mailbox-kind mailbox-kind-" +
                    (b.management_mode || "human")
                  }
                >
                  {b.management_mode === "ai"
                    ? "AI agent mailbox"
                    : b.management_mode === "shared"
                      ? "Shared team mailbox"
                      : "Human-managed mailbox"}
                </span>
                <div className="account-details">
                  <span>
                    {b.provider === "demo"
                      ? "Sample mailbox"
                      : b.provider.toUpperCase()}
                  </span>
                  <span>
                    <span className="tiny-dot" />
                    {b.unread} unread
                  </span>
                </div>
                {b.error && <p className="error-text">{b.error}</p>}
                <footer>
                  <button
                    className="text-button"
                    onClick={() => {
                      setSelected(b);
                      setModal("mailbox-settings");
                    }}
                  >
                    Manage mailbox <ChevronRight size={15} />
                  </button>
                  <button
                    className="icon-button"
                    title="Move mailbox up"
                    disabled={i === 0 || !b.can_write}
                    onClick={async () => {
                      try {
                        await patch("/mailboxes/" + b.id, {
                          position: Math.max(0, boxes[i - 1].position),
                        });
                        await patch("/mailboxes/" + boxes[i - 1].id, {
                          position: b.position,
                        });
                        await refresh();
                      } catch (e) {
                        error(e);
                      }
                    }}
                  >
                    <ArrowUp size={15} />
                  </button>
                  {user.role === "admin" && b.provider !== "demo" && (
                    <button
                      className="icon-button danger"
                      title="Delete mailbox"
                      onClick={async () => {
                        if (
                          !window.confirm(
                            `Delete ${b.email} from Postlane and Mailcow?`,
                          )
                        )
                          return;
                        try {
                          await api(`/mailboxes/${b.id}`, { method: "DELETE" });
                          await refresh();
                          notify("Mailbox deleted.");
                        } catch (e) {
                          error(e);
                        }
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </footer>
              </section>
            ))}
          </div>
          {!boxes.length && (
            <Empty
              title="Bring your first mailbox home"
              text="Add a hosted account, or connect a mailbox you already use."
            />
          )}
        </>
      )}
      {tab === "domains" && (
        <>
          <div className="info-callout">
            <ShieldCheck size={22} />
            <div>
              <strong>Domain verification and mail readiness</strong>
              <p>
                The table below shows the exact records Postlane expects and the
                values currently visible in DNS. Correct records at your DNS
                provider, then click Check DNS.
              </p>
            </div>
          </div>
          <div className="domain-list">
            {records.map((d) => {
              const open = expandedDomain === d.id;
              const checks = [
                "ownership",
                "mx",
                "spf",
                "dmarc",
                "dkim",
                "mail_host_a",
              ];
              const passed = checks.filter((key) =>
                key === "ownership"
                  ? d.verified
                  : key === "mail_host_a"
                    ? Boolean(d.dns?.[key]?.length)
                    : Boolean(d.dns?.[key + "_ok"]),
              ).length;
              return (
                <div key={d.id} className="domain-accordion">
                  <button
                    className={"domain-summary " + (open ? "open" : "")}
                    onClick={() => setExpandedDomain(open ? null : d.id)}
                    aria-expanded={open}
                  >
                    <span className="account-icon">
                      <Globe size={21} />
                    </span>
                    <span className="domain-summary-copy">
                      <strong>{d.name}</strong>
                      <small>
                        {d.verified
                          ? "Ownership verified"
                          : "Verification needed"}{" "}
                        · {passed}/{checks.length} checks passing
                      </small>
                    </span>
                    <span
                      className={"status-pill " + (d.verified ? "good" : "")}
                    >
                      {d.verified ? "Ready" : "Needs attention"}
                    </span>
                    <ChevronRight
                      className={
                        open ? "domain-chevron open" : "domain-chevron"
                      }
                      size={18}
                    />
                  </button>
                  {open && (
                    <>
                      <section className="panel domain-card domain-details">
                        <header>
                          <div>
                            <h3>{d.name}</h3>
                            <span
                              className={
                                "status-pill " + (d.verified ? "good" : "")
                              }
                            >
                              {d.verified
                                ? "Ownership verified"
                                : "Verification needed"}
                            </span>
                          </div>
                          <button
                            className="secondary"
                            onClick={async () => {
                              try {
                                await post(`/domains/${d.id}/verify`);
                                await load();
                                notify("DNS check complete.");
                              } catch (e) {
                                error(e);
                              }
                            }}
                          >
                            <RefreshCw size={15} /> Check DNS
                          </button>
                        </header>
                        <div className="dns-record">
                          <small>TXT · _postlane.{d.name}</small>
                          <code>postlane-verification={d.verification}</code>
                          <button
                            className="icon-button"
                            title="Copy verification value"
                            onClick={() =>
                              navigator.clipboard
                                .writeText(
                                  "postlane-verification=" + d.verification,
                                )
                                .then(() => notify("Copied."))
                                .catch(error)
                            }
                          >
                            <Copy size={15} />
                          </button>
                        </div>
                        <div className="dns-checks">
                          {["mx", "spf", "dmarc"].map((k) => (
                            <span key={k}>
                              <span
                                className={
                                  (d.dns?.[k + "_ok"] ??
                                  Boolean(d.dns?.[k]?.length))
                                    ? "check-good"
                                    : "check-pending"
                                }
                              >
                                {(d.dns?.[k + "_ok"] ??
                                Boolean(d.dns?.[k]?.length)) ? (
                                  <Check size={13} />
                                ) : (
                                  <span>—</span>
                                )}
                              </span>
                              {k.toUpperCase()}{" "}
                              {(d.dns?.[k + "_ok"] ??
                              Boolean(d.dns?.[k]?.length))
                                ? "pass"
                                : "missing / incorrect"}
                            </span>
                          ))}
                        </div>
                        <div className="dns-guidance">
                          <strong>Required DNS records</strong>
                          <p>
                            Copy each record name and value into your DNS
                            provider, then use Check DNS to refresh the results.
                          </p>
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="TXT"
                            host={`_postlane.${d.name}`}
                            value={`postlane-verification=${d.verification}`}
                            current={d.dns?.ownership?.join(" | ") || ""}
                            ok={d.verified}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="MX"
                            host={d.name}
                            value={`10 ${d.dns?.mx_expected || d.mail_host || "mail.example.com"}`}
                            current={d.dns?.mx?.join(" | ") || ""}
                            ok={Boolean(d.dns?.mx_ok ?? d.dns?.mx?.length)}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="TXT"
                            host={d.name}
                            value={
                              d.dns?.spf_expected ||
                              "v=spf1 ip4:YOUR_MAIL_SERVER_IP ~all"
                            }
                            current={d.dns?.spf?.join(" | ") || ""}
                            ok={Boolean(d.dns?.spf_ok ?? d.dns?.spf?.length)}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="TXT"
                            host={`_dmarc.${d.name}`}
                            value={
                              d.dns?.dmarc_expected ||
                              `v=DMARC1; p=none; rua=mailto:postmaster@${d.name}`
                            }
                            current={d.dns?.dmarc?.join(" | ") || ""}
                            ok={Boolean(
                              d.dns?.dmarc_ok ?? d.dns?.dmarc?.length,
                            )}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="TXT"
                            host={`${d.dns?.dkim_selector || "dkim"}._domainkey.${d.name}`}
                            value={
                              d.dns?.dkim_expected ||
                              "Generate the DKIM record in Mailcow first"
                            }
                            current={d.dns?.dkim?.join(" | ") || ""}
                            ok={Boolean(d.dns?.dkim_ok)}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                          <DnsRecordRow
                            checked={Boolean(d.dns?.checked_at)}
                            type="A"
                            host={d.mail_host || "mail.example.com"}
                            value="Public IP of this mail server"
                            current={d.dns?.mail_host_a?.join(" | ") || ""}
                            ok={Boolean(d.dns?.mail_host_a?.length)}
                            onCheck={() =>
                              post(`/domains/${d.id}/verify`).then(load)
                            }
                            notify={notify}
                          />
                        </div>
                      </section>
                      <CatchallEditor
                        domain={d}
                        boxes={boxes}
                        notify={notify}
                      />
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
      {tab === "team" && (
        <>
          <div className="panel">
            <div className="panel-heading">
              <h3>People in your workspace</h3>
              <button
                className="secondary"
                onClick={() => {
                  setEditingGrant(null);
                  setModal("grant");
                }}
              >
                <KeyRound size={15} /> Grant mailbox access
              </button>
            </div>
            {records.map((u) => (
              <div className="team-row" key={u.id}>
                <span className="avatar tone-0">{u.name[0]}</span>
                <div>
                  <strong>{u.name}</strong>
                  <small>{u.email}</small>
                </div>
                <span className="label">{u.role}</span>
                <span className="muted">
                  {u.mfa_enabled ? "2FA enabled" : "2FA not enabled"}
                </span>
                {u.id !== user.id && (
                  <button
                    className="secondary"
                    onClick={async () => {
                      if (
                        !window.confirm(
                          `${u.active ? "Disable" : "Enable"} ${u.email}? Disabling revokes sessions and keys and cancels queued sends.`,
                        )
                      )
                        return;
                      try {
                        await patch(`/users/${u.id}`, { active: !u.active });
                        await load();
                        notify("Account access updated.");
                      } catch (e) {
                        error(e);
                      }
                    }}
                  >
                    {u.active ? "Disable account" : "Enable account"}
                  </button>
                )}
              </div>
            ))}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <h3>Mailbox permissions</h3>
              <span className="muted">Read · Write · Send</span>
            </div>
            {grants.map((g) => (
              <div className="grant-row" key={g.id}>
                <div>
                  <strong>
                    {records.find((u) => u.id === g.user_id)?.name || g.user_id}
                  </strong>
                  <small>
                    {adminBoxes.find((b) => b.id === g.mailbox_id)?.email ||
                      g.mailbox_id}
                  </small>
                </div>
                <span className="label">
                  Read{g.can_write ? " · Write" : ""}
                  {g.can_send ? " · Send" : ""}
                </span>
                <button
                  className="secondary"
                  onClick={() => {
                    setEditingGrant(g);
                    setModal("grant");
                  }}
                >
                  Edit rights
                </button>
                <button
                  className="icon-button"
                  title="Revoke grant"
                  onClick={async () => {
                    try {
                      await api("/grants/" + g.id, { method: "DELETE" });
                      await load();
                      await refresh();
                      notify("Mailbox access revoked.");
                    } catch (e) {
                      error(e);
                    }
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </>
      )}
      {tab === "automations" && (
        <>
          <div className="integration-hero">
            <div>
              <span className="eyebrow">BUILT TO CONNECT</span>
              <h2>
                Your inbox is the beginning.
                <br />
                Your workflow takes it from there.
              </h2>
              <p>
                Route new messages to n8n, organize conversations, and create
                drafts for your team to review.
              </p>
              <a
                href="/api/admin/agent-documentation"
                target="_blank"
                rel="noreferrer"
                className="secondary"
              >
                Open private API documentation <ArrowUpRight size={16} />
              </a>
            </div>
            <div className="workflow-art">
              <span>
                <Mail size={28} />
              </span>
              <i />
              <span>
                <Workflow size={31} />
              </span>
              <i />
              <span>
                <Check size={26} />
              </span>
            </div>
          </div>
          <div className="integration-columns">
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h3>API keys</h3>
                  <p>Only the mailboxes and actions you allow.</p>
                </div>
                <button
                  className="icon-button"
                  title="Create API key"
                  onClick={() => setModal("key")}
                >
                  <Plus size={19} />
                </button>
              </div>
              {keys.length ? (
                keys.map((k) => (
                  <div className="integration-row" key={k.id}>
                    <KeyRound size={19} />
                    <div>
                      <strong>{k.name}</strong>
                      <small>
                        {k.prefix}•••• ·{" "}
                        {k.revoked
                          ? "Revoked"
                          : new Date(k.expires * 1000).toLocaleDateString()}
                      </small>
                      <small>{k.scopes.join(", ")}</small>
                    </div>
                    {!k.revoked && (
                      <button
                        className="icon-button"
                        title="Revoke key"
                        onClick={async () => {
                          try {
                            await api("/keys/" + k.id, { method: "DELETE" });
                            await load();
                          } catch (e) {
                            error(e);
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <div className="small-empty">
                  No API keys yet. Create one for your first workflow.
                </div>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h3>Webhook destinations</h3>
                  <p>Signed events. No email bodies in the payload.</p>
                </div>
                <button
                  className="icon-button"
                  title="Add webhook"
                  onClick={() => setModal("hook")}
                >
                  <Plus size={19} />
                </button>
              </div>
              {hooks.length ? (
                hooks.map((h) => (
                  <div className="integration-row" key={h.id}>
                    <Workflow size={18} />
                    <div>
                      <strong>
                        {boxes.find((b) => b.id === h.mailbox_id)?.email}
                      </strong>
                      <small>{h.url}</small>
                      <small>{h.active ? "Active" : "Disabled"}</small>
                    </div>
                    {h.active && (
                      <button
                        className="icon-button"
                        title="Disable webhook"
                        onClick={async () => {
                          try {
                            await api("/webhooks/" + h.id, {
                              method: "DELETE",
                            });
                            await load();
                          } catch (e) {
                            error(e);
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <div className="small-empty">
                  Connect an approved n8n webhook to get started.
                </div>
              )}
            </section>
          </div>
          <section className="panel">
            <div className="panel-heading">
              <h3>Recent webhook deliveries</h3>
              <button
                className="icon-button"
                title="Refresh delivery history"
                onClick={load}
              >
                <RefreshCw size={16} />
              </button>
            </div>
            {deliveries.length ? (
              deliveries.map((d) => (
                <div className="integration-row" key={d.id}>
                  <Activity size={16} />
                  <code>{d.id.slice(0, 12)}</code>
                  <span className="label">{d.status}</span>
                  <span className="muted">
                    {d.attempts} attempts · {d.response}
                  </span>
                </div>
              ))
            ) : (
              <div className="small-empty">
                Delivery attempts will appear here when events are emitted.
              </div>
            )}
          </section>
          <div className="info-callout">
            <ShieldCheck size={21} />
            <div>
              <strong>Automation prepares. Your team approves.</strong>
              <p>
                API-created drafts require human approval. Automation
                credentials cannot send messages or approve drafts. Webhook
                endpoints must be allowlisted by your server operator.
              </p>
            </div>
          </div>
        </>
      )}
      {tab === "settings" && (
        <>
          <div className="settings-subnav">
            <button
              className={section === "overview" ? "active" : ""}
              onClick={() => setSection("overview")}
            >
              General & security
            </button>
            <button
              className={section === "spam" ? "active" : ""}
              onClick={() => setSection("spam")}
            >
              Spam
            </button>
            {user.role === "admin" && (
              <button
                className={section === "audit" ? "active" : ""}
                onClick={() => setSection("audit")}
              >
                Audit history
              </button>
            )}
          </div>
          {section === "spam" ? (
            <div className="settings-grid">
              <SpamManager boxes={boxes} notify={notify} />
              <SpamRules boxes={boxes} notify={notify} />
            </div>
          ) : section === "audit" ? (
            <div className="panel">
              {records.map((r) => (
                <div className="audit-row" key={r.id}>
                  <ShieldCheck size={16} />
                  <div>
                    <strong>{r.action.replaceAll(".", " · ")}</strong>
                    <small>{r.actor}</small>
                  </div>
                  <time>{new Date(r.at * 1000).toLocaleString()}</time>
                </div>
              ))}
            </div>
          ) : (
            <div className="settings-grid">
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h3>Appearance</h3>
                    <p>Choose a colour theme for this browser.</p>
                  </div>
                </div>
                <div className="settings-body">
                  <label>
                    Colour theme
                    <select
                      value={theme}
                      onChange={(e) =>
                        setTheme(e.target.value as Props["theme"])
                      }
                    >
                      <option value="light">Light</option>
                      <option value="liquid">Liquid Glass</option>
                      <option value="midnight">Midnight</option>
                    </select>
                  </label>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h3>Default sending mailbox</h3>
                    <p>New messages will start from this address.</p>
                  </div>
                  <Mail size={20} />
                </div>
                <div className="settings-body">
                  <select
                    value={defaultMailbox}
                    onChange={(e) => setDefaultMailbox(e.target.value)}
                  >
                    <option value="">Choose automatically</option>
                    {boxes
                      .filter((box) => box.can_send)
                      .map((box) => (
                        <option value={box.id} key={box.id}>
                          {box.email}
                        </option>
                      ))}
                  </select>
                  <button
                    className="primary"
                    disabled={working}
                    onClick={async () => {
                      setWorking(true);
                      try {
                        await patch("/account/preferences", {
                          default_mailbox_id: defaultMailbox,
                        });
                        await refresh();
                        notify(
                          defaultMailbox
                            ? "Default sending mailbox saved."
                            : "Automatic mailbox selection restored.",
                        );
                      } catch (e) {
                        error(e);
                      } finally {
                        setWorking(false);
                      }
                    }}
                  >
                    Save default
                  </button>
                </div>
              </section>
              {user.role === "admin" && user.mfa_enabled && (
                <Installation notify={notify} />
              )}
              <PasswordSettings notify={notify} />
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h3>Email notifications</h3>
                    <p>Get a device notification when new mail arrives.</p>
                  </div>
                  <Bell size={20} />
                </div>
                <div className="settings-body">
                  <div className="environment-row">
                    <span>This device</span>
                    <strong>{notificationsEnabled ? "Enabled" : "Off"}</strong>
                  </div>
                  <button
                    className={notificationsEnabled ? "secondary" : "primary"}
                    onClick={() =>
                      void (notificationsEnabled
                        ? disableNotifications()
                        : enableNotifications())
                    }
                  >
                    <Bell size={16} />{" "}
                    {notificationsEnabled
                      ? "Turn off notifications"
                      : "Enable notifications"}
                  </button>
                  <p className="help">
                    This setting applies to the current browser or installed PWA
                    only.
                  </p>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h3>Your account</h3>
                  <span className="label">{user.role}</span>
                </div>
                <div className="settings-body">
                  <label>
                    Name<strong>{user.name}</strong>
                  </label>
                  <label>
                    Email<strong>{user.email}</strong>
                  </label>
                  <button
                    className="secondary"
                    onClick={() => logout().catch(error)}
                  >
                    <LogOut size={16} /> Sign out
                  </button>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h3>Two-factor authentication</h3>
                  <ShieldCheck size={20} />
                </div>
                <div className="settings-body">
                  <p>
                    Add a second layer of protection with an authenticator app.
                    Required for production administrators.
                  </p>
                  {user.mfa_enabled ? (
                    <>
                      <div className="environment-row">
                        <span>Status</span>
                        <strong>Enabled</strong>
                      </div>
                      <button
                        className="secondary"
                        onClick={() => setModal("mfa-disable")}
                      >
                        Disconnect authenticator
                        <ArrowUpRight size={15} />
                      </button>
                    </>
                  ) : (
                    <button
                      className="secondary"
                      onClick={async () => {
                        try {
                          const s = await post("/auth/mfa/setup");
                          setMfa(s.secret);
                          setModal("mfa");
                        } catch (e) {
                          error(e);
                        }
                      }}
                    >
                      Set up authenticator
                      <ArrowUpRight size={15} />
                    </button>
                  )}
                </div>
              </section>
              <section className="panel privacy-panel">
                <div className="panel-heading">
                  <h3>AI privacy</h3>
                  <Sparkles size={20} />
                </div>
                <div className="settings-body">
                  <p>
                    External AI starts off for every mailbox. Only an
                    administrator can enable it. Generated replies always
                    require review and approval.
                  </p>
                  <div className="privacy-item">
                    <Check size={16} /> No mailbox-wide AI access
                  </div>
                  <div className="privacy-item">
                    <Check size={16} /> No attachments sent to AI
                  </div>
                  <div className="privacy-item">
                    <Check size={16} /> No autonomous replies
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setTab("mailboxes")}
                  >
                    Manage per-mailbox settings <ArrowUpRight size={15} />
                  </button>
                </div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h3>Postlane by CloudMonkey</h3>
                  <Server size={20} />
                </div>
                <div className="settings-body">
                  <p>
                    Created by CloudMonkey. One private installation, with
                    separate storage, credentials, and configuration for your
                    business.
                  </p>
                  <div className="environment-row">
                    <span>Workspace</span>
                    <strong>
                      {demo ? "Sample / local" : "Private installation"}
                    </strong>
                  </div>
                  <div className="environment-row">
                    <span>Mailboxes</span>
                    <strong>{boxes.length}</strong>
                  </div>
                  <div className="environment-row">
                    <span>Folders & labels</span>
                    <strong>Workspace only</strong>
                  </div>
                  <div className="environment-row">
                    <span>Version</span>
                    <strong>0.3.0</strong>
                  </div>
                </div>
              </section>
            </div>
          )}
        </>
      )}
      {modal && (
        <Modal
          title={
            {
              mailbox: "Add a mailbox",
              domain: "Add your domain",
              user: "Invite a team member",
              grant: "Grant mailbox access",
              key: "Create an API key",
              hook: "Connect a webhook",
              "mailbox-settings": "Mailbox settings",
              mfa: "Protect your account",
              "mfa-disable": "Disconnect authenticator",
            }[modal] || modal
          }
          close={() => setModal("")}
        >
          {modal === "mailbox" && (
            <form
              className="stack-form"
              onSubmit={(e) => submit(e, (d) => post("/mailboxes", d))}
            >
              <label>
                Display name
                <input
                  name="name"
                  required
                  placeholder="e.g. Northstar sales"
                />
              </label>
              <label>
                Email address
                <input name="email" type="email" required />
              </label>
              <label>
                Management type
                <select name="management_mode" defaultValue="human">
                  <option value="human">Human-managed mailbox</option>
                  <option value="shared">Shared team mailbox</option>
                  <option value="ai">AI agent mailbox</option>
                </select>
              </label>
              <label>
                Account type
                <select name="provider">
                  <option value="hosted">Hosted on our mail server</option>
                  <option value="gmail">Google / Gmail</option>
                  <option value="microsoft">Microsoft 365 / Outlook</option>
                  <option value="imap">Other IMAP account</option>
                </select>
              </label>
              <p className="help">
                Hosted accounts are created and connected automatically in
                Mailcow. Postlane generates and securely stores the mailbox
                password. Google and Microsoft require OAuth app credentials
                configured by your operator.
              </p>
              <button className="primary" disabled={working || demo}>
                Add mailbox
              </button>
            </form>
          )}
          {modal === "domain" && (
            <form
              className="stack-form"
              onSubmit={(e) => submit(e, (d) => post("/domains", d))}
            >
              <label>
                Domain name
                <input name="name" required placeholder="yourbusiness.com" />
              </label>
              <button className="primary" disabled={working}>
                Add domain
              </button>
            </form>
          )}
          {modal === "user" && (
            <form
              className="stack-form"
              onSubmit={(e) =>
                submit(e, (d) =>
                  post("/users", {
                    name: d.name,
                    email: d.email,
                    password: d.password,
                    role: d.role,
                    grants: adminBoxes.flatMap((b) => {
                      const permission = d["access_" + b.id];
                      return !permission || permission === "none"
                        ? []
                        : [
                            {
                              mailbox_id: b.id,
                              can_write:
                                permission === "write" || permission === "send",
                              can_send: permission === "send",
                            },
                          ];
                    }),
                  }),
                )
              }
            >
              <label>
                Full name
                <input name="name" required />
              </label>
              <label>
                Email
                <input type="email" name="email" required />
              </label>
              <label>
                Initial password
                <input
                  name="password"
                  type="password"
                  minLength={14}
                  required
                  autoComplete="new-password"
                />
              </label>
              <label>
                Role
                <select name="role">
                  <option value="member">Team member</option>
                  <option value="admin">Administrator</option>
                </select>
              </label>
              <fieldset className="initial-mailbox-access">
                <legend>Initial mailbox access</legend>
                <p className="help">
                  No access is granted by default. Shared mailboxes can be
                  assigned to multiple people.
                </p>
                {adminBoxes.map((b) => (
                  <label key={b.id}>
                    {b.email}
                    <select name={"access_" + b.id} defaultValue="none">
                      <option value="none">No access</option>
                      <option value="read">Read only</option>
                      <option value="write">Read and organize / draft</option>
                      <option value="send">Read, organize and send</option>
                    </select>
                  </label>
                ))}
              </fieldset>
              <p className="help">
                Share credentials through a secure channel. This creates a
                workspace user; mailbox access is granted separately.
              </p>
              <button className="primary" disabled={working}>
                Create user
              </button>
            </form>
          )}
          {modal === "grant" && (
            <form
              className="stack-form"
              onSubmit={(e) =>
                submit(e, (d) =>
                  post("/grants", {
                    ...d,
                    can_write: d.can_write === "on",
                    can_send: d.can_send === "on",
                  }),
                )
              }
            >
              {editingGrant && (
                <>
                  <input
                    type="hidden"
                    name="user_id"
                    value={editingGrant.user_id}
                  />
                  <input
                    type="hidden"
                    name="mailbox_id"
                    value={editingGrant.mailbox_id}
                  />
                </>
              )}
              <label>
                Person
                <select
                  name="user_id"
                  defaultValue={editingGrant?.user_id}
                  disabled={Boolean(editingGrant)}
                >
                  {records.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Mailbox
                <select
                  name="mailbox_id"
                  defaultValue={editingGrant?.mailbox_id}
                  disabled={Boolean(editingGrant)}
                >
                  {adminBoxes.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.email}
                    </option>
                  ))}
                </select>
              </label>
              <label className="check-label">
                <input
                  name="can_write"
                  type="checkbox"
                  defaultChecked={editingGrant ? editingGrant.can_write : true}
                />{" "}
                Organize messages and create drafts
              </label>
              <label className="check-label">
                <input
                  name="can_send"
                  type="checkbox"
                  defaultChecked={editingGrant?.can_send || false}
                />{" "}
                Send from this mailbox
              </label>
              <button className="primary" disabled={working}>
                Save access
              </button>
            </form>
          )}
          {modal === "key" && (
            <form
              className="stack-form"
              onSubmit={(e) =>
                submit(e, async (d) => {
                  const k = await post("/keys", {
                    name: d.name,
                    mailbox_ids: [d.mailbox_id],
                    scopes:
                      d.scope === "send"
                        ? ["messages:read", "mail:send"]
                        : d.scope === "write"
                          ? ["messages:read", "messages:write", "drafts:write"]
                          : ["messages:read"],
                    days: 90,
                  });
                  setSecret(k.token);
                })
              }
            >
              <label>
                Key name
                <input
                  name="name"
                  required
                  placeholder="n8n invoice workflow"
                />
              </label>
              <label>
                Mailbox
                <select name="mailbox_id" required defaultValue="">
                  <option value="" disabled>
                    Select a specific mailbox
                  </option>
                  {user.role === "admin" && (
                    <option value="*">
                      All current and future mailboxes (broad access)
                    </option>
                  )}
                  {boxes.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.email}
                      {b.management_mode === "ai"
                        ? " · AI agent mailbox"
                        : b.management_mode === "shared"
                          ? " · Shared"
                          : " · Human"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Permissions
                <select name="scope">
                  <option value="read">Read messages</option>
                  <option value="write">
                    Read, organize, and create drafts
                  </option>
                  <option value="send">
                    Read and send mail (AI-only mailboxes)
                  </option>
                </select>
              </label>
              <p className="help">
                Expires after 90 days. The full key is shown only once. Send and
                approval permissions are granted only when explicitly selected.
                Direct API sending requires an AI-only mailbox with agent
                sending enabled. Human and shared mailboxes require
                human-controlled sending. All-mailbox keys automatically include
                mailboxes added later.
              </p>
              <button className="primary" disabled={working}>
                Create key
              </button>
            </form>
          )}
          {modal === "hook" && (
            <form
              className="stack-form"
              onSubmit={(e) =>
                submit(e, async (d) => {
                  const h = await post("/webhooks", d);
                  setSecret(h.secret);
                })
              }
            >
              <label>
                Mailbox
                <select name="mailbox_id">
                  {boxes.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.email}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Webhook URL
                <input
                  name="url"
                  type="url"
                  required
                  placeholder="https://n8n.example.com/webhook/mail"
                />
              </label>
              <p className="help">
                The server operator must approve this origin. Verify
                X-Postlane-Signature and X-Postlane-Timestamp before processing
                an event.
              </p>
              <button className="primary" disabled={working}>
                Connect webhook
              </button>
            </form>
          )}
          {modal === "mailbox-settings" && selected && (
            <div className="stack-form">
              <div className="selected-mailbox">
                <Mail size={21} />
                <strong>{selected.email}</strong>
              </div>
              <form
                className="stack-form"
                onSubmit={(e) =>
                  submit(e, (d) =>
                    patch("/mailboxes/" + selected.id, {
                      name: d.name,
                      signature: d.signature,
                      signature_html: d.signature_html,
                      logo_url: d.logo_url,
                      ...(user.role === "admin"
                        ? {
                            ai_enabled: d.ai_enabled === "on",
                            management_mode: d.management_mode,
                            ai_send_enabled:
                              d.management_mode === "ai" &&
                              d.ai_send_enabled === "on",
                          }
                        : {}),
                    }),
                  )
                }
              >
                <label>
                  Display name
                  <input name="name" defaultValue={selected.name} required />
                </label>
                {user.role === "admin" && (
                  <>
                    <label>
                      Management type
                      <select
                        name="management_mode"
                        value={selected.management_mode || "human"}
                        onChange={(e) =>
                          setSelected({
                            ...selected,
                            management_mode: e.target.value as
                              "human" | "shared" | "ai",
                          })
                        }
                      >
                        <option value="human">Human-managed mailbox</option>
                        <option value="shared">Shared team mailbox</option>
                        <option value="ai">AI agent mailbox</option>
                      </select>
                    </label>
                    {selected.management_mode === "ai" && (
                      <label className="check-label">
                        <input
                          type="checkbox"
                          name="ai_send_enabled"
                          defaultChecked={selected.ai_send_enabled}
                        />
                        Allow explicitly send-enabled API agents to send without
                        human approval
                      </label>
                    )}
                    <p className="help">
                      A category never grants access. Use Team to assign people
                      and Integrations to issue a separately scoped key for each
                      agent. AI sending stays off until explicitly enabled.
                    </p>
                  </>
                )}
                <label>
                  Signature
                  <textarea
                    name="signature"
                    defaultValue={selected.signature}
                    rows={3}
                  />
                </label>
                <label>
                  Company logo URL
                  <input
                    name="logo_url"
                    type="url"
                    defaultValue={selected.logo_url}
                    placeholder="https://your-domain.example/logo.png"
                  />
                  <span className="help">Use an HTTPS image URL.</span>
                </label>
                <label>
                  Rich signature HTML
                  <textarea
                    name="signature_html"
                    defaultValue={selected.signature_html}
                    rows={5}
                    placeholder="<strong>Your Company</strong><br>Phone: ..."
                  />
                  <span className="help">
                    HTML is sanitized before storage and sending.
                  </span>
                </label>
                {user.role === "admin" && (
                  <label className="check-label">
                    <input
                      type="checkbox"
                      name="ai_enabled"
                      defaultChecked={selected.ai_enabled}
                    />{" "}
                    Allow external AI for this mailbox
                  </label>
                )}
                <p className="help">
                  When enabled, requesting an AI draft sends the selected
                  message text to the operator’s configured provider.
                  Attachments and other mailboxes are excluded.
                </p>
                <button
                  className="primary"
                  disabled={working || !selected.can_write}
                >
                  Save settings
                </button>
              </form>
              {user.role === "admin" && selected.provider === "hosted" && (
                <AliasEditor box={selected} notify={notify} />
              )}{" "}
              {user.role === "admin" && selected.provider !== "demo" && (
                <>
                  <hr />
                  {["gmail", "microsoft"].includes(selected.provider) ? (
                    <button
                      className="secondary"
                      onClick={async () => {
                        try {
                          const r = await post(
                            `/mailboxes/${selected.id}/oauth`,
                          );
                          window.location.assign(r.url);
                        } catch (e) {
                          error(e);
                        }
                      }}
                    >
                      Authorize{" "}
                      {selected.provider === "gmail" ? "Google" : "Microsoft"}{" "}
                      account <ExternalLink size={16} />
                    </button>
                  ) : (
                    <details>
                      <summary>IMAP & SMTP connection</summary>
                      <form
                        className="stack-form"
                        onSubmit={(e) =>
                          submit(e, (d) =>
                            post(`/mailboxes/${selected.id}/connection`, {
                              ...d,
                              imap_port: Number(d.imap_port),
                              smtp_port: Number(d.smtp_port),
                            }),
                          )
                        }
                      >
                        <label>
                          IMAP host
                          <input
                            name="imap_host"
                            required
                            placeholder="mail.yourbusiness.com"
                          />
                        </label>
                        <label>
                          IMAP TLS port
                          <input
                            name="imap_port"
                            type="number"
                            defaultValue={993}
                            required
                          />
                        </label>
                        <label>
                          SMTP host
                          <input
                            name="smtp_host"
                            required
                            placeholder="mail.yourbusiness.com"
                          />
                        </label>
                        <label>
                          SMTP TLS port
                          <select name="smtp_port">
                            <option value="465">465 · implicit TLS</option>
                            <option value="587">587 · required STARTTLS</option>
                          </select>
                        </label>
                        <label>
                          Username
                          <input
                            name="username"
                            defaultValue={selected.email}
                            required
                          />
                        </label>
                        <label>
                          Password / app password
                          <input
                            name="password"
                            type="password"
                            required
                            autoComplete="new-password"
                          />
                        </label>
                        <p className="help">
                          Hosts must be approved in MAIL_ALLOWED_HOSTS.
                          Certificates must be trusted; TLS verification cannot
                          be disabled.
                        </p>
                        <button className="primary" disabled={working}>
                          Save connection
                        </button>
                      </form>
                    </details>
                  )}
                </>
              )}
            </div>
          )}
          {modal === "mfa" && (
            <form
              className="stack-form"
              onSubmit={(e) =>
                submit(e, async (d) => {
                  await post("/auth/mfa/confirm", d);
                  notify(
                    "Two-factor authentication enabled. Sign in again to refresh your session.",
                  );
                  await logout();
                })
              }
            >
              <p>
                Add a time-based account in your authenticator app using this
                secret:
              </p>
              <code className="secret-value">{mfa}</code>
              <label>
                Current 6-digit code
                <input
                  name="code"
                  required
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  autoComplete="one-time-code"
                />
              </label>
              <p className="help">
                Store the secret in your password manager for recovery. Keep
                your Ubuntu administrative access available.
              </p>
              <button className="primary" disabled={working}>
                Enable two-factor authentication
              </button>
            </form>
          )}
          {modal === "mfa-disable" && (
            <form
              className="stack-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.currentTarget));
                setWorking(true);
                try {
                  await post("/auth/mfa/disable", data);
                  notify(
                    "Authenticator disconnected. Sign in again, then reconnect it from Settings.",
                  );
                  await logout();
                } catch (ex) {
                  error(ex);
                } finally {
                  setWorking(false);
                }
              }}
            >
              <p>
                Confirm your password and current authenticator code to
                disconnect 2FA. You will be signed out and can reconnect a new
                authenticator after signing in again.
              </p>
              <label>
                Current password
                <input
                  name="current_password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </label>
              <label>
                Current 6-digit code
                <input
                  name="code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  autoComplete="one-time-code"
                  maxLength={6}
                  required
                />
              </label>
              <button className="primary" disabled={working}>
                {working ? "Disconnecting..." : "Disconnect 2FA"}
              </button>
            </form>
          )}
        </Modal>
      )}
      {secret && (
        <Modal title="Save this secret now" close={() => setSecret("")}>
          <p>
            This value will not be displayed again. Store it in your n8n
            credentials or password manager.
          </p>
          <code className="secret-value">{secret}</code>
          <button
            className="primary"
            onClick={() =>
              navigator.clipboard
                .writeText(secret)
                .then(() => notify("Secret copied."))
                .catch(error)
            }
          >
            <Copy size={16} /> Copy secret
          </button>
        </Modal>
      )}
    </div>
  );
}
