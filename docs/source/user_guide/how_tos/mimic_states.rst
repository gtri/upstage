============
Mimic States
============

Mimic states allow one actor to use another actor's state in place of its own. If you have two "Worker" actors riding in a car, it is
useful to have their location mimic that of the car, rather than write a task for the workers that does the same thing as the car.

Mimic states are activated and deactivated in a similar manner to other states, and they can mimic :doc:`ActiveStates <active_states>` as well.

.. code-block:: python

    ...
    actor.activate_mimic_state(
        self_state="name of state on self",
        mimic_state="name of state to mirror",
        mimic_actor=actor_object_that_has_mimic_state,
        task=self,
    )
    ...
    actor.deactivate_mimic_state(
        self_state="name of state on self",
        task=self,
    )
    ...


Here is a complete example that demonstrates how to use a mimic state:

.. code-block:: python
    :linenos:

    class Car(UP.Actor):
        location = UP.CartesianLocationChangingState(recording=True)
        speed = UP.State(default=2.0)
        riders = UP.State(default_factory=list)


    class Worker(UP.Actor):
        location = UP.State(valid_types=UP.CartesianLocation, recording=True)
        car = UP.State()


    class CarMove(UP.Task):
        def task(self, *, actor: Car):
            new = UP.CartesianLocation(10, 10)
            dist = new - actor.location
            time = dist / actor.speed
            actor.activate_location_state(
                state="location",
                speed=actor.speed,
                waypoints=[new],
                task=self,
            )
            yield UP.Wait(time)
            actor.deactivate_all_states(task=self)
            actor.location
            while actor.riders:
                rider = actor.riders.pop()
                rider.succeed_knowledge_event(name="ARRIVED", cause="here")


    class WorkerRide(UP.Task):
        def task(self, *, actor: Worker):
            car: Car = actor.car
            actor.activate_mimic_state(
                self_state="location",
                mimic_state="location",
                mimic_actor=car,
                task=self,
            )
            evt = actor.create_knowledge_event(name="ARRIVED")
            # NOT A REHEARSAL-SAFE THING TO DO:
            # Better: use a store get/put for real interaction
            car.riders.append(actor)
            yield evt
            print(f"{actor} got event: {evt.get_payload()}: {env.now:.2f}")
            actor.deactivate_mimic_state(
                self_state="location",
                task=self,
            )
            
    def location_ping(env, time, actors):
        while True:
            yield env.timeout(time)
            for a in actors:
                a.location
            
    with UP.EnvironmentContext() as env:
        car = Car(name="Zaphod", location=UP.CartesianLocation(0,0), speed=2)
        w1 = Worker(name="Arthur", car=car, location=UP.CartesianLocation(1,1))
        w2 = Worker(name="Trillian", car=car, location=UP.CartesianLocation(1,2))
        
        CarMove().run(actor=car)
        WorkerRide().run(actor=w1)
        WorkerRide().run(actor=w2)
        
        proc = env.process(location_ping(env, 0.3, [car, w1, w2]))
        
        env.run(until=8)
        print()
        print(w1.location)
        print(w2.location)
        print(car.location)
        print()
        for i in range(10):
            t1, loc1 = w1._location_history[i]
            tc, locc = car._location_history[i]
            print(((t1 - tc), (loc1.x - locc.x), (loc1.y - locc.y)))

    >>> Worker: Trillian got event: {'cause': 'here'}: 7.07
    >>> Worker: Arthur got event: {'cause': 'here'}: 7.07
    >>> 
    >>> CartesianLocation(x=10.0, y=10.0, z=0.0)
    >>> CartesianLocation(x=10.0, y=10.0, z=0.0)
    >>> CartesianLocation(x=10.0, y=10.0, z=0.0)
    >>> 
    >>> (0.0, 1, 1)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)
    >>> (0.0, 0.0, 0.0)


Things to note:

* Line 26: These riders are put there by another task. This is generally bad form, but works for our small example.

* Line 34: We are making the worker's CartesianLocation state match the car's CartesianLocationChangingState.

  * Both can be set with/return a CartesianLocation, so this is OK.

  * If we had one State mimicking a LinearChangingState, that would also work since a State can take a floating point value.

  * States type-check under the hood, so you'll get notified if a mimic doesn't match.

* Line 43: Here we warn again about how this is a bad idea in general.

* Line 46: Deactivation is always needed.

  * As discussed in :doc:`Rehearsal </user_guide/tutorials/interrupts>`, these states are also deactivated on an interrupt.

No coordination between the actors has to occur for this to work. In this example, the car exiting is done to show the useful nature of mimic states,
and to demonstrate other UPSTAGE features, such as ``create_knowledge_event`` and ``succeed_knowledge_event``.

As long as the state values are compatible, ``mimic_state`` should make one get its value (when requested) from its mimic. If either is recording, that
will cause the recording to affect both. Finally, if the actor whose state is being mimiced changes or is deleted, then the mimic state may have issues. This
is not explicitly accounted for, and it is up to the user to make sure dependent actors handle those situations.
