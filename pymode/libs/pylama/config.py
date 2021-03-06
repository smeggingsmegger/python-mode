""" Parse arguments from command line and configuration files. """
import fnmatch
import sys
from os import getcwd, path
from re import compile as re

import logging
from argparse import ArgumentParser

from . import __version__
from .libs.inirama import Namespace
from .lint.extensions import LINTERS


# Setup a logger
LOGGER = logging.getLogger('pylama')
LOGGER.propagate = False
STREAM = logging.StreamHandler(sys.stdout)
LOGGER.addHandler(STREAM)

#: A default checkers
DEFAULT_LINTERS = 'pep8', 'pyflakes', 'mccabe'

CURDIR = getcwd()
DEFAULT_INI_PATH = path.join(CURDIR, 'pylama.ini')


class _Default(object):

    def __init__(self, value=None):
        self.value = value

    def __str__(self):
        return str(self.value)

    __repr__ = lambda s: "<_Default [%s]>" % s.value


def split_csp_str(s):
    """ Split commaseparated string.

    :returns: list of splitted values

    """
    if isinstance(s, (list, tuple)):
        return s
    return list(set(i for i in s.strip().split(',') if i))


def parse_linters(linters):
    """ Initialize choosen linters.

    :returns: list of inited linters

    """
    result = list()
    for name in split_csp_str(linters):
        linter = LINTERS.get(name)
        if linter:
            result.append((name, linter))
        else:
            logging.warn("Linter `%s` not found.", name)
    return result


PARSER = ArgumentParser(description="Code audit tool for python.")
PARSER.add_argument(
    "path", nargs='?', default=_Default(CURDIR),
    help="Path on file or directory.")

PARSER.add_argument(
    "--verbose", "-v", action='store_true', help="Verbose mode.")

PARSER.add_argument('--version', action='version',
                    version='%(prog)s ' + __version__)

PARSER.add_argument(
    "--format", "-f", default=_Default('pep8'), choices=['pep8', 'pylint'],
    help="Error format.")

PARSER.add_argument(
    "--select", "-s", default=_Default(''), type=split_csp_str,
    help="Select errors and warnings. (comma-separated)")


PARSER.add_argument(
    "--linters", "-l", default=_Default(','.join(DEFAULT_LINTERS)),
    type=parse_linters, help=(
        "Select linters. (comma-separated). Choices are %s."
        % ','.join(s for s in LINTERS.keys())
    ))

PARSER.add_argument(
    "--ignore", "-i", default=_Default(''), type=split_csp_str,
    help="Ignore errors and warnings. (comma-separated)")

PARSER.add_argument(
    "--skip", default=_Default(''),
    type=lambda s: [re(fnmatch.translate(p)) for p in s.split(',') if p],
    help="Skip files by masks (comma-separated, Ex. */messages.py)")

PARSER.add_argument("--report", "-r", help="Filename for report.")
PARSER.add_argument(
    "--hook", action="store_true", help="Install Git (Mercurial) hook.")

PARSER.add_argument(
    "--async", action="store_true",
    help="Enable async mode. Usefull for checking a lot of files. "
    "Dont supported with pylint.")

PARSER.add_argument(
    "--options", "-o", default=_Default(DEFAULT_INI_PATH),
    help="Select configuration file. By default is '<CURDIR>/pylama.ini'")


ACTIONS = dict((a.dest, a) for a in PARSER._actions)


def parse_options(args=None, config=True, **overrides): # noqa
    """ Parse options from command line and configuration files.

    :return argparse.Namespace:

    """
    if args is None:
        args = []

    # Parse args from command string
    options = PARSER.parse_args(args)
    options.file_params = dict()
    options.linter_params = dict()

    # Override options
    for k, v in overrides.items():
        passed_value = getattr(options, k, _Default())
        if isinstance(passed_value, _Default):
            setattr(options, k, _Default(v))

    # Compile options from ini
    if config:
        cfg = get_config(str(options.options))
        for k, v in cfg.default.items():
            LOGGER.info('Find option %s (%s)', k, v)
            passed_value = getattr(options, k, _Default())
            if isinstance(passed_value, _Default):
                setattr(options, k, _Default(v))

        # Parse file related options
        for k, s in cfg.sections.items():
            if k == cfg.default_section:
                continue
            if k in LINTERS:
                options.linter_params[k] = dict(s)
                continue
            mask = re(fnmatch.translate(k))
            options.file_params[mask] = dict(s)
            options.file_params[mask]['lint'] = int(
                options.file_params[mask].get('lint', 1)
            )

    # Postprocess options
    opts = dict(options.__dict__.items())
    for name, value in opts.items():
        if isinstance(value, _Default):
            setattr(options, name, process_value(name, value.value))

    return options


def process_value(name, value):
    """ Compile option value. """
    action = ACTIONS.get(name)
    if not action:
        return value

    if callable(action.type):
        return action.type(value)

    if action.const:
        return bool(int(value))

    return value


def get_config(ini_path=DEFAULT_INI_PATH):
    """ Load configuration from INI.

    :return Namespace:

    """
    config = Namespace()
    config.default_section = 'main'
    config.read(ini_path)

    return config


def setup_logger(options):
    """ Setup logger with options. """
    LOGGER.setLevel(logging.INFO if options.verbose else logging.WARN)
    if options.report:
        LOGGER.removeHandler(STREAM)
        LOGGER.addHandler(logging.FileHandler(options.report, mode='w'))
    LOGGER.info('Try to read configuration from: ' + options.options)
