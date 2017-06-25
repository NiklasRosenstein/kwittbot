
import click
import db from './db'


@click.group()
def main():
  pass


@main.command()
def drop():
  " Drop all database information. "

  db.User.drop_collection()
  db.GatewayTransactionDetails.drop_collection()
  db.Transaction.drop_collection()
  print("All data dropped.")


if require.main == module:
  main()
