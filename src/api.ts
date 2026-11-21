export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  mfa_enabled: boolean;
  default_mailbox_id: string;
};
export type Mailbox = {
  id: string;
  name: string;
  email: string;
  provider: string;
  color: string;
  status: string;
  error: string;
  unread: number;
  ai_enabled: boolean;
  management_mode?: "human" | "shared" | "ai";
  ai_send_enabled?: boolean;
  signature: string;
  signature_html: string;
  logo_url: string;
  can_write: boolean;
  can_send: boolean;
  position: number;
  last_sync: number;
};
export type Message = {
  id: string;
  mailbox_id: string;
  sender: string;
  recipients: string;
  subject: string;
  preview: string;
  body?: string;
  html_body?: string;
  folder: string;
  labels: string[];
  unread: boolean;
  starred: boolean;
  received_at: number;
  snoozed_until: number;
  assigned_to: string;
  has_attachments: boolean;
  thread_id: string;
  spam_score: number;
  spam_verdict: "unchecked" | "clean" | "likely_spam" | "spam";
  spam_reasons: string[];
  attachments?: Attachment[];
};
export type Attachment = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  inline: boolean;
};
export type Draft = {
  id: string;
  mailbox_id: string;
  to: string;
  cc: string;
  subject: string;
  body: string;
  html_body: string;
  reply_to: string;
  ai_generated: boolean;
  approved: boolean;
  approval_source?: "agent_policy" | "human" | "none";
  status: string;
  error?: string;
  scheduled_at: number;
  version: number;
  attachments?: Attachment[];
};
export type Folder = {
  id: string;
  mailbox_id: string;
  name: string;
  position: number;
};
let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrf,
      ...options.headers,
    },
    credentials: "same-origin",
  });
  const data = await response
    .json()
    .catch(() => ({ detail: "The server returned an unexpected response" }));
  if (!response.ok) {
    const error = new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail
              .map(
                (issue: { loc?: (string | number)[]; msg?: string }) =>
                  `${(issue.loc || []).filter((part) => part !== "body").join(".")}: ${issue.msg || "Invalid value"}`,
              )
              .join("; ")
          : "The request could not be validated",
    ) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return data;
}
export const post = <T = any>(path: string, data: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export const patch = <T = any>(path: string, data: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
