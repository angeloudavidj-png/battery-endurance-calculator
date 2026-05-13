# Deploying to Streamlit Community Cloud

This guide walks you through hosting the calculator as a live, public web app
at a URL you can drop on a résumé or LinkedIn. **Total time: ~30 minutes**,
**cost: $0**, no credit card needed.

Streamlit Community Cloud is free for public GitHub repos. Limits:
1 GB RAM, 1 CPU, app sleeps after 7 days of inactivity (wakes on first visit).
Plenty for a portfolio demo.

---

## Prerequisites

You need:

- A **GitHub account** (free at github.com)
- **Git** installed locally (`git --version` to check; install from
  [git-scm.com](https://git-scm.com) if missing)
- The project files on your local machine

If you've never used Git before: it's like Google Docs version history but
for code. The "push" step uploads your files to GitHub.

---

## Step 1 — Push the project to GitHub  (~10 min)

### 1a. Create a new GitHub repo

1. Go to [github.com/new](https://github.com/new)
2. Repository name: `battery-endurance-calculator` (or anything you like)
3. Description: *Multirotor & eVTOL battery endurance calculator —
   rotor momentum theory in Python, validated against 4 real aircraft*
4. **Public** (required for free Streamlit hosting)
5. **Do NOT** initialize with a README, .gitignore, or license (you already
   have them locally)
6. Click **Create repository**

GitHub will show a page with instructions. Note the URL —
it'll look like `https://github.com/YOUR_USERNAME/battery-endurance-calculator.git`

### 1b. Push from your local machine

Open a terminal in the project root (where `app.py` and `README.md` are):

```bash
# Initialize git in this folder
git init
git branch -M main

# Stage all files
git add .

# First commit
git commit -m "Initial commit: v2 with profile drag + Joby S4"

# Point at your GitHub repo (REPLACE the URL with yours)
git remote add origin https://github.com/YOUR_USERNAME/battery-endurance-calculator.git

# Upload
git push -u origin main
```

If GitHub asks for credentials, it will prompt for a **personal access token**,
not your password. Create one at
[github.com/settings/tokens](https://github.com/settings/tokens) →
*Generate new token (classic)* → check the `repo` scope → copy the token →
paste it as the password.

### 1c. Verify it worked

Refresh the GitHub repo page. You should see all the project files listed.
The README will render automatically with the embedded charts.

---

## Step 2 — Deploy on Streamlit Cloud  (~15 min)

### 2a. Sign in

1. Go to [streamlit.io/cloud](https://streamlit.io/cloud) (or
   [share.streamlit.io](https://share.streamlit.io))
2. Click **Continue with GitHub** and authorize Streamlit. This lets
   Streamlit read your public repos.

### 2b. New app

1. Click **Create app** (or "New app" in the top right).
2. Select **Deploy a public app from GitHub**.
3. Fill in:
   - **Repository**: `YOUR_USERNAME/battery-endurance-calculator`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL**: customize the subdomain — e.g.
     `david-angelou-bec` → final URL becomes
     `https://david-angelou-bec.streamlit.app`
4. Click **Deploy**.

Streamlit will spend ~2–3 min installing the dependencies in
`requirements.txt`, then load the app. You'll see a build log scroll past
on the right. First-deploy takes the longest — subsequent updates push
in ~30 seconds.

### 2c. If the build fails

Most failures are a missing dependency. Check the build log for `ModuleNotFoundError`,
then add the missing package to `requirements.txt`, commit, and push:

```bash
echo "missing-package>=1.0" >> requirements.txt
git add requirements.txt
git commit -m "Add missing dependency"
git push
```

Streamlit auto-rebuilds on every push.

---

## Step 3 — Polish for recruiters  (~5 min)

### 3a. Add the live URL to the GitHub repo

1. On the repo's main page, click the gear icon next to **About**
   (top right of the file list).
2. Paste the Streamlit URL into the **Website** field.
3. Add tags: `python`, `streamlit`, `aerospace`, `engineering`,
   `multirotor`, `evtol`, `simulation`.
4. Save.

Now the GitHub repo page shows the live link prominently.

### 3b. Add a "Live demo" badge to the README

At the very top of `README.md`, just under the title, add:

```markdown
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://YOUR-SUBDOMAIN.streamlit.app)
```

Commit and push:
```bash
git add README.md
git commit -m "Add live demo badge"
git push
```

### 3c. (Optional) Pin the repo on your GitHub profile

1. Go to `github.com/YOUR_USERNAME`
2. Click **Customize your pins**
3. Check `battery-endurance-calculator`
4. Save

It'll now show up on your profile homepage.

---

## Step 4 — Tell people about it

For LinkedIn:

> Just shipped v2 of my battery endurance calculator — a Python tool that
> predicts hover endurance and forward-flight range for multirotor and
> eVTOL aircraft using rotor momentum theory.
>
> v2's headline: I added a profile-drag term to the forward-flight model,
> collapsing prediction error on the DJI Mavic 3 from ±20 % to ±5 %.
> Hover predictions match published specs to 0.19 % across a **2400× mass
> range** — from a 0.9 kg consumer drone to the 2,177 kg Joby S4 eVTOL.
>
> Built end-to-end in Python: physics module, parametric aircraft database
> with sourced specs, interactive Streamlit UI, automated test suite,
> publication-quality matplotlib charts.
>
> Live demo: `https://YOUR-SUBDOMAIN.streamlit.app`
> Code: `https://github.com/YOUR_USERNAME/battery-endurance-calculator`
>
> #aerospace #python #engineering

Attach the `docs/validation_chart.png` or `docs/forward_flight_v1_v2.png`
as the post image. The latter is the strongest if you want to lead with
the v2 story; the former if you want to lead with the 2400× mass range.

---

## Maintenance

Streamlit Cloud auto-rebuilds on every push to `main`. So your workflow is:

1. Edit code locally
2. `python test_endurance.py` to confirm tests still pass
3. `git add -A && git commit -m "Why this change" && git push`
4. Streamlit rebuilds in ~30 seconds
5. Live URL is updated

If the app **sleeps** after a week of no traffic, the first visit takes
~20 seconds to wake. After that, subsequent loads are instant. Recruiter
visits will wake it; you don't need to babysit it.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` in build log | Missing dep in `requirements.txt` | Add it, push |
| App loads but charts don't render | `make_plots.py` hasn't been run | Run `python make_plots.py` locally, commit the new PNGs, push |
| "Repository not found" on Streamlit | Repo is private | Make it public, or upgrade to paid Streamlit |
| Permission denied on `git push` | Personal access token expired | Regenerate at github.com/settings/tokens |
| App is "snoozing" | 7-day inactivity timeout | First visit wakes it (~20 s) |

If something else goes wrong, the Streamlit build log is the first place to
look. It's verbose and almost always tells you the exact line that failed.
