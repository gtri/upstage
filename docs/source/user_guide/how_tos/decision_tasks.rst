==============
Decision Tasks
==============

Decision tasks are :py:class:`~upstage_des.task.Task`s that take zero time and were briefly demonstrated in :doc:`Rehearsal </tutorials/rehearsal>`. The purpose of a
Decision task is to allow decision making and :py:class:`~upstage_des.task_networks.TaskNetwork` routing without moving the simulation clock and do so inside of a Task Network.

A decision task must implement two methods:

* :py:class:`~upstage_des.task.DecisionTask.make_decision`
* :py:class:`~upstage_des.task.DecisionTask.rehearse_decision`

Neither method outputs anything. The expectation is that inside these methods you modify the task network using:

* :py:meth:`upstage_des.actor.Actor.clear_task_queue`: Empty a task queue
* :py:meth:`upstage_des.actor.Actor.set_task_queue`: Add tasks to an empty queue (by string name) - you must empty the queue first.
* :py:meth:`upstage_des.actor.Actor.set_knowledge`: Modify knowledge

The difference between making and rehearsing the decision is covered in the tutorial. The former method is called during normal operations of UPSTAGE, and the latter is called during a
rehearsal of the task or network. It is up the user to ensure that no side-effects occur during the rehearsal that would touch non-rehearsing state, actors, or other data.
