import sys
import os
sys.path.append(os.getcwd())
from db.market_db import MarketDatabase

def reset_ranks():
    print("Resetting valuation ranks in DB...")
    db = MarketDatabase()
    # 将所有 rank 置为 NULL，触发重新计算
    db.db.execute("UPDATE index_valuation_history SET pe_rank = NULL, pb_rank = NULL")
    db.db.commit()
    print("Done. Next run will re-calculate ranks using new logic.")

if __name__ == "__main__":
    reset_ranks()
