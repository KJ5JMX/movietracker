# Password reset - setup steps

The code is built and tested. These are the things only you can do (account
setup + deploy). Until the Resend key is set, the forgot-password endpoint
still works but no email goes out, so don't skip step 1 before shipping.

## 1. Resend account + domain (~10 min, one time)

1. Sign up at resend.com (free tier: 3,000 emails/month, plenty for resets).
2. Add and verify the domain `thenobodyprojects.com`: Resend gives you a few
   DNS records (SPF/DKIM, a `resend._domainkey` TXT, etc.). Add them in
   Cloudflare DNS for the domain, then click Verify in Resend. Verification is
   what stops your reset emails from landing in spam.
3. Create an API key (Resend dashboard -> API Keys). Copy it once.

## 2. Backend env vars

Add to `server/.env` on the Ubuntu box (and anywhere else the backend runs):

```
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxx
RESET_FROM_EMAIL=ShelfMates <noreply@thenobodyprojects.com>
APP_PUBLIC_URL=https://cuedup-api.thenobodyprojects.com
# optional, defaults to 60:
RESET_TOKEN_TTL_MINUTES=60
```

`RESET_FROM_EMAIL` must be on the domain you verified in step 1.
`APP_PUBLIC_URL` is the base the reset link points at; it must be the public
HTTPS backend, not localhost.

## 3. Deploy the backend

The Docker `entrypoint.sh` runs `flask db upgrade` on start, so the new
`password_reset_tokens` table is created automatically. Just pull and restart:

```
cd ~/movie_tracker && git pull
./deploy/deploy.sh        # or: docker compose up --build --wait
```

Verify after restart:

```
curl -s -X POST https://cuedup-api.thenobodyprojects.com/auth/forgot-password \
  -H 'Content-Type: application/json' -d '{"identifier":"you@example.com"}'
# -> {"message":"If an account matches that, we've sent a reset link. ..."}
```

Use a real account email and confirm the email arrives, then open the link and
reset.

## 4. Ship the app update

The mobile app changed (signup now collects email, Login has "Forgot
password?", new Forgot Password screen). Rebuild and upload to TestFlight /
App Store as usual. JS-only change, no pod install needed.

## How it works (for future you)

- Signup now requires a unique, valid email. Enforced in code, not a DB
  constraint, so existing rows with NULL/duplicate emails are untouched.
- "Forgot password?" -> POST /auth/forgot-password with an email OR username.
  The response is identical whether or not the account exists (no account
  enumeration). Rate-limited per IP and per identifier.
- A single-use token (stored only as a SHA-256 hash) is emailed as a link to
  /auth/reset?token=... The page is server-rendered by Flask in the app
  palette; no in-app deep link / Universal Links needed.
- Token expires after RESET_TOKEN_TTL_MINUTES and is burned on use. Issuing a
  new link invalidates any earlier one for that user.

## Two things to know

- Existing testers signed up without an email, so they have no reset path until
  they add one in Profile -> Settings (email field is already there and
  validated). New signups are covered automatically. Worth a heads-up to your
  current testers.
- You now collect email at signup. That makes a real Privacy Policy more
  pressing for App Store review than it was - the placeholder legal pages are
  still on the pre-submission checklist.
