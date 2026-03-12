import urllib.request
import urllib.error
from typing import Optional
from urllib.parse import quote

BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def http_get(url: str, timeout: int = 30) -> Optional[str]:
    """使用urllib发送GET请求"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": BASE_URL
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            print(f"请求成功，状态码: {resp.getcode()}")
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"请求失败: {e}")
        return None

# 测试请求
url = SEARCH_URL_TPL.format(keyword=quote("张大千"), page=1)
print(f"测试请求: {url}")
html = http_get(url)
if html:
    print(f"页面大小: {len(html)} 字节")
    print("前500字符:")
    print(html[:500])
