================
UPSTAGE vs SimPy
================
.. include:: ../../class_refs.txt

Here we will motivate some of the reason for the existence of UPSTAGE by comparing how things might be done
in both frameworks. SimPy is both simple and powerful, but creating complicated behaviors in agents can result in bulky,
hard to read, and hard to maintain code. Once a simulation designer begins coding large simulations in SimPy, it is our
belief that something like UPSTAGE would emerge to manage the more complexity. 

For this section, we'll use the cashier example from the first tutorial.

The full final example can be :doc:`found here <complex_cashier>`.

----------------
Basic Simulation
----------------

Let's recall the steps of the simulation:

#. Show up to work
#. Go to the checkout lane the "store manager" tells them.
#. Wait for a customer OR break time
#. If customer: Scan items and receive payment
#. If break: take a break, then return to wait.
#. On store closing, go home, then return in the morning.

We'll start by importing and making classes for the entities. Then the cashier's process is defined.

.. code-block:: python

    import simpy as SIM
    from dataclasses import dataclass, field
    import random

    rnd = random.Random()

    @dataclass
    class Cashier:
        name: str
        scan_speed: float
        time_until_break: float = field(default=120.0)
        breaks_until_done: int = field(default=2)
        breaks_taken: int = field(default=0)
        items_scanned: int = field(default=0)
        time_scanning: float = field(default=0.0)


    @dataclass
    class CheckoutLane:
        name: str
        customer_queue: SIM.Store


    class StoreBoss:
        def __init__(self, lanes: list[CheckoutLane]) -> None:
            self.lanes = lanes
            self._lane_map: dict[str, Cashier] = {}

        def get_lane(self, cashier: Cashier) -> CheckoutLane:
            possible = [lane for lane in self.lanes if lane.name not in self._lane_map]
            lane = rnd.choice(possible)
            self._lane_map[lane.name] = cashier
            return lane


    def checkout_customer(cashier: Cashier, items: int, env: SIM.Environment):
        per_item_time = cashier.scan_speed / items
        for _ in range(items):
            yield env.timeout(per_item_time)
            cashier.items_scanned += 1
        # taking payment
        yield env.timeout(2.0)


    def run_cashier(cashier: Cashier, store_boss: StoreBoss, env: SIM.Environment) -> None:
        while True:
            # go to work
            yield env.timeout(15.0)

            # talk to the boss
            lane: SIM.Store = store_boss.get_lane(cashier)
            
            # reset for the day
            cashier.breaks_taken = 0
            
            # start the waiting in lane loop
            while True:
                break_start = env.now + cashier.time_until_break
                wait_until_break = break_start - env.now
                need_break = wait_until_break <= 0
                if not need_break:
                    break_wait = env.timeout(wait_until_break)
                    cust_get = lane.customer_queue.get()
                    ret = yield break_wait | cust_get
                    if break_wait.processed:
                        need_break = True
                        if cust_get in ret:
                            yield lane.customer_queue.put(ret[cust_get])
                        else:
                            cust_get.cancel()
                    else:
                        yield from checkout_customer(cashier, ret[cust_get], env)

                if need_break:
                    # take a break
                    cashier.breaks_taken += 1
                    if cashier.breaks_taken == cashier.breaks_until_done:
                        # go to a night rest
                        break
                    else:
                        yield env.timeout(15.0)
                        
            # night break
            yield env.timeout(60 * 12.0)
            
            
    def customer_spawner(
        env: SIM.Environment,
        lanes: list[CheckoutLane],
    ):
        while True:
            hrs = env.now / 60
            time_of_day = hrs // 24
            if time_of_day <= 8 or time_of_day >= 15.5:
                time_until_open = (24 - time_of_day) + 8
                yield env.timeout(time_until_open)

            lane_pick = rnd.choice(lanes)
            number_pick = rnd.randint(3, 17)
            yield lane_pick.customer_queue.put(number_pick)
            t = rnd.random() * 25.0 + 5
            yield env.timeout(t)
        
Then we can run the sim with:

.. code-block:: python

    env = SIM.Environment()
    cashier = Cashier(
        name="Bob",
        scan_speed=1.0,
        time_until_break=120.0,
        breaks_until_done=4,
    )
    lane_1 = CheckoutLane(name="Lane 1", customer_queue=SIM.Store(env))
    lane_2 = CheckoutLane(name="Lane 2", customer_queue=SIM.Store(env))
    boss = StoreBoss(lanes=[lane_1, lane_2])

    customer_proc = env.process(customer_spawner(env, [lane_1, lane_2]))
    cashier_proc = env.process(run_cashier(cashier, boss, env))
    env.run(until=20 * 60)

    cashier.items_scanned
    >>> 83


-----------------
First Impressions
-----------------

Much of the simulation feels the same, and it feels somewhat more streamlined (it is half as many lines of code). 

However, the sim is not currently instrumented to record any data, so we don't know when items are scanned, when the customer queue is how full when, etc. We could add that with:

.. code-block:: python

    @dataclass
    class Cashier:
        ...
        items_scanned_data: list[tuple[float, int]]
        ...

    ...

    def checkout_customer(cashier: Cashier, items: int, env: SIM.Environment):
        per_item_time = cashier.scan_speed / items
        for _ in range(items):
            yield env.timeout(per_item_time)
            prev = cashier.items_scanned_data[-1][1]
            cashier.items_scanned_data.append((env.now, prev + 1))
        # taking payment
        yield env.timeout(2.0)

    ...

This gets bulky in any reasonably sized simulation. If you want to turn on or off the recording of certain values, that would have to be controlled within the business logic, adding to 
code bloat and hurting readability.

If you want to record something new, you have to find all the points where it changes and add in the data recording code. Additionally, there is no built-in way to record information
about store events.

Finally, the second `while` loop has a bulky control flow that will break down if more complicated actions are needed. The sim is simple for now because the cashier only follows a simple
linear story (with one IF/OR for the break).

The other factor keeping the code simple is that no methods or entities are interacting.

---------------------------
Interrupts and Complex Flow
---------------------------

Once your research into cashier logistics is going well with the existing code base, the grocery store chain (who is paying for the research) asks what happens to items scanned per minute
if the store manager needs to ask a cashier to go restock a shelf. Now we need to have the cashier know about a request, finish the checkout, then go do the restock. This should also
respect the break time rules. 

We would start by doing this (assume any unseen methods are appropriate):

.. code-block:: python

    class Cashier:
        ...
        requests: SIM.Store

    ...
    # inside run_cashier
    break_wait = env.timeout(wait_until_break)
    cust_get = lane.customer_queue.get()
    restock = cashier.requests.get()
    ret = yield break_wait | cust_get | restock
    # figure out which one happened, then do that task
    if break_wait.processed:
        if restock.processed:
            # tell the manager we can't restock yet
            yield store_boss.tell(cashier, "I'll do it later")
            # TODO: How would we take a break THEN go restock?
        else:
            # break-taking code
            ...
    elif restock.processed:
        # some code to restock
    elif cust_get.processed:
        # process the customer
    ...

The code paths become more complicated the more things the cashier can do. Especially if you want to handle the case where a manager asks for a restock when the cashier is about to go
on break. And the more behaviors and jobs that the simulation needs the cashier or employee to do, the more complicated this code section becomes.

---------------
UPSTAGE Version
---------------

In UPSTAGE, we can use the |Task| and |TaskNetworks| to manage the behaviors in a more forward-compatible manner that preserves the readability of the business logic.

Now that we know we need to simulate tasking from the manager that alters our process flow, let's create a new task for that purpose. Here we are building off of  :doc:`the original sim </user_guide/tutorials/first_sim_full>`.

Also note that we aren't setting up the comms receive task yet. That's later.

.. code-block:: python

    class Cashier(UP.Actor):
        ...
        # Messages store for when we do comms
        messages: UP.SelfMonitoringStore = UP.ResourceState(
            default=UP.SelfMonitoringStore,
        )

        def time_left_to_break(self):
            elapsed = self.env.now - self.get_knowledge("start_time", must_exist=True)
            return self.time_until_break - elapsed


    class InterruptibleTask(UP.Task):
        def on_interrupt(self, *, actor: Cashier, cause: Any) -> InterruptStates:
            # We will only interrupt with a dictionary of data
            assert isinstance(cause, dict)
            job_list: list[str]

            if cause["reason"] == "BREAK TIME":
                job_list = ["Break"]
            elif cause["reason"] == "NEW JOB":
                job_list = cause["job_list"]
            else:
                raise UP.SimulationError("Unexpected interrupt cause")

            # determine time until break
            time_left = actor.time_left_to_break()
            # if there are only five minutes left, take the break and queue the task.
            if time_left <= 5.0 and "Break" not in job_list:
                job_list = ["Break"] + job_list
            
            # Ignore the interrupt, unless we've marked it to know otherwise
            marker = self.get_marker() or "none"
            if marker == "on break":
                if "Break" in job_list:
                    job_list.remove("Break")

            self.clear_actor_task_queue(actor)
            self.set_actor_task_queue(actor, job_list)
            if marker == "cancellable":
                return self.INTERRUPT.END
            return self.INTERRUPT.IGNORE

That |Task| class can be inherited to expect interrupts, modify the task network, and move forward.

With that framework, we can modify the customer wait task:

.. code-block:: python

    class WaitInLane(InterruptibleTask):
        def task(self, *, actor: Cashier) -> TASK_GEN:
            """Wait until break time, or a customer."""
            lane: CheckoutLane = self.get_actor_knowledge(
                actor,
                "checkout_lane",
                must_exist=True,
            )
            customer_arrival = UP.Get(lane.customer_queue)

            self.set_marker(marker="cancellable")
            yield customer_arrival

            customer: int = customer_arrival.get_value()
            self.set_actor_knowledge(actor, "customer", customer, overwrite=True)


Notice that it is much simpler since we aren't doing the `Any` wait now. The marker is set to tell the interruption to
end the task, rather than the default of attempting to finish it.

We make the `InterruptibleTask` as the base class for all the non-decision tasks.

We also modify the short break task to allow for interrupts. We could use the `InterruptibleTask`

.. code-block:: python

    class ShortBreak(InterruptibleTask):
        def task(self, *, actor: Cashier) -> TASK_GEN:
            """Take a short break."""
            self.set_marker("on break")
            yield UP.Wait(15.0)
            self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)
            # The break timing will go here

-----------------
Break Timing Task
-----------------

The break timing and interrupting can be handled separately by this task:

.. code-block:: python

    class CashierBreakTimer(UP.Task):
        def task(self, *, actor: Cashier):
            yield UP.Wait(actor.time_until_break)
            actor.interrupt_network("CashierJob", cause=dict(reason="BREAK TIME"))


And the break timer is run inside the `TalkToBoss` and `ShortBreak` tasks when the start time is set. This is somewhat poor practice,
but for the sake of keeping the example relatively simple, we'll take this direct route.

.. code-block:: python

    class TalkToBoss(UP.DecisionTask):
        def make_decision(self, *, actor: Cashier) -> None:
            """Zero-time task to get information."""
            ...
            self.set_actor_knowledge(actor, "start_time", self.env.now)
            # Convenient spot to run the timer.
            CashierBreakTimer().run(actor=actor)

    ...

    class ShortBreak(UP.Task):
        def task(self, *, actor: Cashier):
            """Take a short break."""
            yield UP.Wait(15.0)
            self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)
            CashierBreakTimer().run(actor=actor)


Running the example as is works the same as before, but now the task flow is interrupted safely by a timing task, removing code within
each task that was checking for that time. This increases the overall amount of code, but reduces the per-task code, leading to
more readable and direct reasoning about the tasks. This also builds the foundation for extensiblity of behaviors and tasks, because
we have mostly separated the logic of task flow, and task behavior. 

We must also change the decision task for breaks to account for us now adding to the task queue after break.

.. code-block:: python

    class Break(UP.DecisionTask):
        def make_decision(self, *, actor: Cashier):
            """Decide what kind of break we are taking."""
            actor.breaks_taken += 1

            # we might have jobs queued
            queue = self.get_actor_task_queue(actor) or []
            if "Break" in queue:
                raise UP.SimulationError("Odd task network state")
            self.clear_actor_task_queue(actor)

            if actor.breaks_taken == actor.breaks_until_done:
                self.set_actor_task_queue(actor, ["NightBreak"])
            elif actor.breaks_taken > actor.breaks_until_done:
                raise UP.SimulationError("Too many breaks taken")
            else:
                self.set_actor_task_queue(actor, ["ShortBreak"] + queue)


---------------
Adding Messages
---------------

Message handling is added with this code:

.. code-block:: python

    class CashierMessages(UP.Task):
        def task(self, *, actor: Cashier):
            getter = UP.Get(actor.messages)
            yield getter
            tasks_needed: list[str] | str = getter.get_value()
            tasks_needed = [tasks_needed] if isinstance(tasks_needed, str) else tasks_needed
            actor.interrupt_network(
                "CashierJob",
                cause=dict(reason="NEW JOB", job_list=tasks_needed),
            )

    cashier_message_net = UP.TaskNetworkFactory.from_single_looping("Messages", CashierMessages)

    ...

    # def run_cashier()...
    ...
    net = cashier_task_network.make_network()
    cashier.add_task_network(net)
    cashier.start_network_loop(net.name, "GoToWork")
    cnet = cashier_message_net.make_network()
    cashier.add_task_network(cnet)
    cashier.start_network_loop(cnet.name, "CashierMessages")


Here the task will loop forever, coming back to wait for a message and pass along the interrupt after formatting the message data.

Now it's up to the simulation creator to add a task for restock that goes back to the checkout lane when it's done. Hint: use the default paths in the task network to do that! The
cashier remembers the assigned checkout lane in its knowledge. The only other thing to do is create a task (or a simpy process if we are being simple) to get the store manager to farm
out tasks:

.. code-block:: python

    class manager_process(boss: StoreBoss, cashiers: list[Cashier]):
        while True:
            # Use the random uniform feature, but convert the UPSTAGE event to simpy
            # because this is a simpy only process
            yield UP.Wait.from_random_uniform(15., 30.).as_event()
            cash = rnd.choice(cashiers)
            yield cash.messages.put(["Restock"])

    ...
    env.process(manager_process(boss, [cashier]))
    ...

-------------------
UPSTAGE Perspective
-------------------

What this example has hopefully shown is that UPSTAGE provides (besides the benefit of built-in data recording for all objects)
a foundation for future-friendly simulations.

There is a cost to that friendliness, which is the verbosity of some of the overhead code in creating tasks, the networks, etc.
It is our belief that this verbosity is a benefit rather than a true cost. It is very easy to make task flow mistakes if there
aren't lots of rules and checks, especially as simulations find emergent results and values of states that a simulation designer
may not have anticipated. Similarly, simulations are generally never finished, as new features and behaviors are often added.
UPSTAGE provides a way to add those behaviors with minimal effort or changes to the existing code.

There is also no one way to make an UPSTAGE simulation. An alternative way to handle break timing and messages would have been
through setting knowledge. A decision task could be run after the `ShortBreak` to choose what to do next, or have been run as part
of a loop where every cashier action ends with a decision task that looks at the requested jobs and plans. Either way would work,
and both would take advantage of UPSTAGE's features for task, event, and state cleanup and tracking.

The key perspective of UPSTAGE is to put in the effort up front to make modular, atomic tasks that handle interrupts
gracefully. Then use task networks to control their flow. Use "parallel" message passing and handling tasks or task networks
to interrupt the primary task networks safely. By separating what an actor can do (and how it does it) from deciding what it should
do, our simulations can grow larger without sacrificing stability or readability.
