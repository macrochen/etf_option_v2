from pathlib import Path
import json
import logging
from typing import Any, Optional

# 配置文件路径
CONFIG_FILE = Path(__file__).parent.parent / 'config' / 'app_config.json'

def get_config_value(key_path: str, default: Any = None) -> Any:
    """
    从配置文件中获取指定路径的值
    
    Args:
        key_path: 配置键路径，使用点号分隔，如 'api_keys.alpha_vantage'
        default: 默认值，当配置不存在时返回
    
    Returns:
        Any: 配置值或默认值
    """
    try:
        if not CONFIG_FILE.exists():
            logging.warning(f"配置文件不存在: {CONFIG_FILE}")
            return default
            
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
        # 处理嵌套键
        keys = key_path.split('.')
        value = config
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
            if value is None:
                return default
                
        return value
    except Exception as e:
        logging.error(f"读取配置失败 ({key_path}): {e}")
        return default
    
def save_config_value(key_path: str, value: Any) -> bool:
    """
    保存配置值到配置文件
    
    Args:
        key_path: 配置键路径，使用点号分隔，如 'data_source.default'
        value: 要保存的值
    
    Returns:
        bool: 保存是否成功
    """
    try:
        # 确保配置目录存在
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取现有配置或创建新配置
        config = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        
        # 处理嵌套键
        keys = key_path.split('.')
        current = config
        
        # 创建嵌套结构
        for key in keys[:-1]:
            current = current.setdefault(key, {})
            
        # 设置最终值
        current[keys[-1]] = value
        
        # 保存配置
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
            
        return True
        
    except Exception as e:
        logging.error(f"保存配置失败 ({key_path}): {e}")
        return False    