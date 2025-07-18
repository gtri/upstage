========
Routines
========

The :py:class:`~upstage_des.routines.Routine` class
is designed to provide support for reusable behaviors
that can be yielded from ``Tasks``. They are limited
to only allow UPSTAGE events to be yielded, which allows
them to be rehearsed and support cancelling/interrupt.

A ``Routine`` should be small and self-contained, such that
any cancellation or interrupt has no side effects to the
task that it is running in.

To create a ``Routine``, subclass from the provided base class.
You must implement these methods:

1. ``run()``: The actual event sequence
2. ``cancel()``: Operations to do when the parent task is interrupted
3. ``rehearse()``: Optional specific rehearsal behavior. UPSTAGE
   will run your routine otherwise, which will break if your ``run()``
   has an infinite loop. 

The example below is a routine to draw cards until you get a
certain result.

.. code-block:: python

    import simpy as SIM
    import upstage_des.api as UP
    from upstage_des.type_help import ROUTINE_GEN

    class CardDrawing(UP.Routine):
        def __init__(self, store: SIM.Store, card_value: str) -> None:
            # super() is super!
            super().__init__()
            self.store = store
            self.results: list[str] = []
            self.card_value = card_value

        def run(self) -> ROUTINE_GEN:
            """Draw cards"""
            while True:
                evt = UP.Get(self.store)
                yield evt
                card: str = evt.get_value()
                self.results.append(card)
                if card == self.card_value:
                    # Return works, but you can also store
                    # the answer and access it later.
                    return self.results
        
        def cancel(self) -> ROUTINE_GEN:
            """Undo the operation."""
            while self.results:
                yield UP.Put(self.store, self.results.pop())

        def rehearsal(self) -> tuple[float, Any | None]:
            """Return time and value."""
            # If you return in run(), make sure to return here.
            self.results = ["FAKE CARD"] * 3
            return 0.0, self.results

Then you would use the routine in a task in this way:

.. code-block:: python

    class PlayCardGame(UP.Task):
        def task(self, *, actor: UP.Actor) -> TASK_GEN:
            drawn: list[str] = yield CardDrawing(
                actor.deck,
                "ace",
            )
            actor.add_cards_to_hand(drawn)

You don't have to store the results as an attribute, but if you prefer
to hold onto the routine instance in more complicated circumstances,
this pattern (similar to ``Get().get_value()``) will work:

.. code-block:: python

    class PlayCardGame(UP.Task):
        def task(self, *, actor: UP.Actor) -> TASK_GEN:
            drawer = CardDrawing(
                actor.deck,
                "ace",
            )
            yield drawer
            actor.add_cards_to_hand(drawer.results)

This allows you to define and repeat custom actions in your 
tasks while reducing the lines of code in your tasks. If the
simulation had several card drawing tasks with different conditions
you could design a ``Routine`` that was usable for all of them.

Built-In Routines
*****************

UPSTAGE provides these built-in ``Routines``:

1. :py:class:`~upstage_des.routines.WindowedGet`: A routine
   for getting every item you can from a store in a given time
   window.
