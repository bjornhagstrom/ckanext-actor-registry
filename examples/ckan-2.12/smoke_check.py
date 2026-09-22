#!/usr/bin/env python3
"""Smoke test for the running example: is the extension installed, migrated and usable?

    python3 smoke_check.py

Uses only the Python standard library. Logs in with the sysadmin from .env (the
password is read from the file and never printed), then checks that the extension is
loaded, the registry pages work and the dataset form uses the example schema. Then it
runs the extension's main flow: create a publisher and a contact point, create a
dataset through the web form with both picked from the registry, and check that the
dataset page shows their details and that the publisher's page lists the dataset.

CKAN shows no dataset form until an organization exists, so the test creates one.
It leaves a few records behind ("Smoke test publisher", "Smoke test contact point",
"Smoke test organization" and "Smoke test dataset"); delete them if you like. Running
it again is safe: it reuses what is already there.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def read_env():
    values = {}
    with open(os.path.join(HERE, ".env")) as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key] = value
    return values


ENV = read_env()
# The process environment wins over .env, so a one-off override (a non-default port,
# for example) is honoured even when .env still has the default.
BASE = os.environ.get("CKAN_SITE_URL", ENV.get("CKAN_SITE_URL", "http://localhost:5000")).rstrip("/")
COOKIES = {}
failures = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def request(path, data=None, depth=0):
    req = urllib.request.Request(BASE + path if path.startswith("/") else path, data=data)
    if COOKIES:
        req.add_header("Cookie", "; ".join("%s=%s" % pair for pair in COOKIES.items()))
    try:
        resp = OPENER.open(req)
        status, headers, body = resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        status, headers, body = error.code, error.headers, error.read().decode("utf-8", "replace")
    # CKAN sends "Domain=;" which http.cookiejar rejects, so cookies are handled by hand.
    for header in headers.get_all("Set-Cookie") or []:
        name, _, value = header.split(";")[0].partition("=")
        COOKIES[name] = value
    if status in (301, 302, 303) and depth < 5:
        location = headers["Location"]
        return request(location[len(BASE):] if location.startswith(BASE) else location, None, depth + 1)
    return status, body


def check(label, ok, detail=""):
    print("%s  %s%s" % ("ok  " if ok else "FAIL", label, ("  (%s)" % detail) if detail and not ok else ""))
    if not ok:
        failures.append(label)


def csrf(page):
    match = re.search(r'name="_csrf_token"[^>]*value="([^"]+)"', page)
    return match.group(1) if match else ""



def find_link_id(path, name):
    """The id in the first link on ``path`` whose text is exactly ``name``, or None."""
    _, page = request(path)
    match = re.search(r'href="[^"]*/([0-9a-f-]{36})"[^>]*>\s*%s\s*<' % re.escape(name), page)
    return match.group(1) if match else None


def form_fields(page):
    """Hidden inputs and submit buttons of the first <form> that contains ``owner_org``/``url``.

    Attribute order in the markup is not fixed -- CKAN's resource form, for example,
    renders ``name`` and ``value`` before ``type`` -- so each ``<input>`` tag is parsed on
    its own rather than assumed to start with ``type="hidden"``.
    """
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", page):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', tag))
        if attrs.get("type") == "hidden" and "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


# 1. CKAN is up and both plugins are loaded.
status, body = request("/api/action/status_show")
extensions = json.loads(body)["result"]["extensions"] if status == 200 else []
check("CKAN answers", status == 200, "HTTP %s" % status)
check("actor_registry plugin loaded", "actor_registry" in extensions, str(extensions))
check("scheming_datasets plugin loaded", "scheming_datasets" in extensions, str(extensions))

# 2. Log in.
_, login_page = request("/user/login")
form = urllib.parse.urlencode({
    "login": ENV.get("CKAN_SYSADMIN_NAME", "admin"),
    "password": ENV["CKAN_SYSADMIN_PASSWORD"],
    "_csrf_token": csrf(login_page),
}).encode()
_, after_login = request("/user/login", form)
check("sysadmin can log in", "/user/_logout" in after_login or "Log out" in after_login)

# 3. The registry works: its tables exist (migration ran) and its pages render.
status, _ = request("/actors")
check("registry page /actors renders", status == 200, "HTTP %s" % status)
status, _ = request("/contactpoints")
check("registry page /contactpoints renders", status == 200, "HTTP %s" % status)

# 4. The dataset form uses the example schema. CKAN shows no dataset form until at
# least one organization exists, so create one (a no-op on later runs).
_, org_form = request("/organization/new")
status, _ = request("/organization/new", urllib.parse.urlencode({
    "name": "smoke-test-organization",
    "title": "Smoke test organization",
    "_csrf_token": csrf(org_form),
}).encode())
check("an organization exists", status in (200, 302) or "smoke-test-organization" in request("/organization/")[1])
status, dataset_form = request("/dataset/new")
check("dataset form renders", status == 200, "HTTP %s" % status)
check("dataset form has the publisher field", 'name="publisher_actor_id"' in dataset_form)
check("dataset form has the contact points field", 'name="contact_point_ids"' in dataset_form)

# 5. Create a publisher and a contact point (re-using them on later runs).
_, new_form = request("/actors/new")
status, body = request("/actors/quick-create", urllib.parse.urlencode({
    "name": "Smoke test publisher",
    "actor_kind": "organization",
    "identifier": "SMOKE-1",
    "identifier_scheme": "EXAMPLE",
    "url": "https://smoke.example.org",
    "_csrf_token": csrf(new_form),
}).encode())
created = status == 200 and json.loads(body).get("success") is True
publisher_id = json.loads(body)["actor"]["id"] if created else find_link_id("/actors", "Smoke test publisher")
check("publisher exists", bool(publisher_id), "HTTP %s %s" % (status, body[:120]))

contact_id = find_link_id("/contactpoints", "Smoke test contact point")
if not contact_id:
    _, cp_form = request("/contactpoints/new")
    status, body = request("/contactpoints/quick-create", urllib.parse.urlencode({
        "name": "Smoke test contact point",
        "email": "smoke@example.org",
        "actor_id": publisher_id or "",
        "_csrf_token": csrf(cp_form),
    }).encode())
    contact_id = json.loads(body)["contact_point"]["id"] if status == 200 else None
check("contact point exists", bool(contact_id))

_, dataset_form = request("/dataset/new")
check("both appear on the dataset form",
      "Smoke test publisher" in html.unescape(dataset_form) and "Smoke test contact point" in html.unescape(dataset_form))

# 6. Create a dataset through the web form, picking both from the registry.
#    CKAN does this in two steps: the dataset form, then a resource (a dataset made in
#    the UI must have one), after which the dataset becomes active.
DATASET = "smoke-test-dataset"
if request("/dataset/" + DATASET)[0] != 200:
    org_id = re.search(r'<option value="([0-9a-f-]{36})"[^>]*>\s*Smoke test organization', dataset_form)
    fields = form_fields(dataset_form)
    fields.update({
        "title": "Smoke test dataset",
        "name": DATASET,
        "notes": "Created by smoke_check.py.",
        "owner_org": org_id.group(1) if org_id else "",
        "private": "False",
        "publisher_actor_id": publisher_id or "",
        "contact_point_ids": contact_id or "",
        "save": "go-resource",
    })
    status, after_step_1 = request("/dataset/new", urllib.parse.urlencode(fields).encode())
    # Accepted means CKAN moved on to the resource form; on a validation error it shows
    # the dataset form again, with the error messages.
    errors = re.findall(r'<li[^>]*data-field-label[^>]*>(.*?)</li>|class="error-block"[^>]*>(.*?)<', after_step_1, re.S)
    check("dataset form is accepted (step 1: dataset)", 'name="url"' in after_step_1 and 'name="publisher_actor_id"' not in after_step_1,
          "HTTP %s, form errors: %s" % (status, [" ".join(filter(None, e)).strip() for e in errors][:3]))
    _, resource_form = request("/dataset/%s/resource/new" % DATASET)
    fields = form_fields(resource_form)
    fields.update({
        "url": "https://smoke.example.org/data.csv",
        "name": "Smoke test data",
        "save": "go-metadata",
    })
    status, after_step_2 = request("/dataset/%s/resource/new" % DATASET, urllib.parse.urlencode(fields).encode())
    # Accepted means CKAN moved on (redirected to the dataset page, finishing the
    # draft): status 200 with no error messages in the body. A validation error
    # re-renders this same form with error messages; a server error is a non-200
    # status. Either way it must be caught here, not silently ignored.
    errors = re.findall(r'<li[^>]*data-field-label[^>]*>(.*?)</li>|class="error-block"[^>]*>(.*?)<', after_step_2, re.S)
    check("resource form is accepted (step 2: resource)", status == 200 and not errors,
          "HTTP %s, form errors: %s" % (status, [" ".join(filter(None, e)).strip() for e in errors][:3]))

status, dataset_page = request("/dataset/" + DATASET)
text = html.unescape(re.sub(r"<[^>]+>", " ", dataset_page))
check("the dataset was created and is visible", status == 200 and "Smoke test dataset" in text, "HTTP %s" % status)
check("the resource created by the smoke test is on the dataset page", "Smoke test data" in text)
check("the dataset page shows the publisher by name, not by id",
      "Smoke test publisher" in text and (publisher_id or "-") not in text.replace("/actors/" + (publisher_id or ""), ""))
check("the dataset page shows the contact point and its email",
      "Smoke test contact point" in text and "smoke@example.org" in text)
status, publisher_page = request("/actors/" + (publisher_id or "missing"))
check("the publisher's page lists the dataset", status == 200 and "Smoke test dataset" in html.unescape(publisher_page))
status, contact_page = request("/contactpoints/" + (contact_id or "missing"))
check("the contact point's page lists the dataset", status == 200 and "Smoke test dataset" in html.unescape(contact_page))

# 7. Swedish texts are available.
status, sv_page = request("/sv/actors")
check("Swedish UI works", status == 200 and "Utgivare" in sv_page, "HTTP %s" % status)

print()
if failures:
    print("%d check(s) failed." % len(failures))
    sys.exit(1)
print("All checks passed.")
