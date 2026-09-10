import os
from typing import Any, Optional

import aiohttp
from dotenv import load_dotenv


load_dotenv()


MOBULA_BASE_URL = "https://api.mobula.io/api/2"

MOBULA_API_KEY = os.getenv("MOBULA_API_KEY")

MOBULA_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 14) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/131.0.0.0 Mobile Safari/537.36"
)


class MobulaError(Exception):
    """خطأ خاص بطبقة Mobula."""
    pass


async def _request(
    endpoint: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:

    if not MOBULA_API_KEY:
        raise MobulaError(
            "MOBULA_API_KEY غير موجود في متغيرات البيئة."
        )

    url = f"{MOBULA_BASE_URL}{endpoint}"

    headers = {
        "Authorization": MOBULA_API_KEY,
        "Accept": "application/json",
        "User-Agent": MOBULA_USER_AGENT,
    }

    timeout = aiohttp.ClientTimeout(total=20)

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                headers=headers,
                params=params,
            ) as response:

                raw_text = await response.text()

                if response.status != 200:
                    raise MobulaError(
                        f"Mobula HTTP {response.status}: "
                        f"{raw_text[:500]}"
                    )

                try:
                    data = await response.json(
                        content_type=None
                    )
                except Exception as exc:
                    raise MobulaError(
                        f"Mobula أعادت استجابة غير صالحة: "
                        f"{raw_text[:500]}"
                    ) from exc

                if not isinstance(data, dict):
                    raise MobulaError(
                        "استجابة Mobula ليست JSON object."
                    )

                return data

    except aiohttp.ClientError as exc:
        raise MobulaError(
            f"خطأ اتصال مع Mobula: {exc}"
        ) from exc

    except TimeoutError as exc:
        raise MobulaError(
            "انتهت مهلة الاتصال مع Mobula."
        ) from exc


async def get_token_details(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/details",
        params={
            "blockchain": "solana",
            "address": mint_address,
        },
    )


async def get_token_price(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/price",
        params={
            "blockchain": "Solana",
            "address": mint_address,
        },
    )


async def get_token_trades(
    mint_address: str,
    limit: int = 100,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    limit = max(1, min(limit, 500))

    return await _request(
        "/token/trades",
        params={
            "blockchain": "Solana",
            "address": mint_address,
            "limit": limit,
        },
    )


async def get_token_holder_positions(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/holder-positions",
        params={
            "blockchain": "Solana",
            "address": mint_address,
        },
    )


async def get_token_trader_positions(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/trader-positions",
        params={
            "blockchain": "Solana",
            "address": mint_address,
        },
    )


async def get_token_security(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/security",
        params={
            "blockchain": "Solana",
            "address": mint_address,
        },
    )


async def get_token_dev_history(
    mint_address: str,
) -> dict[str, Any]:

    if not mint_address:
        raise ValueError(
            "mint_address مطلوب."
        )

    return await _request(
        "/token/dev-history",
        params={
            "blockchain": "Solana",
            "address": mint_address,
        },
    )


async def get_wallet_trades(
    wallet_address: str,
) -> dict[str, Any]:

    if not wallet_address:
        raise ValueError(
            "wallet_address مطلوب."
        )

    return await _request(
        "/wallet/trades",
        params={
            "blockchain": "Solana",
            "address": wallet_address,
        },
    )


async def get_wallet_analysis(
    wallet_address: str,
) -> dict[str, Any]:

    if not wallet_address:
        raise ValueError(
            "wallet_address مطلوب."
        )

    return await _request(
        "/wallet/analysis",
        params={
            "blockchain": "Solana",
            "address": wallet_address,
        },
    )


async def get_wallet_funding(
    wallet_address: str,
) -> dict[str, Any]:

    if not wallet_address:
        raise ValueError(
            "wallet_address مطلوب."
        )

    return await _request(
        "/wallet/funding",
        params={
            "blockchain": "Solana",
            "address": wallet_address,
        },
    )


async def get_wallet_labels(
    wallet_address: str,
) -> dict[str, Any]:

    if not wallet_address:
        raise ValueError(
            "wallet_address مطلوب."
        )

    return await _request(
        "/wallet/labels",
        params={
            "blockchain": "Solana",
            "address": wallet_address,
        },
  )
