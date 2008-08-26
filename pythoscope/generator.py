import os
import re

from Cheetah import Template

from store import TestModule, ModuleNotFound
from util import camelize, write_string_to_file

class GenerationError(Exception):
    pass

def module2testpath(module):
    """Convert a module locator to a proper test filename.

    >>> module2testpath("module.py")
    'test_module.py'
    >>> module2testpath("pythoscope/store.py")
    'test_pythoscope_store.py'
    >>> module2testpath("pythoscope/__init__.py")
    'test_pythoscope.py'
    """
    return "test_" + re.sub(r'%s__init__.py$' % os.path.sep, '.py', module).\
        replace(os.path.sep, "_")

def save_test_module(test_module):
    # Don't save the test file unless it has at least one test case.
    if test_module.test_cases:
        write_string_to_file(test_module.get_content(), test_module.path)

class TestGenerator(object):
    def __init__(self, template, imports, main_snippet=""):
        self.template_path = os.path.join(os.path.dirname(__file__),
                                          "templates/%s.tpl" % template)
        self.imports = imports
        self.main_snippet = main_snippet

    def update_test_module(self, test_module):
        test_cases = self._generate_test_cases(test_module.application_module)
        test_module.add_test_cases(test_cases)
        test_module.ensure_imports(self.imports)
        test_module.ensure_main_snippet(self.main_snippet)
        save_test_module(test_module)

    def _generate_test_cases(self, module):
        mapping = {'module': module, 'camelize': camelize}
        return str(Template.Template(file=self.template_path,
                                     searchList=[mapping]))

template2generator = {
    'unittest': TestGenerator(template='unittest',
                              imports=['unittest'],
                              main_snippet="if __name__ == '__main__':\n    unittest.main()\n"),
    'nose':     TestGenerator(template='nose',
                              imports=[('nose', 'SkipTest')])
}

def generate_test_modules(project, modnames, destdir, template, force=False):
    if os.path.exists(destdir):
        if not os.path.isdir(destdir):
            raise GenerationError("Destination is not a directory.")
    else:
        os.makedirs(destdir)

    test_generator = template2generator[template]

    for modname in modnames:
        module = project[modname]
        test_path = os.path.join(destdir, module2testpath(module.path))
        try:
            test_module = project[test_path]
        except ModuleNotFound:
            test_module = TestModule(test_path, module)

        test_generator.update_test_module(test_module)
