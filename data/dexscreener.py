import aiohttp


DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"


async def get_token_data(mint_address: str):
    url = f"{DEXSCREENER_URL}/{mint_address}"

    timeout = aiohttp.ClientTimeout(total=15)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:

            if response.status != 200:
                return None

            data = await response.json()

    pairs = data.get("pairs", [])

    # نحتفظ فقط بأزواج Solana
    solana_pairs = [
        pair for pair in pairs
        if pair.get("chainId") == "solana"
    ]

    if not solana_pairs:
        return None

    # اختيار الزوج صاحب أعلى سيولة
    best_pair = max(
        solana_pairs,
        key=lambda pair: float(
            pair.get("liquidity", {}).get("usd") or 0
        )
    )

    return best_pair
