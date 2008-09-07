import os
import re
import time

from fixture import TempIO
from nose.tools import assert_equal, assert_not_equal, assert_raises

from pythoscope.astvisitor import parse
from pythoscope.generator import add_tests_to_project, GenerationError
from pythoscope.store import Project, Module, Class, Method, Function, \
     ModuleNeedsAnalysis
from pythoscope.util import read_file_contents

from helper import assert_contains, assert_doesnt_contain, assert_length,\
     CustomSeparator, generate_single_test_module, ProjectInDirectory, \
     ProjectWithModules

# Let nose know that those aren't test functions/classes.
add_tests_to_project.__test__ = False

class TestGenerator:
    def test_generates_unittest_boilerplate(self):
        result = generate_single_test_module(objects=[Function('function')])
        assert_contains(result, "import unittest")
        assert_contains(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_generates_test_class_for_each_production_class(self):
        objects = [Class('SomeClass', [Method('some_method')]),
                   Class('AnotherClass', [Method('another_method')])]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "class TestSomeClass(unittest.TestCase):")
        assert_contains(result, "class TestAnotherClass(unittest.TestCase):")

    def test_generates_test_class_for_each_stand_alone_function(self):
        objects=[Function('some_function'), Function('another_function')]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "class TestSomeFunction(unittest.TestCase):")
        assert_contains(result, "class TestAnotherFunction(unittest.TestCase):")

    def test_generates_test_method_for_each_production_method_and_function(self):
        objects = [Class('SomeClass', [Method('some_method')]),
                   Class('AnotherClass', map(Method, ['another_method', 'one_more'])),
                   Function('a_function')]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "def test_some_method(self):")
        assert_contains(result, "def test_another_method(self):")
        assert_contains(result, "def test_one_more(self):")
        assert_contains(result, "def test_a_function(self):")

    def test_generates_nice_name_for_init_method(self):
        objects = [Class('SomeClass', [Method('__init__')])]
        result = generate_single_test_module(objects=objects)
        assert_contains(result, "def test_object_initialization(self):")

    def test_ignores_empty_classes(self):
        result = generate_single_test_module(objects=[Class('SomeClass', [])])
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_can_generate_nose_style_tests(self):
        objects = [Class('AClass', [Method('a_method')]), Function('a_function')]
        result = generate_single_test_module(template='nose', objects=objects)

        assert_doesnt_contain(result, "import unittest")
        assert_contains(result, "from nose import SkipTest")

        assert_contains(result, "class TestAClass:")
        assert_contains(result, "class TestAFunction:")

        assert_contains(result, "raise SkipTest")
        assert_doesnt_contain(result, "assert False")

        assert_doesnt_contain(result, "if __name__ == '__main__':\n    unittest.main()")

    def test_ignores_private_methods(self):
        objects = [Class('SomeClass', map(Method, ['_semiprivate', '__private', '__eq__']))]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestSomeClass(unittest.TestCase):")

    def test_ignores_private_functions(self):
        result = generate_single_test_module(objects=[Function('_function')])
        assert_doesnt_contain(result, "class")

    def test_ignores_exception_classes(self):
        objects = [Class('ExceptionClass', [Method('method')], bases=['Exception'])]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestExceptionClass(unittest.TestCase):")

    def test_ignores_unittest_classes(self):
        objects = [Class('TestClass', [Method('test_method')], bases=['unittest.TestCase'])]
        result = generate_single_test_module(objects=objects)
        assert_doesnt_contain(result, "class TestTestClass(unittest.TestCase):")

    def test_generates_content_in_right_order(self):
        result = generate_single_test_module(objects=[Function('function')])

        assert re.match(r"import unittest.*?class TestFunction.*?if __name__ == '__main__'", result, re.DOTALL)

    def test_ignores_test_modules(self):
        result = generate_single_test_module()
        assert_equal("", result)

    def test_doesnt_generate_test_files_with_no_test_cases(self):
        project = ProjectWithModules(["module.py"], ProjectInDirectory)
        test_file = os.path.join(project.path, "test_module.py")

        add_tests_to_project(project, ["module"], project.path, 'unittest')

        assert not os.path.exists(test_file)

    def test_doesnt_overwrite_existing_files_which_werent_analyzed(self):
        TEST_CONTENTS = "# test"
        project = ProjectWithModules(["module.py"], ProjectInDirectory)
        project["module"].objects = [Function("function")]
        # File exists, but project does NOT contain corresponding test module.
        existing_file = project.path.putfile("test_module.py", TEST_CONTENTS)

        def add_and_save():
            add_tests_to_project(project, ["module"], project.path, 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

    def test_creates_new_test_module_if_no_of_the_existing_match(self):
        project = ProjectWithModules(["module.py", "test_other.py"])
        project["module"].objects = [Function("function")]

        add_tests_to_project(project, ["module"], project.path, 'unittest')

        project_test_cases = list(project.test_cases_iter())
        assert_length(project_test_cases, 1)
        assert_length(project["test_other"].test_cases, 0)

class TestGeneratorWithSingleModule:
    def setUp(self):
        self.project = ProjectWithModules(["module.py", "test_module.py"])
        self.project["module"].objects = [Function("function")]

    def test_adds_imports_to_existing_test_files_only_if_they_arent_present(self):
        imports = ["unittest", ("nose", "SkipTest")]
        for imp in imports:
            self.project["test_module"].imports = [imp]

            add_tests_to_project(self.project, ["module"], self.project.path, 'unittest')

            assert_equal([imp], self.project["test_module"].imports)

    def test_appends_new_test_classes_to_existing_test_files(self):
        TEST_CONTENTS = "class TestSomething: pass\n\n"
        self.project["test_module"].code = parse(TEST_CONTENTS)

        add_tests_to_project(self.project, ["module"], self.project.path, 'unittest')

        assert_contains(self.project["test_module"].get_content(), TEST_CONTENTS)
        assert_contains(self.project["test_module"].get_content(), "class TestFunction(unittest.TestCase):")

    def test_associates_test_cases_with_application_modules(self):
        add_tests_to_project(self.project, ["module"], self.project.path, 'unittest')

        project_test_cases = list(self.project.test_cases_iter())
        assert_length(project_test_cases, 1)
        assert_equal(project_test_cases[0].associated_modules, [self.project["module"]])

    def test_chooses_the_right_existing_test_module_for_new_test_case(self):
        self.project.create_module("test_other.py")

        add_tests_to_project(self.project, ["module"], self.project.path, 'unittest')

        assert_length(self.project["test_module"].test_cases, 1)
        assert_length(self.project["test_other"].test_cases, 0)

    def test_doesnt_overwrite_existing_files_which_were_modified_since_last_analysis(self):
        TEST_CONTENTS = "# test"
        project = ProjectWithModules(["module.py", "test_module.py"], ProjectInDirectory)
        project["module"].objects = [Function("function")]
        # File exists, and project contains corresponding, but outdated, test module.
        existing_file = project.path.putfile("test_module.py", TEST_CONTENTS)
        project["test_module"].created = time.time() - 3600

        def add_and_save():
            add_tests_to_project(project, ["module"], project.path, 'unittest')
            project.save()

        assert_raises(ModuleNeedsAnalysis, add_and_save)
        assert_equal(TEST_CONTENTS, read_file_contents(existing_file))

class TestGeneratorWithProjectInDirectory:
    def setUp(self):
        self.project = ProjectInDirectory()

    def test_uses_existing_destination_directory(self):
        add_tests_to_project(self.project, [], self.project.path, 'unittest')
        # Simply make sure it doesn't raise any exceptions.

    def test_raises_an_exception_if_destdir_is_a_file(self):
        destfile = self.project.path.putfile("file", "its content")
        assert_raises(GenerationError,
                      lambda: add_tests_to_project(self.project, [], destfile, 'unittest'))
