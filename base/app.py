
from telegram.ext import Handler
from werkzeug.local import Local, release_local
import abc
import collections
import logging
import re
import traceback

Command = collections.namedtuple('Command', 'name text')
CommandHandler = collections.namedtuple('CommandHandler', 'name func help')

#: GLobal data available inside the application handlers.
g = Local()
current_app = g('current_app')
update = g('update')
bot = g('bot')
command = g('command')
callback_middleware_result = g('callback_middleware_result')


def init_local(app, bot, update):
  g.current_app = app
  g.update = update
  g.bot = bot
  g.command = None
  g.callback_middleware_result = {}


class EndUpdateException(Exception):
  """
  Can be raised to prematurely end the handling of an update. Note that
  all #Middleware.after_handle_update() methods will be invoked nevertheless.
  """


class Middleware(metaclass=abc.ABCMeta):

  @abc.abstractmethod
  def before_handle_update(self):
    pass

  @abc.abstractmethod
  def after_handle_update(self):
    pass


class CallbackMiddleware(Middleware):

  def __init__(self, callback):
    self.callback = callback

  def before_handle_update(self):
    callback_middleware_result[self] = self.callback()

  def after_handle_update(self):
    result = callback_middleware_result.get(self)
    if callable(result):
      result()


class Application(Handler):
  """
  This object represents a telegram bot application. The application is just
  another telegram #Handler.
  """

  def __init__(self, name, debug=False):
    self.name = name
    self.logger = logging.Logger(name)
    self.debug = debug
    self._middleware = []
    self.commands = {'help': CommandHandler('help', do_help, 'Show this help.')}
    self.message_handler = None
    self.edited_message_handler = None
    self.inline_query_handler = None
    self.chosen_inline_result_handler = None
    self.callback_query_handler = None
    self.channel_post_handler = None
    self.edited_channel_post_handler = None
    self.exception_handler = None
    self.error_handler = None

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(levelname)s -%(asctime)s]: %(message)s'))
    self.logger.addHandler(handler)

  def check_update(self, update):
    # FIXME: If we wanted the #Application to function together with other
    #        telegram #Handler#s, we would need to properly check whether
    #        we can handle the update.
    return True

  def handle_update(self, update, dispatcher):
    init_local(self, dispatcher.bot, update)
    if update.message:
      g.command = parse_command(update.message.text)

    try:
      for mw in self._middleware:
        mw.before_handle_update()
      if g.command:
        self.handle_command()
      elif update.message:
        self.handle_message()
      elif update.edited_message:
        self.handle_edited_message()
      elif update.inline_query:
        self.handle_inline_query()
      elif update.chosen_inline_result:
        self.handle_chosen_inline_result()
      elif update.callback_query:
        self.handle_callback_query()
      elif update.channel_post:
        self.handle_channel_post()
      elif update.edited_channel_post:
        self.handle_edited_channel_post()
    except EndUpdateException:
      return
    except BaseException as exc:
      self.handle_exception(exc)
    finally:
      try:
        for mw in self._middleware:
          mw.after_handle_update()
      finally:
        release_local(g)

  def handle_command(self):
    if g.command.name in self.commands:
      self.commands[g.command.name].func()
    else:
      self.handle_message()

  def handle_message(self):
    if self.message_handler:
      self.message_handler()

  def handle_edited_message(self):
    if self.edited_message_handler:
      self.edited_message_handler()

  def handle_inline_query(self):
    if self.inline_query_handler:
      self.inline_query_handler()

  def handle_chosen_inline_result(self):
    if self.chosen_inline_result_handler:
      self.chosen_inline_result_handler()

  def handle_callback_query(self):
    if self.callback_query_handler:
      self.callback_query_handler()

  def handle_channel_post(self):
    if self.channel_post_handler:
      self.channel_post_handler()

  def handle_edited_channel_post(self):
    if self.edited_channel_post_handler:
      self.edited_channel_post_handler()

  def handle_exception(self, exc):
    if self.exception_handler:
      self.exception_handler(exc)
    else:
      msg = traceback.format_exc()
      self.logger.exception('Update "%s" has caused an exception.', update)
      if self.debug:
        reply_text(msg)

  def handle_error(self, bot, update, error):
    init_local(self, bot, update)
    if self.error_handler:
      self.error_handler(error)
    else:
      self.logger.error('Update "%s" caused error "%s"', update, error)

  def command(self, name_or_func=None, help=None):
    name = name_or_func
    def decorator(func):
      self.commands[name] = CommandHandler(
        name or func.__name__, func, help or func.__doc__)
      return func

    if callable(name_or_func):
      name = name_or_func.__name__
      return decorator(name_or_func)
    return decorator

  def message(self, func):
    self.message_handler = func
    return func

  def edited_message(self, func):
    self.edited_message_handler = func
    return func

  def inline_query(self, func):
    self.inline_query_handler = func
    return func

  def chosen_inline_result(self, func):
    self.chosen_inline_result_handler = func
    return func

  def callback_query(self, func):
    self.callback_query = func
    return func

  def channel_post(self, func):
    self.channel_post_handler = func
    return func

  def edited_channel_post(self, func):
    self.edited_channel_post_handler = func
    return func

  def exception(self, func):
    self.exception_handler = func
    return func

  def middleware(self, func):
    """
    Decorator for a function that acts as a middleware and will be called
    when #Middleware.before_handle_update() is called. If the decorated
    function returns a callable object, it will be called for
    #Middleware.after_handle_update().
    """

    self.add_middleware(CallbackMiddleware(func))

  def add_middleware(self, middleware):
    """
    Adds a #Middleware to the #Application.
    """

    self._middleware.append(middleware)


def parse_command(text):
  match = re.match('^/(\w+)', update.message.text)
  if match:
    text = update.message.text[match.end(1):].lstrip()
    return Command(match.group(1), text)
  return None


def end_update():
  """
  Raises an #EndUpdateException exception.
  """

  raise EndUpdateException()


def reply_text(*args, **kwargs):
  """
  Replies to the current chat. If a *chat_id* keyword parameter is specified,
  that chat is used instead.

  See also #telegram.bot.Bot.sendMessage().
  """

  chat_id = kwargs.pop('chat_id', None)
  if chat_id is None:
    chat_id = g.update.effective_chat.id
  g.bot.sendMessage(chat_id, *args, **kwargs)


def chat_action(action, *args, **kwargs):
  """
  Sends a chat action. See #telegram.bot.Bot.send_chat_action().
  """

  chat_id = kwargs.pop('chat_id', None)
  if chat_id is None:
    chat_id = g.update.effective_chat.id
  g.bot.send_chat_action(chat_id, action, **kwargs)


def do_help():
  """
  Default help action.
  """

  lines = []
  for cmd in current_app.commands.values():
    line = '/' + cmd.name
    if cmd.help:
      line += ' -- ' + cmd.help
    lines.append(line)
  lines.sort()
  lines.insert(0, 'Available commands:')
  reply_text('\n'.join(lines))
