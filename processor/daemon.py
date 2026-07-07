"""Hermes Daemon — continuously scheduled job runner.

Reads HermesVault/config/schedule.yaml. Runs processors on their configured
interval. Retries with exponential backoff. Reloads schedule on file change.
Graceful Ctrl+C shutdown. Failed jobs are logged and do not stop the daemon.
"""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from processor.history import JobHistory, JobRecord
from processor.log import get_logger

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE_FILE = ROOT / "HermesVault" / "config" / "schedule.yaml"

_TICK = 10  # seconds between scheduling checks

_DEFAULT_SCHEDULE = """\
jobs:
  slack:
    every: 5m
  krx:
    every: 5m
  markdown:
    every: 5m
  wiki:
    every: 5m
  summary:
    every: 10m
  entity:
    every: 10m
  keyword:
    every: 10m
  related:
    every: 10m
  cleaner:
    every: day
  validator:
    every: sunday
  index:
    every: hour

retry:
  count: 3
  delay: 30s
  backoff: exponential
"""

_PROCESSOR_MAP: dict[str, str] = {
    "slack": "ingest.providers.slack.SlackProvider",
    "krx": "ingest.providers.krx.KRXProvider",
    "markdown": "processor.markdown_processor.MarkdownProcessor",
    "wiki": "processor.wiki_processor.WikiProcessor",
    "summary": "processor.summary_processor.SummaryProcessor",
    "entity": "processor.entity_processor.EntityProcessor",
    "keyword": "processor.keyword_processor.KeywordProcessor",
    "related": "processor.related_processor.RelatedProcessor",
    "cleaner": "processor.cleaner.Cleaner",
    "cleanup": "processor.cleaner.Cleaner",
    "index": "processor.vault_indexer.VaultIndexer",
    "validator": "processor.validator.Validator",
    "validate": "processor.validator.Validator",
}


def _parse_interval(value: str) -> int:
    """Parse interval string to seconds. Supports: 5m 2h 1d hour day sunday 30s."""
    v = str(value).strip().lower()
    if v == "hour":
        return 3600
    if v == "day":
        return 86400
    if v == "sunday":
        return 7 * 86400
    if v.endswith("m"):
        return int(v[:-1]) * 60
    if v.endswith("h"):
        return int(v[:-1]) * 3600
    if v.endswith("s"):
        return int(v[:-1])
    if v.endswith("d"):
        return int(v[:-1]) * 86400
    return int(v)


_MAX_RETRY_WAIT = 600  # cap so a misconfigured schedule.yaml can't stall the daemon


@dataclass
class RetryPolicy:
    count: int = 3
    delay: int = 30  # base delay seconds
    backoff: str = "exponential"

    def wait_for(self, attempt: int) -> float:
        if self.backoff == "exponential":
            wait = self.delay * (2**attempt)
        elif self.backoff == "linear":
            wait = self.delay * (attempt + 1)
        else:
            wait = float(self.delay)
        return min(wait, _MAX_RETRY_WAIT)


@dataclass
class JobSpec:
    name: str
    interval: int  # seconds
    next_run: float = 0.0


@dataclass
class Schedule:
    jobs: list[JobSpec] = field(default_factory=list)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    mtime: float = 0.0


def _load_schedule() -> Schedule:
    try:
        import yaml
    except ImportError:
        raise ImportError("pyyaml is required for daemon mode.\n" "Install: pip install pyyaml")

    if not SCHEDULE_FILE.exists():
        SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_FILE.write_text(_DEFAULT_SCHEDULE, encoding="utf-8")
        logger.info(f"[DAEMON] Created default schedule: {SCHEDULE_FILE}")

    raw = yaml.safe_load(SCHEDULE_FILE.read_text(encoding="utf-8")) or {}
    retry_raw = raw.get("retry") or {}
    retry = RetryPolicy(
        count=int(retry_raw.get("count", 3)),
        delay=_parse_interval(str(retry_raw.get("delay", "30s"))),
        backoff=str(retry_raw.get("backoff", "exponential")),
    )

    jobs: list[JobSpec] = []
    for name, cfg in (raw.get("jobs") or {}).items():
        cfg = cfg or {}
        interval = _parse_interval(cfg.get("every", "1h"))
        jobs.append(JobSpec(name=str(name), interval=interval))

    return Schedule(
        jobs=jobs,
        retry=retry,
        mtime=SCHEDULE_FILE.stat().st_mtime,
    )


def _make_processor(name: str):
    dotpath = _PROCESSOR_MAP.get(name.lower())
    if dotpath is None:
        raise ValueError(f"Unknown processor: {name!r}. Valid: {sorted(_PROCESSOR_MAP)}")
    module_path, cls_name = dotpath.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)()


def _run_job(job: JobSpec, retry: RetryPolicy, history: JobHistory) -> None:
    logger.info(f"[DAEMON] Job start: {job.name}")
    start = time.perf_counter()
    start_ts = JobRecord.now()
    exc_msg: str | None = None
    status = "ok"
    attempts = 0

    for attempt in range(max(1, retry.count)):
        attempts = attempt
        try:
            p = _make_processor(job.name)
            p.process()
            break
        except Exception as e:
            exc_msg = str(e)
            if attempt < retry.count - 1:
                wait = retry.wait_for(attempt)
                logger.warning(
                    f"[DAEMON] {job.name} attempt {attempt + 1} failed: {e}"
                    f" -- retry in {wait:.0f}s"
                )
                time.sleep(wait)
            else:
                status = "fail"
                logger.error(f"[DAEMON] {job.name} failed after {retry.count} attempt(s): {e}")

    elapsed = time.perf_counter() - start
    history.append(
        JobRecord(
            name=job.name,
            start_time=start_ts,
            finish_time=JobRecord.now(),
            duration=round(elapsed, 3),
            status=status,
            exception=exc_msg if status == "fail" else None,
            retry_count=attempts,
        )
    )
    if status == "ok":
        logger.info(f"[DAEMON] Job done: {job.name} ({elapsed:.2f}s)")


def run_daemon() -> None:
    logger.info("[DAEMON] Starting. Press Ctrl+C to stop.")
    logger.info(f"[DAEMON] Schedule: {SCHEDULE_FILE}")

    schedule = _load_schedule()
    history = JobHistory()
    now = time.time()

    # Run all jobs immediately on first start
    for job in schedule.jobs:
        job.next_run = now

    logger.info(f"[DAEMON] {len(schedule.jobs)} job(s) loaded:")
    for job in schedule.jobs:
        logger.info(f"  {job.name:<14} every {job.interval}s")

    try:
        while True:
            now = time.time()

            # Reload schedule.yaml if modified
            if SCHEDULE_FILE.exists():
                mtime = SCHEDULE_FILE.stat().st_mtime
                if mtime != schedule.mtime:
                    logger.info("[DAEMON] Schedule changed -- reloading.")
                    prev_next = {j.name: j.next_run for j in schedule.jobs}
                    schedule = _load_schedule()
                    for job in schedule.jobs:
                        job.next_run = prev_next.get(job.name, now)

            # Run due jobs (sequential to avoid resource contention)
            for job in schedule.jobs:
                if now >= job.next_run:
                    _run_job(job, schedule.retry, history)
                    job.next_run = time.time() + job.interval

            time.sleep(_TICK)

    except KeyboardInterrupt:
        logger.info("")
        logger.info("[DAEMON] Stopped.")
