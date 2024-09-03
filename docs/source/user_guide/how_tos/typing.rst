==================
Typing and UPSTAGE
==================
.. include:: ../../class_refs.txt

UPSTAGE runs type checking using ``mypy``, which can be installed with the ``lint`` directive (see CONTRIBUTING.md for more).

It is recommended to type your simulations to ensure stable running and reduce the chances for bugs. The difficulty with
typing is that often there are circular imports or other issues when making simulations. The following advice will help with
creating good typing for your simulations.

-------------
Typing States
-------------

The primary types to care about are the types of a |State|. While the state definition includes a ``valid_types`` entry, that entry
doesn't provide information to static type checkers or to your IDE. |State| objects are ``Generic``, and can have their types defined
in the following way:

.. code-block:: python

    class Gardener(UP.Actor):
        skill_level: UP.State[int](default=0, valid_types=int)
        time_in_sun: UP.LinearChangingState[float](default=0.0, recording=True)

Later, your IDE will know that any ``Gardener`` instance's ``skill_level`` attribute is an integer type.

.. note::

    It is a future feature to remove the ``valid_types`` input and just use the type hinting to check.

These states already have an assigned type, or have a limited scope of types:

1. :py:class:`~upstage.states.DetectabilityState`: This state is a boolean
2. :py:class:`~upstage.states.CartesianLocationChangingState`: The output is of type ``CartesianLocation``
3. :py:class:`~upstage.states.GeodeticLocationChangingState`: The output is of type ``GeodeticLocation``
4. :py:class:`~upstage.states.ResourceState`: The type must be a ``simpy.Store`` or ``simpy.Container`` (or a subclass). You can still define the type.
5. :py:class:`~upstage.states.CommunicationStore`: This is of type ``simpy.Store``

----------------------
Task and Process Types
----------------------

Tasks and simpy processes have output types that are ``Generator`` types. UPSTAGE has a type alias for each of these:

.. code-block:: python

    from simpy import Environment
    from upstage.type_help import TASK_GEN, SIMPY_GEN
    from upstage.api import Task, Actor, process, InterruptStates

    class SomeTask(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            ...

        def on_interrupt(self, *, actor: Actor, cause: Any) -> InterruptStates:
            ...
            return self.INTERRUPT.END

    @process
    def a_simpy_process(env: Environment, wait: float) -> SIMPY_GEN:
        yield env.timeout(wait)

The methods on decision tasks should all return ``None``.


--------------------
Avoiding Circularity
--------------------

If you have a lot of circularity in your code, such as actors needing to know about each other within their definitions,
there are a few things to try. First, is to use ``Protocol`` classes to define the interfaces. Then, ensure that your state
definitions, methods, etc. match the protocols. This can limit the effectiveness of the protocol if you'd like type hinting and
tab completion in your IDE. If at all possible, use the actual |Actor| subclasses as types in |Task| classes and elsewhere to get all
the features they have as hints.

An alternative is to use ``typing.TYPE_CHECKING`` to allow circular imports for when ``mypy`` checks. Use a string of the type
instead of the actual type in this case. There are several examples of this in UPSTAGE and in SIMPY, both for circularity and for
making the API easier to understand for ``mypy`` and your IDE. This will allow your IDE to hint more things to you, and can prevent
mypy errors if you use a protocol an forget to add something like ``add_knowledge`` to it.

The first thing to check is if inheritence in the actors can solve your problem, but often it cannot. If you actors are in
the same file, you can simply use strings for the types, and you're all set. If they are in separate files, use the above two
ideas.

.. code-block:: python

    class Manager(UP.Actor):
        employees = UP.State[list["Employee"]](default_factory=list)

    
    class Employee(UP.Actor):
        # Note the string "None", because a None value is treated as no default.
        manager = UP.State[Manager | str](default="None")
