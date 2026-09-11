import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Awaitable, Callable

import aiohttp
import aiosqlite

from data.dexscreener import get_token_data
from market.market_intelligence import analyze_market_intelligence
from security.goplus import get_token_security
from scoring.security_score import calculate_security_score


PULSE_URL = "https://api.mobula.io/api/2/pulse"
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


def _timestamp(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return number

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


def _merge_token(item: dict[str, Any]) -> dict[str, Any]:
    """
    Mobula TokenDataSchema can place identity/liquidity inside `token`
    while statistics such as volume/trades/created_at are at the root.
    Preserve BOTH layers.
    """
    nested = item.get("token")
    if isinstance(nested, dict):
        merged = dict(item)
        merged.update(nested)
        return merged
    return dict(item)


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """
    Normalize the different REST response wrappers used by Pulse V2.

    Supported examples:
      {"data": {"new": [...], "bonding": [...], "bonded": [...]}}
      {"new": {"data": [...]}, ...}
      {"payload": {"new": [...]}, ...}
    """
    found: list[dict[str, Any]] = []

    def add_list(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict):
                found.append(_merge_token(item))

    def inspect_view(view: Any) -> None:
        if isinstance(view, list):
            add_list(view)
            return

        if not isinstance(view, dict):
            return

        if isinstance(view.get("data"), list):
            add_list(view["data"])

        if isinstance(view.get("items"), list):
            add_list(view["items"])

    if isinstance(payload, dict):
        # Direct top-level views.
        for name in ("new", "bonding", "bonded"):
            inspect_view(payload.get(name))

        # Common REST wrapper.
        data = payload.get("data")
        if isinstance(data, dict):
            for name in ("new", "bonding", "bonded"):
                inspect_view(data.get(name))

        payload_node = payload.get("payload")
        if isinstance(payload_node, dict):
            for name in ("new", "bonding", "bonded"):
                inspect_view(payload_node.get(name))

        result = payload.get("result")
        if isinstance(result, dict):
            for name in ("new", "bonding", "bonded"):
                inspect_view(result.get(name))

    # Deduplicate by mint/address.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in found:
        mint = str(
            _first(
                item,
                "address",
                "tokenAddress",
                "mint",
                default="",
            )
        ).strip()

        if not mint or mint in seen:
            continue

        seen.add(mint)
        unique.append(item)

    return unique


def _extract_security_result(
    data: Any,
    mint: str,
) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    result = data.get("result")
    if not result:
        return None

    if isinstance(result, dict):
        direct = result.get(mint)
        if isinstance(direct, dict):
            return direct

        for key, value in result.items():
            if str(key).lower() == mint.lower():
                if isinstance(value, dict):
                    return value

        security_fields = {
            "mintable",
            "freezable",
            "holders",
            "metadata_mutable",
            "balance_mutable_authority",
            "transfer_fee",
            "transfer_hook",
        }

        if any(field in result for field in security_fields):
            return result

        if len(result) == 1:
            value = next(iter(result.values()))
            if isinstance(value, dict):
                return value

    if isinstance(result, list):
        for item in result:
            if not isinstance(item, dict):
                continue

            address = _first(
                item,
                "contract_address",
                "address",
                "mint",
                default="",
            )

            if str(address).lower() == mint.lower():
                return item

        if len(result) == 1 and isinstance(result[0], dict):
            return result[0]

    return None


class EarlyDetectionEngine:
    """
    Production Early Detection engine.

    Pipeline:
        Mobula Pulse Token Mode
        -> cheap discovery filter
        -> shortlist
        -> GoPlus security gate
        -> DEX Screener market analysis
        -> final score
        -> Discord alert

    This is analysis only. It never executes a trade.
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

        self.max_age_minutes = _float(
            os.getenv("EARLY_DETECTION_MAX_AGE_MINUTES"),
            45,
        )

        self.min_liquidity = _float(
            os.getenv("EARLY_DETECTION_MIN_LIQUIDITY_USD"),
            2500,
        )

        self.min_volume_5m = _float(
            os.getenv("EARLY_DETECTION_MIN_VOLUME_5M_USD"),
            250,
        )

        self.min_trades_5m = _int(
            os.getenv("EARLY_DETECTION_MIN_TRADES_5M"),
            5,
        )

        self.shortlist_size = max(
            1,
            _int(
                os.getenv("EARLY_DETECTION_SHORTLIST_SIZE"),
                5,
            ),
        )

        self.alert_score_threshold = _float(
            os.getenv("EARLY_DETECTION_ALERT_SCORE"),
            62,
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
        print("Early Detection V2: started")

        while not self.stop_event.is_set():
            try:
                await self.scan_once()
            except Exception as error:
                print(
                    "Early Detection V2 error:",
                    repr(error),
                )

            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

        print("Early Detection V2: stopped")

    async def _fetch_pulse(self) -> dict[str, Any] | None:
        if not self.mobula_api_key:
            print(
                "Early Detection V2: MOBULA_API_KEY غير موجود."
            )
            return None

        # Mobula's documented REST Pulse V2 token-mode request.
        # POST is used so the request explicitly asks for the default
        # token views: new, bonding and bonded.
        body = {
            "assetMode": True,
            "compressed": False,
            "model": "default",
            "chainId": ["solana:solana"],
        }

        headers = {
            "Authorization": self.mobula_api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Meme-Intelligence-Early-Detection/2.0",
        }

        timeout = aiohttp.ClientTimeout(total=25)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:
            async with session.post(
                PULSE_URL,
                json=body,
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
    def _metrics(
        token: dict[str, Any],
    ) -> dict[str, float]:
        volume_5m = _float(
            _first(
                token,
                "volume_5min",
                "volume5min",
                "volume_5m",
                "volume5m",
                "volume5mUSD",
                default=0,
            )
        )

        trades_5m = _int(
            _first(
                token,
                "trades_5min",
                "trades5min",
                "trades_5m",
                "trades5m",
                default=0,
            )
        )

        buys_5m = _int(
            _first(
                token,
                "buys_5min",
                "buys5min",
                "buys_5m",
                "buys5m",
                default=0,
            )
        )

        sells_5m = _int(
            _first(
                token,
                "sells_5min",
                "sells5min",
                "sells_5m",
                "sells5m",
                default=0,
            )
        )

        if trades_5m <= 0:
            trades_5m = buys_5m + sells_5m

        organic_volume = _float(
            _first(
                token,
                "organic_volume_5min",
                "organicVolume5min",
                "organic_volume_5m",
                default=0,
            )
        )

        organic_trades = _int(
            _first(
                token,
                "organic_trades_5min",
                "organicTrades5min",
                "organic_trades_5m",
                default=0,
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

        return {
            "volume_5m": volume_5m,
            "trades_5m": float(trades_5m),
            "buys_5m": float(buys_5m),
            "sells_5m": float(sells_5m),
            "organic_volume_5m": organic_volume,
            "organic_trades_5m": float(organic_trades),
            "liquidity": liquidity,
        }

    @staticmethod
    def _age_minutes(
        token: dict[str, Any],
    ) -> float | None:
        created_at = _timestamp(
            _first(
                token,
                "created_at",
                "createdAt",
                "createdTimestamp",
                default=None,
            )
        )

        if created_at is None:
            return None

        return max(
            0.0,
            (time.time() - created_at) / 60,
        )

    def _cheap_filter_reason(
        self,
        token: dict[str, Any],
        age_minutes: float | None,
    ) -> str | None:
        if (
            age_minutes is not None
            and age_minutes > self.max_age_minutes
        ):
            return "age"

        metrics = self._metrics(token)

        if metrics["liquidity"] < self.min_liquidity:
            return "liquidity"

        if (
            metrics["volume_5m"] < self.min_volume_5m
            and metrics["trades_5m"] < self.min_trades_5m
        ):
            return "activity"

        return None

    def _discovery_score(
        self,
        token: dict[str, Any],
        age_minutes: float | None,
    ) -> float:
        metrics = self._metrics(token)
        score = 0.0

        # Freshness
        if age_minutes is None:
            score += 8
        elif age_minutes <= 5:
            score += 25
        elif age_minutes <= 10:
            score += 21
        elif age_minutes <= 20:
            score += 17
        elif age_minutes <= 45:
            score += 10

        # Liquidity
        liquidity = metrics["liquidity"]

        if liquidity >= 50_000:
            score += 12
        elif liquidity >= 20_000:
            score += 18
        elif liquidity >= 10_000:
            score += 20
        elif liquidity >= 5_000:
            score += 16
        elif liquidity >= 2_500:
            score += 10

        # Recent volume
        volume = metrics["volume_5m"]

        if volume >= 20_000:
            score += 22
        elif volume >= 10_000:
            score += 19
        elif volume >= 2_500:
            score += 15
        elif volume >= 500:
            score += 9
        elif volume >= 250:
            score += 5

        # Trade breadth
        trades = metrics["trades_5m"]

        if trades >= 100:
            score += 12
        elif trades >= 50:
            score += 10
        elif trades >= 25:
            score += 7
        elif trades >= 10:
            score += 4
        elif trades >= 5:
            score += 2

        # Organic activity bonus
        organic_volume = metrics["organic_volume_5m"]

        if organic_volume > 0 and volume > 0:
            organic_ratio = organic_volume / volume

            if organic_ratio >= 0.70:
                score += 5
            elif organic_ratio >= 0.40:
                score += 3

        # Participant quality
        holders = _int(
            _first(
                token,
                "holdersCount",
                "holders_count",
                default=0,
            )
        )

        smart = _int(
            _first(
                token,
                "smartTradersCount",
                "smart_traders_count",
                default=0,
            )
        )

        pro = _int(
            _first(
                token,
                "proTradersCount",
                "pro_traders_count",
                default=0,
            )
        )

        if holders >= 250:
            score += 4
        elif holders >= 100:
            score += 2

        score += min(4, smart)
        score += min(4, pro)

        return max(
            0.0,
            min(100.0, score),
        )

    async def _already_alerted(
        self,
        mint: str,
    ) -> bool:
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

        return bool(
            row
            and int(row[0]) == 1
        )

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
    ) -> tuple[
        float,
        dict[str, Any] | None,
    ]:
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

        return (
            _float(
                analysis.get("score"),
                0,
            ),
            analysis,
        )

    async def _build_candidate(
        self,
        token: dict[str, Any],
        discovery_score: float,
        debug: dict[str, int],
    ) -> tuple[
        dict[str, Any],
        str,
    ] | None:
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
            debug["missing_mint"] += 1
            return None

        if await self._already_alerted(mint):
            debug["already_alerted"] += 1
            return None

        try:
            security_score, security = await self._security_gate(
                mint
            )
        except Exception as error:
            debug["security_error"] += 1
            print(
                "Early Detection V2 security error:",
                mint,
                repr(error),
            )
            return None

        if security is None:
            debug["security_missing"] += 1
            return None

        critical = security.get(
            "critical",
            [],
        )

        if critical:
            debug["security_critical"] += 1
            return None

        if security_score < self.security_threshold:
            debug["security_low"] += 1
            return None

        try:
            pair = await get_token_data(mint)
        except Exception as error:
            debug["pair_error"] += 1
            print(
                "Early Detection V2 DEX error:",
                mint,
                repr(error),
            )
            return None

        if not pair:
            debug["pair_missing"] += 1
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
            debug["final_score_low"] += 1

            await self._save_token(
                token,
                final_score,
                security_score,
                False,
            )

            return None

        metrics = self._metrics(token)
        age = self._age_minutes(token)

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

        source = str(
            _first(
                token,
                "source",
                default="غير معروف",
            )
        )

        exchange = token.get("exchange")
        dex_name = "غير معروف"

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

        age_text = (
            f"{age:.1f} دقيقة"
            if age is not None
            else "غير متاح"
        )

        message = (
            "━━━━━━━━━━━━━━━━━━\n"
            "🚨 **Early Detection V2 — مرشح مبكر**\n\n"
            f"🪙 **العملة:** `{name}`\n"
            f"🏷️ **الرمز:** `${symbol}`\n"
            f"⏱️ **العمر:** `{age_text}`\n"
            f"💧 **السيولة:** `${metrics['liquidity']:,.0f}`\n"
            f"📈 **الحجم 5د:** `${metrics['volume_5m']:,.0f}`\n"
            f"🔄 **المعاملات 5د:** `{int(metrics['trades_5m'])}`\n"
            f"🧪 **الحجم العضوي 5د:** "
            f"`{metrics['organic_volume_5m']:,.0f}`\n"
            f"🏭 **المصدر:** `{source}`\n"
            f"🔄 **المنصة:** `{dex_name}`\n\n"
            f"🚀 **درجة الاكتشاف:** "
            f"`{discovery_score:.1f}/100`\n"
            f"🛡️ **درجة الأمان:** "
            f"`{security_score:.1f}/100`\n"
            f"📊 **Market Score:** "
            f"`{market_score:.1f}/100`\n"
            f"🎯 **الدرجة النهائية:** "
            f"`{final_score:.1f}/100`\n\n"
            "🧭 **الحالة:** `مراقبة مبكرة`\n"
            "⚠️ تنبيه تحليلي فقط، وليس توصية شراء "
            "أو ضمانًا للربح.\n\n"
            f"🔗 **السوق:** {pair_url}\n"
            f"🧾 **Mint:** `{mint}`"
        )

        await self._save_token(
            token,
            final_score,
            security_score,
            True,
        )

        debug["alerts_qualified"] += 1

        return token, message

    @staticmethod
    def _stats(
        values: list[float],
    ) -> dict[str, Any]:
        if not values:
            return {
                "count": 0,
                "min": 0,
                "median": 0,
                "max": 0,
                "average": 0,
            }

        ordered = sorted(values)
        count = len(ordered)

        if count % 2:
            median = ordered[count // 2]
        else:
            median = (
                ordered[count // 2 - 1]
                + ordered[count // 2]
            ) / 2

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
                "seen": 0,
                "candidates": 0,
                "alerts": 0,
            }

        pulse = await self._fetch_pulse()

        if not pulse:
            return {
                "status": "error",
                "seen": 0,
                "candidates": 0,
                "alerts": 0,
            }

        items = _extract_items(pulse)

        debug: dict[str, Any] = {
            "mode": "Mobula Pulse V2 / assetMode=true",
            "raw_items": len(items),
            "age": 0,
            "liquidity": 0,
            "activity": 0,
            "passed_cheap": 0,
            "already_alerted": 0,
            "missing_mint": 0,
            "security_error": 0,
            "security_missing": 0,
            "security_critical": 0,
            "security_low": 0,
            "pair_error": 0,
            "pair_missing": 0,
            "final_score_low": 0,
            "alerts_qualified": 0,
        }

        liquidity_values: list[float] = []
        volume_values: list[float] = []
        trades_values: list[float] = []
        organic_volume_values: list[float] = []

        candidates: list[
            tuple[
                float,
                dict[str, Any],
            ]
        ] = []

        for raw_item in items:
            token = _merge_token(raw_item)

            age = self._age_minutes(token)
            metrics = self._metrics(token)

            liquidity_values.append(
                metrics["liquidity"]
            )
            volume_values.append(
                metrics["volume_5m"]
            )
            trades_values.append(
                metrics["trades_5m"]
            )
            organic_volume_values.append(
                metrics["organic_volume_5m"]
            )

            reason = self._cheap_filter_reason(
                token,
                age,
            )

            if reason is not None:
                debug[reason] += 1
                continue

            debug["passed_cheap"] += 1

            score = self._discovery_score(
                token,
                age,
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
                )
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        alerts = 0

        for discovery_score, token in candidates[
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

        debug["liquidity_stats"] = self._stats(
            liquidity_values
        )
        debug["volume_5m_stats"] = self._stats(
            volume_values
        )
        debug["trades_5m_stats"] = self._stats(
            trades_values
        )
        debug["organic_volume_5m_stats"] = self._stats(
            organic_volume_values
        )

        print(
            "Early Detection V2 debug:",
            json.dumps(
                debug,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

        return {
            "status": "ok",
            "seen": len(items),
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
                    SUM(
                        CASE
                            WHEN alerted = 1
                            THEN 1
                            ELSE 0
                        END
                    )
                FROM early_detection_tokens
                """
            ) as cursor:
                row = await cursor.fetchone()

        return {
            "running": (
                self.task is not None
                and not self.task.done()
            ),
            "channel_id": self.channel_id,
            "interval_seconds": self.interval_seconds,
            "tracked_tokens": _int(
                row[0] if row else 0
            ),
            "alerts_sent": _int(
                row[1] if row else 0
            ),
        }
