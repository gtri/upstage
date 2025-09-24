========================
Key/Value Resource State
========================

The :py:class:`~upstage_des.states.MultiStoreState` is a state, similar to
:py:class:`~upstage_des.states.DictionaryState`, which allows a state to be
a dictionary. In this case, the dictionary's value are ``Store`` or ``Container``
types, and the state initialization has features to streamline the creation
of those objects.

The use case for this state is for any store or container tracking that has
runtime-definable names beyond the capabilities provided by
:py:class:`~upstage_des.states.ResourceState`. See :doc:`Resource States <resource_state>`
for more information. This state matches much of the syntax of that state.

Here is an example of creating a general ``MultiStoreState``:

.. code-block:: python

    import upstage_des.api as UP

    class Warehouse(UP.Actor):
        storage = UP.MultiStoreState[Store| Container](
            default=Store,
            valid_types=(Store, Container),
            default_kwargs={"capacity": 100},
        )
    
    with UP.EnvironmentContext():
        wh = Warehouse(
            name='Depot',
            storage = {
                "shelf":{"capacity":10},
                "bucket":{"kind": UP.SelfMonitoringContainer, "init": 30},
                "charger":{},
            }
        )
        assert wh.storage["shelf"].capacity == 10
        assert wh.storage["bucket"].level == 30
        assert wh.storage["charger"].capacity == 100
        assert wh.storage["charger"].items == []

In the state definition, the type of the ``MultiStoreState`` is for your
IDE to use.
