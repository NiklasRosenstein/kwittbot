
from telegram.ext import Updater, Filters
from telegram.ext import InlineQueryHandler, MessageHandler
from telegram import ChatAction, ParseMode
from textwrap import dedent
from werkzeug.local import Local

import logging
import types
import config from './config.json'
import db from './db'
import handlers from './base/handler'
import {LocalMiddleware} from './base/middleware'
import {UserMiddleware, UpdateMiddleware} from './middleware'
import {escape_markdown} from './utils'

#: Global thread-local object that stores information about the current
#: telegram update such as the current #db.User and the current #bot and
#: #update so other functions can access it without passing the information
#: to the function explicitly. These members are initialized with the
#: #UserMiddleware and #UpdateMiddleware.
g = Local()


def reply(*args, **kwargs):
  """
  Replies to the current chat. If a *chat_id* keyword parameter is specified,
  that chat is used instead. Requires #g.bot and #g.update initialized using
  the #UpdateMiddleware.
  """

  chat_id = kwargs.pop('chat_id', None)
  if chat_id is None:
    chat_id = g.update.effective_chat.id
  g.bot.sendMessage(chat_id, *args, **kwargs)


def chat_action(action, *args, **kwargs):
  chat_id = kwargs.pop('chat_id', None)
  if chat_id is None:
    chat_id = g.update.effective_chat.id
  g.bot.send_chat_action(chat_id, action, **kwargs)


class KwittbotCommandHandler(handlers.CommandHandler):

  def handle_command(self, bot, update):
    logging.info('/%s from @%s', update.message.command, update.effective_user.username)
    super().handle_command(bot, update)

  def _setup_account(self):
    # Create a new user.
    g.user = db.User.from_telegram_user(g.update.effective_chat, g.update.effective_user)
    g.user.save()

    reply(
      "Hi {}! Seems like this is your first time here. You can now use "
      "@KwittBot to send money to your friends or request money from them.\n"
      "Type /help when you're stuck!"
      .format(g.user.username)
    )

  def _parse_send_or_request(self, cmd, text):
    """
    Parses the text sent to the /send or /request command which is of the
    syntax: /COMMAND AMOUNT @USER [DESCRIPTION]

    # Return
    (amount, target, description) or #False
    """

    parts = text.strip().split()
    if len(parts) < 2 or not parts[1].startswith('@'):
      reply('Syntax is /{} AMOUNT @USER [DESCRIPTION]'.format(cmd))
      return False

    try:
      amount = db.Decimal(parts[0])
    except db.decimal.InvalidOperation:
      reply('The amount you specified is invalid: {!r}'.format(parts[0]))
      return False

    # Find the specified @USER.
    target_name = parts[1][1:]
    target = db.User.objects(username__iexact=target_name).first()
    if not target:
      reply(
        "Sorry, I could not find @{}. Maybe they are not using "
        "@KwittBot, yet?"
        .format(target_name)
      )
      return False

    if target == g.user and not config['settings']['allowSendToSelf']:
      reply("Sorry, you can not specify yourself in this command.")
      return

    description = ' '.join(parts[2:])
    return (amount, target, description)

  def do_start(self, bot, update):
    " Register to @KwittBot. "

    chat_action('typing')
    if g.user:
      reply("We already got you covered. Type /help when you're stuck!")
    else:
      self._setup_account()

  def do_send(self, bot, update):
    " Send money to a friend. "

    chat_action('typing')
    if not g.user:
      self._setup_account()

    result = self._parse_send_or_request('send', update.message.text)
    if not result:
      return

    amount, target, description = result
    if amount > g.user.balance:
      reply(
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

    reply(
      "You have sent {} to @{}. You're new balance is {}."
      .format(amount, target.username, g.user.balance)
    )
    reply(
      "You just received {} from @{}."
      .format(amount, g.user.username),
      chat_id=target.chat_id
    )

  def do_request(self, bot, update):
    " Request money from a friend. "

    chat_action('typing')
    if not g.user:
      self._setup_account()

    result = self._parse_send_or_request('send', update.message.text)
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

    reply(
      "You have requested {} from @{}."
      .format(amount, target.username)
    )
    # TODO: InlineKeyboardButton to comply to the request.
    append = '\nTheir message: "{}"'.format(description) if description else ""
    reply(
      ("@{} requested you to send {}." + append)
      .format(g.user.username, amount, description),
      chat_id=target.chat_id
    )

  def do_balance(self, bot, update):
    " Check your current balance on @KwittBot. "

    chat_action('typing')
    if not g.user:
      self._setup_account()

    g.user.update_balance()

    reply(
      'Your current balance is *{}*.'.format(g.user.balance),
      parse_mode=ParseMode.MARKDOWN
    )

  def do_transactions(self, bot, update):
    " Show your transaction history. "

    chat_action('typing')
    if not g.user:
      self._setup_account()

    # TODO: Parse arguments and display transactions accordingly.

    transactions = g.user.get_transactions()
    if not transactions:
      reply(
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
    reply(message, parse_mode=ParseMode.MARKDOWN)

  def do_credit(self, bot, update):
    " Charge your account (eg. via PayPal). "

    chat_action('typing')
    if not g.user:
      self._setup_account()

    amount = update.message.text.strip()
    try:
      amount = db.Decimal(amount)
    except db.decimal.InvalidOperation:
      reply("The amount you entered is invalid: {!r}".format(amount))
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
    reply(
      "You've been credited *{}*.".format(amount),
      parse_mode=ParseMode.MARKDOWN
    )

  def do_debit(self, bot, update):
    " Withdraw money from your account. "

    reply("Currently not implemented.")


def error(bot, update, error):
  logging.error('Update "%s" caused error "%s"' % (update, error))


def main():
  logging.basicConfig(format='[%(levelname)s - %(asctime)s]: %(message)s', level=logging.INFO)
  logging.info('Firing up KwittBot ...')

  mwhandler = handlers.MiddlewareHandler()
  mwhandler.add_handler(KwittbotCommandHandler())
  mwhandler.add_middleware(LocalMiddleware([g]))
  mwhandler.add_middleware(UserMiddleware(g, 'user'))
  mwhandler.add_middleware(UpdateMiddleware(g))

  updater = Updater(config['telegramApiToken'])
  updater.dispatcher.add_handler(mwhandler)
  updater.dispatcher.add_error_handler(error)
  updater.start_polling()

  logging.info('Connecting to MongoDB ...')
  db.User.objects().first()  # Fake query, so that a connection will be established

  logging.info('Polling started, entering IDLE ...')
  updater.idle()


if require.main == module:
  main()
