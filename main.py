
from telegram.ext import Updater, MessageHandler, InlineQueryHandler, Filters
from telegram import InputTextMessageContent, InlineQueryResultArticle
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

import logging
import signal
import config from './config.json'


def message(bot, update):
  pass


def inline(bot, update):
  query = update.inline_query

  markup = InlineKeyboardMarkup([
    [InlineKeyboardButton("Send Money", callback_data='send')]
  ])
  content = InputTextMessageContent('Uh, how much money exactly?')
  article = InlineQueryResultArticle('SomeID', 'Send Money', content, reply_markup=markup)

  query.answer([article])


def error(bot, update, error):
  logging.warning('Update "%s" caused error "%s"' % (update, error))


def main():
  logging.basicConfig(format='[%(levelname)s - %(asctime)s]: %(message)s', level=logging.INFO)
  logging.info('Firing up KwittBot ...')

  updater = Updater(config['telegramApiToken'])
  updater.dispatcher.add_handler(MessageHandler(Filters.text, message))
  updater.dispatcher.add_handler(InlineQueryHandler(inline))
  updater.dispatcher.add_error_handler(error)
  updater.start_polling()

  logging.info('Polling started, entering IDLE ...')
  updater.idle()


if require.main == module:
  main()
