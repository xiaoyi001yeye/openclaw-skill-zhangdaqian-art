import os
import json
import time
import re
import argparse
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

# 配置
BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 2  # 请求间隔，秒
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

def get_session() -> requests.Session:
    """创建带UA的session"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Referer": BASE_URL
    })
    return session

def extract_art_id(detail_url: str) -> Optional[str]:
    """从详情页URL提取艺术品ID"""
    match = re.search(r"paimai-art(\d+)", detail_url)
    return match.group(1) if match else None

def load_existing_art_ids() -> set:
    """加载已存在的艺术品ID集合"""
    art_ids = set()
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            art_id = filename[:-5]
            art_ids.add(art_id)
    return art_ids

def crawl_list_page(session: requests.Session, keyword: str, page: int) -> List[Dict]:
    """抓取单页列表数据"""
    url = SEARCH_URL_TPL.format(keyword=quote(keyword), page=page)
    print(f"正在抓取第 {page} 页: {url}")
    
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"抓取列表页失败: {e}")
        return []
    
    art_items = []
    items = soup.select(".listItem")
    if not items:
        print("当前页无数据")
        return []
    
    for item in items:
        try:
            # 基础信息
            name_elem = item.select_one(".title a")
            if not name_elem:
                continue
                
            name = name_elem.get_text(strip=True)
            detail_url = urljoin(BASE_URL, name_elem["href"])
            art_id = extract_art_id(detail_url)
            if not art_id:
                continue
                
            # 艺术家
            artist = item.select_one(".artist").get_text(strip=True) if item.select_one(".artist") else ""
            # 拍卖行
            auction_house = item.select_one(".company").get_text(strip=True) if item.select_one(".company") else ""
            # 拍卖时间
            auction_time = item.select_one(".time").get_text(strip=True) if item.select_one(".time") else ""
            # 估价
            estimate = item.select_one(".estimate").get_text(strip=True) if item.select_one(".estimate") else ""
            # 成交价
            hammer_price = item.select_one(".price").get_text(strip=True) if item.select_one(".price") else ""
            # 拍品号
            lot_number = item.select_one(".lot").get_text(strip=True) if item.select_one(".lot") else ""
            
            art_items.append({
                "id": art_id,
                "name": name,
                "artist": artist,
                "auction_house": auction_house,
                "auction_time": auction_time,
                "lot_number": lot_number,
                "estimate": estimate,
                "hammer_price": hammer_price,
                "list_url": url,
                "detail_url": detail_url,
                "crawl_time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            print(f"解析列表项失败: {e}")
            continue
    
    return art_items

def crawl_detail_page(session: requests.Session, art_item: Dict) -> Dict:
    """抓取详情页补充数据"""
    detail_url = art_item["detail_url"]
    print(f"正在抓取详情页: {detail_url}")
    
    try:
        resp = session.get(detail_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"抓取详情页失败: {e}")
        return art_item
    
    # 详情页字段提取
    detail_info = {}
    
    # 拍卖专场
    session_elem = soup.select_one(".session a")
    if session_elem:
        detail_info["auction_session"] = session_elem.get_text(strip=True)
    
    # 作品信息栏
    info_items = soup.select(".inforTxt li")
    for item in info_items:
        text = item.get_text(strip=True)
        if "尺寸：" in text:
            detail_info["size"] = text.replace("尺寸：", "").strip()
        elif "材质：" in text:
            detail_info["material"] = text.replace("材质：", "").strip()
        elif "年代：" in text:
            detail_info["creation_year"] = text.replace("年代：", "").strip()
        elif "签名：" in text:
            detail_info["signature"] = text.replace("签名：", "").strip()
        elif "款识：" in text:
            detail_info["inscription"] = text.replace("款识：", "").strip()
        elif "出版：" in text:
            detail_info["published"] = text.replace("出版：", "").strip()
        elif "展览：" in text:
            detail_info["exhibited"] = text.replace("展览：", "").strip()
        elif "来源：" in text:
            detail_info["provenance"] = text.replace("来源：", "").strip()
        elif "备注：" in text:
            detail_info["remark"] = text.replace("备注：", "").strip()
    
    # 作品描述
    desc_elem = soup.select_one(".describeTxt")
    if desc_elem:
        detail_info["description"] = desc_elem.get_text(strip=True)
    
    # 合并数据
    art_item.update(detail_info)
    return art_item

def save_art_data(art_item: Dict):
    """保存艺术品数据到JSON文件"""
    file_path = os.path.join(DATA_DIR, f"{art_item['id']}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(art_item, f, ensure_ascii=False, indent=2)
    print(f"已保存: {art_item['name']}")

def crawl_keyword(keyword: str):
    """根据关键字抓取所有艺术品数据"""
    session = get_session()
    existing_ids = load_existing_art_ids()
    page = 1
    total_crawled = 0
    
    while True:
        list_items = crawl_list_page(session, keyword, page)
        if not list_items:
            break
            
        new_count = 0
        for item in list_items:
            if item["id"] in existing_ids:
                print(f"跳过已存在: {item['name']}")
                continue
                
            # 抓取详情页
            time.sleep(REQUEST_DELAY)
            full_item = crawl_detail_page(session, item)
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
    parser = argparse.ArgumentParser(description="雅昌艺术网艺术品抓取工具")
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
        # 安装依赖
        try:
            import requests
            import bs4
        except ImportError:
            print("正在安装依赖...")
            os.system("pip install requests beautifulsoup4")
            import requests
            import bs4
            
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
