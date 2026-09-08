
import os
import time
import hmac
import hashlib
import aiohttp


GOPLUS_APP_KEY = os.getenv("GOPLUS_APP_KEY")
GOPLUS_APP_SECRET = os.getenv("GOPLUS_APP_SECRET")

TOKEN_URL = "https://api.gopluslabs.io/api/v1/token_security/solana"


def generate_signature(timestamp: str) -> str:
    message = f"{GOPLUS_APP_KEY}{timestamp}"

    return hmac.new(
        GOPLUS_APP_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()


async def get_token_security(mint_address: str):
    if not GOPLUS_APP_KEY or not GOPLUS_APP_SECRET:
        raise RuntimeError("GoPlus API credentials غير موجودة")

    timestamp = str(int(time.time()))

    signature = generate_signature(timestamp)

    headers = {
        "Authorization": f"Bearer {GOPLUS_APP_KEY}",
        "X-API-KEY": GOPLUS_APP_KEY,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature,
    }

    params = {
        "contract_addresses": mint_address
    }

    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            TOKEN_URL,
            params=params,
            headers=headers
        ) as response:

            if response.status != 200:
                return None

            return await response.json()
