"""Self-service "about" photo gallery, managed from /admin without touching
the repo or Render by hand.

Render's web service filesystem is ephemeral - anything written to disk at
runtime is gone on the next deploy/restart. So instead of saving uploads
locally, every add/delete goes straight through GitHub's Contents API to
this repo's live branch. That push is what Render already watches to
redeploy (same as any commit we make ourselves), so a change here reaches
the live site the same way everything else does - a commit, then a minute
or two for Render's build. The homepage itself just reads the folder off
the local checkout (fast, no GitHub API call on every page view); /admin
reads GitHub directly instead, so what it shows is never stale while a
deploy is in flight.

Requires a GITHUB_TOKEN env var on Render - a Personal Access Token
(fine-grained, scoped to just this repo, Contents: Read and write) created
by whoever owns the GitHub repo. Never fabricate or guess this value.
"""
import os
import time
import unicodedata

import requests

GALLERY_DIR = "static/images/gallery"
LOCAL_GALLERY_PATH = os.path.join(os.path.dirname(__file__), GALLERY_DIR)

# This repo + its live branch (see CLAUDE.md "Repo specifics worth
# remembering") - Render deploys from this exact branch, so a commit here
# is what makes an uploaded photo actually show up on the site.
GITHUB_REPO = os.environ.get("GITHUB_REPO", "eys2005-afk/VEAHAVTA")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "claude/veahavta-flask-skeleton-ohzlsq")

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def _sort_key(name):
    """Ordering for the gallery: the original seed photos (place-1.jpg..)
    always come first, in their own numeric order - the caption badge
    ("הבית שלנו...") is positioned over whatever lands in that first slide,
    so a new upload must never be sorted ahead of them (plain alphabetical
    sort did exactly that: "photo-..." < "place-..." since 'h' < 'l',
    bumping a brand-new photo into the caption's slot). Anything else
    (photo-<ms-epoch-timestamp>.ext uploads) sorts after, in upload order -
    the timestamp is a fixed-width decimal string, so alphabetical order
    there already matches chronological order."""
    if name.startswith("place-"):
        try:
            return (0, int(name.split("-", 1)[1].split(".", 1)[0]))
        except ValueError:
            return (0, 0)
    return (1, name)


MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8MB - generous for a phone photo, not a dumping ground

API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GALLERY_DIR}"


class GalleryError(Exception):
    """Raised for any problem a client-facing admin message should explain."""


def _token():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise GalleryError(
            "GITHUB_TOKEN לא מוגדר ב-Render - אי אפשר לשמור תמונות בלי זה."
        )
    return token


def _headers():
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _safe_filename(original_name, content):
    """A short, collision-proof, path-traversal-proof filename - keeps only
    the extension from what the visitor's browser sent, discards the rest
    (no directory components, no unicode tricks, no relying on a
    client-supplied name at all for the stem)."""
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    ext = unicodedata.normalize("NFKC", ext)
    if ext not in ALLOWED_EXTENSIONS:
        raise GalleryError(
            f"סוג קובץ לא נתמך ({ext or 'לא ידוע'}) - רק jpg/jpeg/png/webp."
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise GalleryError("הקובץ גדול מדי (מעל 8MB) - אפשר לכווץ ולנסות שוב.")
    if not content:
        raise GalleryError("הקובץ ריק.")
    return f"photo-{int(time.time() * 1000)}.{ext}"


def list_images():
    """Current gallery images straight from GitHub (never stale, even mid-
    deploy). Each item: {"name", "download_url"}. Raises GalleryError on
    any failure - callers show that message rather than a blank admin
    section."""
    resp = requests.get(
        API_BASE, headers=_headers(), params={"ref": GITHUB_BRANCH}, timeout=15
    )
    if resp.status_code == 404:
        return []
    if not resp.ok:
        raise GalleryError(f"GitHub החזיר שגיאה ({resp.status_code}) בעת קריאת הגלריה.")
    items = [
        {"name": item["name"], "download_url": item["download_url"]}
        for item in resp.json()
        if item["type"] == "file"
    ]
    return sorted(items, key=lambda i: _sort_key(i["name"]))


def add_image(original_name, content):
    """Upload one new photo. Returns the stored filename."""
    filename = _safe_filename(original_name, content)
    import base64

    resp = requests.put(
        f"{API_BASE}/{filename}",
        headers=_headers(),
        json={
            "message": f"Add gallery photo {filename} (via /admin)",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": GITHUB_BRANCH,
        },
        timeout=20,
    )
    if not resp.ok:
        raise GalleryError(f"ההעלאה נכשלה (GitHub החזיר {resp.status_code}).")
    return filename


def delete_image(filename):
    """Remove one photo by name. Refuses to empty the gallery completely -
    the carousel needs at least one image."""
    if "/" in filename or filename in ("", ".", ".."):
        raise GalleryError("שם קובץ לא תקין.")

    current = list_images()
    if len(current) <= 1:
        raise GalleryError("לא ניתן למחוק את התמונה האחרונה - חייבת להישאר לפחות אחת.")

    get_resp = requests.get(
        f"{API_BASE}/{filename}",
        headers=_headers(),
        params={"ref": GITHUB_BRANCH},
        timeout=15,
    )
    if not get_resp.ok:
        raise GalleryError("התמונה לא נמצאה.")
    sha = get_resp.json()["sha"]

    del_resp = requests.delete(
        f"{API_BASE}/{filename}",
        headers=_headers(),
        json={
            "message": f"Remove gallery photo {filename} (via /admin)",
            "sha": sha,
            "branch": GITHUB_BRANCH,
        },
        timeout=20,
    )
    if not del_resp.ok:
        raise GalleryError(f"המחיקה נכשלה (GitHub החזיר {del_resp.status_code}).")


def local_image_filenames():
    """What the currently-deployed container actually has on disk - this is
    what the public homepage renders, and may lag list_images() by however
    long the last deploy took."""
    try:
        names = [
            f for f in os.listdir(LOCAL_GALLERY_PATH)
            if f.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS
        ]
    except FileNotFoundError:
        return []
    return sorted(names, key=_sort_key)
