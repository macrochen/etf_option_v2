import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
import logging

class WyckoffAnalyzer:
    def __init__(self):
        pass

    def normalize_df(self, df):
        """标准化 DataFrame：统一列名，处理数据类型"""
        try:
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
            
            new_df_data = {}
            standard_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            
            for std in standard_cols:
                for i, raw_c in enumerate(raw_cols):
                    if raw_c in col_map and col_map[raw_c] == std:
                        new_df_data[std] = df.iloc[:, i]
                        break
            
            clean_df = pd.DataFrame(new_df_data)
            
            # 检查必要列
            required = ['date', 'open', 'high', 'low', 'close']
            missing = [r for r in required if r not in clean_df.columns]
            if missing:
                return None, f"数据缺少必要列或无法识别列名: {missing}"
            
            # 转换类型
            clean_df['date'] = pd.to_datetime(clean_df['date'])
            clean_df = clean_df.sort_values('date').reset_index(drop=True)
            for col in ['open', 'high', 'low', 'close']:
                clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')
            
            # 处理成交量（可能缺失）
            if 'volume' in clean_df.columns:
                clean_df['volume'] = pd.to_numeric(clean_df['volume'], errors='coerce').fillna(0)
            else:
                clean_df['volume'] = 0
                
            return clean_df.ffill().bfill(), None
        except Exception as e:
            return None, f"标准化数据失败: {str(e)}"

    def process_csv(self, file_stream):
        """处理上传的CSV文件"""
        try:
            df = pd.read_csv(file_stream)
            return self.normalize_df(df)
        except Exception as e:
            return None, f"解析CSV失败: {str(e)}"

    def _calculate_indicators(self, df):
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['Vol_MA20'] = df['volume'].rolling(window=20).mean()
        df['Rel_Vol'] = df['volume'] / df['Vol_MA20']
        
        # 趋势判断逻辑：优先使用 MA200 (牛熊线)，数据不足则用 MA60
        if len(df) >= 200:
            df['Trend_MA'] = df['close'].rolling(window=200).mean()
            df['Trend_Name'] = 'MA200'
        else:
            df['Trend_MA'] = df['close'].rolling(window=60).mean()
            df['Trend_Name'] = 'MA60'
            
        return df

    def _detect_live_signals(self, df):
        """基于“过去”识别“当下”的实时信号探测"""
        signals = []
        n = len(df)
        window = 30 

        for i in range(window, n):
            lookback = df.iloc[i-window:i]
            
            # 1. 线性相关性检查 (Pearson r) - 确保是横盘
            prices_c = lookback['close'].values
            times = np.arange(len(prices_c))
            corr = np.corrcoef(times, prices_c)[0, 1]
            if abs(corr) > 0.75: continue
            
            # 2. 价格重心位移检查
            amp = lookback['high'].max() - lookback['low'].min()
            displacement = abs(lookback['close'].iloc[-1] - lookback['close'].iloc[0])
            if amp > 0 and (displacement / amp) > 0.6: continue

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

        # 信号去重 (10天内同类信号只取最新的)
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
        
        base_lookback = 30
        start_idx = max(0, idx - base_lookback)
        max_total_lookback = 150
        for lookback_i in range(start_idx - 1, max(0, idx - max_total_lookback), -1):
            c_close = df['close'].iloc[lookback_i]
            if sup * 0.98 <= c_close <= res * 1.02:
                start_idx = lookback_i
            else:
                break
        
        # 修正：箱体应延续到最新一天，而不是停留在信号发生日
        end_idx = len(df) - 1
        
        p_before = df.iloc[max(0, start_idx-20):start_idx]['close'].mean()
        zone_color = 'rgba(0, 123, 255, 0.12)'
        prior_trend = "Unknown"
        if p_before > res: 
            zone_color = 'rgba(40, 167, 69, 0.18)'
            prior_trend = "Down"
        elif p_before < sup: 
            zone_color = 'rgba(220, 53, 69, 0.18)'
            prior_trend = "Up"

        return [{
            'name': '关键结构', 'start': df.iloc[start_idx]['date'].strftime('%Y-%m-%d'),
            'end': df.iloc[end_idx]['date'].strftime('%Y-%m-%d'),
            'color': zone_color, 'support': float(sup), 'resistance': float(res),
            'type': prior_trend
        }]

    def analyze(self, raw_df):
        """主分析接口，自动处理标准化和诊断"""
        # 1. 执行标准化
        df, error = self.normalize_df(raw_df)
        if error:
            raise ValueError(error)
            
        df = self._calculate_indicators(df)
        
        # 2. 探测信号
        signals = self._detect_live_signals(df)
        
        # 3. 信号有效性校验与箱体生成
        last_sig = signals[-1] if signals else None
        latest_plan = None
        
        # 检查 UT 信号是否已失效
        if last_sig and last_sig['code'] == 'UT':
            current_close = df.iloc[-1]['close']
            if current_close > last_sig['stop_loss']:
                # 信号被证伪
                latest_plan = {
                    'date': df.iloc[-1]['date'].strftime('%Y-%m-%d'),
                    'display_name': 'UT 信号失效',
                    'type': 'Neutral',
                    'logic': f"之前的 UT 卖点已被最新价格 {current_close:.2f} 突破（高于止损 {last_sig['stop_loss']:.2f}）。当前进入强势突破观察期。",
                    'stop_loss': 0, 'stop_loss_label': "观察期无特定止损",
                    'action': "等待新的结构确认", 'code': 'Invalidated'
                }
                # 从展示列表中移除该失效信号，避免误导
                signals.pop()
        
        # 无论信号是否刚刚被移除，我们都需要用它（或之前的有效信号）来画箱体
        # 注意：如果刚才 pop 了，last_sig 变量里存的还是那个被 pop 的对象，正好用来画箱体
        zones = self._find_final_zone(df, last_sig)
        
        # 4. 动态定性逻辑
        if zones:
            latest_zone = zones[0]
            # 这里用原始 signals 列表（如果 pop 了就不包含 UT 了，这符合逻辑，因为失效的 UT 不应影响结构定性，或者应该影响？）
            # 如果 UT 失效了，可能意味着 SOS，但目前我们先保留原有的 zones 逻辑
            has_sos = any(s['code'] == 'SOS' for s in signals)
            has_sow = any(s['code'] == 'SOW' for s in signals)
            if latest_zone['type'] == 'Up' and has_sos:
                latest_zone['name'] = "Re-accumulation (再吸筹确认)"
                latest_zone['color'] = 'rgba(40, 167, 69, 0.25)'
            elif latest_zone['type'] == 'Down' and has_sow:
                latest_zone['name'] = "Re-distribution (再派发确认)"
                latest_zone['color'] = 'rgba(220, 53, 69, 0.25)'

        # --- 趋势判定 ---
        current_price = df.iloc[-1]['close']
        current_ma = df.iloc[-1]['Trend_MA']
        ma_name = df.iloc[-1]['Trend_Name']
        trend_status = "Neutral"
        
        if pd.isna(current_ma):
            trend_desc = "数据不足，无法判断趋势"
        elif current_price > current_ma * 1.01:
            trend_status = "Bullish"
            trend_desc = f"价格位于 {ma_name} 之上，长期趋势向好"
        elif current_price < current_ma * 0.99:
            trend_status = "Bearish"
            trend_desc = f"价格位于 {ma_name} 之下，长期趋势偏空"
        else:
            trend_desc = f"价格在 {ma_name} 附近缠绕，趋势不明朗"
            
        trend_info = {
            'status': trend_status,
            'desc': trend_desc,
            'ma_name': ma_name
        }
        
        # 如果没有被 invalidate 覆盖，则生成正常的 plan
        if last_sig and not latest_plan:
            # 根据趋势调整建议
            bias_note = ""
            if last_sig['type'] == 'Bullish':
                if trend_status == 'Bullish': bias_note = "【顺势共振】买点处于上升趋势中，胜率较高。"
                elif trend_status == 'Bearish': bias_note = "【逆势博弈】买点处于下降趋势中，仅看作反弹，需严格止损。"
            elif last_sig['type'] == 'Bearish':
                if trend_status == 'Bearish': bias_note = "【顺势共振】卖点处于下降趋势中，可坚定持有。"
                elif trend_status == 'Bullish': bias_note = "【逆势调整】卖点处于上升趋势中，可能是上涨中继，不宜过分看空。"
                
            latest_plan = {
                'date': last_sig['date'], 'display_name': last_sig['name'],
                'type': last_sig['type'], 
                'logic': last_sig['desc'] + "<br><br>" + bias_note, 
                'stop_loss': last_sig['stop_loss'], 'stop_loss_label': last_sig['stop_loss_label'],
                'action': last_sig['action'], 'code': last_sig['code']
            }

        return {
            'dates': df['date'].dt.strftime('%Y-%m-%d').tolist(),
            'data': df[['open', 'close', 'low', 'high']].astype(float).values.tolist(),
            'volumes': [int(v) for v in df['volume'].tolist()],
            'trend_line': df['Trend_MA'].fillna('').tolist(),
            'trend_info': trend_info,
            'signals': signals, 'zones': zones, 'latest_plan': latest_plan
        }, signals
