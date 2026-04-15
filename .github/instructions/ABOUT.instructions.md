---
description: This file contains general instructions that apply to all files in the project. Use this file to provide guidelines, best practices, or any other information that should be considered when working on the project.
applyTo: '**/*'
# applyTo: 'Describe when these instructions should be loaded by the agent based on task context' # when provided, instructions will automatically be added to the request context when the pattern matches an attached file
---

<!-- Tip: Use /create-instructions in chat to generate content with agent assistance -->

- title = "Telegram Bot Wrapper for OpenAI API"
- description = "A Telegram bot that serves as a wrapper for the OpenAI API, allowing users to interact with OpenAI's language models through Telegram bots."

## Features
- Seamless integration with Telegram bots.
- Support for various OpenAI API endpoints/models.
- Easy configuration and deployment.
- Secure handling of API keys and tokens.
- User-friendly interface for interacting with OpenAI's language models.
- must be able to handle multiple users and conversations simultaneously.
- should include error handling and logging for debugging purposes.
- should be designed with scalability in mind to accommodate future growth and additional features.
- should be customizable to change API endpoints, API keys, and other settings without modifying the codebase from the ENV file or a config file.

## Technologies Used
- Python for backend development.
- Telegram Bot API for bot integration.
- OpenAI API for language model interactions.
- Docker for containerization and deployment.
