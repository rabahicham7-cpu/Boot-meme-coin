import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiohttp
import aiosqlite

from data.dexscreener import get_token_data
from market.market_intelligence import analyze_market_intelligence
from security.goplus import get_token_security
from scoring.security_score import calculate_security_score


PULSE_URL = "https://pulse-v2-api.mobula.io/api/2/pulse"
DB_PATH = os.getenv("EARLY_DETECTION_DB", "early_detection.db")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        value = float(value)
        if value > 10_000_000_000:
            value /= 1000
        return value

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(
                text.replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
            try:
                number = float(text)
                if number > 10_000_000_000:
                    number /= 1000
                return number
            except ValueError:
                return None

    return None


def _extract_security_result(data: Any, mint: str) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    result = data.get("result")
    if not result:
        return None

    if isinstance(result, dict):
        token_data = result.get(mint)
        if isinstance(token_data, dict):
            return token_data

        for key, value in result.items():
            if str(key).lower() == mint.lower() and isinstance(value, dict):
                return value

        token_fields = {
            "mintable",
            "freezable",
            "holders",
            "metadata_mutable",
            "balance_mutable_authority",
            "transfer_fee",
            "transfer_hook",
        }

        if any(field in result for field in token_fields):
            return result

        if len(result) == 1:
            first_value = next(iter(result.values()))
            if isinstance(first_value, dict):
                return first_value

    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue

            address = (
                item.get("contract_address")
                or item.get("address")
                or item.get("mint")
            )

            if address and str(address).lower() == mint.lower():
                return item

        if len(result) == 1 and isinstance(result[0], dict):
            return result[0]

    return None


class EarlyDetectionEngine:
    """
    Phase 1:
    - Discover newly listed Solana tokens through Mobula Pulse HTTP.
    - Apply cheap market filters before spending security/API budget.
    - Run GoPlus security only for shortlisted candidates.
    - Send a conservative "مرشح مبكر" alert; never call it a buy signal.
    """

    def __init__(
        self,
        send_alert: Callable[[int, str], Awaitable[None]],
    ):
        self.send_alert = send_alert

        self.mobula_api_key = os.getenv("MOBULA_API_KEY", "").strip()

        self.interval_seconds = max(
            30,
            _int(
                os.getenv("EARLY_DETECTION_INTERVAL_SECONDS"),
                60,
            ),
        )

        self.min_liquidity = _float(
            os.getenv("EARLY_DETECTION_MIN_LIQUIDITY_USD"),
            5_000,
        )

        self.min_volume_5m = _float(
            os.getenv("EARLY_DETECTION_MIN_VOLUME_5M_USD"),
            500,
        )

        self.min_trades_5m = _int(
            os.getenv("EARLY_DETECTION_MIN_TRADES_5M"),
            10,
        )

        self.max_age_minutes = _float(
            os.getenv("EARLY_DETECTION_MAX_AGE_MINUTES"),
            30,
        )

        self.shortlist_size = max(
            1,
            _int(
                os.getenv("EARLY_DETECTION_SHORTLIST_SIZE"),
                3,
            ),
        )

        self.alert_score_threshold = _float(
            os.getenv("EARLY_DETECTION_ALERT_SCORE"),
            65,
        )

        self.security_threshold = _float(
            os.getenv("EARLY_DETECTION_SECURITY_THRESHOLD"),
            60,
        )

        self.channel_id: int | None = None
        self.task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()

    async def initialize(self) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS early_detection_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS early_detection_tokens (
                    mint TEXT PRIMARY KEY,
                    symbol TEXT,
                    name TEXT,
                    first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL,
                    last_score REAL DEFAULT 0,
                    security_score REAL DEFAULT 0,
                    alerted INTEGER DEFAULT 0
                )
                """
            )

            await db.commit()

            async with db.execute(
                """
                SELECT value
                FROM early_detection_settings
                WHERE key = 'channel_id'
                """
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            try:
                self.channel_id = int(row[0])
            except (TypeError, ValueError):
                self.channel_id = None

    async def set_channel(self, channel_id: int) -> None:
        self.channel_id = int(channel_id)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO early_detection_settings(key, value)
                VALUES('channel_id', ?)
                ON CONFLICT(key)
                DO UPDATE SET value = excluded.value
                """,
                (str(channel_id),),
            )
            await db.commit()

    async def clear_channel(self) -> None:
        self.channel_id = None

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                DELETE FROM early_detection_settings
                WHERE key = 'channel_id'
                """
            )
            await db.commit()

    def start(self) -> None:
        if self.task is not None and not self.task.done():
            return

        self.stop_event.clear()
        self.task = asyncio.create_task(
            self._run(),
            name="early-detection",
        )

    async def stop(self) -> None:
        self.stop_event.set()

        if self.task is not None:
            try:
                await asyncio.wait_for(
                    self.task,
                    timeout=5,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()

        self.task = None

    async def _run(self) -> None:
        print("Early Detection: started")

        while not self.stop_event.is_set():
            try:
                await self.scan_once()
            except Exception as error:
                print(
                    "Early Detection error:",
                    repr(error),
                )

            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

        print("Early Detection: stopped")

    async def _fetch_pulse(self) -> dict[str, Any] | None:
        if not self.mobula_api_key:
            print(
                "Early Detection: MOBULA_API_KEY غير موجود."
            )
            return None

        params = {
            "assetMode": "false",
            "chainId": "solana:solana",
            "model": "default",
        }

        headers = {
            "Authorization": self.mobula_api_key,
            "Accept": "application/json",
            "User-Agent": "Meme-Intelligence-Early-Detection/1.0",
        }

        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:
            async with session.get(
                PULSE_URL,
                params=params,
                headers=headers,
            ) as response:
                data = await response.json(
                    content_type=None
                )

                if response.status != 200:
                    raise RuntimeError(
                        f"Mobula Pulse HTTP {response.status}: {data}"
                    )

                if not isinstance(data, dict):
                    raise RuntimeError(
                        "Mobula Pulse returned unexpected data."
                    )

                return data

    @staticmethod
    def _view_items(
        pulse: dict[str, Any],
        view_name: str = "new",
    ) -> list[dict[str, Any]]:
        view = pulse.get(view_name)

        if not isinstance(view, dict):
            return []

        data = view.get("data")

        if not isinstance(data, list):
            return []

        result: list[dict[str, Any]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            token = item.get("token")

            if isinstance(token, dict):
                result.append(token)
            else:
                result.append(item)

        return result

    @staticmethod
    def _normalize_token(item: dict[str, Any]) -> dict[str, Any]:
        # Mobula can return token fields directly or nested under "token".
        token = item.get("token")

        if isinstance(token, dict):
            merged = dict(item)
            merged.update(token)
            return merged

        return item

    def _discovery_score(
        self,
        token: dict[str, Any],
        age_minutes: float | None,
    ) -> float:
        liquidity = _float(
            _first(
                token,
                "liquidity",
                "liquidityUSD",
                "liquidityUsd",
                "approximateReserveUSD",
                default=0,
            )
        )

        volume_5m = _float(
            _first(
                token,
                "volume5min",
                "volume5m",
                "volume5mUSD",
                "volume5minUSD",
                "volume5MinUSD",
                default=0,
            )
        )

        volume_1h = _float(
            _first(
                token,
                "volume1h",
                "volume1hUSD",
                default=0,
            )
        )

        buys_5m = _int(
            _first(
                token,
                "buys5min",
                "buyCount5m",
                "buys5m",
                default=0,
            )
        )

        sells_5m = _int(
            _first(
                token,
                "sells5min",
                "sellCount5m",
                "sells5m",
                default=0,
            )
        )

        holders = _int(
            _first(
                token,
                "holdersCount",
                "holders_count",
                default=0,
            )
        )

        smart_traders = _int(
            _first(
                token,
                "smartTradersCount",
                "smart_traders_count",
                default=0,
            )
        )

        pro_traders = _int(
            _first(
                token,
                "proTradersCount",
                "pro_traders_count",
                default=0,
            )
        )

        score = 0.0

        # Freshness: highest weight for very early candidates.
        if age_minutes is not None:
            if age_minutes <= 5:
                score += 25
            elif age_minutes <= 10:
                score += 20
            elif age_minutes <= 20:
                score += 14
            else:
                score += 8

        # Liquidity: enough to be tradable, but not so much that
        # the signal is already a mature large-cap opportunity.
        if liquidity >= 50_000:
            score += 15
        elif liquidity >= 20_000:
            score += 20
        elif liquidity >= 10_000:
            score += 18
        elif liquidity >= 5_000:
            score += 14
        elif liquidity >= 2_500:
            score += 8

        # Recent activity.
        if volume_5m >= 20_000:
            score += 20
        elif volume_5m >= 10_000:
            score += 18
        elif volume_5m >= 2_500:
            score += 14
        elif volume_5m >= 500:
            score += 8

        if volume_1h >= 50_000:
            score += 8
        elif volume_1h >= 10_000:
            score += 5

        # Transaction breadth.
        total_trades = buys_5m + sells_5m

        if total_trades >= 100:
            score += 12
        elif total_trades >= 50:
            score += 9
        elif total_trades >= 25:
            score += 6
        elif total_trades >= 10:
            score += 3

        # Early participant quality.
        if holders >= 250:
            score += 5
        elif holders >= 100:
            score += 3

        if smart_traders >= 3:
            score += 5
        elif smart_traders >= 1:
            score += 3

        if pro_traders >= 3:
            score += 5
        elif pro_traders >= 1:
            score += 3

        return max(0.0, min(100.0, score))

    def _cheap_filter_reason(
        self,
        token: dict[str, Any],
        age_minutes: float | None,
    ) -> str | None:
        """Return the first cheap-filter rejection reason, or None if passed."""
        if age_minutes is not None and age_minutes > self.max_age_minutes:
            return "age"

        liquidity = _float(
            _first(
                token,
                "liquidity",
                "liquidityUSD",
                "liquidityUsd",
                "approximateReserveUSD",
                default=0,
            )
        )

        if liquidity < self.min_liquidity:
            return "liquidity"

        volume_5m = _float(
            _first(
                token,
                "volume5min",
                "volume5m",
                "volume5mUSD",
                "volume5minUSD",
                "volume5MinUSD",
                default=0,
            )
        )

        buys_5m = _int(
            _first(
                token,
                "buys5min",
                "buyCount5m",
                "buys5m",
                default=0,
            )
        )

        sells_5m = _int(
            _first(
                token,
                "sells5min",
                "sellCount5m",
                "sells5m",
                default=0,
            )
        )

        if (
            volume_5m < self.min_volume_5m
            and (buys_5m + sells_5m) < self.min_trades_5m
        ):
            return "activity"

        return None

    def _cheap_filter(
        self,
        token: dict[str, Any],
        age_minutes: float | None,
    ) -> bool:
        return self._cheap_filter_reason(token, age_minutes) is None

    async def _already_alerted(self, mint: str) -> bool:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """
                SELECT alerted
                FROM early_detection_tokens
                WHERE mint = ?
                """,
                (mint,),
            ) as cursor:
                row = await cursor.fetchone()

        return bool(row and int(row[0]) == 1)

    async def _save_token(
        self,
        token: dict[str, Any],
        score: float,
        security_score: float = 0,
        alerted: bool = False,
    ) -> None:
        mint = str(
            _first(
                token,
                "address",
                "tokenAddress",
                "mint",
                default="",
            )
        ).strip()

        if not mint:
            return

        symbol = str(
            _first(
                token,
                "symbol",
                default="?",
            )
        )

        name = str(
            _first(
                token,
                "name",
                default="Unknown",
            )
        )

        now = time.time()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO early_detection_tokens(
                    mint,
                    symbol,
                    name,
                    first_seen,
                    last_seen,
                    last_score,
                    security_score,
                    alerted
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mint)
                DO UPDATE SET
                    symbol = excluded.symbol,
                    name = excluded.name,
                    last_seen = excluded.last_seen,
                    last_score = excluded.last_score,
                    security_score = excluded.security_score,
                    alerted = CASE
                        WHEN excluded.alerted = 1 THEN 1
                        ELSE early_detection_tokens.alerted
                    END
                """,
                (
                    mint,
                    symbol,
                    name,
                    now,
                    now,
                    score,
                    security_score,
                    1 if alerted else 0,
                ),
            )

            await db.commit()

    async def _security_gate(
        self,
        mint: str,
    ) -> tuple[float, dict[str, Any] | None]:
        response = await get_token_security(mint)
        security = _extract_security_result(
            response,
            mint,
        )

        if security is None:
            return 0.0, None

        analysis = calculate_security_score(
            security
        )

        score = _float(
            analysis.get("score"),
            0,
        )

        return score, analysis

    async def _build_candidate(
        self,
        token: dict[str, Any],
        discovery_score: float,
        debug: dict[str, int] | None = None,
    ) -> tuple[dict[str, Any], str] | None:
        mint = str(
            _first(
                token,
                "address",
                "tokenAddress",
                "mint",
                default="",
            )
        ).strip()

        if not mint:
            return None

        if await self._already_alerted(mint):
            if debug is not None:
                debug["already_alerted"] = debug.get("already_alerted", 0) + 1
            return None

        security_score, security = await self._security_gate(
            mint
        )

        # Security is a gate, not just another weighted feature.
        if security is None:
            if debug is not None:
                debug["security_missing"] = debug.get("security_missing", 0) + 1
            await self._save_token(
                token,
                discovery_score,
                0,
                False,
            )
            return None

        critical = security.get(
            "critical",
            [],
        )

        if critical:
            if debug is not None:
                debug["security_critical"] = debug.get("security_critical", 0) + 1
            await self._save_token(
                token,
                discovery_score,
                security_score,
                False,
            )
            return None

        if security_score < self.security_threshold:
            if debug is not None:
                debug["security_low"] = debug.get("security_low", 0) + 1
            await self._save_token(
                token,
                discovery_score,
                security_score,
                False,
            )
            return None

        pair = await get_token_data(
            mint
        )

        if not pair:
            if debug is not None:
                debug["pair_missing"] = debug.get("pair_missing", 0) + 1
            await self._save_token(
                token,
                discovery_score,
                security_score,
                False,
            )
            return None

        market = analyze_market_intelligence(
            pair
        )

        market_score = _float(
            market.get("market_score"),
            0,
        )

        final_score = (
            discovery_score * 0.45
            + security_score * 0.35
            + market_score * 0.20
        )

        if final_score < self.alert_score_threshold:
            if debug is not None:
                debug["final_score_low"] = debug.get("final_score_low", 0) + 1
            await self._save_token(
                token,
                final_score,
                security_score,
                False,
            )
            return None

        symbol = str(
            _first(
                token,
                "symbol",
                default="?",
            )
        )

        name = str(
            _first(
                token,
                "name",
                default="غير معروف",
            )
        )

        liquidity = _float(
            _first(
                token,
                "liquidity",
                "liquidityUSD",
                "liquidityUsd",
                "approximateReserveUSD",
                default=0,
            )
        )

        volume_5m = _float(
            _first(
                token,
                "volume5min",
                "volume5m",
                "volume5mUSD",
                "volume5minUSD",
                "volume5MinUSD",
                default=0,
            )
        )

        created_at = _parse_timestamp(
            _first(
                token,
                "createdAt",
                "created_at",
                "createdTimestamp",
                default=None,
            )
        )

        age_minutes = None
        if created_at is not None:
            age_minutes = max(
                0.0,
                (
                    time.time() - created_at
                ) / 60,
            )

        source = str(
            _first(
                token,
                "source",
                default="غير معروف",
            )
        )

        dex_name = "غير معروف"
        exchange = token.get("exchange")
        if isinstance(exchange, dict):
            dex_name = str(
                exchange.get(
                    "name",
                    dex_name,
                )
            )

        pair_url = pair.get(
            "url",
            f"https://dexscreener.com/solana/{mint}",
        )

        message = (
            "━━━━━━━━━━━━━━━━━━\n"
            "🚨 **Early Detection — مرشح مبكر**\n\n"
            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
            f"⏱️ **العمر التقريبي:** "
            f"`{age_minutes:.1f} دقيقة`"
            if age_minutes is not None
            else
            "━━━━━━━━━━━━━━━━━━\n"
            "🚨 **Early Detection — مرشح مبكر**\n\n"
            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
        )

        message += (
            f"💧 **السيولة:** `${liquidity:,.0f}`\n"
            f"📈 **الحجم 5د:** `${volume_5m:,.0f}`\n"
            f"🏭 **المصدر:** `{source}`\n"
            f"🔄 **المنصة:** `{dex_name}`\n\n"
            f"🚀 **درجة الاكتشاف:** `{discovery_score:.1f}/100`\n"
            f"🛡️ **درجة الأمان:** `{security_score:.1f}/100`\n"
            f"📊 **Market Score:** `{market_score:.1f}/100`\n"
            f"🎯 **الدرجة المبكرة:** `{final_score:.1f}/100`\n\n"
            "🧭 **الحالة:** `مراقبة مبكرة`\n"
            "⚠️ هذا تنبيه تحليلي مبكر، وليس توصية شراء أو ضمانًا للربح.\n\n"
            f"🔗 **السوق:** {pair_url}\n"
            f"🧾 **Mint:** `{mint}`"
        )

        await self._save_token(
            token,
            final_score,
            security_score,
            True,
        )

        if debug is not None:
            debug["alerts_qualified"] = debug.get("alerts_qualified", 0) + 1

        return token, message

    @staticmethod
    def _distribution_stats(values: list[float]) -> dict[str, float | int | None]:
        if not values:
            return {
                "count": 0,
                "min": None,
                "median": None,
                "max": None,
                "average": None,
            }

        ordered = sorted(values)
        count = len(ordered)
        middle = count // 2

        if count % 2 == 0:
            median = (
                ordered[middle - 1] + ordered[middle]
            ) / 2
        else:
            median = ordered[middle]

        return {
            "count": count,
            "min": ordered[0],
            "median": median,
            "max": ordered[-1],
            "average": sum(ordered) / count,
        }

    async def scan_once(self) -> dict[str, Any]:
        if self.channel_id is None:
            return {
                "status": "idle",
                "reason": "لم يتم تحديد قناة التنبيهات.",
                "candidates": 0,
                "alerts": 0,
            }

        pulse = await self._fetch_pulse()

        if not pulse:
            return {
                "status": "error",
                "candidates": 0,
                "alerts": 0,
            }

        raw_items = self._view_items(
            pulse,
            "new",
        )

        candidates: list[tuple[float, dict[str, Any], float | None]] = []

        debug: dict[str, Any] = {
            "raw_items": len(raw_items),
            "non_solana": 0,
            "age": 0,
            "liquidity": 0,
            "activity": 0,
            "passed_cheap": 0,
            "already_alerted": 0,
            "security_missing": 0,
            "security_critical": 0,
            "security_low": 0,
            "pair_missing": 0,
            "final_score_low": 0,
            "alerts_qualified": 0,
            "liquidity_values": [],
            "volume_5m_values": [],
            "trades_5m_values": [],
            "age_values": [],
        }

        for raw in raw_items:
            token = self._normalize_token(raw)

            liquidity_value = _float(
                _first(
                    token,
                    "liquidity",
                    "liquidityUSD",
                    "liquidityUsd",
                    "approximateReserveUSD",
                    default=0,
                )
            )
            debug["liquidity_values"].append(liquidity_value)

            volume_5m_value = _float(
                _first(
                    token,
                    "volume5min",
                    "volume5m",
                    "volume5mUSD",
                    "volume5minUSD",
                    "volume5MinUSD",
                    default=0,
                )
            )
            debug["volume_5m_values"].append(volume_5m_value)

            buys_5m_value = _int(
                _first(
                    token,
                    "buys5min",
                    "buyCount5m",
                    "buys5m",
                    default=0,
                )
            )
            sells_5m_value = _int(
                _first(
                    token,
                    "sells5min",
                    "sellCount5m",
                    "sells5m",
                    default=0,
                )
            )
            debug["trades_5m_values"].append(
                buys_5m_value + sells_5m_value
            )

            chain_id = str(
                _first(
                    token,
                    "chainId",
                    "chain_id",
                    default="",
                )
            ).lower()

            if chain_id and "solana" not in chain_id:
                debug["non_solana"] += 1
                continue

            created_at = _parse_timestamp(
                _first(
                    token,
                    "createdAt",
                    "created_at",
                    "createdTimestamp",
                    default=None,
                )
            )

            age_minutes = None
            if created_at is not None:
                age_minutes = max(
                    0.0,
                    (
                        time.time() - created_at
                    ) / 60,
                )
                debug["age_values"].append(age_minutes)

            reason = self._cheap_filter_reason(
                token,
                age_minutes,
            )

            if reason is not None:
                debug[reason] += 1
                continue

            debug["passed_cheap"] += 1

            score = self._discovery_score(
                token,
                age_minutes,
            )

            await self._save_token(
                token,
                score,
                0,
                False,
            )

            candidates.append(
                (
                    score,
                    token,
                    age_minutes,
                )
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        alerts = 0

        for discovery_score, token, _ in candidates[
            : self.shortlist_size
        ]:
            result = await self._build_candidate(
                token,
                discovery_score,
                debug,
            )

            if result is None:
                continue

            _, message = result

            await self.send_alert(
                self.channel_id,
                message,
            )

            alerts += 1

        liquidity_values = [
            value
            for value in debug.get("liquidity_values", [])
            if value > 0
        ]
        age_values = [
            value
            for value in debug.get("age_values", [])
            if value >= 0
        ]
        volume_5m_values = [
            value
            for value in debug.get("volume_5m_values", [])
            if value >= 0
        ]
        trades_5m_values = [
            value
            for value in debug.get("trades_5m_values", [])
            if value >= 0
        ]

        debug["liquidity_stats"] = self._distribution_stats(
            liquidity_values
        )
        debug["volume_5m_stats"] = self._distribution_stats(
            volume_5m_values
        )
        debug["trades_5m_stats"] = self._distribution_stats(
            trades_5m_values
        )
        debug["age_stats"] = self._distribution_stats(
            age_values
        )
        debug.pop("liquidity_values", None)
        debug.pop("volume_5m_values", None)
        debug.pop("trades_5m_values", None)
        debug.pop("age_values", None)

        print(
            "Early Detection debug:",
            json.dumps(debug, ensure_ascii=False, sort_keys=True),
        )

        return {
            "status": "ok",
            "seen": len(raw_items),
            "candidates": len(candidates),
            "alerts": alerts,
            "debug": debug,
        }

    async def status(self) -> dict[str, Any]:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """
                SELECT
                    COUNT(*),
                    SUM(CASE WHEN alerted = 1 THEN 1 ELSE 0 END)
                FROM early_detection_tokens
                """
            ) as cursor:
                row = await cursor.fetchone()

        total = _int(row[0] if row else 0)
        alerted = _int(row[1] if row else 0)

        return {
            "running": (
                self.task is not None
                and not self.task.done()
            ),
            "channel_id": self.channel_id,
            "interval_seconds": self.interval_seconds,
            "tracked_tokens": total,
            "alerts_sent": alerted,
        }
