import re
from urllib.parse import urljoin

BASE_URL = "https://artso.artron.net"

# 读取测试页面
with open("test_list.html", "r", encoding="utf-8") as f:
    html = f.read()

# 提取所有艺术品链接
pattern = re.compile(r'<a[^>]*href="([^"]*paimai-art[0-9]+[^"]*)"[^>]*>([^<]*)</a>')
matches = pattern.findall(html)

print(f"找到 {len(matches)} 个艺术品链接：")
seen = set()
for href, name in matches:
    art_id = re.search(r"paimai-art(\d+)", href).group(1)
    if art_id not in seen:
        seen.add(art_id)
        name = name.strip()
        detail_url = urljoin(BASE_URL, href)
        print(f"ID: {art_id}, 名称: {name}, URL: {detail_url}")

print(f"\n共 {len(seen)} 个唯一艺术品")
