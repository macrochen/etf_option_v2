import pytesseract
from PIL import Image, ImageEnhance, ImageOps
import re
import io
import logging

class OCRService:
    @staticmethod
    def parse_screenshot(image_bytes: bytes) -> dict:
        """
        解析截图内容，返回所有识别到的文本块及其坐标
        (已优化：智能间距合并，解决连体字和拆散问题)
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            
            # --- 图像预处理增强 ---
            image = image.convert('L')
            
            # 提高对比度增强系数，帮助识别灰色字体
            # cutoff用于忽略直方图两端极值，使中间的灰色更明显
            image = ImageOps.autocontrast(image, cutoff=2) 
            
            width, height = image.size
            scale_factor = 2
            new_size = (int(width * scale_factor), int(height * scale_factor))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # 适度锐化
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)
            
            # 识别
            data = pytesseract.image_to_data(image, lang='chi_sim+eng', output_type=pytesseract.Output.DICT)
            
            # --- 智能聚合逻辑 ---
            blocks = [] 
            current_block = None
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text = data['text'][i].strip()
                if not text:
                    continue
                
                # 坐标信息
                l = data['left'][i]
                t = data['top'][i]
                w = data['width'][i]
                h = data['height'][i]
                r = l + w
                b = t + h
                
                # 逻辑行号 (Tesseract 自己的行划分)
                line_id = f"{data['block_num'][i]}_{data['par_num'][i]}_{data['line_num'][i]}"
                
                should_merge = False
                if current_block and current_block['line_id'] == line_id:
                    # 在同一行，计算间距
                    gap = l - current_block['right']
                    avg_height = (h + (current_block['bottom'] - current_block['top'])) / 2
                    
                    # 阈值判断：
                    # 1. 间距小于字高的一半 -> 视为同个词 (如 "科" "创")
                    # 2. 间距很大 -> 视为不同词 (如 "市价" ... "123")
                    if gap < avg_height * 0.6: 
                        should_merge = True
                    
                    # 特殊处理：如果前一个是中文，当前也是中文，放宽合并条件（因为中文有时候间距略大）
                    if not should_merge and re.match(r'[\u4e00-\u9fa5]', current_block['text'][-1:]) and re.match(r'[\u4e00-\u9fa5]', text):
                         if gap < avg_height * 1.2:
                             should_merge = True

                if should_merge:
                    # 合并
                    current_block['text'] += text
                    current_block['right'] = max(current_block['right'], r)
                    current_block['bottom'] = max(current_block['bottom'], b)
                    # top/left 保持 block 初始值，因为是向右延伸
                else:
                    # 结束上一个块，开始新块
                    if current_block:
                        blocks.append(current_block)
                    
                    current_block = {
                        'text': text,
                        'left': l, 'top': t, 'right': r, 'bottom': b,
                        'line_id': line_id
                    }
            
            # 追加最后一个块
            if current_block:
                blocks.append(current_block)
            
            # --- 转换为输出格式 ---
            raw_texts = []
            for block in blocks:
                text = block['text']
                
                # 清洗逻辑
                if re.match(r'^[^\w\u4e00-\u9fa5]+$', text):
                    continue
                # 单个字母过滤，但保留 'K', 'M' 等单位，或者保留数字
                if len(text) == 1 and re.match(r'[a-zA-Z]', text) and text not in ['K', 'M', 'B']:
                    continue
                
                # 还原坐标
                box = {
                    'left': block['left'] / scale_factor,
                    'top': block['top'] / scale_factor,
                    'width': (block['right'] - block['left']) / scale_factor,
                    'height': (block['bottom'] - block['top']) / scale_factor
                }
                
                raw_texts.append({
                    'text': text,
                    'box': box
                })
            
            return {
                'raw_texts': raw_texts,
                'image_size': {'width': width, 'height': height}
            }
            
        except Exception as e:
            logging.error(f"OCR parse error: {e}")
            return {'raw_texts': [], 'error': str(e)}

    @staticmethod
    def _parse_eng_only(image_bytes):
        # 废弃
        return []
