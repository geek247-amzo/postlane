"""Provider adapters. Never log tokens, message bodies, or server credentials."""

import base64
import email
import imaplib
import json
import os
import re
import smtplib
import ssl
from datetime import timezone
from email.message import EmailMessage
from email.policy import default
from email.utils import parsedate_to_datetime, make_msgid, formataddr
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote, urlparse
import httpx
from . import config
from .security import encrypt, decrypt
from .models import now


class ProviderError(Exception):
    pass


class DeliveryUncertain(ProviderError):
    pass


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "tr") and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


class SafeEmailHtml(HTMLParser):
    """Keep email presentation while removing active or unsafe HTML."""

    allowed_tags = {
        "a", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
        "div", "em", "font", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
        "i", "img", "li", "ol", "p", "pre", "small", "span", "strong",
        "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr",
        "u", "ul",
    }
    void_tags = {"br", "col", "hr", "img"}
    allowed_attrs = {
        "a": {"href", "title", "target", "rel"},
        "img": {"src", "alt", "title", "width", "height"},
        "*": {"align", "bgcolor", "class", "colspan", "height", "style", "valign", "width"},
    }

    def __init__(self, inline_images):
        super().__init__(convert_charrefs=True)
        self.inline_images = inline_images
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"meta", "link", "base"}:
            return
        if tag in {"head", "title", "script", "style", "iframe", "object", "embed", "form", "video", "audio"}:
            self.skip += 1
            return
        if self.skip or tag not in self.allowed_tags:
            return
        output = []
        allowed = self.allowed_attrs.get("*", set()) | self.allowed_attrs.get(tag, set())
        for name, value in attrs:
            name = name.lower()
            if name not in allowed or value is None or name.startswith("on"):
                continue
            value = str(value).strip()
            if name == "href":
                scheme = urlparse(value).scheme.lower()
                if scheme not in {"http", "https", "mailto"}:
                    continue
            if name == "src":
                if value.lower().startswith("cid:"):
                    value = self.inline_images.get(value[4:].strip("<>"), "")
                scheme = urlparse(value).scheme.lower()
                if scheme not in {"https", "data"} or (scheme == "data" and not value.lower().startswith("data:image/")):
                    continue
            if name == "style":
                lowered = value.lower()
                if any(token in lowered for token in ("url(", "expression", "javascript:", "-moz-binding")):
                    continue
            output.append(f' {name}="{escape(value, quote=True)}"')
        self.parts.append("<" + tag + "".join(output) + (" />" if tag in self.void_tags else ">"))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"head", "title", "script", "style", "iframe", "object", "embed", "form", "video", "audio"}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.allowed_tags and tag not in self.void_tags:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(escape(data))


def safe_email_html(value, inline_images=None):
    parser = SafeEmailHtml(inline_images or {})
    parser.feed(value)
    return "".join(parser.parts)[:750000]


def plain_html(value):
    p = TextExtractor()
    p.feed(value)
    return "".join(p.parts).strip()


def parse_mime(raw):
    msg = email.message_from_bytes(raw, policy=default)
    plain_part = None
    html_part = None
    if msg.is_multipart():
        # Some newsletters wrap alternative/related parts several levels deep;
        # get_body() can miss those, so inspect every non-attachment part.
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain" and plain_part is None:
                plain_part = part
            elif part.get_content_type() == "text/html" and html_part is None:
                html_part = part
    elif msg.get_content_type() == "text/html":
        html_part = msg
    else:
        plain_part = msg
    text = ""
    html_body = ""
    attachments = []
    for part in msg.walk():
        disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if disposition == "attachment" or (filename and disposition != "inline"):
            payload = part.get_payload(decode=True)
            if payload and len(payload) <= 5_000_000:
                attachments.append(
                    {
                        "filename": filename or "attachment",
                        "content_type": part.get_content_type() or "application/octet-stream",
                        "content_id": (part.get("Content-ID") or "").strip("<>"),
                        "inline": disposition == "inline",
                        "content": payload,
                    }
                )
    try:
        if plain_part and plain_part.get_content_type() == "text/plain":
            text = plain_part.get_content()
        if html_part:
            source = html_part.get_content()
            if isinstance(source, str):
                inline_images = {}
                for part in msg.walk():
                    content_id = (part.get("Content-ID") or "").strip("<>")
                    payload = part.get_payload(decode=True)
                    if content_id and part.get_content_maintype() == "image" and payload:
                        inline_images[content_id] = "data:%s;base64,%s" % (
                            part.get_content_type(),
                            base64.b64encode(payload).decode("ascii"),
                        )
                html_body = safe_email_html(source, inline_images)
                if not text:
                    text = plain_html(source)
    except (LookupError, UnicodeError):
        text = "[Message encoding could not be decoded]"
    try:
        date = parsedate_to_datetime(str(msg.get("Date", "")))
        timestamp = int(
            (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()
        )
    except (ValueError, TypeError, OverflowError):
        timestamp = now()
    return {
        "sender": str(msg.get("From", "")),
        "recipients": str(msg.get("To", "")),
        "subject": str(msg.get("Subject", "(No subject)"))[:1000],
        "body": text[:500000],
        "html_body": html_body,
        "authentication": " ".join(
            str(msg.get(header, ""))
            for header in ("Authentication-Results", "Received-SPF", "DKIM-Signature")
            if msg.get(header)
        ),
        "thread_id": str(
            msg.get("References") or msg.get("In-Reply-To") or msg.get("Message-ID", "")
        )[-500:],
        "received_at": timestamp,
        "has_attachments": bool(attachments)
        or any(p.get_content_disposition() == "attachment" for p in msg.walk()),
        "attachments": attachments,
    }


def checked_host(host):
    allowed = {
        x.strip().lower()
        for x in os.getenv("MAIL_ALLOWED_HOSTS", "").split(",")
        if x.strip()
    }
    if host.lower() not in allowed:
        raise ProviderError(
            "Mail host must be listed in MAIL_ALLOWED_HOSTS by the server operator"
        )
    return host


def imap_connection(cfg):
    host = checked_host(cfg["imap_host"])
    conn = imaplib.IMAP4_SSL(
        host,
        int(cfg.get("imap_port", 993)),
        ssl_context=ssl.create_default_context(),
        timeout=25,
    )
    conn.login(cfg["username"], cfg["password"])
    return conn


def get_token(box):
    cfg = decrypt(box.config)
    if cfg.get("expires_at", 0) > now() + 120:
        return cfg["access_token"]
    provider = box.provider
    prefix = "GOOGLE" if provider == "gmail" else "MICROSOFT"
    endpoint = (
        "https://oauth2.googleapis.com/token"
        if provider == "gmail"
        else "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    )
    with httpx.Client(timeout=25, trust_env=False) as client:
        result = client.post(
            endpoint,
            data={
                "grant_type": "refresh_token",
                "refresh_token": cfg.get("refresh_token", ""),
                "client_id": os.getenv(prefix + "_CLIENT_ID", ""),
                "client_secret": config.secret_value(prefix + "_CLIENT_SECRET"),
            },
        )
        if result.status_code != 200:
            raise ProviderError("Authorization expired; reconnect this account")
        token = result.json()
    cfg.update(
        access_token=token["access_token"],
        expires_at=now() + token.get("expires_in", 3600),
    )
    if token.get("refresh_token"):
        cfg["refresh_token"] = token["refresh_token"]
    box.config = encrypt(cfg)
    return cfg["access_token"]


def provider_http(box):
    return httpx.Client(
        headers={"Authorization": "Bearer " + get_token(box)},
        timeout=30,
        trust_env=False,
    )


def require_ok(response):
    if not response.is_success:
        raise ProviderError(
            f"Provider returned HTTP {response.status_code}; check account authorization"
        )
    return response.json() if response.content else {}


def fetch_messages(box):
    if box.provider in ("imap", "hosted"):
        cfg = decrypt(box.config)
        if not cfg:
            raise ProviderError("Connect this mailbox before syncing")
        conn = imap_connection(cfg)
        result = []
        try:
            for local, remote in cfg.get(
                "folders", {"inbox": "INBOX", "sent": "Sent"}
            ).items():
                status, _ = conn.select(
                    '"' + remote.replace('"', "") + '"', readonly=True
                )
                if status != "OK":
                    continue
                validity = conn.response("UIDVALIDITY")[1]
                epoch = (validity[0] or b"0").decode() if validity else "0"
                status, data = conn.uid("search", None, "ALL")
                if status != "OK":
                    continue
                for uid in data[0].split()[-100:]:
                    size_status, size_data = conn.uid("fetch", uid, "(RFC822.SIZE)")
                    if size_status != "OK":
                        continue
                    size_match = re.search(
                        rb"RFC822.SIZE (\d+)",
                        b" ".join(x for x in size_data if isinstance(x, bytes)),
                    )
                    if not size_match or int(size_match.group(1)) > 5_000_000:
                        continue
                    status, parts = conn.uid(
                        "fetch", uid, "(RFC822.SIZE FLAGS BODY.PEEK[])"
                    )
                    if status != "OK":
                        continue
                    for part in parts:
                        if isinstance(part, tuple) and len(part[1]) <= 5_000_000:
                            result.append(
                                {
                                    **parse_mime(part[1]),
                                    "remote_id": f"{remote}|{epoch}|{uid.decode()}",
                                    "folder": local,
                                    "unread": b"\\Seen" not in part[0],
                                }
                            )
            return result
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    if box.provider == "gmail":
        with provider_http(box) as c:
            listing = require_ok(
                c.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    params={"maxResults": 100},
                )
            )
            result = []
            for item in listing.get("messages", []):
                data = require_ok(
                    c.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}",
                        params={"format": "raw"},
                    )
                )
                labels = data.get("labelIds", [])
                result.append(
                    {
                        **parse_mime(base64.urlsafe_b64decode(data["raw"] + "===")),
                        "remote_id": data["id"],
                        "thread_id": data["threadId"],
                        "folder": "trash"
                        if "TRASH" in labels
                        else "spam"
                        if "SPAM" in labels
                        else "sent"
                        if "SENT" in labels
                        else "inbox"
                        if "INBOX" in labels
                        else "archive",
                        "unread": "UNREAD" in labels,
                    }
                )
            return result
    if box.provider == "microsoft":
        with provider_http(box) as c:
            result = []
            for remote, local in [("inbox", "inbox"), ("sentitems", "sent")]:
                data = require_ok(
                    c.get(
                        f"https://graph.microsoft.com/v1.0/me/mailFolders/{remote}/messages",
                        params={"$top": 100, "$orderby": "receivedDateTime desc"},
                        headers={"Prefer": 'outlook.body-content-type="html"'},
                    )
                )
                for m in data.get("value", []):
                    from datetime import datetime

                    sender = m.get("from", {}).get("emailAddress", {})
                    content = m.get("body", {}).get("content", "")
                    attachments = []
                    if m.get("hasAttachments"):
                        attachment_data = require_ok(
                            c.get(
                                f"https://graph.microsoft.com/v1.0/me/messages/{m['id']}/attachments",
                                params={"$top": 50},
                            )
                        )
                        for item in attachment_data.get("value", []):
                            encoded = item.get("contentBytes")
                            if item.get("@odata.type", "").endswith("fileAttachment") and encoded:
                                payload = base64.b64decode(encoded)
                                if len(payload) <= 5_000_000:
                                    attachments.append(
                                        {
                                            "filename": item.get("name", "attachment"),
                                            "content_type": item.get("contentType", "application/octet-stream"),
                                            "content_id": item.get("contentId", ""),
                                            "inline": bool(item.get("isInline")),
                                            "content": payload,
                                        }
                                    )
                    result.append(
                        {
                            "remote_id": m["id"],
                            "thread_id": m.get("conversationId", ""),
                            "sender": f"{sender.get('name', '')} <{sender.get('address', '')}>",
                            "recipients": ", ".join(
                                x["emailAddress"]["address"]
                                for x in m.get("toRecipients", [])
                            ),
                            "subject": m.get("subject", "")[:1000],
                            "body": plain_html(content)[:500000],
                            "html_body": safe_email_html(content),
                            "folder": local,
                            "unread": not m.get("isRead", False),
                            "received_at": int(
                                datetime.fromisoformat(
                                    m["receivedDateTime"].replace("Z", "+00:00")
                                ).timestamp()
                            ),
                            "has_attachments": m.get("hasAttachments", False),
                            "attachments": attachments,
                        }
                    )
            return result
    raise ProviderError("This mailbox has no live provider")


def build_mime(box, draft, attachments=None):
    m = EmailMessage()
    m["From"] = formataddr((box.name or "", box.email))
    m["To"] = draft.to
    if draft.cc:
        m["Cc"] = draft.cc
    m["Subject"] = draft.subject
    m["Message-ID"] = f"<postlane.{draft.id}@{box.email.split('@')[1]}>"
    m.set_content(draft.body)
    if draft.html_body:
        m.add_alternative(draft.html_body, subtype="html")
    for attachment in attachments or []:
        content_type = attachment.content_type or "application/octet-stream"
        maintype, _, subtype = content_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        m.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
            disposition="inline" if attachment.inline else "attachment",
            **({"cid": attachment.content_id} if attachment.content_id else {}),
        )
    return m


def send_message(box, draft, attachments=None):
    m = build_mime(box, draft, attachments)
    if box.provider in ("imap", "hosted"):
        cfg = decrypt(box.config)
        if not cfg:
            raise ProviderError("Connect an SMTP server first")
        host = checked_host(cfg["smtp_host"])
        port = int(cfg.get("smtp_port", 465))
        context = ssl.create_default_context()
        try:
            conn = (
                smtplib.SMTP_SSL(host, port, timeout=30, context=context)
                if port == 465
                else smtplib.SMTP(host, port, timeout=30)
            )
            with conn:
                if port != 465:
                    conn.ehlo()
                    conn.starttls(context=context)
                    conn.ehlo()
                conn.login(cfg["username"], cfg["password"])
                try:
                    refused = conn.send_message(m)
                    if refused:
                        raise DeliveryUncertain(
                            "Some recipients were rejected; verify provider delivery before retrying"
                        )
                except (smtplib.SMTPServerDisconnected, TimeoutError, OSError) as ex:
                    raise DeliveryUncertain(
                        "SMTP connection ended during submission; verify delivery before retrying"
                    ) from ex
        except smtplib.SMTPRecipientsRefused as ex:
            refused = ", ".join(sorted(ex.recipients))[:500]
            raise ProviderError(f"SMTP rejected recipient(s): {refused}") from ex
        except smtplib.SMTPResponseException as ex:
            reason = ex.smtp_error.decode(errors="replace") if isinstance(ex.smtp_error, bytes) else str(ex.smtp_error)
            raise ProviderError(f"SMTP rejected the request ({ex.smtp_code}): {reason[:300]}") from ex
    elif box.provider in ("gmail", "microsoft"):
        with provider_http(box) as c:
            try:
                if box.provider == "gmail":
                    r = c.post(
                        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                        json={"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()},
                    )
                else:
                    r = c.post(
                        "https://graph.microsoft.com/v1.0/me/sendMail",
                        content=base64.b64encode(m.as_bytes()),
                        headers={"Content-Type": "text/plain"},
                    )
                if r.status_code >= 500:
                    raise DeliveryUncertain(
                        "Provider submission status is uncertain; verify before retrying"
                    )
                require_ok(r)
            except httpx.TransportError as ex:
                raise DeliveryUncertain(
                    "Provider connection interrupted; verify delivery before retrying"
                ) from ex
    else:
        raise ProviderError("Demo mailboxes cannot send email")


def update_remote(box, message, changes):
    """Workspace labels/folders are local; read state is synchronized to provider."""
    if "unread" not in changes or box.provider == "demo":
        return
    if box.provider in ("hosted", "imap"):
        cfg = decrypt(box.config)
        conn = imap_connection(cfg)
        try:
            folder, epoch, uid = message.remote_id.rsplit("|", 2)
            if conn.select('"' + folder.replace('"', "") + '"')[0] != "OK":
                raise ProviderError("Remote folder is unavailable")
            current = (conn.response("UIDVALIDITY")[1][0] or b"0").decode()
            if current != epoch:
                raise ProviderError(
                    "Mailbox changed; sync before updating this message"
                )
            status, _ = conn.uid(
                "store",
                uid,
                "-FLAGS.SILENT" if changes["unread"] else "+FLAGS.SILENT",
                "(\\Seen)",
            )
            if status != "OK":
                raise ProviderError("Provider could not update read status")
        finally:
            conn.logout()
    else:
        with provider_http(box) as c:
            if box.provider == "gmail":
                require_ok(
                    c.post(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(message.remote_id, safe='')}/modify",
                        json={
                            "addLabelIds": ["UNREAD"] if changes["unread"] else [],
                            "removeLabelIds": [] if changes["unread"] else ["UNREAD"],
                        },
                    )
                )
            else:
                require_ok(
                    c.patch(
                        f"https://graph.microsoft.com/v1.0/me/messages/{quote(message.remote_id, safe='')}",
                        json={"isRead": not changes["unread"]},
                    )
                )
