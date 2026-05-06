#!/usr/bin/env python3
"""Mirror all GitHub repos owned by GITHUB_USER to a Forgejo org.

Reads config from env: GITHUB_USER, GITHUB_PAT, FORGEJO_URL, FORGEJO_ORG,
FORGEJO_TOKEN. Idempotent: creates missing mirrors, force-syncs existing
ones. One line of stdout per repo. Exits 0 even if individual repos fail
so a single bad mirror doesn't block the rest of the nightly job.
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


def list_github_repos(user_token):
    repos = []
    page = 1
    while True:
        url = (
            "https://api.github.com/user/repos"
            f"?affiliation=owner&visibility=all&per_page=100&page={page}"
        )
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


def main():
    gh_user = os.environ.get("GITHUB_USER", "will-tm")
    gh_pat = os.environ["GITHUB_PAT"]
    fj_url = os.environ.get("FORGEJO_URL", "https://forgejo.will-tm.io").rstrip("/")
    fj_org = os.environ.get("FORGEJO_ORG", "gh-mirrors")
    fj_tok = os.environ["FORGEJO_TOKEN"]
    fj_auth = f"token {fj_tok}"

    repos = list_github_repos(gh_pat)
    print(f"Discovered {len(repos)} GitHub repos under {gh_user}", flush=True)

    created = synced = failed = 0
    for r in repos:
        name = r["name"]
        check_url = f"{fj_url}/api/v1/repos/{fj_org}/{name}"
        status, _ = _http(check_url, token_header=fj_auth)

        if status == 200:
            sync_url = f"{check_url}/mirror-sync"
            s, b = _http(sync_url, method="POST", token_header=fj_auth, timeout=60)
            if s == 200:
                print(f"SYNC OK   {fj_org}/{name}", flush=True)
                synced += 1
            else:
                print(f"SYNC FAIL {fj_org}/{name} status={s} {b[:200].decode(errors='replace')}", flush=True)
                failed += 1

        elif status == 404:
            body = {
                "clone_addr": r["clone_url"],
                "repo_owner": fj_org,
                "repo_name": name,
                "description": (r.get("description") or "")[:255],
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
                print(f"CREATED   {fj_org}/{name} ({tag}, {r['size']}KB)", flush=True)
                created += 1
            else:
                err = b[:200].decode(errors="replace")
                print(f"CREATE FAIL {fj_org}/{name} status={s} {err}", flush=True)
                failed += 1

        else:
            print(f"CHECK FAIL {fj_org}/{name} status={status}", flush=True)
            failed += 1

    print(
        f"Summary: discovered={len(repos)} created={created} "
        f"synced={synced} failed={failed}",
        flush=True,
    )


if __name__ == "__main__":
    main()
