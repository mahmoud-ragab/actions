import socket
import requests
import whois
import tldextract
import concurrent.futures
import threading
from typing import Dict, Optional

# 全局锁：多线程写文件时防止多个线程同时写入造成内容错乱
lock = threading.Lock()

# 统一请求头，避免部分网站拦截默认请求
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

# 这些状态码通常说明网站是活跃的，域名大概率在使用
ACTIVE_HTTP_CODES = {200, 204, 301, 302, 307, 308, 401, 403}

# WHOIS 中常见的“未注册”关键词
AVAILABLE_KEYWORDS = [
    "no match for",
    "not found",
    "no data found",
    "domain not found",
    "status: free",
    "available",
    "no entries found",
    "object does not exist",
]

# WHOIS 中常见的“已注册”关键词
REGISTERED_KEYWORDS = [
    "domain name:",
    "registrar:",
    "creation date:",
    "registry expiry date:",
    "name server:",
    "updated date:",
    "status:",
]


def extract_registered_domain(domain: str) -> Optional[str]:
    """
    提取可注册主域名
    例如：
    aluno.barrosmelo.edu.br -> barrosmelo.edu.br
    mail.google.com -> google.com
    a.b.c.university.ac.uk -> university.ac.uk
    """
    domain = domain.strip().lower()

    # 去掉协议头和末尾斜杠
    domain = domain.replace("http://", "").replace("https://", "").strip("/")

    extracted = tldextract.extract(domain)

    # 没提取到主体或后缀，说明输入不合法
    if not extracted.domain or not extracted.suffix:
        return None

    return f"{extracted.domain}.{extracted.suffix}"


def has_dns_record(domain: str) -> bool:
    """
    检查域名是否存在 DNS 解析记录
    能解析通常说明域名已注册并且在使用
    不能解析不代表一定未注册
    """
    try:
        socket.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False
    except Exception:
        return False


def parse_whois_text(raw_text: str) -> str:
    """
    根据 WHOIS 文本粗略分类
    返回：
    AVAILABLE / REGISTERED / UNKNOWN
    """
    text = raw_text.lower()

    if any(keyword in text for keyword in AVAILABLE_KEYWORDS):
        return "AVAILABLE"

    if any(keyword in text for keyword in REGISTERED_KEYWORDS):
        return "REGISTERED"

    return "UNKNOWN"


def check_domain_by_whois(domain: str) -> str:
    """
    使用 WHOIS 查询域名状态
    返回：
    AVAILABLE / REGISTERED / UNKNOWN
    """
    try:
        info = whois.whois(domain)
        text = str(info).strip()

        if text:
            return parse_whois_text(text)

        return "UNKNOWN"

    except Exception as e:
        error_text = str(e).lower()

        # 只有异常文本明确说明未注册时，才判 AVAILABLE
        if any(keyword in error_text for keyword in AVAILABLE_KEYWORDS):
            return "AVAILABLE"

        # 其余情况一律 UNKNOWN，避免误判
        return "UNKNOWN"


def check_website_activity(domain: str, timeout: int = 5) -> bool:
    """
    检查网站是否有活跃迹象
    同时尝试：
    - https://domain
    - http://domain

    只要返回常见活跃状态码，就视为在使用
    """
    urls = [f"https://{domain}", f"http://{domain}"]

    session = requests.Session()
    session.headers.update(HEADERS)

    for url in urls:
        try:
            # 先 HEAD，请求更轻
            response = session.head(
                url,
                timeout=timeout,
                allow_redirects=True,
                verify=False,
            )

            if response.status_code in ACTIVE_HTTP_CODES:
                return True

            # 某些网站不支持 HEAD，再尝试 GET
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                verify=False,
            )

            if response.status_code in ACTIVE_HTTP_CODES:
                return True

        except requests.RequestException:
            continue
        except Exception:
            continue

    return False


def analyze_domain(domain: str) -> Dict[str, str]:
    """
    综合分析单个域名状态

    final_status 规则：
    1. DNS 活跃 -> REGISTERED
    2. 网站活跃 -> REGISTERED
    3. WHOIS 显示 REGISTERED -> REGISTERED
    4. WHOIS 显示 AVAILABLE，且 DNS/Web 都不活跃 -> AVAILABLE
    5. 其余 -> UNKNOWN
    """
    result = {
        "input": domain,
        "main_domain": "",
        "dns_active": "False",
        "web_active": "False",
        "whois_status": "UNKNOWN",
        "final_status": "UNKNOWN",
    }

    main_domain = extract_registered_domain(domain)

    if not main_domain:
        result["final_status"] = "UNKNOWN"
        return result

    result["main_domain"] = main_domain

    # 先检查 DNS
    dns_active = has_dns_record(main_domain)
    result["dns_active"] = str(dns_active)

    # 再查 WHOIS
    whois_status = check_domain_by_whois(main_domain)
    result["whois_status"] = whois_status

    # 再检查网站活跃性
    web_active = check_website_activity(main_domain)
    result["web_active"] = str(web_active)

    # 综合判断
    if dns_active:
        result["final_status"] = "REGISTERED"
        return result

    if web_active:
        result["final_status"] = "REGISTERED"
        return result

    if whois_status == "REGISTERED":
        result["final_status"] = "REGISTERED"
        return result

    if whois_status == "AVAILABLE" and not dns_active and not web_active:
        result["final_status"] = "AVAILABLE"
        return result

    result["final_status"] = "UNKNOWN"
    return result


def append_line(filename: str, text: str) -> None:
    """
    线程安全地追加写入一行
    """
    with lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def process_domain(domain: str) -> None:
    """
    处理单个域名
    只输出 AVAILABLE 和 UNKNOWN
    REGISTERED 只打印，不写文件
    """
    result = analyze_domain(domain)

    input_domain = result["input"]
    main_domain = result["main_domain"]
    dns_active = result["dns_active"]
    web_active = result["web_active"]
    whois_status = result["whois_status"]
    final_status = result["final_status"]

    log_line = (
        f"[{final_status}] input={input_domain} | "
        f"main={main_domain or 'N/A'} | "
        f"dns={dns_active} | web={web_active} | whois={whois_status}"
    )
    print(log_line)

    # 只有明确可注册的才写入 available_domains.txt
    if final_status == "AVAILABLE":
        append_line("available_domains.txt", main_domain)

    # 查不准的写入 unknown_domains.txt，方便后续人工复查
    elif final_status == "UNKNOWN":
        append_line("unknown_domains.txt", log_line)

    # REGISTERED 不生成文件，只打印日志


def load_domains(file_path: str) -> list:
    """
    从文件读取域名
    支持：
    - 一行一个
    - 逗号分隔
    - 混合格式

    自动去重并保持原顺序
    """
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()

    raw_domains = [
        d.strip()
        for d in content.replace(",", "\n").splitlines()
        if d.strip()
    ]

    seen = set()
    clean_domains = []

    for d in raw_domains:
        if d not in seen:
            seen.add(d)
            clean_domains.append(d)

    return clean_domains


def clear_output_files() -> None:
    """
    运行前清空输出文件
    这里只保留两个文件
    """
    for filename in [
        "available_domains.txt",
        "unknown_domains.txt",
    ]:
        open(filename, "w", encoding="utf-8").close()


def main():
    """
    主函数流程：
    1. 读取 domain.txt
    2. 清空输出文件
    3. 多线程并发处理
    4. 输出完成提示
    """
    file_path = "domain.txt"

    try:
        domains = load_domains(file_path)

        if not domains:
            print("❌ domain.txt 里没有有效域名")
            return

        clear_output_files()

        # 并发别太大，避免 WHOIS 被限流
        max_workers = 10

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(process_domain, domains)

        print("\n✅ 处理完成")
        print("大概率可注册：available_domains.txt")
        print("待人工复核：unknown_domains.txt")

    except FileNotFoundError:
        print("❌ 未找到 domain.txt 文件，请检查文件路径。")
    except Exception as e:
        print(f"❌ 程序运行出错：{e}")


if __name__ == "__main__":
    # 屏蔽 HTTPS 证书警告
    requests.packages.urllib3.disable_warnings()
    main()
