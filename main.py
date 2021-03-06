
from telegram.ext import Updater, Filters
from telegram.ext import InlineQueryHandler, MessageHandler
from telegram import ChatAction, ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from textwrap import dedent
from werkzeug.local import Local

import functools
import logging
import types

import config from './config.json'
import db from './db'
import {escape_markdown} from './utils'
import {
  Application, g,
  update, command,
  reply_text, chat_action
} from './base/app'


# Our chatbot :3
app = Application('KwittBot', debug=True)

# We don't use a proxy for the user object yet, because MongoEngine has
# trouble processing it!
#user = g('user')


def requires_user(func):
  """
  Decorator that automatically registeres a user.
  """

  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    if not user:
      register_user()
    return func(*args, **kwargs)

  return wrapper


@app.middleware
def user_middleware():
  # Find the db.User that has issued the current update and make it
  # available in g.user.
  user = None
  if update.effective_user:
    try:
      user = db.User.objects(telegram_id=update.effective_user.id).get()
    except db.User.DoesNotExist:
      user = None
  g.user = user


@app.middleware
def logging_middleware():
  if g.command:
    logging.info('/%s from @%s', g.command.name, update.effective_user.username)


@app.command
def start():
  " Register to @KwittBot. "

  chat_action('typing')
  if user:
    reply_text("We already got you covered. Type /help when you're stuck!")
  else:
    register_user()


@app.command
@requires_user
def send():
  " Send money to a friend. "

  chat_action('typing')
  result = parse_send_or_request('send', command.text)
  if not result:
    return

  amount, target, description = result
  if amount > g.user.balance:
    reply_text(
      "Sorry, your balance is {}. You can not send {} to @{}!"
      .format(g.user.balance, amount, target.username)
    )
    return

  # Create a new transaction between the current user and the target.
  transaction = db.Transaction(
    amount=amount,
    receiver=target,
    sender=g.user,
    gateway_details=None,
    description=description
  )
  transaction.save()

  # Update both user's balance.
  g.user.update_balance()
  target.update_balance()

  reply_text(
    "You have sent {} to @{}. You're new balance is {}."
    .format(amount, target.username, user.balance)
  )
  reply_text(
    "You just received {} from @{}."
    .format(amount, user.username),
    chat_id=target.chat_id
  )

@app.command
@requires_user
def request():
  " Request money from a friend. "

  chat_action('typing')
  result = parse_send_or_request('send', command.text)
  if not result:
    return

  amount, target, description = result

  # Issue a new request to the target user.
  request = db.Request(
    issuer=g.user,
    target=target,
    amount=amount,
    description=description,
    mode=db.Request.Modes.OPEN
  )
  request.save()

  reply_text(
    "You have requested {} from @{}."
    .format(amount, target.username)
  )

  # Buttons to answer the request.
  markup = InlineKeyboardMarkup([
    [
      InlineKeyboardButton('Send {}'.format(amount), callback_data='send:' + str(request.id)),
      InlineKeyboardButton('Reject', callback_data='reject:' + str(request.id)),
    ]
  ])

  # Send a message to the user that the money is being requested from.
  their_msg = '\nTheir message: "{}"'.format(description) if description else ""
  reply_text(
    ("@{} requested you to send {}." + their_msg)
    .format(g.user.username, amount, description),
    chat_id=target.chat_id,
    reply_markup=markup
  )


@app.command
@requires_user
def balance():
  " Check your current balance on @KwittBot. "

  chat_action('typing')
  g.user.update_balance()

  reply_text(
    'Your current balance is *{}*.'.format(g.user.balance),
    parse_mode=ParseMode.MARKDOWN
  )


@app.command
@requires_user
def transactions():
  " Show your transaction history. "

  chat_action('typing')

  # TODO: Parse arguments and display transactions accordingly.

  transactions = g.user.get_transactions()
  if not transactions:
    reply_text(
      "There are no transactions on your account, yet."
    )
    return

  # Build a list of the transactions.
  lines = [
    'Showing {} out of {} transactions:'
    .format(len(transactions), len(transactions))
  ]
  for t in transactions:
    gain = False
    if t.receiver == g.user:
      gain = True
      if not t.sender:
        msg = 'from {}'.format(t.gateway_details.provider)
      elif t.sender == t.receiver:
        msg = 'to yourself'
      else:
        msg = 'from @{}'.format(t.sender.username)
    elif t.sender == g.user:
      msg = 'to @{}'.format(t.receiver.username)

    msg += ' ({})'.format(t.date.strftime('%Y-%m-%d %H:%M'))
    lines.append('*{}* '.format(t.amount) + escape_markdown(msg))

  message = '\n'.join(lines)
  reply_text(message, parse_mode=ParseMode.MARKDOWN)


@app.command
@requires_user
def credit():
  " Charge your account (eg. via PayPal). "

  chat_action('typing')
  amount = command.text.strip()
  try:
    amount = db.Decimal(amount)
  except db.decimal.InvalidOperation:
    reply_text("The amount you entered is invalid: {!r}".format(amount))
    return

  # Create a new transaction from a payment gateway.
  details = db.GatewayTransactionDetails(provider='telegram_credit_command')

  # And a new transaction from the gateway to the user.
  transaction = db.Transaction(
    amount=amount,
    receiver=g.user,
    sender=None,
    gateway_details=details
  )

  # FIXME: Two-phase transaction to ensure either both objects are saved
  #        or none!
  details.save()
  transaction.save()

  # Update the users balance/
  g.user.update_balance()
  reply_text(
    "You've been credited *{}*.".format(amount),
    parse_mode=ParseMode.MARKDOWN
  )


@app.command
@requires_user
def debit():
  " Withdraw money from your account. "

  reply_text("Currently not implemented.")


@app.callback_query
def callback_data():
  query = update.callback_query
  data = query.data
  if data.startswith('send:') or data.startswith('reject:'):
    request_id = data.partition(':')[2]
    request = db.Request.objects(id=request_id).first()
    if not request:
      reply_text('Error: Request "{}" does not exist.'.format(request_id))
      return

    if request.target != g.user:
      # That's a security issue. Ideally, other users wouldn't be able
      # to find out the ID of a request targeting a different user.
      app.logger.warning('User @%s (id: %s) was trying to answer request '
        '%s which is actually targeted to @%s (id: %s)', g.user.username,
        g.user.telegram_id, request.id, request.target.username,
        request.target.telegram_id)

      reply_text("Wait wait wait, that's not your money request! What are you doing here?!")
      return

    if request.mode != request.Modes.OPEN:
      reply_text("The request is not open anymore.")
      return

    # TODO:
    if data.startswith('send:'):
      reply_text('TODO: Implement sending a request (I marked it '
        'as fulfilled nevertheless)')
      request.mode = request.Modes.FULFILLED
      request.save()
    else:
      reply_text("You rejected the request.")
      request.mode = request.Modes.REJECTED
      request.save()
      reply_text(
        "@{} rejected your request for {}."
        .format(g.user.username, request.amount),
        chat_id=request.issuer.chat_id
      )


def register_user():
  # Create a new user.
  g.user = db.User.from_telegram_user(g.update.effective_chat, g.update.effective_user)
  g.user.save()

  reply_text(
    "Hi {}! Seems like this is your first time here. You can now use "
    "@KwittBot to send money to your friends or request money from them.\n"
    "Type /help when you're stuck!"
    .format(g.user.username)
  )


def parse_send_or_request(cmd, text):
  """
  Parses the text sent to the /send or /request command which is of the
  syntax: /COMMAND AMOUNT @USER [DESCRIPTION]

  # Return
  (amount, target, description) or #False
  """

  parts = text.strip().split()
  if len(parts) < 2 or not parts[1].startswith('@'):
    reply_text('Syntax is /{} AMOUNT @USER [DESCRIPTION]'.format(cmd))
    return False

  try:
    amount = db.Decimal(parts[0])
  except db.decimal.InvalidOperation:
    reply_text('The amount you specified is invalid: {!r}'.format(parts[0]))
    return False

  # Find the specified @USER.
  target_name = parts[1][1:]
  target = db.User.objects(username__iexact=target_name).first()
  if not target:
    reply_text(
      "Sorry, I could not find @{}. Maybe they are not using "
      "@KwittBot, yet?"
      .format(target_name)
    )
    return False

  if target == g.user and not config['settings']['allowSendToSelf']:
    reply_text("Sorry, you can not specify yourself in this command.")
    return

  description = ' '.join(parts[2:])
  return (amount, target, description)
def main():
  logging.basicConfig(format='[%(levelname)s - %(asctime)s]: %(message)s', level=logging.INFO)
  logging.info('Firing up KwittBot ...')

  updater = Updater(config['telegramApiToken'])
  updater.dispatcher.add_handler(app)
  updater.dispatcher.add_error_handler(app.handle_error)
  updater.start_polling()

  logging.info('Connecting to MongoDB ...')
  db.User.objects().first()  # Fake query, so that a connection will be established

  logging.info('Polling started, entering IDLE ...')
  updater.idle()


if require.main == module:
  main()
