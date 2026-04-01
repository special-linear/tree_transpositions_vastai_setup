import time, os, uuid, requests
from pathlib import Path
from cayleypy import CayleyGraph, CayleyGraphDef
from cayleypy.permutation_utils import transposition
import networkx as nx

# TASK ACQUISITION AND REPORTING

BROKER_URL = os.environ.get('BROKER_URL')
if not BROKER_URL:
    rint("Missing BROKER_URL env var; check Vast template/account env vars.", flush=True)
    sys.exit(2)

BROKER_KEY = os.environ.get('BROKER_KEY')
if not BROKER_KEY:
    rint("Missing BROKER_KEY env var; check Vast template/account env vars.", flush=True)
    sys.exit(2)

WORKER = "Kaggle"
RUN_ID = str(uuid.uuid4())[:8]

STATE_DIR = Path(os.environ.get("STATE_DIR", "/workspace/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Network protection knobs
HTTP_TIMEOUT = (10, 180)         # (connect_timeout, read_timeout) in seconds
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "6"))
BACKOFF_BASE = float(os.environ.get("BACKOFF_BASE", "1.5"))
BACKOFF_CAP = float(os.environ.get("BACKOFF_CAP", "60"))

PENDING_PATH = STATE_DIR / "pending_submit.jsonl"

sess = requests.Session()
sess.headers.update({"User-Agent": f"kaggle-worker/{WORKER}/{RUN_ID}"})


def request_json(method: str, url: str, *, params=None, body=None, timeout=HTTP_TIMEOUT,
                 max_retries=MAX_RETRIES, retry_statuses=(429, 500, 502, 503, 504)):
    """
    Make an HTTP request returning parsed JSON, with retries/backoff on:
      - timeouts
      - transient connection errors
      - HTTP 429/5xx

    NOTE: Retrying a CLAIM request can (rarely) double-lease tasks if the first
    attempt succeeded server-side but the response was lost. If that matters a lot,
    keep leases shorter and/or add idempotency support on the Apps Script side.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            r = sess.request(method, url, params=params, json=body, timeout=timeout)
            r.raise_for_status()
            return r.json()

        except (ReadTimeout, ConnectTimeout, ConnectionError) as e:
            last_err = e
            # exponential backoff + jitter
            sleep = min(BACKOFF_CAP, (BACKOFF_BASE ** attempt)) + random.random()
            print(f"[HTTP] {method} timeout/conn error: {e}. Retry {attempt+1}/{max_retries} in {sleep:.1f}s")
            time.sleep(sleep)
            continue

        except HTTPError as e:
            last_err = e
            code = e.response.status_code if e.response is not None else None
            if code in retry_statuses and attempt < max_retries - 1:
                sleep = min(BACKOFF_CAP, (BACKOFF_BASE ** attempt)) + random.random()
                print(f"[HTTP] {method} HTTP {code}. Retry {attempt+1}/{max_retries} in {sleep:.1f}s")
                time.sleep(sleep)
                continue
            # non-retriable HTTP error or retries exhausted
            raise

        except Exception as e:
            # unexpected (e.g. JSON parse error)
            last_err = e
            sleep = min(BACKOFF_CAP, (BACKOFF_BASE ** attempt)) + random.random()
            print(f"[HTTP] {method} unexpected error: {e}. Retry {attempt+1}/{max_retries} in {sleep:.1f}s")
            time.sleep(sleep)
            continue

    raise RuntimeError(f"HTTP request failed after {max_retries} retries: {last_err}")


def claim(n: int, lease_min: int):
    data = request_json(
        "GET",
        BROKER_URL,
        params={
            "action": "claim",
            "key": BROKER_KEY,
            "worker": WORKER,
            "n": int(n),
            "lease_min": int(lease_min),
        },
    )
    if not data.get("ok", False):
        raise RuntimeError(f"claim failed: {data}")
    return data.get("tasks", [])


def submit_items(items):
    if not items:
        return {"ok": True, "updated": 0}

    data = request_json(
        "POST",
        BROKER_URL,
        params={"key": BROKER_KEY},
        body={
            "action": "submit",
            "key": BROKER_KEY,
            "worker": WORKER,
            "items": items,
        },
    )
    if not data.get("ok", False):
        raise RuntimeError(f"submit failed: {data}")
    return data


def append_pending(items):
    if not items:
        return
    with open(PENDING_PATH, "a", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def load_pending(max_items=None):
    if not os.path.exists(PENDING_PATH):
        return []
    items = []
    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
            if max_items is not None and len(items) >= max_items:
                break
    return items


def rewrite_pending(remaining_items):
    if not remaining_items:
        if os.path.exists(PENDING_PATH):
            os.remove(PENDING_PATH)
        return
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        for it in remaining_items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def flush_pending(batch_size=200):
    """
    Try to submit pending items in chunks. If submit fails, keep them.
    Returns number of items successfully flushed.
    """
    pending = load_pending(max_items=None)
    if not pending:
        return 0

    flushed = 0
    idx = 0
    while idx < len(pending):
        chunk = pending[idx: idx + batch_size]
        try:
            resp = submit_items(chunk)
            flushed += len(chunk)
            idx += len(chunk)
            print(f"[flush_pending] Submitted {len(chunk)} pending -> {resp}")
        except Exception as e:
            # keep remaining (including current chunk) for later
            print(f"[flush_pending] Submit failed, keeping {len(pending) - idx} pending. Error: {e}")
            rewrite_pending(pending[idx:])
            return flushed

    # all flushed
    rewrite_pending([])
    return flushed


# GRAPHS PROCESSING

def _parse_any6_to_nx(code: str) -> nx.Graph:
    b = code.encode("ascii")
    if code.startswith(":"):                   # sparse6
        return nx.from_sparse6_bytes(b)
    return nx.from_graph6_bytes(b)


def tree_transpositions(code: str) -> CayleyGraphDef:
    graph = _parse_any6_to_nx(code)
    n = graph.number_of_nodes()
    generators = [transposition(n, i, j) for i, j in graph.edges()]
    generator_names = [f't({i},{j})' for i, j in graph.edges()]
    name = f"tree_transpositions-{code}"
    return CayleyGraphDef.create(
        generators,
        central_state=list(range(n)),
        generator_names=generator_names,
        name=name,
    )


def tree_cayley_diameter(code: str):
    bfs_result = None
    cg_def = tree_transpositions(code)
    cg = CayleyGraph(cg_def)
    bfs_result = cg.bfs()
    return bfs_result.diameter()


# EXECUTION

def main():
    CLAIM_N = 1
    LEASE_MIN = 120
    TIME_LIMIT_SECONDS = 2 * 60 * 60  # e.g. 2 hours
    SAFETY_SECONDS = 300  # stop early to ensure final submit

    SUBMIT_EVERY = 1  # submit in chunks to avoid losing work
    EMPTY_QUEUE_SLEEP = 30  # seconds
    MAX_EMPTY_CLAIMS = 3  # how many empty claims before exiting

    deadline = t0 + TIME_LIMIT_SECONDS - SAFETY_SECONDS

    total_claimed = 0
    total_done = 0
    total_failed = 0
    empty_claims = 0

    while time.time() < deadline:
        # Always try to flush pending before claiming new work
        flush_pending()

        # (1) claim with protection (catch errors and continue)
        try:
            tasks = claim(CLAIM_N, (deadline - time.time() + 2 * SAFETY_SECONDS) // 60)
        except Exception as e:
            # Don't crash; backoff and retry later
            sleep = min(BACKOFF_CAP, 5 + random.random() * 5)
            print(f"[claim] failed: {e}. Sleeping {sleep:.1f}s then retrying...")
            time.sleep(sleep)
            continue

        if not tasks:
            empty_claims += 1
            print(
                f"No tasks available (empty_claims={empty_claims}/{MAX_EMPTY_CLAIMS}). Sleeping {EMPTY_QUEUE_SLEEP}s...")
            if empty_claims >= MAX_EMPTY_CLAIMS:
                break
            time.sleep(EMPTY_QUEUE_SLEEP)
            continue

        empty_claims = 0
        total_claimed += len(tasks)
        print(f"Claimed {len(tasks)} tasks (total_claimed={total_claimed}).")

        buffer = []
        for t in tasks:
            if time.time() >= deadline:
                print("Near deadline; stopping compute to ensure final submit.")
                break

            tid = str(t.get("id"))
            g6 = t.get("graph6", "")

            try:
                d = tree_cayley_diameter(g6)
                print(f'G={g6} diam={d}')
                buffer.append({"id": tid, "diameter": int(d)})
                total_done += 1
            except Exception as e:
                print(f'Calculation failed: {e}')
                buffer.append({"id": tid, "status": "failed"})
                total_failed += 1

            # Submit in chunks; on submit failure, persist to pending and continue
            if len(buffer) >= min(SUBMIT_EVERY, CLAIM_N):
                try:
                    resp = submit_items(buffer)
                    print(f"Submitted {len(buffer)} items -> {resp}")
                    buffer.clear()
                except Exception as e:
                    print(f"[submit] failed: {e}. Saving {len(buffer)} items to pending.")
                    append_pending(buffer)
                    buffer.clear()
                    # back off a bit
                    time.sleep(2 + random.random() * 3)

        # submit remaining for this batch
        if buffer:
            try:
                resp = submit_items(buffer)
                print(f"Submitted {len(buffer)} items -> {resp}")
                buffer.clear()
            except Exception as e:
                print(f"[submit] failed: {e}. Saving {len(buffer)} items to pending.")
                append_pending(buffer)
                buffer.clear()

    # Final flush attempt
    flush_pending()

    print(
        f"[{WORKER}/{RUN_ID}] Done. claimed={total_claimed}, done={total_done}, failed={total_failed}, elapsed={time.time() - t0:.1f}s")


if __name__ == '__main__':
    main()