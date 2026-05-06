#!/usr/bin/env python3
"""Mirror GitHub repos to a Forgejo org.

MIRROR_SOURCE=owned (default): repos owned by the authenticated user
(/user/repos). Destination repo name = github name.

MIRROR_SOURCE=starred: repos starred by the authenticated user
(/user/starred). Destination repo name = "<owner>__<repo>" so multiple
upstreams that share a repo name don't collide in one Forgejo org.

Reads config from env: GITHUB_USER, GITHUB_PAT, FORGEJO_URL, FORGEJO_ORG,
FORGEJO_TOKEN, MIRROR_SOURCE. Idempotent: creates missing mirrors,
force-syncs existing ones. One line of stdout per repo. Exits 0 even
if individual repos fail so a single bad mirror doesn't block the rest
of the nightly job.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def _http(url, method="GET", token_header=None, body=None, timeout=600):
    req = urllib.request.Request(url, method=method)
    if token_header:
        req.add_header("Authorization", token_header)
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def list_github_repos(user_token, source):
    if source == "starred":
        path = "/user/starred"
    else:
        path = "/user/repos?affiliation=owner&visibility=all"
    sep = "&" if "?" in path else "?"
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com{path}{sep}per_page=100&page={page}"
        status, body = _http(url, token_header=f"token {user_token}")
        if status != 200:
            print(f"!! GitHub list page {page} failed status={status}", flush=True)
            sys.exit(1)
        chunk = json.loads(body)
        if not chunk:
            break
        repos.extend(chunk)
        page += 1
    return repos


def target_name(r, source):
    """Pick the destination repo name in Forgejo."""
    if source == "starred":
        return r["full_name"].replace("/", "__")
    return r["name"]


def main():
    gh_user = os.environ.get("GITHUB_USER", "will-tm")
    gh_pat = os.environ["GITHUB_PAT"]
    fj_url = os.environ.get("FORGEJO_URL", "https://forgejo.will-tm.io").rstrip("/")
    fj_org = os.environ.get("FORGEJO_ORG", "gh-mirrors")
    fj_tok = os.environ["FORGEJO_TOKEN"]
    source = os.environ.get("MIRROR_SOURCE", "owned").lower()
    if source not in ("owned", "starred"):
        print(f"!! invalid MIRROR_SOURCE={source!r}", flush=True)
        sys.exit(2)
    fj_auth = f"token {fj_tok}"

    repos = list_github_repos(gh_pat, source)
    label = f"starred by {gh_user}" if source == "starred" else f"owned by {gh_user}"
    print(f"Discovered {len(repos)} GitHub repos {label}", flush=True)

    created = synced = failed = 0
    for r in repos:
        name = target_name(r, source)
        check_url = f"{fj_url}/api/v1/repos/{fj_org}/{name}"
        status, _ = _http(check_url, token_header=fj_auth)

        if status == 200:
            sync_url = f"{check_url}/mirror-sync"
            s, b = _http(sync_url, method="POST", token_header=fj_auth, timeout=60)
            if s == 200:
                print(f"SYNC OK   {fj_org}/{name}", flush=True)
                synced += 1
            else:
                err = b[:200].decode(errors="replace")
                print(f"SYNC FAIL {fj_org}/{name} status={s} {err}", flush=True)
                failed += 1

        elif status == 404:
            desc_prefix = (
                f"[mirror of {r['full_name']}] " if source == "starred" else ""
            )
            description = (desc_prefix + (r.get("description") or ""))[:255]
            body = {
                "clone_addr": r["clone_url"],
                "repo_owner": fj_org,
                "repo_name": name,
                "description": description,
                "mirror": True,
                "mirror_interval": "8h0m0s",
                "private": r["private"],
                "auth_token": gh_pat,
                "service": "github",
                "wiki": False,
                "issues": False,
                "pull_requests": False,
                "releases": True,
                "milestones": False,
                "labels": False,
            }
            mig_url = f"{fj_url}/api/v1/repos/migrate"
            s, b = _http(mig_url, method="POST", token_header=fj_auth, body=body)
            if s == 201:
                tag = "private" if r["private"] else "public"
                print(
                    f"CREATED   {fj_org}/{name} ({tag}, {r['size']}KB)",
                    flush=True,
                )
                created += 1
            else:
                err = b[:200].decode(errors="replace")
                print(f"CREATE FAIL {fj_org}/{name} status={s} {err}", flush=True)
                failed += 1

        else:
            print(f"CHECK FAIL {fj_org}/{name} status={status}", flush=True)
            failed += 1

    print(
        f"Summary: source={source} discovered={len(repos)} "
        f"created={created} synced={synced} failed={failed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
