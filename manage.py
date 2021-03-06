
import click
import db from './db'
import {app} from './main'


@click.group()
def main():
  pass


@main.command()
@click.option('--users', is_flag=True, help='Also drop users.')
def drop(users):
  " Drop all database information. "

  if users:
    print('Dropping User ...')
    db.User.drop_collection()

  print('Dropping GatewayTransactionDetails ...')
  db.GatewayTransactionDetails.drop_collection()

  print('Dropping Transaction ...')
  db.Transaction.drop_collection()

  print('Dropping Request ...')
  db.Request.drop_collection()


@main.command('format-command-list')
def format_command_list():
  for cmd in app.commands.values():
    line = cmd.name + ' - ' + cmd.help
    print(line)


if require.main == module:
  main()
