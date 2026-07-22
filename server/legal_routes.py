"""Privacy Policy and Terms of Use, served as HTML straight from the backend.

Why these live here instead of a separate website: the app already reaches this
host over HTTPS through the Cloudflare Tunnel, so two routes give Apple (and a
future Google Play listing) the public URLs they require with no extra hosting.

Use the public URLs in App Store Connect / Play Console and in the app's
Settings screen:
    https://cuedup-api.thenobodyprojects.com/privacy
    https://cuedup-api.thenobodyprojects.com/terms

NOTE: This is a plain-language template, not legal advice. Review it (a lawyer
is worth it once you take real money) and set the three values below before you
submit: CONTACT_EMAIL, GOVERNING_LAW, and EFFECTIVE_DATE if you change the text.
"""

from html import escape

from flask import Blueprint, Response

legal_bp = Blueprint("legal", __name__)

# ---- Set these for your listing ---------------------------------------------
APP_NAME = "Bardo"
DEVELOPER = "The Nobody Projects"
CONTACT_EMAIL = "theshelfmateapp@gmail.com"
GOVERNING_LAW = "the State of Texas, USA"  # TODO: set to your actual state/country
EFFECTIVE_DATE = "June 19, 2026"
# -----------------------------------------------------------------------------


def _page(title, body_html):
    """One server-rendered page in the Bardo palette, mobile-friendly."""
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - {escape(APP_NAME)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif;
          background: #F4EFE6; color: #2D2520; margin: 0; padding: 24px 16px;
          line-height: 1.6; }}
  .card {{ max-width: 680px; margin: 24px auto 64px; background: #FFFCF7;
           border: 2px solid #2D2520; border-radius: 12px; padding: 28px 24px;
           box-shadow: 4px 4px 0 #2D2520; }}
  h1 {{ color: #2D5F4F; font-size: 26px; margin: 0 0 4px; }}
  h2 {{ color: #2D5F4F; font-size: 19px; margin: 28px 0 6px; }}
  h3 {{ font-size: 16px; margin: 18px 0 4px; }}
  a {{ color: #2D5F4F; }}
  ul {{ padding-left: 20px; }}
  li {{ margin: 4px 0; }}
  .muted {{ color: #7B5E47; font-size: 14px; }}
  .effective {{ color: #7B5E47; font-size: 14px; margin-bottom: 18px; }}
  .pill {{ display: inline-block; background: #2D5F4F; color: #FFFCF7;
           font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px;
           letter-spacing: .04em; }}
  hr {{ border: none; border-top: 2px solid #E4DBCB; margin: 28px 0; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #1F1813; color: #F0E6D5; }}
    .card {{ background: #2D2620; border-color: #F0E6D5; box-shadow: 4px 4px 0 #000; }}
    h1, h2 {{ color: #6A9B7F; }}
    a {{ color: #6A9B7F; }}
    .muted, .effective {{ color: #C9B79C; }}
    hr {{ border-top-color: #44392F; }}
  }}
</style>
</head>
<body><div class="card">{body_html}</div></body>
</html>"""
    return Response(html, status=200, mimetype="text/html")


_PRIVACY_BODY = f"""
  <span class="pill">PRIVACY POLICY</span>
  <h1>{escape(APP_NAME)} Privacy Policy</h1>
  <p class="effective">Effective {escape(EFFECTIVE_DATE)}</p>

  <p>{escape(APP_NAME)} ("we", "us", the "app") is a personal watch / read list
  with a private friends layer, made by {escape(DEVELOPER)}. This policy explains
  what we collect, why, and the choices you have. We kept it short because we
  collect little and sell nothing.</p>

  <h2>The short version</h2>
  <ul>
    <li>We collect what you give us to run your account and lists, plus what is
        needed to deliver push notifications and process a subscription.</li>
    <li>We do <strong>not</strong> show ads, run third-party advertising or
        analytics trackers, or sell or rent your personal information.</li>
    <li>Your lists and activity are shared only with friends you choose to
        connect with, and only as far as your privacy setting allows.</li>
    <li>You can delete your account, and all of your data, from inside the app
        at any time.</li>
  </ul>

  <h2>Information we collect</h2>
  <h3>Account information</h3>
  <p>A username, your password (stored only as a salted hash, never in plain
  text), and optionally a display name and email address. An email lets you
  reset your password and receive notifications you have turned on. Each account
  gets a friend code so others can add you.</p>

  <h3>If you use Sign in with Apple or Google</h3>
  <p>We receive a stable, app-specific identifier for you from Apple or Google,
  and an email address if you allow it (Apple may give you a private relay
  address; that is fine). We use it only to create and sign you into your
  account. We never receive your Apple or Google password.</p>

  <h3>Content you create</h3>
  <p>The titles you add to your lists (movies, TV, songs, books) and details
  about them, your watch / read status and reading progress, your star ratings,
  your written notes and reviews, recommendations you send or receive, your
  friend connections, your Movie Night picks, and comments you post in
  spoiler-gated book discussions.</p>

  <h3>Preferences and usage signals</h3>
  <p>Settings such as theme, notification and privacy preferences and genre
  interests, and lightweight in-app signals like which streaming services you
  tap most, used only to order things helpfully for you. We do not build an
  advertising profile.</p>

  <h3>Push notifications</h3>
  <p>If you enable notifications, we store the push token your device provides
  so we can deliver alerts (a friend request, a recommendation, a release
  reminder). Turn notifications off in iOS Settings at any time.</p>

  <h3>Subscriptions</h3>
  <p>If you buy a {escape(APP_NAME)} Pro subscription, the purchase is handled by
  Apple. Apple processes your payment; we never see your card details. We store
  the subscription's status and expiry and an Apple transaction identifier so we
  can unlock Pro for your account and prevent one purchase unlocking many
  accounts.</p>

  <h2>How we use information</h2>
  <ul>
    <li>To run your account and sync your lists across sign-ins.</li>
    <li>To power the social features you opt into: friends, recommendations,
        shared reviews and book discussions.</li>
    <li>To send notifications you have enabled.</li>
    <li>To provide and verify {escape(APP_NAME)} Pro.</li>
    <li>To keep the service secure and debug problems.</li>
  </ul>

  <h2>Who your information is shared with</h2>
  <h3>Other people, by your choice</h3>
  <p>When you add a friend, that friend can see what your privacy setting allows
  (for example, items you mark to share, recommendations you send them, and
  reviews you choose to share). Your "Privacy" setting (Just me / Friends /
  Public) controls this, and you can change it any time.</p>

  <h3>Service providers we rely on</h3>
  <p>We use a small set of third parties to make the app work. They receive only
  what they need:</p>
  <ul>
    <li><strong>Apple</strong> - sign-in, in-app purchases, and push delivery
        (APNs).</li>
    <li><strong>Google</strong> - sign-in, if you choose it.</li>
    <li><strong>OMDb, the iTunes Search API, and Open Library</strong> - we send
        the title you are searching for to look up movie, TV, music and book
        details. We do not send your identity.</li>
    <li><strong>Watchmode</strong> - looks up where a title streams (this feature
        may be turned off in the current version). We send only the title's
        identifier.</li>
    <li><strong>Resend</strong> - delivers account emails such as password
        resets.</li>
  </ul>
  <p>These providers have their own privacy policies. We may also disclose
  information if the law requires it, or to protect the rights and safety of our
  users or the service.</p>

  <h2>What we do not do</h2>
  <p>We do not sell or rent your personal information. We do not show third-party
  ads. We do not embed third-party advertising or analytics SDKs, and there is no
  algorithmic tracking feed. Everything social is friend-driven and labeled with
  who it came from.</p>

  <h2>Data retention and deletion</h2>
  <p>We keep your information while your account is active. You can delete your
  account from <em>Profile &rarr; Settings &rarr; Delete account</em> inside the
  app. Deleting your account removes your profile and your associated content
  (lists, ratings, notes, recommendations and the like) from our database. Some
  records may remain briefly in encrypted backups before they age out, and we may
  retain the minimum needed to meet legal or financial obligations (for example,
  a record that a subscription existed).</p>

  <h2>Security</h2>
  <p>Passwords are stored only as salted hashes. The app talks to our server over
  HTTPS, and sessions use signed tokens. No system is perfectly secure, but we
  take reasonable steps to protect your information.</p>

  <h2>Children</h2>
  <p>{escape(APP_NAME)} is not directed to children under 13, and we do not
  knowingly collect personal information from them. If you believe a child has
  given us information, contact us and we will delete it.</p>

  <h2>Your rights</h2>
  <p>Depending on where you live, you may have the right to access, correct,
  export or delete your personal information. You can do most of this in the app
  (edit your profile, delete your account). For anything else, email us.</p>

  <h2>Changes to this policy</h2>
  <p>If we make material changes, we will update this page and the effective date
  above. Continued use after a change means you accept the updated policy.</p>

  <h2>Contact</h2>
  <p>Questions about privacy? Email
  <a href="mailto:{escape(CONTACT_EMAIL)}">{escape(CONTACT_EMAIL)}</a>.</p>

  <hr>
  <p class="muted">{escape(APP_NAME)} is a product of {escape(DEVELOPER)}.
  See also our <a href="/terms">Terms of Use</a>.</p>
"""


_TERMS_BODY = f"""
  <span class="pill">TERMS OF USE</span>
  <h1>{escape(APP_NAME)} Terms of Use</h1>
  <p class="effective">Effective {escape(EFFECTIVE_DATE)}</p>

  <p>These Terms of Use ("Terms") are an agreement between you and
  {escape(DEVELOPER)} ("we", "us") governing your use of the {escape(APP_NAME)}
  app and service. By creating an account or using the app, you agree to these
  Terms. If you do not agree, do not use the app.</p>

  <h2>1. Who can use {escape(APP_NAME)}</h2>
  <p>You must be at least 13 years old (or the minimum age of digital consent
  where you live, if higher) to use the app. If you are under 18, you confirm a
  parent or guardian agrees to these Terms on your behalf.</p>

  <h2>2. Your account</h2>
  <p>You are responsible for your account and for keeping your credentials
  secure. Keep your information accurate. Tell us promptly if you suspect
  unauthorized use. You are responsible for activity that happens under your
  account.</p>

  <h2>3. Acceptable use</h2>
  <p>Use {escape(APP_NAME)} only for lawful, personal, non-commercial purposes.
  Do not:</p>
  <ul>
    <li>Break the law, infringe others' rights, or violate these Terms.</li>
    <li>Post content that is unlawful, harassing, hateful, or infringing.</li>
    <li>Attempt to access other users' accounts or data without permission.</li>
    <li>Probe, scrape, overload, reverse-engineer, or disrupt the service.</li>
    <li>Misuse the social features to spam or harass other people.</li>
  </ul>
  <p>We may suspend or terminate accounts that violate these Terms.</p>

  <h2>4. Your content</h2>
  <p>You keep ownership of the notes, reviews, comments and lists you create.
  You grant us a limited license to store, display and share that content as
  needed to operate the app, including showing it to the friends you choose
  under your privacy setting. You are responsible for the content you post and
  for having the right to post it.</p>

  <h2>5. Third-party content and data</h2>
  <p>Movie, TV, music and book details and streaming availability come from
  third-party sources (including OMDb, the iTunes Search API, Open Library and
  Watchmode). We do not control and are not responsible for the accuracy,
  availability or licensing of that information. {escape(APP_NAME)} does not host
  or stream any media; "where to watch" links point to third-party services.</p>

  <h2>6. {escape(APP_NAME)} Pro subscriptions</h2>
  <p>Some features require a paid subscription ("{escape(APP_NAME)} Pro"), sold
  as an auto-renewable in-app purchase through Apple. By subscribing you agree
  that:</p>
  <ul>
    <li>Payment is charged to your Apple ID at confirmation of purchase.</li>
    <li>The subscription renews automatically for the same period and price
        unless you turn off auto-renew at least 24 hours before the current
        period ends.</li>
    <li>Your Apple ID is charged for renewal within 24 hours before the period
        ends.</li>
    <li>You manage and cancel your subscription in your Apple ID account
        settings; deleting the app does not cancel it.</li>
    <li>Prices may change; we will give notice as required, and any increase
        applies only after it takes effect.</li>
  </ul>
  <p>Payments and refunds are handled by Apple under Apple's terms. We do not
  process payments or issue refunds directly. Free features may change or end at
  our discretion.</p>

  <h2>7. The app is provided "as is"</h2>
  <p>{escape(APP_NAME)} is provided on an "as is" and "as available" basis,
  without warranties of any kind, whether express or implied, to the maximum
  extent permitted by law. We do not warrant that the app will be uninterrupted,
  error-free, or that third-party data will be accurate.</p>

  <h2>8. Limitation of liability</h2>
  <p>To the maximum extent permitted by law, {escape(DEVELOPER)} will not be
  liable for any indirect, incidental, special, consequential or punitive
  damages, or for lost data or profits, arising from your use of the app. Our
  total liability for any claim relating to the app will not exceed the greater
  of the amount you paid us in the twelve months before the claim, or 25 US
  dollars.</p>

  <h2>9. Termination</h2>
  <p>You may stop using {escape(APP_NAME)} and delete your account at any time.
  We may suspend or end your access if you violate these Terms or to protect the
  service. Sections that by their nature should survive termination (such as
  content license, disclaimers and limitation of liability) will survive.</p>

  <h2>10. Apple-required terms</h2>
  <p>These Terms are between you and {escape(DEVELOPER)} only, not with Apple.
  Apple is not responsible for the app or its content. Apple has no obligation to
  provide maintenance or support for the app. If the app fails to conform to any
  applicable warranty, you may notify Apple and Apple will refund the purchase
  price (if any); to the maximum extent permitted by law, Apple has no other
  warranty obligation. {escape(DEVELOPER)}, not Apple, is responsible for
  addressing any claims relating to the app, including product liability, legal
  or regulatory compliance, and intellectual-property claims. Apple and its
  subsidiaries are third-party beneficiaries of these Terms and may enforce them
  against you. You confirm you are not located in a country subject to a US
  Government embargo and are not on any US Government restricted-parties list.</p>

  <h2>11. Changes to these Terms</h2>
  <p>We may update these Terms. If we make material changes we will update this
  page and the effective date. Continued use after a change means you accept the
  updated Terms.</p>

  <h2>12. Governing law</h2>
  <p>These Terms are governed by the laws of {escape(GOVERNING_LAW)}, without
  regard to its conflict-of-laws rules, except where local consumer-protection
  law gives you stronger rights.</p>

  <h2>13. Contact</h2>
  <p>Questions about these Terms? Email
  <a href="mailto:{escape(CONTACT_EMAIL)}">{escape(CONTACT_EMAIL)}</a>.</p>

  <hr>
  <p class="muted">{escape(APP_NAME)} is a product of {escape(DEVELOPER)}.
  See also our <a href="/privacy">Privacy Policy</a>.</p>
"""


@legal_bp.route("/privacy", methods=["GET"])
def privacy():
    return _page("Privacy Policy", _PRIVACY_BODY)


@legal_bp.route("/terms", methods=["GET"])
def terms():
    return _page("Terms of Use", _TERMS_BODY)
