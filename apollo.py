"""Apollo.io client — the ENRICHMENT tool in the toolbox.

Verified working flow (paid plan):
  1. organizations/enrich (domain) -> org id + employees / revenue / founded
  2. mixed_people/api_search (organization_ids + owner titles) -> owner record id
     (people/search is deprecated; search masks name/email until revealed)
  3. people/match (id, reveal_personal_emails) -> real name + email + LinkedIn
     (costs 1 credit; mobile phone needs the async webhook flow — not done here)
"""
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import config

_BASE = "https://api.apollo.io/api/v1"
OWNER_TITLES = ["owner", "president", "founder", "ceo",
                "general manager", "partner", "principal"]

try:
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _CTX = ssl.create_default_context()


def _req(method: str, path: str, body: dict = None, params: dict = None) -> dict:
    url = _BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Api-Key", config.APOLLO_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45, context=_CTX) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"error": f"HTTP {e.code}"}


def enrich_org(domain: str) -> dict | None:
    res = _req("GET", "/organizations/enrich", params={"domain": domain})
    return res.get("organization") if isinstance(res, dict) else None


def find_owner(org_id: str) -> dict | None:
    res = _req("POST", "/mixed_people/api_search",
               body={"organization_ids": [org_id],
                     "person_titles": OWNER_TITLES, "per_page": 1})
    ppl = res.get("people", []) if isinstance(res, dict) else []
    return ppl[0] if ppl else None


def reveal_person(person_id: str) -> dict | None:
    res = _req("POST", "/people/match",
               body={"id": person_id, "reveal_personal_emails": True})
    return res.get("person") if isinstance(res, dict) else None


def enrich_company(domain: str, pause: float = 0.4) -> dict:
    """Full enrichment for one company domain. Returns {org, owner}."""
    out = {"domain": domain, "org": None, "owner": None}
    org = enrich_org(domain)
    if not org or not org.get("id"):
        return out
    out["org"] = org
    time.sleep(pause)
    stub = find_owner(org["id"])
    if stub and stub.get("id"):
        time.sleep(pause)
        out["owner"] = reveal_person(stub["id"]) or stub
    return out
