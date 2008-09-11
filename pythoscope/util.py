import os
import re

# Portability code.
try:
    set = set
except NameError:
    from sets import Set as set

try:
    sorted = sorted
except NameError:
    def sorted(alist):
        alist = alist[:]
        alist.sort()
        return alist

def camelize(name):
    """Covert name into CamelCase.

    >>> camelize('underscore_name')
    'UnderscoreName'
    >>> camelize('AlreadyCamelCase')
    'AlreadyCamelCase'
    >>> camelize('')
    ''
    """
    def upcase(match):
        return match.group(1).upper()
    return re.sub(r'(?:^|_)(.)', upcase, name)


def underscore(name):
    """Convert name into underscore_name.

    >>> underscore('CamelCase')
    'camel_case'
    >>> underscore('already_underscore_name')
    'already_underscore_name'
    >>> underscore('BigHTMLClass')
    'big_html_class'
    >>> underscore('')
    ''
    """
    if name and name[0].isupper():
        name = name[0].lower() + name[1:]

    def capitalize(match):
        string = match.group(1).capitalize()
        return string[:-1] + string[-1].upper()

    def underscore(match):
        return '_' + match.group(1).lower()

    name = re.sub(r'([A-Z]+)', capitalize, name)
    return re.sub(r'([A-Z])', underscore, name)

def read_file_contents(filename):
    fd = file(filename)
    contents = fd.read()
    fd.close()
    return contents

def write_string_to_file(string, filename):
    fd = file(filename, 'w')
    fd.write(string)
    fd.close()

def all_of_type(objects, type):
    """Return all objects that are instances of a given type.
    """
    return [o for o in objects if isinstance(o, type)]

def max_by_not_zero(func, collection):
    """Return the element of a collection for which func returns the highest
    value, greater than 0.

    Return None if there is no such value.

    >>> max_by_not_zero(len, ["abc", "d", "ef"])
    'abc'
    >>> max_by_not_zero(lambda x: x, [0, 0, 0, 0]) is None
    True
    >>> max_by_not_zero(None, []) is None
    True
    """
    if not collection:
        return None

    def annotate(element):
        return (func(element), element)

    highest = max(map(annotate, collection))
    if highest and highest[0] > 0:
        return highest[1]
    else:
        return None

def python_modules_below(path):
    def is_python_module(path):
        return path.endswith(".py")
    return filter(is_python_module, rlistdir(path))

def rlistdir(path):
    """Resursive directory listing. Yield all files below given path,
    ignoring those which names begin with a dot.
    """
    if os.path.basename(path).startswith('.'):
        return

    if os.path.isdir(path):
        for entry in os.listdir(path):
            for subpath in rlistdir(os.path.join(path, entry)):
                yield subpath
    else:
        yield path

def get_names(objects):
    return map(lambda c: c.name, objects)

class DirectoryException(Exception):
    pass

def ensure_directory(directory):
    """Make sure given directory exists, creating it if necessary.
    """
    if os.path.exists(directory):
        if not os.path.isdir(directory):
            raise DirectoryException("Destination is not a directory.")
    else:
        os.makedirs(directory)

def get_last_modification_time(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        # File may not exist, in which case it was never modified.
        return 0

def extract_subpath(path, prefix):
    """Remove prefix from given path to generate subpath, so the following
    correspondence is preserved:

      path <=> os.path.join(prefix, subpath)

    in terms of physical path (i.e. not necessarily strict string
    equality).
    """
    prefix_length = len(prefix)
    if not prefix.endswith(os.path.sep):
        prefix_length += 1
    return os.path.realpath(path)[prefix_length:]
