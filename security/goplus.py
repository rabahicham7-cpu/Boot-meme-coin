import aiohttp


GOPLUS_SOLANA_SECURITY_URL = (
    "https://api.gopluslabs.io/api/v1/solana/token_security"
)


async def get_token_security(mint_address: str):

    timeout = aiohttp.ClientTimeout(total=15)

    params = {
        "contract_addresses": mint_address
    }

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.get(
            GOPLUS_SOLANA_SECURITY_URL,
            params=params
        ) as response:

            data = await response.json(
                content_type=None
            )

            if response.status != 200:
                raise RuntimeError(
                    f"GoPlus security HTTP error: "
                    f"{response.status} - {data}"
                )

            if data.get("code") != 1:
                raise RuntimeError(
                    f"GoPlus security failed: {data}"
                )

            return data
