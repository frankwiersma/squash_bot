# Squash Bot 🏸

Welcome to the Squash Bot project! This bot helps you reserve squash court slots seamlessly using a Telegram bot interface.

## Features ✨

- **Reserve Slots 🎾**: Easily reserve available squash court slots.
- **View Reservations 📋**: Check your current reservations.
- **Cancel Reservations ❌**: Cancel all your reservations at once.

## Project Structure 📁

```
squash_bot
├── Dockerfile
├── requirements.txt
├── squash_bot.py
├── credentials.py.example
└── README.md
```

## Getting Started 🚀

### Prerequisites 📋

- Docker
- Python 3.9
- Telegram Bot API token

### Installation 🛠️

1. **Clone the repository**:
    ```bash
    git clone /home/pentest/experimental/squash_bot
    cd squash_bot
    ```

2. **Setup credentials**:
    - Copy `credentials.py.example` to `credentials.py`.
    - Replace the placeholders with your actual credentials.

3. **Build and run the Docker container**:
    ```bash
    docker build -t squash_bot .
    docker run -d squash_bot
    ```

### Usage 📘

- **Start the bot**:
    ```bash
    docker run -d squash_bot
    ```

- **Interact with the bot** on Telegram using the commands:
    - `/start`: Initiate the bot and display the main menu.
    - Use the inline buttons to reserve slots, view reservations, or cancel all reservations.

### Files 📄

- **Dockerfile**: Defines the container environment for running the bot.
- **requirements.txt**: Lists the Python dependencies.
- **squash_bot.py**: The main script containing the bot's logic.
- **credentials.py.example**: Template for storing your credentials.

## Contributing 🤝

1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m 'Add some feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

## License 📜

This project is licensed under the MIT License.

## Contact 📧

For any questions or suggestions, feel free to open an issue or contact the maintainer.

Happy coding! 😊

---

*Made with ❤️ by the Squash Bot Team*