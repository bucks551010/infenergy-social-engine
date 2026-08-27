# Social Platform Publishing Setup

## Code Completed

The shared platform registry treats Facebook, Instagram, LinkedIn, YouTube, and TikTok as platform capabilities rather than isolated endpoint branches. It reports enabled state, required configuration, supported formats, scheduling support, and processing-status support without returning secret values.

Image Studio can select YouTube and TikTok, generate platform-specific copy, preserve per-platform outcomes, schedule them through the existing scheduler, and requires a rendered Scored Story Reel before either video platform can be selected. The automatic editorial calendar retains its existing default platform set.

YouTube uses OAuth refresh credentials and the YouTube Data API v3. Uploads use `videos.insert` with a resumable upload session. New installations default to `unlisted`; title, description, tags, category, privacy, and made-for-kids declarations are mapped from the content/configuration contract. Processing status is available through `videos.list`.

TikTok uses the Content Posting API direct-post initialization contract with `PULL_FROM_URL`, returns `PROCESSING`, and exposes a status lookup. The feature defaults to disabled and `SELF_ONLY`. Native TikTok photo carousel publishing is not enabled because the current official account/app eligibility and API contract could not be verified from this environment.

Command Intelligence OS includes a single-owner TikTok Login Kit Web connection flow. OAuth state is one-time and expires after ten minutes. Access and refresh tokens are encrypted at rest on the Railway volume, never returned to the browser, refreshed shortly before access-token expiry, and atomically replaced when TikTok rotates the refresh token. The existing `TIKTOK_REFRESH_TOKEN` variable remains a fallback for pre-OAuth deployments only.

Both video adapters fail before upload when their feature flag is disabled, credentials are incomplete, or the media is not a public HTTPS MP4. Provider failures are normalized into authentication, rate-limit, network, media, policy, processing, content-validation, or unknown categories with retryability metadata.

Command Intelligence OS exposes `platforms.status`, a machine-readable capability that reports connection health and action-required states without exposing credentials.

## Action Required From Owner

### YouTube

1. Create or select a Google Cloud project and enable YouTube Data API v3.
2. Configure the OAuth consent screen and an OAuth web application owned by Infenergy.
3. Request only the upload scope required by the publisher: `https://www.googleapis.com/auth/youtube.upload`.
4. Add the configured redirect URI to the Google OAuth client.
5. Authorize the intended YouTube channel and obtain a durable refresh token through a trusted OAuth flow.
6. Put the client ID, client secret, and refresh token in Railway secrets. Never paste them into source control or application logs.
7. Keep `YOUTUBE_PRIVACY_STATUS=unlisted` during acceptance testing.
8. Set `YOUTUBE_PUBLISHING_ENABLED=true` only after a private or unlisted test upload completes and processing status reaches success.
9. Review YouTube quota, branding, made-for-kids, and API Services Terms obligations before public automation.

The code refreshes and uses an existing authorization grant. A user-facing OAuth connect/callback UI and encrypted multi-account token vault are not represented as complete; the current deployment is a single-owner Railway secret model.

### TikTok

1. Create a TikTok for Developers application owned by Infenergy.
2. Add Login Kit for Web and Content Posting API products, then request `user.info.basic`, `video.upload`, and `video.publish`.
3. In the TikTok developer portal, register this exact Web redirect URI: `https://jubilant-harmony-production-5bd1.up.railway.app/api/auth/tiktok/callback`.
4. Complete TikTok app review/audit and comply with any private-only restrictions applied to unaudited clients.
5. Verify the public media domain TikTok will pull from, then place the client key and client secret in Railway sealed variables.
6. Set `TIKTOK_REDIRECT_URI` to the exact URI above and set `TIKTOK_TOKEN_ENCRYPTION_KEY` to a stable high-entropy secret. Changing that encryption key invalidates stored credentials.
7. Open Command Intelligence OS → Social and choose **Connect TikTok**. Confirm the connected creator identity shown after the callback. Do not manually copy tokens into the browser or logs.
8. Confirm the account's creator information, privacy choices, duration limits, music/content disclosure rules, and commercial-content requirements against the current official API before enabling public posts.
9. Keep `TIKTOK_PRIVACY_LEVEL=SELF_ONLY` and `TIKTOK_PUBLISHING_ENABLED=false` until app approval. Set `TIKTOK_PUBLISH_MODE=draft` to test upload-to-inbox separately from Direct Post.
10. Set `TIKTOK_PUBLISHING_ENABLED=true` only after authorization, app approval, and a private test whose status polling reaches success.

TikTok's developer portal remains authoritative for app-specific review status and allowed redirect URIs. Native photo carousel and analytics ingestion remain disabled until those contracts, scopes, app review, and account eligibility are verified.

## Railway Variables

Use `.env.example` as the variable-name inventory. In Railway, secret values must be entered as sealed variables; `REPLACE_ME` is intentionally treated as missing configuration. Both new platform feature flags must remain `false` while placeholders are present.

Image Studio requires its existing `SOCIAL_ENGINE_URL` and `SOCIAL_ENGINE_TOKEN` connection to the Social Engine. It does not receive or store social-provider secrets.

## Operational Checks

1. Call the protected Command OS capability `platforms.status` and verify the platform reports `CONNECTED`.
2. Render and technically QA a 1080x1920 H.264/AAC Scored Story Reel.
3. Publish one private/unlisted test per platform.
4. Persist the returned platform identifier immediately.
5. Poll processing status until success or terminal failure.
6. Confirm the external post from the owner account, not only the scheduler's run status.
7. Enable public privacy and scheduled automation only after the complete check passes.

## Current Limits

The existing scheduler owns delivery timing, idempotent platform outcomes, and retries. YouTube and TikTok processing can outlive the initial request; their initial outcome is therefore not proof of publication. A recurring reconciliation worker and normalized YouTube/TikTok analytics ingestion are still required before platform processing and performance feedback can be called fully autonomous.
