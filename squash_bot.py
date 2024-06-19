import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
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
    slots_text = f"Available Reservation Slots for {date} ({period}):\n" + "\n".join([f"{idx + 1}. Slot Time: {time}" for idx, (time, _) in enumerate(unique_slots.items())])
    return (slots_text, list(unique_slots.values())) if unique_slots else (f"No available {period} slots for {date}.", [])

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
    days = [(1, 'Tomorrow'), (2, 'Day After Tomorrow'), (get_next_weekday_date(2), 'Coming Wednesday'), (get_next_weekday_date(2, next_week=True), 'Next Week Wednesday')]
    keyboard = [[InlineKeyboardButton(text, callback_data=f"date_{(datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')}")] for days_ahead, text in days]
    await update.message.reply_text('Select a date:', reply_markup=InlineKeyboardMarkup(keyboard))

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
            slots_text, filtered_slots = await display_slots(slots, selected_period, context.user_data['selected_date'])
            context.user_data['filtered_slots'] = filtered_slots
            await query.edit_message_text(text=slots_text)
            if filtered_slots:
                await query.message.reply_text("Use /reserve_slot <slot_number> to reserve a slot.")
        else:
            await query.edit_message_text(text="Login failed.")

    else:
        command_map = {
            'command_reserve': reserve,
            'command_reserve_slot': lambda u, c: u.message.reply_text("Use /reserve_slot <slot_number> to reserve a slot after selecting a date and period."),
            'command_cancel_all': cancel_all_command,
            'command_help': help_command
        }
        await command_map.get(query.data, lambda u, c: None)(update, context)

async def reserve_slot_command(update: Update, context: CallbackContext) -> None:
    session = await login()
    filtered_slots = context.user_data.get('filtered_slots')
    if session and filtered_slots:
        try:
            slot_index = int(update.message.text.split()[1]) - 1
            if 0 <= slot_index < len(filtered_slots):
                result, start_time, end_time = await reserve_slot(session, filtered_slots[slot_index], context.user_data['selected_date'])
                await update.message.reply_text(result)
                if start_time and end_time:
                    await send_ics_file(update, context.user_data['selected_date'], start_time, end_time)
            else:
                await update.message.reply_text('Invalid slot number.')
        except (IndexError, ValueError):
            await update.message.reply_text('Invalid input. Please enter a valid slot number.')
    else:
        await update.message.reply_text('You need to log in and check slots first. Use /reserve.')

async def send_ics_file(update: Update, date: str, start_time: str, end_time: str):
    start_time_ics = (datetime.strptime(start_time, '%H:%M') - timedelta(hours=2)).strftime('%H:%M')
    end_time_ics = (datetime.strptime(end_time, '%H:%M') - timedelta(hours=2)).strftime('%H:%M')

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Your Organization//NONSGML v1.0//EN
BEGIN:VEVENT
UID:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}@yourdomain.com
DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{date.replace('-', '')}T{start_time_ics.replace(':', '')}00Z
DTEND:{date.replace('-', '')}T{end_time_ics.replace(':', '')}00Z
SUMMARY:Squash
DESCRIPTION:Squash Reservation at Allinn Baanreserveren
END:VEVENT
END:VCALENDAR"""

    ics_file_path = f"/tmp/reservation_{datetime.now().strftime('%Y%m%dT%H%M%SZ')}.ics"
    with open(ics_file_path, 'w') as file:
        file.write(ics_content)

    await update.message.reply_document(open(ics_file_path, 'rb'))

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
