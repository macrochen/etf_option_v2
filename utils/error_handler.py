import traceback
import logging
from functools import wraps
from typing import Callable, Any
from flask import jsonify

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('backtest.log')
    ]
)
logger = logging.getLogger(__name__)

def log_error(error: Exception, context: str = "") -> str:
    """统一的错误日志记录方法"""
    error_msg = f"{context}: {str(error)}\n堆栈信息:\n{traceback.format_exc()}"
    logger.error(error_msg)
    return error_msg

def api_error_handler(f: Callable) -> Callable:
    """API错误处理装饰器"""
    @wraps(f)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            # 处理特定的ValueError
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 400  # 返回400状态码
        except Exception as e:
            # 处理其他异常
            error_msg = log_error(e, f"执行 {f.__name__} 时发生错误")
            return jsonify({
                'status': 'error',
                'message': '发生了一个未知错误，请稍后再试。'
            }), 500  # 返回500状态码
    return wrapper 