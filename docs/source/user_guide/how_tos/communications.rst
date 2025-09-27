==============
Communications
==============

UPSTAGE provides a built-in classes for passing communications between actors.
There is point-to-point communication which is highly simplified and flexible
for message-passing when you want to abstract away any routing or other concerns.
There is also a communications manager based on routing tables that allows pre-
defined routing to be followed. That same manager is subclassable for more
complicated routing schemes and behaviors.

Point to Point Communications
=============================

The :py:class:`~upstage_des.communications.comms.PointToPointCommsManager` class
allows actors to send messages while allowing for simplified retry attempts
and timeouts. It also allows for communications blocking to be turned on
and off on a point to point basis.

The :py:class:`~upstage_des.communications.comms.Message` class is used to
describe a message, although strings and dictionaries can also be passed as
messages, and UPSTAGE will convert them into the ``Message`` class. The 
message will include information about the sender, mode, and other data.

The communications manager needs to be instantiated and run, and any number
of them can be run to represent different modes of communication. For 
simplicity, communications stores on an actor can have multiple modes
to receive communications on. Each mode needs its own manager which can
then determine the right store to send the message to. 

The following code shows how create an actor class that has two communication
interfaces, and then start the necessary comms managers.

.. code-block:: python

    import upstage_des.api as UP

    class Worker(UP.Actor):
        walkie = UP.CommunicationStore(modes=["UHF"])
        intercom = UP.CommunicationStore(modes=["loudspeaker"])

    
    with UP.EnvironmentContext() as env:
        w1 = Worker(name="worker1")
        w2 = Worker(name="worker2")

        uhf_comms = PointToPointCommsManager(name="Walkies", mode="UHF")
        loudspeaker_comms = PointToPointCommsManager(name="Overhead", mode="loudspeaker")

        UP.add_stage_variable("uhf", uhf_comms)
        UP.add_stage_variable("loudspeaker", loudspeaker_comms)

        uhf_comms.run()
        loudspeaker_comms.run()

The ``PointToPointCommsManager`` class allows for explicitly connecting actors and the
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
***********************

Communications can be halted for all transmissions of a single manager by setting ``comms_degraded`` to be ``True`` at any time.
Setting it back to False will allow comms to pass again, and any retries that are waiting (and didn't exceed a timeout) will go through.

Additionally, specific links can be stopped by adding/removing from ``blocked_links`` with a tuple of ``(sender_actor, destination_actor)``
links to shut down. The same timeout rules will apply.

Routing Table Communications
============================

UPSTAGE has a :py:class:`~upstage_des.communications.routing.StaticNetworkCommsManager` that
routes comms according to a pre-defined network. Nodes (which are ``Actors``) must be
explicitly connected, and this manager will route through shortest number of hops.

An example creation of the manager is given below:

.. code-block:: python

    class CommNode(Actor):
        messages = CommunicationStore(modes=None)

    with EnvironmentContext() as env:
        nodes = {
            name: CommNode(name=name, messages={"modes":["cup-and-string"]})
            for name in "ABCDEFGH"
        }
        mgr = StaticNetworkCommsManager(
            name="StaticManager",
            mode="cup-and-string",
            send_time=1/3600.,
            retry_max_time=20/3600.,
            retry_rate=4/3600.,
            global_ignore=False,
        )
        for u, v in ["AB", "BC", "AD", "DE", "EF", "FG", "GH", "HC", "EB"]:
            mgr.connect_nodes(nodes[u], nodes[v], two_way=False)

Note how this manager uses ``connect_nodes()``, to define explicit edges in the
routing graph. You can optionally set ``two_way`` to ``True`` if you want the
edge to go back and forth.

The manager is still invoked the same by any actor wanting to send a message.
Use ``make_put`` and yield on the returned event to put the message into the
network.

The reason this is called a routing table method, even though it uses a graph,
is because the underlying ``select_hop`` method only tells the current node
where to send the message to. Once the message is passed along, it'll re-check
what node to go to next.

This manager allows for degraded comms and comms retry like the point-to-point one.
If a link is degraded, after the retry fails the network will re-plan a
route assuming the intermediate destination node is no longer available.

.. note::

    Message routing does not depend on the Actors used for routing. No messages
    are sent to the stores on the Actors connected, and the actors do not need
    tasks or processes to handle message routing. The routing manager moves
    the messages in time only until it reaches the desired destination.

The behavior is:

1. Ask for transmit from SOURCE to DEST
2. Set CURRENT to SOURCE
3. Find the NEXT in the shortest path from CURRENT to DEST
4. If there is no path, stop trying to send and end.
5. Attempt to send to NEXT (this is the degraded comms/retry step)
6. If it can send, do so. Set CURRENT = NEXT. If NEXT is DEST, Goto 8. Otherwise, Goto 3.
7. If it can't send, drop NEXT from the route options. Goto 3
8. Place message in DEST and end.

Since this is time-based, a link can re-open during transmission. If the
network has paths:

::

    A -> B -> C
    A -> D -> E -> F -> G -> H -> C
    E -> B -> C


and we want to send a message from A to C, but B is blocked, a retry will have the
network eventually take the long way through ADEFGHC. If B comes back online
after the message gets to E, the routing will choose ADEBC instead.

If B does not come back online, the router will still try to go to B from E
since that is shorter. If B is still down, it will take longer due to the
retry. Set the input ``global_ignore`` to ``True`` to ignore a bad node
for the entire routing and avoid this behavior.

Make Your Own
=============

The intent of the :py:class:`~upstage_des.communications.routing.StaticNetworkCommsManager` class
is to provide an example of a more dynamic comms routing feature. It is based on the
:py:class:`~upstage_des.communications.routing.RoutingCommsManagerBase` class, which holds most
of the work the manager does. This includes managing retries and the behavior steps described
above. The ``StaticNetworkCommsManager`` only implements enough features to build, store, and
call the network to determine the next hop.

To make your own, you only have to implement the ``select_hop`` method, which returns the next
actor to send a message to. Currently, there are not placeholders in the base class for
running other processes (such as acknowledgment, network discovery, etc.) on failures in the
built-in message transmission process. Acknowledgment is implied through the retry features,
but anything more advanced is not built-in.

It is possible to create a network discovery protocol in effect by creating a process that
determines which links should exist at a given time step. Then, as long as the data structure
you modify there is used in ``select_hop``, you can have more complicated network behaviors
approximated without large amounts of explicit message passing.
