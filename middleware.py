
import {Middleware} from './base/middleware'
import db from './db'


class InitLocalMiddleware(Middleware):

  def __init__(self, local, member_name, func):
    self.local = local
    self.member_name = member_name
    self.func = func

  def before_handle_update(self, update, dispatcher):
    setattr(self.local, self.member_name, self.func())


class UserMiddleware(Middleware):

  def __init__(self, local, member_name):
    self.local = local
    self.member_name = member_name

  def before_handle_update(self, update, dispatcher):
    if update.effective_user:
      try:
        user = db.User.objects(telegram_id=update.effective_user.id).get()
      except db.User.DoesNotExist:
        user = None
      setattr(self.local, self.member_name, user)


class UpdateMiddleware(Middleware):

  def __init__(self, local):
    self.local = local

  def before_handle_update(self, update, dispatcher):
    self.local.update = update
    self.local.bot = dispatcher.bot
