"""Official-number messaging through your own provider account: WhatsApp Business (Meta Cloud API), Twilio (SMS + WhatsApp),
MSG91 (SMS flow) or any provider with a simple HTTPS JSON API ("Custom").
This software never holds your money or your provider's rules. You must have an approved provider account, approved WhatsApp
templates and (for SMS in India) DLT-registered sender ID and templates. Messages go only to people marked as agreeing to them."""
import json, re, ssl, base64, urllib.request, urllib.error, urllib.parse, ipaddress, socket
from . import db

class GatewayError(Exception):
    pass

PROVIDERS = {"whatsapp": ["None", "Meta", "Twilio", "Custom"], "sms": ["None", "MSG91", "Twilio", "Custom"]}

def normalise_phone(raw, default_cc="91"):
    """Return digits-only international number (no +) or None."""
    d = re.sub(r"[^\d+]", "", raw or "")
    plus = d.startswith("+")
    d = d.lstrip("+")
    if not d: return None
    if not plus:
        if len(d) == 10: d = default_cc + d
        elif len(d) == 11 and d.startswith("0"): d = default_cc + d[1:]
        elif len(d) == 12 and d.startswith(default_cc): pass
    return d if 10 <= len(d) <= 15 and not d.startswith("0") else None

def _safe_url(url):
    u = urllib.parse.urlparse(url or "")
    if u.scheme != "https" or not u.hostname: raise GatewayError("Provider address must start with https://")
    try:
        for fam, _t, _p, _c, sa in socket.getaddrinfo(u.hostname, u.port or 443, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sa[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved: raise GatewayError("Provider address points to a private network, which is not allowed")
    except socket.gaierror:
        raise GatewayError("Could not find the provider's address")
    return url

def _post(url, headers, data, timeout=20):
    """HTTPS POST. Returns (status, text). Replaced in tests."""
    _safe_url(url)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return r.status, r.read(20000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(20000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise GatewayError(f"Could not reach the provider: {e}")

def _err(body, status):
    try:
        j = json.loads(body)
        m = (j.get("error") or {}).get("message") if isinstance(j.get("error"), dict) else j.get("message") or j.get("error") or j.get("errors")
        return f"Provider said ({status}): {str(m)[:200]}"
    except (ValueError, AttributeError):
        return f"Provider said ({status}): {body[:200]}"

def configured(s, channel):
    p = s.get("wa_provider" if channel == "whatsapp" else "sms_provider", "None")
    return p if p in PROVIDERS[channel] and p != "None" else None

def status(s):
    return dict(whatsapp=configured(s, "whatsapp"), sms=configured(s, "sms"))

def _need(s, *keys):
    miss = [k for k in keys if not (s.get(k) or "").strip()]
    if miss: raise GatewayError("Provider settings are incomplete. Fill in: " + ", ".join(miss))

def send(s, channel, to, text, params=(), template=""):
    """Send one message. Returns the provider's message id (string). Raises GatewayError on any problem."""
    p = configured(s, channel)
    if not p: raise GatewayError(f"{'WhatsApp' if channel == 'whatsapp' else 'SMS'} is not set up. Open Settings → Official WhatsApp and SMS.")
    num = normalise_phone(to)
    if not num: raise GatewayError("That phone number does not look right")
    params = [str(x) for x in params]
    if channel == "whatsapp" and p == "Meta":
        _need(s, "wa_phone_id", "wa_token")
        if template:
            body = {"messaging_product": "whatsapp", "to": num, "type": "template", "template": {"name": template, "language": {"code": s.get("wa_lang") or "en"}}}
            if params: body["template"]["components"] = [{"type": "body", "parameters": [{"type": "text", "text": x} for x in params]}]
        else:   # free text only works inside WhatsApp's 24-hour reply window
            body = {"messaging_product": "whatsapp", "to": num, "type": "text", "text": {"body": text}}
        st, out = _post(f"https://graph.facebook.com/v20.0/{urllib.parse.quote(s['wa_phone_id'].strip(), safe='')}/messages",
                        {"Authorization": "Bearer " + s["wa_token"].strip(), "Content-Type": "application/json"}, json.dumps(body).encode())
        if st >= 300: raise GatewayError(_err(out, st))
        try: return json.loads(out)["messages"][0]["id"]
        except (ValueError, KeyError, IndexError): return ""
    if p == "Twilio":
        _need(s, "twilio_sid", "twilio_token", "twilio_wa_from" if channel == "whatsapp" else "twilio_sms_from")
        frm = s["twilio_wa_from"].strip() if channel == "whatsapp" else s["twilio_sms_from"].strip()
        form = {"To": ("whatsapp:+" if channel == "whatsapp" else "+") + num, "From": (("whatsapp:" + frm.replace("whatsapp:", "")) if channel == "whatsapp" else frm)}
        if channel == "whatsapp" and template.startswith("HX"):
            form["ContentSid"] = template; form["ContentVariables"] = json.dumps({str(i + 1): v for i, v in enumerate(params)})
        else:
            form["Body"] = text
        auth = base64.b64encode(f"{s['twilio_sid'].strip()}:{s['twilio_token'].strip()}".encode()).decode()
        st, out = _post(f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(s['twilio_sid'].strip(), safe='')}/Messages.json",
                        {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"}, urllib.parse.urlencode(form).encode())
        if st >= 300: raise GatewayError(_err(out, st))
        try: return json.loads(out).get("sid", "")
        except ValueError: return ""
    if channel == "sms" and p == "MSG91":
        _need(s, "sms_authkey")
        if not template: raise GatewayError("MSG91 needs your DLT-approved template ID on the template (Approved template name or DLT template ID)")
        rec = {"mobiles": num}
        for i, v in enumerate(params): rec[f"VAR{i + 1}"] = v
        st, out = _post("https://control.msg91.com/api/v5/flow/", {"authkey": s["sms_authkey"].strip(), "Content-Type": "application/json", "accept": "application/json"},
                        json.dumps({"template_id": template, "recipients": [rec]}).encode())
        if st >= 300: raise GatewayError(_err(out, st))
        try:
            j = json.loads(out)
            if str(j.get("type", "success")).lower() == "error": raise GatewayError(_err(out, st))
            return str(j.get("message") or "")
        except ValueError: return ""
    if p == "Custom":
        _need(s, "custom_url")
        try: hdr = json.loads(s.get("custom_headers") or "{}"); assert isinstance(hdr, dict)
        except (ValueError, AssertionError): raise GatewayError("Custom headers must be a JSON object, e.g. {\"Authorization\": \"Bearer …\"}")
        tpl = s.get("custom_body") or '{"to": "{to}", "message": "{message}"}'
        def q(v): return json.dumps(str(v))[1:-1]            # JSON-escape each value so the body stays valid JSON
        body = tpl.replace("{to}", q(num)).replace("{message}", q(text)).replace("{channel}", channel).replace("{template}", q(template))
        for i, v in enumerate(params): body = body.replace("{p%d}" % (i + 1), q(v))
        try: json.loads(body)
        except ValueError: raise GatewayError("Custom body is not valid JSON after filling in the message")
        st, out = _post(s["custom_url"].strip(), {"Content-Type": "application/json", **{str(k): str(v) for k, v in hdr.items()}}, body.encode())
        if st >= 300: raise GatewayError(_err(out, st))
        return ""
    raise GatewayError("That provider does not support this channel")
