#!/usr/bin/env python3
"""Daemon dos residentes do Habblaud.

Mantém a presença fixa de cada residente no escritório (eventos de hook do Codex via
POST /api/codex/events, com heartbeat < HOOK_PRESENCE_MS=60s) e executa tarefas de
verdade com `claude -p`, reportando o progresso (PreToolUse por ferramenta usada).
Tarefas chegam por arquivos em <state>/spool (veja o script `residentes`).
"""
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

CONFIG_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.habblaud/residentes.json")
STATE_DIR = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "~/.habblaud/residentes.d").expanduser()
SPOOL = STATE_DIR / "spool"
LOG_DIR = STATE_DIR
HEARTBEAT_S = 25.0          # < HOOK_PRESENCE_MS (60s) do Habblaud
POLL_S = 1.0

HEARTBEAT_LOCK = threading.Lock()
SESSIONS = {}               # id -> session uuid (estável enquanto o daemon vive)
BUSY = set()                # ids executando tarefa agora
JOBS = {}                   # id -> descrição curta do estado


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def cfg():
    try:
        return json.loads(pathlib.Path(CONFIG_PATH).expanduser().read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:
        log(f"config inválida: {e}")
        return {}


def slug(s):
    s = re.sub(r"[^\w\s-]", "", s.strip(), flags=re.UNICODE).strip()
    return re.sub(r"[\s-]+", "-", s).lower() or "sala"


def expand(p):
    return os.path.expanduser(p)


def send(base, account, event):
    body = json.dumps({"account": account, "event": event}).encode()
    req = urllib.request.Request(f"{base}/api/codex/events", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode()).get("ok") is True
    except Exception as e:
        log(f"falar com o Habblaud falhou: {e}")
        return False


def session_of(r, base, account, start=True):
    rid = r["id"]
    if rid not in SESSIONS:
        SESSIONS[rid] = str(uuid.uuid4())
        if start:
            send(base, account, {"hook_event_name": "SessionStart",
                                 "session_id": SESSIONS[rid], "cwd": room_cwd(r)})
    return SESSIONS[rid]


def room_cwd(r):
    return f"/escritorio/salas/{slug(r.get('sala') or r['id'])}"


def heartbeat_all(base, account, residents):
    with HEARTBEAT_LOCK:
        for r in residents:
            sid = session_of(r, base, account)
            send(base, account, {"hook_event_name": "Stop", "session_id": sid})


def run_task(r, task, base, account):
    rid = r["id"]
    sid = session_of(r, base, account)
    room = room_cwd(r)
    work = expand(r.get("cwd") or "~")
    BUSY.add(rid)
    JOBS[rid] = f"trabalhando: {task[:60]}"
    log(f"{rid}: tarefa iniciada em {work}: {task[:80]}")
    send(base, account, {"hook_event_name": "UserPromptSubmit", "session_id": sid,
                         "cwd": room, "prompt": task[:300]})
    logfile = open(LOG_DIR / f"log-{rid}.log", "a")
    logfile.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} — {task}\n")
    system = "\n".join(p for p in [r.get("prompt"), f"Papel: {r['papel']}" if r.get("papel") else None] if p)
    cmd = ["claude", "-p", task, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions" if r.get("permissivo", True) else "default"]
    if system:
        cmd += ["--append-system-prompt", system]
    if r.get("memoria", True):
        cmd += ["--continue"]
    try:
        proc = subprocess.Popen(cmd, cwd=work, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            logfile.write(line)
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        label = block.get("name", "ferramenta")
                        inp = block.get("input") or {}
                        detail = inp.get("description") or inp.get("command") or inp.get("file_path") or ""
                        send(base, account, {"hook_event_name": "PreToolUse", "session_id": sid,
                                             "cwd": room, "tool_name": f"{label}: {detail}"[:120],
                                             "tool_input": {}})
        proc.wait()
        ok = proc.returncode == 0
        JOBS[rid] = "ocioso"
        log(f"{rid}: tarefa {'concluída' if ok else 'falhou (exit ' + str(proc.returncode) + ')'}")
        logfile.write(f"----- exit {proc.returncode}\n")
    except FileNotFoundError:
        JOBS[rid] = "erro: claude não encontrado"
        log(f"{rid}: comando claude não está no PATH")
    finally:
        logfile.close()
        BUSY.discard(rid)
        send(base, account, {"hook_event_name": "Stop", "session_id": sid})


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SPOOL.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "daemon.pid").write_text(str(os.getpid()))
    running = True

    def bye(_sig, _frm):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    log("daemon dos residentes no ar")

    threads = []
    last_beat = 0.0
    prev_ids = set()
    while running:
        conf = cfg()
        base = conf.get("habblaud", "http://127.0.0.1:4747")
        account = conf.get("conta", ".codex-g4")
        residents = [r for r in conf.get("residentes", []) if r.get("id")]
        ids = {r["id"] for r in residents}

        # residentes novos -> chegam; removidos -> saem
        for r in residents:
            if r["id"] not in prev_ids:
                sid = session_of(r, base, account)
                JOBS.setdefault(r["id"], "ocioso")
                log(f"{r['id']} chegou na sala {r.get('sala') or r['id']}")
        for gone in prev_ids - ids:
            SESSIONS.pop(gone, None)
            JOBS.pop(gone, None)
            log(f"{gone} saiu do escritório")
        prev_ids = ids

        # heartbeat (presença fixa)
        if time.time() - last_beat >= HEARTBEAT_S:
            threading.Thread(target=heartbeat_all, args=(base, account, residents), daemon=True).start()
            last_beat = time.time()

        # fila de tarefas
        for f in sorted(SPOOL.glob("*.json")):
            try:
                job = json.loads(f.read_text())
            except Exception:
                f.unlink(missing_ok=True)
                continue
            f.unlink(missing_ok=True)
            r = next((x for x in residents if x["id"] == job.get("id")), None)
            if not r:
                log(f"tarefa para residente desconhecido: {job.get('id')}")
                continue
            if r["id"] in BUSY:
                log(f"{r['id']} já está ocupado; tarefa descartada (tente de novo)")
                continue
            t = threading.Thread(target=run_task, args=(r, job.get("task", ""), base, account), daemon=True)
            t.start()
            threads.append(t)

        (STATE_DIR / "jobs.json").write_text(json.dumps(JOBS, ensure_ascii=False, indent=1))
        time.sleep(POLL_S)

    # saída limpa: todos saem do escritório
    conf = cfg()
    base = conf.get("habblaud", "http://127.0.0.1:4747")
    account = conf.get("conta", ".codex-g4")
    for rid, sid in SESSIONS.items():
        send(base, account, {"hook_event_name": "SessionEnd", "session_id": sid})
    (STATE_DIR / "daemon.pid").unlink(missing_ok=True)
    log("daemon encerrado; residentes saíram do escritório")


if __name__ == "__main__":
    main()
