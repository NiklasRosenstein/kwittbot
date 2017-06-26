<img src="http://i.imgur.com/HFdsUh7.png" align="right" width="128px">

# @KwittBot

KwittBot is a Telegram bot that allows you to send and receive money from
friends.

## Deployment

  [Node.py]: https://nodepy.org/

* Install [Node.py]: `>_ pip3 install node.py`
* Install dependencies: `>_ nppm install`
* Create a configuration file: `>_ cp config.json.example config.json`
* Update the configuration file with MongoDB credentials and the Telegram Token
* Run: `>_ nodepy .`

## Development Status

* Proof of concept: No real money transactions, yet
* [ ] MongoDB and MongoEngine will likely be replaced by another database
  (Postgres, Cassandra) and ORM library (SQLAlchemy)
* [ ] Awareness of currency
* [ ] Ability to accept or deny requests for money via InlineKeyboard or command
* [ ] Command to list outstanding requests and to accept, deny or withdraw them

## Example

![](https://i.imgur.com/TPWIiUC.png)
