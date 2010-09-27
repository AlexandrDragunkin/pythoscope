from pythoscope.compat import all, set, sorted
from pythoscope.generator.code_string import CodeString, combine
from pythoscope.generator.constructor import constructor_as_string, call_as_string_for
from pythoscope.generator.setup_optimizer import optimize
from pythoscope.serializer import BuiltinException, CompositeObject,\
    ImmutableObject, MapObject, UnknownObject, SequenceObject, SerializedObject
from pythoscope.side_effect import BuiltinMethodWithPositionArgsSideEffect, SideEffect
from pythoscope.store import Call, FunctionCall, UserObject, MethodCall,\
    GeneratorObject, GeneratorObjectInvocation
from pythoscope.util import counted, flatten, key_for_value


# :: SerializedObject | [SerializedObject] -> bool
def can_be_constructed(obj):
    if isinstance(obj, list):
        return all(map(can_be_constructed, obj))
    elif isinstance(obj, SequenceObject):
        return all(map(can_be_constructed, obj.contained_objects))
    elif isinstance(obj, GeneratorObject):
        return obj.is_activated()
    return not isinstance(obj, UnknownObject)

# :: Call -> Call
def top_caller(call):
    if call.caller is None:
        return call
    return top_caller(call.caller)

# :: ([Event], int) -> [Event]
def older_than(events, reference_timestamp):
    return filter(lambda e: e.timestamp < reference_timestamp, events)

# :: (Call, int) -> [Call]
def subcalls_before_timestamp(call, reference_timestamp):
    for c in older_than(call.subcalls, reference_timestamp):
        yield c
        for sc in subcalls_before_timestamp(c, reference_timestamp):
            yield sc

# :: Call -> [Call]
def calls_before(call):
    """Go up the call graph and return all calls that happened before
    the given one.

    >>> class Call(object):
    ...     def __init__(self, caller, timestamp):
    ...         self.subcalls = []
    ...         self.caller = caller
    ...         self.timestamp = timestamp
    ...         if caller:
    ...             caller.subcalls.append(self)
    >>> top = Call(None, 1)
    >>> branch1 = Call(top, 2)
    >>> leaf1 = Call(branch1, 3)
    >>> branch2 = Call(top, 4)
    >>> leaf2 = Call(branch2, 5)
    >>> leaf3 = Call(branch2, 6)
    >>> leaf4 = Call(branch2, 7)
    >>> branch3 = Call(top, 8)
    >>> calls_before(branch3) == [top, branch1, leaf1, branch2, leaf2, leaf3, leaf4]
    True
    >>> calls_before(leaf3) == [top, branch1, leaf1, branch2, leaf2]
    True
    >>> calls_before(branch2) == [top, branch1, leaf1]
    True
    >>> calls_before(branch1) == [top]
    True
    """
    top = top_caller(call)
    return [top] + list(subcalls_before_timestamp(top, call.timestamp))

# :: [Call] -> [SideEffect]
def side_effects_of(calls):
    return flatten(map(lambda c: c.side_effects, calls))

# :: Call -> [SideEffect]
def side_effects_before(call):
    return older_than(side_effects_of(calls_before(call)), call.timestamp)

# :: SerializedObject | Call | [SerializedObject] | [Call] -> [SerializedObject]
def get_contained_objects(obj):
    """Return a list of SerializedObjects this object requires during testing.

    This function will descend recursively if objects contained within given
    object are composite themselves.
    """
    if isinstance(obj, list):
        return flatten(map(get_contained_objects, obj))
    elif isinstance(obj, ImmutableObject):
        # ImmutableObjects are self-sufficient.
        return []
    elif isinstance(obj, UnknownObject):
        return []
    elif isinstance(obj, SequenceObject):
        return get_those_and_contained_objects(obj.contained_objects)
    elif isinstance(obj, MapObject):
        return get_those_and_contained_objects(flatten(obj.mapping))
    elif isinstance(obj, BuiltinException):
        return get_those_and_contained_objects(obj.args)
    elif isinstance(obj, UserObject):
        return get_contained_objects(obj.get_init_and_external_calls())
    elif isinstance(obj, (FunctionCall, MethodCall, GeneratorObjectInvocation)):
        if obj.raised_exception():
            output = obj.exception
        else:
            output = obj.output
        return get_those_and_contained_objects(obj.input.values() + [output])
    elif isinstance(obj, GeneratorObject):
        if obj.is_activated():
            return get_those_and_contained_objects(obj.args.values()) +\
                get_contained_objects(obj.calls)
        else:
            return []
    else:
        raise TypeError("Wrong argument to get_contained_objects: %r." % obj)

# :: [SerializedObject] -> [SerializedObject]
def get_those_and_contained_objects(objs):
    """Return a list containing given objects and all objects contained within
    them.
    """
    return objs + get_contained_objects(objs)

# :: [SerializedObject|Call] -> [SerializedObject|Call]
def sorted_by_timestamp(objects):
    return sorted(objects, key=lambda o: o.timestamp)

# :: [SideEffect] -> [SerializedObject]
def objects_referenced_by_side_effects(side_effects):
    return flatten(map(lambda se: se.referenced_objects, side_effects))

# :: [SideEffect] -> [SerializedObject]
def objects_affected_by_side_effects(side_effects):
    return flatten(map(lambda se: se.affected_objects, side_effects))

# :: ([SideEffect], set([SerializedObject])) -> [SideEffect]
def side_effects_that_affect_objects(side_effects, objects):
    "Filter out side effects that are irrelevant to given set of objects."
    for side_effect in side_effects:
        for obj in side_effect.affected_objects:
            if obj in objects:
                yield side_effect

class Dependencies(object):
    def __init__(self, call):
        self.all = []

    def _calculate(self, objects, relevant_side_effects):
        """
        First, we look at all objects required for the call's input/output
        (pre- and post- call dependencies each do one of those). Next, we look
        at all side effects that affected those objects before the call. Those
        side effects can reference more objects, which in turn can be affected
        by more side effects, so we do this back and forth until we have
        a complete set of objects and side effects that have direct or indirect
        relationship to the call.
        """
        all_objects = []
        all_side_effects = set()
        def update(objects):
            all_objects.extend(objects)

            # We have some objects, let's see how many side effects affect them.
            new_side_effects = set(side_effects_that_affect_objects(relevant_side_effects, objects))
            previous_side_effects_count = len(all_side_effects)
            all_side_effects.update(new_side_effects)
            if len(all_side_effects) == previous_side_effects_count:
                return

            # Similarly, new side effects may yield some new objects, let's recur.
            update(get_those_and_contained_objects(objects_referenced_by_side_effects(new_side_effects)))
        # We start with objects required for the call itself.
        update(objects)

        # Finally assemble the whole timeline of dependencies.
        # Since data we have was gathered during real execution there is no way setup
        # dependencies are cyclic, i.e. there is a strict order of object creation.
        # We've chosen to sort objects by their creation timestamp.
        self.all = sorted_by_timestamp(set(all_objects).union(all_side_effects))

        self._remove_objects_unworthy_of_naming(dict(counted(all_objects)))

        optimize(self)

    def _remove_objects_unworthy_of_naming(self, objects_usage_counts):
        affected_objects = objects_affected_by_side_effects(self.get_side_effects())
        for obj, usage_count in objects_usage_counts.iteritems():
            # ImmutableObjects don't need to be named, as their identity is
            # always unambiguous.
            if not isinstance(obj, ImmutableObject):
                # Anything mentioned more than once have to be named.
                if usage_count > 1:
                    continue
                # Anything affected by side effects is also worth naming.
                if obj in affected_objects:
                    continue
            self.all.remove(obj)

    def get_side_effects(self):
        return filter(lambda x: isinstance(x, SideEffect), self.all)

    def get_objects(self):
        return filter(lambda x: isinstance(x, SerializedObject), self.all)

    def replace_pair_with_event(self, event1, event2, new_event):
        """Replaces pair of events with a single event. The second event
        must be a SideEffect.

        Optimizer only works on values with names, which means we don't really
        have to traverse the whole Project tree and replace all occurences
        of an object. It is sufficient to replace it on the dependencies
        timeline, which will be used as a base for naming objects and their
        later usage.
        """
        if not isinstance(event2, SideEffect):
            raise TypeError("Second argument to replace_pair_with_object has to be a SideEffect, was %r instead." % event2)
        new_event.timestamp = event1.timestamp
        self.all[self.all.index(event1)] = new_event
        if isinstance(event1, SerializedObject):
            if not isinstance(new_event, SerializedObject):
                raise TypeError("Expected new_event to be of the same type as event1 in a call to replace_pair_with_object, got %r instead." % new_event)
        self.all.remove(event2)

class PreCallDependencies(Dependencies):
    """Dependencies for making a call.
    """
    def __init__(self, call):
        super(PreCallDependencies, self).__init__(call)
        self._calculate(get_contained_objects(call), side_effects_before(call))

class CallOutputDependencies(Dependencies):
    """Dependencies regarding call's output value.
    """
    def __init__(self, call):
        super(CallOutputDependencies, self).__init__(call)
        self._calculate(get_those_and_contained_objects([call.output]), call.side_effects)

# :: SerializedObject -> str
def get_name_base_for_object(obj):
    common_names = {'list': 'alist',
                    'dict': 'adict',
                    'array.array': 'array',
                    'types.FunctionType': 'function',
                    'types.GeneratorType': 'generator'}
    return common_names.get(obj.type_name, 'obj')

# :: [str], str -> str
def get_next_name(names, base):
    """Figure out a new name starting with base that doesn't appear in given
    list of names.

    >>> get_next_name(["alist", "adict1", "adict2"], "adict")
    'adict3'
    """
    base_length = len(base)
    def has_right_base(name):
        return name.startswith(base)
    def get_index(name):
        return int(name[base_length:])
    return base + str(max(map(get_index, filter(has_right_base, names))) + 1)

# :: SerializedObject, {SerializedObject: str} -> None
def assign_name_to_object(obj, assigned_names):
    """Assign a right name for given object.

    May reassign an existing name for an object as a side effect.
    """
    if assigned_names.has_key(obj):
        return
    base = get_name_base_for_object(obj)
    other_obj = key_for_value(assigned_names, base)

    if other_obj:
        # Avoid overlapping names by numbering objects with the same base.
        assigned_names[other_obj] = base+"1"
        assigned_names[obj] = base+"2"
    elif base+"1" in assigned_names.values():
        # We have some objects already numbered, insert a name with a new index.
        assigned_names[obj] = get_next_name(assigned_names.values(), base)
    else:
        # It's the first object with that base.
        assigned_names[obj] = base

# :: ([SerializedObject], {SerializedObject: str}) -> None
def assign_names_to_objects(objects, names):
    """Modifies names dictionary as a side effect.
    """
    for obj in sorted_by_timestamp(objects):
        assign_name_to_object(obj, names)

# :: (SerializedObject, str, {SerializedObject: str}) -> CodeString
def setup_for_named_object(obj, name, already_assigned_names):
    constructor = constructor_as_string(obj, already_assigned_names)
    setup = combine(name, constructor, "%s = %s\n")
    if constructor.uncomplete:
        setup = combine("# ", setup)
    return setup

# :: CodeString -> CodeString
def add_newline(code_string):
    return combine(code_string, "\n")

# :: (SideEffect, {SerializedObject: str}) -> CodeString
def setup_for_side_effect(side_effect, already_assigned_names):
    object_name = already_assigned_names[side_effect.obj]
    if isinstance(side_effect, BuiltinMethodWithPositionArgsSideEffect):
        return add_newline(call_as_string_for("%s.%s" % (object_name, side_effect.definition.name),
                                              side_effect.args_mapping(),
                                              side_effect.definition,
                                              already_assigned_names))
    else:
        raise TypeError("Unknown side effect type: %r" % side_effect)

# :: (Dependencies, {SerializedObject: str}) -> CodeString
def create_setup_for_dependencies(dependencies, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    already_assigned_names = names.copy()
    assign_names_to_objects(dependencies.get_objects(), names)
    full_setup = CodeString("")
    for dependency in dependencies.all:
        if isinstance(dependency, SerializedObject):
            name = names[dependency]
            setup = setup_for_named_object(dependency, name, already_assigned_names)
            already_assigned_names[dependency] = name
        else:
            setup = setup_for_side_effect(dependency, already_assigned_names)
        full_setup = combine(full_setup, setup)
    return full_setup

# :: (Call, {SerializedObject : str}) -> CodeString
def assign_names_and_setup(call, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    if not isinstance(call, Call):
        raise TypeError("Tried to call assign_names_and_setup with %r instead of a call." % call)
    pre_setup = create_setup_for_input(call, names)
    post_setup = create_setup_for_output(call, names)
    return combine(pre_setup, post_setup)

# :: ([Call], {SerializedObject : str}) -> CodeString
def assign_names_and_setup_for_multiple_calls(calls, names):
    """Returns a setup code string. Modifies names dictionary as a side effect.
    """
    full_setup = CodeString("")
    for call in sorted_by_timestamp(calls):
        setup = assign_names_and_setup(call, names)
        full_setup = combine(full_setup, setup)
    return full_setup

# :: (Call, {SerializedObject : str}) -> CodeString
def create_setup_for_input(call, names):
    pre_dependencies = PreCallDependencies(call)
    return create_setup_for_dependencies(pre_dependencies, names)

# :: (Call, {SerializedObject : str}) -> CodeString|str
def create_setup_for_output(call, names):
    """Sometimes the call's output doesn't depend on the input at all. If the
    object has been altered by the call we need to create and name a new copy of
    it to prepare a good equality assertion.
    """
    if call.output is not None and \
            can_be_constructed(call.output) and \
            call.output not in names.keys():
        post_dependencies = CallOutputDependencies(call)
        return create_setup_for_dependencies(post_dependencies, names)
    return ""
