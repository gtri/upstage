# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""States that enable sharing between tasks."""

from upstage_des.actor import Actor
from upstage_des.base import UpstageError
from upstage_des.states import ActiveState
from upstage_des.task import Task


class SharedLinearChangingState(ActiveState[float]):
    """A state whose value changes linearly over time.

    Allows for multiple users of the state, keyed on actor and task.

    Assumes it's a non-frozen, floating-point value.

    Still activated in the usual way:

    >>> class Example(Actor):
    >>>     fuel = SharedLinearChangingState()
    ...
    >>> example.activate_state(
    >>>     state="fuel",
    >>>     task=self,
    >>>     rate=actor.fuel_burn,
    >>> )
    """

    def __init__(
        self,
        *,
        default: float | None = None,
        recording: bool = False,
    ) -> None:
        """Create a linear changing state that is shareable.

        Args:
            default (float | None, optional): Default value. Defaults to None.
            recording (bool, optional): If the state records. Defaults to False.
        """
        super().__init__(
            default=default,
            frozen=False,
            valid_types=float,
            recording=recording,
            default_factory=None,
        )
        self.IGNORE_LOCK: bool = True

    def _active(self, instance: Actor) -> float | None:
        """Return a value to set based on time or some other criteria.

        Args:
            instance (Actor): The actor instance of the state

        Returns:
            float: The value of the state
        """
        # Note the task needs to default to none, so when we call 'active'
        # to update the rate, we aren't adding a new one
        data = self.get_activity_data(instance)
        now: float = data["now"]
        current: float = data["value"]
        rate_tasks: dict[Task, float] = data.get("_rate_tasks", {})
        started_at: float | None = data.get("started_at", None)
        if started_at is None:
            # it's not currently active
            return None
        # no matter what, update the value
        curr_rate = sum(rate_tasks.values())

        last_calc_time: float = data.get("_last_time", now)
        elapsed = now - last_calc_time
        change = elapsed * curr_rate
        new_value = current + change

        # Task shows up from the activation
        if "task" in data:
            rate_to_add: float = data["rate"]
            task: Task = data["task"]
            if task in rate_tasks:
                raise UpstageError(
                    f"Duplicate task setting a rate {task}"
                    f"setting {self.name} on {instance}."
                    "You may have forgotten to deactivate."
                )
            rate_tasks[task] = rate_to_add

        self.__set__(instance, new_value)
        instance._set_active_state_data(
            state_name=self.name,
            started_at=now,
            _rate_tasks=rate_tasks,
            _last_time=now,
        )
        return new_value

    def deactivate(self, instance: Actor, task: Task | None = None) -> bool:
        """Deactivate the state.

        Args:
            instance (Actor): Actor the state is on
            task (Task): The task that is stopping its rate.

        Returns:
            bool: Still active or not
        """
        if task is None:
            raise UpstageError("Unexpected rate deactivation without a task.")
        data = self.get_activity_data(instance)
        rate_tasks: dict[Task, float] = data.get("_rate_tasks", {})
        # Since this state is ignoring the lock,
        # we can get here without it being active.
        if task not in rate_tasks:
            raise UpstageError(f"Task {task} is not changing {self.name} on {instance}")
        del rate_tasks[task]
        instance._set_active_state_data(
            state_name=self.name,
            _rate_tasks=rate_tasks,
        )
        # force a re-calculation
        getattr(instance, self.name)
        if rate_tasks:
            return True
        return False
