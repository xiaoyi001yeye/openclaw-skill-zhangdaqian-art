import os
import json
import time
import re
import argparse
import subprocess
from urllib.parse import quote, urljoin

# 配置
BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 2  # 请求间隔，秒
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_url(url: str) -> str:
    """使用curl获取页面内容"""
    cmd = [
        "curl",
        "-A", USER_AGENT,
        "--referer", BASE_URL,
        "--connect-timeout", "30",
        "--max-time", "60",
        "-s",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout

def extract_art_items(html: str) -> list:
    """从HTML中提取所有艺术品项"""
    # 匹配每个艺术品的完整块
    item_pattern = re.compile(r'<div class="imgWrap">.*?</h3>', re.DOTALL)
    items = item_pattern.findall(html)
    
    art_list = []
    for item_html in items:
        # 提取详情URL和ID
        url_match = re.search(r'<a href="([^"]*paimai-art[0-9]+[^"]*)"', item_html)
        if not url_match:
            continue
        detail_url = url_match.group(1)
        art_id = re.search(r"paimai-art(\d+)", detail_url).group(1)
        
        # 提取名称
        name_match = re.search(r'<a[^>]*paimai-art[^>]*>([^<]*)</a>', item_html)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        
        art_list.append({
            "id": art_id,
            "name": name,
            "detail_url": detail_url
        })
    
    return art_list

def load_existing_ids() -> set:
    """加载已存在的ID"""
    existing = set()
    for f in os.listdir(DATA_DIR):
        if f.endswith(".json"):
            existing.add(f[:-5])
    return existing

def crawl_keyword(keyword: str):
    """抓取关键字相关艺术品"""
    existing_ids = load_existing_ids()
    page = 1
    total_new = 0
    
    while True:
        print(f"正在抓取第 {page} 页...")
        url = SEARCH_URL_TPL.format(keyword=quote(keyword), page=page)
        html = fetch_url(url)
        
        items = extract_art_items(html)
        if not items:
            print("没有更多结果了")
            break
            
        new_count = 0
        for item in items:
            if item["id"] in existing_ids:
                print(f"跳过已存在: {item['name']}")
                continue
                
            # 保存基础数据
            item["crawl_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
            file_path = os.path.join(DATA_DIR, f"{item['id']}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
            
            print(f"新增: {item['name']}")
            existing_ids.add(item["id"])
            new_count += 1
            total_new += 1
            time.sleep(REQUEST_DELAY)
        
        print(f"第 {page} 页完成，新增 {new_count} 件")
        page += 1
        time.sleep(REQUEST_DELAY)
        
        # 简单的分页终止判断
        if len(items) < 10:
            break
    
    print(f"全部抓取完成，共新增 {total_new} 件赵云相关艺术品")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", help="搜索关键字")
    args = parser.parse_args()
    crawl_keyword(args.keyword)
