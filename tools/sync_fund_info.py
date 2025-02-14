#!/usr/bin/env python3
from utils.fund_info_manager import FundInfoManager
from db.config import MARKET_DATA_DB
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def sync_fund_info():
    """同步基金基本信息"""
    try:
        logging.info("开始同步基金信息...")
        fund_info_manager = FundInfoManager(MARKET_DATA_DB)
        updated_count = fund_info_manager.sync_fund_info()
        logging.info(f"同步完成，共更新 {updated_count} 只基金的基本信息")
    except Exception as e:
        logging.error(f"同步失败: {str(e)}")
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="同步基金基本信息")
    parser.add_argument('--force', action='store_true', help='强制更新所有基金信息')
    args = parser.parse_args()
    
    sync_fund_info()