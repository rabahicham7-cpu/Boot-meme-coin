import os
import time
import hashlib
import aiohttp


GOPLUS_APP_KEY = os.getenv("GOPLUS_APP_KEY")
GOPLUS_APP_SECRET = os.getenv("GOPLUS_APP_SECRET")

GOPLUS_TOKEN_URL = "https://api.gopluslabs.io/api/v1/token"
GOPLUS_SOLANA_SECURITY_URL = (
    "https://api.gopluslabs.io/api/v1/solana/token_security"
)


async def get_access_token(session: aiohttp.ClientSession):
    if not GOPLUS_APP_KEY or not GOPLUS_APP_SECRET:
        raise RuntimeError("بيانات GoPlus غير موجودة")

    timestamp = str(int(time.time()))

    sign_string = (
        GOPLUS_APP_KEY
        + timestamp
        + GOPLUS_APP_SECRET
    )

    signature = hashlib.sha1(
        sign_string.encode("utf-8")
    ).hexdigest()

    payload = {
        "app_key": GOPLUS_APP_KEY,
        "sign": signature,
        "time": int(timestamp),
    }

    async with session.post(
        GOPLUS_TOKEN_URL,
        json=payload
    ) as response:

        data = await response.json()

        if response.status != 200:
            raise RuntimeError(
                f"GoPlus token error: {data}"
            )

        if data.get("code") != 1:
            raise RuntimeError(
                f"GoPlus authentication failed: {data}"
            )

        result = data.get("result") or {}

        access_token = result.get("access_token")

        if not access_token:
            raise RuntimeError(
                "GoPlus لم يُرجع Access Token"
            )

        return access_token


async def get_token_security(mint_address: str):
    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        access_token = await get_access_token(session)

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        params = {
            "contract_addresses": mint_address
        }

        async with session.get(
            GOPLUS_SOLANA_SECURITY_URL,
            params=params,
            headers=headers
        ) as response:

            data = await response.json()

            if response.status != 200:
                raise RuntimeError(
                    f"GoPlus security error: {data}"
                )

            if data.get("code") != 1:
                raise RuntimeError(
                    f"GoPlus security failed: {data}"
                )

            return data
