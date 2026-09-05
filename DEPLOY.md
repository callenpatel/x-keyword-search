# Deploying to Streamlit Community Cloud

Twenty minutes end to end. You need a GitHub account and a Streamlit Community Cloud account, both free. Ben needs neither.

## Before anything else: rotate the two credentials

The desktop version had a twitterapi.io key and a Gmail app password written into `x_keyword_search.py`. That file went out in the zip, so treat both as burned, and replace them before this goes anywhere near GitHub.

1. twitterapi.io — sign in, revoke `new1_bb07...e4a3`, generate a new key.
2. Gmail — go to https://myaccount.google.com/apppasswords, delete the app password ending `vqwv`, create a new one.

The new values go in Streamlit's secrets panel in step 4, never in the repo. Git history is permanent, so a key that gets committed once stays exposed even if you delete it in the next commit.

## 1. Make the repo

From the project folder:

```bash
cd x-keyword-search-web
git init
git add .
git commit -m "X Keyword Search as a hosted web app"
```

Check nothing secret is staged before you push:

```bash
git status --short
git grep -nE "new1_|[a-z]{4} [a-z]{4} [a-z]{4} [a-z]{4}" -- . ':!DEPLOY.md'
```

The second command should print nothing. Then create the repo on GitHub and push:

```bash
gh repo create x-keyword-search --public --source=. --remote=origin --push
```

No `gh`? Make an empty repo at https://github.com/new, then:

```bash
git remote add origin https://github.com/YOUR-USERNAME/x-keyword-search.git
git branch -M main
git push -u origin main
```

The free Streamlit tier deploys from public repos. The repo holds no keys, so public is fine.

## 2. Deploy

1. Go to https://share.streamlit.io and sign in with GitHub.
2. **Create app** → **Deploy a public app from GitHub**.
3. Repository `YOUR-USERNAME/x-keyword-search`, branch `main`, main file `streamlit_app.py`.
4. Click **Advanced settings** and set Python version to 3.11.
5. Under **Secrets** in that same dialog, paste this with your new values:

```toml
TWITTERAPI_IO_KEY = "your-new-key"
DEFAULT_LIST_URL = "https://x.com/i/lists/THE-LIST-YOU-WANT-HIM-TO-SEE"
DEFAULT_KEYWORDS = "first keyword\nsecond keyword\nvoted against"
SENDER_EMAIL = "twitterscanupdate@gmail.com"
SENDER_APP_PASSWORD = "your-new-app-password"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "465"
```

6. **Deploy**. First build takes two or three minutes.

`DEFAULT_LIST_URL` and `DEFAULT_KEYWORDS` are what make it land as a demo instead of an empty form. Point them at the List and the terms his team actually watches, so the first thing he sees is his own beat.

## 3. Set the URL

Under **Settings → General**, the subdomain is editable. Something like `x-keyword-search.streamlit.app` reads better in an email than the generated string.

## 4. Check it the way he will

Open the URL in a private window, signed out of everything. You should get the table filled in within a few seconds of load, with no prompt of any kind. Click a post link, download the spreadsheet, and send yourself an email summary.

## Updating it later

```bash
git add -A && git commit -m "what changed" && git push
```

Cloud redeploys on push. Secrets are edited in the dashboard under **Settings → Secrets**, and the app restarts on save.

## Two things to know about the free tier

**Apps sleep after about 12 hours with no visitors.** A sleeping app shows the visitor a wake button and takes 30 seconds or so to come back. That is a bad first impression on a cold email, and the fix is to keep it warm: hit the URL every few hours for the days around your send. Any uptime pinger set to a 6-hour interval does it, or a cron line on a machine that stays on:

```bash
0 */6 * * * curl -s -o /dev/null https://x-keyword-search.streamlit.app
```

**Anyone with the link can use it, and every check spends your API credit.** The app reads the List once per 15 minutes and shares that read across everyone looking, so a handful of visitors costs about what one costs. The exposure is the link spreading further than intended. For a cold pitch to one person that is a reasonable trade for zero friction. If you want it closed later, Streamlit's **Settings → Sharing** restricts viewing to email addresses you list, which does put a sign-in in front of it.

## If the build fails

Open **Manage app** at the bottom right for the log.

- `ModuleNotFoundError` — the package is missing from `requirements.txt`.
- `KeyError: 'TWITTERAPI_IO_KEY'` — the secrets panel is empty or was saved without the app restarting.
- The app loads but says the key was rejected — the key is wrong, or it was pasted with a stray space.
