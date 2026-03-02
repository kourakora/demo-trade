import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
from gtts import gTTS
import base64
import io
import random

# --- 初期設定 ---
st.set_page_config(page_title="本格デモトレード", layout="wide")
st.title("🕯️ リアルタイム・ローソク足 ＆ ニュース連動ダッシュボード")

# 【変更】is_liveフラグを追加し、リアルタイム動作時のみニュースが発生するようにする
def get_next_price_change(is_live=False):
    # ニュースの発生ロジック（リアルタイム更新中で、かつ約3%の確率で発生）
    if is_live and np.random.random() < 0.03 and st.session_state.news_timer == 0:
        news_list = [
            {"text": "相互関税を引き上げ！貿易摩擦の懸念から売り注文が殺到", "impact": -5.0, "voice": "ニュース速報です。相互関税が引き上げられました。強い下落トレンドに警戒してください。"},
            {"text": "相互関税を引き下げ！歴史的な合意により買い注文が殺到", "impact": 5.0, "voice": "ニュース速報です。相互関税が引き下げられました。強い上昇トレンドが発生しています。"},
            {"text": "中央銀行が予想外の利上げを発表！市場に動揺広がる", "impact": -4.0, "voice": "ニュース速報です。中央銀行が利上げを発表しました。株価の急落に注意してください。"},
            {"text": "大型の追加経済対策が可決！市場は好感", "impact": 4.0, "voice": "ニュース速報です。大型経済対策が可決されました。買いの勢いが強まっています。"}
        ]
        event = random.choice(news_list)
        st.session_state.current_news = event["text"]
        st.session_state.news_timer = 15 # 15回の更新（約数十分）テロップを表示し続ける
        
        # ニュースによる強烈なトレンド（ドリフト）とボラティリティの強制上書き
        st.session_state.drift += event["impact"]
        st.session_state.volatility = min(15.0, st.session_state.volatility + 5.0)
        
        # 音声メッセージをニュースにセット
        st.session_state.voice_message = event["voice"]

    # 通常の値動きロジック
    st.session_state.drift += np.random.normal(0, 0.4)
    st.session_state.drift *= 0.95 
    st.session_state.volatility += np.random.normal(0, 0.5)
    st.session_state.volatility = max(1.0, min(10.0, st.session_state.volatility))
    
    jump = 0
    if np.random.random() < 0.02:
        jump = np.random.normal(0, st.session_state.volatility * 5)
        
    change = st.session_state.drift + np.random.normal(0, st.session_state.volatility) + jump
    return change

if 'initialized' not in st.session_state:
    st.session_state.balance = 1000000  
    st.session_state.position = 0       
    st.session_state.avg_price = 0.0    
    st.session_state.history = []
    st.session_state.current_id = 0
    st.session_state.trade_log = []    
    st.session_state.asset_history = [{"回数": 0, "総資産": 1000000}] 
    
    st.session_state.voice_message = None
    st.session_state.wait_for_audio = False 
    
    # 【追加】ニュース管理用の変数
    st.session_state.current_news = None
    st.session_state.news_timer = 0
    
    st.session_state.drift = 0.0       
    st.session_state.volatility = 4.0  
    
    last_close = 1000.0
    for _ in range(300): 
        # 初期データの生成時は is_live=False なのでニュースは起きない
        change = get_next_price_change(is_live=False)
        new_close = last_close + change
        high = max(last_close, new_close) + abs(np.random.normal(0, st.session_state.volatility * 0.5))
        low = min(last_close, new_close) - abs(np.random.normal(0, st.session_state.volatility * 0.5))
        
        st.session_state.current_id += 1
        st.session_state.history.append({
            "id": st.session_state.current_id,
            "open": last_close, "high": high, "low": low, "close": new_close
        })
        last_close = new_close
        
    st.session_state.initialized = True

def generate_next_candle():
    last_close = st.session_state.history[-1]["close"]
    
    # 【変更】リアルタイム時は is_live=True で呼び出し、ニュース発生フラグを立てる
    change = get_next_price_change(is_live=True)
    new_close = last_close + change
    
    high = max(last_close, new_close) + abs(np.random.normal(0, st.session_state.volatility * 0.5))
    low = min(last_close, new_close) - abs(np.random.normal(0, st.session_state.volatility * 0.5))
    
    st.session_state.current_id += 1
    st.session_state.history.append({
        "id": st.session_state.current_id,
        "open": last_close, "high": high, "low": low, "close": new_close
    })
    
    if len(st.session_state.history) > 300:
        st.session_state.history.pop(0)
        
    # ニュースの表示タイマーを減らす
    if st.session_state.news_timer > 0:
        st.session_state.news_timer -= 1
        if st.session_state.news_timer == 0:
            st.session_state.current_news = None

def trade(action, amount):
    current_price = st.session_state.history[-1]["close"]
    qty_change = amount if action == "buy" else -amount
    old_position = st.session_state.position
    
    realized_pnl = 0
    closed_qty = 0
    
    if old_position > 0 and qty_change < 0:
        closed_qty = min(old_position, abs(qty_change))
        realized_pnl = (current_price - st.session_state.avg_price) * closed_qty
        trade_type = "買建の決済"
    elif old_position < 0 and qty_change > 0:
        closed_qty = min(abs(old_position), qty_change)
        realized_pnl = (st.session_state.avg_price - current_price) * closed_qty
        trade_type = "売建の決済"
        
    if closed_qty > 0:
        if realized_pnl > 0:
            st.session_state.voice_message = f"{int(realized_pnl):,}円の利益です。"
        elif realized_pnl < 0:
            st.session_state.voice_message = f"{int(abs(realized_pnl)):,}円の損失です。"
        else:
            st.session_state.voice_message = "同値撤退しました。"
    else:
        if action == "buy":
            st.session_state.voice_message = "買建しました。"
        else:
            st.session_state.voice_message = "売建しました。"

    st.session_state.balance -= qty_change * current_price
    new_position = old_position + qty_change
    
    if closed_qty > 0:
        result_mark = "🟢 勝ち" if realized_pnl > 0 else "🔴 負け" if realized_pnl < 0 else "⚪ 同値"
        st.session_state.trade_log.append({
            "結果": result_mark,
            "種類": trade_type,
            "数量": closed_qty,
            "建値": f"¥{st.session_state.avg_price:,.1f}",
            "決済値": f"¥{current_price:,.1f}",
            "確定損益": int(realized_pnl)
        })
        
        current_total_asset = st.session_state.balance + (new_position * current_price)
        st.session_state.asset_history.append({
            "回数": len(st.session_state.trade_log),
            "総資産": current_total_asset
        })
    
    if new_position == 0:
        st.session_state.avg_price = 0.0
    elif old_position == 0:
        st.session_state.avg_price = current_price
    elif (old_position > 0 and new_position > 0) or (old_position < 0 and new_position < 0):
        if abs(new_position) > abs(old_position):
            total_cost = abs(old_position) * st.session_state.avg_price + amount * current_price
            st.session_state.avg_price = total_cost / abs(new_position)
    else:
        st.session_state.avg_price = current_price
        
    st.session_state.position = new_position

# --- UIレイアウト ---
current_price = st.session_state.history[-1]["close"]

unrealized_pnl = 0
if st.session_state.position > 0:
    unrealized_pnl = (current_price - st.session_state.avg_price) * st.session_state.position
elif st.session_state.position < 0:
    unrealized_pnl = (st.session_state.avg_price - current_price) * abs(st.session_state.position)

total_assets = st.session_state.balance + (st.session_state.position * current_price)

st.sidebar.markdown("### 📊 口座状況")
st.sidebar.metric("総資産", f"¥{total_assets:,.0f}", f"評価損益: ¥{unrealized_pnl:,.0f}")
st.sidebar.write(f"現金残高: ¥{st.session_state.balance:,.0f}")

if st.session_state.position > 0:
    st.sidebar.success(f"📈 買建: {st.session_state.position}株")
    st.sidebar.write(f"平均建値: ¥{st.session_state.avg_price:,.1f}")
elif st.session_state.position < 0:
    st.sidebar.error(f"📉 売建: {abs(st.session_state.position)}株")
    st.sidebar.write(f"平均建値: ¥{st.session_state.avg_price:,.1f}")
else:
    st.sidebar.info("ノーポジション")

st.sidebar.markdown("---")
display_count = st.sidebar.slider("表示件数（ズーム）", min_value=30, max_value=200, value=100, step=10)

st.sidebar.markdown("---")
st.sidebar.markdown("### ⏱️ 時間の進め方")
auto_update = st.sidebar.checkbox("自動更新（1秒ごと）", value=False)
if st.sidebar.button("▶ 手動で1単位進める"):
    generate_next_candle()
    st.rerun()

# 【追加】ニュース速報のテロップ表示領域
if st.session_state.current_news:
    st.error(f"🚨 **{st.session_state.current_news}**")

col_chart, col_trade = st.columns([3, 1])

with col_trade:
    st.markdown("### ⚡ 注文パネル")
    st.write(f"現在値: **¥{current_price:,.1f}**")
    
    trade_amount = st.number_input("取引数量", min_value=100, step=100, value=1000)
    
    st.markdown("---")
    if st.button(f"🔴 買 ({trade_amount}株)", use_container_width=True):
        trade("buy", trade_amount)
        st.rerun()
        
    if st.button(f"🔵 売 ({trade_amount}株)", use_container_width=True):
        trade("sell", trade_amount)
        st.rerun()
        
    st.markdown("---")
    if st.button("全決済 (ポジション0へ)", use_container_width=True) and st.session_state.position != 0:
        if st.session_state.position > 0:
            trade("sell", st.session_state.position)
        else:
            trade("buy", abs(st.session_state.position))
        st.rerun()

with col_chart:
    df = pd.DataFrame(st.session_state.history)
    df['SMA5'] = df['close'].rolling(window=5).mean()
    df['SMA25'] = df['close'].rolling(window=25).mean()
    df['SMA75'] = df['close'].rolling(window=75).mean()

    display_df = df.tail(display_count)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=display_df['id'], open=display_df['open'], high=display_df['high'], low=display_df['low'], close=display_df['close'],
        increasing_line_color='red', decreasing_line_color='green', name="価格"
    ))
    fig.add_trace(go.Scatter(x=display_df['id'], y=display_df['SMA5'], mode='lines', name='SMA5', line=dict(color='orange', width=2)))
    fig.add_trace(go.Scatter(x=display_df['id'], y=display_df['SMA25'], mode='lines', name='SMA25', line=dict(color='dodgerblue', width=2)))
    fig.add_trace(go.Scatter(x=display_df['id'], y=display_df['SMA75'], mode='lines', name='SMA75', line=dict(color='purple', width=2)))

    if st.session_state.position != 0:
        line_color = "red" if st.session_state.position > 0 else "blue"
        fig.add_hline(y=st.session_state.avg_price, line_dash="dash", line_color=line_color, 
                      annotation_text=f"建値 (¥{st.session_state.avg_price:.1f})", 
                      annotation_position="bottom right")

    min_vals = [display_df['low'].min(), display_df['SMA5'].min(), display_df['SMA25'].min(), display_df['SMA75'].min()]
    max_vals = [display_df['high'].max(), display_df['SMA5'].max(), display_df['SMA25'].max(), display_df['SMA75'].max()]
    
    y_min = min([v for v in min_vals if pd.notna(v)])
    y_max = max([v for v in max_vals if pd.notna(v)])
    
    price_range = y_max - y_min
    base_margin = price_range * 0.15 
    min_margin = st.session_state.volatility * 5 
    y_margin = max(base_margin, min_margin)

    fig.update_layout(
        height=450, margin=dict(l=0, r=0, t=30, b=0),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(
            range=[y_min - y_margin, y_max + y_margin],
            fixedrange=True
        ) 
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 音声再生処理 ---
if st.session_state.voice_message:
    try:
        tts = gTTS(text=st.session_state.voice_message, lang='ja')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        b64 = base64.b64encode(fp.read()).decode()
        md = f"""
            <div style="display:none; height:0px; width:0px; overflow:hidden;">
                <audio autoplay="true">
                    <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                </audio>
            </div>
            """
        st.markdown(md, unsafe_allow_html=True)
        st.session_state.voice_message = None
        st.session_state.wait_for_audio = True 
    except Exception as e:
        st.error(f"音声生成エラー: {e}")

# --- トレード成績と履歴の表示 ---
st.markdown("---")
st.markdown("### 🏆 取引成績 ＆ トレードログ")

total_trades = len(st.session_state.trade_log)

if total_trades > 0:
    winning_trades = [log["確定損益"] for log in st.session_state.trade_log if log["確定損益"] > 0]
    losing_trades = [log["確定損益"] for log in st.session_state.trade_log if log["確定損益"] < 0]
    
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    total_realized_pnl = sum(log["確定損益"] for log in st.session_state.trade_log)
    win_rate = (win_count / total_trades) * 100
    
    avg_win = sum(winning_trades) / win_count if win_count > 0 else 0
    avg_loss = sum(losing_trades) / loss_count if loss_count > 0 else 0
    
    risk_reward_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    col_stat1.metric("勝率", f"{win_rate:.1f} %")
    col_stat2.metric("総決済回数", f"{total_trades} 回", f"{win_count}勝 / {loss_count}敗")
    col_stat3.metric("累計確定損益", f"¥{total_realized_pnl:,.0f}")
    col_stat4.metric("リスクリワード・レシオ", f"{risk_reward_ratio:.2f}", "1.0以上なら損小利大")

    col_sub1, col_sub2, col_sub3, col_sub4 = st.columns(4)
    col_sub1.metric("平均利益 (勝ちトレード)", f"¥{avg_win:,.0f}")
    col_sub2.metric("平均損失 (負けトレード)", f"¥{avg_loss:,.0f}")
    
    col_graph, col_table = st.columns([1, 1])
    
    with col_graph:
        st.markdown("#### 📈 資産推移グラフ")
        asset_df = pd.DataFrame(st.session_state.asset_history)
        fig_asset = go.Figure()
        fig_asset.add_trace(go.Scatter(x=asset_df['回数'], y=asset_df['総資産'], mode='lines+markers', line=dict(color='green', width=3)))
        fig_asset.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="総資産 (¥)", xaxis_title="決済回数")
        st.plotly_chart(fig_asset, use_container_width=True)

    with col_table:
        st.markdown("#### 📝 履歴一覧")
        log_df = pd.DataFrame(st.session_state.trade_log)[::-1]
        def color_pnl(val):
            color = 'red' if val < 0 else 'green' if val > 0 else 'black'
            return f'color: {color}'
        st.dataframe(log_df.style.map(color_pnl, subset=['確定損益']), use_container_width=True, height=300)

else:
    st.info("まだ決済された取引はありません。トレードを開始してください！")

# --- 自動更新ループと音声待機ロジック ---
if auto_update:
    if st.session_state.get("wait_for_audio", False):
        time.sleep(6) 
        st.session_state.wait_for_audio = False
    else:
        time.sleep(1)
        
    generate_next_candle()
    st.rerun()
else:
    if st.session_state.get("wait_for_audio", False):
        st.session_state.wait_for_audio = False