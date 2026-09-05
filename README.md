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

## Running it locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill in the key
streamlit run streamlit_app.py
```

## What is in here

| File | What it does |
| --- | --- |
| `streamlit_app.py` | the web interface |
| `scanner.py` | keyword matching, reading the List, email, CSV |
| `requirements.txt` | Python packages |
| `.streamlit/config.toml` | theme and server settings |
| `.streamlit/secrets.toml.example` | the settings to fill in, as a template |

No keys live in the code. They are read from the host's secrets at run time.
