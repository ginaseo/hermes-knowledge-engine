import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from processor import log as _log
from processor.cleaner import Cleaner
from processor.entity_processor import EntityProcessor
from processor.keyword_processor import KeywordProcessor
from processor.markdown_processor import MarkdownProcessor
from processor.related_processor import RelatedProcessor
from processor.summary_processor import SummaryProcessor
from processor.validator import Validator
from processor.vault_indexer import VaultIndexer
from processor.wiki_processor import WikiProcessor

_log.setup()
logger = _log.get_logger(__name__)

# entity / keyword / related share no inter-dependency — safe to run concurrently
_PARALLEL_GROUP = {"entity", "keyword", "related"}
_SUBCOMMANDS = frozenset(
    {
        "run",
        "watch",
        "validate",
        "clean",
        "benchmark",
        "daemon",
        "history",
        "evaluate",
        "benchmark-retrieval",
    }
)


class ProcessorRunner:

    def __init__(self):
        raw = [arg.lower() for arg in sys.argv[1:]]

        # Extract subcommand if the first positional arg is a known subcommand
        self.subcommand = "run"
        args = list(raw)
        if args and args[0] in _SUBCOMMANDS:
            self.subcommand = args.pop(0)

        self.force = "--force" in args
        self.parallel = "--parallel" in args
        self.watch, self.watch_interval = self._parse_watch(args)
        self.log_level = self._parse_flag(args, "--log-level", "INFO")
        self.log_file_path = self._parse_flag(args, "--log-file", None)
        self.last_n = int(self._parse_flag(args, "--last", "20") or 20)
        self.targets = {arg for arg in args if not arg.startswith("--")}

        # Reconfigure logging now that CLI options are known
        _log.setup(
            level=self.log_level,
            log_file=Path(self.log_file_path) if self.log_file_path else None,
        )

        self.processors = [
            ("markdown", MarkdownProcessor()),
            ("wiki", WikiProcessor()),
            ("summary", SummaryProcessor()),
            ("entity", EntityProcessor()),
            ("keyword", KeywordProcessor()),
            ("related", RelatedProcessor()),
            ("cleaner", Cleaner()),
            ("index", VaultIndexer()),
            ("validator", Validator()),
        ]

    @staticmethod
    def _parse_watch(args: list[str], default: int = 30) -> tuple[bool, int]:
        """Parse --watch and --watch=N flags. Returns (enabled, interval_seconds)."""
        for arg in args:
            if arg == "--watch":
                return True, default
            if arg.startswith("--watch="):
                try:
                    return True, max(1, int(arg.split("=", 1)[1]))
                except ValueError:
                    return True, default
        return False, default

    @staticmethod
    def _parse_flag(args: list[str], prefix: str, default: str | None) -> str | None:
        """Extract value from --key=value style arg."""
        for arg in args:
            if arg.startswith(f"{prefix}="):
                return arg.split("=", 1)[1]
        return default

    def run(self) -> None:
        cmd = self.subcommand
        if cmd == "watch" or self.watch:
            self._watch()
        elif cmd == "validate":
            Validator().process()
        elif cmd == "clean":
            Cleaner().process()
        elif cmd == "benchmark":
            self._benchmark()
        elif cmd == "daemon":
            from processor.daemon import run_daemon

            run_daemon()
        elif cmd == "history":
            from processor.history import JobHistory

            JobHistory().display(n=self.last_n)
        elif cmd == "evaluate":
            from processor.evaluator import Evaluator

            Evaluator().run()
        elif cmd == "benchmark-retrieval":
            from processor.retrieval import RetrievalBenchmark

            RetrievalBenchmark().run()
        else:  # "run" or default
            self._run_once()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_once(self) -> None:
        start = time.perf_counter()

        logger.info("=" * 50)
        logger.info(" Processor Runner Start")
        logger.info("=" * 50)

        pending = self._filter_targets()
        failed = self._run_parallel(pending) if self.parallel else self._run_sequential(pending)

        logger.info("")
        if failed:
            logger.info("Failed Processors")
            for name in failed:
                logger.info(f"- {name}")
        else:
            logger.info("[PASS] All processors completed.")

        total = time.perf_counter() - start
        logger.info("=" * 50)
        logger.info(" Processor Runner Finished")
        logger.info("=" * 50)
        logger.info("")
        logger.info(f"Elapsed : {total:.2f} sec")

    def _filter_targets(self) -> list[tuple[str, object]]:
        if not self.targets:
            return list(self.processors)
        return [(n, p) for n, p in self.processors if n in self.targets]

    def _run_sequential(self, pending: list) -> list[str]:
        failed: list[str] = []
        for name, processor in pending:
            logger.info("")
            logger.info(f"Running : {processor.__class__.__name__}")
            started = time.perf_counter()
            try:
                if hasattr(processor, "force"):
                    processor.force = self.force
                processor.process()
                logger.info(f"[TIME] {time.perf_counter() - started:.2f} sec")
            except Exception as e:
                failed.append(name)
                logger.error(f"[FAIL] {processor.__class__.__name__}")
                logger.error(str(e))
        return failed

    def _run_parallel(self, pending: list) -> list[str]:
        """Pipeline is sequential; entity/keyword/related run concurrently.
        Each thread's log output is buffered and flushed in original order
        to prevent interleaved console output.
        """
        failed: list[str] = []
        parallel_batch: list[tuple[str, object]] = []

        def flush_batch() -> None:
            if not parallel_batch:
                return
            names = ", ".join(n for n, _ in parallel_batch)
            logger.info("")
            logger.info(f"Running parallel: {names}")
            started = time.perf_counter()

            with ThreadPoolExecutor() as pool:
                # Submit each processor with a thread-local capture buffer
                futures = {
                    pool.submit(_log.capture, p.process): (i, n)
                    for i, (n, p) in enumerate(parallel_batch)
                }
                results: dict[int, str] = {}
                for future in as_completed(futures):
                    idx, proc_name = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        failed.append(proc_name)
                        results[idx] = f"[FAIL] {proc_name}: {e}\n"

            # Print captured output in original processor order (no interleaving)
            for i in sorted(results):
                sys.stdout.write(results[i])
            sys.stdout.flush()

            logger.info(f"[TIME] parallel group {time.perf_counter() - started:.2f} sec")
            parallel_batch.clear()

        for name, processor in pending:
            if hasattr(processor, "force"):
                processor.force = self.force

            if name in _PARALLEL_GROUP:
                parallel_batch.append((name, processor))
                continue

            flush_batch()

            logger.info("")
            logger.info(f"Running : {processor.__class__.__name__}")
            started = time.perf_counter()
            try:
                processor.process()
                logger.info(f"[TIME] {time.perf_counter() - started:.2f} sec")
            except Exception as e:
                failed.append(name)
                logger.error(f"[FAIL] {processor.__class__.__name__}")
                logger.error(str(e))

        flush_batch()
        return failed

    def _watch(self) -> None:
        interval = self.watch_interval
        logger.info(f"[WATCH] Polling every {interval}s. Ctrl+C to stop.")
        try:
            while True:
                logger.info("")
                logger.info(f"[WATCH] {time.strftime('%H:%M:%S')}")
                try:
                    self._run_once()
                except Exception as e:
                    logger.error(f"[WATCH] Run error: {e}")
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("")
            logger.info("[WATCH] Stopped.")

    def _benchmark(self) -> None:
        logger.info("=" * 50)
        logger.info(" Benchmark Mode")
        logger.info("=" * 50)

        pending = self._filter_targets()
        results: list[tuple[str, float, str]] = []

        for name, processor in pending:
            if hasattr(processor, "force"):
                processor.force = self.force
            started = time.perf_counter()
            status = "OK"
            try:
                processor.process()
            except Exception as e:
                status = "FAIL"
                logger.error(f"[FAIL] {name}: {e}")
            elapsed = time.perf_counter() - started
            results.append((name, elapsed, status))

        logger.info("")
        logger.info("=" * 50)
        logger.info(" Benchmark Report")
        logger.info("=" * 50)
        logger.info(f"  {'Processor':<14}  {'Time':>8}  Status")
        logger.info(f"  {'-' * 14}  {'-' * 8}  ------")
        for name, elapsed, status in results:
            logger.info(f"  {name:<14}  {elapsed:>7.2f}s  {status}")
        total = sum(e for _, e, _ in results)
        logger.info(f"  {'-' * 14}  {'-' * 8}")
        logger.info(f"  {'TOTAL':<14}  {total:>7.2f}s")


def main() -> None:
    """Entry point for `hermes` CLI command."""
    ProcessorRunner().run()


if __name__ == "__main__":
    main()
