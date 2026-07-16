"""KRX stock data provider — reads briefing_data.json and kospi200_screen.json."""

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ingest.base import BaseProvider

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "HermesVault"

load_dotenv(ROOT / ".env")

_DEFAULT_SOURCE = r"C:\CompWork\krx-brief\results"
KRX_SOURCE = Path(os.getenv("KRX_RESULTS_DIR", _DEFAULT_SOURCE))


class KRXProvider(BaseProvider):

    def connect(self):
        pass  # local files

    def fetch(self):
        briefing_file = KRX_SOURCE / "briefing_data.json"
        screen_file = KRX_SOURCE / "kospi200_screen.json"

        if not briefing_file.exists() and not screen_file.exists():
            print(f"[KRX] No files found in {KRX_SOURCE}")
            return None

        results = {}
        if briefing_file.exists():
            results["briefing"] = json.loads(briefing_file.read_text(encoding="utf-8"))
        if screen_file.exists():
            results["screen"] = json.loads(screen_file.read_text(encoding="utf-8"))
        return results

    def save(self, data):
        out_dir = VAULT / "knowledge" / "slack"
        out_dir.mkdir(parents=True, exist_ok=True)

        generated = (data.get("briefing") or data.get("screen") or {}).get("generated", "")
        date_str = generated[:10] if generated else datetime.now().strftime("%Y-%m-%d")

        if "briefing" in data:
            path = out_dir / f"{date_str}-krx-briefing.md"
            if not path.exists():
                path.write_text(self._fmt_briefing(data["briefing"], date_str), encoding="utf-8")
                print(f"[KRX] Saved {path.name}")
            else:
                print(f"[KRX] Already exists: {path.name}")

        if "screen" in data:
            path = out_dir / f"{date_str}-krx-screen.md"
            if not path.exists():
                path.write_text(self._fmt_screen(data["screen"], date_str), encoding="utf-8")
                print(f"[KRX] Saved {path.name}")
            else:
                print(f"[KRX] Already exists: {path.name}")

    def process(self):
        self.run()

    def _fmt_briefing(self, data: dict, date: str) -> str:
        lines = [f"# KRX Portfolio Briefing -- {date}\n"]

        indices = data.get("indices", {})
        if indices:
            lines.append("## 시장 지수\n")
            for name, info in indices.items():
                pct = info.get("pct", 0)
                sign = "+" if pct >= 0 else ""
                lines.append(f"- **{name}**: {info.get('current')} ({sign}{pct}%)")
            lines.append("")

        holdings = data.get("holdings", [])
        if holdings:
            lines.append("## 포트폴리오 현황\n")
            for h in holdings:
                name = h.get("name", "")
                current = h.get("current", "N/A")
                pct = h.get("pct", 0)
                ret = h.get("return_pct", 0)
                pnl = h.get("pnl_krw") or h.get("pnl", 0)
                sign = "+" if pct >= 0 else ""
                ret_sign = "+" if ret >= 0 else ""

                lines.append(f"### {name}")
                lines.append(f"- 현재가: {current:,} | 등락: {sign}{pct}%")
                lines.append(f"- 수익률: {ret_sign}{ret}% | 손익: {pnl:,}")
                if h.get("rsi14"):
                    lines.append(
                        f"- RSI14: {h['rsi14']}"
                        f" | MA5: {h.get('ma5', 'N/A'):,}"
                        f" | MA20: {h.get('ma20', 'N/A'):,}"
                    )
                lines.append("")

        return "\n".join(lines)

    def _fmt_screen(self, data: dict, date: str) -> str:
        lines = [f"# KOSPI200 스크리닝 -- {date}\n"]

        macro = data.get("macro", {})
        if macro:
            lines.append("## 매크로\n")
            us10y = macro.get("us10y", {})
            usdkrw = macro.get("usdkrw", {})
            lines.append(f"- 미국 10년물: {us10y.get('latest_pct')}% ({us10y.get('chg_bp')}bp)")
            lines.append(f"- 달러/원: {usdkrw.get('latest')} ({usdkrw.get('chg_pct')}%)")
            kospi = macro.get("kospi", {})
            if kospi:
                lines.append(f"- KOSPI: {kospi.get('close')} ({kospi.get('chg_pct')}%)")
            lines.append("")

        recs = data.get("recommendations", [])
        if recs:
            lines.append("## 추천 종목\n")
            for r in recs:
                name = r.get("name", "")
                held = " [보유중]" if r.get("held") else ""
                thesis = r.get("thesis_status") or ""

                lines.append(f"### {name} ({r.get('code')}){held}")
                lines.append(
                    f"- 섹터: {r.get('sector')} | 스코어: {r.get('score')}"
                    f" | 모멘텀: {r.get('momentum_pct')}%"
                )

                tech = r.get("technical") or {}
                if tech:
                    lines.append(
                        f"- RSI14: {tech.get('rsi14')}"
                        f" | MA20 위: {tech.get('above_ma20')}"
                        f" | MA200 대비: {tech.get('vs_ma200_pct')}%"
                    )

                fund = r.get("fundamentals_dart") or {}
                if fund:
                    lines.append(
                        f"- PER: {r.get('PER')} | PBR: {r.get('PBR')}"
                        f" | ROE: {fund.get('roe_pct')}%"
                        f" | 부채비율: {fund.get('debt_ratio_pct')}%"
                    )

                if thesis:
                    lines.append(f"- 투자의견: {thesis}")

                disc = r.get("disclosure") or {}
                if disc.get("hard_negative"):
                    nm = disc["hard_negative"][0].get("report_nm", "").strip()
                    lines.append(f"- [강한 악재] {nm}")
                if disc.get("soft_negative"):
                    nm = disc["soft_negative"][0].get("report_nm", "").strip()
                    lines.append(f"- [공시] {nm}")

                lines.append("")

        return "\n".join(lines)
