import os
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd
import requests

from src.utils.config_loader import ConfigLoader
from src.utils.indicators import Indicators
from src.utils.tushare_provider import TushareProvider


TABLE_INTERVAL_MAP = {
    "dat_1mins": "1min",
    "dat_5mins": "5min",
    "dat_10mins": "10min",
    "dat_15mins": "15min",
    "dat_30mins": "30min",
    "dat_60mins": "60min",
    "dat_days": "D",
}


class HistoryDiffSyncService:
    def __init__(self):
        self._run_lock = threading.Lock()
        self._is_running = False
        self._last_report: dict[str, Any] = {}

    def get_status(self) -> dict[str, Any]:
        return {
            "is_running": self._is_running,
            "last_report": self._last_report,
        }

    def run_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._run_lock.acquire(blocking=False):
            return {"status": "busy", "msg": "sync task is already running", "report": self._last_report}
        self._is_running = True
        started_at = datetime.now()
        try:
            report = self._run_sync_impl(payload or {})
            report["started_at"] = started_at.isoformat(timespec="seconds")
            report["finished_at"] = datetime.now().isoformat(timespec="seconds")
            self._last_report = report
            return {"status": "success", "report": report}
        except Exception as e:
            report = {
                "status": "failed",
                "error": str(e),
                "started_at": started_at.isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._last_report = report
            return {"status": "error", "msg": str(e), "report": report}
        finally:
            self._is_running = False
            self._run_lock.release()

    def _run_sync_impl(self, payload: dict[str, Any]) -> dict[str, Any]:
        cfg = ConfigLoader.reload()
        history_base_url = str(cfg.get("data_provider.default_api_url", "") or "").strip().rstrip("/")
        history_api_key = str(cfg.get("data_provider.default_api_key", "") or "").strip()
        tushare_token = str(cfg.get("data_provider.tushare_token", "") or "").strip()
        if not history_base_url:
            raise RuntimeError("missing data_provider.default_api_url")
        if not history_api_key:
            raise RuntimeError("missing data_provider.default_api_key")
        if not tushare_token:
            raise RuntimeError("missing data_provider.tushare_token")

        lookback_days = int(payload.get("lookback_days", 10) or 10)
        max_codes = int(payload.get("max_codes", 200) or 200)
        batch_size = int(payload.get("batch_size", 500) or 500)
        dry_run = bool(payload.get("dry_run", False))
        on_duplicate = str(payload.get("on_duplicate", "ignore") or "ignore")
        start_time = self._parse_datetime(payload.get("start_time"))
        end_time = self._parse_datetime(payload.get("end_time"))
        if end_time is None:
            end_time = datetime.now()
        if start_time is None:
            start_time = end_time - timedelta(days=lookback_days)
        if start_time >= end_time:
            raise RuntimeError("start_time must be earlier than end_time")

        selected_tables = payload.get("tables")
        if not selected_tables:
            tables = list(TABLE_INTERVAL_MAP.keys())
        else:
            tables = [str(t).strip() for t in selected_tables if str(t).strip() in TABLE_INTERVAL_MAP]
        if not tables:
            raise RuntimeError("no valid tables selected")

        codes = self._resolve_codes(payload.get("codes"), max_codes=max_codes)
        if not codes:
            raise RuntimeError("no stock codes available")

        headers = {"x-api-key": history_api_key, "Content-Type": "application/json"}
        provider = TushareProvider(token=tushare_token)
        session = requests.Session()

        summary = {
            "codes_total": len(codes),
            "tables": tables,
            "dry_run": dry_run,
            "start_time": start_time.isoformat(timespec="seconds"),
            "end_time": end_time.isoformat(timespec="seconds"),
            "total_source_rows": 0,
            "total_existing_rows": 0,
            "total_missing_rows": 0,
            "total_written_rows": 0,
            "code_reports": [],
        }

        for code in codes:
            source_frames = self._build_source_frames(provider, code, start_time, end_time, tables)
            code_report = {"code": code, "tables": []}
            for table in tables:
                source_df = source_frames.get(table)
                if source_df is None or source_df.empty:
                    code_report["tables"].append(
                        {
                            "table": table,
                            "source_rows": 0,
                            "existing_rows": 0,
                            "missing_rows": 0,
                            "written_rows": 0,
                        }
                    )
                    continue
                key_col = "trade_time" if table != "dat_days" else "date"
                existing_keys = self._fetch_existing_keys(
                    session=session,
                    base_url=history_base_url,
                    headers=headers,
                    table=table,
                    code=code,
                    start_time=start_time,
                    end_time=end_time,
                )
                source_keys = source_df[key_col].astype(str)
                missing_mask = ~source_keys.isin(existing_keys)
                missing_df = source_df.loc[missing_mask].copy()
                written_rows = 0
                if not dry_run and not missing_df.empty:
                    rows = missing_df.to_dict("records")
                    written_rows = self._push_rows(
                        session=session,
                        base_url=history_base_url,
                        headers=headers,
                        table=table,
                        rows=rows,
                        batch_size=batch_size,
                        on_duplicate=on_duplicate,
                    )
                table_report = {
                    "table": table,
                    "source_rows": int(len(source_df)),
                    "existing_rows": int(len(existing_keys)),
                    "missing_rows": int(len(missing_df)),
                    "written_rows": int(written_rows),
                }
                code_report["tables"].append(table_report)
                summary["total_source_rows"] += table_report["source_rows"]
                summary["total_existing_rows"] += table_report["existing_rows"]
                summary["total_missing_rows"] += table_report["missing_rows"]
                summary["total_written_rows"] += table_report["written_rows"]
            summary["code_reports"].append(code_report)
        return summary

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "")
        try:
            return datetime.fromisoformat(text)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        raise RuntimeError(f"invalid datetime: {value}")

    def _normalize_code(self, code: str) -> str:
        c = str(code or "").strip().upper()
        if not c:
            return c
        if c.startswith("SH") and len(c) == 8 and c[2:].isdigit():
            return f"{c[2:]}.SH"
        if c.startswith("SZ") and len(c) == 8 and c[2:].isdigit():
            return f"{c[2:]}.SZ"
        if "." in c:
            return c
        if len(c) == 6 and c.isdigit():
            return f"{c}.SH" if c.startswith("6") else f"{c}.SZ"
        return c

    def _resolve_codes(self, payload_codes: Any, max_codes: int) -> list[str]:
        out: list[str] = []
        if isinstance(payload_codes, list):
            out.extend([self._normalize_code(x) for x in payload_codes if str(x).strip()])
        if not out:
            cfg = ConfigLoader.reload()
            targets = cfg.get("targets", [])
            if isinstance(targets, list):
                out.extend([self._normalize_code(x) for x in targets if str(x).strip()])
        if not out:
            file_path = os.path.join("data", "stock_list.csv")
            if os.path.exists(file_path):
                try:
                    df = pd.read_csv(file_path)
                    if "code" in df.columns:
                        out.extend([self._normalize_code(x) for x in df["code"].astype(str).tolist()])
                    elif len(df.columns) > 0:
                        out.extend([self._normalize_code(x) for x in df.iloc[:, 0].astype(str).tolist()])
                except Exception:
                    pass
        dedup = []
        seen = set()
        for c in out:
            if not c or c in seen:
                continue
            seen.add(c)
            dedup.append(c)
            if len(dedup) >= max_codes:
                break
        return dedup

    def _build_source_frames(
        self,
        provider: TushareProvider,
        code: str,
        start_time: datetime,
        end_time: datetime,
        tables: list[str],
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        base_df = provider.fetch_minute_data(code, start_time, end_time)
        if base_df is None or base_df.empty:
            return frames
        df = base_df.copy()
        if "dt" not in df.columns and "trade_time" in df.columns:
            df = df.rename(columns={"trade_time": "dt"})
        required = ["dt", "open", "high", "low", "close", "vol", "amount"]
        if any(col not in df.columns for col in required):
            return frames
        df["dt"] = pd.to_datetime(df["dt"], errors="coerce")
        df = df.dropna(subset=["dt"]).sort_values("dt").drop_duplicates(subset=["dt"])
        df["open"] = pd.to_numeric(df["open"], errors="coerce")
        df["high"] = pd.to_numeric(df["high"], errors="coerce")
        df["low"] = pd.to_numeric(df["low"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["vol"] = pd.to_numeric(df["vol"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        df["code"] = code
        if df.empty:
            return frames
        source_by_interval: dict[str, pd.DataFrame] = {"1min": df}
        needed_intervals = {TABLE_INTERVAL_MAP[t] for t in tables}
        for interval in needed_intervals:
            if interval == "1min":
                continue
            source_by_interval[interval] = Indicators.resample(df.copy(), interval)
            source_by_interval[interval]["code"] = code
        for table in tables:
            interval = TABLE_INTERVAL_MAP[table]
            interval_df = source_by_interval.get(interval)
            if interval_df is None or interval_df.empty:
                frames[table] = pd.DataFrame()
                continue
            table_df = interval_df.copy()
            if "dt" not in table_df.columns:
                frames[table] = pd.DataFrame()
                continue
            table_df["dt"] = pd.to_datetime(table_df["dt"], errors="coerce")
            table_df = table_df.dropna(subset=["dt"])
            table_df = table_df[(table_df["dt"] >= start_time) & (table_df["dt"] <= end_time)]
            if table_df.empty:
                frames[table] = pd.DataFrame()
                continue
            table_df = table_df.sort_values("dt").drop_duplicates(subset=["dt"]).reset_index(drop=True)
            table_df["date"] = table_df["dt"].dt.strftime("%Y-%m-%d")
            table_df["pre_close"] = table_df["close"].shift(1)
            table_df["change"] = table_df["close"] - table_df["pre_close"]
            table_df["pct_chg"] = table_df["change"] / table_df["pre_close"] * 100.0
            table_df["pre_close"] = table_df["pre_close"].fillna(table_df["close"])
            table_df["change"] = table_df["change"].fillna(0.0)
            table_df["pct_chg"] = table_df["pct_chg"].replace([pd.NA, pd.NaT], 0.0).fillna(0.0)
            if table == "dat_days":
                use_cols = [
                    "code",
                    "date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "vol",
                    "amount",
                    "pre_close",
                    "change",
                    "pct_chg",
                ]
                out_df = table_df[use_cols].copy()
            else:
                table_df["trade_time"] = table_df["dt"].dt.strftime("%Y-%m-%dT%H:%M:%S")
                use_cols = [
                    "code",
                    "trade_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "vol",
                    "amount",
                    "date",
                    "pre_close",
                    "change",
                    "pct_chg",
                ]
                out_df = table_df[use_cols].copy()
            frames[table] = out_df.reset_index(drop=True)
        return frames

    def _fetch_existing_keys(
        self,
        session: requests.Session,
        base_url: str,
        headers: dict[str, str],
        table: str,
        code: str,
        start_time: datetime,
        end_time: datetime,
    ) -> set[str]:
        path = f"{base_url}/tables/{table}/rows"
        offset = 0
        limit = 10000
        result: set[str] = set()
        key_col = "trade_time" if table != "dat_days" else "date"
        if table == "dat_days":
            filters = [
                f"code:eq:{code}",
                f"date:gte:{start_time.strftime('%Y-%m-%d')}",
                f"date:lte:{end_time.strftime('%Y-%m-%d')}",
            ]
            order_by = "date"
        else:
            filters = [
                f"code:eq:{code}",
                f"trade_time:gte:{start_time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"trade_time:lte:{end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
            order_by = "trade_time"
        while True:
            params = {
                "limit": limit,
                "offset": offset,
                "order_by": order_by,
                "order_dir": "asc",
                "filter": filters,
            }
            resp = session.get(path, headers=headers, params=params, timeout=45)
            if resp.status_code != 200:
                raise RuntimeError(f"query existing rows failed table={table} code={code} status={resp.status_code}")
            payload = resp.json()
            rows = payload.get("rows") if isinstance(payload, dict) else payload
            if not isinstance(rows, list) or len(rows) == 0:
                break
            for row in rows:
                if isinstance(row, dict) and row.get(key_col) is not None:
                    result.add(str(row.get(key_col)))
            if len(rows) < limit:
                break
            offset += limit
        return result

    def _push_rows(
        self,
        session: requests.Session,
        base_url: str,
        headers: dict[str, str],
        table: str,
        rows: list[dict[str, Any]],
        batch_size: int,
        on_duplicate: str,
    ) -> int:
        if not rows:
            return 0
        path = f"{base_url}/tables/{table}/rows"
        written = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            payload = {"on_duplicate": on_duplicate, "rows": batch}
            resp = session.post(path, headers=headers, json=payload, timeout=90)
            if resp.status_code != 200:
                raise RuntimeError(f"insert rows failed table={table} status={resp.status_code} detail={resp.text[:200]}")
            data = resp.json()
            rowcount = data.get("rowcount") if isinstance(data, dict) else None
            if isinstance(rowcount, int):
                written += rowcount
            else:
                written += len(batch)
        return written
