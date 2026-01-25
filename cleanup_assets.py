from db.portfolio_db import PortfolioDatabase
import logging

logging.basicConfig(level=logging.INFO)
db = PortfolioDatabase()

print("Scanning for invalid assets (empty symbol or name)...")

# 查找
sql = "SELECT id, account_name, symbol, name FROM asset_holdings WHERE symbol = '' OR symbol IS NULL OR name = '' OR name IS NULL"
rows = db.db.fetch_all(sql)

if not rows:
    print("No invalid assets found.")
else:
    print(f"Found {len(rows)} invalid assets:")
    ids_to_delete = []
    for row in rows:
        print(f"ID: {row[0]}, Account: {row[1]}, Symbol: '{row[2]}', Name: '{row[3]}'")
        ids_to_delete.append(row[0])
    
    # 删除
    confirm = 'y' # auto confirm for script
    if confirm == 'y':
        for asset_id in ids_to_delete:
            db.delete_asset(asset_id)
            print(f"Deleted Asset ID: {asset_id}")
        print("Cleanup complete.")
