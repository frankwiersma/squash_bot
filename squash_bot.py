import asyncio
import requests
import logging
import sys
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, JobQueue
from telegram.error import BadRequest, TimedOut
import os

from credentials import TELEGRAM_BOT_TOKEN, USERNAME, PASSWORD, PLAYERS1, PLAYERS2, BASE_URL, CHAT_ID

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
    print("Debug: Entering login function")
    session = requests.Session()
    login_url = f"{BASE_URL}/auth/login"
    logger.info(f"Attempting to login. URL: POST {login_url}")
    print(f"Debug: Attempting to login. URL: POST {login_url}")
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
        logger.info(f"Login response status code: {response.status_code}")
        print(f"Debug: Login response status code: {response.status_code}")
        logger.info("Login successful.")
        print("Debug: Login successful.")
        return session
    except requests.exceptions.RequestException as e:
        logger.error(f"Login failed: {str(e)}")
        print(f"Debug: Login failed: {str(e)}")
        return None

async def error_handler(update: object, context: CallbackContext) -> None:
    print(f"Debug: Exception while handling an update: {context.error}")
    logger.error(f"Exception while handling an update: {context.error}")

    if isinstance(context.error, BadRequest):
        if "Query is too old" in str(context.error):
            logger.warning("Received a 'Query is too old' error. The bot might be responding too slowly.")
            print("Debug: Received a 'Query is too old' error. The bot might be responding too slowly.")
        else:
            logger.error(f"BadRequest error: {context.error}")
            print(f"Debug: BadRequest error: {context.error}")
    elif isinstance(context.error, TimedOut):
        logger.error(f"Request timed out: {context.error}")
        print(f"Debug: Request timed out: {context.error}")
    else:
        logger.error(f"Unexpected error: {context.error}")
        print(f"Debug: Unexpected error: {context.error}")

async def get_slots(session, date=None):
    print("Debug: Entering get_slots function")
    date = date or datetime.now().strftime('%Y-%m-%d')
    slots_url = f"{BASE_URL}/reservations/{date}/sport/785"
    logger.info(f"Fetching slots for date: {date}. URL: GET {slots_url}")
    print(f"Debug: Fetching slots for date: {date}. URL: GET {slots_url}")
    response = session.get(slots_url, headers=HEADERS)

    if response.status_code == 200:
        logger.info("Slots fetched successfully.")
        print("Debug: Slots fetched successfully.")
        soup = BeautifulSoup(response.content, 'html.parser')
        slots = [(slot.get("slot"), slot.find_parent("tr").get("data-time"), slot.find_parent("tr").get("utc"))
                 for slot in soup.find_all("td", {"type": "free"}) if slot.find_parent("tr").get("utc")]
        current_utc_time = datetime.now(timezone.utc).timestamp()
        return [(slot_id, slot_time, slot_utc) for slot_id, slot_time, slot_utc in slots if float(slot_utc) > current_utc_time]
    else:
        logger.error(f"Failed to fetch slots with status code: {response.status_code}")
        print(f"Debug: Failed to fetch slots with status code: {response.status_code}")
    return []

async def start(update: Update, context: CallbackContext) -> None:
    print("Debug: Start command received.")
    logger.info("Start command received.")
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: CallbackContext):
    print("Debug: Showing main menu.")
    logger.info("Showing main menu.")
    keyboard = [
        [InlineKeyboardButton("Reserve a slot", callback_data="command_reserve")],
        [InlineKeyboardButton("Show current reservations", callback_data="command_show_reservations")],
        [InlineKeyboardButton("Cancel all reservations", callback_data="command_cancel_all")],
        [InlineKeyboardButton("Help", callback_data="command_help")]
    ]
    message_text = 'Welcome! What would you like to do?'
    
    if update.message:
        await update.message.reply_text(text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    logger.info(f"Button pressed with data: {query.data}")
    print(f"Debug: Button pressed with data: {query.data}")
    
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning("Callback query is too old. Continuing with the command execution.")
            print("Debug: Callback query is too old. Continuing with the command execution.")
        else:
            raise

    if query.data.startswith('command_'):
        command = query.data.split('_')[1]
        logger.info(f"Command received: {command}")
        print(f"Debug: Command received: {command}")
        try:
            if command == 'reserve':
                await reserve(update, context)
            elif command == 'show_reservations':
                logger.info("Calling show_reservations function")
                print("Debug: Calling show_reservations function")
                await show_reservations(update, context)
            elif command == 'cancel_all':
                logger.info("Calling cancel_all_command function")
                print("Debug: Calling cancel_all_command function")
                await cancel_all_command(update, context)
            elif command == 'help':
                await help_command(update, context)
        except Exception as e:
            logger.error(f"Error executing command {command}: {str(e)}", exc_info=True)
            print(f"Debug: Error executing command {command}: {str(e)}")
            await query.edit_message_text(f"An error occurred while executing the {command} command. Please try again later.")
    elif query.data.startswith('date_'):
        context.user_data['selected_date'] = selected_date = query.data.split('_')[1]
        logger.info(f"Date selected: {selected_date}")
        print(f"Debug: Date selected: {selected_date}")
        periods = ["morning", "afternoon", "evening"]
        keyboard = [[InlineKeyboardButton(period.capitalize(), callback_data=f'period_{period}')] for period in periods]
        await query.edit_message_text(text=f"Selected date: {selected_date}\nSelect a period:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('page_'):
        page = int(query.data.split('_')[1])
        await reserve(update, context, page)
    elif query.data.startswith('period_'):
        selected_period = query.data.split('_')[1]
        context.user_data['selected_period'] = selected_period
        logger.info(f"Period selected: {selected_period}")
        print(f"Debug: Period selected: {selected_period}")
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
            logger.info(f"Slot selected: {selected_slot}")
            print(f"Debug: Slot selected: {selected_slot}")
            await reserve_slot_command(update, context, selected_slot)
        else:
            await query.edit_message_text(text="Invalid slot selection. Please try again.")
            await show_main_menu(update, context)

async def reserve(update: Update, context: CallbackContext, page=0) -> None:
    print("Debug: Entering reserve function")
    date_options = get_date_options()
    keyboard = create_date_keyboard(date_options, page)
    if update.callback_query:
        await update.callback_query.edit_message_text('Select a date:', reply_markup=keyboard)
    else:
        await update.message.reply_text('Select a date:', reply_markup=keyboard)

async def reserve_slot_command(update: Update, context: CallbackContext, selected_slot=None) -> None:
    print("Debug: Entering reserve_slot_command function")
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
    await show_main_menu(update, context)

async def send_ics_file(query: CallbackQuery, date: str, start_time: str, end_time: str):
    print("Debug: Entering send_ics_file function")
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
    print("Debug: Entering get_future_reservations function")
    future_reservations_url = f"{BASE_URL}/user/future"
    logger.info(f"Fetching future reservations. URL: GET {future_reservations_url}")
    print(f"Debug: Fetching future reservations. URL: GET {future_reservations_url}")
    try:
        response = session.get(future_reservations_url, headers=HEADERS)
        response.raise_for_status()
        logger.info(f"Future reservations page fetched successfully. Status code: {response.status_code}")
        print(f"Debug: Future reservations page fetched successfully. Status code: {response.status_code}")
        soup = BeautifulSoup(response.content, 'html.parser')
        reservations = []
        
        table = soup.find('table', class_='oneBorder')
        if table:
            rows = table.find_all('tr', class_=['odd', 'even'])
            logger.info(f"Found {len(rows)} reservation rows in the table")
            print(f"Debug: Found {len(rows)} reservation rows in the table")
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
                            'made_on': cols[4].text.strip(),
                            'cost': cols[5].text.strip()
                        })
                        logger.info(f"Parsed reservation: {reservations[-1]['date']} at {reservations[-1]['start_time']}")
                        print(f"Debug: Parsed reservation: {reservations[-1]['date']} at {reservations[-1]['start_time']}")
        
        logger.info(f"Total of {len(reservations)} future reservations found")
        print(f"Debug: Total of {len(reservations)} future reservations found")
        return reservations
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching future reservations: {str(e)}")
        print(f"Debug: Error fetching future reservations: {str(e)}")
        return []

async def cancel_reservation(session, reservation_id):
    print(f"Debug: Entering cancel_reservation function for reservation {reservation_id}")
    cancel_url = f"{BASE_URL}{reservation_id}/cancel"
    logger.info(f"Attempting to cancel reservation: {reservation_id}. URL: GET {cancel_url}")
    print(f"Debug: Attempting to cancel reservation: {reservation_id}. URL: GET {cancel_url}")
    response = session.get(cancel_url, headers=HEADERS)
    if response.status_code == 200:
        logger.info(f"Cancellation page for {reservation_id} fetched successfully")
        print(f"Debug: Cancellation page for {reservation_id} fetched successfully")
        soup = BeautifulSoup(response.content, 'html.parser')
        token = soup.find("input", {"name": "_token"})
        if token:
            logger.info(f"CSRF token found for {reservation_id}")
            print(f"Debug: CSRF token found for {reservation_id}")
            logger.info(f"Confirming cancellation. URL: POST {cancel_url}")
            print(f"Debug: Confirming cancellation. URL: POST {cancel_url}")
            confirm_response = session.post(cancel_url, headers=HEADERS, data={
                '_token': token.get("value"),
                'confirmed': '1'
            })
            if confirm_response.status_code == 200:
                logger.info(f"Reservation {reservation_id} cancelled successfully")
                print(f"Debug: Reservation {reservation_id} cancelled successfully")
                return "Reservation cancelled successfully."
            else:
                logger.error(f"Failed to cancel reservation {reservation_id}. Status code: {confirm_response.status_code}")
                print(f"Debug: Failed to cancel reservation {reservation_id}. Status code: {confirm_response.status_code}")
                return f"Failed to cancel reservation! Status code: {confirm_response.status_code}"
        else:
            logger.error(f"CSRF token not found for {reservation_id}")
            print(f"Debug: CSRF token not found for {reservation_id}")
            return "Failed to cancel reservation: CSRF token not found"
    else:
        logger.error(f"Failed to fetch cancellation page for {reservation_id}. Status code: {response.status_code}")
        print(f"Debug: Failed to fetch cancellation page for {reservation_id}. Status code: {response.status_code}")
    return f"Failed to initiate cancellation! Status code: {response.status_code}"

async def cancel_all_command(update: Update, context: CallbackContext) -> None:
    print("Debug: Entered cancel_all_command function")
    logger.info("Entered cancel_all_command function")
    query = update.callback_query

    try:
        print("Debug: Attempting to login for cancel_all_command")
        logger.info("Attempting to login for cancel_all_command")
        session = await login()
        if session:
            print("Debug: Login successful, proceeding to cancel reservations")
            logger.info("Login successful, proceeding to cancel reservations")
            reservations = await get_future_reservations(session)
            print(f"Debug: Found {len(reservations)} reservations to cancel")
            logger.info(f"Found {len(reservations)} reservations to cancel")
            if reservations:
                results = []
                for reservation in reservations:
                    print(f"Debug: Attempting to cancel reservation: {reservation['id']}")
                    logger.info(f"Attempting to cancel reservation: {reservation['id']}")
                    result = await cancel_reservation(session, reservation['id'])
                    print(f"Debug: Cancellation result for {reservation['id']}: {result}")
                    logger.info(f"Cancellation result for {reservation['id']}: {result}")
                    results.append(f"Reservation on {reservation['date']} at {reservation['start_time']}: {result}")
                result_text = "\n".join(results)
                print("Debug: Sending cancellation results to user")
                logger.info("Sending cancellation results to user")
                await query.edit_message_text(f"Cancellation results:\n\n{result_text}")
            else:
                print("Debug: No upcoming reservations found")
                logger.info("No upcoming reservations found")
                await query.edit_message_text("No upcoming reservations found.")
        else:
            print("Debug: Login failed in cancel_all_command")
            logger.error("Login failed in cancel_all_command")
            await query.edit_message_text("Login failed. Unable to cancel reservations.")
    except Exception as e:
        print(f"Debug: Error in cancel_all_command: {str(e)}")
        logger.error(f"Error in cancel_all_command: {str(e)}", exc_info=True)
        await query.edit_message_text("An error occurred while canceling reservations. Please try again later.")
    
    print("Debug: Finished cancel_all_command, showing main menu")
    logger.info("Finished cancel_all_command, showing main menu")
    await asyncio.sleep(3)
    await show_main_menu(update, context)

async def help_command(update: Update, context: CallbackContext) -> None:
    print("Debug: Entering help_command function")
    help_text = (
        "Here are the available options:\n\n"
        "• Reserve a slot: Start the reservation process\n"
        "• Show current reservations: Display your upcoming reservations\n"
        "• Cancel all reservations: Cancel all your upcoming reservations\n"
        "• Help: Show this help message\n")
    await update.callback_query.edit_message_text(help_text)
    await show_main_menu(update, context)
        

async def show_reservations(update: Update, context: CallbackContext) -> None:
    print("Debug: Entered show_reservations function")
    logger.info("Entered show_reservations function")
    query = update.callback_query

    try:
        print("Debug: Attempting to login for show_reservations")
        logger.info("Attempting to login for show_reservations")
        session = await login()
        if session:
            print("Debug: Login successful, fetching current reservations")
            logger.info("Login successful, fetching current reservations")
            reservations = await get_future_reservations(session)
            print(f"Debug: Found {len(reservations)} reservations")
            logger.info(f"Found {len(reservations)} reservations")
            if reservations:
                reservation_text = "Your current reservations:\n\n"
                for reservation in reservations:
                    reservation_text += (
                        f"Date: {reservation['date']}\n"
                        f"Weekday: {reservation['weekday']}\n"
                        f"Start Time: {reservation['start_time']}\n"
                        f"Court: {reservation['court']}\n"
                        f"Made On: {reservation['made_on']}\n"
                        f"Cost: {reservation['cost']}\n\n"
                    )
                print("Debug: Sending reservation information to user")
                logger.info("Sending reservation information to user")
                await query.edit_message_text(reservation_text)
            else:
                print("Debug: No upcoming reservations found")
                logger.info("No upcoming reservations found")
                await query.edit_message_text("You have no upcoming reservations.")
        else:
            print("Debug: Login failed in show_reservations")
            logger.error("Login failed in show_reservations")
            await query.edit_message_text("Login failed. Please try again later.")
    except Exception as e:
        print(f"Debug: Error in show_reservations: {str(e)}")
        logger.error(f"Error in show_reservations: {str(e)}", exc_info=True)
        await query.edit_message_text("An error occurred while fetching reservations. Please try again later.")
    
    print("Debug: Finished show_reservations, showing main menu")
    logger.info("Finished show_reservations, showing main menu")
    await asyncio.sleep(3)
    await show_main_menu(update, context)

async def send_initial_message(context: CallbackContext):
    print("Debug: Entering send_initial_message function")
    chat_id = context.job.data
    try:
        message_text = 'Welcome! What would you like to do?'
        keyboard = [
            [InlineKeyboardButton("Reserve a slot", callback_data="command_reserve")],
            [InlineKeyboardButton("Show current reservations", callback_data="command_show_reservations")],
            [InlineKeyboardButton("Cancel all reservations", callback_data="command_cancel_all")],
            [InlineKeyboardButton("Help", callback_data="command_help")]
        ]
        print(f"Debug: Sending initial message to chat {chat_id}")
        await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"Debug: Failed to send initial message to chat {chat_id}: {e}")
        logger.error(f"Failed to send initial message to chat {chat_id}: {e}")

def get_date_options(num_days=14):
    print("Debug: Entering get_date_options function")
    today = datetime.now().date()
    date_options = []
    for i in range(num_days):
        date = today + timedelta(days=i)
        if date.weekday() < 5:  # Monday to Friday
            date_options.append((date, 'Today' if i == 0 else 'Tomorrow' if i == 1 else date.strftime('%A, %d %b')))
    print(f"Debug: Generated {len(date_options)} date options")
    return date_options

def create_date_keyboard(date_options, page=0, items_per_page=8):
    print("Debug: Entering create_date_keyboard function")
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
    
    print(f"Debug: Created date keyboard with {len(keyboard)} rows")
    return InlineKeyboardMarkup(keyboard)

async def display_slots(slots, period, date):
    print(f"Debug: Entering display_slots function for {period} on {date}")
    period_slots = {
        'morning': [slot for slot in slots if 6 <= int(slot[1].split(':')[0]) < 12],
        'afternoon': [slot for slot in slots if 12 <= int(slot[1].split(':')[0]) < 18],
        'evening': [slot for slot in slots if 18 <= int(slot[1].split(':')[0]) < 24]
    }.get(period, [])

    unique_slots = {slot[1]: slot for slot in period_slots}
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    formatted_date = date_obj.strftime('%A %d %b')
    slots_text = f"Available Reservation Slots for {formatted_date} ({period.capitalize()}):"
    
    keyboard = []
    for idx, (time, slot) in enumerate(unique_slots.items()):
        keyboard.append([InlineKeyboardButton(time, callback_data=f"slot_{idx}")])
    
    print(f"Debug: Found {len(unique_slots)} unique slots for {period}")
    return (slots_text, list(unique_slots.values()), InlineKeyboardMarkup(keyboard)) if unique_slots else (f"No available {period} slots for {formatted_date}.", [], None)

async def reserve_slot(session, selected_slot, date):
    print(f"Debug: Entering reserve_slot function for slot {selected_slot} on {date}")
    reservation_url = f"{BASE_URL}/reservations/make/{selected_slot[0]}/{selected_slot[2]}"
    logger.info(f"Attempting to reserve slot: {selected_slot} for date: {date}. URL: GET {reservation_url}")
    print(f"Debug: Attempting to reserve slot: {selected_slot} for date: {date}. URL: GET {reservation_url}")
    response = session.get(reservation_url, headers=HEADERS)

    if response.status_code == 200:
        logger.info("Reservation slot fetched successfully.")
        print("Debug: Reservation slot fetched successfully.")
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
        logger.info(f"Confirming reservation. URL: POST {confirm_url}")
        print(f"Debug: Confirming reservation. URL: POST {confirm_url}")
        confirm_response = session.post(confirm_url, headers=HEADERS, data=confirm_data)
        if confirm_response.status_code == 200:
            if 'success' in confirm_response.json().get('message', ''):
                logger.info("Reservation successful.")
                print("Debug: Reservation successful.")
                return "Reservation successful!", confirm_data['start_time'], confirm_data['end_time']
            else:
                logger.error("Reservation failed: Unexpected response format.")
                print("Debug: Reservation failed: Unexpected response format.")
                return "Reservation failed: Unexpected response format.", None, None
    logger.error(f"Reservation failed! Status code: {response.status_code}")
    print(f"Debug: Reservation failed! Status code: {response.status_code}")
    return f"Reservation failed! Status code: {response.status_code}", None, None

def main():
    print("Debug: Entering main function")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.job_queue.run_once(send_initial_message, when=1, data=CHAT_ID)
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    print("Debug: Starting polling")
    application.run_polling()

if __name__ == "__main__":
    main()