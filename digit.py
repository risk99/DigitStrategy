import telebot
import requests
import time
import os
from datetime import datetime, timedelta, timezone

# ========== CONFIGURATION ========== 
BOT_TOKEN = '8685736939:AAGbzSlibDslZRl6nJEhWkJqk9oBIRtMnjw'
CHANNEL_ID = '-1003770494230'


API_URL = "https://draw.ar-lottery01.com/TrxWinGo/TrxWinGo_1M/GetHistoryIssuePage.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

bot = telebot.TeleBot(BOT_TOKEN)

state = {
    "history": {},
    "total_wins": 0,
    "total_losses": 0,
    "current_loss_streak": 0,
    "max_loss_data": {}, 
    "last_day": "",
    "loss_msg_id": None, 
    "live_msg_id": None, 
    "predictions_memory": {}, 
    "processed_periods": set(),
    "current_prediction": {"period_full": None, "block": None, "side": None, "conf": 0, "note": "Processing..."}
}

def get_mm_time():
    return datetime.now(timezone.utc) + timedelta(hours=6, minutes=30)

# --- ၁။ AUTO PATTERN ANALYZER (Unified Logic) ---

def algo_dynamic_pattern(history_list):
    """
    Data အဟောင်းတွေထဲကနေ လက်ရှိ ၂ လုံးတွဲ / ၃ လုံးတွဲ Pattern ကိုရှာပြီး 
    Win Rate အများဆုံး (၇၀% အထက်) သေချာမှသာ ခန့်မှန်းပေးမယ့် Logic
    """
    nums = [int(x['number']) for x in history_list]
    if len(nums) < 4: return None, "Not enough data"

    # လက်ရှိ နောက်ဆုံးထွက်ထားတဲ့ Sequence တွေ
    target_3 = [nums[0], nums[1], nums[2]]
    target_2 = [nums[0], nums[1]]

    # (၁) ၃ လုံးတွဲ Pattern ကို အရင်စစ်မယ်
    b_count_3, s_count_3 = 0, 0
    for i in range(1, len(nums) - 3):
        if [nums[i], nums[i+1], nums[i+2]] == target_3:
            outcome = nums[i-1] # Pattern ပြီးနောက် ထွက်ခဲ့တဲ့ ရလဒ်
            if outcome >= 5: b_count_3 += 1
            else: s_count_3 += 1

    total_3 = b_count_3 + s_count_3
    if total_3 >= 2: # အရင်က အနည်းဆုံး ၂ ကြိမ် ထွက်ဖူးမှ တွက်မယ်
        b_pct = (b_count_3 / total_3) * 100
        s_pct = (s_count_3 / total_3) * 100
        seq_str = f"[{nums[2]},{nums[1]},{nums[0]}]"
        # Winrate 75% အထက်ရှိမှ ယူမယ်
        if b_pct >= 75: return "BIG", f"3-Digit {seq_str} ({b_pct:.0f}%)"
        if s_pct >= 75: return "SMALL", f"3-Digit {seq_str} ({s_pct:.0f}%)"

    # (၂) ၃ လုံးတွဲ သိပ်မသေချာရင် ၂ လုံးတွဲ ဆက်စစ်မယ်
    b_count_2, s_count_2 = 0, 0
    for i in range(1, len(nums) - 2):
        if [nums[i], nums[i+1]] == target_2:
            outcome = nums[i-1]
            if outcome >= 5: b_count_2 += 1
            else: s_count_2 += 1
            
    total_2 = b_count_2 + s_count_2
    if total_2 >= 3: # အရင်က အနည်းဆုံး ၃ ကြိမ် ထွက်ဖူးမှ တွက်မယ်
        b_pct = (b_count_2 / total_2) * 100
        s_pct = (s_count_2 / total_2) * 100
        seq_str = f"[{nums[1]},{nums[0]}]"
        # Winrate 70% အထက်ရှိမှ ယူမယ်
        if b_pct >= 70: return "BIG", f"2-Digit {seq_str} ({b_pct:.0f}%)"
        if s_pct >= 70: return "SMALL", f"2-Digit {seq_str} ({s_pct:.0f}%)"

    # Winrate နည်းနေရင် / Pattern မမိရင်
    return None, "Weak Trend (SKIP)"

def get_prediction(history_data):
    try:
        data_list = sorted(history_data, key=lambda x: int(x['issueNumber']), reverse=True)
        latest = data_list[0]
        
        side, p_type = algo_dynamic_pattern(data_list) 
        
        if side is None:
            return "SKIP", 0, p_type, latest.get('blockNumber')
            
        return side, 100, p_type, latest.get('blockNumber')
    except Exception as e:
        return None, 0, f"Error: {e}", None

# --- ၂။ STATS & UTILS ---

def update_loss_stats(streak):
    if streak <= 0: return
    now = get_mm_time()
    today = now.strftime("%d,%m,%Y")
    if state["last_day"] != today:
        state["max_loss_data"] = {}
        state["last_day"] = today
    if streak not in state["max_loss_data"]:
        state["max_loss_data"][streak] = {"times": 1, "last_time": now.strftime("%I:%M %p")}
    else:
        state["max_loss_data"][streak]["times"] += 1
        state["max_loss_data"][streak]["last_time"] = now.strftime("%I:%M %p")

# --- ၃။ MESSAGE BUILDERS ---

def build_live_msg(remaining_sec):
    total = state["total_wins"] + state["total_losses"]
    win_rate = (state["total_wins"] / total * 100) if total > 0 else 0
    curr = state['current_prediction']
    
    msg = f"<b>🍁GLOBAL TRX LIVE - AUTO PATTERN BOT</b>\n"
    msg += f"🍁ʜɪꜱᴛᴏʀʏ: <b>W-{state['total_wins']} | L-{state['total_losses']}</b>\n"
    msg += f"🍁ᴡɪɴʀᴀᴛᴇ: <b>{win_rate:.1f}%</b> \n"    
    msg += f"🍁ᴛɪᴍᴇ ʀᴇᴍᴀɪɴɪɴɢ: <b>{remaining_sec}s</b>\n"
    
    table = "📄     Period Number     • Result   •  W/L •\n"
                
    sorted_hist = sorted(state["history"].values(), key=lambda x: int(x['issueNumber']), reverse=True)
    
    for item in sorted_hist[:10]:
        p = str(item['issueNumber'])
        num = int(item['number'])
        actual_side = "BIG" if num >= 5 else "SMALL"
        
        wl = "▫️"
        if p in state["predictions_memory"]:
            predicted = state["predictions_memory"][p]
            if predicted == actual_side:
                wl = "🍏"
                if p not in state["processed_periods"]:
                    update_loss_stats(state["current_loss_streak"])
                    state["total_wins"] += 1
                    state["current_loss_streak"] = 0
                    state["processed_periods"].add(p)
            else:
                wl = "🍎"
                if p not in state["processed_periods"]:
                    state["total_losses"] += 1
                    state["current_loss_streak"] += 1
                    state["processed_periods"].add(p)
        
        table += f"🍁 {p[-17:]}  •  {num}-{actual_side[:1]}     • {wl:^3} •\n"

    msg += f"<pre>{table}</pre>"
        
    msg += f"🍁ᴘᴇʀɪᴏᴅ: {curr['period_full'][-17:] if curr['period_full'] else '----'}\n"
    if curr['side'] == "SKIP":
        msg += f"🍁ᴘʀᴇᴅɪᴄᴛɪᴏɴ: <b>SKIP ⏸</b> \n"
    else:
        msg += f"🍁ᴘʀᴇᴅɪᴄᴛɪᴏɴ: <b>{curr['side'] or 'WAITING'}</b> \n"
        
    msg += f"🍁ʟᴏɢɪᴄ ᴜsᴇᴅ: <i>{curr['note']}</i>\n"
    msg += f"🍁ᴄʀᴇᴀᴛᴏʀ: @XQNSY"

    return msg

def build_loss_msg():
    msg = f"<b>⏰ Max Loss History</b>\n"
    msg += f"<i>🗓️ Date: {state['last_day']}</i>\n\n"
    if not state["max_loss_data"]:
        msg += "▫️ No loss streaks recorded yet."
    else:
        for s in sorted(state["max_loss_data"].keys(), reverse=True):
            d = state["max_loss_data"][s]
            msg += f"<code>⚡{s}x {d['times']}Time {d['last_time']}</code>\n"
    return msg

# --- ၄။ MAIN LOOP ---

def main_loop():
    print("Bot starting with Unified Auto Pattern Analyzer (70%+ Winrate filter)...")
    state["last_day"] = get_mm_time().strftime("%d,%m,%Y")
    
    while True:
        try:
            # Pattern ပြန်ရှာဖို့ API ကနေ Data ၁၅၀ ယူပါမယ်
            res = requests.get(f"{API_URL}?pageSize=150&pageNo=1&ts={int(time.time())}", headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json().get('data', {}).get('list', [])
                for i in data: state["history"][i['issueNumber']] = i
                
                latest_p = sorted(state["history"].keys(), reverse=True)[0]
                next_p = str(int(latest_p) + 1)
                
                if state["current_prediction"]["period_full"] != next_p:
                    side, conf, note, b_num = get_prediction(list(state["history"].values()))
                        
                    state["current_prediction"] = {
                        "period_full": next_p, 
                        "block": b_num,
                        "side": side, 
                        "conf": conf, 
                        "note": note
                    }
                    
                    if side and side != "SKIP": 
                        state["predictions_memory"][next_p] = side

                rem_sec = 60 - get_mm_time().second
                
                l_text = build_loss_msg()
                if state["loss_msg_id"] is None:
                    m = bot.send_message(CHANNEL_ID, l_text, parse_mode='HTML')
                    state["loss_msg_id"] = m.message_id
                else:
                    try: bot.edit_message_text(l_text, CHANNEL_ID, state["loss_msg_id"], parse_mode='HTML')
                    except: pass

                v_text = build_live_msg(rem_sec)
                if state["live_msg_id"] is None:
                    m = bot.send_message(CHANNEL_ID, v_text, parse_mode='HTML')
                    state["live_msg_id"] = m.message_id
                else:
                    try: bot.edit_message_text(v_text, CHANNEL_ID, state["live_msg_id"], parse_mode='HTML')
                    except: pass

                time.sleep(5)
            else:
                time.sleep(10)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
