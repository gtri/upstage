# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any

import pytest
from simpy import Store

import upstage_des.api as UP
from upstage_des.api import (
    Actor,
    EnvironmentContext,
    Get,
    Message,
    MessageContent,
    PointToPointCommsManager,
    ResourceState,
    State,
    Task,
    Wait,
)
from upstage_des.communications.processes import generate_comms_wait
from upstage_des.type_help import SIMPY_GEN, TASK_GEN


class ReceiveSend(Actor):
    incoming = ResourceState[Store](default=Store)
    result = State[Any](default="None")


class ReceiveTask(Task):
    def task(self, *, actor: ReceiveSend) -> TASK_GEN:
        item = yield Get(actor.incoming)
        actor.result = item


class SendTask(Task):
    comms: PointToPointCommsManager
    receiver: ReceiveSend

    def task(self, *, actor: ReceiveSend) -> TASK_GEN:
        yield Wait(1.0)
        content = MessageContent(data=dict(action="move", thought="good"))
        message = Message(actor, content, self.receiver)
        yield self.comms.make_put(message, actor, self.receiver)


def test_send_receive() -> None:
    with EnvironmentContext() as env:
        receiver = ReceiveSend(name="recv")
        sender = ReceiveSend(name="send")

        rec_task = ReceiveTask()
        sen_task = SendTask()

        comms = PointToPointCommsManager(
            name="Comm",
            init_entities=[(receiver, "incoming")],
            debug_logging=True,
        )
        comms.run()

        rec_task.run(actor=receiver)
        sen_task.comms = comms
        sen_task.receiver = receiver
        sen_task.run(actor=sender)

        env.run()

        assert env.now == 1.0, "Wrong simulation end time for comms"
        assert receiver.result != "None", "No result for comms"
        assert isinstance(receiver.result, Message), "Wrong result format"
        content = receiver.result.content.data
        assert content["action"] == "move"
        assert content["thought"] == "good"


def test_send_receive_delayed() -> None:
    with EnvironmentContext() as env:
        receiver = ReceiveSend(name="recv")
        sender = ReceiveSend(name="send")

        rec_task = ReceiveTask()
        sen_task = SendTask()

        comms = PointToPointCommsManager(
            name="Comm",
            send_time=0.25,
            debug_logging=True,
        )
        comms.connect(receiver, "incoming")
        comms.run()

        rec_task.run(actor=receiver)
        sen_task.comms = comms
        sen_task.receiver = receiver
        sen_task.run(actor=sender)

        env.run()

        assert env.now == 1.25, "Wrong simulation end time for comms"
        assert receiver.result != "None", "No result for comms"
        assert isinstance(receiver.result, Message), "Wrong result format"
        content = receiver.result.content.data
        assert content["action"] == "move"
        assert content["thought"] == "good"


def test_degraded() -> None:
    with EnvironmentContext() as env:
        receiver = ReceiveSend(name="recv")
        sender = ReceiveSend(name="send")

        rec_task = ReceiveTask()
        sen_task = SendTask()

        comms = PointToPointCommsManager(
            name="Comm",
            send_time=0.25,
            debug_logging=True,
        )
        comms.comms_degraded = True
        comms.connect(receiver, "incoming")
        comms.run()

        rec_task.run(actor=receiver)
        sen_task.comms = comms
        sen_task.receiver = receiver
        sen_task.run(actor=sender)

        env.run(until=4)
        comms.comms_degraded = False

        assert receiver.result == "None"


def test_blocked() -> None:
    with EnvironmentContext() as env:
        receiver = ReceiveSend(name="recv")
        sender = ReceiveSend(name="send")

        rec_task = ReceiveTask()
        sen_task = SendTask()

        comms = PointToPointCommsManager(
            name="Comm",
            send_time=0.25,
            debug_logging=True,
        )
        comms.connect(receiver, "incoming")
        comms.run()

        comms.blocked_links.append((sender, receiver))

        rec_task.run(actor=receiver)
        sen_task.comms = comms
        sen_task.receiver = receiver
        sen_task.run(actor=sender)

        env.run(until=4)
        comms.comms_degraded = False

        assert receiver.result == "None"


def test_comms_wait() -> None:
    with UP.EnvironmentContext() as env:
        store = Store(env=env)
        data_point = []

        def cback(message: MessageContent) -> None:
            data_point.append(message)

        msg = Message(
            sender=UP.Actor(name="me"),
            content=MessageContent(data={"hello": "world"}),
            destination=UP.Actor(name="you"),
        )
        wait_proc = generate_comms_wait(store, cback)
        wait_proc()

        store.put(msg)
        env.run(until=1)
        assert len(data_point) == 1


class Worker(UP.Actor):
    walkie = UP.CommunicationStore(modes=["UHF", "other"])
    intercom = UP.CommunicationStore(modes="loudspeaker")


def test_worker_talking() -> None:
    with EnvironmentContext() as env:
        w1 = Worker(name="worker1")
        w2 = Worker(name="worker2")

        uhf_comms = PointToPointCommsManager(name="Walkies", mode="UHF")
        loudspeaker_comms = PointToPointCommsManager(name="Overhead", mode="loudspeaker")

        uhf_comms.run()
        loudspeaker_comms.run()

        evt1 = uhf_comms.make_put("Hello worker", w1, w2)
        evt2 = loudspeaker_comms.make_put("Hello worker", w2, w1)

        def do() -> SIMPY_GEN:
            yield evt1.as_event()
            yield evt2.as_event()

        env.process(do())

        env.run()
        assert len(w2.walkie.items) == 1
        assert w2.walkie.items[0].mode == "UHF"
        assert len(w1.intercom.items) == 1
        assert w1.intercom.items[0].mode == "loudspeaker"


class CommNode(Actor):
    messages = UP.CommunicationStore(modes=None)


def _build_net(two_way: bool = False) -> tuple[dict[str, CommNode], UP.RoutingTableCommsManager]:
    nodes = {
        name: CommNode(name=name, messages={"modes": ["cup-and-string"]}) for name in "ABCDEFGH"
    }
    mgr = UP.RoutingTableCommsManager(
        name="StaticManager",
        mode="cup-and-string",
        send_time=1 / 3600.0,
        retry_max_time=20 / 3600.0,
        retry_rate=4 / 3600.0,
        debug_logging=True,
    )
    # Set up the routes
    opts = [
        ("A", "B"),
        ("B", "C"),
        ("A", "D"),
        ("D", "E"),
        ("E", "F"),
        ("F", "G"),
        ("G", "H"),
        ("H", "C"),
        ("E", "B"),
    ]
    for u, v in opts:
        mgr.connect_nodes(nodes[u], nodes[v], two_way=two_way)
    return nodes, mgr


def _start(
    msg: str, mgr: UP.RoutingTableCommsManager, nodes: dict[str, CommNode], source: str, dest: str
) -> SIMPY_GEN:
    put = mgr.make_put(msg, nodes[source], nodes[dest])
    yield put.as_event()


def test_routing_basic() -> None:
    with EnvironmentContext() as env:
        nodes, mgr = _build_net()
        # Check the shortest path calcs with node dropouts.
        nxt = mgr.select_hop(nodes["A"], nodes["C"])
        assert nxt is nodes["B"]
        nxt = mgr.select_hop(nodes["A"], nodes["C"], [nodes["B"]])
        assert nxt is nodes["D"]
        nxt = mgr.select_hop(nodes["A"], nodes["C"], [nodes["B"], nodes["D"]])
        assert not nxt

        # Asking for a node not in the network will fail
        notin = CommNode(name="not in", messages={"modes": ["doesn'thave"]})
        nxt = mgr.select_hop(notin, nodes["C"], [nodes["B"], nodes["D"]])
        assert nxt is None

        with pytest.raises(UP.SimulationError, match="has no comms store on mode"):
            mgr.connect_nodes(notin, nodes["C"])

        # Test the actual routing mechanics
        # Run the manager
        mgr.run()
        env.process(_start("First message", mgr, nodes, "A", "C"))
        env.run()
        # Takes two hops to reach the destination
        assert env.now == 1 / 3600 * 2.0
        assert len(mgr.debug_log) == 3
        assert mgr.debug_log[0]["time"] == 0
        assert mgr.debug_log[0]["event"] == "Moved message"
        assert mgr.debug_log[0]["current"] == nodes["A"]
        assert mgr.debug_log[0]["destination"] == nodes["B"]
        assert mgr.debug_log[1]["time"] == 1 / 3600
        assert mgr.debug_log[1]["event"] == "Moved message"
        assert mgr.debug_log[1]["current"] == nodes["B"]
        assert mgr.debug_log[1]["destination"] == nodes["C"]
        assert mgr.debug_log[2]["time"] == 1 / 3600 * 2
        assert mgr.debug_log[2]["event"] == "Destination reached"
        assert len(nodes["C"].messages.items) == 1
        assert nodes["C"].messages.items[0].content.message == "First message"

        nodes, mgr = _build_net(two_way=True)
        mgr.run()
        env.process(_start("First message", mgr, nodes, "C", "A"))
        env.run()
        assert len(mgr.debug_log) == 3
        assert nodes["A"].messages.items[0].content.message == "First message"
        assert nodes["B"].messages.items == []


def test_routing_drop_node() -> None:
    """When we drop a node, expect it to take longer.

    This doesn't have global on, which means B will be tried twice.
    """
    with EnvironmentContext() as env:
        nodes, mgr = _build_net()
        mgr.run()
        mgr.blocked_nodes.append(nodes["B"])
        env.process(_start("Second message", mgr, nodes, "A", "C"))
        env.run()
        expected_time = (20 / 3600.0 * 2) + (1 / 3600 * 6)
        assert pytest.approx(env.now) == expected_time
        assert len(mgr.debug_log) == 19
        expect = ["Can't send, waiting"] * 5 + ["Stopped trying to send"] + ["Moved message"] * 2
        expect += ["Can't send, waiting"] * 5 + ["Stopped trying to send"]
        expect += ["Moved message"] * 4 + ["Destination reached"]
        assert [x["event"] for x in mgr.debug_log] == expect
        assert nodes["C"].messages.items[0].content.message == "Second message"


def test_routing_drop_node_global() -> None:
    """When we drop a node, expect it to take longer.

    This has global on, which means B will be tried only once.
    """
    with EnvironmentContext() as env:
        nodes, mgr = _build_net()
        mgr.global_ignore = True
        mgr.blocked_nodes.append(nodes["B"])
        mgr.run()
        env.process(_start("Third message", mgr, nodes, "A", "C"))
        env.run()
        expected_time = 20 / 3600.0 + (1 / 3600 * 6)
        assert pytest.approx(env.now) == expected_time
        assert len(mgr.debug_log) == 13
        expect = ["Can't send, waiting"] * 5 + ["Stopped trying to send"] + ["Moved message"] * 2
        expect += ["Moved message"] * 4 + ["Destination reached"]
        assert [x["event"] for x in mgr.debug_log] == expect
        assert nodes["C"].messages.items[0].content.message == "Third message"


def test_routing_drop_and_return() -> None:
    """Drop a node, but bring it back mid-send."""
    with EnvironmentContext() as env:
        nodes, mgr = _build_net()
        mgr.blocked_nodes.append(nodes["B"])
        mgr.run()
        env.process(_start("Fourth message", mgr, nodes, "A", "C"))

        env.run(until=7 / 3600.0)
        mgr.blocked_nodes = []
        env.run()
        expected_time = 8 / 3600.0 + (1 / 3600 * 2)
        assert pytest.approx(env.now) == expected_time
        assert len(mgr.debug_log) == 5
        expect = ["Can't send, waiting"] * 2 + ["Moved message"] * 2 + ["Destination reached"]
        assert [x["event"] for x in mgr.debug_log] == expect
        assert nodes["C"].messages.items[0].content.message == "Fourth message"


def test_routing_no_route() -> None:
    """Drop a node, but bring it back mid-send."""
    with EnvironmentContext() as env:
        nodes, mgr = _build_net()
        mgr.blocked_nodes.append(nodes["B"])
        mgr.blocked_nodes.append(nodes["D"])
        mgr.run()
        env.process(_start("Fifth message", mgr, nodes, "A", "C"))

        env.run()
        expected_time = 20 / 3600.0 * 2
        assert pytest.approx(env.now) == expected_time
        assert len(mgr.debug_log) == 13
        expect = ["Can't send, waiting"] * 5 + ["Stopped trying to send"]
        expect += ["Can't send, waiting"] * 5 + ["Stopped trying to send"]
        expect += ["No message route available"]
        assert [x["event"] for x in mgr.debug_log] == expect
        assert nodes["C"].messages.items == []


if __name__ == "__main__":
    test_routing_no_route()
