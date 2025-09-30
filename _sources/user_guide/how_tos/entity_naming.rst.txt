==============
Named Entities
==============

Named entities are an :py:class:`~upstage_des.base.EnvironmentContext` and
:py:class:`~upstage_des.base.NamedUpstageEntity` enabled feature where you
can store instances in particular "entity groups" to gather them from later.
UPSTAGE's :py:class:`~upstage_des.actor.Actor` inherits from :py:class:`~upstage_des.base.NamedUpstageEntity`,
giving all Actors the feature. Similarly, the ``SelfMonitoring<>`` resources
do the same to enable quick access to recorded simulation data.

All Actors are retrievable with the :py:meth:`~upstage_des.base.UpstageBase.get_actors`
method if they inherit from Actor.

Entities are retrievable with :py:meth:`~upstage_des.base.UpstageBase.get_all_entity_groups`
and :py:meth:`~upstage_des.base.UpstageBase.get_entity_group`.

Defining a named entity is done in the class definition:

.. code-block:: python

    class Car(UP.Actor, entity_groups=["vehicle"]):
        ...

    class Talker(UP.Actor, entity_groups=["has-radio"]):
        ...

    class Plane(UP.Actor, entity_groups=["vehicle", "air"]):
        ...

    class FastTalkingPlane(Plane, Talker):
        ...

    class NoSpecificGroup(UP.Actor):
        ...
        
    class Different(UP.NamedUpstageEntity, entity_groups=["separate"]):
        ...    
        

Once you are in an environment context you can get the actual instances. 

.. code-block:: python

    with UP.EnvironmentContext():
        manage = UP.UpstageBase()
        
        c1 = Car(name="car1")
        c2 = Car(name="car2")
        p = Plane(name="plane")
        fp = FastTalkingPlane(name="fast plane")
        other = NoSpecificGroup(name="all alone")
        talk = Talker(name="Basic Talker")
        d = Different()
        
        actor_entities = manage.get_actors()
        print(actor_entities)
        >>> [Car: car1, Car: car2, Plane: plane, FastTalkingPlane: fast plane, NoSpecificGroup: all alone, Talker: Basic Talker]
        
        vehicles = manage.get_entity_group("vehicle")
        print(vehicles)
        >>> [Car: car1, Car: car2, Plane: plane, FastTalkingPlane: fast plane]
        
        air = manage.get_entity_group("air")
        print(air)
        >>> [Plane: plane, FastTalkingPlane: fast plane]

        radio = manage.get_entity_group("has-radio")
        print(radio)
        >>> [FastTalkingPlane: fast plane, Talker: Basic Talker]

        different = manage.get_entity_group("separate")
        print(different)
        >>> [<__main__.Different object at ...>]

Note that entity groups are inheritable and that you can inherit from ``NamedUpstageEntity``
and retrieve the instance without needing an Actor. You may also create an instance of
``UpstageBase`` to get access to the required methods. Actors and Tasks can access
that method already.

If you are going to create a non-Actor version of a named entity, ensure your init
calls ``super()``. The following example shows a use case where a simulation may
want to look up entities in the simulation universe that don't need to be actors.

.. code-block:: python

    class PowerGenerator(UP.NamedUpstageEntity):
        def __init__(self, name: str, kwh: float) -> None:
            super().__init__()
            self.name = name
            self.kwh = kwh

        def __repr__(self) -> str:
            return f"{self.name} - {self.kwh}KwH"


    class Nuclear(PowerGenerator, entity_groups="Nuclear"):
        def __init__(self, name: str, kwh: float, num_towers: int) -> None:
            super().__init__(name, kwh)
            self.num_towers = num_towers


    class Planner(UP.DecisionTask):
        def make_decision(self, *, actor: UP.Actor) -> None:
            # Decide on which power plant to upgrade next
            plants = self.get_entity_group("PowerGenerator")
            nuclear = self.get_entity_group("Nuclear")
            print(plants)
            print(nuclear)


    with UP.EnvironmentContext(random_seed=321456) as env:
        rng = UP.get_stage().random
        pgs = [
            PowerGenerator(f"{i}", rng.randint(10, 100))
            for i in range(5)
        ]
        pgs += [
            Nuclear(f"Nuc_{i}", rng.randint(10, 100), rng.randint(1,4))
            for i in range(5)
        ]
        # You wouldn't actually make an actor just to run the task,
        # but it serves as a reminder of getting entities inside
        # an UpstageBase subclass
        t = Planner()
        t.make_decision(actor=UP.Actor(name="example"))
        >>>[0 - 61KwH, 1 - 71KwH, 2 - 58KwH, 3 - 43KwH, 4 - 37KwH, Nuc_0 - 66KwH, Nuc_1 - 60KwH, Nuc_2 - 37KwH, Nuc_3 - 53KwH, Nuc_4 - 15KwH]
        >>>[Nuc_0 - 66KwH, Nuc_1 - 60KwH, Nuc_2 - 37KwH, Nuc_3 - 53KwH, Nuc_4 - 15KwH]
