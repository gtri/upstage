import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN


class KnowEvenTask(UP.Task):
    def task(self, *, actor: UP.Actor) -> TASK_GEN:
        evt = actor.create_knowledge_event(name="EvtName")
        actor.create_knowledge_event(name="other evt")
        self.set_actor_knowledge(actor, "finished", False)
        yield evt
        self.set_actor_knowledge(actor, "finished", True, overwrite=True)

    def on_interrupt(self, *, actor: UP.Actor, cause: str) -> UP.InterruptStates:
        self.set_actor_knowledge(actor, "cause", cause)
        return UP.InterruptStates.END


def test_knowledge_event_clear() -> None:
    with UP.EnvironmentContext() as env:
        act = UP.Actor(name="Example")

        task = KnowEvenTask()
        task.run(actor=act)

        env.run()
        assert not act._knowledge["finished"]
        act.succeed_knowledge_event(name="EvtName")
        env.run()
        assert act._knowledge["finished"]
        assert "EvtName" not in act._knowledge
        assert "other evt" in act._knowledge

    with UP.EnvironmentContext() as env:
        act = UP.Actor(name="Example")

        task = KnowEvenTask()
        proc = task.run(actor=act)

        env.run()
        assert not act._knowledge["finished"]
        proc.interrupt(cause="ending")
        env.run()
        assert "EvtName" not in act._knowledge
        assert not act._knowledge["finished"]
        assert act._knowledge["cause"] == "ending"
        # Only the yielded event should be cleared.
        assert "other evt" in act._knowledge


if __name__ == "__main__":
    test_knowledge_event_clear()
