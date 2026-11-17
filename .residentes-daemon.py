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
import sys
import threading
import time
import urllib.request
import uuid

CONFIG_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.habblaud/residentes.json")
STATE_DIR = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "~/.habblaud/residentes.d").expanduser()
SPOOL = STATE_DIR / "spool"
EXEC = STATE_DIR / "exec"
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


def run_task(r, task, path):
    """Repassa a tarefa ao G4 OS: marca como na fila e deixa o arquivo para o executor
    (job 'Residentes — executor' dos Agendamentos) pegar. O daemon nunca executa nada."""
    rid = r["id"]
    BUSY.add(rid)
    JOBS[rid] = f"na fila do G4 OS: {task[:60]}"
    log(f"{rid}: tarefa na fila para o G4 OS: {task[:80]}")
    if path:
        try:
            EXEC.mkdir(parents=True, exist_ok=True)
            pathlib.Path(path).rename(EXEC / pathlib.Path(path).name)  # spool/ -> exec/
        except FileNotFoundError:
            pass  # já movida
    BUSY.discard(rid)


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SPOOL.mkdir(parents=True, exist_ok=True)
    EXEC.mkdir(parents=True, exist_ok=True)
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

        # tarefa já assumida pelo executor do G4 OS (sumiu de exec/) -> de volta a ocioso
        for rid, j in list(JOBS.items()):
            if j.startswith("na fila") and not list(EXEC.glob(f"*-{rid}.json")):
                JOBS[rid] = "ocioso"

        # fila de tarefas
        for f in sorted(SPOOL.glob("*.json")):
            try:
                job = json.loads(f.read_text())
            except Exception:
                continue  # arquivo ainda sendo escrito; tenta no próximo ciclo
            r = next((x for x in residents if x["id"] == job.get("id")), None)
            if not r:
                log(f"tarefa para residente desconhecido: {job.get('id')}")
                f.unlink(missing_ok=True)
                continue
            if any(t.name == f"task-{f.name}" for t in threads):
                continue  # já assumida por outra thread
            t = threading.Thread(target=run_task, args=(r, job.get("task", ""), str(f)), name=f"task-{f.name}", daemon=True)
            t.start()
            threads.append(t)

        # mapeamento id -> session_id para o executor do G4 OS
        (STATE_DIR / "sessions.json").write_text(
            json.dumps(SESSIONS, indent=1))

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
