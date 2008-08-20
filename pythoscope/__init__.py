import getopt
import os
import sys

from collector import collect_information_from_paths
from generator import generate_test_modules
from store import Project

PROJECT_FILE = ".pythoscope"

def collect(appname, args):
    project = Project(modules=collect_information_from_paths(args))
    project.save_to_file(PROJECT_FILE)

GENERATE_USAGE = """Pythoscope generator usage:

    %s generate [options] [module names...]

This command will generate test suites for the listed modules.
As a module name, you can use both direct path or locator in dot-style
notation. For example, both of the following are acceptable:

  package/sub/module.py
  package.sub.module

All test files will be written to a single directory.

Options:
  -d PATH, --destdir=PATH    Destination directory for generated test
                             files. Default is "pythoscope-tests/".
  -h, --help                 Show this help message and exit.
  -t TEMPLATE_NAME, --template=TEMPLATE_NAME
                             Name of a template to use (see below for
                             a list of available templates). Default
                             is "unittest".

Available templates:
  * unittest     All tests are placed into classes which derive
                 from unittest.TestCase. Each test module ends with
                 an import-safe call to unittest.main().
  * nose         Nose-style tests, which don't import unittest and use
                 SkipTest as a default test body.
"""

def generate(appname, args):
    try:
        options, args = getopt.getopt(sys.argv[2:], "d:ht:", ["destdir=", "help", "template="])
    except getopt.GetoptError, err:
        print "Error:", err, "\n"
        print GENERATE_USAGE % appname
        sys.exit(1)

    template = "unittest"
    destdir = "pythoscope-tests"

    for opt, value in options:
        if opt in ("-d", "--destdir"):
            destdir = value
        elif opt in ("-h", "--help"):
            print GENERATE_USAGE % appname
            sys.exit()
        elif opt in ("-t", "--template"):
            template = value

    project = Project(filepath=PROJECT_FILE)
    generate_test_modules(project, args, destdir, template)

def main():
    appname, mode, args = os.path.basename(sys.argv[0]), sys.argv[1], sys.argv[2:]

    if mode == 'collect':
        collect(appname, args)
    elif mode == 'generate':
        generate(appname, args)
