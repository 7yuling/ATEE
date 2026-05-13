import ipaddress
from typing import Any


HEADER_PRIORITY = ("cf-connecting-ip", "x-forwarded-for", "x-real-ip")


class TrustedRealIpResolver:
    def __init__(self, trusted_proxy_cidrs: list[str] | None = None):
        self.trusted_proxy_cidrs = trusted_proxy_cidrs or []
        self._trusted_networks = []
        for cidr in self.trusted_proxy_cidrs:
            try:
                self._trusted_networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                continue

    def resolve(self, headers: dict[str, str], remote_addr: str) -> dict[str, Any]:
        remote_ip = self._parse_ip(remote_addr)
        normalized_headers = {k.lower(): v for k, v in headers.items()}

        if not self.trusted_proxy_cidrs:
            return {
                "client_ip": str(remote_ip) if remote_ip else remote_addr,
                "source": "remote_addr",
                "ip_trust_status": "untrusted_proxy_unknown",
                "can_ip_ban": False,
                "risk": "trusted_proxy_cidrs_not_configured",
            }

        if not remote_ip:
            return {
                "client_ip": remote_addr,
                "source": "remote_addr_invalid",
                "ip_trust_status": "invalid_remote_addr",
                "can_ip_ban": False,
                "risk": "remote_addr_invalid",
            }

        if self._is_trusted_proxy(remote_ip):
            for header in HEADER_PRIORITY:
                candidate = self._extract_header_ip(header, normalized_headers.get(header))
                if candidate:
                    return {
                        "client_ip": str(candidate),
                        "source": header,
                        "ip_trust_status": "trusted_proxy_header",
                        "can_ip_ban": True,
                        "risk": None,
                    }

        return {
            "client_ip": str(remote_ip),
            "source": "remote_addr",
            "ip_trust_status": "remote_addr_only",
            "can_ip_ban": True,
            "risk": None,
        }

    def _is_trusted_proxy(self, remote_ip: ipaddress._BaseAddress) -> bool:
        return any(remote_ip in network for network in self._trusted_networks)

    def _extract_header_ip(self, header: str, value: str | None) -> ipaddress._BaseAddress | None:
        if not value:
            return None
        first = value.split(",")[0].strip() if header == "x-forwarded-for" else value.strip()
        return self._parse_ip(first)

    def _parse_ip(self, value: str) -> ipaddress._BaseAddress | None:
        try:
            return ipaddress.ip_address(value)
        except ValueError:
            return None

