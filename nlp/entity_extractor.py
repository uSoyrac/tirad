"""
Asset entity çıkarma: Metin içinden hangi kripto/hisse bahsedildiğini bulur.
"""
import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Bilinen kripto semboller ve yaygın isimleri
CRYPTO_ALIASES = {
    "BTC": ["bitcoin", "btc", "₿"],
    "ETH": ["ethereum", "eth", "ether"],
    "SOL": ["solana", "sol"],
    "BNB": ["binance coin", "bnb"],
    "AVAX": ["avalanche", "avax"],
    "ADA": ["cardano", "ada"],
    "DOT": ["polkadot", "dot"],
    "LINK": ["chainlink", "link"],
    "MATIC": ["polygon", "matic"],
    "ATOM": ["cosmos", "atom"],
    "NEAR": ["near protocol", "near"],
    "FTM": ["fantom", "ftm"],
    "ARB": ["arbitrum", "arb"],
    "OP": ["optimism", "op"],
    "SUI": ["sui"],
    "APT": ["aptos", "apt"],
    "INJ": ["injective", "inj"],
    "TIA": ["celestia", "tia"],
    "DOGE": ["dogecoin", "doge"],
    "SHIB": ["shiba", "shib"],
    "XRP": ["ripple", "xrp"],
    "LTC": ["litecoin", "ltc"],
    "UNI": ["uniswap", "uni"],
    "AAVE": ["aave"],
    "CRV": ["curve", "crv"],
    "MKR": ["maker", "mkr"],
    "PEPE": ["pepe"],
    "WIF": ["dogwifhat", "wif"],
    "BONK": ["bonk"],
    "TON": ["toncoin", "ton"],
    "NOT": ["notcoin", "not"],
    "TAO": ["bittensor", "tao"],
    "ENA": ["ethena", "ena"],
    "EIGEN": ["eigenlayer", "eigen"],
}

# Tüm alias'ları → sembol eşlemesi
ALIAS_TO_SYMBOL = {}
for symbol, aliases in CRYPTO_ALIASES.items():
    ALIAS_TO_SYMBOL[symbol.lower()] = symbol
    for alias in aliases:
        ALIAS_TO_SYMBOL[alias.lower()] = symbol

# BIST hisse kısa isimleri
BIST_ALIASES = {
    "THYAO": ["thy", "türk hava yolları", "türk havayolları", "turkish airlines", "tal"],
    "EREGL": ["ereğli", "erdemir", "eregli"],
    "GARAN": ["garanti", "garanti bankası", "garanti bank"],
    "SASA": ["sasa", "sasa polyester"],
    "ASELS": ["aselsan"],
    "KCHOL": ["koç holding", "koc holding"],
    "BIMAS": ["bim", "bim mağazaları"],
    "TUPRS": ["tüpraş", "tupras"],
    "AKBNK": ["akbank"],
    "ISCTR": ["iş bankası", "is bankasi"],
    "XU100": ["bist 100", "borsa istanbul", "bist100", "xu100"],
}

BIST_ALIAS_MAP = {}
for symbol, aliases in BIST_ALIASES.items():
    BIST_ALIAS_MAP[symbol.lower()] = symbol
    for a in aliases:
        BIST_ALIAS_MAP[a.lower()] = symbol


def extract_crypto_mentions(text: str) -> Counter:
    """Metinden kripto asset mention'larını çıkarır."""
    text_lower = text.lower()
    mentions = Counter()

    # Doğrudan sembol eşleştirme ($BTC, #ETH formatları dahil)
    pattern = r'\$([A-Z]{2,10})|#([A-Z]{2,10})\b'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        symbol = (match.group(1) or match.group(2)).upper()
        if symbol in CRYPTO_ALIASES:
            mentions[symbol] += 2  # $ ve # formatları daha güçlü sinyal

    # Alias eşleştirme
    for alias, symbol in ALIAS_TO_SYMBOL.items():
        if len(alias) <= 2:  # Çok kısa aliaslar yanlış pozitif üretir
            # Kelime sınırı ile ara
            if re.search(rf'\b{re.escape(alias)}\b', text_lower):
                mentions[symbol] += 1
        elif alias in text_lower:
            mentions[symbol] += 1

    return mentions


def extract_bist_mentions(text: str) -> Counter:
    """Metinden BIST hisse mention'larını çıkarır."""
    text_lower = text.lower()
    mentions = Counter()

    for alias, symbol in BIST_ALIAS_MAP.items():
        if alias in text_lower:
            mentions[symbol] += 1

    return mentions


def get_top_mentioned_assets(texts: list[str], top_n: int = 5, asset_type: str = "crypto") -> list[str]:
    """
    Birden fazla metin içinden en çok bahsedilen assetleri döndürür.
    asset_type: 'crypto' veya 'bist'
    """
    total_mentions = Counter()

    for text in texts:
        if asset_type == "crypto":
            total_mentions.update(extract_crypto_mentions(text))
        else:
            total_mentions.update(extract_bist_mentions(text))

    # Minimum 2 mention eşiği
    filtered = {k: v for k, v in total_mentions.items() if v >= 2}
    top = [symbol for symbol, _ in Counter(filtered).most_common(top_n)]

    logger.info(f"Top {top_n} mentioned ({asset_type}): {top}")
    return top
