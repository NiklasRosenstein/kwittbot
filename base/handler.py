
from telegram.ext import Handler, MessageHandler, Filters
import re


class CommandHandler(MessageHandler):
  """
  An alternative to #telegram.ext.CommandHandler that provides a
  #handle_command() function that can be overwritten. It's default
  implementation looks for a callable member with the same name as
  the command to invoke.
  """

  def __init__(self):
    MessageHandler.__init__(self, Filters.text | Filters.command, None)

  def handle_update(self, update, dispatcher):
    bot = dispatcher.bot
    match = re.match('^/(\w+)', update.message.text)
    if match:
      cmdname = match.group(1)
      text = update.message.text[1 + len(cmdname):].lstrip()
      update.message.command = cmdname
      update.message.text = text
      self.handle_command(bot, update)

  def handle_command(self, bot, update):
    func = getattr(self, 'do_' + update.message.command, None)
    if callable(func):
      func(bot, update)
      return True
    return False

  def do_help(self, bot, update):
    " Show this help. "

    commands = []
    for key in dir(self):
      if not key.startswith('do_'): continue
      value = getattr(self, key)
      if not callable(value): continue
      line = '/' + key[3:]
      if value.__doc__:
        line += value.__doc__
      commands.append(line)
    commands.sort()
    update.message.reply_text('Available commands:\n' + '\n'.join(commands))


class MiddlewareHandler(Handler):

  def __init__(self):
    self.middlewares = []
    self.handlers = []

  def check_update(self, update):
    for handler in self.handlers:
      if handler.check_update(update):
        update.__handler = handler
        return True

  def handle_update(self, update, dispatcher):
    handler = update.__handler
    del update.__handler

    for mw in self.middlewares:
      mw.before_handle_update(update, dispatcher)
    handler.handle_update(update, dispatcher)
    for mw in reversed(self.middlewares):
      mw.after_handle_update(update, dispatcher)

  def add_handler(self, handler):
    self.handlers.append(handler)

  def add_middleware(self, middleware):
    self.middlewares.append(middleware)
