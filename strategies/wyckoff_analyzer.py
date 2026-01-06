import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

class WyckoffAnalyzer:
    def __init__(self):
        pass

    def process_csv(self, file_stream):
        """处理上传的CSV文件"""
        try:
            # 读取CSV
            df = pd.read_csv(file_stream)
            
            # 标准化列名：转小写、去空格
            raw_cols = [str(c).lower().strip() for c in df.columns]
            
            # 扩展列名映射表
            col_map = {
                'date': 'date', 'time': 'date', '日期': 'date', '交易日期': 'date',
                'open': 'open', '开盘': 'open', '开盘价': 'open',
                'high': 'high', '最高': 'high', '最高价': 'high',
                'low': 'low', '最低': 'low', '最低价': 'low',
                'close': 'close', '收盘': 'close', '收盘价': 'close',
                'volume': 'volume', 'vol': 'volume', '成交量': 'volume', '成交额': 'volume'
            }
            
            # 核心修复：防止重复列名映射
            # 遍历映射表，在原始列中寻找第一个匹配项
            final_mapping = {}
            for target, _ in col_map.items(): # 注意：这里逻辑稍微变一下
                pass # 稍后处理
            
            # 重新构建列
            new_df_data = {}
            found_cols = []
            
            # 按照我们需要的标准列名去原数据中找
            standard_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            
            for std in standard_cols:
                # 在原始列中找哪一个能对应到 std
                for i, raw_c in enumerate(raw_cols):
                    if raw_c in col_map and col_map[raw_c] == std:
                        # 找到了对应的列，取出来，并记录已处理
                        new_df_data[std] = df.iloc[:, i]
                        found_cols.append(std)
                        break # 只取第一个匹配的，跳过重复的
            
            # 转换为新的 DataFrame
            clean_df = pd.DataFrame(new_df_data)
            
            # 强制检查必要列
            required = ['date', 'open', 'high', 'low', 'close']
            missing = [r for r in required if r not in clean_df.columns]
            if missing:
                return None, f"CSV文件缺少必要列或无法识别列名: {missing}"
            
            # 数据清洗
            clean_df['date'] = pd.to_datetime(clean_df['date'])
            clean_df = clean_df.sort_values('date').reset_index(drop=True)
            
            for col in ['open', 'high', 'low', 'close']:
                clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')
            
            if 'volume' not in clean_df.columns:
                clean_df['volume'] = 0
            else:
                clean_df['volume'] = pd.to_numeric(clean_df['volume'], errors='coerce').fillna(0)
                
            return clean_df.ffill().bfill(), None
        except Exception as e:
            import traceback
            logging.error(traceback.format_exc())
            return None, f"解析CSV失败: {str(e)}"

    def _calculate_indicators(self, df):
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
        df['Rel_Vol'] = df['volume'] / df['Vol_MA20']
        return df

    def _detect_live_signals(self, df):
        """
        核心升级：基于“过去”识别“当下”。
        优化横盘过滤器：放宽门槛，捕捉大级别横盘。
        """
        signals = []
        n = len(df)
        window = 30 

        for i in range(window, n):
            lookback = df.iloc[i-window:i]
            
            # 1. 线性相关性检查 - 放宽到 0.75，以免误杀带有一点点倾斜的长横盘
            prices_c = lookback['close'].values
            times = np.arange(len(prices_c))
            corr = np.corrcoef(times, prices_c)[0, 1]
            if abs(corr) > 0.75: 
                continue
            
            # 2. 价格重心位移检查 - 放宽到 0.6
            amp = lookback['high'].max() - lookback['low'].min()
            displacement = abs(lookback['close'].iloc[-1] - lookback['close'].iloc[0])
            if amp > 0 and (displacement / amp) > 0.6:
                continue

            local_sup = np.percentile(lookback['low'], 5)
            local_res = np.percentile(lookback['high'], 95)
            
            today = df.iloc[i]
            date_str = today['date'].strftime('%Y-%m-%d')

            # --- 场景探测 ---
            if today['low'] < local_sup * 0.999 and today['close'] > local_sup * 0.998:
                signals.append({
                    'date': date_str, 'code': 'Spring', 'name': 'Spring (买点)',
                    'desc': f"探测到假跌破！价格刺破支撑位 {local_sup:.2f} 后收回。",
                    'price': float(today['low']), 'type': 'Bullish', 'index': i,
                    'stop_loss': float(today['low'] * 0.99),
                    'action': "即时买入 / 关注", 'stop_loss_label': "风控止损位",
                    'trigger_res': float(local_res), 'trigger_sup': float(local_sup)
                })
            elif today['close'] > local_res * 1.005 and today['Rel_Vol'] > 1.1:
                signals.append({
                    'date': date_str, 'code': 'SOS', 'name': 'SOS (强势突破)',
                    'desc': f"强势突破！价格放量冲破阻力位 {local_res:.2f}。",
                    'price': float(today['close']), 'type': 'Bullish', 'index': i,
                    'stop_loss': float(today['low'] * 0.98),
                    'action': "趋势加仓", 'stop_loss_label': "风控止损位",
                    'trigger_res': float(local_res), 'trigger_sup': float(local_sup)
                })
            elif today['high'] > local_res * 1.001 and today['close'] < local_res * 1.002:
                signals.append({
                    'date': date_str, 'code': 'UT', 'name': 'Upthrust (离场)',
                    'desc': f"假突破警示！价格冲过阻力位 {local_res:.2f} 后跌回。",
                    'price': float(today['high']), 'type': 'Bearish', 'index': i,
                    'stop_loss': float(today['high'] * 1.01),
                    'action': "减仓 / 离场", 'stop_loss_label': "纠错回补位",
                    'trigger_res': float(local_res), 'trigger_sup': float(local_sup)
                })

        deduped = []
        for s in signals:
            if not deduped or s['code'] != deduped[-1]['code'] or (s['index'] - deduped[-1]['index']) > 10:
                deduped.append(s)
            else:
                deduped[-1] = s
        return deduped

    def _find_final_zone(self, df, last_signal):
        """向左回溯搜索，找回完整的长横盘结构"""
        if not last_signal: return []
        
        idx = last_signal['index']
        res = last_signal['trigger_res']
        sup = last_signal['trigger_sup']
        
        # 向左探测：只要之前的 K 线还在 [sup, res] 范围内，箱体就一直向左伸长
        # 最长找 120 天（约半年）
        start_idx = idx
        max_lookback = 120
        for lookback_i in range(idx - 1, max(0, idx - max_lookback), -1):
            c_close = df['close'].iloc[lookback_i]
            # 允许 2% 的溢出容错
            if sup * 0.98 <= c_close <= res * 1.02:
                start_idx = lookback_i
            else:
                # 遇到真正的破位了，停止回溯
                break
        
        # 简单判断颜色
        p_before = df.iloc[max(0, start_idx-20):start_idx]['close'].mean()
        zone_color = 'rgba(0, 123, 255, 0.12)'
        if p_before > res: zone_color = 'rgba(40, 167, 69, 0.18)'
        elif p_before < sup: zone_color = 'rgba(220, 53, 69, 0.18)'

        return [{
            'name': '关键结构', 'start': df.iloc[start_idx]['date'].strftime('%Y-%m-%d'),
            'end': df.iloc[idx]['date'].strftime('%Y-%m-%d'),
            'color': zone_color, 'support': float(sup), 'resistance': float(res)
        }]

    def analyze(self, df):
        df = self._calculate_indicators(df)
        
        # 1. 探测信号
        signals = self._detect_live_signals(df)
        
        # 2. 获取最后一个信号并提取其自带的水平线
        last_sig = signals[-1] if signals else None
        zones = self._find_final_zone(df, last_sig)
        
        latest_plan = None
        if last_sig:
            latest_plan = {
                'date': last_sig['date'], 'display_name': last_sig['name'],
                'type': last_sig['type'], 'logic': last_sig['desc'],
                'stop_loss': last_sig['stop_loss'], 'stop_loss_label': last_sig['stop_loss_label'],
                'action': last_sig['action'], 'code': last_sig['code']
            }

        return {
            'dates': df['date'].dt.strftime('%Y-%m-%d').tolist(),
            'data': df[['open', 'close', 'low', 'high']].astype(float).values.tolist(),
            'volumes': [int(v) for v in df['volume'].tolist()],
            'signals': signals, 'zones': zones, 'latest_plan': latest_plan
        }, signals