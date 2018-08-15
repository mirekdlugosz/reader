import os.path
import os
import logging

import click

from . import Reader


APP_NAME = 'reader'
DB_ENVVAR = '{}_DB'.format(APP_NAME.upper())


def get_default_db_path(create_dir=False):
    app_dir = click.get_app_dir(APP_NAME)
    db_path = os.path.join(app_dir, 'db.sqlite')
    if create_dir:
        os.makedirs(app_dir, exist_ok=True)
    return db_path


def abort(message, *args, **kwargs):
    raise click.ClickException(message.format(*args, **kwargs))


def setup_logging(verbose):
    if verbose == 0:
        level = logging.WARNING
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.getLogger('reader').setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)-7s %(message)s', '%Y-%m-%dT%H:%M:%S')
    handler.setFormatter(formatter)
    logging.getLogger('reader').addHandler(handler)


@click.group()
@click.option('--db', type=click.Path(dir_okay=False), envvar=DB_ENVVAR)
@click.pass_context
def cli(ctx, db):
    if db is None:
        try:
            db = get_default_db_path(create_dir=True)
        except Exception as e:
            abort("{}", e)
    ctx.obj = db


@cli.command()
@click.argument('url')
@click.option('--update/--no-update')
@click.option('-v', '--verbose', count=True)
@click.pass_obj
def add(db_path, url, update, verbose):
    setup_logging(verbose)
    try:
        reader = Reader(db_path)
    except Exception as e:
        abort("{}: {}", db_path, e)
    reader.add_feed(url)
    if update:
        reader.update_feed(url)


@cli.command()
@click.argument('url')
@click.option('-v', '--verbose', count=True)
@click.pass_obj
def remove(db_path, url, verbose):
    setup_logging(verbose)
    try:
        reader = Reader(db_path)
    except Exception as e:
        abort("{}: {}", db_path, e)
    reader.remove_feed(url)


@cli.command()
@click.argument('url', required=False)
@click.option('--new-only/--no-new-only')
@click.option('-v', '--verbose', count=True)
@click.pass_obj
def update(db_path, url, new_only, verbose):
    setup_logging(verbose)
    try:
        reader = Reader(db_path)
    except Exception as e:
        abort("{}: {}", db_path, e)
    if url:
        reader.update_feed(url)
    else:
        reader.update_feeds(new_only=new_only)


@cli.group()
def list():
    pass


@list.command()
@click.pass_obj
def feeds(db_path):
    for feed in Reader(db_path).get_feeds():
        click.echo(feed.url)


from reader.app.cli import serve
cli.add_command(serve)


if __name__ == '__main__':
    cli()