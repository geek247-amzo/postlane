from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(Input):
    email: EmailStr
    password: str = Field(max_length=256)
    code: str = Field(default="", max_length=6)


class SetupInput(LoginInput):
    name: str = Field(min_length=1, max_length=120)
    token: str = Field(max_length=200)


class InitialMailboxAccess(Input):
    mailbox_id: str
    can_write: bool = False
    can_send: bool = False


class UserInput(Input):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=14, max_length=256)
    role: Literal["admin", "member"] = "member"
    grants: list[InitialMailboxAccess] = Field(default_factory=list, max_length=100)


class GrantInput(Input):
    user_id: str
    mailbox_id: str
    can_write: bool = True
    can_send: bool = False


class DomainInput(Input):
    name: str = Field(
        min_length=3,
        max_length=253,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    )


class CatchallInput(Input):
    destination: EmailStr


class MailboxInput(Input):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["hosted", "imap", "gmail", "microsoft"] = "hosted"
    management_mode: Literal["human", "shared", "ai"] = "human"
    password: str | None = Field(default=None, min_length=14, max_length=256)


class ConnectionInput(Input):
    imap_host: str = Field(min_length=1, max_length=253)
    imap_port: int = Field(default=993, ge=1, le=65535)
    smtp_host: str = Field(min_length=1, max_length=253)
    smtp_port: int = Field(default=465, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class PushSubscriptionInput(Input):
    endpoint: str = Field(min_length=20, max_length=2000)
    p256dh: str = Field(min_length=20, max_length=500)
    auth: str = Field(min_length=10, max_length=500)
    device: str = Field(default="", max_length=120)


class MailboxPatch(Input):
    management_mode: Literal["human", "shared", "ai"] | None = None
    ai_send_enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    ai_enabled: bool | None = None
    signature: str | None = Field(default=None, max_length=5000)
    signature_html: str | None = Field(default=None, max_length=20000)
    logo_url: str | None = Field(default=None, max_length=2000)
    position: int | None = Field(default=None, ge=0, le=10000)


class FolderInput(Input):
    mailbox_id: str
    name: str = Field(min_length=1, max_length=120, pattern=r"^[^\x00-\x1f]+$")


class MessagePatch(Input):
    unread: bool | None = None
    starred: bool | None = None
    folder: str | None = Field(default=None, min_length=1, max_length=120)
    labels: list[str] | None = Field(default=None, max_length=20)
    snoozed_until: int | None = Field(default=None, ge=0)
    assigned_to: str | None = None

    @field_validator("labels")
    @classmethod
    def labels_valid(cls, v):
        if v and any(not s.strip() or len(s) > 40 for s in v):
            raise ValueError("Labels must be 1–40 characters")
        return v


class SpamFeedbackInput(Input):
    verdict: Literal["spam", "not_spam"]


class OutboundAttachmentInput(Input):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(default="application/octet-stream", min_length=1, max_length=255)
    content_base64: str = Field(min_length=1, max_length=14_000_000)
    inline: bool = False
    content_id: str = Field(default="", max_length=500)


class DraftInput(Input):
    mailbox_id: str
    to: str = Field(default="", max_length=4000)
    cc: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=998)
    body: str = Field(default="", max_length=100000)
    html_body: str = Field(default="", max_length=200000)
    reply_to: str = ""
    attachments: list["OutboundAttachmentInput"] | None = Field(default=None, max_length=20)
    forward_attachment_ids: list[str] | None = Field(default=None, max_length=20)
    version: int | None = None

    @field_validator("to", "cc", "subject")
    @classmethod
    def no_header_injection(cls, v):
        if "\r" in v or "\n" in v:
            raise ValueError("Headers cannot contain newlines")
        return v


class AiComposeInput(Input):
    mailbox_id: str
    mode: Literal["enhance", "custom"] = "enhance"
    instruction: str = Field(min_length=3, max_length=8000)
    subject: str = Field(default="", max_length=998)
    body: str = Field(default="", max_length=100000)

    @field_validator("subject")
    @classmethod
    def no_subject_header_injection(cls, v):
        if "\r" in v or "\n" in v:
            raise ValueError("Subject cannot contain newlines")
        return v


class SendInput(Input):
    scheduled_at: int = Field(default=0, ge=0)


class ApiSendInput(Input):
    to: str = Field(min_length=1, max_length=4000)
    cc: str = Field(default="", max_length=4000)
    subject: str = Field(default="", max_length=998)
    body: str = Field(default="", max_length=100000)
    html_body: str = Field(default="", max_length=200000)
    reply_to: str = ""
    attachments: list["OutboundAttachmentInput"] = Field(default_factory=list, max_length=20)
    forward_attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    scheduled_at: int = Field(default=0, ge=0)

    @field_validator("to", "cc", "subject")
    @classmethod
    def no_header_injection(cls, v):
        if "\r" in v or "\n" in v:
            raise ValueError("Headers cannot contain newlines")
        return v


class ApprovalInput(Input):
    version: int = Field(ge=1)


class KeyInput(Input):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[
        Literal[
            "messages:read",
            "messages:write",
            "drafts:write",
            "mail:send",
            "aliases:manage",
        ]
    ] = Field(min_length=1)
    mailbox_ids: list[str] = Field(min_length=1, max_length=100)
    days: int = Field(default=90, ge=1, le=365)


class HookInput(Input):
    mailbox_id: str
    url: str = Field(max_length=2000)


class TextInput(Input):
    text: str = Field(min_length=1, max_length=5000)


class CodeInput(Input):
    code: str = Field(pattern=r"^\d{6}$")


class AliasInput(Input):
    email: EmailStr


class PasswordChangeInput(Input):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=14, max_length=256)
    code: str = Field(default="", max_length=6)


class MfaDisableInput(Input):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=6)


class UserStateInput(Input):
    active: bool


class AccountPreferencesInput(Input):
    default_mailbox_id: str = Field(default="", max_length=32)
