"""Narrow business operations. Targets come from saved connections, never model URLs."""

import json
import os
import re
from sqlalchemy import select, or_
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .work_providers import call_json, call_text
from .security import decrypt, encrypt, mailbox_access
from .models import Message, Draft, now
from . import config

OPERATIONS = {
    "clickup": {
        "list_tasks": {},
        "create_task": {"title": "Task title", "body": "Description"},
    },
    "notion": {
        "search_pages": {"query": "Search text"},
        "read_page": {"file_id": "Page ID from search_pages"},
        "create_page": {"title": "Page title", "body": "Plain text content"},
    },
    "drive": {
        "search_files": {"query": "Filename text"},
        "read_document": {
            "file_id": "Google Doc or plain-text file ID from search_files"
        },
        "create_document": {"title": "Document name", "body": "Plain text content"},
    },
    "mail": {
        "search_mail": {"query": "Subject or body search"},
        "create_draft": {
            "to": "Recipient email",
            "title": "Subject",
            "body": "Message text",
        },
    },
    "linkedin": {"publish_post": {"body": "Exact PUBLIC post text"}},
    "facebook": {
        "list_posts": {},
        "publish_post": {"body": "Exact PUBLIC page post text"},
    },
    "instagram": {
        "list_posts": {},
        "publish_image": {
            "body": "Exact PUBLIC caption",
            "image_url": "Public HTTPS JPEG image URL; no upload is performed by Postlane",
        },
    },
}
READ_OPERATIONS = {
    "list_tasks",
    "search_pages",
    "search_files",
    "search_mail",
    "list_posts",
    "read_page",
    "read_document",
}


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(default="", max_length=200)
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=10000)
    to: str = Field(default="", max_length=320)
    image_url: str = Field(default="", max_length=2000)
    file_id: str = Field(default="", max_length=100)


def validated(provider, operation, values):
    if operation not in OPERATIONS.get(provider, {}):
        raise HTTPException(422, "Operation is not available on this connection")
    allowed = OPERATIONS[provider][operation]
    if set(values) - set(allowed):
        raise HTTPException(422, "Unexpected action argument")
    result = Arguments.model_validate(values).model_dump()
    if "file_id" in allowed and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,100}", result["file_id"]
    ):
        raise HTTPException(422, "Invalid document identifier")
    if any(not result[k].strip() for k in allowed if k != "query"):
        raise HTTPException(422, "Required action content is missing")
    if provider == "mail" and operation == "create_draft":
        from email_validator import validate_email, EmailNotValidError

        try:
            result["to"] = validate_email(
                result["to"], check_deliverability=False
            ).normalized
        except EmailNotValidError:
            raise HTTPException(
                422, "A single valid recipient email is required"
            ) from None
    if provider == "notion" and len(result["body"]) > 2000:
        raise HTTPException(
            422, "Notion page text is limited to 2,000 characters per action"
        )
    if provider == "linkedin" and len(result["body"]) > 3000:
        raise HTTPException(422, "LinkedIn posts are limited to 3,000 characters")
    if provider == "instagram" and operation == "publish_image":
        from urllib.parse import urlsplit
        import ipaddress

        parts = urlsplit(result["image_url"])
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or "." not in parts.hostname
        ):
            raise HTTPException(422, "Instagram needs a public HTTPS image URL")
        try:
            if not ipaddress.ip_address(parts.hostname).is_global:
                raise HTTPException(422, "Private image addresses are not allowed")
        except ValueError:
            pass
        if len(result["body"]) > 2200:
            raise HTTPException(
                422, "Instagram captions are limited to 2,200 characters"
            )
    return {k: result[k] for k in allowed}


def settings_valid(provider, settings):
    allowed = {
        "clickup": {"list_id"},
        "notion": {"page_id"},
        "drive": set(),
        "mail": {"mailbox_id"},
        "linkedin": {"author"},
        "facebook": {"page_id"},
        "instagram": {"account_id"},
    }
    if provider not in allowed or set(settings) != allowed[provider]:
        raise HTTPException(422, "Connection settings do not match this provider")
    for key, value in settings.items():
        if not isinstance(value, str):
            raise HTTPException(422, "Connection identifiers must be text")
        pattern = (
            r"urn:li:(person|organization):[A-Za-z0-9_-]+"
            if key == "author"
            else r"[A-Za-z0-9_-]{1,100}"
        )
        if not re.fullmatch(pattern, value):
            raise HTTPException(422, "Invalid connection identifier")
    return settings


def execute(connection, operation, values, db, principal):
    args = validated(connection.provider, operation, values)
    cfg = settings_valid(connection.provider, json.loads(connection.settings))
    token = decrypt(connection.secret).get("token", "")
    provider = connection.provider
    headers = {"Authorization": "Bearer " + token}
    if provider == "mail":
        box = mailbox_access(
            db,
            principal,
            cfg["mailbox_id"],
            "write" if operation == "create_draft" else "read",
        )
        if not box.ai_enabled:
            raise HTTPException(
                403, "Enable external AI for this mailbox before using it in Work"
            )
        if operation == "search_mail":
            matches = db.scalars(
                select(Message)
                .where(
                    Message.mailbox_id == box.id,
                    or_(
                        Message.subject.contains(args["query"], autoescape=True),
                        Message.body.contains(args["query"], autoescape=True),
                    ),
                )
                .order_by(Message.received_at.desc())
                .limit(10)
            )
            return [
                {
                    "id": m.id,
                    "sender": m.sender,
                    "subject": m.subject,
                    "text": m.body[:1200],
                }
                for m in matches
            ]
        draft = Draft(
            user_id=principal.user.id,
            mailbox_id=box.id,
            to=args["to"],
            subject=args["title"],
            body=args["body"],
            ai_generated=True,
        )
        db.add(draft)
        db.flush()
        return {
            "draft_id": draft.id,
            "status": "draft",
            "next_step": "Review, approve and send from Mail. Work cannot send email.",
        }
    if provider == "clickup":
        headers["Authorization"] = token
        url = f"https://api.clickup.com/api/v2/list/{cfg['list_id']}/task"
        if operation == "list_tasks":
            result = call_json(
                "GET",
                url,
                headers=headers,
                params={"page": 0, "include_closed": "false"},
            )
            return [
                {
                    "id": t["id"],
                    "name": t.get("name"),
                    "description": (t.get("description") or "")[:2000],
                    "status": t.get("status", {}).get("status"),
                }
                for t in result.get("tasks", [])[:30]
            ]
        return call_json(
            "POST",
            url,
            headers=headers,
            json={
                "name": args["title"],
                "description": args["body"],
                "check_required_custom_fields": True,
            },
        )
    if provider == "notion":
        headers["Notion-Version"] = "2022-06-28"
        if operation == "read_page":
            result = call_json(
                "GET",
                f"https://api.notion.com/v1/blocks/{args['file_id']}/children",
                headers=headers,
                params={"page_size": 50},
            )
            return {
                "blocks": [
                    {
                        "type": b["type"],
                        "text": "".join(
                            t.get("plain_text", t.get("text", {}).get("content", ""))
                            for t in b.get(b["type"], {}).get("rich_text", [])
                        ),
                    }
                    for b in result.get("results", [])
                ],
                "has_more": result.get("has_more", False),
            }
        if operation == "search_pages":
            result = call_json(
                "POST",
                "https://api.notion.com/v1/search",
                headers=headers,
                json={
                    "query": args["query"],
                    "page_size": 20,
                    "filter": {"value": "page", "property": "object"},
                },
            )
            return [
                {"id": p["id"], "url": p.get("url"), "properties": p.get("properties")}
                for p in result.get("results", [])
            ]
        return call_json(
            "POST",
            "https://api.notion.com/v1/pages",
            headers=headers,
            json={
                "parent": {"page_id": cfg["page_id"]},
                "properties": {
                    "title": {"title": [{"text": {"content": args["title"]}}]}
                },
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": args["body"]}}
                            ]
                        },
                    }
                ],
            },
        )
    if provider == "drive":
        secret = decrypt(connection.secret)
        if secret.get("expires_at", 0) < now() + 120:
            result = call_json(
                "POST",
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                    "client_secret": config.secret_value("GOOGLE_CLIENT_SECRET"),
                    "refresh_token": secret.get("refresh_token", ""),
                    "grant_type": "refresh_token",
                },
            )
            secret.update(
                token=result["access_token"],
                expires_at=now() + result.get("expires_in", 3600),
            )
            connection.secret = encrypt(secret)
        headers["Authorization"] = "Bearer " + secret["token"]
        if operation == "read_document":
            url = f"https://www.googleapis.com/drive/v3/files/{args['file_id']}"
            metadata = call_json(
                "GET", url, headers=headers, params={"fields": "id,name,mimeType"}
            )
            mime = metadata.get("mimeType")
            if mime not in ("application/vnd.google-apps.document", "text/plain"):
                raise HTTPException(
                    422,
                    "Only Google Docs and plain-text files can be read in this release",
                )
            content_url = url + (
                "/export?mimeType=text%2Fplain"
                if mime == "application/vnd.google-apps.document"
                else "?alt=media"
            )
            return {
                "id": args["file_id"],
                "name": metadata.get("name"),
                "text": call_text(content_url, headers),
            }
        if operation == "search_files":
            query = args["query"].replace("\\", "\\\\").replace("'", "\\'")
            return call_json(
                "GET",
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={
                    "q": f"trashed = false and name contains '{query}'",
                    "pageSize": 30,
                    "fields": "files(id,name,mimeType,webViewLink),nextPageToken",
                },
            )
        # Multipart upload converts plain text into a Google document in one request.
        import secrets

        boundary = "postlane_" + secrets.token_hex(16)
        metadata = json.dumps(
            {"name": args["title"], "mimeType": "application/vnd.google-apps.document"}
        )
        content = f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadata}\r\n--{boundary}\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n{args['body']}\r\n--{boundary}--\r\n"
        headers["Content-Type"] = f"multipart/related; boundary={boundary}"
        return call_json(
            "POST",
            "https://www.googleapis.com/upload/drive/v3/files",
            headers=headers,
            params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
            content=content.encode(),
        )
    if provider == "linkedin":
        headers.update(
            {"LinkedIn-Version": "202609", "X-Restli-Protocol-Version": "2.0.0"}
        )
        return call_json(
            "POST",
            "https://api.linkedin.com/rest/posts",
            headers=headers,
            json={
                "author": cfg["author"],
                "commentary": args["body"],
                "visibility": "PUBLIC",
                "distribution": {
                    "feedDistribution": "MAIN_FEED",
                    "targetEntities": [],
                    "thirdPartyDistributionChannels": [],
                },
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        )
    if provider == "facebook":
        url = f"https://graph.facebook.com/v25.0/{cfg['page_id']}/feed"
        if operation == "list_posts":
            return call_json(
                "GET",
                url,
                headers=headers,
                params={"fields": "id,message,created_time", "limit": 20},
            )
        return call_json("POST", url, headers=headers, json={"message": args["body"]})
    if provider == "instagram":
        url = f"https://graph.facebook.com/v25.0/{cfg['account_id']}"
        if operation == "list_posts":
            return call_json(
                "GET",
                url + "/media",
                headers=headers,
                params={"fields": "id,caption,permalink,timestamp", "limit": 20},
            )
        container = call_json(
            "POST",
            url + "/media",
            headers=headers,
            json={"image_url": args["image_url"], "caption": args["body"]},
        )
        return call_json(
            "POST",
            url + "/media_publish",
            headers=headers,
            json={"creation_id": container["id"]},
        )
    raise HTTPException(422, "Unsupported operation")
