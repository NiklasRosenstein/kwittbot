
from werkzeug.local import release_local


class Middleware(object):

  def before_handle_update(self, update, dispatcher):
    pass

  def after_handle_update(self, update, dispatcher):
    pass


class LocalMiddleware(Middleware):
  """
  A middleware that manages a #werkzeug.local.Local.
  """

  def __init__(self, locals):
    self._locals = locals

  def after_handle_update(self, update, dispatcher):
    for local in self._locals:
      release_local(local)
