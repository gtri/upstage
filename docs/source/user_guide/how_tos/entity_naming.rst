==============
Named Entities
==============

Named entities are an :py:class:`~upstage_des.base.EnvironmentContext` and :py:class:`~upstage_des.base.NamedUpstageEntity` enabled feature where you can store instances in particular "entity groups" to gather
them from later. UPSTAGE's :py:class:`~upstage_des.actor.Actor` inherits from :py:class:`~upstage_des.base.NamedUpstageEntity`, giving all Actors the feature.

All Actors are retrievable with the :py:meth:`~upstage_des.base.UpstageBase.get_actors` method if they inherit from Actor.

Entities are retrievable with :py:meth:`~upstage_des.base.UpstageBase.get_all_entity_groups` and :py:meth:`~upstage_des.base.UpstageBase.get_entity_group`.

Defining a named entity is done in the class definition:

.. code-block:: python

    class Car(UP.Actor, entity_groups=["vehicle"]):
        ...

    class Plane(UP.Actor, entity_groups=["vehicle", "air"]):
        ...

    class FastPlane(Plane):
        ...

    class NoSpecificGroup(UP.Actor):
        ...
        
    class Different(UP.NamedUpstageEntity, entity_groups=["separate"]):
        ...    
        

Once you are in an environment context you get the actual instances. 

.. code-block:: python

    with UP.EnvironmentContext():
        manage = UP.UpstageBase()
        
        c1 = Car(name="car1")
        c2 = Car(name="car2")
        p = Plane(name="plane")
        fp = FastPlane(name="fast plane")
        other = NoSpecificGroup(name="all alone")
        d = Different()
        
        actor_entities = manage.get_actors()
        print(actor_entities)
        >>> [Car: car1, Car: car2, Plane: plane, FastPlane: fast plane, NoSpecificGroup: all alone]
        
        vehicles = manage.get_entity_group("vehicle")
        print(vehicles)
        >>> [Car: car1, Car: car2, Plane: plane, FastPlane: fast plane]
        
        air = manage.get_entity_group("air")
        print(air)
        >>> [Plane: plane, FastPlane: fast plane]

        different = manage.get_entity_group("separate")
        print(different)
        >>> [<__main__.Different object at 0x000001FFAB28BE10>]

Note that entity groups are inheritable, that you can inherit from ``NamedUpstageEntity`` and retrieve the instance without needing an Actor, and that it's simple to create an instance of
``UpstageBase`` to get access to the required methods.
