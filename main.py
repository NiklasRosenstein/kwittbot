
from telegram.ext import Updater, Filters
from telegram.ext import CommandHandler, InlineQueryHandler, MessageHandler
from telegram import ChatAction, ParseMode
from textwrap import dedent

import logging
import signal
import re
import config from './config.json'
import db from './db'


def escape_markdown(text):
  """Helper function to escape telegram markup symbols"""
  escape_chars = '\*_`\['
  return re.sub(r'([%s])' % escape_chars, r'\\\1', text)


def start(bot, update):
  logging.info('/start %s', update.message.from_user)

  reply = update.message.reply_text
  user = db.User.objects(telegram_id=update.message.from_user.id).first()
  if not user:
    reply("Hi {}, I am @KwittBot! Seems like this is your "
      "first time here, so I'll quickly set up everything for you."
      .format(update.message.from_user.name))
    bot.send_chat_action(chat_id=update.message.chat.id, action=ChatAction.TYPING)
    user = db.User.from_telegram_user(update.message.chat, update.message.from_user)
    user.save()
    reply("Done. You can now use @KwittBot!")
    help(bot, update)
  else:
    reply("Seems like we've already got you covered. Type /help if you "
      "don't know how to use @KwittBot!")
    # TODO: Maybe update user details in case they changed?


def help(bot, update):
  logging.info('/help %s', update.message.from_user)

  update.message.reply_text(dedent("""
    Available commands:\n
    /start -- Register to @KwittBot
    /help -- Show this help
    /send -- Send money to a friend
    /request -- Request money from a friend
    /balance -- Show your current balance
    /transactions -- Show your transaction history.
    /credit -- Charge your @KwittBot account
    /debit -- Withdraw money from your @KwittBot account
    """))


def send(bot, update):
  logging.info('/send %s', update.message.from_user)

  reply = update.message.reply_text
  user = db.User.objects(telegram_id=update.message.from_user.id).first()
  if not user:
    reply("I don't know you man.")
    return

  parts = update.message.text[5:].strip().split()
  if len(parts) != 2 or not parts[1].startswith('@'):
    reply('Invalid syntax')
    return
  try:
    amount = db.Decimal(parts[0])
  except db.decimal.InvalidOperation:
    reply('Invalid amount')
    return

  receiver = db.User.objects(username__iexact=parts[1][1:]).first()
  if not receiver:
    reply("We couldn't find @{}, maybe he/she is not using @KwittBot yet?"
      .format(parts[1][1:]))
    return
  elif receiver == user and not config['settings']['allowSendToSelf']:
    reply("You can't send money to yourself, fool!")
    return

  if amount > user.balance:
    print(user)
    reply("You're balance is {}, you can not send {}.".format(user.balance, amount))
    return

  transaction = db.Transaction(amount=amount, receiver=receiver, sender=user,
    gateway_details=None)
  transaction.save()

  user.update_balance()
  receiver.update_balance()
  reply("You've sent {} to @{}! You're new balance is {}.".format(amount,
    receiver.username, user.balance))
  bot.sendMessage(receiver.chat_id, "You just received {} from @{}".format(amount, user.username))


def request(bot, update):
  pass


def balance(bot, update):
  logging.info('/balance %s', update.message.from_user)

  reply = update.message.reply_text
  user = db.User.objects(telegram_id=update.message.from_user.id).first()
  if not user:
    reply("Sorry, we can't find you in our database! Weird, we currently "
      "don't support deleting your account.")
    return

  bot.send_chat_action(chat_id=update.message.chat.id, action=ChatAction.TYPING)
  user.update_balance()

  reply('Your balance is *{}*'.format(user.balance), parse_mode=ParseMode.MARKDOWN)


def transactions(bot, update):
  logging.info('/transactions %s', update.message.from_user)

  reply = update.message.reply_text
  user = db.User.objects(telegram_id=update.message.from_user.id).first()
  if not user:
    reply("Sorry, who are you again?")
    return

  lines = ['Here is a list of your transactions:']

  transactions = user.get_transactions()
  for t in transactions:
    gain = False
    if t.receiver == user:
      gain = True
      if not t.sender:
        msg = 'from {}'.format(t.gateway_details.provider)
      elif t.sender == t.receiver:
        msg = 'to yourself'
      else:
        msg = 'from @{}'.format(t.sender.username)
    elif t.sender == user:
      msg = 'to @{}'.format(t.receiver.username)

    msg += ' ({})'.format(t.date.strftime('%Y-%m-%d %H:%M'))
    lines.append('*{}* '.format(t.amount) + escape_markdown(msg))

  if not transactions:
    lines.append('*No transactions*')

  reply('\n'.join(lines), parse_mode=ParseMode.MARKDOWN)


def credit(bot, update):
  logging.info('/balance %s', update.message.from_user)

  reply = update.message.reply_text
  user = db.User.objects(telegram_id=update.message.from_user.id).first()
  if not user:
    reply("Sorry, we can't find you in our database!")
    return

  amount = update.message.text[7:].strip()
  try:
    amount = db.Decimal(amount)
  except ValueError as exc:
    reply(str(exc))
    return

  details = db.GatewayTransactionDetails(provider='telegram_dev_command')
  transaction = db.Transaction(amount=amount, receiver=user, sender=None,
    gateway_details=details)

  details.save()
  transaction.save()
  user.update_balance()
  reply("You've been credited *{}*".format(amount), parse_mode=ParseMode.MARKDOWN)


def debit(bot, update):
  pass


def error(bot, update, error):
  logging.error('Update "%s" caused error "%s"' % (update, error))


def main():
  logging.basicConfig(format='[%(levelname)s - %(asctime)s]: %(message)s', level=logging.INFO)
  logging.info('Firing up KwittBot ...')

  updater = Updater(config['telegramApiToken'])
  updater.dispatcher.add_handler(CommandHandler('start', start))
  updater.dispatcher.add_handler(CommandHandler('help', help))
  updater.dispatcher.add_handler(CommandHandler('send', send))
  updater.dispatcher.add_handler(CommandHandler('request', request))
  updater.dispatcher.add_handler(CommandHandler('balance', balance))
  updater.dispatcher.add_handler(CommandHandler('transactions', transactions))
  updater.dispatcher.add_handler(CommandHandler('credit', credit))
  updater.dispatcher.add_handler(CommandHandler('debit', debit))
  updater.dispatcher.add_error_handler(error)
  updater.start_polling()

  logging.info('Connecting to MongoDB ...')
  db.User.objects().first()  # Fake query, so that a connection will be established

  logging.info('Polling started, entering IDLE ...')
  updater.idle()


if require.main == module:
  main()
