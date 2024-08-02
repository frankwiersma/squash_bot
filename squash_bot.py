import asyncio
from datetime import datetime, timedelta, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, JobQueue
from telegram.error import BadRequest, TimedOut
import requests
from bs4 import BeautifulSoup
import os
import json


from credentials import TELEGRAM_BOT_TOKEN, USERNAME, PASSWORD, PLAYERS1, PLAYERS2, BASE_URL, CHAT_ID

bot = Bot(token=TELEGRAM_BOT_TOKEN)
application = Application.builder().token(TELEGRAM_BOT_TOKEN).job_queue(JobQueue()).build()

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
    login_url = f"{BASE_URL}/auth/login"
    try:
        response = session.post(login_url, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': BASE_URL,
            'Referer': f'{BASE_URL}/?reason=LOGGED_IN&goto=%2Freservations',
            **HEADERS
        }, data={
            'goto': '/reservations',
            'username': USERNAME,
            'password': PASSWORD
        })
        response.raise_for_status()
        return session
    except requests.exceptions.RequestException:
        return None

async def error_handler(update: object, context: CallbackContext) -> None:
    pass

async def get_slots(session, date=None):
    date = date or datetime.now().strftime('%Y-%m-%d')
    slots_url = f"{BASE_URL}/reservations/{date}/sport/785"
    response = session.get(slots_url, headers=HEADERS)

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        slots = [(slot.get("slot"), slot.find_parent("tr").get("data-time"), slot.find_parent("tr").get("utc"))
                 for slot in soup.find_all("td", {"type": "free"}) if slot.find_parent("tr").get("utc")]
        current_utc_time = datetime.now(timezone.utc).timestamp()
        return [(slot_id, slot_time, slot_utc) for slot_id, slot_time, slot_utc in slots if float(slot_utc) > current_utc_time]
    return []

async def start(update: Update, context: CallbackContext) -> None:
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🎾 Reserve a slot", callback_data="command_reserve")],
        [InlineKeyboardButton("📋 Show current reservations", callback_data="command_show_reservations")],
        [InlineKeyboardButton("❌ Cancel all reservations", callback_data="command_cancel_all")]
    ]
    message_text = '👋 Welcome! What would you like to do?'
    
    if update.message:
        await update.message.reply_text(text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" not in str(e):
            raise

    try:
        if query.data.startswith('command_'):
            command = query.data[8:]
            if command == 'reserve':
                await reserve(update, context)
            elif command == 'show_reservations':
                await show_reservations(update, context)
            elif command == 'cancel_all':
                await cancel_all_command(update, context)
            else:
                await query.edit_message_text(f"Unknown command: {command}")
        elif query.data.startswith('date_'):
            context.user_data['selected_date'] = selected_date = query.data.split('_')[1]
            periods = ["morning", "afternoon", "evening"]
            keyboard = [[InlineKeyboardButton(period.capitalize(), callback_data=f'period_{period}')] for period in periods]
            await query.edit_message_text(text=f"Selected date: {selected_date}\nSelect a period:", reply_markup=InlineKeyboardMarkup(keyboard))
        elif query.data.startswith('page_'):
            page = int(query.data.split('_')[1])
            await reserve(update, context, page)
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
                    await show_main_menu(update, context)
            else:
                await query.edit_message_text(text="Login failed.")
                await show_main_menu(update, context)
        elif query.data.startswith('slot_'):
            slot_index = int(query.data.split('_')[1])
            filtered_slots = context.user_data.get('filtered_slots')
            if filtered_slots and 0 <= slot_index < len(filtered_slots):
                selected_slot = filtered_slots[slot_index]
                await reserve_slot_command(update, context, selected_slot)
            else:
                await query.edit_message_text(text="Invalid slot selection. Please try again.")
                await show_main_menu(update, context)
        else:
            await query.edit_message_text("An unexpected error occurred. Please try again.")
            await show_main_menu(update, context)
    except Exception as e:
        await query.edit_message_text("An error occurred. Please try again later.")

async def reserve(update: Update, context: CallbackContext, page=0) -> None:
    date_options = get_date_options()
    keyboard = create_date_keyboard(date_options, page)
    if update.callback_query:
        await update.callback_query.edit_message_text('📅 Select a date:', reply_markup=keyboard)
    else:
        await update.message.reply_text('📅 Select a date:', reply_markup=keyboard)

async def reserve_on_date(context: CallbackContext):
    job_data = context.job.data
    session = job_data['session']
    selected_slot = job_data['selected_slot']
    selected_date = job_data['selected_date']
    query = job_data['query']
    
    result, start_time, end_time = await reserve_slot(session, selected_slot, selected_date)
    await bot.send_message(chat_id=CHAT_ID, text=result)
    if start_time and end_time:
        await send_ics_file(query, selected_date, start_time, end_time)

async def reserve_slot_command(update: Update, context: CallbackContext, selected_slot=None) -> None:
    query = update.callback_query
    session = await login()
    if session:
        selected_date = context.user_data['selected_date']
        if selected_slot:
            date_diff = (datetime.strptime(selected_date, '%Y-%m-%d').date() - datetime.now().date()).days
            if date_diff > 7:
                # Store the future reservation details
                store_future_reservation(selected_date, selected_slot)
                await query.edit_message_text(f"Reservation for {selected_date} has been noted and will be booked when within the 7-day window.")
            else:
                # Execute reservation now
                result, start_time, end_time = await reserve_slot(session, selected_slot, selected_date)
                await query.edit_message_text(text=result)
                if start_time and end_time:
                    await send_ics_file(query, selected_date, start_time, end_time)
        else:
            await query.edit_message_text(text='Please select a slot using the buttons provided after choosing a date and period.')
    else:
        await query.edit_message_text(text="Login failed. Please try again later.")
    await show_main_menu(update, context)

def store_future_reservation(date, slot):
    # Store future reservation details locally
    try:
        with open('future_reservations.json', 'r') as file:
            reservations = json.load(file)
    except FileNotFoundError:
        reservations = []

    reservations.append({'date': date, 'slot': slot})
    with open('future_reservations.json', 'w') as file:
        json.dump(reservations, file)

async def check_and_book_reservations():
    # Load future reservations and attempt to book them
    try:
        with open('future_reservations.json', 'r') as file:
            reservations = json.load(file)
    except FileNotFoundError:
        reservations = []

    session = await login()
    if not session:
        return

    updated_reservations = []
    for reservation in reservations:
        date_diff = (datetime.strptime(reservation['date'], '%Y-%m-%d').date() - datetime.now().date()).days
        if date_diff <= 7:
            result, start_time, end_time = await reserve_slot(session, reservation['slot'], reservation['date'])
            bot.send_message(chat_id=CHAT_ID, text=result)  # Notify the result of booking attempt
        else:
            updated_reservations.append(reservation)  # Keep the reservation for future attempts

    # Update the stored reservations
    with open('future_reservations.json', 'w') as file:
        json.dump(updated_reservations, file)


def scheduler():
    # Scheduler to check reservations daily
    application.job_queue.run_repeating(check_and_book_reservations, interval=86400, first=1)  # Check every 24 hours

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

    os.remove(ics_file_path)

async def get_future_reservations(session):
    future_reservations_url = f"{BASE_URL}/user/future"
    try:
        response = session.get(future_reservations_url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        reservations = []
        
        table = soup.find('table', class_='oneBorder')
        if table:
            rows = table.find_all('tr', class_=['odd', 'even'])
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 6:
                    reservation_link = cols[0].find('a', class_='ajaxlink')
                    if reservation_link and 'href' in reservation_link.attrs:
                        reservations.append({
                            'id': reservation_link['href'],
                            'date': cols[0].text.strip(),
                            'weekday': cols[1].text.strip(),
                            'start_time': cols[2].text.strip(),
                            'court': cols[3].text.strip(),
                            'made_on': cols[4].text.strip()
                        })
        return reservations
    except requests.exceptions.RequestException:
        return []

async def cancel_reservation(session, reservation_id):
    cancel_url = f"{BASE_URL}{reservation_id}/cancel"
    response = session.get(cancel_url, headers=HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        token = soup.find("input", {"name": "_token"})
        if token:
            confirm_response = session.post(cancel_url, headers=HEADERS, data={
                '_token': token.get("value"),
                'confirmed': '1'
            })
            if confirm_response.status_code == 200:
                return "✅ Reservation cancelled successfully."
            else:
                return f"❌ Failed to cancel reservation! Status code: {confirm_response.status_code}"
        else:
            return "❌ Failed to cancel reservation: CSRF token not found"
    return f"❌ Failed to initiate cancellation! Status code: {response.status_code}"

async def cancel_all_command(update: Update, context: CallbackContext) -> None:
    query = update.callback_query

    try:
        session = await login()
        if session:
            reservations = await get_future_reservations(session)
            if reservations:
                results = []
                for reservation in reservations:
                    result = await cancel_reservation(session, reservation['id'])
                    results.append(f"📅 Reservation on {reservation['date']} at {reservation['start_time']}: {result}")
                result_text = "\n".join(results)
                await query.edit_message_text(f"🗑️ Cancellation results:\n\n{result_text}")
            else:
                await query.edit_message_text("📅 No upcoming reservations found.")
        else:
            await query.edit_message_text("❌ Login failed. Unable to cancel reservations.")
    except Exception as e:
        await query.edit_message_text(f"⚠️ An error occurred while canceling reservations: {str(e)}. Please try again later.")
    
    await asyncio.sleep(10)
    await query.message.reply_text("🤔 What would you like to do next?")
    await show_main_menu(update, context)
        
async def show_reservations(update: Update, context: CallbackContext) -> None:
    if update.callback_query:
        query = update.callback_query
        send_message = query.edit_message_text
    else:
        send_message = lambda text, **kwargs: context.bot.send_message(chat_id=update.effective_chat.id, text=text, **kwargs)

    try:
        session = await login()
        if session:
            reservations = await get_future_reservations(session)
            if reservations:
                reservation_text = "🏸 *Your Current Reservations:*\n\n"
                for reservation in reservations:
                    reservation_text += (
                        f"📅 *Date:* {reservation['date']}\n"
                        f"📆 *Weekday:* {reservation['weekday']}\n"
                        f"⏰ *Time:* {reservation['start_time']}\n"
                        f"📝 *Made On:* {reservation['made_on']}\n"
                        f"----------------------------------------\n"
                    )
                await send_message(reservation_text, parse_mode='Markdown')
            else:
                await send_message("📅 You have no upcoming reservations.")
        else:
            await send_message("❌ Login failed. Please try again later.")
    except Exception as e:
        await send_message("⚠️ An error occurred while fetching reservations. Please try again later!")
    
    await asyncio.sleep(10)
    await send_message("What would you like to do next?")
    await show_main_menu(update, context)

async def send_initial_message(context: CallbackContext):
    chat_id = context.job.data
    try:
        message_text = '👋 Welcome! What would you like to do?'
        keyboard = [
        [InlineKeyboardButton("🎾 Reserve a slot", callback_data="command_reserve")],
        [InlineKeyboardButton("📋 Show current reservations", callback_data="command_show_reservations")],
        [InlineKeyboardButton("❌ Cancel all reservations", callback_data="command_cancel_all")]
        ]
        await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        pass

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

async def display_slots(slots, period, date):
    period_slots = {
        'morning': [slot for slot in slots if 6 <= int(slot[1].split(':')[0]) < 12],
        'afternoon': [slot for slot in slots if 12 <= int(slot[1].split(':')[0]) < 18],
        'evening': [slot for slot in slots if 18 <= int(slot[1].split(':')[0]) < 24]
    }.get(period, [])

    unique_slots = {slot[1]: slot for slot in period_slots}
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%A %d %b')
    slots_text = f"🕒 Available Reservation Slots for {formatted_date} ({period.capitalize()}):"
    
    keyboard = []
    for idx, (time, slot) in enumerate(unique_slots.items()):
        keyboard.append([InlineKeyboardButton(f"⏰ {time}", callback_data=f"slot_{idx}")])
    
    return (slots_text, list(unique_slots.values()), InlineKeyboardMarkup(keyboard)) if unique_slots else (f"😔 No available {period} slots for {formatted_date}.", [], None)

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

        confirm_url = f"{BASE_URL}/reservations/confirm"
        confirm_response = session.post(confirm_url, headers=HEADERS, data=confirm_data)
        if confirm_response.status_code == 200:
            if 'success' in confirm_response.json().get('message', ''):
                return "Reservation successful!", confirm_data['start_time'], confirm_data['end_time']
            else:
                return "Reservation failed: Unexpected response format.", None, None
    return f"Reservation failed! Status code: {response.status_code}", None, None

def main():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.job_queue.run_once(send_initial_message, when=1, data=CHAT_ID)
    application.add_error_handler(error_handler)

    scheduler()  # Initialize the scheduler for future bookings

    application.run_polling()

if __name__ == "__main__":
    main()