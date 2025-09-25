==============
Communications
==============

UPSTAGE provides a built-in method for passing communications between actors.
The :py:class:`~upstage_des.communications.comms.CommsManager` class
allows actors to send messages while allowing for simplified retry attempts
and timeouts. It also allows for communications blocking to be turned on
and off on a point to point basis.

The :py:class:`~upstage_des.communications.comms.Message` class is used to
describe a message, although strings and dictionaries can also be passed as
messages, and UPSTAGE will convert them into the ``Message`` class.

The communications manager needs to be instantiated and run, and any number
of them can be run, to represent different modes of communication. The
following code shows how create an actor class that has two communication
interfaces, and then start the necessary comms managers.

.. code-block:: python

    import upstage_des.api as UP

    class Worker(UP.Actor):
        walkie = UP.CommunicationStore(modes=["UHF"])
        intercom = UP.CommunicationStore(modes=["loudspeaker"])

    
    with UP.EnvironmentContext() as env:
        w1 = Worker(name="worker1")
        w2 = Worker(name="worker2")

        uhf_comms = CommsManager(name="Walkies", mode="UHF")
        loudspeaker_comms = CommsManager(name="Overhead", mode="loudspeaker")

        UP.add_stage_variable("uhf", uhf_comms)
        UP.add_stage_variable("loudspeaker", loudspeaker_comms)

        uhf_comms.run()
        loudspeaker_comms.run()

The ``CommsManager`` class allows for explicitly connecting actors and the
store that will receive messages, but using the :py:class:`~upstage_des.states.CommunicationStore`
lets the manager auto-discover the proper store for a communications mode,
letting the simulation designer only need to pass the source actor, destination
actor, and message information to the manager.

To send a message, use the comm manager's ``make_put`` method to return an UPSTAGE
event to yield on to send the message.

.. code-block:: python

    class Talk(UP.Task):
        def task(self, *, actor: Worker):
            uhf = self.stage.uhf
            friend = self.get_actor_knowledge(actor, "friend", must_exist=True)
            msg_evt = uhf.make_put("Hello worker", actor, friend)
            yield msg_evt


    class GetMessage(UP.Task):
        def task(self, *, actor: Worker):
            get_uhf = UP.Get(actor.walkie)
            get_loud = UP.Get(actor.loudspeaker)

            yield UP.Any(get_uhf, get_loud)
            
            if get_uhf.is_complete():
                msg = get_uhf.get_value()
                print(f"{msg.sender} sent '{msg.message}' at {msg.time_sent}")
            else:
                get_uhf.cancel()
            ...


Stopping Communications
=======================

Communications can be halted for all transmissions of a single manager by setting ``comms_degraded`` to be ``True`` at any time.
Setting it back to False will allow comms to pass again, and any retries that are waiting (and didn't exceed a timeout) will go through.

Additionally, specific links can be stopped by adding/removing from ``blocked_links`` with a tuple of ``(sender_actor, destination_actor)``
links to shut down. The same timeout rules will apply.
