import { useEffect, useState, useCallback, useRef, FormEvent } from "react";
import {
  Inbox,
  Search,
  Plus,
  Star,
  Clock,
  Send,
  FileText,
  Archive,
  Trash2,
  ChevronDown,
  ChevronRight,
  ArrowUpRight,
  Settings,
  Command,
  Mail,
  MoreHorizontal,
  SlidersHorizontal,
  RefreshCw,
  ArrowLeft,
  ArrowRight,
  Reply,
  Forward,
  ShieldCheck,
  Globe,
  Users,
  Workflow,
  Sparkles,
  X,
  Check,
  LogOut,
  Folder as FolderIcon,
  Paperclip,
  CheckCheck,
  PanelLeft,
  Tag,
  Shield,
  KeyRound,
  Copy,
  ExternalLink,
  MoveRight,
  Bell,
  WifiOff,
  Ban,
  Lock,
  LoaderCircle,
  AlertCircle,
  Eye,
} from "lucide-react";
import {
  api,
  post,
  patch,
  setCsrf,
  User,
  Mailbox,
  Message,
  Attachment,
  Draft,
  Folder,
} from "./api";
import Admin from "./Admin";
import Work from "./Work";

const navigation = [
  ["inbox", "Inbox", Inbox],
  ["starred", "Starred", Star],
  ["snoozed", "Snoozed", Clock],
  ["sent", "Sent", Send],
  ["drafts", "Drafts", FileText],
  ["archive", "Archive", Archive],
  ["trash", "Trash", Trash2],
] as const;
type AppTheme = "light" | "liquid" | "midnight";
const initials = (name: string) =>
  name
    .replace(/<.*>/, "")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
const senderName = (sender: string) =>
  sender.replace(/<.*>/, "").replaceAll('"', "").trim() || sender;
const address = (sender: string) => sender.match(/<([^>]+)>/)?.[1] || sender;
const formatTime = (time: number) => {
  const date = new Date(time * 1000);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString([], {
        day: "numeric",
        month: "short",
        ...(date.getFullYear() !== today.getFullYear()
          ? { year: "numeric" }
          : {}),
      });
};
const formatBytes = (size: number) =>
  size < 1024 * 1024
    ? `${Math.max(1, Math.round(size / 1024))} KB`
    : `${(size / (1024 * 1024)).toFixed(1)} MB`;

const vapidBytes = (value: string) => {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
};

export default function App() {
  const [session, setSession] = useState<{
      user: User;
      demo: boolean;
      mfa_required?: boolean;
      offline?: boolean;
    } | null>(null),
    [ready, setReady] = useState(false),
    [setup, setSetup] = useState(false),
    [demo, setDemo] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [mailboxMode, setMailboxMode] = useState<
    "human" | "shared" | "ai" | "all"
  >(() => {
    const value = localStorage.getItem("postlane_mailbox_mode");
    return value === "ai" || value === "shared" || value === "all"
      ? value
      : "human";
  });
  useEffect(() => {
    localStorage.setItem("postlane_mailbox_mode", mailboxMode);
  }, [mailboxMode]);
  const [boxes, setBoxes] = useState<Mailbox[]>([]),
    [folders, setFolders] = useState<Folder[]>([]),
    [messages, setMessages] = useState<Message[]>([]),
    [drafts, setDrafts] = useState<Draft[]>([]);
  const [folder, setFolder] = useState("inbox"),
    [mailbox, setMailbox] = useState(""),
    [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [total, setTotal] = useState(0),
    [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Message | null>(null),
    [checked, setChecked] = useState<string[]>([]),
    [tab, setTab] = useState("mail"),
    [compose, setCompose] = useState<Partial<Draft> | null>(null);
  const [swipeAction, setSwipeAction] = useState<{
    id: string;
    direction: "read" | "trash";
  } | null>(null);
  const [swipeOffset, setSwipeOffset] = useState<{
    id: string;
    value: number;
  } | null>(null);
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [sideOpen, setSideOpen] = useState(false),
    [filter, setFilter] = useState(false),
    [onlyUnread, setOnlyUnread] = useState(false),
    [newFolder, setNewFolder] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false),
    [offline, setOffline] = useState(!navigator.onLine);
  const [launchShortcut, setLaunchShortcut] = useState(
    () => new URLSearchParams(window.location.search).get("shortcut") || "",
  );
  const [theme, setTheme] = useState<AppTheme>(() => {
    const saved = localStorage.getItem("postlane_theme");
    return saved === "liquid" || saved === "midnight" ? saved : "light";
  });
  const searchRef = useRef<HTMLInputElement>(null);
  const rowSwipe = useRef<{ id: string; x: number; y: number } | null>(null);
  const notify = useCallback((s: string) => setNotice(s), []);
  useEffect(() => {
    localStorage.setItem("postlane_theme", theme);
  }, [theme]);
  const enablePush = useCallback(async () => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      notify("This browser does not support device notifications.");
      return;
    }
    try {
      const permission =
        Notification.permission === "granted"
          ? "granted"
          : await Notification.requestPermission();
      if (permission !== "granted") {
        notify("Notifications are blocked for this browser.");
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      const key = await api<{ public_key: string }>("/push/public-key");
      const subscription =
        (await registration.pushManager.getSubscription()) ||
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: vapidBytes(key.public_key),
        }));
      const json = subscription.toJSON();
      await api("/push/subscriptions", {
        method: "POST",
        body: JSON.stringify({
          endpoint: json.endpoint,
          p256dh: json.keys?.p256dh,
          auth: json.keys?.auth,
          device: navigator.userAgent.slice(0, 120),
        }),
      });
      setPushEnabled(true);
      await registration.showNotification("Postlane notifications enabled", {
        body: "This device will alert you when new mail arrives.",
        icon: "/branding/postlane-icon-192.png",
        tag: "postlane-notification-test",
      });
      notify("Notifications enabled on this device.");
    } catch (e) {
      notify((e as Error).message || "Could not enable notifications.");
    }
  }, [notify]);
  const disablePush = useCallback(async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        const json = subscription.toJSON();
        if (json.endpoint && json.keys?.p256dh && json.keys?.auth) {
          await api("/push/subscriptions", {
            method: "DELETE",
            body: JSON.stringify({
              endpoint: json.endpoint,
              p256dh: json.keys.p256dh,
              auth: json.keys.auth,
              device: navigator.userAgent.slice(0, 120),
            }),
          });
        }
        await subscription.unsubscribe();
      }
      setPushEnabled(false);
      notify("Email notifications turned off on this device.");
    } catch (e) {
      notify((e as Error).message || "Could not turn off notifications.");
    }
  }, [notify]);
  const reloadBoxes = useCallback(async () => {
    const [b, f] = await Promise.all([
      api<Mailbox[]>("/mailboxes"),
      api<Folder[]>("/folders"),
    ]);
    setBoxes(b);
    setFolders(f);
  }, []);
  const refreshSequence = useRef(0);
  useEffect(() => {
    const box = boxes.find((b) => b.id === mailbox);
    const matches =
      !box ||
      mailboxMode === "all" ||
      (mailboxMode === "human"
        ? box.management_mode !== "ai"
        : (box.management_mode || "human") === mailboxMode);
    if (box && !matches) {
      refreshSequence.current += 1;
      setMailbox("");
      setSelected(null);
      setChecked([]);
      setMessages([]);
      setTotal(0);
      setOffset(0);
    }
  }, [boxes, mailbox, mailboxMode]);

  const refresh = useCallback(async () => {
    if (!session || session.mfa_required) return;
    const sequence = ++refreshSequence.current;
    try {
      const [list, ds, current] = await Promise.all([
        api<{ items: Message[]; total: number }>(
          `/messages?folder=${encodeURIComponent(folder === "drafts" ? "inbox" : folder)}&mailbox_id=${mailbox}&management_mode=${mailboxMode}&q=${encodeURIComponent(search)}&offset=${offset}`,
        ),
        api<Draft[]>(`/drafts?management_mode=${mailboxMode}`),
        api<{ user: User }>("/auth/me"),
      ]);
      if (sequence !== refreshSequence.current) return;
      if (current.user.default_mailbox_id !== session.user.default_mailbox_id) {
        setSession((previous) =>
          previous ? { ...previous, user: current.user } : previous,
        );
      }
      setMessages(list.items);
      setTotal(list.total);
      setDrafts(ds);
      await reloadBoxes();
    } catch (e) {
      notify((e as Error).message);
    }
  }, [
    session,
    folder,
    mailbox,
    mailboxMode,
    search,
    offset,
    reloadBoxes,
    notify,
  ]);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("work")) setTab("work");
    const boot = async () => {
      // On iOS Home Screen apps, wait for the worker to control the page before
      // making the first API requests so the authenticated shell can be cached.
      if ("serviceWorker" in navigator) {
        try {
          const registration = await navigator.serviceWorker.register("/sw.js");
          // Check on every app launch so an installed PWA does not remain on
          // an older cached shell after a deployment.
          await registration.update();
          await navigator.serviceWorker.ready;
        } catch (_) {}
      }
      try {
        const status = await api("/auth/status");
        setSetup(status.setup_required);
        setDemo(status.demo);
        const s = await api("/auth/me");
        setCsrf(s.csrf);
        setSession(s);
        const shortcut = new URLSearchParams(window.location.search).get(
          "shortcut",
        );
        if (shortcut === "assistant") setTab("work");
        if (shortcut === "inbox") setTab("mail");
        if (s.user && !s.mfa_required)
          localStorage.setItem("postlane_offline_user", JSON.stringify(s.user));
      } catch (error) {
        // The normal session is now long-lived, but older sessions may still
        // expire after the previous 12-hour limit. Recover those sessions
        // through the trusted 30-day device cookie before showing sign-in.
        if (
          navigator.onLine &&
          ((error as Error & { status?: number }).status === 401 ||
            (error as Error & { status?: number }).status === 403)
        ) {
          try {
            const s = await post("/auth/refresh", {});
            setCsrf(s.csrf);
            setSession({ ...s, offline: false });
            setOffline(false);
            if (s.user && !s.mfa_required)
              localStorage.setItem(
                "postlane_offline_user",
                JSON.stringify(s.user),
              );
            return;
          } catch (_) {}
        }
        const cachedUser = localStorage.getItem("postlane_offline_user");
        const serverRejectedSession =
          (error as Error & { status?: number }).status === 401 ||
          (error as Error & { status?: number }).status === 403;
        if (cachedUser && (!navigator.onLine || !serverRejectedSession)) {
          try {
            setSession({
              user: JSON.parse(cachedUser),
              demo: false,
              offline: true,
            });
            setOffline(true);
          } catch (_) {}
        }
      } finally {
        setReady(true);
      }
    };
    void boot();
  }, []);
  useEffect(() => {
    let reconnecting = false;
    const reconnect = async () => {
      setOffline(false);
      if (reconnecting) return;
      reconnecting = true;
      try {
        // A cached offline session is only a local display session. Once the
        // network returns, validate it and restore the server session before
        // allowing live mailbox actions again.
        const status = await api<{ setup_required: boolean; demo: boolean }>(
          "/auth/status",
        );
        setSetup(status.setup_required);
        setDemo(status.demo);
        const current = await api<{
          user: User;
          csrf: string;
          mfa_required?: boolean;
        }>("/auth/me");
        setCsrf(current.csrf);
        setSession({ ...current, demo: status.demo });
        if (current.user && !current.mfa_required)
          localStorage.setItem(
            "postlane_offline_user",
            JSON.stringify(current.user),
          );
        notify("Connection restored.");
      } catch (error) {
        // A live server response means the cached session is no longer valid;
        // show the login form instead of leaving the user on a dead offline UI.
        if (
          (error as Error & { status?: number }).status === 401 ||
          (error as Error & { status?: number }).status === 403
        ) {
          try {
            const current = await post("/auth/refresh", {});
            setCsrf(current.csrf);
            setSession({ ...current, offline: false });
            setOffline(false);
            if (current.user && !current.mfa_required)
              localStorage.setItem(
                "postlane_offline_user",
                JSON.stringify(current.user),
              );
            notify("Connection restored.");
          } catch (refreshError) {
            if (
              (refreshError as Error & { status?: number }).status === 401 ||
              (refreshError as Error & { status?: number }).status === 403
            ) {
              localStorage.removeItem("postlane_offline_user");
              setSession(null);
              setOffline(false);
            } else {
              setOffline(true);
            }
          }
        } else {
          setOffline(true);
        }
      } finally {
        reconnecting = false;
      }
    };
    const updateOffline = () => setOffline(true);
    window.addEventListener("online", reconnect);
    window.addEventListener("offline", updateOffline);
    if (navigator.onLine && session?.offline) void reconnect();
    return () => {
      window.removeEventListener("online", reconnect);
      window.removeEventListener("offline", updateOffline);
    };
  }, [notify, session?.offline]);
  useEffect(() => {
    // Keep gestures deliberately conservative: native scrolling and text
    // editing should continue to behave normally, while the app gets the two
    // mobile gestures people expect from a mail client.
    let startX = 0;
    let startY = 0;
    let startTarget: EventTarget | null = null;
    let lastRefresh = 0;
    const isEditing = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      Boolean(
        target.closest("input, textarea, select, [contenteditable='true']"),
      );
    const touchStart = (event: TouchEvent) => {
      if (window.innerWidth > 800 || event.touches.length !== 1) return;
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      startTarget = event.target;
    };
    const touchEnd = (event: TouchEvent) => {
      if (window.innerWidth > 800 || event.changedTouches.length !== 1) return;
      if (isEditing(startTarget) || compose) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - startX;
      const dy = touch.clientY - startY;
      const horizontal = Math.abs(dx) > Math.abs(dy);

      if (horizontal && dx > 72 && Math.abs(dy) < 100) {
        if (sideOpen) setSideOpen(false);
        else if (selected) setSelected(null);
        else if (tab !== "mail") setTab("mail");
        return;
      }

      // Pull-to-refresh starts near the top edge so normal downward reading
      // gestures do not unexpectedly reload the mailbox.
      if (
        !horizontal &&
        dy > 82 &&
        startY < 110 &&
        tab === "mail" &&
        session &&
        !session.mfa_required &&
        !offline &&
        Date.now() - lastRefresh > 1200
      ) {
        lastRefresh = Date.now();
        setBusy(true);
        void refresh().finally(() => setBusy(false));
        notify("Refreshing mail…");
      }
    };
    window.addEventListener("touchstart", touchStart, { passive: true });
    window.addEventListener("touchend", touchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", touchStart);
      window.removeEventListener("touchend", touchEnd);
    };
  }, [compose, notify, offline, refresh, selected, session, sideOpen, tab]);
  useEffect(() => {
    if (!session || !("serviceWorker" in navigator)) return;
    void navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => setPushEnabled(Boolean(subscription)))
      .catch(() => {});
  }, [session]);
  useEffect(() => {
    if (!session) return;
    const unread = boxes.reduce((total, box) => total + (box.unread || 0), 0);
    const appNavigator = navigator as Navigator & {
      setAppBadge?: (count?: number) => Promise<void>;
      clearAppBadge?: () => Promise<void>;
    };
    if (unread && appNavigator.setAppBadge)
      void appNavigator.setAppBadge(unread);
    else if (!unread && appNavigator.clearAppBadge)
      void appNavigator.clearAppBadge();
  }, [boxes, session]);
  useEffect(() => {
    if (session) void refresh();
  }, [refresh, session]);
  useEffect(() => {
    if (!session || session.mfa_required) return;
  }, [session]);
  useEffect(() => {
    if (session?.mfa_required) {
      setTab("settings");
      notify(
        "Enable two-factor authentication in Settings, then sign in again to unlock your workspace.",
      );
    }
  }, [session, notify]);
  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(query);
      setOffset(0);
    }, 250);
    return () => clearTimeout(id);
  }, [query]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(""), 6500);
    return () => clearTimeout(id);
  }, [notice]);
  const login = async (path: string, data: unknown) => {
    try {
      setBusy(true);
      const s = await post(path, data);
      setCsrf(s.csrf);
      setSession({ ...s, offline: false });
      setOffline(false);
      if (s.user && !s.mfa_required)
        localStorage.setItem("postlane_offline_user", JSON.stringify(s.user));
      setSetup(false);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const navigate = (f: string, b = mailbox) => {
    setFolder(f);
    setMailbox(b);
    setTab("mail");
    setSelected(null);
    setChecked([]);
    setOffset(0);
    setSideOpen(false);
  };
  const act = async (id: string, data: unknown) => {
    try {
      const m = await patch<Message>("/messages/" + id, data);
      const movedToTrash =
        typeof data === "object" &&
        data !== null &&
        "folder" in data &&
        (data as { folder?: unknown }).folder === "trash";
      if (selected?.id === id) setSelected(movedToTrash ? null : m);
      await refresh();
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const markSpam = async (id: string) => {
    try {
      await post(`/messages/${id}/spam`);
      if (selected?.id === id) setSelected(null);
      await refresh();
      notify("Sender added to the mailbox spam list.");
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const openMessage = async (m: Message) => {
    try {
      const full = await api<Message>("/messages/" + m.id);
      setSelected(full);
      if (m.unread && boxes.find((b) => b.id === m.mailbox_id)?.can_write)
        void act(m.id, { unread: false });
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const bulk = async (data: unknown) => {
    setBusy(true);
    try {
      await Promise.all(checked.map((id) => patch("/messages/" + id, data)));
      setChecked([]);
      await refresh();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const bulkSpam = async () => {
    setBusy(true);
    try {
      await Promise.all(checked.map((id) => post(`/messages/${id}/spam`)));
      setChecked([]);
      await refresh();
      notify("Senders added to the mailbox spam list.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const doSync = async () => {
    setBusy(true);
    try {
      const targets = visibleBoxes.filter(
        (b) => b.can_write && (!mailbox || b.id === mailbox),
      );
      const results = await Promise.allSettled(
        targets.map((b) => post(`/mailboxes/${b.id}/sync`)),
      );
      await refresh();
      notify(
        results.some((r) => r.status === "rejected")
          ? "Some accounts could not sync. Check Mailboxes for details."
          : demo
            ? "Sample mail is up to date."
            : "Mailboxes synchronized.",
      );
    } finally {
      setBusy(false);
    }
  };
  const startCompose = (m?: Message, forward = false) => {
    const b =
      visibleBoxes.find((b) => b.id === (m?.mailbox_id || mailbox)) ||
      visibleBoxes.find((b) => b.id === session?.user.default_mailbox_id) ||
      visibleBoxes.find((b) => b.can_write);
    if (!b) return notify("Add a mailbox before composing.");
    const signatureText = b.signature ? `\n\n${b.signature}` : "";
    const signatureMarkup =
      b.signature_html ||
      (b.signature
        ? `<div>${b.signature
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\n/g, "<br>")}</div>`
        : "");
    const signatureHtml = signatureMarkup
      ? `<!-- postlane-signature -->${
          b.logo_url
            ? `<p><img src="${b.logo_url}" alt="Company logo" style="max-width:240px;height:auto"></p>`
            : ""
        }${signatureMarkup}<!-- /postlane-signature -->`
      : "";
    setCompose({
      mailbox_id: b.id,
      to: m && !forward ? address(m.sender) : "",
      cc: "",
      subject: m
        ? (forward ? "Fwd: " : "Re: ") + m.subject.replace(/^(Re: |Fwd: )/i, "")
        : "",
      body:
        (forward && m
          ? `\n\n---------- Forwarded message ----------\nFrom: ${m.sender}\nSubject: ${m.subject}\n\n${m.body}`
          : "") + signatureText,
      html_body: signatureHtml,
      reply_to: m && !forward ? m.id : "",
      ai_generated: false,
      status: "draft",
    });
  };
  useEffect(() => {
    if (launchShortcut !== "compose" || !session || !boxes.length || compose)
      return;
    startCompose();
    setLaunchShortcut("");
    window.history.replaceState({}, "", window.location.pathname);
  }, [launchShortcut, session, boxes, compose]);
  const visibleBoxes = boxes.filter(
    (b) =>
      mailboxMode === "all" ||
      (mailboxMode === "human"
        ? b.management_mode !== "ai"
        : (b.management_mode || "human") === mailboxMode),
  );
  const switchMailboxMode = (mode: typeof mailboxMode) => {
    refreshSequence.current += 1;
    setMessages([]);
    setDrafts([]);
    setTotal(0);
    setMailboxMode(mode);
    setMailbox("");
    setSelected(null);
    setChecked([]);
    setOffset(0);
    setTab("mail");
    setFolder("inbox");
    setSideOpen(false);
  };
  const displayed = messages.filter((m) => !onlyUnread || m.unread);
  const activeBox = boxes.find((b) => b.id === mailbox);
  const unreadCount = boxes.reduce(
    (total, box) => total + (box.unread || 0),
    0,
  );
  if (!ready)
    return (
      <div className="loading splash-screen">
        <div className="splash-mark">
          <Brand />
        </div>
        <LoaderCircle className="spin" size={19} />
        <span>Opening your workspace…</span>
      </div>
    );
  if (!session)
    return (
      <div className="login-page">
        <div className="login-brand">
          <p className="help">Created by CloudMonkey</p>
          <Brand />
          <div className="login-story">
            <span className="eyebrow">
              A LITTLE LESS INBOX. A LITTLE MORE SPACE.
            </span>
            <h1>
              All your businesses.
              <br />
              One place to breathe.
            </h1>
            <p>
              Your mail, your team, your infrastructure.
              <br />A calmer workspace for everything you’re building.
            </p>
            <div className="login-domains">
              <span>
                <Globe size={16} /> Multiple domains
              </span>
              <span>
                <ShieldCheck size={16} /> Private by default
              </span>
            </div>
          </div>
          <small>Thoughtfully organized. Entirely yours.</small>
        </div>
        <div className="login-form">
          <span className="mini-brand">
            <Mail size={22} /> POSTLANE
          </span>
          <h2>
            {setup ? "Make yourself at home." : "Welcome to your workspace."}
          </h2>
          <p>
            {setup
              ? "Create the administrator account for this installation."
              : "Sign in to keep all your conversations moving."}
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const data = Object.fromEntries(new FormData(e.currentTarget));
              void login(setup ? "/auth/setup" : "/auth/login", data);
            }}
          >
            {setup && (
              <>
                <label>
                  Your name
                  <input name="name" required autoComplete="name" />
                </label>
                <label>
                  Installation token
                  <input name="token" type="password" required />
                </label>
              </>
            )}
            <label>
              Email address
              <input
                name="email"
                type="email"
                required
                autoComplete="username"
                placeholder="you@yourbusiness.com"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                required
                minLength={setup ? 14 : 1}
                autoComplete={setup ? "new-password" : "current-password"}
              />
            </label>
            {!setup && (
              <label>
                Authentication code <span className="muted">if enabled</span>
                <input
                  name="code"
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="one-time-code"
                />
              </label>
            )}
            <button className="primary" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={18} /> : null}
              {setup ? "Create workspace" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </form>
          {demo && (
            <div className="demo-entry">
              <span>Explore with fictional mail. Sending is disabled.</span>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => login("/auth/demo", {})}
              >
                Open sample workspace <ArrowUpRight size={17} />
              </button>
            </div>
          )}
          <p className="secure-caption">
            <Lock size={13} /> Privately hosted. No advertising. No tracking.
          </p>
        </div>
        {notice && <Toast text={notice} close={() => setNotice("")} />}
      </div>
    );
  return (
    <div className={`app-shell theme-${theme}`}>
      <aside className={"sidebar " + (sideOpen ? "mobile-open" : "")}>
        <div className="sidebar-brand-row">
          <Brand />
          <button
            className="sidebar-close"
            aria-label="Hide navigation menu"
            onClick={() => setSideOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <button
          className="workspace-switch"
          onClick={() => {
            setTab("settings");
            setSideOpen(false);
          }}
        >
          <span className="workspace-avatar">
            N<span />
          </span>
          <span>
            <strong>My workspace</strong>
            <small>
              {boxes.length} mailboxes ·{" "}
              {new Set(boxes.map((b) => b.email.split("@")[1])).size} domains
            </small>
          </span>
          <ChevronDown size={15} />
        </button>
        <button className="compose-button" onClick={() => startCompose()}>
          <Plus size={20} /> Compose<span>C</span>
        </button>
        <div className="nav-section-label">WORKSPACE</div>
        <nav>
          {navigation.map(([id, title, Icon]) => (
            <button
              key={id}
              className={
                "nav-item " + (tab === "mail" && folder === id ? "active" : "")
              }
              onClick={() => navigate(id)}
            >
              <Icon size={18} />
              <span>{title}</span>
              {id === "inbox" && (
                <b>
                  {visibleBoxes
                    .filter((b) => !mailbox || b.id === mailbox)
                    .reduce((a, b) => a + b.unread, 0)}
                </b>
              )}
              {id === "drafts" && drafts.length > 0 && (
                <small>{drafts.length}</small>
              )}
            </button>
          ))}
        </nav>
        <div
          className="mailbox-mode-switch"
          role="group"
          aria-label="Mailbox management type"
        >
          {(
            [
              ["human", "Human"],
              ["shared", "Shared"],
              ["ai", "AI agents"],
              ["all", "All"],
            ] as const
          ).map(([id, label]) => (
            <button
              type="button"
              key={id}
              aria-pressed={mailboxMode === id}
              onClick={() => switchMailboxMode(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="nav-section-label">
          <span>
            {mailboxMode === "ai"
              ? "AI MAILBOXES"
              : mailboxMode === "shared"
                ? "SHARED MAILBOXES"
                : "MAILBOXES"}
          </span>
          <button title="Manage mailboxes" onClick={() => setTab("mailboxes")}>
            <Plus size={15} />
          </button>
        </div>
        <button
          className={"mailbox-nav " + (!mailbox ? "chosen" : "")}
          onClick={() => navigate("inbox", "")}
        >
          <span className="all-dot">
            <Inbox size={13} />
          </span>
          <span>
            {mailboxMode === "ai"
              ? "All AI mailboxes"
              : mailboxMode === "shared"
                ? "All shared mailboxes"
                : mailboxMode === "human"
                  ? "All human mailboxes"
                  : "All mailboxes"}
          </span>
          <span className="pill">{visibleBoxes.length}</span>
        </button>
        {visibleBoxes.length > 0 && (
          <div className="mailbox-sub-label">
            {mailboxMode === "ai" ? "AGENT ACCOUNTS" : "CONNECTED MAILBOXES"}
          </div>
        )}
        <div className="mailbox-scroll">
          {visibleBoxes.map((b) => (
            <button
              key={b.id}
              className={"mailbox-nav " + (mailbox === b.id ? "chosen" : "")}
              onClick={() => navigate("inbox", b.id)}
            >
              <span className="mailbox-dot" style={{ background: b.color }} />
              <span title={b.email}>
                {b.email.split("@")[0]}
                <small>@{b.email.split("@")[1]}</small>
              </span>
              {b.unread > 0 && <strong>{b.unread}</strong>}
            </button>
          ))}
        </div>
        <div className="nav-section-label">
          <span>FOLDERS</span>
          <button title="Create folder" onClick={() => setNewFolder(true)}>
            <Plus size={15} />
          </button>
        </div>
        <div className="folder-scroll">
          {folders
            .filter(
              (f) =>
                visibleBoxes.some((b) => b.id === f.mailbox_id) &&
                (!mailbox || f.mailbox_id === mailbox),
            )
            .map((f) => (
              <button
                key={f.id}
                className={
                  "nav-item folder-nav " +
                  (folder === f.name && mailbox === f.mailbox_id
                    ? "active"
                    : "")
                }
                onClick={() => navigate(f.name, f.mailbox_id)}
              >
                <FolderIcon size={16} />
                <span>{f.name}</span>
              </button>
            ))}
        </div>
        <div className="sidebar-bottom">
          <button
            className={"nav-item " + (tab === "work" ? "active" : "")}
            onClick={() => setTab("work")}
          >
            <Sparkles size={18} />
            <span>Work</span>
            <span className="new-tag">AI</span>
          </button>
          <button
            className={"nav-item " + (tab === "automations" ? "active" : "")}
            onClick={() => setTab("automations")}
          >
            <Workflow size={18} />
            <span>Integrations</span>
            <span className="new-tag">API</span>
          </button>
          <button
            className={"nav-item " + (tab === "settings" ? "active" : "")}
            onClick={() => setTab("settings")}
          >
            <Settings size={18} />
            <span>Settings</span>
          </button>
          <button className="profile" onClick={() => setTab("settings")}>
            <span className="avatar profile-avatar">
              {initials(session.user.name)}
            </span>
            <span>
              <strong>{session.user.name}</strong>
              <small>
                {session.user.role === "admin"
                  ? "Workspace admin"
                  : "Team member"}
              </small>
            </span>
            <ChevronDown size={15} />
          </button>
        </div>
      </aside>
      {sideOpen && (
        <button
          className="mobile-menu-scrim"
          aria-label="Close navigation menu"
          onClick={() => setSideOpen(false)}
        />
      )}
      <main className="main-workspace">
        <header className="topbar">
          <button
            className="icon-button mobile-toggle"
            title="Toggle navigation"
            onClick={() => setSideOpen(!sideOpen)}
          >
            <PanelLeft size={20} />
          </button>
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <span>
              {tab === "mail"
                ? "Mail"
                : tab === "automations"
                  ? "Integrations"
                  : tab[0].toUpperCase() + tab.slice(1)}
            </span>
          </div>
          <div className="search">
            <Search size={17} />
            <input
              ref={searchRef}
              aria-label="Search mail"
              placeholder="Search your mail"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setTab("mail");
                setSelected(null);
              }}
            />
            <kbd>⌘ K</kbd>
          </div>
          <div className="topbar-right">
            <span className="private-indicator">
              <span /> Private workspace
            </span>
            <button
              className="icon-button"
              title={
                pushEnabled ? "Turn off notifications" : "Enable notifications"
              }
              aria-label={
                unreadCount ? `${unreadCount} unread messages` : "Notifications"
              }
              onClick={() => void (pushEnabled ? disablePush() : enablePush())}
            >
              <Bell size={19} />
              {unreadCount > 0 && (
                <span className="notification-badge">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </button>
            <button
              className="icon-button"
              title="Security settings"
              onClick={() => setTab("settings")}
            >
              <ShieldCheck size={19} />
            </button>
            <span className="avatar small-avatar">
              {initials(session.user.name)}
            </span>
          </div>
        </header>
        {demo && (
          <div className="sample-banner">
            <span>
              <span className="sample-dot" /> Sample workspace
            </span>
            <span>Fictional mail · no live accounts connected</span>
            <button onClick={() => setTab("mailboxes")}>
              View setup <ArrowUpRight size={13} />
            </button>
          </div>
        )}
        {offline && (
          <div className="offline-banner">
            <WifiOff size={14} /> Offline mode · showing cached mail where
            available
          </div>
        )}
        {tab === "work" ? (
          <Work
            boxes={boxes}
            demo={demo}
            notify={notify}
            isAdmin={session.user.role === "admin"}
          />
        ) : tab !== "mail" ? (
          <Admin
            tab={tab}
            setTab={setTab}
            boxes={boxes}
            user={session.user}
            demo={demo}
            notify={notify}
            refresh={refresh}
            theme={theme}
            setTheme={setTheme}
            notificationsEnabled={pushEnabled}
            enableNotifications={enablePush}
            disableNotifications={disablePush}
            logout={async () => {
              await post("/auth/logout");
              localStorage.removeItem("postlane_offline_user");
              navigator.serviceWorker.controller?.postMessage({
                type: "CLEAR_APP_CACHE",
              });
              setSession(null);
            }}
          />
        ) : (
          <>
            <section className="mail-heading">
              <div>
                <div className="heading-kicker">
                  YOUR DAY, A LITTLE MORE ORGANIZED
                </div>
                <h1>
                  {selected
                    ? "Conversation"
                    : folder === "inbox"
                      ? "Inbox"
                      : folder[0].toUpperCase() + folder.slice(1)}
                  {!selected && folder === "inbox" && <span>{total}</span>}
                </h1>
                <p>
                  {activeBox
                    ? activeBox.email
                    : mailboxMode === "ai"
                      ? "AI agent mailboxes · API-managed conversations"
                      : mailboxMode === "shared"
                        ? "Shared mailboxes · access is controlled per person"
                        : mailboxMode === "human"
                          ? "Human-managed mailboxes, including shared inboxes"
                          : "All authorized mailboxes. One clear view."}
                </p>
              </div>
              <div className="heading-actions">
                <span className="mailbox-stack">
                  {visibleBoxes.slice(0, 3).map((b, i) => (
                    <span
                      key={b.id}
                      style={{
                        background: ["#e2eee9", "#eee5f5", "#f6eadc"][i],
                        color: b.color,
                      }}
                    >
                      {b.email[0].toUpperCase()}
                    </span>
                  ))}
                </span>
                <button
                  className="text-button"
                  onClick={() => setTab("mailboxes")}
                >
                  Manage mailboxes <ArrowUpRight size={15} />
                </button>
              </div>
            </section>
            <div
              className="inbox-mode-switch"
              role="group"
              aria-label="Inbox mailbox type"
            >
              {(
                [
                  ["human", "Human"],
                  ["shared", "Shared"],
                  ["ai", "AI agents"],
                  ["all", "All"],
                ] as const
              ).map(([id, label]) => (
                <button
                  type="button"
                  key={id}
                  aria-pressed={mailboxMode === id}
                  onClick={() => switchMailboxMode(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mail-surface">
              <div className="mail-toolbar">
                <div className="toolbar-left">
                  {selected ? (
                    <button
                      className="icon-button"
                      title="Back to inbox"
                      onClick={() => setSelected(null)}
                    >
                      <ArrowLeft size={18} />
                    </button>
                  ) : (
                    <input
                      type="checkbox"
                      aria-label="Select visible messages"
                      checked={
                        displayed.length > 0 &&
                        checked.length === displayed.length
                      }
                      onChange={(e) =>
                        setChecked(
                          e.target.checked ? displayed.map((m) => m.id) : [],
                        )
                      }
                    />
                  )}
                  <button
                    className={"icon-button " + (busy ? "spinning" : "")}
                    title="Sync mailboxes"
                    disabled={busy}
                    onClick={doSync}
                  >
                    <RefreshCw size={16} />
                  </button>
                  <div className="toolbar-divider" />
                  {checked.length > 0 ? (
                    <>
                      <span className="muted">{checked.length} selected</span>
                      <button
                        className="icon-button"
                        title="Archive selected"
                        aria-label="Archive selected emails"
                        onClick={() => bulk({ folder: "archive" })}
                      >
                        <Archive size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="Mark selected as read"
                        onClick={() => bulk({ unread: false })}
                      >
                        <CheckCheck size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="Trash selected"
                        aria-label="Delete selected emails"
                        onClick={() => bulk({ folder: "trash" })}
                      >
                        <Trash2 size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="Mark selected as spam"
                        onClick={() => void bulkSpam()}
                      >
                        <Ban size={17} />
                      </button>
                    </>
                  ) : (
                    <select
                      className="toolbar-select"
                      aria-label="Choose mailbox"
                      value={mailbox}
                      onChange={(e) => navigate("inbox", e.target.value)}
                    >
                      <option value="">
                        {mailboxMode === "ai"
                          ? "All AI mailboxes"
                          : mailboxMode === "shared"
                            ? "All shared mailboxes"
                            : mailboxMode === "human"
                              ? "All human mailboxes"
                              : "All mailboxes"}
                      </option>
                      {visibleBoxes.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name || b.email}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <div className="toolbar-right">
                  <button
                    className={"filter-button " + (filter ? "selected" : "")}
                    onClick={() => setFilter(!filter)}
                  >
                    <SlidersHorizontal size={15} /> Filter
                  </button>
                  <span className="range">
                    {total ? offset + 1 : 0}–{Math.min(offset + 50, total)} of{" "}
                    {total}
                  </span>
                  <button
                    className="icon-button"
                    title="Previous page"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - 50))}
                  >
                    <ChevronRight className="rotate" size={17} />
                  </button>
                  <button
                    className="icon-button"
                    title="Next page"
                    disabled={offset + 50 >= total}
                    onClick={() => setOffset(offset + 50)}
                  >
                    <ChevronRight size={17} />
                  </button>
                </div>
              </div>
              {filter && (
                <div className="filter-panel">
                  <label>
                    <input
                      type="checkbox"
                      checked={onlyUnread}
                      onChange={(e) => setOnlyUnread(e.target.checked)}
                    />{" "}
                    Unread on this page
                  </label>
                  <select
                    aria-label="Filter mailbox"
                    value={mailbox}
                    onChange={(e) => navigate(folder, e.target.value)}
                  >
                    <option value="">
                      {mailboxMode === "ai"
                        ? "All AI mailboxes"
                        : mailboxMode === "shared"
                          ? "All shared mailboxes"
                          : mailboxMode === "human"
                            ? "All human mailboxes"
                            : "All mailboxes"}
                    </option>
                    {visibleBoxes.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.email}
                      </option>
                    ))}
                  </select>
                  <button
                    className="text-button"
                    onClick={() => {
                      setOnlyUnread(false);
                      setQuery("");
                      navigate("inbox", "");
                    }}
                  >
                    Reset
                  </button>
                </div>
              )}
              {selected ? (
                <MessageView
                  message={selected}
                  box={boxes.find((b) => b.id === selected.mailbox_id)!}
                  folders={folders}
                  act={(data) => act(selected.id, data)}
                  spam={() => void markSpam(selected.id)}
                  reply={() => startCompose(selected)}
                  forward={() => startCompose(selected, true)}
                  ai={async () => {
                    try {
                      setBusy(true);
                      const d = await post<Draft>(
                        `/messages/${selected.id}/ai-draft`,
                      );
                      setCompose(d);
                      await refresh();
                    } catch (e) {
                      notify((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                  busy={busy}
                  notify={notify}
                />
              ) : folder === "drafts" ? (
                <div className="draft-list">
                  {drafts.length ? (
                    drafts
                      .filter((d) => !mailbox || d.mailbox_id === mailbox)
                      .map((d) => (
                        <div className="draft-row" key={d.id}>
                          <button
                            className="draft-open"
                            onClick={() => setCompose(d)}
                          >
                            <FileText size={20} />
                            <div>
                              <strong>{d.subject || "Untitled draft"}</strong>
                              <span>{d.to || "No recipients yet"}</span>
                            </div>
                          </button>
                          <span className="label">
                            {d.status === "sent" ? "Accepted" : d.status}
                          </span>
                          {d.ai_generated && <Sparkles size={16} />}
                          <button
                            className="draft-delete"
                            title="Delete draft"
                            aria-label={`Delete ${d.subject || "untitled draft"}`}
                            onClick={async () => {
                              if (!window.confirm("Delete this draft?")) return;
                              try {
                                await api(`/drafts/${d.id}`, {
                                  method: "DELETE",
                                });
                                await refresh();
                                notify("Draft deleted.");
                              } catch (e) {
                                notify((e as Error).message);
                              }
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      ))
                  ) : (
                    <Empty
                      title="Room for your next idea"
                      text="Your saved drafts will appear here."
                    />
                  )}
                </div>
              ) : (
                <>
                  <div className="inbox-tabs">
                    <button
                      className="inbox-tab current"
                      onClick={() => setOnlyUnread(false)}
                    >
                      <Inbox size={16} />
                      {folder === "inbox" ? "All conversations" : "Messages"}
                      <span>{total}</span>
                    </button>
                    <button
                      className={"inbox-tab " + (onlyUnread ? "current" : "")}
                      onClick={() => setOnlyUnread(!onlyUnread)}
                    >
                      <span className="unread-tab-dot" /> Unread
                    </button>
                    <div className="inbox-tabs-end">
                      <ShieldCheck size={13} /> Your mail stays yours
                    </div>
                  </div>
                  <div className="message-list">
                    {displayed.length ? (
                      displayed.map((m, i) => {
                        const box = boxes.find((b) => b.id === m.mailbox_id);
                        return (
                          <div
                            key={m.id}
                            className={
                              "message-row " +
                              (m.unread ? "unread " : "") +
                              (checked.includes(m.id) ? "checked " : "") +
                              (swipeAction?.id === m.id
                                ? `swipe-${swipeAction.direction}`
                                : "")
                            }
                            onTouchStart={(event) => {
                              if (window.innerWidth > 800) return;
                              const target = event.target as HTMLElement;
                              if (target.closest("input, .star-button")) return;
                              const touch = event.touches[0];
                              rowSwipe.current = {
                                id: m.id,
                                x: touch.clientX,
                                y: touch.clientY,
                              };
                            }}
                            onTouchMove={(event) => {
                              const start = rowSwipe.current;
                              if (
                                !start ||
                                start.id !== m.id ||
                                window.innerWidth > 800
                              )
                                return;
                              const touch = event.touches[0];
                              const dx = touch.clientX - start.x;
                              const dy = touch.clientY - start.y;
                              if (Math.abs(dx) <= Math.abs(dy) + 8) return;
                              event.preventDefault();
                              setSwipeOffset({
                                id: m.id,
                                value: Math.max(-145, Math.min(145, dx)),
                              });
                            }}
                            onTouchEnd={(event) => {
                              const start = rowSwipe.current;
                              rowSwipe.current = null;
                              if (
                                !start ||
                                start.id !== m.id ||
                                window.innerWidth > 800
                              )
                                return;
                              const touch = event.changedTouches[0];
                              const dx = touch.clientX - start.x;
                              const dy = touch.clientY - start.y;
                              if (
                                Math.abs(dx) < 82 ||
                                Math.abs(dy) > 90 ||
                                Math.abs(dx) < Math.abs(dy)
                              ) {
                                if (swipeOffset?.id === m.id) {
                                  setSwipeOffset({ id: m.id, value: 0 });
                                  window.setTimeout(
                                    () => setSwipeOffset(null),
                                    180,
                                  );
                                }
                                return;
                              }
                              event.preventDefault();
                              event.stopPropagation();
                              const direction =
                                dx > 0 ? "read" : ("trash" as const);
                              setSwipeOffset(null);
                              setSwipeAction({ id: m.id, direction });
                              notify(
                                direction === "read"
                                  ? "Email marked as read."
                                  : "Email moved to trash.",
                              );
                              window.setTimeout(() => {
                                void act(
                                  m.id,
                                  direction === "read"
                                    ? { unread: false }
                                    : { folder: "trash" },
                                );
                                setSwipeAction(null);
                              }, 260);
                            }}
                            style={
                              swipeOffset?.id === m.id && !swipeAction
                                ? {
                                    transform: `translateX(${swipeOffset.value}px)`,
                                    transition: "none",
                                  }
                                : undefined
                            }
                          >
                            <input
                              className="message-select"
                              type="checkbox"
                              aria-label={"Select " + m.subject}
                              checked={checked.includes(m.id)}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) =>
                                setChecked(
                                  e.target.checked
                                    ? [...checked, m.id]
                                    : checked.filter((id) => id !== m.id),
                                )
                              }
                            />
                            <button
                              className={
                                "star-button " + (m.starred ? "is-starred" : "")
                              }
                              title={m.starred ? "Unstar" : "Star"}
                              onClick={() => act(m.id, { starred: !m.starred })}
                            >
                              <Star
                                size={16}
                                fill={m.starred ? "currentColor" : "none"}
                              />
                            </button>
                            <button
                              className="message-open"
                              onClick={() => openMessage(m)}
                            >
                              <span
                                className={
                                  "avatar sender-avatar tone-" + (i % 5)
                                }
                              >
                                {initials(senderName(m.sender))}
                              </span>
                              <span className="sender-column">
                                <strong>{senderName(m.sender)}</strong>
                                <small>
                                  <span style={{ background: box?.color }} />
                                  {box?.email}
                                </small>
                              </span>
                              <span className="message-content">
                                <span className="subject-line">
                                  <strong>{m.subject}</strong>
                                  {m.labels.slice(0, 1).map((l) => (
                                    <span
                                      key={l}
                                      className={
                                        "label label-" +
                                        l.toLowerCase().replaceAll(" ", "-")
                                      }
                                    >
                                      {l}
                                    </span>
                                  ))}
                                  {m.spam_verdict === "spam" && (
                                    <span className="label label-spam">
                                      Spam detected
                                    </span>
                                  )}
                                  {m.spam_verdict === "likely_spam" && (
                                    <span className="label label-warning">
                                      Review spam risk
                                    </span>
                                  )}
                                </span>
                                <span className="message-preview">
                                  {m.preview}
                                </span>
                              </span>
                              <span className="message-meta">
                                <time
                                  dateTime={new Date(
                                    m.received_at * 1000,
                                  ).toISOString()}
                                  title={new Date(
                                    m.received_at * 1000,
                                  ).toLocaleString()}
                                >
                                  {formatTime(m.received_at)}
                                </time>
                                {m.unread && <span className="unread-dot" />}
                                {m.has_attachments && <Paperclip size={13} />}
                              </span>
                            </button>
                          </div>
                        );
                      })
                    ) : (
                      <Empty
                        title={
                          search
                            ? "No conversations found"
                            : "You’re all caught up"
                        }
                        text={
                          search
                            ? "Try a different name, subject, or phrase."
                            : "New conversations will appear here when mail arrives."
                        }
                      />
                    )}
                  </div>
                  <div className="list-footer">
                    <CheckCheck size={15} />
                    <span>
                      {demo
                        ? "You’re exploring sample conversations."
                        : "A little more clarity. A little less inbox."}
                    </span>
                    <button
                      type="button"
                      className="footer-shortcut"
                      title="Keyboard shortcuts"
                      onClick={() => setShortcutsOpen(true)}
                    >
                      ⌘ / Ctrl K · ? Shortcuts
                    </button>
                  </div>
                </>
              )}
            </div>
            <footer className="workspace-footer">
              <span>
                <Lock size={12} /> Hosted by you. Controlled by you.
              </span>
              <span>
                POSTLANE <span className="version">/ 01</span>
              </span>
            </footer>
          </>
        )}
      </main>
      <nav
        className="mobile-bottom-nav"
        aria-label="Mobile workspace navigation"
      >
        <button
          className={tab === "mail" && folder === "inbox" ? "active" : ""}
          onClick={() => navigate("inbox", mailbox)}
        >
          <Inbox size={20} />
          <span>Inbox</span>
        </button>
        <button
          className={compose ? "compose-active" : "compose-main"}
          onClick={() => startCompose()}
        >
          <span className="mobile-compose-orb">
            <Plus size={22} />
          </span>
          <span>Compose</span>
        </button>
        <button
          className={tab === "work" ? "active assistant-nav" : "assistant-nav"}
          onClick={() => {
            setTab("work");
            setSideOpen(false);
          }}
        >
          <Sparkles size={20} />
          <span>Assistant</span>
        </button>
        <button
          className={tab === "mailboxes" ? "active" : ""}
          onClick={() => {
            setTab("mailboxes");
            setSideOpen(false);
          }}
        >
          <Users size={20} />
          <span>Mailboxes</span>
        </button>
        <button
          className={tab === "settings" ? "active" : ""}
          onClick={() => {
            setTab("settings");
            setSideOpen(false);
          }}
        >
          <Settings size={20} />
          <span>Settings</span>
        </button>
      </nav>
      {shortcutsOpen && (
        <Modal title="Keyboard shortcuts" close={() => setShortcutsOpen(false)}>
          <p className="help">Shortcuts pause while typing in a field.</p>
          <div className="shortcut-list">
            {[
              ["Ctrl / ⌘ Shift C", "Compose a new email"],
              ["/ or Ctrl / ⌘ K", "Focus mail search"],
              ["J / K", "Next / previous conversation"],
              ["Enter", "Open conversation"],
              ["R / F", "Reply / forward"],
              ["I", "Mark as read"],
              ["D", "Move to trash"],
              ["Esc", "Close conversation, composer or menu"],
              ["?", "Show shortcuts"],
            ].map(([key, description]) => (
              <div className="shortcut-row" key={key}>
                <kbd>{key}</kbd>
                <span>{description}</span>
              </div>
            ))}
          </div>
        </Modal>
      )}
      {compose && (
        <Composer
          draft={compose}
          boxes={boxes}
          close={() => setCompose(null)}
          notify={notify}
          refresh={refresh}
          onSaved={setCompose}
        />
      )}
      {newFolder && (
        <Modal title="Create a folder" close={() => setNewFolder(false)}>
          <form
            className="stack-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              try {
                await post("/folders", Object.fromEntries(form));
                setNewFolder(false);
                await refresh();
                notify("Folder created.");
              } catch (ex) {
                notify((ex as Error).message);
              }
            }}
          >
            <label>
              Mailbox
              <select name="mailbox_id" defaultValue={mailbox || boxes[0]?.id}>
                {boxes
                  .filter((b) => b.can_write)
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.email}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Folder name
              <input
                name="name"
                required
                maxLength={120}
                placeholder="e.g. Clients / Northstar"
              />
            </label>
            <p className="help">
              Workspace folders organize mail in Postlane. They do not move
              messages at your email provider.
            </p>
            <button className="primary">Create folder</button>
          </form>
        </Modal>
      )}
      {notice && <Toast text={notice} close={() => setNotice("")} />}
    </div>
  );
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-icon">
        <Mail size={22} strokeWidth={1.7} />
      </span>
      <span>
        postlane<span className="brand-period">.</span>
      </span>
    </div>
  );
}
export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <div>
        <Inbox size={25} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
export function Modal({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon-button" onClick={close} title="Close dialog">
            <X size={20} />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function Toast({ text, close }: { text: string; close: () => void }) {
  return (
    <div className="toast" role="status">
      <AlertCircle size={18} />
      <span>{text}</span>
      <button className="icon-button" onClick={close} title="Dismiss">
        <X size={16} />
      </button>
    </div>
  );
}

function MessageView({
  message: m,
  box,
  folders,
  act,
  spam,
  reply,
  forward,
  ai,
  busy,
  notify,
}: {
  message: Message;
  box: Mailbox;
  folders: Folder[];
  act: (data: unknown) => void;
  spam: () => void;
  reply: () => void;
  forward: () => void;
  ai: () => void;
  busy: boolean;
  notify: (s: string) => void;
}) {
  const [notes, setNotes] = useState<
      { id: string; text: string; author: string; at: number }[]
    >([]),
    [note, setNote] = useState(""),
    [showNotes, setShowNotes] = useState(false),
    [showDetails, setShowDetails] = useState(false),
    [bodyZoom, setBodyZoom] = useState(100),
    [label, setLabel] = useState("");
  useEffect(() => {
    api(`/messages/${m.id}/notes`)
      .then(setNotes)
      .catch(() => {});
  }, [m.id]);
  return (
    <article className="reader">
      <div className="reader-actions">
        <div>
          <button
            className="icon-button"
            title="Archive in workspace"
            disabled={!box.can_write}
            onClick={() => act({ folder: "archive" })}
          >
            <Archive size={18} />
          </button>
          <button
            className="icon-button"
            title="Move to trash in workspace"
            disabled={!box.can_write}
            onClick={() => act({ folder: "trash" })}
          >
            <Trash2 size={18} />
          </button>
          <button
            className="icon-button"
            title="Mark sender as spam"
            disabled={!box.can_write}
            onClick={spam}
          >
            <Ban size={18} />
          </button>
          <button
            className="icon-button"
            title="Mark unread"
            disabled={!box.can_write}
            onClick={() => act({ unread: true })}
          >
            <Mail size={18} />
          </button>
          <button
            className="icon-button"
            title="Snooze for one day"
            disabled={!box.can_write}
            onClick={() =>
              act({ snoozed_until: Math.floor(Date.now() / 1000) + 86400 })
            }
          >
            <Clock size={18} />
          </button>
        </div>
        <select
          aria-label="Move to workspace folder"
          value={m.folder}
          disabled={!box.can_write}
          onChange={(e) => act({ folder: e.target.value })}
        >
          {[
            "inbox",
            "archive",
            "trash",
            "spam",
            "sent",
            ...folders
              .filter((f) => f.mailbox_id === m.mailbox_id)
              .map((f) => f.name),
          ].map((f) => (
            <option key={f} value={f}>
              {f[0].toUpperCase() + f.slice(1)}
            </option>
          ))}
        </select>
        <div className="reader-zoom" aria-label="Message text size">
          <button
            className="icon-button"
            title="Decrease message text size"
            aria-label="Decrease message text size"
            disabled={bodyZoom <= 80}
            onClick={() => setBodyZoom((value) => Math.max(80, value - 10))}
          >
            −
          </button>
          <span>{bodyZoom}%</span>
          <button
            className="icon-button"
            title="Increase message text size"
            aria-label="Increase message text size"
            disabled={bodyZoom >= 140}
            onClick={() => setBodyZoom((value) => Math.min(140, value + 10))}
          >
            +
          </button>
        </div>
      </div>
      <h2>{m.subject}</h2>
      <div className="reader-labels">
        {m.labels.map((l) => (
          <button
            className="label"
            key={l}
            title="Remove label"
            disabled={!box.can_write}
            onClick={() => act({ labels: m.labels.filter((x) => x !== l) })}
          >
            {l}
            <X size={10} />
          </button>
        ))}
        {box.can_write && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (label.trim()) {
                act({ labels: [...new Set([...m.labels, label.trim()])] });
                setLabel("");
              }
            }}
          >
            <Tag size={13} />
            <input
              aria-label="Add label"
              placeholder="Add label…"
              value={label}
              maxLength={40}
              onChange={(e) => setLabel(e.target.value)}
            />
          </form>
        )}
      </div>
      <div className="reader-sender">
        <span className="avatar tone-0">{initials(senderName(m.sender))}</span>
        <div>
          <strong>{senderName(m.sender)}</strong>
          <span>{address(m.sender)}</span>
          <small>to {m.recipients}</small>
        </div>
        <time>{new Date(m.received_at * 1000).toLocaleString()}</time>
        <button
          className={"star-button " + (m.starred ? "is-starred" : "")}
          title="Toggle star"
          disabled={!box.can_write}
          onClick={() => act({ starred: !m.starred })}
        >
          <Star size={18} fill={m.starred ? "currentColor" : "none"} />
        </button>
      </div>
      <details
        className="message-details"
        open={showDetails}
        onToggle={(e) => setShowDetails(e.currentTarget.open)}
      >
        <summary>Message details</summary>
        <div className="message-details-grid">
          <span>Mailbox</span>
          <strong>{box.email}</strong>
          <span>From</span>
          <strong>{m.sender}</strong>
          <span>To</span>
          <strong>{m.recipients || "—"}</strong>
          <span>Received</span>
          <strong>{new Date(m.received_at * 1000).toLocaleString()}</strong>
          <span>Folder</span>
          <strong>{m.folder}</strong>
          <span>Conversation</span>
          <strong>{m.thread_id || m.id}</strong>
          <span>Attachments</span>
          <strong>{m.has_attachments ? "Available" : "None"}</strong>
        </div>
      </details>
      {m.spam_verdict !== "clean" && m.spam_verdict !== "unchecked" && (
        <div
          className={`spam-assessment ${m.spam_verdict === "spam" ? "is-spam" : "is-risk"}`}
        >
          <strong>
            <Shield size={15} />{" "}
            {m.spam_verdict === "spam" ? "Spam detected" : "Possible spam"} ·{" "}
            {m.spam_score}/100
          </strong>
          <span>
            {m.spam_reasons?.join(" ") ||
              "Automated checks found suspicious signals."}
          </span>
        </div>
      )}
      <div
        className="reader-body"
        style={{ fontSize: `${13 * (bodyZoom / 100)}px` }}
      >
        {m.html_body ? (
          <div
            className="reader-html"
            dangerouslySetInnerHTML={{ __html: m.html_body }}
          />
        ) : (
          m.body || "(This message has no text content.)"
        )}
      </div>
      {m.has_attachments && (
        <div className="attachment-list">
          <strong>
            <Paperclip size={15} /> Attachments
          </strong>
          {m.attachments?.length ? (
            m.attachments.map((attachment: Attachment) => (
              <a
                className="attachment-item"
                href={`/api/attachments/${attachment.id}`}
                download={attachment.filename}
                key={attachment.id}
              >
                <Paperclip size={15} />
                <span>
                  {attachment.filename}
                  <small>{formatBytes(attachment.size)}</small>
                </span>
              </a>
            ))
          ) : (
            <p className="attachment-note">
              Attachment metadata is still being synchronized. Refresh this
              message shortly.
            </p>
          )}
        </div>
      )}
      <div className="reply-actions">
        <button className="secondary" onClick={reply} disabled={!box.can_write}>
          <Reply size={16} /> Reply
        </button>
        <button
          className="secondary"
          onClick={forward}
          disabled={!box.can_write}
        >
          <Forward size={16} /> Forward
        </button>
        <button
          className="ai-button"
          onClick={ai}
          disabled={busy || !box.can_write}
        >
          <Sparkles size={16} />
          {busy ? "Preparing draft…" : "Draft with AI"}
        </button>
      </div>
      <div className="reader-private">
        <ShieldCheck size={14} /> External AI{" "}
        {box.ai_enabled ? "enabled for this mailbox" : "off for this mailbox"} ·
        Replies always need your approval
      </div>
      <section className="internal-notes">
        <button
          className="text-button"
          onClick={() => setShowNotes(!showNotes)}
        >
          <Users size={16} /> Team notes{" "}
          <span className="pill">{notes.length}</span>
          <ChevronDown size={14} />
        </button>
        {showNotes && (
          <>
            <p className="help">
              Private to people with mailbox access. Never included in replies.
            </p>
            {notes.map((n) => (
              <div className="note" key={n.id}>
                <strong>{n.author}</strong>
                <p>{n.text}</p>
              </div>
            ))}
            {box.can_write && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await post(`/messages/${m.id}/notes`, { text: note });
                    setNotes(await api(`/messages/${m.id}/notes`));
                    setNote("");
                  } catch (ex) {
                    notify((ex as Error).message);
                  }
                }}
              >
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Leave a note for your team…"
                  required
                  maxLength={5000}
                />
                <button className="secondary">Add note</button>
              </form>
            )}
          </>
        )}
      </section>
    </article>
  );
}

function Composer({
  draft,
  boxes,
  close,
  notify,
  refresh,
  onSaved,
}: {
  draft: Partial<Draft>;
  boxes: Mailbox[];
  close: () => void;
  notify: (s: string) => void;
  refresh: () => Promise<void>;
  onSaved: (d: Draft) => void;
}) {
  const MAX_COMPOSER_ATTACHMENT_BYTES = 10 * 1024 * 1024;
  const [data, setData] = useState(draft),
    [attachmentUploads, setAttachmentUploads] = useState<
      { filename: string; content_type: string; content_base64: string }[]
    >([]),
    [busy, setBusy] = useState(false),
    [schedule, setSchedule] = useState(""),
    [windowMode, setWindowMode] = useState<
      "normal" | "minimized" | "fullscreen"
    >("normal"),
    [pinned, setPinned] = useState(true),
    [aiOpen, setAiOpen] = useState(false),
    [previewOpen, setPreviewOpen] = useState(false),
    [aiMode, setAiMode] = useState<"enhance" | "custom">("enhance"),
    [aiInstruction, setAiInstruction] = useState(""),
    [aiBusy, setAiBusy] = useState(false);
  useEffect(() => {
    setData(draft);
    setAttachmentUploads([]);
  }, [draft]);
  const readFile = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () =>
        resolve(String(reader.result).split(",", 2)[1] || "");
      reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
      reader.readAsDataURL(file);
    });
  const addFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    const storedBytes = (data.attachments || []).reduce(
      (sum, file) => sum + file.size,
      0,
    );
    const pendingBytes = attachmentUploads.reduce(
      (sum, file) => sum + Math.floor((file.content_base64.length * 3) / 4),
      0,
    );
    let total = storedBytes + pendingBytes;
    const next = [...attachmentUploads];
    try {
      for (const file of Array.from(files)) {
        if (file.size > MAX_COMPOSER_ATTACHMENT_BYTES) {
          notify(`${file.name} is larger than 10 MB.`);
          continue;
        }
        if (total + file.size > MAX_COMPOSER_ATTACHMENT_BYTES) {
          notify("Attachments are limited to 10 MB per message.");
          break;
        }
        next.push({
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          content_base64: await readFile(file),
        });
        total += file.size;
      }
      setAttachmentUploads(next);
    } catch (e) {
      notify((e as Error).message);
    }
  };
  const save = async () => {
    const payload = {
      mailbox_id: data.mailbox_id,
      to: data.to || "",
      cc: data.cc || "",
      subject: data.subject || "",
      body: data.body || "",
      html_body: data.html_body || "",
      reply_to: data.reply_to || "",
      attachments: attachmentUploads.length ? attachmentUploads : undefined,
      version: data.version,
    };
    const saved = data.id
      ? await api<Draft>("/drafts/" + data.id, {
          method: "PUT",
          body: JSON.stringify(payload),
        })
      : await post<Draft>("/drafts", payload);
    setData(saved);
    setAttachmentUploads([]);
    onSaved(saved);
    await refresh();
    return saved;
  };
  const run = async (action: "save" | "send" | "approve") => {
    setBusy(true);
    try {
      const saved = await save();
      if (action === "approve") {
        const approved = await post<Draft>(`/drafts/${saved.id}/approve`, {
          version: saved.version,
        });
        setData(approved);
        onSaved(approved);
        notify("This exact draft is approved.");
      } else if (action === "send") {
        if (saved.ai_generated) {
          notify(
            "Save and approve this draft, then use “Send approved draft”.",
          );
          return;
        }
        await post(`/drafts/${saved.id}/send`, {
          scheduled_at: schedule
            ? Math.floor(new Date(schedule).getTime() / 1000)
            : 0,
        });
        notify(
          "Queued with a 10-second cancellation window. View Drafts to cancel.",
        );
        close();
        await refresh();
      } else notify("Draft saved.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const set = (key: string, value: string) =>
    setData({ ...data, [key]: value, approved: false });
  const signatureFor = (box?: Mailbox) => {
    if (!box) return { text: "", html: "" };
    const text = box.signature ? `\n\n${box.signature}` : "";
    const markup =
      box.signature_html ||
      (box.signature
        ? `<div>${box.signature.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>")}</div>`
        : "");
    const html = markup
      ? `<!-- postlane-signature -->${box.logo_url && !markup.includes("<img") ? `<p><img src="${box.logo_url}" alt="Company logo" style="max-width:240px;height:auto"></p>` : ""}${markup}<!-- /postlane-signature -->`
      : "";
    return { text, html };
  };
  const stripMailboxSignatures = (value: string) => {
    let result = value;
    for (const box of boxes) {
      if (!box.signature) continue;
      const escaped = box.signature.replace(/[.*+?^()|[\\]\\\\]/g, "\\$&");
      const suffix = new RegExp("\\s*" + escaped + "\\s*$");
      while (suffix.test(result)) result = result.replace(suffix, "");
    }
    return result.replace(/\s+$/, "");
  };
  const changeMailbox = (mailboxId: string) => {
    const newBox = boxes.find((b) => b.id === mailboxId);
    const body = stripMailboxSignatures(data.body || "");
    const html = (data.html_body || "")
      .replace(
        /<!-- postlane-signature -->[\s\S]*?<!-- \/postlane-signature -->/g,
        "",
      )
      .trim();
    const signature = signatureFor(newBox);
    setData({
      ...data,
      mailbox_id: mailboxId,
      body: body.replace(/\s+$/, "") + signature.text,
      html_body: html + signature.html,
      approved: false,
    });
  };
  const runAiAssist = async () => {
    if (!previewBox?.ai_enabled) {
      notify("Enable external AI for this mailbox in Settings first.");
      return;
    }
    if (!aiInstruction.trim()) {
      notify("Tell the assistant what you want the email to say.");
      return;
    }
    setAiBusy(true);
    try {
      const result = await post<{ subject: string; body: string }>(
        "/ai/compose",
        {
          mailbox_id: data.mailbox_id,
          mode: aiMode,
          instruction: aiInstruction.trim(),
          subject: data.subject || "",
          body: stripMailboxSignatures(data.body || ""),
        },
      );
      const signature = signatureFor(previewBox);
      setData({
        ...data,
        subject: result.subject,
        body: result.body.trim() + signature.text,
        html_body: signature.html,
        ai_generated: true,
        approved: false,
      });
      setAiOpen(false);
      setAiInstruction("");
      notify("AI draft prepared. Review it before approving or sending.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  };
  const previewBox = boxes.find((b) => b.id === data.mailbox_id);
  const previewSignatureOnly = (data.html_body || "")
    .trim()
    .startsWith("<!-- postlane-signature -->");
  const previewPlain = stripMailboxSignatures(data.body || "");
  const escapedPreview = previewPlain
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\n/g, "<br>");
  const renderedPreview = previewSignatureOnly
    ? `<div>${escapedPreview}</div>${data.html_body || ""}`
    : data.html_body || `<div>${escapedPreview}</div>`;
  return (
    <div className={`compose-backdrop ${pinned ? "compose-is-pinned" : ""}`}>
      <section
        className={`composer composer-${windowMode}`}
        role="dialog"
        aria-modal="true"
        aria-label="Compose message"
      >
        <header>
          <span>
            <Mail size={17} />{" "}
            {data.ai_generated ? "Review AI draft" : "New message"}
          </span>
          <div className="composer-window-controls">
            <button
              className="icon-button"
              title={
                windowMode === "minimized"
                  ? "Restore composer"
                  : "Minimize composer"
              }
              onClick={() =>
                setWindowMode(
                  windowMode === "minimized" ? "normal" : "minimized",
                )
              }
              aria-label="Minimize composer"
            >
              —
            </button>
            <button
              className={`icon-button ${pinned ? "active" : ""}`}
              title={pinned ? "Unpin composer" : "Pin composer to bottom"}
              onClick={() => setPinned(!pinned)}
              aria-label="Pin composer"
            >
              {pinned ? "📌" : "📍"}
            </button>
            <button
              className="icon-button"
              title={
                windowMode === "fullscreen"
                  ? "Restore composer size"
                  : "Maximize composer"
              }
              onClick={() =>
                setWindowMode(
                  windowMode === "fullscreen" ? "normal" : "fullscreen",
                )
              }
              aria-label="Maximize composer"
            >
              □
            </button>
            <button
              className="icon-button"
              title="Close composer (unsaved changes are discarded)"
              onClick={close}
              aria-label="Close composer"
            >
              <X size={19} />
            </button>
          </div>
        </header>
        <div className="compose-fields">
          <label>
            From
            <select
              disabled={!!data.id || !!data.reply_to}
              value={data.mailbox_id}
              onChange={(e) => changeMailbox(e.target.value)}
            >
              {boxes
                .filter((b) => b.can_write)
                .map((b) => (
                  <option value={b.id} key={b.id}>
                    {b.email}
                  </option>
                ))}
            </select>
          </label>
          <label>
            To
            <input
              value={data.to || ""}
              onChange={(e) => set("to", e.target.value)}
              placeholder="recipient@example.com"
            />
          </label>
          <label>
            Cc
            <input
              value={data.cc || ""}
              onChange={(e) => set("cc", e.target.value)}
              placeholder="Add recipients"
            />
          </label>
          <label>
            Subject
            <input
              value={data.subject || ""}
              onChange={(e) => set("subject", e.target.value)}
              placeholder="A clear beginning"
            />
          </label>
        </div>
        <textarea
          className="compose-body"
          aria-label="Message body"
          value={data.body || ""}
          onChange={(e) => set("body", e.target.value)}
          placeholder="Write something worth opening…"
          disabled={data.status !== "draft"}
        />
        <div className="compose-ai-row">
          <button
            type="button"
            className="preview-button"
            onClick={() => setPreviewOpen(true)}
            aria-haspopup="dialog"
          >
            <Eye size={15} /> Preview
          </button>
          <button
            type="button"
            className="ai-assist-button"
            onClick={() => {
              setAiMode(data.body?.trim() ? "enhance" : "custom");
              setAiOpen(true);
            }}
            disabled={data.status !== "draft" || aiBusy}
          >
            <Sparkles size={15} /> AI Assist
          </button>
          <span>
            {previewBox?.ai_enabled
              ? "Enhance this draft or describe what you need."
              : "Enable AI for this mailbox in Settings to use assistance."}
          </span>
        </div>
        <div className="compose-attachments">
          <label className="attachment-button">
            <Paperclip size={15} /> Add attachments
            <input
              type="file"
              multiple
              onChange={(e) => {
                void addFiles(e.target.files);
                e.currentTarget.value = "";
              }}
              disabled={data.status !== "draft" || busy}
              aria-label="Add attachments"
            />
          </label>
          <span className="attachment-limit">Up to 10 MB total</span>
          {!!data.attachments?.length && (
            <div className="attached-files">
              {data.attachments.map((file) => (
                <span className="attached-file" key={file.id}>
                  <Paperclip size={13} /> {file.filename}
                </span>
              ))}
            </div>
          )}
          {!!attachmentUploads.length && (
            <div className="attached-files">
              {attachmentUploads.map((file, index) => (
                <span
                  className="attached-file"
                  key={`${file.filename}-${index}`}
                >
                  <Paperclip size={13} /> {file.filename}
                  <button
                    type="button"
                    onClick={() =>
                      setAttachmentUploads((items) =>
                        items.filter((_, i) => i !== index),
                      )
                    }
                    aria-label={`Remove ${file.filename}`}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
        <details className="compose-html-source">
          <summary>HTML email source (optional)</summary>
          <textarea
            className="compose-html-input"
            aria-label="HTML email source"
            value={data.html_body || ""}
            onChange={(e) => set("html_body", e.target.value)}
            placeholder="Optional HTML version. The plain-text version remains included for compatibility."
            disabled={data.status !== "draft"}
          />
        </details>
        {data.ai_generated && (
          <div className="approval-banner">
            <ShieldCheck size={17} />
            {data.approved
              ? "Approved. Editing requires a new approval."
              : "Review the recipients and content, then approve before sending."}
          </div>
        )}
        {data.status === "draft" ? (
          <>
            <div className="compose-schedule">
              <Clock size={14} />
              <label>
                Schedule{" "}
                <input
                  type="datetime-local"
                  value={schedule}
                  onChange={(e) => setSchedule(e.target.value)}
                />
              </label>
              <span>Optional · 10-second undo window</span>
            </div>
            <footer>
              <button
                className="primary"
                disabled={busy}
                onClick={async () => {
                  if (data.ai_generated && data.approved && data.id) {
                    setBusy(true);
                    try {
                      await post(`/drafts/${data.id}/send`, {
                        scheduled_at: schedule
                          ? Math.floor(new Date(schedule).getTime() / 1000)
                          : 0,
                      });
                      close();
                      await refresh();
                      notify("Approved draft queued.");
                    } catch (e) {
                      notify((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  } else void run(data.ai_generated ? "approve" : "send");
                }}
              >
                {busy ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <Send size={16} />
                )}{" "}
                {data.ai_generated
                  ? data.approved
                    ? "Send approved draft"
                    : "Save & approve"
                  : "Send"}
              </button>
              <button
                className="text-button"
                onClick={() => run("save")}
                disabled={busy}
              >
                Save draft
              </button>
              <span className="compose-status">
                {data.id ? "Saved draft" : "Not saved yet"}
              </span>
            </footer>
          </>
        ) : (
          <footer>
            <span className="label">{data.status}</span>
            {data.status === "queued" && (
              <button
                className="secondary"
                onClick={async () => {
                  try {
                    const d = await post<Draft>(`/drafts/${data.id}/cancel`);
                    onSaved(d);
                    await refresh();
                  } catch (e) {
                    notify((e as Error).message);
                  }
                }}
              >
                Cancel scheduled send
              </button>
            )}
            <p className="help">
              {data.status === "uncertain"
                ? data.error ||
                  "Check your provider before sending again; delivery status is uncertain."
                : data.status === "failed"
                  ? data.error ||
                    "Submission failed. Check mailbox authorization and provider settings."
                  : ""}
            </p>
          </footer>
        )}
        {aiOpen && (
          <div className="ai-assist-backdrop" role="presentation">
            <section
              className="ai-assist-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="ai-assist-title"
            >
              <div className="ai-assist-heading">
                <div>
                  <span className="ai-assist-kicker">
                    <Sparkles size={13} /> POSTLANE AI
                  </span>
                  <h2 id="ai-assist-title">Shape your email</h2>
                  <p>Turn a rough idea into a clear, polished draft.</p>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setAiOpen(false)}
                  aria-label="Close AI assistant"
                >
                  <X size={17} />
                </button>
              </div>
              <div
                className="ai-assist-tabs"
                role="tablist"
                aria-label="AI draft mode"
              >
                <button
                  type="button"
                  className={aiMode === "enhance" ? "active" : ""}
                  onClick={() => setAiMode("enhance")}
                >
                  Enhance existing
                </button>
                <button
                  type="button"
                  className={aiMode === "custom" ? "active" : ""}
                  onClick={() => setAiMode("custom")}
                >
                  Start from instructions
                </button>
              </div>
              <label className="ai-assist-label" htmlFor="ai-instruction">
                What should the email do?
              </label>
              <textarea
                id="ai-instruction"
                className="ai-assist-input"
                autoFocus
                value={aiInstruction}
                onChange={(e) => setAiInstruction(e.target.value)}
                placeholder={
                  aiMode === "enhance"
                    ? "Make it warmer, clearer, and keep the request concise…"
                    : "Write a friendly follow-up confirming tomorrow's meeting at 10:00…"
                }
                rows={5}
              />
              <div className="ai-assist-hint">
                <ShieldCheck size={14} /> Your mailbox signature is added
                separately and the result remains editable.
              </div>
              <div className="ai-assist-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setAiOpen(false)}
                  disabled={aiBusy}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="primary ai-generate-button"
                  onClick={() => void runAiAssist()}
                  disabled={aiBusy || !aiInstruction.trim()}
                >
                  {aiBusy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  {aiBusy ? "Preparing…" : "Prepare draft"}
                </button>
              </div>
            </section>
          </div>
        )}
        {previewOpen && (
          <div
            className="compose-preview-backdrop"
            onMouseDown={(e) => {
              if (e.target === e.currentTarget) setPreviewOpen(false);
            }}
          >
            <section
              className="compose-preview-modal"
              role="dialog"
              aria-modal="true"
              aria-label="Rendered email preview"
            >
              <header>
                <div>
                  <Eye size={17} />
                  <strong>Rendered preview</strong>
                </div>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setPreviewOpen(false)}
                  aria-label="Close rendered preview"
                >
                  <X size={19} />
                </button>
              </header>
              <div
                className="compose-preview-body"
                dangerouslySetInnerHTML={{ __html: renderedPreview }}
              />
            </section>
          </div>
        )}
      </section>
    </div>
  );
}
