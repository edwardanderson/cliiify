import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version


try:
    USER_AGENT = f'cliiify/{version("cliiify")}'
except PackageNotFoundError:
    USER_AGENT = 'cliiify'


def urlopen(url: str, timeout: float = 30):
    """Open a URL, identifying ourselves: Python's default user agent is
    rejected by some servers."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise OSError(f'server refused request ({exc.code} {exc.reason}): {url}') from exc
