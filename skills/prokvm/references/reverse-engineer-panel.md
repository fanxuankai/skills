# Reverse-engineering a ProKvm panel

The ProKvm member center has no official API. Endpoints below were derived by reading the panel's own HTML/JS with `curl -sk`. Replace `<panel-ip>` with the user's panel host throughout. Repeat this process when the panel upgrades and the bundled script stops working.

## 1. Get a working session

```bash
# Save cookies to a jar so subsequent curl calls are authenticated
curl -sk -c /tmp/pk.cookies -o /tmp/pk.login.html \
  "https://<panel-ip>/login"

# Log in
curl -sk -c /tmp/pk.cookies -b /tmp/pk.cookies -o /tmp/pk.index.html \
  -X POST "https://<panel-ip>/login" \
  -H "Referer: https://<panel-ip>/login" \
  --data-urlencode "username=..." \
  --data-urlencode "password=..." \
  --data "login_type=PASS" --data "submit=1"
```

Confirm success by grepping the response for `member/index` or `setTimeout` (the panel redirects after a successful login). If neither appears, the login form field names may have changed — inspect `/tmp/pk.login.html` for the `<form>` and its `<input>` names.

## 2. Find the server list

Browse `/server/index`:

```bash
curl -sk -b /tmp/pk.cookies "https://<panel-ip>/server/index?page=0" -o /tmp/pk.list0.html
curl -sk -b /tmp/pk.cookies "https://<panel-ip>/server/index?page=10" -o /tmp/pk.list10.html
```

The list page does **not** render rows server-side in a clean table — it embeds a JS object:

```html
<script> var list = { "0": { "id_sn": "701", "net": "100", ... }, "1": {...} }; </script>
```

Extract it:

```bash
python3 -c "
import re, json
html = open('/tmp/pk.list0.html').read()
m = re.search(r'var list\s*=\s*(\{.*?\})\s*;', html, re.S)
print(json.dumps(json.loads(m.group(1)), ensure_ascii=False, indent=2))
"
```

`page=0` returns the first 10 servers, `page=10` the next batch. There is also `/server/index?size=1000` which returns everything on one page — handy for counting, but still parse the `var list` block the same way.

## 3. Inspect one upgrade page

```bash
curl -sk -b /tmp/pk.cookies \
  "https://<panel-ip>/server/detail/701/upgrade?type=list" \
  -o /tmp/pk.upg701.html
```

Look for three things in the HTML:

1. `name="spec_id"` — a `<select>` whose first `<option value="...">` is the current spec id.
2. A slider bound to `net`, with min/current/max attributes. The markup varies; useful regexes:
   - min: `net:\s*"(\d+)"`
   - current: `form_data:\s*\{[^}]*net:\s*"(\d+)"`
   - max: `:max="parseFloat\('(\d+)'\)"`
3. The form action — usually `POST` to the same URL without the `?type=list` query.

## 4. Test one upgrade submit

Always test on a single server before batching. Open the browser's devtools (or use curl) to capture the exact form fields and headers the panel sends:

```bash
curl -sk -b /tmp/pk.cookies \
  -X POST "https://<panel-ip>/server/detail/701/upgrade" \
  -H "Referer: https://<panel-ip>/server/detail/701/upgrade?type=list" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "X-PJAX: true" \
  --data "spec_id=...&net=200&def=0&coupon_id=0&action=1&type=server&scene=server_upgrade"
```

The panel returns JSON: `{"code":0,"msg":"云服务器升级成功！"}` on success. Any non-zero `code` carries a `msg` describing the failure (node SSL error, insufficient balance, spec mismatch, etc.).

## 5. When endpoints drift

If a step returns unexpected HTML or a non-zero code with an unfamiliar message, re-run step 1–4 against the panel and diff against the saved `/tmp/pk.*.html` files. The panel is small enough that the whole surface is one login + a handful of `/server/*` pages, so finding the new field/endpoint is quick once you have the cookie jar working.
