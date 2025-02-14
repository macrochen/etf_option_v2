import os
import time
import requests
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_pdf_urls(url):
    """
    从网页中提取PDF下载链接
    """
    # 初始化Chrome浏览器，使用 webdriver_manager 自动管理 ChromeDriver
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')  # 无界面模式
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # 访问页面
        driver.get(url)
        
        # 等待PDF链接加载
        wait = WebDriverWait(driver, 10)
        pdf_elements = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href$='.pdf']"))
        )
        
        # 提取所有PDF链接
        pdf_urls = [elem.get_attribute('href') for elem in pdf_elements]
        return pdf_urls
    
    finally:
        driver.quit()

def download_pdf(url, folder_path):
    """
    下载PDF文件到指定文件夹
    """
    try:
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        filename = unquote(url.split('/')[-1])
        file_path = os.path.join(folder_path, filename)
        
        if os.path.exists(file_path):
            print(f"文件已存在: {filename}")
            return
        
        # 设置请求头，模拟浏览器行为
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://powerupgammas.com/'
        }
        
        # 下载文件
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        print(f"成功下载: {filename}")
        # 添加延时，避免请求过快
        time.sleep(1)
        
    except Exception as e:
        print(f"下载失败 {url}: {str(e)}")

def get_article_urls(url):
    """
    从文章列表页面提取文章链接
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        article_elements = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.more-link"))
        )
        article_urls = [elem.get_attribute('href') for elem in article_elements]
        return article_urls
    finally:
        driver.quit()

def download_article_as_pdf(url, folder_path):
    """
    将文章页面下载为PDF
    """
    try:
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        # 从URL中提取文章标题作为文件名
        filename = url.rstrip('/').split('/')[-1] + '.pdf'
        file_path = os.path.join(folder_path, filename)
        
        if os.path.exists(file_path):
            print(f"文件已存在: {filename}")
            return
        
        # 初始化Chrome浏览器
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')  # 设置窗口大小
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        try:
            # 访问页面
            driver.get(url)
            # 等待页面加载完成
            time.sleep(3)
            
            # 打印为PDF
            print_options = {
                'landscape': False,
                'displayHeaderFooter': False,
                'printBackground': True,
                'preferCSSPageSize': True,
                'scale': 1,
                'paperWidth': 8.27,  # A4 宽度（英寸）
                'paperHeight': 11.69,  # A4 高度（英寸）
                'marginTop': 0,
                'marginBottom': 0,
                'marginLeft': 0,
                'marginRight': 0
            }
            
            # 获取PDF数据
            result = driver.execute_cdp_cmd('Page.printToPDF', print_options)
            if 'data' in result:
                import base64
                pdf_data = base64.b64decode(result['data'])
                
                # 保存PDF文件
                with open(file_path, 'wb') as f:
                    f.write(pdf_data)
                
                print(f"成功下载: {filename}")
            else:
                raise Exception("PDF数据生成失败")
            
            time.sleep(1)
            
        finally:
            driver.quit()
            
    except Exception as e:
        print(f"下载失败 {url}: {str(e)}")

def main():
    # 设置PDF保存路径
    pdf_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'articles_pdf')
    
    # 文章列表页面
    source_url = 'https://powerupgammas.com/articles/'
    
    # 获取文章链接
    article_urls = get_article_urls(source_url)
    print(f"找到 {len(article_urls)} 篇文章")
    
    # 先尝试下载第一篇文章
    if article_urls:
        download_article_as_pdf(article_urls[0], pdf_folder)

if __name__ == "__main__":
    main()