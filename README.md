# Squash Reservation Bot

This project is a Telegram bot designed to automate the process of reserving squash courts. The bot interacts with a specific reservation website, handles user commands, and provides an interface for booking and canceling squash court reservations.

## Features

- **Login:** Authenticates to the reservation website.
- **Check Available Slots:** Retrieves and displays available squash court slots.
- **Reserve Slot:** Allows users to reserve a specific slot.
- **Cancel Reservations:** Cancels all upcoming reservations.
- **Interactive Menu:** Provides an interactive menu for users to select commands.

## Requirements

- Python 3.8+
- `requests` library
- `beautifulsoup4` library
- `python-telegram-bot` library

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/squash-reservation-bot.git
    cd squash-reservation-bot
    ```

2. Install the required libraries:
    ```sh
    pip install requests beautifulsoup4 python-telegram-bot
    ```

3. Replace `'YOUR_TELEGRAM_BOT_TOKEN'` with your actual Telegram bot token in the `TELEGRAM_BOT_TOKEN` variable.

4. Update the login credentials in the `login` function:
    ```python
    response = session.post("https://allinn.baanreserveren.nl/auth/login", headers={
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://allinn.baanreserveren.nl',
        'Referer': 'https://allinn.baanreserveren.nl/?reason=LOGGED_IN&goto=%2Freservations',
        **HEADERS
    }, data={
        'goto': '/reservations',
        'username': 'your-email@example.com',
        'password': 'your-password'
    })
    ```

## Usage

1. Run the bot:
    ```sh
    python bot.py
    ```

2. Open your Telegram app and start a chat with your bot.

3. Use the following commands:
    - `/start`: Display the interactive menu.
    - `/reserve`: Start the reservation process by selecting a date and period (morning, afternoon, evening).
    - `/reserve_slot <slot_number>`: Reserve a specific slot after selecting a date and period.
    - `/cancel_all`: Cancel all upcoming reservations.
    - `/help`: Show the help message with available commands.

## Bot Commands

- **/start**: Displays a welcome message with an interactive menu of commands.
- **/reserve**: Initiates the process of reserving a squash court by selecting a date and period.
- **/reserve_slot <slot_number>**: Reserves a selected slot based on the user's choice.
- **/cancel_all**: Cancels all future reservations.
- **/help**: Provides information about the available commands.

## Functions

- `login()`: Authenticates the user on the reservation website.
- `get_slots(session, date=None)`: Retrieves available slots for a specific date.
- `display_slots(slots, period, date)`: Displays available slots for a selected period.
- `reserve_slot(session, selected_slot, date)`: Reserves a selected slot.
- `start(update, context)`: Handles the `/start` command.
- `reserve(update, context)`: Handles the `/reserve` command.
- `button(update, context)`: Handles button clicks in the interactive menu.
- `reserve_slot_command(update, context)`: Handles the `/reserve_slot` command.
- `get_future_reservations(session)`: Retrieves future reservations.
- `cancel_reservation(session, reservation_id)`: Cancels a specific reservation.
- `cancel_all_command(update, context)`: Handles the `/cancel_all` command.
- `help_command(update, context)`: Handles the `/help` command.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any changes or enhancements.

