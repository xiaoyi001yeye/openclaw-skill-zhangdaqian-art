import os
import json
import time
import re
import argparse
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
from html.parser import HTMLParser
import urllib.request

# 配置
BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 2  # 请求间隔，秒
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

class ListPageParser(HTMLParser):
    """列表页解析器"""
    def __init__(self):
        super().__init__()
        self.in_list_item = False
        self.in_title = False
        self.in_artist = False
        self.in_company = False
        self.in_time = False
        self.in_estimate = False
        self.in_price = False
        self.in_lot = False
        self.current_item = {}
        self.items = []
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        if tag == "div" and "listItem" in class_name:
            self.in_list_item = True
            self.current_item = {}
        elif self.in_list_item and tag == "div" and "title" in class_name:
            self.in_title = True
        elif self.in_list_item and tag == "a" and self.in_title:
            self.current_item["detail_url"] = urljoin(BASE_URL, attrs_dict.get("href", ""))
            # 提取ID
            match = re.search(r"paimai-art(\d+)", self.current_item["detail_url"])
            if match:
                self.current_item["id"] = match.group(1)
        elif self.in_list_item and tag == "div" and "artist" in class_name:
            self.in_artist = True
        elif self.in_list_item and tag == "div" and "company" in class_name:
            self.in_company = True
        elif self.in_list_item and tag == "div" and "time" in class_name:
            self.in_time = True
        elif self.in_list_item and tag == "div" and "estimate" in class_name:
            self.in_estimate = True
        elif self.in_list_item and tag == "div" and "price" in class_name:
            self.in_price = True
        elif self.in_list_item and tag == "div" and "lot" in class_name:
            self.in_lot = True
    
    def handle_endtag(self, tag):
        if tag == "div" and self.in_list_item:
            if self.current_item.get("id") and self.current_item.get("name"):
                self.items.append(self.current_item.copy())
            self.in_list_item = False
        elif tag == "div" and self.in_title:
            self.in_title = False
        elif tag == "div" and self.in_artist:
            self.in_artist = False
        elif tag == "div" and self.in_company:
            self.in_company = False
        elif tag == "div" and self.in_time:
            self.in_time = False
        elif tag == "div" and self.in_estimate:
            self.in_estimate = False
        elif tag == "div" and self.in_price:
            self.in_price = False
        elif tag == "div" and self.in_lot:
            self.in_lot = False
    
    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
            
        if self.in_title:
            self.current_item["name"] = data
        elif self.in_artist:
            self.current_item["artist"] = data
        elif self.in_company:
            self.current_item["auction_house"] = data
        elif self.in_time:
            self.current_item["auction_time"] = data
        elif self.in_estimate:
            self.current_item["estimate"] = data
        elif self.in_price:
            self.current_item["hammer_price"] = data
        elif self.in_lot:
            self.current_item["lot_number"] = data

class DetailPageParser(HTMLParser):
    """详情页解析器"""
    def __init__(self):
        super().__init__()
        self.in_session = False
        self.in_infor_txt = False
        self.in_describe = False
        self.current_field = ""
        self.result = {}
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        if tag == "div" and "session" in class_name:
            self.in_session = True
        elif tag == "ul" and "inforTxt" in class_name:
            self.in_infor_txt = True
        elif tag == "div" and "describeTxt" in class_name:
            self.in_describe = True
        elif self.in_infor_txt and tag == "li":
            self.current_field = ""
    
    def handle_endtag(self, tag):
        if tag == "div" and self.in_session:
            self.in_session = False
        elif tag == "ul" and self.in_infor_txt:
            self.in_infor_txt = False
        elif tag == "div" and self.in_describe:
            self.in_describe = False
    
    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
            
        if self.in_session and tag == "a":
            self.result["auction_session"] = data
        elif self.in_describe:
            self.result["description"] = self.result.get("description", "") + data
        elif self.in_infor_txt:
            self.current_field += data
            if "：" in self.current_field:
                key, value = self.current_field.split("：", 1)
                key = key.strip()
                value = value.strip()
                if key == "尺寸":
                    self.result["size"] = value
                elif key == "材质":
                    self.result["material"] = value
                elif key == "年代":
                    self.result["creation_year"] = value
                elif key == "签名":
                    self.result["signature"] = value
                elif key == "款识":
                    self.result["inscription"] = value
                elif key == "出版":
                    self.result["published"] = value
                elif key == "展览":
                    self.result["exhibited"] = value
                elif key == "来源":
                    self.result["provenance"] = value
                elif key == "备注":
                    self.result["remark"] = value

def fetch_url(url: str) -> Optional[str]:
    """使用urllib获取页面内容"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"请求失败 {url}: {e}")
        return None

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

def crawl_list_page(keyword: str, page: int) -> List[Dict]:
    """抓取单页列表数据"""
    url = SEARCH_URL_TPL.format(keyword=quote(keyword), page=page)
    print(f"正在抓取第 {page} 页: {url}")
    
    html = fetch_url(url)
    if not html:
        return []
    
    parser = ListPageParser()
    parser.feed(html)
    return parser.items

def crawl_detail_page(art_item: Dict) -> Dict:
    """抓取详情页补充数据"""
    detail_url = art_item["detail_url"]
    print(f"正在抓取详情页: {detail_url}")
    
    html = fetch_url(detail_url)
    if not html:
        return art_item
    
    parser = DetailPageParser()
    parser.feed(html)
    art_item.update(parser.result)
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
            if "id" not in item or item["id"] in existing_ids:
                print(f"跳过已存在或无效: {item.get('name', '未知')}")
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
        
        # 检测是否到最后一页
        if len(list_items) < 10:
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
    parser = argparse.ArgumentParser(description="雅昌艺术网艺术品抓取工具（无依赖版）")
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
