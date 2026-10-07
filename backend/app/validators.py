"""Input validation & sanitisation. Nothing here makes network calls."""
from __future__ import annotations
import ipaddress
import re
from urllib.parse import urlsplit

EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
GENERIC_RE = re.compile(r"^[A-Za-z0-9]{20,100}$")

# Networks we can actually verify. `id` is the EVM chain id used by explorer/GoPlus.
CHAINS = {
    "ethereum": {"id": 1, "label": "Ethereum", "explorer": "Etherscan", "dex": "ethereum", "cg": "ethereum"},
    "bsc": {"id": 56, "label": "BNB Smart Chain", "explorer": "BscScan", "dex": "bsc", "cg": "binance-smart-chain"},
    "polygon": {"id": 137, "label": "Polygon", "explorer": "PolygonScan", "dex": "polygon", "cg": "polygon-pos"},
    "arbitrum": {"id": 42161, "label": "Arbitrum One", "explorer": "Arbiscan", "dex": "arbitrum", "cg": "arbitrum-one"},
    "base": {"id": 8453, "label": "Base", "explorer": "BaseScan", "dex": "base", "cg": "base"},
}
# Valid-format networks this MVP cannot verify (reported honestly as unsupported).
UNSUPPORTED = {"solana": SOLANA_RE, "other": GENERIC_RE}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INVIS = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"')]+|(?<![@\w])(?:[a-z0-9-]+\.)+(?:com|net|org|io|xyz|top|co|in|app|live|site|online|cc|vip|club|finance|exchange|example)\b[^\s<>\"')]*", re.I)


class ValidationFailure(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field, self.message = field, message


def sanitize_text(text: str | None, limit: int) -> str:
    t = _INVIS.sub("", _CTRL.sub("", text or ""))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) > limit:
        raise ValidationFailure("text", f"The text is too long ({len(t):,} characters). Please shorten it to {limit:,} characters or fewer.")
    return t


def validate_address(address: str, chain: str) -> str:
    """Return the normalised address, or raise ValidationFailure. A malformed address is a user error, not a risk signal."""
    address = (address or "").strip()
    if not address:
        return ""
    chain = (chain or "").lower()
    if not chain:
        raise ValidationFailure("chain", "Choose the blockchain this contract address belongs to.")
    if chain in CHAINS:
        if not EVM_RE.match(address):
            raise ValidationFailure("contract_address", f"This is not a valid {CHAINS[chain]['label']} address. It should start with 0x followed by 40 hexadecimal characters.")
        return address.lower()
    if chain in UNSUPPORTED:
        if not UNSUPPORTED[chain].match(address):
            raise ValidationFailure("contract_address", f"This does not look like a valid {chain.title()} address.")
        return address
    raise ValidationFailure("chain", f"Unknown blockchain '{chain[:30]}'.")


def registrable_domain(host: str) -> str:
    """Heuristic eTLD+1 (no public-suffix list offline). Good enough for RDAP lookups of common domains."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "gov", "ac", "edu", "nic"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_url(raw: str) -> dict:
    """Validate a user-supplied link. We never fetch the page itself; we only extract a public hostname
    for RDAP / Safe Browsing lookups. IPs, localhost and private names are rejected (SSRF hygiene)."""
    raw = (raw or "").strip()
    if len(raw) > 2048:
        raise ValidationFailure("url", "The link is too long to analyse.")
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw):
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise ValidationFailure("url", "This does not look like a valid web address.")
    if parts.scheme not in ("http", "https"):
        raise ValidationFailure("url", "Only http:// and https:// links can be analysed.")
    if parts.username or parts.password:
        raise ValidationFailure("url", "Links containing a username or password are not accepted.")
    if port not in (None, 80, 443):
        raise ValidationFailure("url", "Links with custom ports are not accepted.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValidationFailure("url", "This does not look like a valid web address.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValidationFailure("url", "Links that use a raw IP address cannot be analysed. Paste the website name instead.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValidationFailure("url", "This web address contains invalid characters.")
    bad_suffix = (".local", ".internal", ".localhost", ".lan", ".home.arpa", ".intranet")
    if "." not in host or host == "localhost" or host.endswith(bad_suffix):
        raise ValidationFailure("url", "Only public website names can be analysed.")
    labels = host.split(".")
    if not all(re.fullmatch(r"(?!-)[a-z0-9-]{1,63}(?<!-)", l) for l in labels) or not re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]+", labels[-1]):
        raise ValidationFailure("url", "This web address contains invalid characters.")
    return {"url": f"{parts.scheme}://{host}{parts.path or ''}"[:300], "host": host, "domain": registrable_domain(host)}
