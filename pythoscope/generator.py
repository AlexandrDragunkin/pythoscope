import os
import re

from astvisitor import EmptyCode, descend, parse, ASTVisitor
from store import Class, Function, TestClass, TestMethod, ModuleNotFound, LiveObject
from util import camelize, underscore, sorted


def constructor_as_string(object):
    """For a given object return a string representing a code that will
    construct it.

    >>> constructor_as_string(123)
    '123'
    >>> constructor_as_string('string')
    "'string'"
    >>> obj = LiveObject(None, Class('SomeClass'), None)
    >>> constructor_as_string(obj)
    'SomeClass()'
    """
    if isinstance(object, LiveObject):
        # TODO: look for __init__ call and base the constructor on that.
        return "%s()" % object.klass.name
    return repr(object)

def call_as_string(object_name, input):
    """Generate code for calling an object with given input.

    >>> call_as_string('fun', {'a': 1, 'b': 2})
    'fun(a=1, b=2)'
    >>> call_as_string('capitalize', {'str': 'string'})
    "capitalize(str='string')"
    """
    return "%s(%s)" % (object_name, ', '.join(["%s=%s" % (arg, constructor_as_string(value)) for arg, value in input.iteritems()]))

def object2id(object):
    """Convert object to string that can be used as an identifier.
    """
    return re.sub(r'\.|\!', '', re.sub(r'\s+', '_', str(object).strip()))

def call2testname(object_name, input, output):
    """Generate a test method name that describes given object call.

    >>> call2testname('do_this', {}, True)
    'test_do_this_returns_true'
    >>> call2testname('square', {'x': 7}, 49)
    'test_square_returns_49_for_7'
    >>> call2testname('capitalize', {'str': 'a word.'}, 'A word.')
    'test_capitalize_returns_A_word_for_a_word'

    Two or more arguments are mentioned by name.
        >>> call2testname('ackermann', {'m': 3, 'n': 2}, 29)
        'test_ackermann_returns_29_for_m_equal_3_and_n_equal_2'

    Will sort arguments alphabetically.
        >>> call2testname('concat', {'s1': 'Hello ', 's2': 'world!'}, 'Hello world!')
        'test_concat_returns_Hello_world_for_s1_equal_Hello_and_s2_equal_world'

    Always starts and ends a word with a letter or number.
        >>> call2testname('strip', {'n': 1, 's': '  A bit of whitespace  '}, ' A bit of whitespace ')
        'test_strip_returns_A_bit_of_whitespace_for_n_equal_1_and_s_equal_A_bit_of_whitespace'
    """
    if input:
        if len(input) == 1:
            arguments = object2id(input.values()[0])
        else:
            arguments = "_and_".join(["%s_equal_%s" % (arg, object2id(value)) for arg, value in sorted(input.iteritems())])
        call_description = "%s_for_%s" % (object2id(output), arguments)
    else:
        call_description = str(output).lower()
    return "test_%s_returns_%s" % (underscore(object_name), call_description)

def sorted_test_method_descriptions(descriptions):
    return sorted(descriptions, key=lambda md: md.name)

def name2testname(name):
    if name[0].isupper():
        return "Test%s" % name
    return "test_%s" % name

def should_ignore_method(method):
    return method.name.startswith('_') and method.name != "__init__"

def method_descriptions_from_function(function):
    for call in function.get_unique_calls():
        name = call2testname(function.name, call.input, call.output)
        assertions = [(constructor_as_string(call.output),
                       call_as_string(function.name, call.input))]
        yield TestMethodDescription(name, assertions)

def method_description_from_live_object(live_object):
    if len(live_object.calls) == 1:
        call = live_object.calls[0]
        test_name = call2testname(call.method_name, call.input, call.output)
    else:
        # TODO: come up with a nicer name for methods with more than one call.
        test_name = "%s_%s" % (underscore(live_object.klass.name), live_object.id)

    # Before we call the method, we have to construct an object.
    local_name = underscore(live_object.klass.name)
    setup = "%s = %s\n" % (local_name, constructor_as_string(live_object))

    assertions = []
    for call in live_object.calls:
        name = "%s.%s" % (local_name, call.method_name)
        assertions.append((constructor_as_string(call.output),
                           call_as_string(name, call.input)))

    return TestMethodDescription(test_name, assertions, setup)

class UnknownTemplate(Exception):
    def __init__(self, template):
        Exception.__init__(self, "Couldn't find template %r." % template)
        self.template = template

def localize_method_code(code, method_name):
    """Return part of the code tree that corresponds to the given method
    definition.
    """
    class LocalizeMethodVisitor(ASTVisitor):
        def __init__(self):
            ASTVisitor.__init__(self)
            self.method_body = None
        def visit_function(self, name, args, body):
            if name == method_name:
                self.method_body = body

    return descend(code.children, LocalizeMethodVisitor).method_body

class TestMethodDescription(object):
    # Assertions should be a list of tuples in form (expected_value, actual_value).
    def __init__(self, name, assertions=[], setup=""):
        self.name = name
        self.assertions = assertions
        self.setup = setup

class TestGenerator(object):
    imports = []
    main_snippet = EmptyCode()

    def from_template(cls, template):
        if template == 'unittest':
            return UnittestTestGenerator()
        elif template == 'nose':
            return NoseTestGenerator()
        else:
            raise UnknownTemplate(template)
    from_template = classmethod(from_template)

    def ensure_import(self, import_):
        if import_ not in self.imports:
            self.imports.append(import_)

    def add_tests_to_project(self, project, modnames, force=False):
        for modname in modnames:
            module = project[modname]
            self._add_tests_for_module(module, project, force)

    def _add_tests_for_module(self, module, project, force):
        for test_case in self._generate_test_cases(module):
            project.add_test_case(test_case, force)

    def _generate_test_cases(self, module):
        for object in module.testable_objects:
            test_case = self._generate_test_case(object, module)
            if test_case:
                yield test_case

    def _generate_test_case(self, object, module):
        class_name = name2testname(camelize(object.name))
        method_descriptions = sorted_test_method_descriptions(self._generate_test_method_descriptions(object, module))

        # Don't generate empty test classes.
        if method_descriptions:
            test_body = self.create_test_class(class_name, method_descriptions)
            test_code = parse(test_body)
            def methoddesc2testmethod(method_description):
                name = method_description.name
                return TestMethod(name=name, code=localize_method_code(test_code, name))
            return TestClass(name=class_name,
                             code=test_code,
                             test_cases=map(methoddesc2testmethod, method_descriptions),
                             imports=self.imports,
                             main_snippet=self.main_snippet,
                             associated_modules=[module])

    def _generate_test_method_descriptions(self, object, module):
        if isinstance(object, Function):
            return self._generate_test_method_descriptions_for_function(object, module)
        elif isinstance(object, Class):
            return self._generate_test_method_descriptions_for_class(object, module)

    def _generate_test_method_descriptions_for_function(self, function, module):
        if function.calls:
            # We're calling the function, so we have to make sure it will
            # be imported in the test
            self.ensure_import((module.locator, function.name))

            # We have at least one call registered, so use it.
            return method_descriptions_from_function(function)
        else:
            # No calls were traced, so we're go for a single test stub.
            return [TestMethodDescription(name2testname(underscore(function.name)))]

    def _generate_test_method_descriptions_for_class(self, klass, module):
        if klass.live_objects:
            # We're calling the method, so we have to make sure its class
            # will be imported in the test
            self.ensure_import((module.locator, klass.name))

        for live_object in klass.live_objects.values():
            yield method_description_from_live_object(live_object)

        # No calls were traced for those methods, so we'll go for simple test stubs.
        for method in klass.get_untraced_methods():
            if not should_ignore_method(method):
                yield self._generate_test_method_description_for_method(method)

    def _generate_test_method_description_for_method(self, method):
        if method.name == '__init__':
            name = "object_initialization"
        else:
            name = method.name
        return TestMethodDescription(name2testname(name))

class UnittestTestGenerator(TestGenerator):
    main_snippet = parse("if __name__ == '__main__':\n    unittest.main()\n")

    def __init__(self):
        self.imports = ['unittest']

    def create_test_class(self, class_name, method_descriptions):
        result = "class %s(unittest.TestCase):\n" % class_name
        for method_description in method_descriptions:
            if method_description.assertions:
                result += "    def %s(self):\n" % method_description.name
                result += "        " + method_description.setup
                for assertion in method_description.assertions:
                    result += "        self.assertEqual(%s, %s)\n" % assertion
                result += "\n"
            else:
                result += "    def %s(self):\n" % method_description.name
                result += "        assert False # TODO: implement your test here\n\n"
        return result

class NoseTestGenerator(TestGenerator):
    def __init__(self):
        self.imports = []

    def create_test_class(self, class_name, method_descriptions):
        result = "class %s:\n" % class_name
        for method_description in method_descriptions:
            if method_description.assertions:
                result += "    def %s(self):\n" % method_description.name
                result += "        " + method_description.setup
                for assertion in method_description.assertions:
                    result += "        assert_equal(%s, %s)\n" % assertion
                result += "\n"
                self.ensure_import(('nose.tools', 'assert_equal'))
            else:
                result += "    def %s(self):\n" % method_description.name
                result += "        raise SkipTest # TODO: implement your test here\n\n"
                self.ensure_import(('nose', 'SkipTest'))
        return result

def add_tests_to_project(project, modnames, template, force=False):
    generator = TestGenerator.from_template(template)
    generator.add_tests_to_project(project, modnames, force)
