import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import filters, MessageHandler, CommandHandler, ApplicationBuilder, ContextTypes

from chain import get_chain_response
from database import save_message_to_db, connect_2_db
from transcribe_audio import oga_2_mp3_2_text
from text_to_speech import get_audio

import os
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Load environment variables from .env file
load_dotenv()

TELEGRAM_BOT = os.getenv('TELEGRAM_BOT')

last_user_message_id = None
last_bot_message_id = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, 
                                   text="I'm a bot, please talk to me!")

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    message_id = update.message.message_id

    # Delete previous messages
    for message in context.bot.get_chat_messages(chat_id=chat_id, limit=message_id):
        context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)

    await context.bot.send_message(chat_id=chat_id, text="Conversation cleared.")

async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_user_message_id, last_bot_message_id

    # Get the chat_id
    chat_id = update.effective_chat.id

    # Delete the user's last message
    if last_user_message_id is not None:
        await context.bot.delete_message(chat_id=chat_id, message_id=last_user_message_id)

    # Delete the bot's last message
    if last_bot_message_id is not None:
        await context.bot.delete_message(chat_id=chat_id, message_id=last_bot_message_id)

    # Connect to the database
    _, message_history = connect_2_db()

    # Remove the last two messages (user's and bot's) from the database
    message_history.update_one(
        {'user_id': str(chat_id)},
        {'$pop': {'messages': 1}}
    )
    message_history.update_one(
        {'user_id': str(chat_id)},
        {'$pop': {'messages': 1}}
    )

    await context.bot.send_message(chat_id=chat_id, text="Last message deleted.")

async def delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Get the chat_id
    chat_id = update.effective_chat.id

    # Connect to the database
    _, message_history = connect_2_db()

    # Remove all messages for the user from the database
    message_history.update_one(
        {'user_id': str(chat_id)},
        {'$set': {'messages': []}}
    )

    await context.bot.send_message(chat_id=chat_id, text="All messages deleted.")

async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_user_message_id, last_bot_message_id

    # Store the user's message_id
    last_user_message_id = update.message.message_id

    user_text = update.message.text
    user_firstname = update.message.chat.first_name
    user_id = str(update.message.chat.id)

    users, message_history = connect_2_db()

    # Get response and audio
    model_res = get_chain_response(user_id, user_text, user_firstname)
    
    # Store to db
    save_message_to_db(user_id, user_text, model_res)

    # Get the message ID to reply to
    reply_to_message_id = update.message.message_id
    
    # Send a text message and store the message_id
    bot_message = await update.message.reply_text(text=model_res, reply_to_message_id=reply_to_message_id)
    last_bot_message_id = bot_message.message_id

async def audio_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_user_message_id, last_bot_message_id

    last_user_message_id = update.message.message_id

    current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    user_id = str(update.message.chat.id)
    user_lastname = update.message.chat.last_name
    user_firstname = update.message.chat.first_name

    users, message_history = connect_2_db()
    
    user_data = users.find_one({"user_id": user_id})
    
    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)
    await new_file.download_to_drive(f"{file_id}.oga")
    
    user_text = oga_2_mp3_2_text(file_id)

    model_res = get_chain_response(user_id, user_text, user_firstname)

    save_message_to_db(user_id, user_text, model_res)

    reply_to_message_id = update.message.message_id
    
    bot_message = await update.message.reply_text(text=model_res, reply_to_message_id=reply_to_message_id)
    last_bot_message_id = bot_message.message_id

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")


if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    delete_handler = CommandHandler('delete', delete_last)  # Define delete_handler
    application.add_handler(delete_handler)
    
    delete_all_handler = CommandHandler('delete_all', delete_all)
    application.add_handler(delete_all_handler)

    clear_handler = CommandHandler('clear', clear)
    application.add_handler(clear_handler)

    text_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), text_input)
    application.add_handler(text_handler)

    # Handler for audio messages
    audio_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), audio_input)
    application.add_handler(audio_handler)

    # Removing the payment-related handlers
    # Removed: deposit_handler, CallbackQueryHandler(handle_button), PreCheckoutQueryHandler(precheckout_callback), 
    # and MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback)

    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    application.add_handler(unknown_handler)

    application.run_polling()
    # Store the user's message_id
    last_user_message_id = update.message.message_id

    user_text = update.message.text
    user_firstname = update.message.chat.first_name
    user_id = str(update.message.chat.id)

    users, message_history = connect_2_db()

    # insert user expiration date to mongo
    user_data = users.find_one({"user_id": user_id})

    # get response and audio
    model_res = get_chain_response(user_id, user_text, user_firstname)
    
    # store to db
    save_message_to_db(user_id, user_text, model_res)

    # Get the message ID to reply to
    reply_to_message_id = update.message.message_id
    
    # Send a text message and store the message_id
    bot_message = await update.message.reply_text(text=model_res, reply_to_message_id=reply_to_message_id)
    last_bot_message_id = bot_message.message_id

async def audio_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_user_message_id, last_bot_message_id
    
    if not is_username_allowed(username):
        await context.bot.send_message(chat_id=update.message.chat_id, text="You are not allowed to use this bot.")
        return
    
    last_user_message_id = update.message.message_id

    current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    user_id = str(update.message.chat.id)
    user_lastname = update.message.chat.last_name
    user_firstname = update.message.chat.first_name

    users, message_history = connect_2_db()
    
    user_data = users.find_one({"user_id": user_id})
    
    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)
    await new_file.download_to_drive(f"{file_id}.oga")
    
    user_text = oga_2_mp3_2_text(file_id)

    model_res = get_chain_response(user_id, user_text, user_firstname)

    save_message_to_db(user_id, user_text, model_res)

    reply_to_message_id = update.message.message_id
    
    bot_message = await update.message.reply_text(text=model_res, reply_to_message_id=reply_to_message_id)
    last_bot_message_id = bot_message.message_id

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Price: $10", callback_data='10'),
            InlineKeyboardButton("Price: $20", callback_data='20'),
        ],
        [
            InlineKeyboardButton("Price: $30", callback_data='30'),
            InlineKeyboardButton("Price: $5000", callback_data='5000'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose a price:', reply_markup=reply_markup)


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    selected_price = int(query.data)  # Price in USD cents

    # Invoice parameters
    title = "Product Title"
    description = "Product Description"
    payload = "Custom-Payload"
    provider_token = STRIPE_TEST_PAY
    currency = "USD"
    prices = [LabeledPrice("Product", selected_price * 100)]  # Convert to cents

    # Sending the invoice
    await context.bot.send_invoice(
        query.message.chat_id, title, description, payload,
        provider_token, currency, prices
    )
    await query.answer()


# after (optional) shipping, it's the pre-checkout
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answers the PreQecheckoutQuery"""
    query = update.pre_checkout_query
    # check the payload, is this from your bot?
    if query.invoice_payload != "Custom-Payload":
        # answer False pre_checkout_query
        await query.answer(ok=False, error_message="Something went wrong...")
    else:
        await query.answer(ok=True)


# finally, after contacting the payment provider...
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirms the successful payment."""
    # Get the total_amount from the successful_payment object (in the smallest units of the currency, e.g., cents)
    total_amount = update.message.successful_payment.total_amount
    # Calculate duration in minutes (1$ = 1 minute, assuming total_amount is in cents)
    duration_minutes = total_amount // 100
    # Calculate the expiration time
    # Store the expiration time
    user_id = str(update.message.chat.id)

    users, message_history = connect_2_db()
    
    # Update or insert the user into the collection
    users.update_one(
        {'user_id': user_id},
        upsert=True)

    # Notify the user
    await update.message.reply_text(f"Thank you for your payment! You can now use the bot for {duration_minutes} minutes.")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry, I didn't understand that command.")



if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    delete_handler = CommandHandler('delete', delete_last)  # Define delete_handler
    application.add_handler(delete_handler)
    
    delete_all_handler = CommandHandler('delete_all', delete_all)
    application.add_handler(delete_all_handler)

    clear_handler = CommandHandler('clear', clear)
    application.add_handler(clear_handler)

    text_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), text_input)
    application.add_handler(text_handler)

    #                                               NOT A COMMAND i.e. /start
    audio_handler = MessageHandler(filters.VOICE & (~filters.COMMAND), audio_input)
    application.add_handler(audio_handler)


    deposit_handler = CommandHandler('deposit', deposit)
    application.add_handler(deposit_handler)

    application.add_handler(CallbackQueryHandler(handle_button))

    
    # Pre-checkout handler to final check
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    # Success! Notify your user!
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    application.add_handler(unknown_handler)

    application.run_polling()
