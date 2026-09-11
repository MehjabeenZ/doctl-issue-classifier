# Deploying this app

Not yet deployed. This is the prep work + instructions so deploying is a fast,
already-decided step rather than something to figure out live. Nothing in this
file has been executed — no cloud resources exist yet, no account credentials
were used to write it.

**No GitHub repo is required for this.** The zip deliverable (source code) and
the live "running application" link are two independent requirements — the
live copy just needs to be *a* running instance of this code reachable by
URL, not something deployed from a connected Git repo specifically. The path
below deploys straight from a prebuilt Docker image instead, so nothing about
this take-home needs to go on GitHub at all.

## Recommended: Render, deployed from a prebuilt image (no GitHub)

Render supports what it calls an "image-backed service" — deploy directly
from a Docker image pushed to a registry, with no Git connection at all
(confirmed against Render's own docs, 2026-09-10). Docker Hub is the simplest
registry for this: free account, and a **private** repo there keeps the image
itself un-public (unlike a GitHub-connected deploy, which still means
authorizing Render's GitHub App against your repo even if the repo is
private).

**Real tradeoff to know**: Render's free web-service tier spins the instance
down after a period of inactivity, so the *first* request after idle has a
cold-start delay (roughly 30–60s). Worth opening the link yourself a minute
before the review session, or mentioning it if a reviewer hits it cold.

**Port note**: the Dockerfile `EXPOSE`s 8080 and uvicorn binds to it directly.
Render says it's "usually able to detect" a non-default bound port — should
just work, but if the deploy builds and traffic doesn't route, set the port
to `8080` explicitly under the service's **Settings -> Port** in the
dashboard.

### Steps

1. **Create a free Docker Hub account** if you don't have one already
   (hub.docker.com) — no payment method required for public or a single
   private repo on the free tier.

2. **Build and tag the image** (from the repo root):
   ```bash
   docker build -t <your-dockerhub-username>/doctl-issue-classifier:latest .
   ```

3. **Push it**:
   ```bash
   docker login   # once, interactively
   docker push <your-dockerhub-username>/doctl-issue-classifier:latest
   ```
   If you want the repo private on Docker Hub (recommended if the take-home
   content shouldn't be public), create the repo as **Private** first in the
   Docker Hub UI before pushing — pushing to a name that doesn't exist yet
   auto-creates it as **public** by default.

4. **In the Render dashboard**: **+ New -> Web Service** -> under "Source
   Code," choose **Existing Image** instead of connecting a Git provider.
   Paste the image URL (`docker.io/<your-dockerhub-username>/doctl-issue-classifier:latest`).
   If the repo is private, Render will prompt for Docker Hub credentials
   (username + a Docker Hub **access token**, not your account password —
   generate one under Docker Hub's Account Settings -> Security).

5. **Set environment variables** (Render's Environment tab for the service):
   - `SI_API_KEY` — your real key, marked as a **secret** value in the UI.
   - `DRY_RUN=false`
   - Everything else (`SI_BASE_URL`, `DEFAULT_CONCURRENCY`, `MAX_OUTPUT_TOKENS`)
     already defaults sensibly per `backend/app/config.py`; only set these if
     you want something different.

6. **Plan**: choose **Free**.

7. **Deploy**. Render gives you a live `https://<service-name>.onrender.com`
   URL once it pulls the image and starts the container — that's what goes
   in the README.

To redeploy after a code change: rebuild, re-tag, `docker push` again, then
trigger a manual redeploy in the Render dashboard (or set up a registry
webhook — not necessary for a one-off take-home).

## Alternative: still avoids GitHub — Fly.io CLI

`flyctl` builds and deploys directly from the local Dockerfile via its own
CLI (`fly launch`, `fly deploy`) — no Git hosting involved at all, arguably
even more direct than the Docker Hub route above. **Caveat**: Fly requires a
payment method on file even to use its free usage allowance, as a backstop
against exceeding it — worth knowing if you'd rather not attach a card
anywhere for a take-home exercise. Only worth it if the Docker Hub + Render
path above has some blocker.

## If you'd rather use GitHub anyway

`render.yaml` (Blueprint spec) is already written at the repo root for this —
Render auto-detects it once a repo is connected. This just isn't the default
recommendation anymore, since it adds a GitHub step that isn't actually
required. See git history / ask if you want the GitHub-connected steps
written back out in detail.

## What was ruled out: DigitalOcean App Platform

Kept only as a note in case circumstances change (e.g. the admin confirms the
$5/mo would draw from the exercise's SI credit, or confirms it's fine to pay
directly — the credit's wording in the exercise PDF scopes it to "Serverless
Inference" specifically, not other DO products, so this wasn't assumed
either way). If App Platform becomes the plan again: single Dockerfile
service, port 8080, `SI_API_KEY` as a "Secret"-type env var, cheapest
instance size as of 2026-09-10 was `apps-s-1vcpu-1gb` ($5/mo, no free tier
for a running service) — re-verify current pricing/slug at deploy time.

## What's NOT done here

- No cloud resources created, nothing deployed, no image pushed anywhere yet
  — this is prep only, per the constraint not to spend money or touch real
  infrastructure without explicit go-ahead.
- The real `SI_API_KEY` value is not and should never be written into any
  committed file — set it live via Render's environment editor.
