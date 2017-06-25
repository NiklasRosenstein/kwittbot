
from datetime import datetime
from mongoengine import *
import decimal
import config from './config.json'

db = connect(**config['mongoDb'])
decimal_context = decimal.Context(prec=2)


def Decimal(number=0):
  return decimal.Decimal(number, decimal_context)


class User(Document):

  #: The ID of the bot's private chat with the user.
  chat_id = IntField(unique=True)

  #: Numeric ID of the telegram user that will not change.
  telegram_id = IntField(unique=True)

  #: Telegram username (without the @), can be changed by the user.
  username = StringField(unique=True)

  #: User's display name.
  name = StringField()

  #: User language code.
  language_code = StringField()

  #: The users current balance. This value is cached, but can be recomputed
  #: from the users transactions history.
  balance = DecimalField(precision=2)

  @classmethod
  def from_telegram_user(cls, chat, user):
    return cls(chat.id, user.id, user.username, user.name, user.language_code, 0.0)

  def update_balance(self):
    """
    This method must be called after a transaction for a user has been
    created. It recalculates the user's balance based on the transaction
    history.
    """

    balance = Decimal()
    for t in self.get_transactions():
      if t.receiver == t.sender:
        # We use self-transactions for simple testing purposes.
        # Skip them in the balance update.
        continue
      if t.receiver == self:
        balance += t.amount
      elif t.sender == self:
        balance -= t.amount
      else:
        raise RuntimeError('User is not part of this transaction', t)
    self.balance = balance
    self.save()

  def get_transactions(self):
    """
    Returns a query of all transactions that the user participates in
    as a receiver or sender.
    """

    return Transaction.objects(Q(receiver=self) | Q(sender=self))

  def get_requests(self, target=None):
    """
    Returns a query of all requests that the user issues.
    """

    query = Request.objects(issuer=self)
    if target is not None:
      query = query.filter(target=target)
    return query

  def get_reverse_requests(self):
    """
    Returns a query of all requests that have been targeted to this user.
    """

    return Request.objects(target=self)


class GatewayTransactionDetails(Document):
  """
  Represents a transaction from or to a Payment Gateway (eg. if the user wants
  to charge their account or withdraw money).
  """

  #: ID of the payment provider.
  provider = StringField()

  # TODO ...


class Transaction(Document):
  """
  A transaction between users is always a positive amount of money transfered
  from the #sender to the #receiver. If there is no #sender, there must be a
  a #gateway_details object and the transaction represents one debited or
  credited to/from a Payment Gateway (eg. PayPal, etc.).
  """

  #: The amount of money being transfered from the #receiver to the #sender
  #: or to the payment gateway as specified in #gatewaye_details. Always
  #: positive for user to user transactions.
  amount = DecimalField(precision=2)

  #: Date of the transaction in the server's local time.
  date = DateTimeField()

  #: The user that received the transaction.
  receiver = ReferenceField('User', reverse_delete_rule=DENY)

  #: The user that sent the transaction amount. This may be null when the
  #: transaction is actually one between a user and a payment gateway, in
  #: which case the #gateway_details are provided.
  sender = ReferenceField('User', reverse_delete_rule=DENY)

  #: If there is no #sender, the transaction represents a debit/credit to/from
  #: a payment gateway.
  gateway_details = ReferenceField('GatewayTransactionDetails', reverse_delete_rule=DENY)

  #: A text description of the transaction.
  description = StringField()

  def clean(self):
    if not self.date:
      self.date = datetime.now()
    if not self.sender:
      if not self.gateway_details:
        raise ValidationError('Transaction requires either a sender '
          'or gateway_details, otherwise we can not trace back the source '
          'of the transaction.')
    if self.sender and self.amount < 0:
      raise ValidationError('P2P transactions always require a positive amount.')
    if self.sender == self.receiver and not config['settings']['allowSendToSelf']:
      raise ValidationError('P2P transactions must have a different '
        'sender and receiver.')


class Request(Document):
  """
  Represents a request for money from another user.
  """

  #: The amount of money being requested.
  amount = DecimalField()

  #: The date that the request was issued.
  date = DateTimeField()

  #: The user that issued the request.
  issuer = ReferenceField('User', reverse_delete_rule=DENY)

  #: The user that is requested to send money.
  target = ReferenceField('User', reverse_delete_rule=DENY)

  #: A message for the request.
  description = ListField(StringField())

  def clean(self):
    if self.issuer == self.target and not config['settings']['allowSendToSelf']:
      raise ValidationError('Requests must have a different issuer and target.')
    if self.amount < 0:
      raise ValidationError('Requests must have a positive amount.')
    if not self.date:
      self.date = datetime.now()
