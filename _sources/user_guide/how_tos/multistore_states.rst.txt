========================
Key/Value Resource State
========================

The :py:class:`~upstage_des.states.MultiStoreState` is a state, similar to
:py:class:`~upstage_des.states.DictionaryState`, which allows a state to be
a dictionary of ``Store`` or ``Container`` values on string keys. This state
has initialization features to streamline the creation of those objects.

The use case for this state is for any store or container tracking that has
runtime-definable names beyond the capabilities provided by
:py:class:`~upstage_des.states.ResourceState`. See :doc:`Resource States <resource_states>`
for more information. This state matches much of the syntax of the ``ResourceState``.

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

Note how even though the states default to ``Store``, the ``kind`` argument
in the initialization overrides that default. It's only because SimPy stores
and containers have a "capacity" argument that this example doesn't fail. It
is recommended to not mix types if possible to avoid extra work in type checking
or setting appropriate defaults.
