import telebot
import requests
import time
import os
import re
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

# --- ၀။ TIMEZONE UTILS ---
def get_mm_time():
    return datetime.now(timezone.utc) + timedelta(hours=6, minutes=30)

# --- ၁။ MAIN ALGORITHM (User's Strategy Only) ---

def algo_number_history(history_list):
    """
    Number History Alternating Logic
    နောက်ဆုံးထွက်ခဲ့တဲ့ ဂဏန်းကိုယူမယ်။ အဲ့ဂဏန်း အရင်တစ်ခေါက်က ထွက်ခဲ့တုန်းက
    သူ့နောက်မှာ BIG လာခဲ့သလား၊ SMALL လာခဲ့သလား ကြည့်မယ်။
    """
    if len(history_list) < 2:
        return None 

    latest_num = str(history_list[0].get('number'))

    for i in range(1, len(history_list)):
        if str(history_list[i].get('number')) == latest_num:
            following_item = history_list[i-1]
            following_num = int(following_item.get('number'))
            following_size = "BIG" if following_num >= 5 else "SMALL"

            return "SMALL" if following_size == "BIG" else "BIG"

    return None

def get_prediction(history_data):
    try:
        data_list = sorted(history_data, key=lambda x: int(x['issueNumber']), reverse=True)
        latest = data_list[0]
        
        side = algo_number_history(data_list) 
        
        if side is None:
            return "SKIP", 0, f"No previous data for {latest.get('number')}", latest.get('blockNumber')
            
        conf = 100 
        note = f"NumHistory Logic"
        
        return side, conf, note, latest.get('blockNumber')
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
    
    msg = f"<b>🍁GLOBAL TRX LIVE - WWC LABS</b>\n"
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
    msg += f"🍁ᴘʀᴇᴅɪᴄᴛɪᴏɴ: <b>{curr['side'] or 'WAITING'}</b> ({curr['conf']}%)\n"
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
    print("Bot starting with Pure Number History Logic & Skip Feature...")
    state["last_day"] = get_mm_time().strftime("%d,%m,%Y")
    
    while True:
        try:
            res = requests.get(f"{API_URL}?pageSize=50&pageNo=1&ts={int(time.time())}", headers=HEADERS, timeout=15)
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
                
                # Update Messages
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