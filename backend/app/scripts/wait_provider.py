"""Bounded provider readiness gate; does not modify the supplied sandbox."""

import time
import urllib.error
import urllib.request

from app.core.config import get_settings


def main():
    url = get_settings().payswift_base_url.rstrip("/") + "/health"
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise SystemExit("PaySwift readiness timed out")


if __name__ == "__main__":
    main()
