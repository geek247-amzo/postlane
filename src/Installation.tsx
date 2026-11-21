import { useEffect, useState, FormEvent } from "react";
import { api, post } from "./api";

export function Installation({ notify }: { notify: (value: string) => void }) {
  const [status, setStatus] = useState<any>(null);
  const load = () =>
    api("/installation")
      .then(setStatus)
      .catch((e) => notify(e.message));
  useEffect(() => {
    void load();
  }, []);
  return (
    <section className="panel">
      <div className="panel-heading">
        <h3>Installation checks</h3>
        <button className="secondary" onClick={load}>
          Refresh
        </button>
      </div>
      <div className="settings-body">
        <p>
          Configuration is the first step. Verify real delivery and automation
          before importing business mail.
        </p>
        {!status ? (
          <p>Loading installation status...</p>
        ) : (
          <>
            <div className="environment-row">
              <span>Environment</span>
              <strong>{status.mode}</strong>
            </div>
            <div className="environment-row">
              <span>Database</span>
              <strong>{status.database}</strong>
            </div>
            <div className="environment-row">
              <span>Worker heartbeat</span>
              <strong>
                {status.worker.healthy ? "Recent" : "Missing or stale"}
              </strong>
            </div>
            <div className="environment-row">
              <span>Verified domains</span>
              <strong>{status.domains_verified}</strong>
            </div>
            <div className="environment-row">
              <span>Connected mailboxes</span>
              <strong>
                {status.connected_mailboxes} / {status.mailboxes}
              </strong>
            </div>
            {Object.entries(status.integrations).map(([name, enabled]) => (
              <div className="environment-row" key={name}>
                <span>{name}</span>
                <strong>
                  {enabled ? "Configured; verify live" : "Not configured"}
                </strong>
              </div>
            ))}
            <div className="environment-row">
              <span>Uncertain submissions</span>
              <strong>{status.uncertain_submissions}</strong>
            </div>
            <div className="environment-row">
              <span>Failed webhook deliveries</span>
              <strong>{status.failed_webhooks}</strong>
            </div>
            <p className="help">OAuth callback: {status.oauth_callback}</p>
          </>
        )}
        <p className="help">
          Operator guide: docs/agent-setup.md in your private repository. API
          schema:{" "}
          <a href="/api/openapi.json" target="_blank" rel="noreferrer">
            OpenAPI
          </a>
          .
        </p>
      </div>
    </section>
  );
}

export function PasswordSettings({
  notify,
}: {
  notify: (value: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setBusy(true);
    try {
      await post("/auth/password", data);
      form.reset();
      notify("Password changed. Other browser sessions have been signed out.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <h3>Change password</h3>
      </div>
      <form className="settings-body stack-form" onSubmit={submit}>
        <label>
          Current password
          <input
            name="current_password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={256}
          />
        </label>
        <label>
          New password
          <input
            name="new_password"
            type="password"
            autoComplete="new-password"
            required
            minLength={14}
            maxLength={256}
          />
        </label>
        <label>
          Authenticator code (if enabled)
          <input
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
          />
        </label>
        <button className="secondary" disabled={busy}>
          {busy ? "Saving..." : "Update password"}
        </button>
      </form>
    </section>
  );
}
