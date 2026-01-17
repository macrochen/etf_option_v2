import pytesseract
from PIL import Image
import re
import io
import logging

class OCRService:
    @staticmethod
    def parse_screenshot(image_bytes: bytes) -> list:
        """
        解析截图内容，提取资产列表
        返回格式: [{'symbol': '600519', 'name': '贵州茅台', 'quantity': 100, 'cost_price': 1500}, ...] 
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # 预处理图片可能提高准确率（灰度、二值化等），这里先做基础识别
            text = pytesseract.image_to_string(image, lang='chi_sim+eng') # 假设用户安装了中文包，否则fallback到eng
            
            lines = text.split('\n')
            assets = []
            
            # 简单的启发式解析
            # 模式1: 寻找6位数字代码 (如 600519, 510300, 159915)
            # 很多APP布局是： 名称 代码 ... 数量 ... 市值
            
            code_pattern = re.compile(r'(\d{6})')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 查找股票代码
                match = code_pattern.search(line)
                if match:
                    symbol = match.group(1)
                    
                    # 尝试从行中提取其他数字
                    # 移除代码，剩下的找数字
                    remaining = line.replace(symbol, ' ')
                    
                    # 提取所有数字（包括浮点数）
                    numbers = re.findall(r'-?\d+\.?\d*', remaining)
                    
                    # 提取文字作为名称 (简单过滤掉数字和特殊字符)
                    # 这里假设名称在代码前面或附近
                    name_part = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', remaining)
                    
                    # 简单的推断逻辑：
                    # 通常截图里会有：持仓数量、成本/现价、市值
                    # 这很难精确，所以我们返回原始识别结果给前端，让用户选
                    
                    asset = {
                        'symbol': symbol,
                        'name': name_part or '未知名称',
                        'raw_line': line,
                        'suggested_quantity': 0,
                        'suggested_cost': 0
                    }
                    
                    # 尝试猜测数量和成本
                    # 假设：数量通常是整数或2位小数，成本通常是价格
                    if len(numbers) >= 2:
                        # 这是一个非常粗略的猜测，完全依赖于APP的排版
                        # 比如: 数量 100, 成本 50.5
                        # 往往最大的那个数字可能是市值，把它排除？
                        try:
                            valid_nums = [float(n) for n in numbers]
                            # 假设第一个是数量，第二个是价格（或者反过来，需要用户确认）
                            asset['suggested_quantity'] = valid_nums[0]
                            asset['suggested_cost'] = valid_nums[1] if len(valid_nums) > 1 else 0
                        except:
                            pass
                            
                    assets.append(asset)
            
            return assets
            
        except Exception as e:
            logging.error(f"OCR parse error: {e}")
            # 如果没有中文包，尝试仅英文
            if "chi_sim" in str(e):
                 logging.warning("chi_sim not found, retrying with eng only")
                 return OCRService._parse_eng_only(image_bytes)
            return []

    @staticmethod
    def _parse_eng_only(image_bytes):
        """仅使用英文模型重试（针对代码）"""
        try:
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image, lang='eng')
            lines = text.split('\n')
            assets = []
            code_pattern = re.compile(r'(\d{6})')
            
            for line in lines:
                match = code_pattern.search(line)
                if match:
                    symbol = match.group(1)
                    numbers = re.findall(r'-?\d+\.?\d*', line.replace(symbol, ' '))
                    asset = {
                        'symbol': symbol,
                        'name': '请手动输入',
                        'raw_line': line,
                        'suggested_quantity': 0,
                        'suggested_cost': 0
                    }
                    if len(numbers) >= 2:
                        try:
                            asset['suggested_quantity'] = float(numbers[0])
                            asset['suggested_cost'] = float(numbers[1])
                        except: pass
                    assets.append(asset)
            return assets
        except Exception as e:
             logging.error(f"OCR retry error: {e}")
             return []
