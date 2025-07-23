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

1. :py:class:`~upstage_des.states.DetectabilityState`: This state is a boolean
2. :py:class:`~upstage_des.states.CartesianLocationChangingState`: The output is of type ``CartesianLocation``
3. :py:class:`~upstage_des.states.GeodeticLocationChangingState`: The output is of type ``GeodeticLocation``
4. :py:class:`~upstage_des.states.ResourceState`: The type must be a ``simpy.Store`` or ``simpy.Container`` (or a subclass). You can still define the type.
5. :py:class:`~upstage_des.states.CommunicationStore`: This is of type ``simpy.Store``

----------------------
Task and Process Types
----------------------

Tasks, Routines, and simpy processes have output types that are ``Generator`` types.
UPSTAGE has a type alias for each of these:

.. code-block:: python

    from simpy import Environment
    from upstage_des.type_help import ROUTINE_GEN, SIMPY_GEN, TASK_GEN
    from upstage_des.api import Task, Actor, process, InterruptStates

    class SomeTask(Task):
        def task(self, *, actor: Actor) -> TASK_GEN:
            ...

        def on_interrupt(self, *, actor: Actor, cause: Any) -> InterruptStates:
            ...
            return self.INTERRUPT.END

    class SimpleRoutine(UP.Routine):
        def __init__(self, time: float) -> None:
            self.time = time

        def run(self) -> ROUTINE_GEN:
            yield UP.Wait(self.time, rehearsal_time_to_complete=self.time * 2)

    @process
    def a_simpy_process(env: Environment, wait: float) -> SIMPY_GEN:
        yield env.timeout(wait)

The methods on decision tasks should all return ``None``.

Routines and SimPy generators expect to be able to receive data into themselves and
to return data, but the ``Task.task()`` methods do not give a return value other than
``None`` to indicate a stopping of the iteration.

--------------------
Avoiding Circularity
--------------------

If you have a lot of circularity in your code, such as actors needing to know about each other within their definitions,
there are a few things to try. The first option is to use ``Protocol`` classes to define the interfaces. Then, ensure that your state
definitions, methods, etc. match the protocols. Your protocol will need to inherit from ``Actor`` at some point, otherwise the
type hint system won't let you know about actor specific methods.

The alternative is to use ``typing.TYPE_CHECKING`` to allow circular imports during type checking. Use a string of the type
instead of the actual type in this case. There are several examples of this in UPSTAGE and in SIMPY, both for circularity and for
making the API easier to understand for type checkers and your IDE. This will allow your IDE to hint more things to you, and can prevent
errors if you use a protocol an forget to add something like ``add_knowledge()`` to it.

The first thing to check is if inheritence in the actors can solve your problem, but often it cannot. If you actors are in
the same file, you can simply use strings for the types, and you're all set. If they are in separate files, use the above two
ideas.

.. code-block:: python

    class Manager(UP.Actor):
        employees = UP.State[list["Employee"]](default_factory=list)

    
    class Employee(UP.Actor):
        # Note the string "None", because a None value is treated as no default.
        manager = UP.State[Manager | str](default="None")
