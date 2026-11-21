# CloudMonkey Work

Work expands Postlane into a private business workspace with AI chat and connected actions. The inbox reply and composer assistants also use your newest enabled Hermes webhook connection when present, otherwise your most recently added enabled API-key provider connection. They run text generation only, never Work tools; Hermes replies must contain no actions. In Work chat, a Hermes connection is Jeff's reply-only assistant: it receives no selected integrations, returns plain text, and cannot propose actions or send mail. Other AI connections can use only the Work integrations selected for that conversation. Connections stay private to their owner; mailbox AI opt-in, write access and human review still apply. If no personal API-key connection exists, the legacy operator-configured mail AI remains available. Provider failures do not switch to another identity. Open **Work** in the sidebar, then **Connections**.

## Connect a model and business tools

1. Add OpenAI, Gemini, Claude or DeepSeek with your own API key. Click **Test key & load models**, choose an available text model, then **Save connection**. Editing the key clears the previous model choices and requires a new check. The authenticated model-list request validates listing access without generating text; it does not prove generation permissions or available billing credit. Keys are encrypted server-side and never returned after saving. Codex account authorization and Hermes webhook setup remain separate.
2. Add the business connections below. Connections and chat history are private to their creating user, including from other workspace administrators. Each person supplies their own authorized credentials.
3. Start a conversation, select a model and the specific connections it may use, then confirm external AI data sharing. Reads run automatically on those connections. Every change or public post appears as an immutable action card with its exact arguments and **Approve & run** / **Reject** controls.
4. After approving a change, ask the agent to continue if further work is needed. Read-only steps can run in a bounded loop automatically. There is no unattended, indefinite background agent.

| Connection                     | Credential / target                                                 | Available actions                                                           |
| ------------------------------ | ------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| ClickUp                        | Personal API token and list ID                                      | List recent open tasks with descriptions; create tasks in that list         |
| Notion                         | Internal integration token; shared parent page ID                   | Search shared pages, read first 50 top-level blocks, create a child page    |
| Gmail and other connected mail | Existing Postlane mailbox ID and current mailbox grants             | Search local synchronized mail; prepare approval-required drafts            |
| Google Drive                   | OAuth account consent                                               | Search files, read Google Docs/plain-text files, create Google Docs         |
| LinkedIn                       | Authorized access token and person/organization author URN          | Publish a text post after explicit approval                                 |
| Facebook Pages                 | Page access token and Page ID                                       | Read recent posts; publish a text post after approval                       |
| Instagram Business             | Facebook-linked professional account ID and authorized access token | Read recent media; publish one public JPEG image and caption after approval |

Notion searches cover pages shared with the integration, not only its configured creation parent. ClickUp reads the first page, capped at 30 tasks. Mail search returns up to 10 cached messages with bounded text; existing recent-sync limitations still apply. Notion page creation is limited to 2,000 text characters. Drive text reading is bounded to 200 KB downloaded / 20,000 characters returned; PDFs, spreadsheets and attachments are not parsed. No remote images are fetched by the application for previews.

## Google setup

Use the existing server GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET for both Gmail mailbox OAuth and Google Drive. Enable the Gmail API and Drive API in the Google Cloud project. Register both redirect URIs:

```text
https://YOUR_APP_HOST/api/oauth/callback
https://YOUR_APP_HOST/api/work/oauth/callback
```

The first callback connects Gmail mailboxes from Admin. The second callback connects Drive from Work.

### Gmail to Work sequence

1. In Admin, add a mailbox with account type **Google / Gmail** and the exact Gmail address.
2. Open the mailbox settings, choose **Authorize Google account**, and complete consent in the same browser.
3. Run a mailbox sync and confirm recent mail appears in Postlane.
4. Enable external AI on that mailbox only after the mailbox owner agrees to the selected provider policy.
5. In Work, add **Gmail & connected mail**, choose that mailbox, and include it in a conversation.

Work reads only the locally synchronized, grant-authorized mailbox cache. It can create approval-required drafts, but it cannot send email.

### Drive callback

```text
https://YOUR_APP_HOST/api/work/oauth/callback
```

Drive asks for `drive.readonly` and `drive.file`: reading existing Drive content and creating app-managed documents. These scopes have provider verification/consent requirements; complete them for the intended deployment. After saving the Drive connection, choose **Authorize Google** in the same browser. Refresh tokens are encrypted. Revoke provider grants and disconnect when offboarding.

Mail access reuses existing Gmail/Microsoft/IMAP connections. A mailbox must have external AI explicitly enabled, and the current person must have its relevant grant. Work does not send mail: its drafts enter the existing review/approval/send flow. Turning off mailbox AI or revoking its grant blocks further use and access to Work histories tied to that mailbox.

## ClickUp setup

Create a ClickUp personal API token for the operator or service account that owns the target workspace. Save one Work connection per ClickUp list using the list ID from the ClickUp URL or API. The adapter can read the first page of open tasks and create approved tasks in that list with `check_required_custom_fields=true`; if ClickUp requires custom fields that are not supplied, the action fails instead of silently creating an incomplete task.

Use separate ClickUp connections for separate businesses or clients. Do not paste tokens into chat. Disable or disconnect the Work connection when offboarding a user; pending task actions are cancelled when the connection state changes.

## Social setup

Use developer applications and tokens authorized for the target business accounts. This release accepts access tokens; social OAuth registration, token renewal, provider review and account permissions are operator-managed. LinkedIn uses Posts API version 202609 and needs the applicable member/organization posting permission. Facebook needs Page read/post permissions such as pages_read_engagement and pages_manage_posts. Instagram uses the Facebook Login API for a professional account linked to a Page, with instagram_basic and instagram_content_publish plus applicable Page permissions. It uses Graph API v25.0. Personal Instagram accounts are unsupported.

Instagram publishing uses a public HTTPS JPEG URL that Meta fetches, followed by container publication. Images must satisfy Meta's requirements. Video/Reels, carousels, scheduling, comments and analytics are not implemented. If either publication step cannot be confirmed, the action becomes **uncertain** and never retries automatically. Inspect Meta before requesting another publication.

## Codex account sign-in

Codex account authentication is separate from OpenAI API keys. The optional bridge uses the official app-server device-code flow and keeps a separate Codex profile for each Postlane user. It does not turn a ChatGPT subscription into a general OpenAI API key. Eligibility, organizational policy, device authorization availability and account limits still apply. See [official Codex authentication](https://developers.openai.com/codex/auth) and [app-server protocol](https://developers.openai.com/codex/app-server).

On the Ubuntu installation:

```sh
python3 scripts/enable_codex.py
docker compose -f compose.yaml -f deploy/compose.codex.yaml config --quiet
docker compose -f compose.yaml -f deploy/compose.codex.yaml up -d --build
```

The generator preserves an existing bridge secret. Use the same Compose override for subsequent updates. The bridge has no public port, no mail/database volumes, no application encryption key and no business integration tokens. It runs Codex CLI 0.155.1, as a non-root process with a read-only root, dropped capabilities and a separate auth volume. Native shell, unified execution, account apps, web search and multi-agent features are disabled; server tool requests are rejected. Business actions always run through Postlane's validated adapters and approval checks.

In **Work → Connections**, choose **Sign in**, complete the OpenAI device page with your displayed code, then **Check account**. Add a Codex connection with a model ID permitted by that account. Never paste ChatGPT cookies, auth.json or OAuth refresh tokens into a connection or chat. Sign out from this panel to remove account access; merely disabling an AI connection does not log the account out of the bridge.

Treat the `codex-accounts` volume as sensitive authentication storage. Codex manages its own credentials; they are not encrypted with Postlane's Fernet key. Use encrypted host storage and backups. Deleting a Work chat deletes the app history, not provider-side retention; Codex chats are requested as ephemeral. OpenAI API requests set store=false; other providers' retention and data-use terms remain applicable.

## Execution guarantees and limits

Actions expire after 24 hours. Changing connection state cancels pending actions and advances a version checked at execution. A compare-and-set claim prevents the same approved action from being executed twice. Interrupted or ambiguous writes become uncertain, not automatically retryable. Repeating the same request in a new chat can still create a new action; this is not provider-wide exactly-once delivery.

Each user turn allows at most three model calls, five actions per model response, and four concurrent generations per installation. A user has ten chat requests per 15 minutes; this conservative limit currently shares the authentication throttle utility. Model responses must match the action schema. Unknown connections, URL injection, arbitrary tools and extra action fields fail closed. Work API endpoints require human browser sessions and CSRF protection; automation bearer keys cannot operate them.

Generated actions are proposals, not proof that a task ran. Read results and action outputs are untrusted content. The interface renders text without executing HTML. Connections selected together may contribute data to the same external model context; choose only the accounts appropriate for that conversation. Set provider-side spending limits before enabling team usage.

## Validation before rollout

Automated tests cover adapter request formats, automatic reads, bounded loops, ownership, secret encryption, mailbox consent/grants, approval, duplicate submissions and uncertain writes. The optional bridge CI checks initialization, empty account state and disabled execution features without a real login. Live model completions, social permissions/publication, Google consent/refresh and signed-in Codex responses still require controlled account testing. No browser was available in the development environment; run desktop/mobile acceptance on the deployed interface before handing it to customers.

Official API references: [OpenAI Responses](https://developers.openai.com/api/docs/guides/text), [Gemini](https://ai.google.dev/gemini-api/docs/text-generation), [Claude Messages](https://platform.claude.com/docs/en/api/messages/create), [DeepSeek](https://api-docs.deepseek.com/), [ClickUp](https://developer.clickup.com/reference/createtask), [Notion](https://developers.notion.com/reference/post-page), [Drive](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list), [LinkedIn](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api), [Facebook Pages](https://developers.facebook.com/docs/pages-api/posts/), [Instagram publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing).

Model discovery uses fixed provider HTTPS origins with certificate verification, no redirects and bounded pagination/response sizes: [OpenAI](https://developers.openai.com/api/reference/resources/models/methods/list), [Gemini](https://aistudio.google.com/api-reference/models/list-models), [Claude](https://platform.claude.com/docs/en/api/models/list), [DeepSeek](https://api-docs.deepseek.com/api/list-models/).
