# X Keyword Search

Watches one X List and shows every post that mentions your keywords. It runs in the browser. There is nothing to install and nothing to sign in to.

## Using it

Open the link. The List and keywords are already filled in, and the latest matches are on screen when the page finishes loading.

- **Check now** reads the List again right away.
- **Keep checking every 15 minutes** re-checks on its own while the tab is open.
- **Each check looks back** sets how far back a check reads, from 6 hours to 2 weeks.
- **Open on X** in the last column opens that post.
- **Download spreadsheet** saves everything found so far as a file Excel opens.

To watch something else, paste a different List address in the sidebar and edit the keywords. Keywords go one per line. A line can be a name or a phrase such as `voted against`. Matching is whole-word and ignores capitals, so `ICE` does not match `service`.

## Email

Type an address in the sidebar and click **Send me a summary now** to get the last week of matches. Tick **Also email after each check that finds something new** to get one after every check that turns something up, for as long as the tab stays open.

## If something looks wrong

The message above the table says what happened.

- **No posts came back** — check the List address. The List has to be public.
- **Asked us to slow down** — wait a few minutes and click Check now.
- **API key or credit** — the account behind the app needs attention.

## What is in here

| File | What it does |
| --- | --- |
| `streamlit_app.py` | the web interface |
| `scanner.py` | keyword matching, reading the List, email, CSV |
| `requirements.txt` | Python packages the host installs |
| `secrets.example.toml` | the settings to fill in, as a template |

No keys live in the code. They are read from the host's secrets at run time.

## Settings

These are set in the host's secrets panel, never in the repo.

| Setting | What it does |
| --- | --- |
| `TWITTERAPI_IO_KEY` | required, reads X through twitterapi.io |
| `DEFAULT_LIST_URL` | the List the app opens onto |
| `DEFAULT_KEYWORDS` | the keywords it opens with, separated by `\n` |
| `SENDER_EMAIL` | the account summaries are sent from |
| `SENDER_APP_PASSWORD` | a Gmail app password for that account |
