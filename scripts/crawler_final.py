import os
import json
import time
import re
import argparse
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
import subprocess
from html.parser import HTMLParser

# 配置
BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 2  # 请求间隔，秒
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_url(url: str) -> Optional[str]:
    """使用curl获取页面内容"""
    try:
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
    except subprocess.CalledProcessError as e:
        print(f"请求失败 {url}: {e}")
        return None

def extract_art_list(html: str) -> List[Dict]:
    """从HTML中提取艺术品列表"""
    pattern = re.compile(r'<a[^>]*href="([^"]*paimai-art[0-9]+[^"]*)"[^>]*>([^<]*)</a>')
    matches = pattern.findall(html)
    
    art_list = []
    seen_ids = set()
    
    for href, name in matches:
        art_id_match = re.search(r"paimai-art(\d+)", href)
        if not art_id_match:
            continue
            
        art_id = art_id_match.group(1)
        if art_id in seen_ids:
            continue
            
        seen_ids.add(art_id)
        name = name.strip()
        # 去掉前面的拍品号，如 [0331]默雷 刘备关羽铜印 立轴 → 默雷 刘备关羽铜印 立轴
        name = re.sub(r'^\[\d+\]\s*', '', name)
        
        if not name:
            continue
            
        detail_url = urljoin(BASE_URL, href)
        art_list.append({
            "id": art_id,
            "name": name,
            "detail_url": detail_url
        })
    
    return art_list

def extract_detail_info(html: str) -> Dict:
    """从详情页提取详细信息"""
    info = {}
    
    # 提取艺术家
    artist_match = re.search(r'<div[^>]*class="[^"]*artist[^"]*"[^>]*>([^<]+)</div>', html)
    if artist_match:
        info["artist"] = artist_match.group(1).strip()
    
    # 提取拍卖行
    company_match = re.search(r'<div[^>]*class="[^"]*company[^"]*"[^>]*>([^<]+)</div>', html)
    if company_match:
        info["auction_house"] = company_match.group(1).strip()
    
    # 提取拍卖时间
    time_match = re.search(r'<div[^>]*class="[^"]*time[^"]*"[^>]*>([^<]+)</div>', html)
    if time_match:
        info["auction_time"] = time_match.group(1).strip()
    
    # 提取拍卖专场
    session_match = re.search(r'<div[^>]*class="[^"]*session[^"]*"[^>]*><a[^>]*>([^<]+)</a></div>', html)
    if session_match:
        info["auction_session"] = session_match.group(1).strip()
    
    # 提取拍品号
    lot_match = re.search(r'<div[^>]*class="[^"]*lot[^"]*"[^>]*>([^<]+)</div>', html)
    if lot_match:
        info["lot_number"] = lot_match.group(1).strip()
    
    # 提取估价
    estimate_match = re.search(r'<div[^>]*class="[^"]*estimate[^"]*"[^>]*>([^<]+)</div>', html)
    if estimate_match:
        info["estimate"] = estimate_match.group(1).strip()
    
    # 提取成交价
    price_match = re.search(r'<div[^>]*class="[^"]*price[^"]*"[^>]*>([^<]+)</div>', html)
    if price_match:
        info["hammer_price"] = price_match.group(1).strip()
    
    # 提取作品信息
    info_patterns = [
        ("size", r"尺寸：([^<]+)"),
        ("material", r"材质：([^<]+)"),
        ("creation_year", r"年代：([^<]+)"),
        ("signature", r"签名：([^<]+)"),
        ("inscription", r"款识：([^<]+)"),
        ("published", r"出版：([^<]+)"),
        ("exhibited", r"展览：([^<]+)"),
        ("provenance", r"来源：([^<]+)"),
        ("remark", r"备注：([^<]+)"),
    ]
    
    for key, pattern in info_patterns:
        match = re.search(pattern, html)
        if match:
            info[key] = match.group(1).strip()
    
    # 提取描述
    desc_match = re.search(r'<div[^>]*class="[^"]*describeTxt[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
    if desc_match:
        desc = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
        if desc:
            info["description"] = desc
    
    return info

def load_existing_art_ids() -> set:
    """加载已存在的艺术品ID集合"""
    art_ids = set()
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            art_id = filename[:-5]
            art_ids.add(art_id)
    return art_ids

def crawl_list_page(keyword: str, page: int) -> List[Dict]:
    """抓取单页列表数据"""
    url = SEARCH_URL_TPL.format(keyword=quote(keyword), page=page)
    print(f"正在抓取第 {page} 页: {url}")
    
    html = fetch_url(url)
    if not html:
        return []
    
    art_list = extract_art_list(html)
    print(f"当前页找到 {len(art_list)} 件艺术品")
    return art_list

def crawl_detail_page(art_item: Dict) -> Dict:
    """抓取详情页补充数据"""
    detail_url = art_item["detail_url"]
    print(f"正在抓取详情页: {detail_url}")
    
    html = fetch_url(detail_url)
    if not html:
        return art_item
    
    detail_info = extract_detail_info(html)
    art_item.update(detail_info)
    return art_item

def save_art_data(art_item: Dict):
    """保存艺术品数据到JSON文件"""
    file_path = os.path.join(DATA_DIR, f"{art_item['id']}.json")
    art_item["crawl_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(art_item, f, ensure_ascii=False, indent=2)
    print(f"已保存: {art_item['name']}")

def crawl_keyword(keyword: str):
    """根据关键字抓取所有艺术品数据"""
    existing_ids = load_existing_art_ids()
    page = 1
    total_crawled = 0
    
    while True:
        list_items = crawl_list_page(keyword, page)
        if not list_items:
            break
            
        new_count = 0
        for item in list_items:
            if item["id"] in existing_ids:
                print(f"跳过已存在: {item['name']}")
                continue
                
            # 抓取详情页
            time.sleep(REQUEST_DELAY)
            full_item = crawl_detail_page(item)
            save_art_data(full_item)
            existing_ids.add(item["id"])
            new_count += 1
            total_crawled += 1
            
        print(f"第 {page} 页处理完成，新增 {new_count} 件")
        page += 1
        time.sleep(REQUEST_DELAY)
        
        # 检测是否到最后一页（当前页返回的数量少于常规数量时停止）
        if len(list_items) < 10:  # 每页默认显示10条
            break
    
    print(f"抓取完成，共新增 {total_crawled} 件艺术品数据")

def list_arts() -> List[str]:
    """列出所有已抓取的艺术品名称"""
    art_names = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(DATA_DIR, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    art_names.append(data["name"])
            except Exception as e:
                print(f"读取文件失败 {filename}: {e}")
                continue
    
    return sorted(art_names)

def get_art_by_name(name: str) -> List[Dict]:
    """根据名称查询艺术品数据（模糊匹配）"""
    results = []
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(DATA_DIR, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if name.lower() in data["name"].lower():
                        results.append(data)
            except Exception as e:
                print(f"读取文件失败 {filename}: {e}")
                continue
    
    return results

def main():
    parser = argparse.ArgumentParser(description="雅昌艺术网艺术品抓取工具（最终版）")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 抓取命令
    crawl_parser = subparsers.add_parser("crawl", help="根据关键字抓取艺术品数据")
    crawl_parser.add_argument("keyword", help="搜索关键字")
    
    # 列表命令
    list_parser = subparsers.add_parser("list", help="列出所有已抓取的艺术品")
    
    # 查询命令
    get_parser = subparsers.add_parser("get", help="根据名称查询艺术品详情")
    get_parser.add_argument("name", help="艺术品名称")
    
    args = parser.parse_args()
    
    if args.command == "crawl":
        crawl_keyword(args.keyword)
    elif args.command == "list":
        arts = list_arts()
        if not arts:
            print("暂无已抓取的艺术品数据")
        else:
            print("已抓取的艺术品列表：")
            for i, name in enumerate(arts, 1):
                print(f"{i}. {name}")
    elif args.command == "get":
        results = get_art_by_name(args.name)
        if not results:
            print(f"未找到名称包含 '{args.name}' 的艺术品")
        else:
            print(f"找到 {len(results)} 个匹配结果：")
            for i, art in enumerate(results, 1):
                print(f"\n=== 结果 {i} ===")
                print(json.dumps(art, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
