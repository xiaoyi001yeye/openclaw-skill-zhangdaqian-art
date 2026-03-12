import os
import json
import time
import re
import argparse
import atexit
import signal
import urllib.request
import urllib.error
from typing import List, Dict, Optional
from urllib.parse import quote, urljoin
from html.parser import HTMLParser

# 使用系统自带的urllib代替requests，无需额外依赖
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 进度文件路径
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crawl_progress.json")

# 配置
BASE_URL = "https://artso.artron.net"
SEARCH_URL_TPL = "https://artso.artron.net/auction/search_auction.php?keyword={keyword}&page={page}"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
REQUEST_DELAY = 2  # 请求间隔，秒
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

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
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"请求失败: {e}")
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

def load_progress() -> Dict:
    """加载抓取进度"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"读取进度文件失败: {e}")
    return {
        "keyword": "",
        "current_page": 1,
        "total_crawled": 0,
        "last_update": "",
        "status": "idle"
    }

def save_progress(progress: Dict):
    """保存抓取进度"""
    progress["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def report_progress(progress: Dict, final: bool = False):
    """上报抓取进度"""
    status = "完成" if final else "进行中"
    print(f"\n=== 抓取进度{status} ===")
    print(f"关键字: {progress['keyword']}")
    print(f"当前页码: {progress['current_page']}")
    print(f"已抓取总数: {progress['total_crawled']}")
    print(f"最后更新: {progress['last_update']}")
    print("========================\n")

def cleanup_handler(signum, frame):
    """信号处理函数，处理异常退出"""
    progress = load_progress()
    if progress["status"] == "running":
        progress["status"] = "interrupted"
        save_progress(progress)
        print(f"\n⚠️  抓取任务被中断，当前进度已保存:")
        report_progress(progress)
    exit(1)

# 注册信号处理
signal.signal(signal.SIGINT, cleanup_handler)
signal.signal(signal.SIGTERM, cleanup_handler)

# 注册退出处理
def atexit_handler():
    progress = load_progress()
    if progress["status"] == "running":
        progress.update({"status": "stopped"})
        save_progress(progress)
        print(f"\n⚠️  抓取任务意外终止，当前进度已保存:")
        report_progress(progress)

atexit.register(atexit_handler)

class ArtListParser(HTMLParser):
    """列表页HTML解析器"""
    def __init__(self):
        super().__init__()
        self.art_items = []
        self.current_item = {}
        self.in_list_item = False
        self.in_title = False
        self.in_artist = False
        self.in_company = False
        self.in_time = False
        self.in_estimate = False
        self.in_price = False
        self.in_lot = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        if tag == "div" and "listItem" in class_name:
            self.in_list_item = True
            self.current_item = {}
        elif self.in_list_item and tag == "div" and "title" in class_name:
            self.in_title = True
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
        elif self.in_title and tag == "a":
            self.current_item["detail_url"] = urljoin(BASE_URL, attrs_dict.get("href", ""))
            self.current_item["id"] = extract_art_id(self.current_item["detail_url"])
            
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
            
    def handle_endtag(self, tag):
        if tag == "div" and self.in_list_item:
            if "id" in self.current_item and "name" in self.current_item:
                self.art_items.append(self.current_item.copy())
            self.in_list_item = False
        elif self.in_title and tag == "div":
            self.in_title = False
        elif self.in_artist and tag == "div":
            self.in_artist = False
        elif self.in_company and tag == "div":
            self.in_company = False
        elif self.in_time and tag == "div":
            self.in_time = False
        elif self.in_estimate and tag == "div":
            self.in_estimate = False
        elif self.in_price and tag == "div":
            self.in_price = False
        elif self.in_lot and tag == "div":
            self.in_lot = False

def crawl_list_page(keyword: str, page: int) -> List[Dict]:
    """抓取单页列表数据"""
    url = SEARCH_URL_TPL.format(keyword=quote(keyword), page=page)
    print(f"正在抓取第 {page} 页: {url}")
    
    html = http_get(url)
    if not html:
        print("抓取列表页失败")
        return []
    
    parser = ArtListParser()
    try:
        parser.feed(html)
    except Exception as e:
        print(f"解析列表页失败: {e}")
        return []
    
    if not parser.art_items:
        print("当前页无数据")
        return []
    
    # 添加公共字段
    for item in parser.art_items:
        item["list_url"] = url
        item["crawl_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    return parser.art_items

class ArtDetailParser(HTMLParser):
    """详情页HTML解析器"""
    def __init__(self):
        super().__init__()
        self.detail_info = {}
        self.in_session = False
        self.in_info_item = False
        self.in_describe = False
        self.current_info_text = ""
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        if tag == "div" and "session" in class_name:
            self.in_session = True
        elif tag == "ul" and "inforTxt" in class_name:
            self.in_info_item = True
        elif tag == "div" and "describeTxt" in class_name:
            self.in_describe = True
            
    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
            
        if self.in_session:
            self.detail_info["auction_session"] = data
        elif self.in_info_item:
            self.current_info_text += data
        elif self.in_describe:
            self.detail_info["description"] = data
            
    def handle_endtag(self, tag):
        if self.in_session and tag == "div":
            self.in_session = False
        elif self.in_info_item and tag == "ul":
            self.in_info_item = False
            # 解析info文本
            lines = self.current_info_text.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if "尺寸：" in line:
                    self.detail_info["size"] = line.replace("尺寸：", "").strip()
                elif "材质：" in line:
                    self.detail_info["material"] = line.replace("材质：", "").strip()
                elif "年代：" in line:
                    self.detail_info["creation_year"] = line.replace("年代：", "").strip()
                elif "签名：" in line:
                    self.detail_info["signature"] = line.replace("签名：", "").strip()
                elif "款识：" in line:
                    self.detail_info["inscription"] = line.replace("款识：", "").strip()
                elif "出版：" in line:
                    self.detail_info["published"] = line.replace("出版：", "").strip()
                elif "展览：" in line:
                    self.detail_info["exhibited"] = line.replace("展览：", "").strip()
                elif "来源：" in line:
                    self.detail_info["provenance"] = line.replace("来源：", "").strip()
                elif "备注：" in line:
                    self.detail_info["remark"] = line.replace("备注：", "").strip()
        elif self.in_describe and tag == "div":
            self.in_describe = False

def crawl_detail_page(art_item: Dict) -> Dict:
    """抓取详情页补充数据"""
    detail_url = art_item["detail_url"]
    print(f"正在抓取详情页: {detail_url}")
    
    html = http_get(detail_url)
    if not html:
        print("抓取详情页失败")
        return art_item
    
    parser = ArtDetailParser()
    try:
        parser.feed(html)
    except Exception as e:
        print(f"解析详情页失败: {e}")
        return art_item
    
    # 合并数据
    art_item.update(parser.detail_info)
    return art_item

def save_art_data(art_item: Dict):
    """保存艺术品数据到JSON文件"""
    file_path = os.path.join(DATA_DIR, f"{art_item['id']}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(art_item, f, ensure_ascii=False, indent=2)
    print(f"已保存: {art_item['name']}")

def crawl_keyword(keyword: str):
    """根据关键字抓取所有艺术品数据"""
    existing_ids = load_existing_art_ids()
    
    # 加载之前的进度
    progress = load_progress()
    if progress.get("keyword") == keyword and progress.get("status") in ["interrupted", "stopped"]:
        page = progress["current_page"]
        total_crawled = progress["total_crawled"]
        print(f"\n🔄 检测到未完成的 '{keyword}' 抓取任务，从第 {page} 页继续...")
    else:
        page = 1
        total_crawled = 0
        print(f"\n🚀 开始新的抓取任务，关键字: {keyword}")
    
    # 初始化进度
    progress.update({
        "keyword": keyword,
        "current_page": page,
        "total_crawled": total_crawled,
        "status": "running"
    })
    save_progress(progress)
    report_progress(progress)
    
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
            
            # 实时更新进度
            progress["total_crawled"] = total_crawled
            save_progress(progress)
            
        print(f"第 {page} 页处理完成，新增 {new_count} 件")
        
        # 每处理完一页上报一次进度
        progress["current_page"] = page
        save_progress(progress)
        report_progress(progress)
        
        page += 1
        time.sleep(REQUEST_DELAY)
        
        # 检测是否到最后一页（当前页返回的数量少于常规数量时停止）
        if len(list_items) < 10:  # 每页默认显示10条
            break
    
    # 任务完成
    progress["status"] = "completed"
    save_progress(progress)
    report_progress(progress, final=True)
    print(f"✅ 抓取任务全部完成，共新增 {total_crawled} 件艺术品数据")

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

def show_progress():
    """显示当前抓取进度"""
    progress = load_progress()
    if progress["status"] == "idle":
        print("当前没有正在进行的抓取任务")
        return
    
    status_map = {
        "running": "🟢 运行中",
        "interrupted": "🔴 已中断",
        "stopped": "🟡 已停止",
        "completed": "✅ 已完成"
    }
    
    print("\n=== 当前抓取任务进度 ===")
    print(f"状态: {status_map.get(progress['status'], progress['status'])}")
    print(f"关键字: {progress['keyword']}")
    print(f"当前页码: {progress['current_page']}")
    print(f"已抓取总数: {progress['total_crawled']}")
    print(f"最后更新: {progress['last_update']}")
    print("========================\n")

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
    
    # 进度查询命令
    subparsers.add_parser("progress", help="查看当前抓取任务进度")
    
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
    elif args.command == "progress":
        show_progress()

if __name__ == "__main__":
    main()
