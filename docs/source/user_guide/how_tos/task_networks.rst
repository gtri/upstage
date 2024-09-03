=============
Task Networks
=============

Task Networks have been demonstrated in :doc:`First Simulation </user_guide//tutorials/first_simulation>`, and this document will add some details to the usage of Task Networks.

In general, once an Actor has received a Task Network instance, all introspection or modifications of that network goes through the actor.

Defining a Network
==================

Define a network by mapping a task name (string) to a task class, then by mapping those task names to the tasks that are allowed to take place after the key task has been performed, with an
optional default. 

.. code-block:: python

    class MoveTask(UP.Task):
        # Assume states change and that the next task is defined in the queue
        ...
    
    class ReadTask(UP.Task):
        # Assume states change and that the next task is defined in the queue
        ...
    
    task_classes = {
        "Move": MoveTask,
        "Read": ReadTask,
    }
    task_links = {
        "Move": {
                "default": None,
                "allowed":["Move", "Read"],
            },
        "Read": {
                "default": "Move",
                "allowed":["Move", "Read"],
            },
    }
    move_and_read_factory = UP.TaskNetworkFactory("MoveAndRead", task_classes, task_links)


The task classes are given names, and those strings are used to define the default and allowable task ordering. The task ordering need to know the default task (can be None) and the allowed tasks.
Allowed tasks must be supplied. If no default is given, an error will be thrown if no task ordering is given when a new task is selected. If the default or the set task queue violates the 
allowed rule, an error will be thrown.

To start a task network on an actor with the factory first make an instance of the network, add it to the actor, then start the loop with or without a queue:

.. code-block:: python

    net = move_and_read_factory.make_network()
    some_actor.add_task_network(net)
    some_actor.start_network_loop(net.name, "Move")

You can either start a loop on a single task, or define an initial queue through the network if desired (but you must somehow define the first task to run):

.. code-block:: python

    net = move_and_read_factory.make_network()
    some_actor.add_task_network(net)
    some_actor.set_task_queue(net.name, ["Move", "Move"])
    some_actor.start_network_loop(net.name)


Modifying the Task Network
--------------------------

Task Networks work by running a defined queue of task names, then by selecting ``default`` links until either a new queue is defined or a rule is violated (and you will get an exception).

You can modify the task network flow using:

* :py:meth:`upstage.actor.Actor.clear_task_queue`: Empty a task queue
* :py:meth:`upstage.actor.Actor.set_task_queue`: Add tasks to an empty queue (by string name) - you must empty the queue first.

These two methods are preferred since they prevent the risks of appending to a queue without looking at the queue.

Introspecting the Task Network
------------------------------

The task network queues can be viewed using:

* :py:meth:`upstage.actor.Actor.get_task_queue`: This requires the network name.
* :py:meth:`upstage.actor.Actor.get_all_task_queues`: This will return for all the networks on the actor.

You can get the names and processes of tasks that are running (and their network names) using:

* :py:meth:`upstage.actor.Actor.get_running_task`: Returns a dataclass with the task name and process object of the task on the defined network.
* :py:meth:`upstage.actor.Actor.get_running_tasks`: Returns the same as above, but keyed on task network names.

You would want the processes to interrupt them, but you can also use :py:meth:`upstage.actor.Actor.interrupt_network` to do that.

Note that the task queue methods won't return the current tasks, just what's defined to run next. Use the running task methods to find the current task.

A note on TaskNetworkFactory
----------------------------

The :py:class:`~upstage.task_network.TaskNetworkFactory` class has some convience methods for creating factories from typical use cases:

#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_looping`: From a single task, make a network that loops on it.
    * Useful for a Singleton task that, for example, receives communications and farms them out or manages other task networks.
#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_terminating`: A network that does one task, then freezes for the rest of the simulation.
#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_ordered_looping`: A series of tasks with no branching that loops.
#. :py:meth:`~upstage.task_network.TaskNetworkFactory.from_single_looping`: A series of tasks with no branching that terminates at the end.

A terminating task network contains a :py:class:`~upstage.task.TerminalTask` task at the end, which waits on an un-succeedable event in a rehearsal-safe manner.


Running Multiple Networks
=========================

An actor has no limits to the number of Task Networks it can run. As long as the Actor's states do not overlap in the networks, they can all run in "parallel". Simply keep the network names
unique.

When adding parallel task networks, you can avoid a name clash with :py:meth:`upstage.actor.Actor.suggest_network_name`, and use the resulting name to add the network. When you are done with a network,
it can be deleted from the actor's attributes using: :py:meth:`upstage.actor.Actor.delete_task_network`. The task network will still be allowed to run, so make sure it's in a terminal state first. It will
de-clutter the task network introspection methods, though.

See :doc:`Nucleus <nucleus>` and :doc:`State Sharing <state_sharing>` for features related to inter-Task Networks "communication".

If a state is going to be shared, it's best to add it as a nucleus state so that if another task modifies the state, the other networks can be made aware and change.
