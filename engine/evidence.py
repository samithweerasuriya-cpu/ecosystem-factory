#!/usr/bin/env python3
"""Evidence module: sources are fetched and stored by script, and claims are checked against the
stored copies before any reviewer runs. Stdlib only (PDF text needs the optional markitdown CLI).

Derived from the author's earlier private labs (source registry, citation format, verifier rules,
"cited means fetched" check), with the stored copy as the single source of truth.

  python engine/evidence.py fetch <job> <url> --handoff H<nnn> [--title T]
  python engine/evidence.py register <job> <path> [--title T]   # a file from the job's inputs/ or sources/
  python engine/evidence.py list <job>
  python engine/evidence.py check <job> [<artifact>]          # exit 0 clean, 1 problems
  python engine/evidence.py refetch <job>                      # restore missing cached copies, flag changes
  python engine/evidence.py show <job> <source-id>             # where the stored copy is

Rules (rules/check-evidence.md): E01 unknown source, E02 not stored by the fetch script or unfetchable
backing a fact, E03 quote not verbatim, E04 claim type rule (fact: rank; decision: answers or approved
artifact), E05 quote too long, E06 stored copy missing or changed.
Where things live: the tracked registry, fetch log and quote index in <job>/evidence/; page text in
an untracked cache: cache/evidence/ for synthetic and public jobs, <job>/evidence/cache/ for internal
jobs (inside private/). Only this script writes them (the hook blocks every other write).
"""
import argparse
import datetime
import hashlib
import html.parser
import ipaddress
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labcore as lc  # noqa: E402
import check_refs  # noqa: E402

CITE_RE = re.compile(r"\[(S|A|G):([A-Za-z0-9._-]+)(?:\s*§\s*([^\]\"“”]*?))?\s*(?:[\"“]([^\"”]*)[\"”])?\s*\]")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
DEFAULTS = {"enabled": True, "claim_types": {"fact": {"cites": ["S"], "max_rank": 4, "high_confidence": True},
                                             "decision": {"cites": ["A", "G"], "high_confidence": True}},
            "domains": {}, "files": {}, "max_quote_words": 25, "min_text_chars": 400, "max_fetch_bytes": 5000000,
            "fetch_timeout_s": 20, "max_redirects": 5, "polite_pause_s": 1.0,
            "user_agent": "ecosystem-factory-evidence/1.0", "pdf_converter": ["markitdown"], "allow_private_hosts": False}


class EvidenceError(lc.LabError):
    pass


def config():
    f = lc.CONFIG / "evidence.json"
    return {**DEFAULTS, **(lc.load_json(f) if f.exists() else {})}


def enabled():
    return (lc.CONFIG / "evidence.json").exists() and config().get("enabled", True)


# ---------- where things live ----------

def store(job_id):
    d = lc.job_dir(job_id) / "evidence"
    d.mkdir(exist_ok=True)
    return d


def cache_dir(job_id):
    d = (lc.job_dir(job_id) / "evidence" / "cache") if lc.is_internal(job_id) else (lc.ROOT / "cache" / "evidence")
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_registry(job_id):
    f = store(job_id) / "registry.json"
    return lc.load_json(f) if f.exists() else {"sources": []}


def save_registry(job_id, reg):
    lc.save_json(store(job_id) / "registry.json", reg)


def fetch_log(job_id):
    f = store(job_id) / "fetch-log.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def log_fetch(job_id, entry):
    with open(store(job_id) / "fetch-log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": lc.now_ms(), **entry}) + "\n")


def next_id(reg):
    return f"S{len(reg['sources']) + 1:02d}"


def rank_for_host(host, cfg):
    host = (host or "").casefold()
    for domain, rank in sorted(cfg.get("domains", {}).items(), key=lambda kv: -len(kv[0])):
        d = domain.casefold()
        if host == d or host.endswith("." + d):
            return int(rank)
    return 5


# ---------- text ----------

class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.noscript, self.title, self._skip, self._in_title, self._in_noscript = [], [], "", 0, False, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "noscript":
            self._in_noscript = True
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "noscript":
            self._in_noscript = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        elif self._in_noscript:
            self.noscript.append(data)
        else:
            self.parts.append(data)


def html_to_text(raw):
    p = _Text()
    p.feed(raw)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.parts))
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    js = bool(re.search(r"(enable|requires?|turn on)\s+javascript", (" ".join(p.noscript) + " " + text[:2000]), re.I))
    return p.title.strip(), text, js


def normalise(s):
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def convert_pdf(raw, cfg):
    """Text of a PDF through the markitdown CLI (as the earlier lab's ingest did), or None."""
    cmd = cfg.get("pdf_converter") or []
    if not cmd or shutil.which(cmd[0]) is None:
        return None
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "doc.pdf"
        f.write_bytes(raw)
        r = subprocess.run([*cmd, str(f)], capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 and r.stdout.strip() else None


def convert(raw, content_type, name, cfg):
    """(title, text, status, reason) for fetched or registered bytes."""
    if content_type in ("text/html", "application/xhtml+xml") or name.lower().endswith((".html", ".htm")):
        title, text, js = html_to_text(raw.decode("utf-8", errors="replace"))
        if js or len(text) < cfg["min_text_chars"]:
            return title, text, "unfetchable", "no readable text without JavaScript (or too little text)"
        return title, text, "stored", None
    if content_type == "application/pdf" or name.lower().endswith(".pdf"):
        text = convert_pdf(raw, cfg)
        if text is None:
            return "", "", "unfetchable", "PDF: no converter available (install the markitdown CLI) or conversion failed"
        return "", text, "stored", None
    if content_type.startswith("text/") or content_type in ("application/json", "application/xml") \
            or name.lower().endswith((".md", ".txt", ".csv", ".json", ".xml", ".yaml", ".yml")):
        return "", raw.decode("utf-8", errors="replace"), "stored", None
    return "", "", "unfetchable", f"unsupported content type {content_type or 'unknown'}"


# ---------- fetching ----------

def check_host(url, cfg):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise EvidenceError(f"only http(s) URLs can be fetched: {url}")
    if cfg.get("allow_private_hosts"):
        return u.hostname
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))}
    except socket.gaierror as e:
        raise EvidenceError(f"cannot resolve {u.hostname}: {e}")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise EvidenceError(f"{u.hostname} resolves to a private or local address ({a}); refused")
    return u.hostname


class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, cfg):
        super().__init__()
        self.cfg, self.count = cfg, 0
        self.max_redirections = cfg["max_redirects"]

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.cfg["max_redirects"]:
            raise EvidenceError(f"more than {self.cfg['max_redirects']} redirects")
        check_host(newurl, self.cfg)              # the private-address rule again, after every redirect
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(job_id, url, handoff, title=None, _opener=None):
    """Fetch one page inside an open agent call, store its text and register it. Returns the entry."""
    cfg, caps = config(), lc.caps()
    call = lc.find_call_by_handoff(job_id, handoff) if handoff else None
    if call is None:
        raise EvidenceError("fetch only inside an open agent call: pass --handoff from your handoff block")
    log = fetch_log(job_id)
    if len([e for e in log if e.get("call") == call["id"]]) >= caps.get("fetches_per_call", 15):
        log_fetch(job_id, {"url": url, "call": call["id"], "status": "refused", "reason": "fetches_per_call cap"})
        raise EvidenceError(f"fetch cap reached for {call['id']}: fetches_per_call={caps.get('fetches_per_call', 15)}")
    if len([e for e in log if e.get("status") != "refused"]) >= caps.get("fetches_per_job", 60):
        log_fetch(job_id, {"url": url, "call": call["id"], "status": "refused", "reason": "fetches_per_job cap"})
        raise EvidenceError(f"fetch cap reached for {job_id}: fetches_per_job={caps.get('fetches_per_job', 60)}")
    try:
        host = check_host(url, cfg)
    except EvidenceError as e:
        log_fetch(job_id, {"url": url, "call": call["id"], "status": "refused", "reason": str(e)})
        raise
    last = [e for e in log if e.get("host") == host and e.get("status") in ("stored", "unfetchable", "error")]
    if last:  # polite: a short pause between requests to the same host
        waited = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(last[-1]["ts"])).total_seconds()
        if waited < cfg["polite_pause_s"]:
            time.sleep(cfg["polite_pause_s"] - waited)
    opener = _opener or urllib.request.build_opener(_Redirects(cfg))
    req = urllib.request.Request(url, headers={"User-Agent": cfg["user_agent"], "Accept": "text/html,text/plain,application/pdf;q=0.9,*/*;q=0.5"})
    try:
        with opener.open(req, timeout=cfg["fetch_timeout_s"]) as resp:
            raw = resp.read(cfg["max_fetch_bytes"] + 1)
            final_url, ctype = resp.geturl(), resp.headers.get_content_type()
    except (urllib.error.URLError, OSError, EvidenceError) as e:
        log_fetch(job_id, {"url": url, "host": host, "call": call["id"], "status": "error", "reason": str(e)[:300]})
        raise EvidenceError(f"fetch failed for {url}: {e}")
    if len(raw) > cfg["max_fetch_bytes"]:
        page_title, text, status, reason = "", "", "unfetchable", f"larger than {cfg['max_fetch_bytes']} bytes"
    else:
        page_title, text, status, reason = convert(raw, ctype, urllib.parse.urlsplit(final_url).path, cfg)
    entry = _register(job_id, kind="web", where={"url": url, "final_url": final_url},
                      title=title or page_title or url, rank=rank_for_host(urllib.parse.urlsplit(final_url).hostname, cfg),
                      text=text, raw=raw, status=status, reason=reason, extra={"content_type": ctype, "call": call["id"]})
    log_fetch(job_id, {"url": url, "final_url": final_url, "host": host, "call": call["id"], "status": status,
                       "reason": reason, "bytes": len(raw), "source": entry["id"], "sha256": entry["sha256"]})
    return entry


def _register(job_id, kind, where, title, rank, text, raw, status, reason, extra):
    reg = load_registry(job_id)
    body = text.encode("utf-8") if status == "stored" else raw
    sha = hashlib.sha256(body).hexdigest()
    key = where.get("url") or where.get("path")
    same = next((s for s in reg["sources"] if (s.get("url") or s.get("path")) == key and s["sha256"] == sha), None)
    if same:
        return same
    if status == "stored":
        (cache_dir(job_id) / f"{sha}.txt").write_text(text, encoding="utf-8")
    entry = {"id": next_id(reg), "kind": kind, **where, "title": title[:200], "rank": rank, "fetched_at": lc.now(),
             "sha256": sha, "status": status, "reason": reason, "bytes": len(raw), **extra}
    prior = [s for s in reg["sources"] if (s.get("url") or s.get("path")) == key]
    if prior:
        entry["supersedes"] = prior[-1]["id"]
    reg["sources"].append(entry)
    save_registry(job_id, reg)
    return entry


def register(job_id, path, title=None):
    """Register a local file: only from the job's inputs/ (the approver's) or the operate-locked sources/."""
    cfg = config()
    p = Path(path)
    p = (p if p.is_absolute() else lc.ROOT / p).resolve()
    allowed = [(lc.job_dir(job_id) / "inputs").resolve(), (lc.ROOT / "sources").resolve()]
    if not any(p.is_relative_to(a) for a in allowed) or not p.is_file():
        raise EvidenceError("register only files from the job's inputs/ or the ecosystem's sources/ folder")
    raw = p.read_bytes()
    rel = lc.rel(p)
    page_title, text, status, reason = convert(raw, "", p.name, cfg)
    rank = int(cfg.get("files", {}).get(rel, 5))
    return _register(job_id, kind="file", where={"path": rel}, title=title or page_title or p.name, rank=rank,
                     text=text, raw=raw, status=status, reason=reason, extra={})


def stored_text(job_id, entry):
    f = cache_dir(job_id) / f"{entry['sha256']}.txt"
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8")
    return text if hashlib.sha256(text.encode("utf-8")).hexdigest() == entry["sha256"] else None


def refetch(job_id, _opener=None):
    """Restore missing cached copies (fresh clone); a page whose content changed is marked 'changed'."""
    cfg, reg, out = config(), load_registry(job_id), []
    for s in reg["sources"]:
        if s["status"] != "stored" or stored_text(job_id, s) is not None:
            continue
        if s["kind"] == "file":
            p = lc.ROOT / s["path"]
            text = convert(p.read_bytes(), "", p.name, cfg)[1] if p.exists() else ""
        else:
            check_host(s["final_url"], cfg)
            opener = _opener or urllib.request.build_opener(_Redirects(cfg))
            with opener.open(urllib.request.Request(s["final_url"], headers={"User-Agent": cfg["user_agent"]}),
                             timeout=cfg["fetch_timeout_s"]) as resp:
                raw, ctype = resp.read(cfg["max_fetch_bytes"] + 1), resp.headers.get_content_type()
            text = convert(raw, ctype, urllib.parse.urlsplit(s["final_url"]).path, cfg)[1]
        if hashlib.sha256(text.encode("utf-8")).hexdigest() == s["sha256"]:
            (cache_dir(job_id) / f"{s['sha256']}.txt").write_text(text, encoding="utf-8")
            out.append((s["id"], "restored"))
        else:
            s["status"], s["reason"] = "changed", f"content changed since {s['fetched_at']} (re-fetched {lc.now()})"
            out.append((s["id"], "changed"))
    save_registry(job_id, reg)
    return out


# ---------- checking an artifact ----------

def check(job_id, artifact):
    """(problems, uncited sentences, quotes) for an artifact version. Problems use rules E01-E06."""
    cfg = config()
    st = lc.load_state(job_id)
    reg = {s["id"]: s for s in load_registry(job_id)["sources"]}
    inputs = {i["id"]: i for i in st.get("inputs", [])}
    fact = cfg["claim_types"]["fact"]
    max_words = cfg["max_quote_words"]
    problems, uncited, quotes = [], [], []

    def problem(rule, loc, issue):
        problems.append({"rule": rule, "location": loc, "issue": issue})

    for where, text in check_refs.artifact_texts(lc.ROOT, artifact):
        for n, line in enumerate(text.splitlines(), 1):
            loc = f"{where}:{n}"
            for m in CITE_RE.finditer(line):
                kind, sid, location, quote = m.group(1), m.group(2), (m.group(3) or "").strip(), m.group(4)
                if quote is not None and len(quote.split()) > max_words:
                    problem("E05", loc, f"quote of {len(quote.split())} words cited to {kind}:{sid}; at most {max_words}")
                if kind == "S":
                    s = reg.get(sid)
                    if s is None:
                        problem("E01", loc, f"source {sid} is not in the evidence registry")
                        continue
                    if s["status"] == "changed":
                        problem("E06", loc, f"source {sid} changed since it was stored ({s.get('reason')}); fetch it again and re-check the claim")
                        continue
                    if s["status"] != "stored":
                        problem("E02", loc, f"source {sid} is {s['status']} ({s.get('reason')}); it cannot back a fact")
                        continue
                    body = stored_text(job_id, s)
                    if body is None:
                        problem("E06", loc, f"stored copy of {sid} is missing or changed; run evidence.py refetch")
                        continue
                    if s["rank"] > fact["max_rank"]:
                        problem("E04", loc, f"{sid} has rank {s['rank']}; a fact needs rank {fact['max_rank']} or better")
                    if quote is not None:
                        quotes.append({"source": sid, "location": location, "quote": quote, "sha256": s["sha256"], "at": loc})
                        if normalise(quote) not in normalise(body):
                            problem("E03", loc, f"quote is not word for word in {sid}: \"{quote[:80]}\"")
                elif kind == "A":
                    i = inputs.get(sid)
                    if i is None:
                        problem("E04", loc, f"decision cites [A:{sid}], which is not a recorded input")
                    elif quote is not None:
                        body = (lc.ROOT / i["path"]).read_text(encoding="utf-8", errors="replace")
                        quotes.append({"source": f"A:{sid}", "location": location, "quote": quote, "at": loc})
                        if normalise(quote) not in normalise(body):
                            problem("E03", loc, f"quote is not word for word in input {sid}: \"{quote[:80]}\"")
                elif kind == "G":
                    try:
                        g = lc.load_state(sid)
                        ok, why = lc.verify_gate(sid, g["route"]["gate"]) if g["route"].get("gate") else (False, "no gate")
                    except lc.LabError as e:
                        ok, why = False, str(e)
                    if not ok:
                        problem("E04", loc, f"decision cites [G:{sid}], which is not an approved artifact ({why})")
            if not CITE_RE.search(line):
                for sentence in SENTENCE_RE.split(line):
                    s = sentence.strip()
                    if s and not s.startswith(("#", "|-", "```", ">")) and re.search(r"\d|https?://|[\"“]", s):
                        uncited.append({"at": loc, "sentence": s[:200]})
    return problems, uncited, quotes


def findings_doc(job_id, artifact, version, problems):
    return {"job_id": job_id, "reviewer": "check-evidence", "artifact_path": artifact, "artifact_version": version,
            "verdict": "fail" if problems else "pass", "rules_checked": ["E01", "E02", "E03", "E04", "E05", "E06"],
            "findings": [{"id": f"F-{i:02d}", "rule": p["rule"], "severity": "blocker", "location": p["location"],
                          "issue": p["issue"], "fix": "Cite a stored source that supports the claim, fix the quote, "
                          "or turn the claim into an open question."} for i, p in enumerate(problems, 1)],
            "summary": f"{len(problems)} evidence problem(s)" if problems else "all citations check out"}


def record_check(job_id, artifact, version):
    """Run the check, write the quote index and the uncited list for the Verifier; return problems."""
    problems, uncited, quotes = check(job_id, artifact)
    lc.save_json(store(job_id) / "quotes.json", {"artifact": artifact, "version": version, "quotes": quotes})
    lc.save_json(store(job_id) / f"uncited-{version}.json",
                 {"artifact": artifact, "note": "hint list for the Verifier: sentences with numbers, links or quote "
                  "marks but no citation; not a check", "sentences": uncited})
    return problems


# ---------- registry check (ported registry_check.py) ----------

def check_registry(job_ids=None):
    """(problems, orphans) across the given jobs (default: every job): duplicate ids, stored entries
    whose cached copy is missing or does not match, and cached files no entry references."""
    jobs = job_ids or [s["job_id"] for s in lc.all_jobs()]
    problems, referenced, caches = [], set(), set()
    for j in jobs:
        seen = set()
        for s in load_registry(j)["sources"]:
            if s["id"] in seen:
                problems.append(f"{j}: DUPLICATE id {s['id']}")
            seen.add(s["id"])
            if s["status"] == "stored":
                f = cache_dir(j) / f"{s['sha256']}.txt"
                referenced.add(f.resolve())
                if stored_text(j, s) is None:
                    problems.append(f"{j}: MISSING stored copy for {s['id']} ({lc.rel(f)})")
        caches.add(cache_dir(j).resolve())
    orphans = sorted(lc.rel(f) for d in caches for f in Path(d).glob("*.txt") if f.resolve() not in referenced)
    return problems, orphans


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="evidence module")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("job"); f.add_argument("url"); f.add_argument("--handoff", required=True)
    f.add_argument("--title")
    r = sub.add_parser("register"); r.add_argument("job"); r.add_argument("path"); r.add_argument("--title")
    for name in ("list", "refetch"):
        sub.add_parser(name).add_argument("job")
    c = sub.add_parser("check"); c.add_argument("job"); c.add_argument("artifact", nargs="?")
    s = sub.add_parser("show"); s.add_argument("job"); s.add_argument("source")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "fetch":
            e = fetch(a.job, a.url, a.handoff, a.title)
            print(f"{e['id']} {e['status']} rank {e['rank']}: {e.get('final_url') or e.get('path')}"
                  + (f" ({e['reason']})" if e.get("reason") else ""))
        elif a.cmd == "register":
            e = register(a.job, a.path, a.title)
            print(f"{e['id']} {e['status']} rank {e['rank']}: {e['path']}" + (f" ({e['reason']})" if e.get("reason") else ""))
        elif a.cmd == "list":
            for e in load_registry(a.job)["sources"]:
                print(f"{e['id']}  {e['status']:<11} rank {e['rank']}  {e.get('final_url') or e.get('path')}  {e['title'][:60]}")
        elif a.cmd == "refetch":
            for sid, what in refetch(a.job):
                print(f"{sid}: {what}")
        elif a.cmd == "check":
            art = a.artifact or lc.load_state(a.job)["artifact_path"]
            problems, uncited, _ = check(a.job, art)
            for p in problems:
                print(f"{p['rule']}  {p['location']}  {p['issue']}")
            print(f"{len(uncited)} uncited sentence(s) listed for the Verifier")
            print("evidence OK" if not problems else f"{len(problems)} problem(s)")
            return 1 if problems else 0
        elif a.cmd == "show":
            e = next((x for x in load_registry(a.job)["sources"] if x["id"] == a.source), None)
            if e is None:
                print(f"no source {a.source}", file=sys.stderr); return 1
            print(json.dumps(e, indent=2))
            print(f"stored copy: {lc.rel(cache_dir(a.job) / (e['sha256'] + '.txt'))}")
    except lc.LabError as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return ex.code
    return 0


if __name__ == "__main__":
    sys.exit(main())
