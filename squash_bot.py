import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
import os

# Import credentials from credentials.py
from credentials import TELEGRAM_BOT_TOKEN, USERNAME, PASSWORD, PLAYERS1, PLAYERS2, BASE_URL

# Initialize bot and application
bot = Bot(token=TELEGRAM_BOT_TOKEN)
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.6478.57 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'Ajax': '1',
    'Referer': f'{BASE_URL}/reservations',
    'Accept': 'text/javascript, text/html, application/xml, text/xml, */*',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
}

def get_date_options(num_days=14):
    today = datetime.now().date()
    date_options = []
    for i in range(num_days):
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Monday to Friday
            date_options.append((date, 'Today' if i == 0 else 'Tomorrow' if i == 1 else date.strftime('%A, %d %b')))
    return date_options

def create_date_keyboard(date_options, page=0, items_per_page=8):
    keyboard = []
    start = page * items_per_page
    end = start + items_per_page
    for date, display_text in date_options[start:end]:
        keyboard.append([InlineKeyboardButton(display_text, callback_data=f"date_{date.strftime('%Y-%m-%d')}")])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Previous", callback_data=f"page_{page-1}"))
    if end < len(date_options):
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    return InlineKeyboardMarkup(keyboard)

async def login():
    session = requests.Session()
    response = session.post(f"{BASE_URL}/auth/login", headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': BASE_URL,
        'Referer': f'{BASE_URL}/?reason=LOGGED_IN&goto=%2Freservations',
        **HEADERS
    }, data={
        'goto': '/reservations',
        'username': USERNAME,
        'password': PASSWORD
    })

    return session if response.status_code == 200 else None

async def get_slots(session, date=None):
    date = date or datetime.now().strftime('%Y-%m-%d')
    response = session.get(f"{BASE_URL}/reservations/{date}/sport/785", headers=HEADERS)

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        slots = [(slot.get("slot"), slot.find_parent("tr").get("data-time"), slot.find_parent("tr").get("utc"))
                 for slot in soup.find_all("td", {"type": "free"}) if slot.find_parent("tr").get("utc")]
        current_utc_time = datetime.now(timezone.utc).timestamp()
        return [(slot_id, slot_time, slot_utc) for slot_id, slot_time, slot_utc in slots if float(slot_utc) > current_utc_time]
    return []

async def display_slots(slots, period, date):
    period_slots = {
        'morning': [slot for slot in slots if 6 <= int(slot[1].split(':')[0]) < 12],
        'afternoon': [slot for slot in slots if 12 <= int(slot[1].split(':')[0]) < 18],
        'evening': [slot for slot in slots if 18 <= int(slot[1].split(':')[0]) < 24]
    }.get(period, [])

    unique_slots = {slot[1]: slot for slot in period_slots}
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%A %d %b')  # e.g., "Monday 05 Aug"
    slots_text = f"Available Reservation Slots for {formatted_date} ({period.capitalize()}):"
    
    keyboard = []
    for idx, (time, slot) in enumerate(unique_slots.items()):
        keyboard.append([InlineKeyboardButton(time, callback_data=f"slot_{idx}")])
    
    return (slots_text, list(unique_slots.values()), InlineKeyboardMarkup(keyboard)) if unique_slots else (f"No available {period} slots for {formatted_date}.", [], None)

async def reserve_slot(session, selected_slot, date):
    reservation_url = f"{BASE_URL}/reservations/make/{selected_slot[0]}/{selected_slot[2]}"
    response = session.get(reservation_url, headers=HEADERS)

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        confirm_data = {
            '_token': soup.find("input", {"name": "_token"}).get("value"),
            'resource_id': selected_slot[0],
            'date': date,
            'start_time': soup.find("input", {"name": "start_time"}).get("value"),
            'end_time': soup.find("select", {"name": "end_time"}).find("option").get("value") if soup.find("select", {"name": "end_time"}).find("option") else '22:45',
            'confirmed': soup.find("input", {"name": "confirmed"}).get("value") if soup.find("input", {"name": "confirmed"}) else '1',
            'notes': soup.find("input", {"name": "notes"}).get("value") if soup.find("input", {"name": "notes"}) else '',
            'players[1]': PLAYERS1,
            'players[2]': PLAYERS2
        }

        confirm_response = session.post(f"{BASE_URL}/reservations/confirm", headers=HEADERS, data=confirm_data)
        if confirm_response.status_code == 200:
            if 'success' in confirm_response.json().get('message', ''):
                return "Reservation successful!", confirm_data['start_time'], confirm_data['end_time']
            else:
                return "Reservation failed: Unexpected response format.", None, None
    return f"Reservation failed! Status code: {response.status_code}", None, None

async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [[InlineKeyboardButton(command, callback_data=f"command_{command[1:]}")] for command in ["/reserve", "/reserve_slot", "/cancel_all", "/help"]]
    await update.message.reply_text('Welcome! Select a command:', reply_markup=InlineKeyboardMarkup(keyboard))

async def reserve(update: Update, context: CallbackContext) -> None:
    date_options = get_date_options()
    keyboard = create_date_keyboard(date_options)
    await update.message.reply_text('Select a date:', reply_markup=keyboard)

def get_next_weekday_date(weekday, next_week=False):
    days_ahead = weekday - datetime.now().weekday()
    if days_ahead <= 0:
        days_ahead += 7
    if next_week:
        days_ahead += 7
    return days_ahead

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data.startswith('date_'):
        context.user_data['selected_date'] = selected_date = query.data.split('_')[1]
        periods = ["morning", "afternoon", "evening"]
        keyboard = [[InlineKeyboardButton(period.capitalize(), callback_data=f'period_{period}')] for period in periods]
        await query.edit_message_text(text=f"Selected date: {selected_date}\nSelect a period:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith('period_'):
        selected_period = query.data.split('_')[1]
        context.user_data['selected_period'] = selected_period
        session = await login()

        if session:
            slots = await get_slots(session, context.user_data['selected_date'])
            slots_text, filtered_slots, keyboard = await display_slots(slots, selected_period, context.user_data['selected_date'])
            context.user_data['filtered_slots'] = filtered_slots
            if keyboard:
                await query.edit_message_text(text=slots_text, reply_markup=keyboard)
            else:
                await query.edit_message_text(text=slots_text)
        else:
            await query.edit_message_text(text="Login failed.")

    elif query.data.startswith('slot_'):
        slot_index = int(query.data.split('_')[1])
        filtered_slots = context.user_data.get('filtered_slots')
        if filtered_slots and 0 <= slot_index < len(filtered_slots):
            selected_slot = filtered_slots[slot_index]
            await reserve_slot_command(update, context, selected_slot)
        else:
            await query.edit_message_text(text="Invalid slot selection. Please try again.")

    else:
        command_map = {
            'command_reserve': reserve,
            'command_reserve_slot': lambda u, c: u.message.reply_text("Use /reserve_slot <slot_number> to reserve a slot after selecting a date and period."),
            'command_cancel_all': cancel_all_command,
            'command_help': help_command
        }
        await command_map.get(query.data, lambda u, c: None)(update, context)

async def reserve_slot_command(update: Update, context: CallbackContext, selected_slot=None) -> None:
    query = update.callback_query
    session = await login()
    if session:
        if selected_slot:
            result, start_time, end_time = await reserve_slot(session, selected_slot, context.user_data['selected_date'])
            await query.edit_message_text(text=result)
            if start_time and end_time:
                await send_ics_file(query, context.user_data['selected_date'], start_time, end_time)
        else:
            await query.edit_message_text(text='Please select a slot using the buttons provided after choosing a date and period.')
    else:
        await query.edit_message_text(text="Login failed. Please try again later.")

async def send_ics_file(query: CallbackQuery, date: str, start_time: str, end_time: str):
    start_time_ics = datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M')
    end_time_ics = datetime.strptime(f"{date} {end_time}", '%Y-%m-%d %H:%M')

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Your Organization//NONSGML v1.0//EN
BEGIN:VEVENT
UID:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}@yourdomain.com
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start_time_ics.strftime('%Y%m%dT%H%M%S')}
DTEND:{end_time_ics.strftime('%Y%m%dT%H%M%S')}
SUMMARY:Squash
DESCRIPTION:Squash Reservation at Allinn Baanreserveren
END:VEVENT
END:VCALENDAR"""

    ics_file_path = f"/tmp/reservation_{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.ics"
    with open(ics_file_path, 'w') as file:
        file.write(ics_content)

    with open(ics_file_path, 'rb') as ics_file:
        await query.message.reply_document(document=ics_file, filename="squash_reservation.ics")

    os.remove(ics_file_path)  # Clean up the temporary file

async def get_future_reservations(session):
    response = session.get(f"{BASE_URL}/user/future", headers=HEADERS)
    if response.status_code == 200:
        return [a['href'] for a in BeautifulSoup(response.content, 'html.parser').select('a.ajaxlink') if '/reservations/' in a['href']]
    return []

async def cancel_reservation(session, reservation_id):
    cancel_url = f"{BASE_URL}{reservation_id}/cancel"
    response = session.get(cancel_url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        confirm_response = session.post(cancel_url, headers=HEADERS, data={'_token': soup.find("input", {"name": "_token"}).get("value"), 'confirmed': '1'})
        return "Reservation cancelled successfully." if confirm_response.status_code == 200 else f"Failed to cancel reservation! Status code: {confirm_response.status_code}"
    return f"Failed to initiate cancellation! Status code: {response.status_code}"

async def cancel_all_command(update: Update, context: CallbackContext) -> None:
    session = await login()
    if session:
        results = [await cancel_reservation(session, reservation_id) for reservation_id in await get_future_reservations(session)]
        await update.message.reply_text("\n".join(results) if results else "No upcoming reservations found.")
    else:
        await update.message.reply_text("Login failed.")

async def help_command(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(
        "Here are the available commands:\n"
        "/reserve - Start the reservation process\n"
        "/reserve_slot <slot_number> - Reserve a selected slot\n"
        "/cancel_all - Cancel all upcoming reservations\n"
        "/help - Show this help message\n"
    )

def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reserve", reserve))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("reserve_slot", reserve_slot_command))
    application.add_handler(CommandHandler("cancel_all", cancel_all_command))
    application.add_handler(CommandHandler("help", help_command))
    application.run_polling()

if __name__ == "__main__":
    main()
