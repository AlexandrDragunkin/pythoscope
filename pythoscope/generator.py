import os

from Cheetah import Template

from util import camelize, write_string_to_file

def module2testpath(module):
    """Convert a module locator to a proper test filename.

    >>> module2testpath("module.py")
    'test_module.py'
    >>> module2testpath("pythoscope/store.py")
    'test_pythoscope_store.py'
    """
    return "test_" + module.replace("/", "_")

def template_path(name):
    "Return a path to the given template."
    return os.path.join(os.path.dirname(__file__), "templates/%s.tpl" % name)

def generate_test_module(module, template="unittest"):
    mapping = {'module': module, 'camelize': camelize}
    return str(Template.Template(file=template_path(template),
                                 searchList=[mapping]))

def generate_test_modules(project, modnames, destdir):
    os.makedirs(destdir)
    for modname in modnames:
        module = project[modname]
        test_module = generate_test_module(module)
        test_path = os.path.join(destdir, module2testpath(module.path))
        write_string_to_file(test_module, test_path)
